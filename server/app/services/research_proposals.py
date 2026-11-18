"""Proposal and approval core (contract 4, checks C26/C27).

A proposal persists an unaccepted typed edit set with external/native provenance.
Approval is a server-recorded write binding the exact payload hash and target
revisions with an expiry. Applying consumes the approval once, inside one
transaction that re-checks authorization, targets and hash; stale targets return
the proposal to review. Idempotent apply replays the original receipt. The edits, the
state transition and the receipt are one savepoint (RULES-review-versioning.md, rule 8).
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.database.models import ResearchEntity, ResearchOrigin, ResearchProposal
from . import research_access, research_entities


def canonical_digest(payload) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _canonical_targets(targets):
    """Targets keyed by canonical UUID text, so a compact or upper-case spelling accepted at
    creation is the same key every later lookup uses. A malformed target is a client error."""
    if not isinstance(targets, dict) or not targets: raise HTTPException(422, "Proposal targets are required")
    canonical = {}
    for key, expected in targets.items():
        try: entity_id = str(UUID(key)) if isinstance(key, str) else None
        except ValueError: entity_id = None
        if entity_id is None or entity_id in canonical:
            raise HTTPException(422, "Proposal targets are distinct record ids")
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1:
            raise HTTPException(422, "Proposal targets bind expected revisions")
        canonical[entity_id] = expected
    return canonical


def _bound_edits(proposal, targets):
    """The proposal's edit set as (entity id, payload) pairs. The whole envelope is checked here:
    a malformed edit is a 422, never an unhandled exception, and each target is edited at most
    once (two edits bound to one expected revision cannot both apply)."""
    edits = proposal.payload.get("edits") if isinstance(proposal.payload, dict) else None
    if not isinstance(edits, list) or not edits:
        raise HTTPException(422, "Proposal edit set does not match its bound targets")
    bound = []
    for step in edits:
        if not isinstance(step, dict) or not isinstance(step.get("entity_id"), str) \
                or not isinstance(step.get("payload"), dict):
            raise HTTPException(422, "Each proposal edit needs an entity_id string and a payload object")
        try: entity_id = UUID(step["entity_id"])
        except ValueError as error: raise HTTPException(422, "Each proposal edit needs an entity_id string and a payload object") from error
        if str(entity_id) not in targets:
            raise HTTPException(422, "Proposal edit set does not match its bound targets")
        bound.append((entity_id, step["payload"]))
    if len({entity_id for entity_id, _payload in bound}) != len(bound):
        raise HTTPException(422, "A proposal edits each target once")
    return bound


def create_proposal(db: Session, project_id, actor_id, origin: str, payload: dict, targets: dict, *,
                    idempotency_key=None, proposal_id=None, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    if origin not in tuple(ResearchOrigin): raise HTTPException(422, "Unknown proposal origin")
    if origin == ResearchOrigin.EXTERNAL_AI.value:
        if not payload.get("client_identity") or not payload.get("content_sha256"):
            raise HTTPException(422, "External-AI proposals require client identity and submitted-content hash")
        if payload.get("request_id") or payload.get("message_id"):
            raise HTTPException(422, "External-AI proposals cannot claim native assistant identity")
    if origin == ResearchOrigin.ASSISTANT.value and not (payload.get("request_id") and payload.get("message_id")):
        raise HTTPException(422, "Native assistant proposals require durable request identity")
    targets = _canonical_targets(targets)
    for entity_id in targets:
        entity = db.query(ResearchEntity).filter(ResearchEntity.id == UUID(entity_id),
                                                 ResearchEntity.project_id == project_id).first()
        if not entity: raise HTTPException(422, "Proposal target must be a project record")
    digest = canonical_digest(payload)
    if idempotency_key:
        existing = db.query(ResearchProposal).filter(ResearchProposal.project_id == project_id,
                                                     ResearchProposal.idempotency_key == idempotency_key).first()
        if existing:
            if existing.payload_sha256 != digest or existing.targets != targets:
                raise HTTPException(409, "Idempotency key reused with a different proposal")
            # Replay recovers the persisted original creation receipt (R32) — later
            # mutations on the proposal draw their own sequences.
            return existing, {"replayed": True,
                              "change_sequence": (existing.receipt or {}).get("change_sequence",
                                                                              existing.change_sequence)}
    proposal = ResearchProposal(id=proposal_id or uuid4(), project_id=project_id, origin=origin,
                                payload=payload, payload_sha256=digest, targets=targets, state="pending",
                                idempotency_key=idempotency_key, created_by=actor_id)
    db.add(proposal)
    proposal.change_sequence = research_access.advance_change_sequence(db, project_id)
    # The creation receipt is persisted durably: later mutations (approval, stale,
    # expiry) draw their own sequences, and replay must recover THIS original (R32).
    proposal.receipt = {"change_sequence": proposal.change_sequence}
    receipt = {"replayed": False, "change_sequence": proposal.change_sequence}
    db.flush()  # commit=False callers read this back in the same transaction (R54)
    if commit: db.commit()
    return proposal, receipt


def approve_proposal(db: Session, project_id, actor_id, proposal_id, *, expires_in_seconds=3600, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    proposal = db.query(ResearchProposal).filter(ResearchProposal.id == UUID(str(proposal_id)),
                                                 ResearchProposal.project_id == project_id).with_for_update().first()
    if not proposal: raise HTTPException(404, "Proposal not found")
    db.refresh(proposal)  # observe the committed row even when this session cached it (R36)
    if proposal.state != "pending": raise HTTPException(409, f"Proposal is {proposal.state}, not approvable")
    now = datetime.now(timezone.utc)
    proposal.state = "approved"
    proposal.approval = {"approver_id": str(actor_id), "approved_at": now.isoformat(),
                         "expires_at": (now + timedelta(seconds=expires_in_seconds)).isoformat(),
                         "bound_payload_sha256": proposal.payload_sha256, "bound_targets": proposal.targets}
    proposal.change_sequence = research_access.advance_change_sequence(db, project_id)
    db.flush()  # commit=False callers read this back in the same transaction (R54)
    if commit: db.commit()
    return proposal


def apply_proposal(db: Session, project_id, actor_id, proposal_id, *, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    proposal = db.query(ResearchProposal).filter(ResearchProposal.id == UUID(str(proposal_id)),
                                                 ResearchProposal.project_id == project_id).with_for_update().first()
    if not proposal: raise HTTPException(404, "Proposal not found")
    db.refresh(proposal)  # observe the committed row even when this session cached it (R36)
    if proposal.state == "applied" and proposal.applied_receipt:
        return {"receipt": proposal.applied_receipt, "replayed": True}
    if proposal.state != "approved": raise HTTPException(409, f"Proposal is {proposal.state}")
    approval = proposal.approval or {}
    # Recompute the digest from the actual stored payload: stored-vs-stored comparisons
    # would let a mutated payload ride an approval bound to the original text.
    digest = canonical_digest(proposal.payload)
    # The whole approval is checked before the first edit: nothing after this point may fail on
    # a field the approval was supposed to carry (R53).
    try: expires_at = datetime.fromisoformat(approval.get("expires_at") or "")
    except (TypeError, ValueError): expires_at = None
    if expires_at is None or expires_at.tzinfo is None or not approval.get("approver_id") \
            or digest != proposal.payload_sha256 \
            or approval.get("bound_payload_sha256") != digest \
            or approval.get("bound_targets") != proposal.targets:
        raise HTTPException(409, "Approval does not bind this proposal")
    targets = _canonical_targets(proposal.targets)
    edits = _bound_edits(proposal, targets)
    if datetime.now(timezone.utc) > expires_at:
        proposal.state = "expired"
        proposal.change_sequence = research_access.advance_change_sequence(db, project_id)
        db.flush()  # a caller-held transaction must re-read this state, not lose it on refresh
        if commit: db.commit()
        raise HTTPException(410, "Proposal approval expired")
    # Deterministic lock order: ascending entity id inside the transaction.
    entity_ids = sorted(UUID(key) for key in targets)
    entities = {e.id: e for e in db.query(ResearchEntity).filter(ResearchEntity.id.in_(entity_ids),
                                                                ResearchEntity.project_id == project_id).with_for_update().all()}
    for entity in entities.values(): db.refresh(entity)  # committed state, even when cached (R36)
    for entity_id in entity_ids:
        entity = entities.get(entity_id)
        if not entity or entity.revision != targets[str(entity_id)]:
            proposal.state = "stale"
            proposal.change_sequence = research_access.advance_change_sequence(db, project_id)
            db.flush()
            if commit: db.commit()
            raise HTTPException(409, "Proposal target revisions changed; returned to review")
    # The edit set applies all-or-nothing (C08). Validate EVERY edit before the first mutation, so
    # a schema failure in a later edit cannot leave an earlier one flushed in this session, where
    # the next unrelated commit would persist it under a still-approved proposal (R52).
    for entity_id, payload in edits:
        entity = entities[entity_id]
        try: research_entities.validate_payload(entity.type, payload)
        except ValueError as error: raise HTTPException(422, f"Proposal edit violates {entity.type} schema: {error}") from error
    provenance = {key: value for key, value in proposal.payload.items()
                  if key in ("client_identity", "content_sha256", "declared_model", "request_id", "message_id")}
    # One savepoint holds the revisions, the state transition and the receipt, flushed together
    # (R53). A failure anywhere inside rolls all of it back; a success is visible to a replay in
    # the same transaction, whose refresh would otherwise discard an unflushed "applied" state
    # and return the proposal to review with its edits already written.
    with db.begin_nested():
        applied = {}
        for entity_id, payload in edits:
            applied[str(entity_id)] = research_entities.revise_entity(
                db, project_id, actor_id, entity_id, targets[str(entity_id)], payload,
                origin=proposal.origin, provenance=provenance, commit=False)
        receipt = {"applied": applied, "proposal_sha256": proposal.payload_sha256,
                   "approver_id": approval["approver_id"], "applied_at": datetime.now(timezone.utc).isoformat()}
        proposal.state = "applied"; proposal.applied_receipt = receipt
        db.flush()
    if commit: db.commit()
    return {"receipt": receipt, "replayed": False}
