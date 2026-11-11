"""Strict, bounded shared investigation documents. No model or storage side effects."""
import json
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strict=True, max_length=20_000)]
Label = Annotated[str, StringConstraints(strict=True, max_length=500)]

class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Case(Record):
    question: Text = ""
    why_it_matters: Text = ""
    landscape: Text = ""
    coverage_limits: Text = ""
    provisional_answer: Text = ""
    unresolved_tension: Text = ""
    reconciliation: Text = ""
    discriminating_experiment: Text = ""
    update_criteria: Text = ""
    search_date: date | None = None

class Claim(Record):
    id: UUID
    statement: Annotated[str, StringConstraints(strict=True, max_length=2000)]
    reasoning: Text = ""
    caveats: Text = ""
    archived: StrictBool = False

class Setup(Record):
    model: Text = ""
    task: Text = ""
    training: Text = ""
    intervention: Text = ""
    evaluation: Text = ""
    other: Text = ""

Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$", strict=True)]
Line = Annotated[StrictInt, Field(ge=1)]

class Anchor(Record):
    kind: Literal["anchored"]
    paper_id: UUID
    start_line: Line
    end_line: Line
    quote: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=20000)]
    source_sha256: Digest
    quote_sha256: Digest
    title: Text = ""
    authors: list[Label] = Field(default_factory=list, max_length=500)
    publish_date: Label | None = None
    doi: Label | None = None
    page_span: tuple[Line, Line] | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.end_line < self.start_line: raise ValueError("Reversed source lines")
        if self.page_span and self.page_span[1] < self.page_span[0]: raise ValueError("Reversed pages")
        return self

class Unbound(Record):
    kind: Literal["unbound"]
    origin_locator: Label = ""
    notes: Text = ""

class Redacted(Record):
    kind: Literal["redacted"]
    paper_id: UUID

class Finding(Record):
    id: UUID
    label: Label
    observed_result: Text = ""
    author_interpretation: Text = ""
    our_interpretation: Text = ""
    setup: Setup = Field(default_factory=Setup)
    limitations: Text = ""
    source: Annotated[Anchor | Unbound | Redacted, Field(discriminator="kind")]
    archived: StrictBool = False

class Relation(Record):
    id: UUID
    claim_id: UUID
    finding_id: UUID
    relation: Literal["supports", "challenges", "qualifies"]
    rationale: Text = ""

class Provenance(Record):
    kind: Literal["human", "assembled", "assistant", "imported"] = "human"
    request_id: UUID | None = None
    message_id: UUID | None = None
    origin_label: Label | None = None
    original_ids: list[Label] = Field(default_factory=list,max_length=1000)
    edited: StrictBool = False
    inserted_at: datetime | None = None
    inserted_by: UUID | None = None
    reviewed: StrictBool = False

    @model_validator(mode="after")
    def assistant_identity(self):
        if self.kind == "assistant" and (not self.request_id or not self.message_id):
            raise ValueError("Assistant provenance requires local request and message")
        return self

class Block(Record):
    id: UUID
    kind: Literal["paragraph", "source_quote", "gap"]
    text: Annotated[str, StringConstraints(strict=True,max_length=10000)] = ""
    claim_ids: list[UUID] = Field(default_factory=list,max_length=100)
    finding_ids: list[UUID] = Field(default_factory=list,max_length=500)
    provenance: Provenance = Field(default_factory=Provenance)
    dependency_pins: dict[Annotated[str,StringConstraints(max_length=100)], Digest] = Field(default_factory=dict,max_length=1600)
    quote_snapshot: Annotated[Anchor | Redacted, Field(discriminator="kind")] | None = None

class Section(Record):
    id: UUID
    title: Label
    blocks: list[Block] = Field(default_factory=list,max_length=1000)

class Manuscript(Record):
    title: Label = ""
    sections: list[Section] = Field(default_factory=list,max_length=30)

class InvestigationDocument(Record):
    format: Literal["openpaper/investigation"] = "openpaper/investigation"
    version: StrictInt = 1
    case: Case = Field(default_factory=Case)
    claims: list[Claim] = Field(default_factory=list,max_length=100)
    findings: list[Finding] = Field(default_factory=list,max_length=500)
    relations: list[Relation] = Field(default_factory=list,max_length=1000)
    manuscript: Manuscript = Field(default_factory=Manuscript)

    @model_validator(mode="after")
    def graph(self):
        if self.version != 1: raise ValueError("Unsupported investigation version")
        claims={c.id for c in self.claims}; findings={f.id for f in self.findings}
        entities=[*self.claims,*self.findings,*self.relations,*self.manuscript.sections]
        blocks=[b for s in self.manuscript.sections for b in s.blocks]
        if len(blocks)>1000: raise ValueError("Too many blocks")
        entities.extend(blocks)
        if len({e.id for e in entities})!=len(entities): raise ValueError("Duplicate object ID")
        triples=set()
        for r in self.relations:
            if r.claim_id not in claims or r.finding_id not in findings: raise ValueError("Dangling relation")
            triple=(r.claim_id,r.finding_id,r.relation)
            if triple in triples: raise ValueError("Duplicate relation")
            triples.add(triple)
        for b in blocks:
            if len(set(b.claim_ids))!=len(b.claim_ids) or len(set(b.finding_ids))!=len(b.finding_ids): raise ValueError("Duplicate block references")
            if not set(b.claim_ids)<=claims or not set(b.finding_ids)<=findings: raise ValueError("Dangling block")
            if b.kind=="source_quote" and len(b.finding_ids)!=1: raise ValueError("Source quote needs exactly one finding")
        if len(json.dumps(self.model_dump(mode="json"),ensure_ascii=False,separators=(",",":")).encode())>2_000_000:
            raise ValueError("Investigation exceeds UTF-8 byte limit")
        return self

class SaveInvestigation(Record):
    document: InvestigationDocument
    reviewed_block_ids: list[UUID] = Field(default_factory=list,max_length=1000)
    reviewed_proposal_ids: list[UUID] = Field(default_factory=list,max_length=1000)


class CreateDraftRequest(Record):
    id: UUID
    base_revision: Annotated[StrictInt, Field(ge=1)]
    section_id: UUID
    claim_ids: list[UUID] = Field(default_factory=list,max_length=10)
    finding_ids: list[UUID] = Field(min_length=1,max_length=20)
    instructions: Annotated[str,StringConstraints(strict=True,max_length=2000)] = ""
    provider: Literal['gemini','openai','anthropic']

    @model_validator(mode='after')
    def unique_selection(self):
        if len(set(self.claim_ids))!=len(self.claim_ids) or len(set(self.finding_ids))!=len(self.finding_ids): raise ValueError('Duplicate selection')
        return self
