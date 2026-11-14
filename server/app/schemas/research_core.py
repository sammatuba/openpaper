"""Strict, bounded research-core payloads. No model or storage side effects.

Mirrors docs/work/CONTRACT-ai-native-research-platform.md section 2. Extra keys are
forbidden everywhere; provenance rules prevent external AI content from impersonating
native assistant requests and vice versa.
"""
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strict=True, max_length=20_000)]
Label = Annotated[str, StringConstraints(strict=True, max_length=500)]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$", strict=True)]
Line = Annotated[StrictInt, Field(ge=1)]

ENTITY_TYPES = ("question", "claim", "finding", "assumption", "decision", "gap")
RELATION_TYPES = ("supports", "challenges", "qualifies", "assumes", "motivates", "tests", "measures", "derived_from", "cites")
ORIGINS = ("human", "assembled", "assistant", "imported", "external_ai")


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Setup(Record):
    model: Text = ""
    task: Text = ""
    training: Text = ""
    intervention: Text = ""
    evaluation: Text = ""
    other: Text = ""


class Missingness(Record):
    """Missingness distinctions are explicit values, never zero (strategy 3.2)."""
    state: Literal["not_reported", "not_applicable", "not_yet_inspected"]


class Anchor(Record):
    source_version_id: UUID
    start_line: Line
    end_line: Line
    quote: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=20_000)]
    quote_sha256: Digest
    page_span: tuple[Line, Line] | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.end_line < self.start_line: raise ValueError("Reversed source lines")
        if self.page_span and self.page_span[1] < self.page_span[0]: raise ValueError("Reversed pages")
        return self


class Unbound(Record):
    origin_locator: Label = ""
    notes: Text = ""


class Redacted(Record):
    paper_id: UUID


class ClaimPayload(Record):
    statement: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=2000)]
    reasoning: Text = ""
    caveats: Text = ""
    status: Literal["provisional", "supported", "disputed", "reconciled", "withdrawn"] = "provisional"


class FindingPayload(Record):
    label: Label
    observed_result: Text = ""
    author_interpretation: Text = ""
    our_interpretation: Text = ""
    limitations: Text = ""
    setup: Setup = Field(default_factory=Setup)
    anchor: Anchor | Unbound | Redacted | None = None


class QuestionPayload(Record):
    text: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=20_000)]
    target_decision: Text = ""
    status: Literal["open", "resolved", "withdrawn"] = "open"


class AssumptionPayload(Record):
    text: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=20_000)]
    basis_entity_ids: list[UUID] = Field(default_factory=list, max_length=100)
    status: Literal["active", "retired"] = "active"


class DecisionPayload(Record):
    text: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=20_000)]
    rationale: Text = ""
    decided_by: UUID  # the named decider (contract 2.1)
    status: Literal["active", "superseded"] = "active"


class GapPayload(Record):
    description: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=20_000)]
    blocking_entity_ids: list[UUID] = Field(default_factory=list, max_length=100)
    status: Literal["open", "addressed"] = "open"


PAYLOAD_MODELS = {
    "question": QuestionPayload,
    "claim": ClaimPayload,
    "finding": FindingPayload,
    "assumption": AssumptionPayload,
    "decision": DecisionPayload,
    "gap": GapPayload,
}


class Provenance(Record):
    client_identity: Label | None = None  # validated MCP client id for external_ai
    declared_model: Label | None = None  # client declaration, not attestation
    content_sha256: Digest | None = None  # submitted bytes for external_ai
    request_id: UUID | None = None  # durable native assistant request
    message_id: UUID | None = None
    origin_label: Label | None = None
    edited: StrictBool = False
    reviewed: StrictBool = False

    @model_validator(mode="after")
    def identity_boundaries(self):
        external = bool(self.client_identity) or bool(self.content_sha256)
        native = bool(self.request_id) or bool(self.message_id)
        if external and native: raise ValueError("External-AI provenance cannot carry native request identity")
        return self


def validate_payload(entity_type: str, payload: dict) -> dict:
    model = PAYLOAD_MODELS.get(entity_type)
    if model is None: raise ValueError(f"Unknown entity type: {entity_type}")
    return model.model_validate(payload).model_dump(mode="json")


def validate_provenance(origin: str, provenance: dict) -> dict:
    if origin not in ORIGINS: raise ValueError(f"Unknown origin: {origin}")
    validated = Provenance.model_validate(provenance or {}).model_dump(mode="json")
    if origin == "assistant" and (not validated["request_id"] or not validated["message_id"]):
        raise ValueError("Native assistant provenance requires local request and message identity")
    if origin == "external_ai" and (not validated["client_identity"] or not validated["content_sha256"]):
        raise ValueError("External-AI provenance requires validated client identity and content hash")
    return validated


# Frozen endpoint legality table (contract 2.3). Presentation connectors never reach the DB.
ALLOWED_ENDPOINTS = {
    "supports": {"finding": {"claim"}},
    "challenges": {"finding": {"claim"}},
    "qualifies": {"finding": {"claim"}},
    "assumes": {"claim": {"assumption"}},
    "motivates": {"finding": {"question"}, "assumption": {"question"}, "claim": {"question"}},
    "tests": {"claim": {"claim"}, "question": {"claim"}},
    "measures": {"finding": {"claim"}},
    "derived_from": {"claim": {"claim", "finding"}, "finding": {"claim", "finding"}},
    "cites": {"claim": {"finding"}},
}


def endpoint_allowed(relation_type: str, source_type: str, target_type: str) -> bool:
    return target_type in ALLOWED_ENDPOINTS.get(relation_type, {}).get(source_type, ())
