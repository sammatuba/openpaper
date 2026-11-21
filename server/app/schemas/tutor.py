"""The session state a tutor carries from one turn to the next.

The chat replays only the last few messages of a conversation to the model, so
a tutoring session cannot live in the transcript: the skill map shown ten
messages ago is already out of view. The tutor writes this state at the end of
every turn, it is stored on that assistant message under `trace["tutor"]`, and
the latest one is handed back on the next turn.

Everything here is written by a model, so validation repairs rather than
rejects: a level of 7 becomes 5, an unknown phase becomes "teaching". The one
thing that cannot be repaired is a state with no subskills, which is not a
state at all — callers treat that as no state and keep the previous one.
"""

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Key under Message.trace that holds a TutorState dump.
TUTOR_TRACE_KEY = "tutor"

MAX_LEVEL = 5
MAX_SUBSKILLS = 10
MAX_LINES = 12
MAX_NAME_CHARS = 140
MAX_LINE_CHARS = 300

PHASES = ("diagnostic", "teaching", "assessment", "complete")
DIFFICULTIES = ("easier", "normal", "harder")


def without_tutor_state(messages: List[dict]) -> List[dict]:
    """Formatted messages with the tutoring session taken out of their trace.

    For readers who are not the learner. A shared paper shows its chat, and a
    tutor's questions and the learner's answers are part of that; the tutor's
    private notes on what the learner gets wrong are not.
    """
    cleaned = []
    for message in messages:
        trace = message.get("trace")
        if isinstance(trace, dict) and TUTOR_TRACE_KEY in trace:
            rest = {
                key: value for key, value in trace.items() if key != TUTOR_TRACE_KEY
            }
            message = {**message, "trace": rest or None}
        cleaned.append(message)
    return cleaned


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _int(value: Any, low: int, high: int, default: int) -> int:
    try:
        return max(low, min(high, int(float(value))))
    except (TypeError, ValueError, OverflowError):
        # OverflowError: JSON admits Infinity and 1e999, and int() of either
        # raises it rather than ValueError.
        return default


def _lines(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    cleaned = [_text(item, MAX_LINE_CHARS) for item in value]
    # The newest lines are the ones kept. The tutor appends, so cutting from
    # the front of an over-long list loses old notes; cutting from the back
    # would refuse every new one from the thirteenth on, for good.
    return [line for line in cleaned if line][-MAX_LINES:]


class TutorSubskill(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    level: int = 0
    # Independent checks passed toward the next level since the level last
    # changed, and whether one of them was unprompted recall. Together they are
    # the evidence a level rise needs, kept here because the turns that
    # produced it will have scrolled out of the model's view.
    passes: int = 0
    unprompted: bool = False
    # Turn on which this subskill was last tested; what spaced review reads.
    last_checked: int = 0
    notes: str = ""

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, value: Any) -> str:
        return _text(value, MAX_NAME_CHARS)

    @field_validator("level", mode="before")
    @classmethod
    def _level(cls, value: Any) -> int:
        return _int(value, 0, MAX_LEVEL, 0)

    @field_validator("passes", mode="before")
    @classmethod
    def _passes(cls, value: Any) -> int:
        return _int(value, 0, 99, 0)

    @field_validator("unprompted", mode="before")
    @classmethod
    def _unprompted(cls, value: Any) -> bool:
        return value is True or str(value).strip().lower() == "true"

    @field_validator("last_checked", mode="before")
    @classmethod
    def _last_checked(cls, value: Any) -> int:
        return _int(value, 0, 1_000_000, 0)

    @field_validator("notes", mode="before")
    @classmethod
    def _notes(cls, value: Any) -> str:
        return _text(value, MAX_LINE_CHARS)


class TutorState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic: str = ""
    phase: str = "diagnostic"
    target_level: int = 4
    difficulty: str = "normal"
    # Name of the subskill being worked on, matching one in `subskills`.
    focus: Optional[str] = None
    subskills: List[TutorSubskill] = Field(default_factory=list)
    # Open misconceptions only; the tutor drops one once it is resolved.
    misconceptions: List[str] = Field(default_factory=list)
    # What has been explained or told outright, as opposed to demonstrated.
    covered: List[str] = Field(default_factory=list)
    diagnostic_asked: int = 0
    # Set by the server, never trusted from the model.
    turn: int = 0

    @field_validator("topic", mode="before")
    @classmethod
    def _topic(cls, value: Any) -> str:
        return _text(value, MAX_NAME_CHARS)

    @field_validator("phase", mode="before")
    @classmethod
    def _phase(cls, value: Any) -> str:
        phase = str(value or "").strip().lower()
        return phase if phase in PHASES else "teaching"

    @field_validator("target_level", mode="before")
    @classmethod
    def _target_level(cls, value: Any) -> int:
        return _int(value, 1, MAX_LEVEL, 4)

    @field_validator("difficulty", mode="before")
    @classmethod
    def _difficulty(cls, value: Any) -> str:
        difficulty = str(value or "").strip().lower()
        return difficulty if difficulty in DIFFICULTIES else "normal"

    @field_validator("focus", mode="before")
    @classmethod
    def _focus(cls, value: Any) -> Optional[str]:
        return _text(value, MAX_NAME_CHARS) or None

    @field_validator("subskills", mode="before")
    @classmethod
    def _subskills(cls, value: Any) -> list:
        if not isinstance(value, list):
            return []
        named = [
            item
            for item in value
            if isinstance(item, dict) and _text(item.get("name"), MAX_NAME_CHARS)
        ]
        return named[:MAX_SUBSKILLS]

    @field_validator("misconceptions", "covered", mode="before")
    @classmethod
    def _line_lists(cls, value: Any) -> List[str]:
        return _lines(value)

    @field_validator("diagnostic_asked", "turn", mode="before")
    @classmethod
    def _counters(cls, value: Any) -> int:
        return _int(value, 0, 1_000_000, 0)
