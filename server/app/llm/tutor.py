"""Tutor mode for the paper chat: the parts that are not the prompt.

A tutor turn ends with a state block the learner never reads. This module
lifts that block out of the answer stream, validates it, and builds the system
prompt that hands the previous one back. See app.schemas.tutor for why the
state exists at all.
"""

import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, Optional, Union

from app.llm.prompts import TUTOR_PAPER_SYSTEM_PROMPT
from app.schemas.tutor import TutorState
from pydantic import ValidationError

logger = logging.getLogger(__name__)

TUTOR_STATE_START = "---TUTOR-STATE---"
TUTOR_STATE_END = "---END-TUTOR-STATE---"


_WHOLE_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _load_object(raw: str) -> Optional[dict]:
    """`raw` as one JSON object, or None.

    The whole of it, start to end: a code fence is allowed only around the
    entire object. The lenient parser used elsewhere would also accept prose
    that merely contains a fenced JSON example, and here "is this a finished
    object" decides whether what follows is private.
    """
    text = raw.strip()
    fenced = _WHOLE_FENCE.fullmatch(text)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _as_state(data: Optional[dict]) -> Optional[TutorState]:
    if data is None:
        return None
    try:
        state = TutorState.model_validate(data)
    except ValidationError as exc:
        logger.warning("Unusable tutor state: %s", exc)
        return None
    if not state.subskills:
        logger.warning("Tutor state names no subskills; ignoring it.")
        return None
    return state


def parse_tutor_state(raw: str) -> Optional[TutorState]:
    """The state a tutor wrote, or None when it is not usable.

    None is an ordinary outcome, not an error: the caller keeps whatever state
    the session already had, and the tutor writes a fresh one next turn.
    """
    return _as_state(_load_object(raw))


def _is_complete_json(raw: str) -> bool:
    return _load_object(raw) is not None


# Keys only a session state has. One is enough to treat an object as one.
_STATE_KEYS = ("subskills", "misconceptions", "diagnostic_asked")
_STATE_KEY_IN_TEXT = re.compile(r'"(?:subskills|misconceptions|diagnostic_asked)"\s*:')
_MARKER_LINE = re.compile(
    r"^[ \t]*-{2,}[ \t]*(?:END[- _]?)?TUTOR[- _]?STATE[ \t]*-{2,}[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_EMPTY_FENCE = re.compile(r"```(?:json)?\s*```")


def scrub_unmarked_state(text: str) -> str:
    """`text` with any session state that arrived outside its markers removed.

    The markers are how the state is kept out of the learner's message, and a
    model can get them wrong: leave the opening one off, misspell it, write the
    object on its own. What it wrote then travels as ordinary reply text. This
    is the check on the way to storage, where a reply becomes something a
    shared paper shows: any JSON object carrying a state's keys is cut out,
    along with stray marker lines, and an unfinished one is cut to the end.

    It cannot catch a tutor that says its notes in plain sentences. Nothing
    can; the prompt asks it not to.
    """
    if not text or not _STATE_KEY_IN_TEXT.search(text):
        return text

    decoder = json.JSONDecoder()
    position = 0
    while True:
        start = text.find("{", position)
        if start == -1:
            break
        try:
            data, end = decoder.raw_decode(text, start)
        except ValueError:
            position = start + 1
            continue
        if isinstance(data, dict) and any(key in data for key in _STATE_KEYS):
            text = text[:start] + text[end:]
            position = start
        else:
            # Not a state itself; one may still be nested inside it.
            position = start + 1

    # What is left with a state's keys in it never closed: cut off by the
    # output limit, or not valid JSON. From its opening brace on, it goes.
    unfinished = _STATE_KEY_IN_TEXT.search(text)
    if unfinished:
        start = text.rfind("{", 0, unfinished.start())
        text = text[: start if start != -1 else unfinished.start()]

    text = _MARKER_LINE.sub("", text)
    text = _EMPTY_FENCE.sub("", text)
    return text.rstrip()


def scrub_citations(evidence: Optional[dict]) -> Optional[dict]:
    """A reply's citations with the same check applied to each quotation.

    A state written inside the evidence block, ahead of its closing marker,
    is read as part of the last quotation. Citations are stored and shared
    with the message, so they get the scrub the message gets. A quotation
    with nothing left is dropped.
    """
    if not evidence or not isinstance(evidence.get("citations"), list):
        return evidence
    kept = []
    changed = False
    for citation in evidence["citations"]:
        reference = citation.get("reference") if isinstance(citation, dict) else None
        if isinstance(reference, str):
            clean = scrub_unmarked_state(reference)
            if clean != reference:
                changed = True
                if not clean.strip():
                    continue
                citation = {**citation, "reference": clean}
        kept.append(citation)
    return {**evidence, "citations": kept} if changed else evidence


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
