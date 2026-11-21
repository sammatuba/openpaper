import asyncio
import logging
import re
import uuid
from typing import AsyncGenerator, Literal, Optional, Sequence, Union

from app.database.crud.conversation_crud import conversation_crud
from app.database.crud.paper_crud import paper_crud
from app.database.models import ConversableType, Paper
from app.llm.base import BaseLLMClient, ModelType
from app.llm.citation_handler import CitationHandler
from app.llm.json_parser import JSONParser
from app.llm.prompts import (
    ANSWER_PAPER_QUESTION_SYSTEM_PROMPT,
    ANSWER_PAPER_QUESTION_USER_MESSAGE,
    CONCISE_MODE_INSTRUCTIONS,
    DETAILED_MODE_INSTRUCTIONS,
    GENERATE_NARRATIVE_SUMMARY,
    NORMAL_MODE_INSTRUCTIONS,
    TUTOR_PAPER_USER_MESSAGE,
)
from app.llm.provider import FileContent, LLMProvider, TextContent
from app.llm.tutor import build_tutor_system_prompt, next_turn, split_tutor_state
from app.llm.utils import LLMBlockedError, retry_llm_operation
from app.schemas.message import ResponseStyle
from app.schemas.responses import AudioOverviewForLLM
from app.schemas.user import CurrentUser
from fastapi import Depends
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.database.crud.message_crud import message_crud
from app.database.database import get_db
from app.helpers.s3 import s3_service


class PaperNotFoundError(ValueError):
    """The paper asked about doesn't exist, or doesn't belong to the user."""


class PaperOperations(BaseLLMClient):
    """Operations related to paper analysis and chat functionality"""

    @retry_llm_operation(max_retries=3, delay=1.0)
    def create_narrative_summary(
        self,
        paper_id: str,
        user: CurrentUser,
        length: Optional[Literal["short", "medium", "long"]] = "medium",
        additional_instructions: Optional[str] = None,
        db: Session = Depends(get_db),
    ) -> AudioOverviewForLLM:
        """
        Create a narrative summary of the paper using the specified model
        """
        paper = paper_crud.get(db, id=paper_id, user=user)

        if not paper:
            raise ValueError(f"Paper with ID {paper_id} not found.")

        # Word count targets for audio durations at ~150 words/min
        # short: ~3 min, medium: ~7 min, long: ~14 min
        word_count_map = {
            "short": 450,
            "medium": 1000,
            "long": 2000,
        }

        formatted_prompt = GENERATE_NARRATIVE_SUMMARY.format(
            additional_instructions=additional_instructions,
            length=word_count_map.get(str(length), word_count_map["medium"]),
        )

        pdf_bytes = s3_service.download_bytes(str(paper.s3_object_key))

        message_content = [
            FileContent(
                data=pdf_bytes,
                mime_type="application/pdf",
                filename=f"{paper.title or 'paper'}.pdf",
                text_fallback=str(paper.raw_content) if paper.raw_content else None,
            ),
            TextContent(text=formatted_prompt),
        ]

        # Generate narrative summary using the LLM
        try:
            response = self.generate_content(
                contents=message_content,
                schema=AudioOverviewForLLM,
            )
        except LLMBlockedError as e:
            # Narrating a whole paper is the longest single generation we ask
            # for, which makes it the most likely to wander into a stretch the
            # model has memorized and trip Gemini's recitation filter. That
            # verdict is a property of the sampled continuation, not of the
            # request, so one fresh draw usually clears it — unlike a safety or
            # blocklist verdict, which is stable and gets re-raised as-is.
            if not e.is_recitation:
                raise
            logger.warning(
                f"Recitation block on narrative summary for paper {paper_id}; resampling once."
            )
            response = self.generate_content(
                contents=message_content,
                schema=AudioOverviewForLLM,
            )

        try:
            if response and response.text:
                # Parse the response text as JSON
                response_json = JSONParser.validate_and_extract_json(response.text)
                # Validate against the AudioOverview schema
                audio_overview = AudioOverviewForLLM.model_validate(response_json)
                return audio_overview
            else:
                raise ValueError("Empty response from LLM.")
        except ValueError as e:
            logger.error(f"Error parsing LLM response: {e}", exc_info=True)
            raise ValueError(f"Invalid response from LLM: {str(e)}")

    async def chat_with_paper(
        self,
        paper_id: str,
        conversation_id: str,
        question: str,
        current_user: CurrentUser,
        llm_provider: Optional[LLMProvider] = None,
        user_references: Optional[Sequence[str]] = None,
        response_style: Optional[str] = "normal",
        model_type: ModelType = ModelType.DEFAULT,
        db: Session = Depends(get_db),
    ) -> AsyncGenerator[Union[str, dict], None]:
        """
        Chat with the paper using the specified model
        """

        user_citations = (
            CitationHandler.convert_references_to_citations(user_references)
            if user_references
            else None
        )

        paper: Paper = paper_crud.get(db, id=paper_id, user=current_user)

        if not paper:
            raise PaperNotFoundError(f"Paper with ID {paper_id} not found.")

        casted_conversation_id = uuid.UUID(conversation_id)

        # An ordinary answer is something a shared paper shows, so it is
        # written without sight of the paper's tutoring turns: it cannot
        # repeat what it was never given. The tutor reads everything.
        conversation_history = message_crud.get_conversation_messages(
            db,
            conversation_id=casted_conversation_id,
            current_user=current_user,
            shareable_only=response_style != ResponseStyle.TUTOR,
        )

        question_with_citations = (
            f"{question}\n\n{user_citations}" if user_citations else question
        )

        # Set only on a tutor turn: the number that turn will carry.
        tutor_turn: Optional[int] = None

        if response_style == ResponseStyle.TUTOR:
            # A tutor turn leaves the learner's session state on the message it
            # is saved to, so it may only go to this paper's own conversation,
            # which nobody else reads. The request names the paper and the
            # conversation separately; a project conversation named here would
            # put that state in front of the project's other members.
            conversation = conversation_crud.get_conversation_by_id(
                db, conversation_id=casted_conversation_id, user_id=current_user.id
            )
            if (
                conversation is None
                or conversation.conversable_type != ConversableType.PAPER
                or str(conversation.conversable_id) != str(paper.id)
            ):
                raise ValueError("Tutor mode works in this paper's own conversation.")

            # The session does not live in the transcript — only the last few
            # messages are replayed — so it is read back from where the last
            # tutor turn stored it.
            tutor_state = message_crud.get_latest_tutor_state(
                db, conversation_id=casted_conversation_id, current_user=current_user
            )
            tutor_turn = next_turn(tutor_state)
            formatted_system_prompt = build_tutor_system_prompt(tutor_state)
            formatted_prompt = TUTOR_PAPER_USER_MESSAGE.format(
                message=question_with_citations
            )
        else:
            if response_style == ResponseStyle.DETAILED:
                additional_instructions = DETAILED_MODE_INSTRUCTIONS
            elif response_style == ResponseStyle.CONCISE:
                additional_instructions = CONCISE_MODE_INSTRUCTIONS
            else:
                additional_instructions = NORMAL_MODE_INSTRUCTIONS

            formatted_system_prompt = ANSWER_PAPER_QUESTION_SYSTEM_PROMPT.format(
                additional_instructions=additional_instructions,
            )
            formatted_prompt = ANSWER_PAPER_QUESTION_USER_MESSAGE.format(
                question=question_with_citations,
            )

        # This runs inside an async generator, so the blocking download goes to
        # a thread: run inline, a multi-megabyte PDF stalls the whole worker's
        # event loop, including every other user's in-flight LLM stream.
        pdf_bytes = await asyncio.to_thread(
            s3_service.download_bytes, str(paper.s3_object_key)
        )

        answer = self._stream_paper_answer(
            message=[TextContent(text=formatted_prompt)],
            file=FileContent(
                data=pdf_bytes,
                mime_type="application/pdf",
                filename=f"{paper.title or 'paper'}.pdf",
                text_fallback=str(paper.raw_content) if paper.raw_content else None,
            ),
            system_prompt=formatted_system_prompt,
            history=conversation_history,
            llm_provider=llm_provider,
            model_type=model_type,
            tutor_turn=tutor_turn,
        )

        async for chunk in answer:
            yield chunk

    async def _model_text(
        self,
        *,
        message: list,
        file: FileContent,
        system_prompt: str,
        history: list,
        llm_provider: Optional[LLMProvider],
        model_type: ModelType,
    ) -> AsyncGenerator[dict, None]:
        """The model's raw answer as "content" and "reset" events."""
        async for chunk in self.send_message_stream(
            message=message,
            file=file,
            system_prompt=system_prompt,
            history=history,
            provider=llm_provider,
            model_type=model_type,
        ):
            if chunk.is_restart:
                yield {"type": "reset", "content": ""}
                continue

            logger.debug(f"Received chunk: {chunk.text}")

            if chunk.text:
                yield {"type": "content", "content": chunk.text}

    async def _stream_paper_answer(
        self,
        *,
        message: list,
        file: FileContent,
        system_prompt: str,
        history: list,
        llm_provider: Optional[LLMProvider],
        model_type: ModelType,
        tutor_turn: Optional[int] = None,
    ) -> AsyncGenerator[Union[str, dict], None]:
        """Stream one answer about a paper, splitting its evidence block off.

        Yields "content" chunks for what the reader sees, one "references"
        chunk for the evidence block, and "reset" when the upstream request was
        re-sent and everything so far should be discarded. On a tutor turn
        (`tutor_turn` set) it also yields one "tutor_state" chunk.
        """
        evidence_buffer: list[str] = []
        text_buffer: str = ""
        in_evidence_section = False

        START_DELIMITER = "---EVIDENCE---"
        END_DELIMITER = "---END-EVIDENCE---"

        source: AsyncGenerator[Union[str, dict], None] = self._model_text(
            message=message,
            file=file,
            system_prompt=system_prompt,
            history=history,
            llm_provider=llm_provider,
            model_type=model_type,
        )
        if tutor_turn is not None:
            # The tutor's state comes out of the raw text before anything
            # reads it as evidence. Done the other way round, a reply that
            # forgot to close its evidence block would carry the state into a
            # citation, and citations are shown to whoever the paper is
            # shared with.
            source = split_tutor_state(source, turn=tutor_turn)

        async for event in source:
            if not isinstance(event, dict):
                continue

            if event.get("type") == "reset":
                # The upstream connection dropped mid-answer and the request was
                # re-sent. The partial answer is not resumable, so drop the
                # parse state and tell the client to clear what it rendered.
                evidence_buffer = []
                text_buffer = ""
                in_evidence_section = False
                yield {"type": "reset", "content": ""}
                continue

            if event.get("type") != "content":
                # A tutor turn's state. Not text, so not parsed.
                yield event
                continue

            text = event.get("content")

            if not text:
                continue

            text_buffer += text

            if in_evidence_section:
                evidence_buffer.append(text_buffer)
                text_buffer = ""
            elif START_DELIMITER in text_buffer:
                in_evidence_section = True
                # Yield what came before the delimiter; the rest opens the
                # evidence buffer.
                pre_evidence, _, opening = text_buffer.partition(START_DELIMITER)
                if pre_evidence:
                    yield {"type": "content", "content": pre_evidence}
                evidence_buffer = [opening]
                text_buffer = ""

            if in_evidence_section:
                # Looked for in the same pass that opened the block, not only
                # when a later chunk arrives: a block that opens and closes in
                # the stream's last chunk used to be dropped whole.
                evidence_text = "".join(evidence_buffer)
                delimiter_pos = evidence_text.find(END_DELIMITER)
                if delimiter_pos == -1:
                    continue

                structured_evidence = CitationHandler.parse_evidence_block(
                    evidence_text[:delimiter_pos]
                )
                yield {
                    "type": "references",
                    "content": {
                        "citations": structured_evidence,
                    },
                }

                # Whatever followed the block goes back into the text buffer,
                # exactly as it arrived, and leaves through the ordinary path
                # below. Two things used to go wrong here. It was yielded now
                # and again when the buffer flushed, so it showed twice. And it
                # was cut from a stripped copy of the buffer, so a chunk ending
                # in a space lost that space and joined two words.
                in_evidence_section = False
                evidence_buffer = []
                text_buffer = evidence_text[delimiter_pos + len(END_DELIMITER) :]

            # Keep a reasonable buffer size for detecting delimiters
            if len(text_buffer) > len(START_DELIMITER) * 2:
                to_yield = text_buffer[: -len(START_DELIMITER)]
                yield {"type": "content", "content": to_yield}
                text_buffer = text_buffer[-len(START_DELIMITER) :]

        # A block the stream ended inside is dropped, as it always was: its last
        # quotation is cut off wherever the output stopped, and a cut-off
        # quotation presented as the paper's words is worse than none.

        if text_buffer:
            yield {"type": "content", "content": text_buffer}
