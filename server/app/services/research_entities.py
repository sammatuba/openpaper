"""Typed research entity/relation mutations: conditional transactions with receipts.

Every mutation re-authorizes inside its transaction, validates expected revisions
(stale -> 412), appends history (never rewrites), and bumps the project change
sequence. AI-origin records keep their origin when edited and record derivation;
origins are never reset or erased (strategy 10.5).
"""
import copy
from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.database.models import (Paper, ProjectPaper, ResearchEntity, ResearchEntityRevision, ResearchProject,
                                 ResearchRelation, ResearchOrigin, ResearchSourceVersion)
from app.schemas.research_core import RELATION_TYPES, endpoint_allowed, validate_payload, validate_provenance
from . import research_access


def _verify_anchor(db: Session, project_id, payload, latest):
    """Server-side anchor integrity (C05): the quotation digest must match its own text,
    the source version must belong to this project, and — unless the complete anchor is
    byte-for-byte unchanged — the quotation must match the current source lines. Only a
    fully identical anchor skips line verification, preserving redaction semantics."""
    anchor = (payload or {}).get("anchor")
    if not anchor or "source_version_id" not in anchor: return
    from .investigation import text_hash
    if text_hash(anchor.get("quote", "")) != anchor.get("quote_sha256"):
        raise HTTPException(422, "Anchor quotation digest does not match its text")
    version = db.query(ResearchSourceVersion).filter(ResearchSourceVersion.id == UUID(str(anchor["source_version_id"])),
                                                     ResearchSourceVersion.project_id == project_id).first()
    if not version: raise HTTPException(422, "Anchor source version must belong to this project")
    previous = ((latest.payload or {}).get("anchor") if latest is not None else None) or {}
    unchanged = all(previous.get(key) == anchor.get(key)
                    for key in ("source_version_id", "start_line", "end_line", "quote", "quote_sha256"))
    if unchanged: return
    paper = db.query(Paper).filter(Paper.id == version.paper_id).first() if version.paper_id else None
    current = text_hash(paper.raw_content) if paper and paper.raw_content else None
    if current != version.text_sha256:
        raise HTTPException(409, "Source text is unavailable or changed; anchor requires review")
    lines = paper.raw_content.split("\n")
    if anchor["end_line"] > len(lines): raise HTTPException(422, "Anchor range exceeds source text")
    selected = "\n".join(lines[anchor["start_line"] - 1:anchor["end_line"]])
    if selected != anchor["quote"] or text_hash(selected) != anchor["quote_sha256"]:
        raise HTTPException(422, "Anchor quotation does not match exact source lines")


def _project_row(db: Session, project_id, *, lock=False):
    query = db.query(ResearchProject).filter(ResearchProject.project_id == project_id)
    if lock: query = query.with_for_update()
    row = query.first()
    if row is None or row.storage_generation != "v2":
        # One authoritative write path: typed writes exist only after conversion (contract 1.2).
        raise HTTPException(409, "Typed research writes require converted storage (storage_generation v2)")
    return row


def _bump(db: Session, project_id) -> int:
    row = _project_row(db, project_id, lock=True)
    row.change_sequence = (row.change_sequence or 0) + 1
    return row.change_sequence


def _check_storage_generation(db: Session, project_id):
    _project_row(db, project_id)


def create_entity(db: Session, project_id, actor_id, entity_type: str, payload: dict, *, entity_id=None,
                  origin="human", provenance=None, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    _check_storage_generation(db, project_id)
    try: typed = validate_payload(entity_type, payload)
    except ValueError as error: raise HTTPException(422, str(error)) from error
    _verify_anchor(db, project_id, typed, None)
    try: provenance = validate_provenance(origin, provenance or {})
    except ValueError as error: raise HTTPException(422, str(error)) from error
    entity = ResearchEntity(id=entity_id or uuid4(), project_id=project_id, type=entity_type, revision=1, payload=typed, created_by=actor_id)
    db.add(entity)
    db.flush()  # parent row must exist before its revision row in the same transaction
    db.add(ResearchEntityRevision(id=uuid4(), entity_id=entity.id, revision=1, payload=typed, origin=origin, provenance=provenance, actor_id=actor_id))
    sequence = _bump(db, project_id)
    if commit: db.commit()
    return {"entity_id": str(entity.id), "revision": 1, "change_sequence": sequence}


def revise_entity(db: Session, project_id, actor_id, entity_id, expected_revision: int, payload: dict, *,
                  origin="human", provenance=None, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    _check_storage_generation(db, project_id)
    entity = db.query(ResearchEntity).filter(ResearchEntity.id == entity_id, ResearchEntity.project_id == project_id).with_for_update().first()
    if not entity: raise HTTPException(404, "Research entity not found")
    if entity.revision != expected_revision:
        raise HTTPException(412, "Research entity changed", headers={"X-Current-Revision": str(entity.revision)})
    try: typed = validate_payload(entity.type, payload)
    except ValueError as error: raise HTTPException(422, str(error)) from error
    latest = db.query(ResearchEntityRevision).filter(ResearchEntityRevision.entity_id == entity.id).order_by(ResearchEntityRevision.revision.desc()).first()
    derived = None
    ai_origins = (ResearchOrigin.ASSISTANT.value, ResearchOrigin.EXTERNAL_AI.value)
    if latest and latest.origin in ai_origins:
        # Deriving is mandatory for AI-origin content; origin is never reset or erased and
        # its identity (native request/message or external client) cannot be replaced (contract 2.2).
        if origin not in ("human", latest.origin):
            raise HTTPException(422, "Derived AI content cannot be re-originated")
        identity_keys = ("client_identity", "content_sha256", "request_id", "message_id")
        supplied = provenance or {}
        for key in identity_keys:
            if supplied.get(key) and (latest.provenance or {}).get(key) != supplied[key]:
                raise HTTPException(422, "Cannot erase or replace AI provenance identity")
        origin = latest.origin
        provenance = {**(latest.provenance or {}), **{k: v for k, v in supplied.items() if k not in identity_keys}, "edited": True}
        derived = {"entity_id": str(entity.id), "revision": latest.revision}
    elif origin in ai_origins and latest is not None:
        # AI-authored content applied onto human/imported state still derives from that state (C27).
        derived = {"entity_id": str(entity.id), "revision": latest.revision}
    _verify_anchor(db, project_id, typed, latest)
    try: provenance = validate_provenance(origin, provenance or {})
    except ValueError as error: raise HTTPException(422, str(error)) from error
    revision = entity.revision + 1
    entity.revision = revision; entity.payload = typed
    db.add(ResearchEntityRevision(id=uuid4(), entity_id=entity.id, revision=revision, payload=typed, origin=origin,
                                  provenance=provenance, actor_id=actor_id, derived_from=derived))
    sequence = _bump(db, project_id)
    if commit: db.commit()
    return {"entity_id": str(entity.id), "revision": revision, "change_sequence": sequence}


def create_relation(db: Session, project_id, actor_id, relation_type: str, source_id, target_id, rationale: str, *,
                    relation_id=None, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    _check_storage_generation(db, project_id)
    if relation_type not in RELATION_TYPES: raise HTTPException(422, "Unknown relation type")
    if not (rationale or "").strip(): raise HTTPException(422, "Scientific relations require a rationale")
    entities = db.query(ResearchEntity).filter(ResearchEntity.id.in_([source_id, target_id]),
                                               ResearchEntity.project_id == project_id).all()
    by_id = {str(e.id): e for e in entities}
    source = by_id.get(str(source_id)); target = by_id.get(str(target_id))
    if not source or not target:
        raise HTTPException(422, "Relation endpoints must be project records (dangling or cross-project reference)")
    if not endpoint_allowed(relation_type, source.type, target.type):
        raise HTTPException(422, f"Relation {relation_type} does not allow {source.type}->{target.type}")
    relation = ResearchRelation(id=relation_id or uuid4(), project_id=project_id, relation_type=relation_type,
                                source_id=source.id, target_id=target.id, rationale=rationale.strip())
    db.add(relation)
    sequence = _bump(db, project_id)
    if commit: db.commit()
    return {"relation_id": str(relation.id), "change_sequence": sequence}


def load_entity(db: Session, project_id, actor_id, entity_id):
    research_access.authorize(db, project_id, actor_id)
    entity = db.query(ResearchEntity).filter(ResearchEntity.id == entity_id, ResearchEntity.project_id == project_id).first()
    if not entity: raise HTTPException(404, "Research entity not found")
    history = db.query(ResearchEntityRevision).filter(ResearchEntityRevision.entity_id == entity.id).order_by(ResearchEntityRevision.revision).all()

    def redact(payload):
        """Access redaction (C07): an anchor whose source is no longer associated with
        this project, or whose extracted text is gone, returns as a redacted locator —
        the captured quotation never leaves the server on a revoked read."""
        anchor = (payload or {}).get("anchor")
        if not anchor or "source_version_id" not in anchor: return payload
        version = db.query(ResearchSourceVersion).filter(ResearchSourceVersion.id == UUID(str(anchor["source_version_id"])),
                                                         ResearchSourceVersion.project_id == project_id).first()
        paper = db.query(Paper).filter(Paper.id == version.paper_id).first() if version and version.paper_id else None
        associated = paper and db.query(ProjectPaper).filter(ProjectPaper.project_id == project_id,
                                                             ProjectPaper.paper_id == paper.id).first()
        if associated and paper.raw_content: return payload
        return {**payload, "anchor": {"paper_id": str(version.paper_id) if version and version.paper_id else None}}

    current_payload = redact(copy.deepcopy(entity.payload))
    return {"entity": {"id": str(entity.id), "type": entity.type, "revision": entity.revision,
                       "payload": current_payload, "archived": entity.archived},
            "history": [{"revision": h.revision, "origin": h.origin,
                         "payload": redact(copy.deepcopy(h.payload)),
                         "provenance": h.provenance,
                         "derived_from": h.derived_from, "actor_id": str(h.actor_id) if h.actor_id else None,
                         "created_at": h.created_at.isoformat() if h.created_at else None} for h in history]}
