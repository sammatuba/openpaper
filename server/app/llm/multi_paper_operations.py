import asyncio
import json
import logging
import uuid
from contextlib import suppress
from typing import AsyncGenerator, List, Literal, Optional, Sequence, Union

from app.database.crud.message_crud import message_crud
from app.database.crud.paper_crud import paper_crud
from app.database.crud.projects.project_crud import project_crud
from app.database.crud.projects.project_paper_crud import project_paper_crud
from app.database.database import get_db
from app.database.models import Paper
from app.llm.base import ModelType
from app.llm.citation_handler import CitationHandler
from app.llm.evidence_operations import EvidenceOperations
from app.llm.json_parser import JSONParser
from app.llm.prompts import (
    ANSWER_EVIDENCE_BASED_QUESTION_MESSAGE,
    ANSWER_EVIDENCE_BASED_QUESTION_SYSTEM_PROMPT,
    GENERATE_MULTI_PAPER_NARRATIVE_SUMMARY,
    TUTOR_PAPER_USER_MESSAGE,
    format_scope,
)
from app.llm.provider import LLMProvider, StreamChunk, SupplementaryContent, TextContent
from app.llm.tutor import (
    build_project_tutor_system_prompt,
    next_turn,
    split_tutor_state,
)
from app.llm.utils import retry_llm_operation
from app.schemas.artifact import CitationArtifactPayload
from app.schemas.message import EvidenceCollection
from app.schemas.responses import AudioOverviewForLLM
from app.schemas.tutor import restrict_path_papers
from app.schemas.user import CurrentUser
from fastapi import Depends
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class MultiPaperOperations(EvidenceOperations):
    """Operations related to multi-paper analysis and chat functionality.

    Inherits evidence gathering and compaction methods from EvidenceOperations.
    """

    async def chat_with_papers(
        self,
        conversation_id: str,
        question: str,
        current_user: CurrentUser,
        all_papers: List[Paper],
        evidence_gathered: EvidenceCollection,
        llm_provider: Optional[LLMProvider] = None,
        user_references: Optional[Sequence[str]] = None,
        mentioned_highlights: Optional[List[dict]] = None,
        project_title: Optional[str] = None,
        is_mention_scoped: bool = False,
        is_tutor_turn: bool = False,
        tutor_state: Optional[dict] = None,
        db: Session = Depends(get_db),
    ) -> AsyncGenerator[Union[str, dict], None]:
        """
        Chat with everything in the user's knowledge base using the specified model

        `project_title` and `is_mention_scoped` describe the set of papers this
        answer is being written about. They are the same inputs the gathering
        loop was given, so the answer names the container the search actually
        covered — a project by its title rather than "the library".

        On a tutor turn (`is_tutor_turn`) the model teaches the set instead of
        answering, from the session in `tutor_state` (None when none has
        started), and the stream also carries one "tutor_state" chunk. The
        caller decides whether a tutor turn is allowed here; see the endpoint.
        """
        user_citations = (
            CitationHandler.convert_references_to_citations(user_references)
            if user_references
            else None
        )

        casted_conversation_id = uuid.UUID(conversation_id)

        # An ordinary answer in a project conversation is read by the
        # project's members, so it is written without sight of the
        # conversation's tutoring turns: it cannot repeat what it was never
        # given. The tutor reads everything.
        conversation_history = message_crud.get_conversation_messages(
            db,
            conversation_id=casted_conversation_id,
            current_user=current_user,
            shareable_only=not is_tutor_turn,
        )

        formatted_paper_options = {
            str(paper.id): str(paper.title) for paper in all_papers
        }

        logger.debug(f"Evidence gathered: {evidence_gathered.get_evidence_dict()}")

        scope = format_scope(
            n_papers=len(all_papers),
            project_title=project_title,
            is_mention_scoped=is_mention_scoped,
        )
        question_with_citations = (
            f"{question}\n\n{user_citations}" if user_citations else question
        )

        # Set only on a tutor turn: the number that turn will carry.
        tutor_turn: Optional[int] = None

        if is_tutor_turn:
            tutor_turn = next_turn(tutor_state)
            formatted_system_prompt = build_project_tutor_system_prompt(
                tutor_state,
                scope=scope,
                papers={
                    str(paper.id): {
                        "title": paper.title,
                        "authors": paper.authors,
                        "published": paper.publish_date,
                    }
                    for paper in all_papers
                },
            )
            formatted_prompt = TUTOR_PAPER_USER_MESSAGE.format(
                message=question_with_citations
            )
        else:
            formatted_system_prompt = (
                ANSWER_EVIDENCE_BASED_QUESTION_SYSTEM_PROMPT.format(
                    scope=scope,
                    available_papers=formatted_paper_options,
                )
            )
            formatted_prompt = ANSWER_EVIDENCE_BASED_QUESTION_MESSAGE.format(
                question=question_with_citations,
            )

        # Build multipart message: supplementary evidence + user question
        message_content = [
            SupplementaryContent(
                content=json.dumps(evidence_gathered.get_evidence_dict(), indent=2),
                label="collected_evidence",
            ),
            TextContent(text=formatted_prompt),
        ]

        # @-mentioned highlights are exact passages the user attached to ground
        # this question. Inject them directly so the answer model always sees
        # them, regardless of what evidence gathering happened to retrieve.
        if mentioned_highlights:
            message_content.insert(
                0,
                SupplementaryContent(
                    content=json.dumps(mentioned_highlights, indent=2),
                    label="mentioned_highlights",
                ),
            )

        # Surface any citation artifacts produced during evidence gathering as
        # first-party cards, and give the answer model the resolved data so it
        # can reference (but not re-paste) them.
        citation_artifacts = evidence_gathered.get_artifacts()
        if citation_artifacts:
            artifact_payloads = [
                CitationArtifactPayload.from_result(artifact).model_dump()
                for artifact in citation_artifacts
            ]
            message_content.insert(
                1,
                SupplementaryContent(
                    content=json.dumps(artifact_payloads, indent=2),
                    label="resolved_citations",
                ),
            )
            for payload in artifact_payloads:
                yield {"type": "artifact", "content": payload}

        # What the turn actually did. Gathering replays its tool results to
        # itself and they stop there, so anything whose outcome is not evidence
        # — a queued chart above all — reaches this model only if it is stated.
        actions = evidence_gathered.describe_actions()
        if actions:
            message_content.insert(
                1,
                SupplementaryContent(
                    content=json.dumps(actions, indent=2),
                    label="actions_taken_this_turn",
                ),
            )

        source: AsyncGenerator[dict, None] = self._model_events(
            message=message_content,
            system_prompt=formatted_system_prompt,
            history=conversation_history,
            llm_provider=llm_provider,
        )
        if tutor_turn is not None:
            # The tutor's state comes out of the raw text before anything
            # reads it as evidence. Done the other way round, a reply that
            # forgot to close its evidence block would carry the state into a
            # citation.
            source = split_tutor_state(source, turn=tutor_turn, project=True)

        allowed_paper_ids = set(formatted_paper_options)
        async for event in self._split_evidence(source, evidence_gathered):
            if event.get("type") == "tutor_state":
                event = {
                    **event,
                    "content": restrict_path_papers(
                        event["content"], allowed_paper_ids
                    ),
                }
            yield event

    async def _model_events(
        self,
        *,
        message: list,
        system_prompt: str,
        history: list,
        llm_provider: Optional[LLMProvider],
    ) -> AsyncGenerator[dict, None]:
        """The model's raw answer as "content" and "reset" events.

        Also "status" until the answer starts, so the user can see the turn is
        still working, and one "error" in place of an exception if the stream
        fails: the caller then stops, and shows nothing it was still holding.
        """
        queue: asyncio.Queue = asyncio.Queue()

        async def pinger():
            """Shows the user the turn is still working until the answer
            starts, then is cancelled. Not what keeps the connection alive —
            the message api does that, for the whole turn rather than only up
            to the first chunk."""
            with suppress(asyncio.CancelledError):
                while True:
                    await queue.put(
                        {"type": "status", "content": "Finalizing thoughts..."}
                    )
                    await asyncio.sleep(5)

        async def stream_reader():
            """Reads from the LLM stream and puts chunks into the queue."""
            try:
                async for chunk in self.send_message_stream(
                    message=message,
                    system_prompt=system_prompt,
                    history=history,
                    provider=llm_provider,
                ):
                    await queue.put(chunk)
            finally:
                await queue.put(None)

        pinger_task = asyncio.create_task(pinger())
        stream_reader_task = asyncio.create_task(stream_reader())

        first_chunk_received = False

        try:
            while True:
                item = await queue.get()
                if item is None:  # Stream is done
                    break

                if isinstance(item, dict) and item.get("type") == "status":
                    yield item
                    continue

                if not first_chunk_received:
                    pinger_task.cancel()
                    first_chunk_received = True

                chunk: StreamChunk = item  # type: ignore

                if chunk.is_restart:
                    # The upstream connection dropped mid-answer and the request
                    # was re-sent. The partial answer is not resumable, so tell
                    # everything downstream to drop what it holds.
                    yield {"type": "reset", "content": ""}
                    continue

                logger.debug(f"Received chunk: {chunk.text}")

                if chunk.text:
                    yield {"type": "content", "content": chunk.text}
        finally:
            if not pinger_task.done():
                pinger_task.cancel()
            if not stream_reader_task.done():
                stream_reader_task.cancel()

        # Check if stream_reader_task raised an exception
        if stream_reader_task.done() and not stream_reader_task.cancelled():
            exc = stream_reader_task.exception()
            if exc is not None:
                logger.error(f"Stream reader task failed with exception: {exc}")
                yield {
                    "type": "error",
                    "content": "Sorry, an error occurred while working on this response. Please try again or contact support (saba@openpaper.ai) if the issue persists.",
                }

    async def _split_evidence(
        self,
        source: AsyncGenerator[dict, None],
        evidence_gathered: EvidenceCollection,
    ) -> AsyncGenerator[dict, None]:
        """Pass an answer through, turning its evidence block into citations.

        Yields "content" for what the reader sees and one "references" chunk
        for the block. "reset" discards what is held and is passed on. An
        "error" is passed on and ends the answer. Anything else (a status, a
        tutor turn's state) is not text, and passes straight through.
        """
        evidence_buffer: list[str] = []
        text_buffer: str = ""
        in_evidence_section = False

        START_DELIMITER = "---EVIDENCE---"
        END_DELIMITER = "---END-EVIDENCE---"

        def citations_in(block: str) -> list:
            structured_evidence = CitationHandler.parse_multi_paper_evidence_block(
                block
            )
            # Resolve compacted citations to original snippets if evidence was compacted
            if evidence_gathered.is_compacted:
                structured_evidence = CitationHandler.resolve_compacted_citations(
                    structured_evidence,
                    evidence_gathered.citation_index,
                )
            return structured_evidence

        async for event in source:
            if not isinstance(event, dict):
                continue

            kind = event.get("type")

            if kind == "reset":
                evidence_buffer = []
                text_buffer = ""
                in_evidence_section = False
                yield {"type": "reset", "content": ""}
                continue

            if kind == "error":
                yield event
                return

            if kind != "content":
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
                # Looked for in the same pass that opened the block, so a
                # block that opens and closes in one chunk is not missed.
                evidence_text = "".join(evidence_buffer)
                delimiter_pos = evidence_text.find(END_DELIMITER)
                if delimiter_pos == -1:
                    continue

                yield {
                    "type": "references",
                    "content": {
                        "citations": citations_in(evidence_text[:delimiter_pos]),
                    },
                }

                # Whatever followed the block goes back into the text buffer,
                # exactly as it arrived, and leaves through the ordinary path
                # below. Two things used to go wrong here, as they did in the
                # paper chat. It was yielded now and again when the buffer
                # flushed, so it showed twice. And it was cut from a stripped
                # copy of the buffer, so a chunk ending in a space lost that
                # space and joined two words.
                in_evidence_section = False
                evidence_buffer = []
                text_buffer = evidence_text[delimiter_pos + len(END_DELIMITER) :]

            # Keep a reasonable buffer size for detecting delimiters
            if len(text_buffer) > len(START_DELIMITER) * 2:
                to_yield = text_buffer[: -len(START_DELIMITER)]
                yield {"type": "content", "content": to_yield}
                text_buffer = text_buffer[-len(START_DELIMITER) :]

        # Handle case where stream ended while still in evidence section
        if in_evidence_section:
            unclosed = "".join(evidence_buffer).strip()
            logger.warning(
                "Stream ended while in evidence section without END_DELIMITER"
            )

            if unclosed:
                try:
                    yield {
                        "type": "references",
                        "content": {
                            "citations": citations_in(unclosed),
                        },
                    }
                except Exception as e:
                    logger.error(f"Failed to parse incomplete evidence block: {e}")
                    yield {"type": "content", "content": unclosed}
            return

        # Yield any remaining text buffer content
        if text_buffer:
            yield {"type": "content", "content": text_buffer}

    @retry_llm_operation(max_retries=3, delay=1.0)
    async def create_multi_paper_narrative_summary(
        self,
        current_user: CurrentUser,
        additional_instructions: Optional[str] = None,
        length: Optional[Literal["short", "medium", "long"]] = "medium",
        project_id: Optional[str] = None,
        db: Session = Depends(get_db),
    ) -> AudioOverviewForLLM:
        """
        Create a narrative summary across multiple papers using evidence gathering
        """
        evidence_collection: Optional[EvidenceCollection] = None

        summary_request = (
            additional_instructions
            or "Provide a comprehensive narrative summary of the key findings, contributions, and insights from the papers in this collection. Synthesize the information to highlight overarching themes and significant advancements."
        )

        # Word count targets for audio durations at ~150 words/min
        # short: ~3 min, medium: ~7 min, long: ~14 min
        word_count_map = {
            "short": 450,
            "medium": 1000,
            "long": 2000,
        }

        # Use the existing evidence gathering system
        async for result in self.gather_evidence(
            question=f"{summary_request}",
            current_user=current_user,
            llm_provider=LLMProvider.GEMINI,
            project_id=project_id,
            db=db,
        ):
            if result.get("type") == "evidence_gathered":
                evidence_collection = result.get("content")
                break

        if evidence_collection is None:
            evidence_collection = EvidenceCollection()

        # Get paper metadata for context
        if project_id:
            project = project_crud.get(db, id=project_id, user=current_user)
            if not project:
                raise ValueError("Project not found.")
            all_papers = project_paper_crud.get_all_papers_by_project_id(
                db, project_id=uuid.UUID(project_id), user=current_user
            )
        else:
            all_papers = paper_crud.get_all_available_papers(db, user=current_user)

        paper_metadata = {
            str(paper.id): {
                "title": paper.title,
                "authors": paper.authors,
                "published": paper.publish_date,
            }
            for paper in all_papers
        }

        formatted_prompt = GENERATE_MULTI_PAPER_NARRATIVE_SUMMARY.format(
            summary_request=summary_request,
            evidence_gathered=evidence_collection.get_evidence_dict(),
            length=word_count_map.get(str(length), word_count_map["medium"]),
            paper_metadata=paper_metadata,
            additional_instructions=additional_instructions or "",
        )

        message_content = [TextContent(text=formatted_prompt)]

        response = self.generate_content(
            contents=message_content,
            model_type=ModelType.DEFAULT,
            provider=LLMProvider.GEMINI,
            schema=AudioOverviewForLLM,
        )

        try:
            if response and response.text:
                response_json = JSONParser.validate_and_extract_json(response.text)
                audio_overview = AudioOverviewForLLM.model_validate(response_json)
                return audio_overview
            else:
                raise ValueError("Empty response from LLM.")
        except ValueError as e:
            logger.error(f"Error parsing LLM response: {e}", exc_info=True)
            raise ValueError(f"Invalid response from LLM: {str(e)}")
