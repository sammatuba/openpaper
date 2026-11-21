"""The session state a tutor carries from one turn to the next.

The chat replays only the last few messages of a conversation to the model, so
a tutoring session cannot live in the transcript: the skill map shown ten
messages ago is already out of view. The tutor writes this state at the end of
every turn, it is stored on that assistant message under `trace["tutor"]`, and
the latest one is handed back on the next turn.

A project conversation has the same mode. Its state also holds a study path
(`TutorState.path`): several papers need an order to be taken in, which one
paper does not.

Everything here is written by a model, so validation repairs rather than
rejects: a level of 7 becomes 5, an unknown phase becomes "teaching". The one
thing that cannot be repaired is a state with no subskills, which is not a
state at all — callers treat that as no state and keep the previous one.
"""

from typing import Any, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Key under Message.trace that holds a TutorState dump.
TUTOR_TRACE_KEY = "tutor"
# Key under Message.trace that marks a message, the learner's or the tutor's,
# as part of a tutoring turn. A tutoring session is the learner's: its turns
# are left out of what a shared paper shows. That is decided by this mark and
# not by inspecting what the tutor wrote, because no inspection can tell a
# reply that is safe to show from one in which the model put its notes on the
# learner somewhere they should not be.
TUTOR_TURN_KEY = "tutor_turn"


def tutor_turn_trace(state: Optional[dict] = None) -> dict:
    """The trace a message of a tutoring turn is saved with."""
    trace: dict = {TUTOR_TURN_KEY: True}
    if state:
        trace[TUTOR_TRACE_KEY] = state
    return trace


MAX_LEVEL = 5
MAX_SUBSKILLS = 10
MAX_LINES = 12
MAX_NAME_CHARS = 140
MAX_LINE_CHARS = 300
# A study path, which only a project session has: the order the tutor means
# to take the papers in.
MAX_UNITS = 12
MAX_UNIT_PAPERS = 8
MAX_PAPER_ID_CHARS = 64
# What a project tutor asks to have read before its next turn.
MAX_FETCH_LINES = 6

PHASES = ("diagnostic", "teaching", "assessment", "complete")
DIFFICULTIES = ("easier", "normal", "harder")
UNIT_STATUSES = ("todo", "current", "done")


def without_tutor_state(messages: List[dict]) -> List[dict]:
    """Formatted messages with the tutoring session taken out of their trace.

    For readers who are not the learner. The second line of defence: the
    queries behind a shared paper and behind a project conversation read by
    another member already leave tutoring turns out altogether, so no message
    that reaches a reader this way should carry a session. If one does, it is
    not handed out.
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


def restrict_path_papers(state: dict, allowed_paper_ids: Iterable[str]) -> dict:
    """A dumped state whose study path names only papers of the project.

    The tutor writes paper ids from a roster it was shown, and can get one
    wrong or invent one. The panel turns each id into a link to a paper, so an
    id that is not the project's is dropped. The unit stays: it is still a
    step of the path.
    """
    path = state.get("path")
    if not isinstance(path, list) or not path:
        return state
    allowed = {str(paper_id) for paper_id in allowed_paper_ids}
    return {
        **state,
        "path": [
            {
                **unit,
                "papers": [
                    paper_id
                    for paper_id in unit.get("papers") or []
                    if paper_id in allowed
                ],
            }
            for unit in path
            if isinstance(unit, dict)
        ],
    }


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


# Fields only a project session has. Left out of a dump when empty, so that a
# paper session is stored, and handed back to its tutor, exactly as it was
# before these existed.
_PROJECT_ONLY_FIELDS = ("path", "fetch")


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


class TutorUnit(BaseModel):
    """One step of a project session's study path."""

    model_config = ConfigDict(extra="ignore")

    title: str
    # Ids of the papers the unit draws on. Whether they are papers of the
    # project is not something this model can know; restrict_path_papers
    # checks that where the project is known.
    papers: List[str] = Field(default_factory=list)
    status: str = "todo"

    @field_validator("title", mode="before")
    @classmethod
    def _title(cls, value: Any) -> str:
        return _text(value, MAX_NAME_CHARS)

    @field_validator("papers", mode="before")
    @classmethod
    def _papers(cls, value: Any) -> List[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        ids: List[str] = []
        for item in value:
            paper_id = _text(item, MAX_PAPER_ID_CHARS)
            if paper_id and paper_id not in ids:
                ids.append(paper_id)
        return ids[:MAX_UNIT_PAPERS]

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, value: Any) -> str:
        status = str(value or "").strip().lower()
        return status if status in UNIT_STATUSES else "todo"


class TutorState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic: str = ""
    phase: str = "diagnostic"
    target_level: int = 4
    difficulty: str = "normal"
    # Name of the subskill being worked on, matching one in `subskills`.
    focus: Optional[str] = None
    subskills: List[TutorSubskill] = Field(default_factory=list)
    # The study path of a project session, in order. Empty for a paper, which
    # is one source and needs no route through it.
    path: List[TutorUnit] = Field(default_factory=list)
    # Open misconceptions only; the tutor drops one once it is resolved.
    misconceptions: List[str] = Field(default_factory=list)
    # What has been explained or told outright, as opposed to demonstrated.
    covered: List[str] = Field(default_factory=list)
    diagnostic_asked: int = 0
    # Project sessions only: what the tutor wants read before its next turn.
    # A project turn has one model fetch passages and another teach from
    # them, and this is the teacher's word to the fetcher. Replaced whole on
    # every turn, so the first lines are the ones kept.
    fetch: List[str] = Field(default_factory=list)
    # Set by the server, never trusted from the model.
    turn: int = 0

    def dump(self) -> dict:
        """The state as it is stored and sent."""
        data = self.model_dump()
        for field in _PROJECT_ONLY_FIELDS:
            if not data.get(field):
                data.pop(field, None)
        return data

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

    @field_validator("path", mode="before")
    @classmethod
    def _path(cls, value: Any) -> list:
        if not isinstance(value, list):
            return []
        titled = [
            item
            for item in value
            if isinstance(item, dict) and _text(item.get("title"), MAX_NAME_CHARS)
        ]
        return titled[:MAX_UNITS]

    @field_validator("misconceptions", "covered", mode="before")
    @classmethod
    def _line_lists(cls, value: Any) -> List[str]:
        return _lines(value)

    @field_validator("fetch", mode="before")
    @classmethod
    def _fetch(cls, value: Any) -> List[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        cleaned = [_text(item, MAX_LINE_CHARS) for item in value]
        return [line for line in cleaned if line][:MAX_FETCH_LINES]

    @field_validator("diagnostic_asked", "turn", mode="before")
    @classmethod
    def _counters(cls, value: Any) -> int:
        return _int(value, 0, 1_000_000, 0)
