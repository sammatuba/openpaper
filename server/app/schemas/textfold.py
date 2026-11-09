"""Validate Textfold v0 documents without dropping upstream extension fields.

Native implementation of the public interchange format, not vendored app code.
Textfold: https://github.com/chenxiachan/textfold/blob/main/docs/format.md
"""
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

Text = Annotated[str, Field(strict=True, max_length=100_000)]
Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=200)]
Level = Literal["topic", "takeaway", "key", "brief", "full"]


class Extensible(BaseModel):
    model_config = ConfigDict(extra="allow")


class FoldUnit(Extensible):
    id: Identifier
    kind: Text = "paragraph"
    full: Text
    sentences: list[Text] = Field(max_length=1000)
    evidence: list[StrictInt] = Field(max_length=1000)
    brief: list[Text] = Field(max_length=1000)
    key: Text
    takeaway: Text
    topic: Text

    @model_validator(mode="after")
    def anchored_excerpt(self):
        if any(i < 0 or i >= len(self.sentences) for i in self.evidence):
            raise ValueError("Evidence must reference existing zero-based sentences")
        if self.brief != [self.sentences[i] for i in self.evidence]:
            raise ValueError("Brief must exactly match the referenced source sentences")
        # Sentences are verbatim, in source order; allow Markdown/spacing between them.
        cursor = 0
        for sentence in self.sentences:
            found = self.full.find(sentence, cursor)
            if not sentence or found < 0:
                raise ValueError("Sentences must occur verbatim and in order in full text")
            cursor = found + len(sentence)
        if not self.sentences and self.full.strip():
            raise ValueError("Nonempty units require source sentences")
        if (self.key or self.takeaway or self.topic) and not self.evidence:
            raise ValueError("Folded text requires source sentence anchors")
        return self


class FoldSection(Extensible):
    id: Identifier
    title: Text
    depth: Annotated[int, Field(strict=True, ge=1, le=6)] = 1
    takeaway: Text
    topic: Text
    units: list[FoldUnit] = Field(max_length=1000)

    @model_validator(mode="after")
    def anchored_takeaway(self):
        if self.takeaway and not any(unit.evidence for unit in self.units):
            raise ValueError("Section takeaways require anchored source units")
        return self


class FoldProvenance(Extensible):
    ai_generated: StrictBool
    local: StrictBool
    model: Text | None = None


class FoldLink(Extensible):
    from_: Identifier = Field(alias="from")
    to: Identifier
    rel: Text


class TextFoldDocument(Extensible):
    format: Literal["textfold/doc"]
    version: Annotated[int, Field(strict=True, ge=0, le=0)]
    id: Identifier
    title: Text
    lang: Text
    levels: list[Level]
    written: list[Level]
    provenance: FoldProvenance
    sections: list[FoldSection] = Field(min_length=1, max_length=100)
    links: list[FoldLink] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def valid_document(self):
        if self.levels != ["topic", "takeaway", "key", "brief", "full"]:
            raise ValueError("Expected all five Textfold levels, coarsest first")
        if any(level not in {"topic", "takeaway", "key"} for level in self.written):
            raise ValueError("Full and Brief must be verbatim source text")
        ids = [s.id for s in self.sections] + [u.id for s in self.sections for u in s.units]
        if len(ids) != len(set(ids)):
            raise ValueError("Section and unit IDs must be unique")
        if any(link.from_ not in ids or link.to not in ids for link in self.links):
            raise ValueError("Argument links must reference existing sections or units")
        if len(json.dumps(self.model_dump(by_alias=True), ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 1_000_000:
            raise ValueError("Research brief exceeds 1 MB")
        return self
