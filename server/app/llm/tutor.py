"""Tutor mode for the paper chat: the parts that are not the prompt.

A tutor turn ends with a state block the learner never reads. This module
lifts that block out of the answer stream, validates it, and builds the system
prompt that hands the previous one back. See app.schemas.tutor for why the
state exists at all.
"""

import json
import logging
from typing import Any, AsyncGenerator, Dict, Optional, Union

from app.llm.json_parser import JSONParser
from app.llm.prompts import TUTOR_PAPER_SYSTEM_PROMPT
from app.schemas.tutor import TutorState
from pydantic import ValidationError

logger = logging.getLogger(__name__)

TUTOR_STATE_START = "---TUTOR-STATE---"
TUTOR_STATE_END = "---END-TUTOR-STATE---"


def parse_tutor_state(raw: str) -> Optional[TutorState]:
    """The state a tutor wrote, or None when it is not usable.

    None is an ordinary outcome, not an error: the caller keeps whatever state
    the session already had, and the tutor writes a fresh one next turn.
    """
    try:
        data = JSONParser.validate_and_extract_json(raw)
        if not isinstance(data, dict):
            return None
        state = TutorState.model_validate(data)
    except (ValueError, ValidationError) as exc:
        logger.warning("Unusable tutor state block: %s", exc)
        return None
    if not state.subskills:
        logger.warning("Tutor state block names no subskills; ignoring it.")
        return None
    return state


def _is_complete_json(raw: str) -> bool:
    try:
        JSONParser.validate_and_extract_json(raw)
    except ValueError:
        return False
    return True


def next_turn(previous: Optional[Dict[str, Any]]) -> int:
    try:
        return int((previous or {}).get("turn") or 0) + 1
    except (TypeError, ValueError):
        return 1


def build_tutor_system_prompt(previous: Optional[Dict[str, Any]]) -> str:
    """The tutor instructions followed by where this session stands."""
    turn = next_turn(previous)
    if not previous:
        # A first turn whose state block was lost leaves no state either, and
        # telling the tutor flatly to start would have it re-open a diagnostic
        # the learner is already answering.
        session = (
            "No session state is stored for this conversation. "
            f"This is turn {turn}. If the conversation above shows no tutoring "
            "yet, start a session. If it shows you already tutoring — your "
            "questions, the learner's answers — then your state from those "
            "turns was lost: rebuild it from what you can see and carry on "
            "from there instead of starting again."
        )
    else:
        session = (
            f"This is turn {turn} of a session already under way. The last "
            "state you stored:\n\n"
            f"{json.dumps(previous, ensure_ascii=False)}\n\n"
            "The learner's message is normally their answer to your last "
            "question in the conversation above. If the conversation went "
            "somewhere else in between, pick the session back up from this "
            "state rather than starting again. If the conversation shows "
            "tutor turns of yours that this state does not reflect, it missed "
            "them: bring it up to date from what you can see."
        )
    return f"{TUTOR_PAPER_SYSTEM_PROMPT}\n## Session state\n{session}\n"


def _held_back(text: str, marker: str) -> int:
    """Length of the longest tail of `text` that could be the start of `marker`.

    That tail has to wait for the next chunk: released now, the first half of a
    marker split across two chunks would reach the learner as visible text.
    """
    for size in range(min(len(text), len(marker) - 1), 0, -1):
        if text.endswith(marker[:size]):
            return size
    return 0


async def split_tutor_state(
    source: AsyncGenerator[Union[str, dict], None],
    *,
    turn: int,
) -> AsyncGenerator[Union[str, dict], None]:
    """Pass an answer stream through, lifting the tutor's state block out of it.

    Content before and after the block is yielded as content; the block itself
    becomes one `tutor_state` chunk carrying the validated state, stamped with
    this turn's number. A block that does not parse is dropped silently — the
    learner's message is already complete without it.

    It fails closed. Once the opening marker has been seen, nothing is visible
    again until a closing marker arrives with complete JSON in front of it. A
    closing marker that turns up inside the JSON (in a note, say) or after
    something that is not JSON does not end the block, so neither the tail of
    a state nor a malformed one can spill into the learner's message, which is
    what a shared paper shows. The price is that whatever followed a malformed
    block that turn, citations included, is dropped with it.
    """
    buffer = ""
    inside = False
    # Where to look for the next closing marker; past any already ruled out.
    scan_from = 0

    def emit(raw: str) -> Optional[dict]:
        state = parse_tutor_state(raw)
        if state is None:
            return None
        state.turn = turn
        return {"type": "tutor_state", "content": state.model_dump()}

    async for chunk in source:
        if not isinstance(chunk, dict) or chunk.get("type") not in ("content", "reset"):
            yield chunk
            continue

        if chunk["type"] == "reset":
            # The answer is being re-sent from scratch; so is its state block.
            buffer = ""
            inside = False
            scan_from = 0
            yield chunk
            continue

        buffer += str(chunk.get("content") or "")

        while True:
            if inside:
                end = buffer.find(TUTOR_STATE_END, scan_from)
                if end == -1:
                    break
                raw = buffer[:end]
                if not _is_complete_json(raw):
                    scan_from = end + len(TUTOR_STATE_END)
                    continue
                buffer = buffer[end + len(TUTOR_STATE_END) :]
                inside = False
                scan_from = 0
                state_chunk = emit(raw)
                if state_chunk:
                    yield state_chunk
                continue

            start = buffer.find(TUTOR_STATE_START)
            if start == -1:
                keep = _held_back(buffer, TUTOR_STATE_START)
                visible, buffer = (
                    buffer[: len(buffer) - keep],
                    buffer[len(buffer) - keep :],
                )
                if visible:
                    yield {"type": "content", "content": visible}
                break
            if start:
                yield {"type": "content", "content": buffer[:start]}
            buffer = buffer[start + len(TUTOR_STATE_START) :]
            inside = True

    if inside:
        # No closing marker ended the block: cut off by the output limit, or
        # malformed. The JSON may still be whole; if not, parse_tutor_state
        # says so. Either way none of it is shown.
        state_chunk = emit(buffer)
        if state_chunk:
            yield state_chunk
    elif buffer:
        # A tail that looked like the start of a marker and never became one.
        yield {"type": "content", "content": buffer}
