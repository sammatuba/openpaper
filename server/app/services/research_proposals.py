"""Proposal and approval core (contract 4, checks C26/C27).

A proposal persists an unaccepted typed edit set with external/native provenance.
Approval is a server-recorded write binding the exact payload hash and target
revisions with an expiry. Applying consumes the approval once, inside one
transaction that re-checks authorization, targets and hash; stale targets return
the proposal to review. Idempotent apply replays the original receipt.
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
    if not isinstance(targets, dict) or not targets: raise HTTPException(422, "Proposal targets are required")
    for entity_id, expected in targets.items():
        entity = db.query(ResearchEntity).filter(ResearchEntity.id == UUID(str(entity_id)),
                                                 ResearchEntity.project_id == project_id).first()
        if not entity: raise HTTPException(422, "Proposal target must be a project record")
        if not isinstance(expected, int) or expected < 1:
            raise HTTPException(422, "Proposal targets bind expected revisions")
    digest = canonical_digest(payload)
    if idempotency_key:
        existing = db.query(ResearchProposal).filter(ResearchProposal.project_id == project_id,
                                                     ResearchProposal.idempotency_key == idempotency_key).first()
        if existing:
            if existing.payload_sha256 != digest or existing.targets != targets:
                raise HTTPException(409, "Idempotency key reused with a different proposal")
            return existing, {"replayed": True}
    proposal = ResearchProposal(id=proposal_id or uuid4(), project_id=project_id, origin=origin,
                                payload=payload, payload_sha256=digest, targets=targets, state="pending",
                                idempotency_key=idempotency_key, created_by=actor_id)
    db.add(proposal)
    if commit: db.commit()
    return proposal, {"replayed": False}


def approve_proposal(db: Session, project_id, actor_id, proposal_id, *, expires_in_seconds=3600, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    proposal = db.query(ResearchProposal).filter(ResearchProposal.id == UUID(str(proposal_id)),
                                                 ResearchProposal.project_id == project_id).with_for_update().first()
    if not proposal: raise HTTPException(404, "Proposal not found")
    if proposal.state != "pending": raise HTTPException(409, f"Proposal is {proposal.state}, not approvable")
    now = datetime.now(timezone.utc)
    proposal.state = "approved"
    proposal.approval = {"approver_id": str(actor_id), "approved_at": now.isoformat(),
                         "expires_at": (now + timedelta(seconds=expires_in_seconds)).isoformat(),
                         "bound_payload_sha256": proposal.payload_sha256, "bound_targets": proposal.targets}
    if commit: db.commit()
    return proposal


def apply_proposal(db: Session, project_id, actor_id, proposal_id, *, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    proposal = db.query(ResearchProposal).filter(ResearchProposal.id == UUID(str(proposal_id)),
                                                 ResearchProposal.project_id == project_id).with_for_update().first()
    if not proposal: raise HTTPException(404, "Proposal not found")
    if proposal.state == "applied" and proposal.receipt:
        return {"receipt": proposal.receipt, "replayed": True}
    if proposal.state != "approved": raise HTTPException(409, f"Proposal is {proposal.state}")
    approval = proposal.approval or {}
    if not approval.get("expires_at") or approval.get("bound_payload_sha256") != proposal.payload_sha256 \
            or approval.get("bound_targets") != proposal.targets:
        raise HTTPException(409, "Approval does not bind this proposal")
    if datetime.now(timezone.utc) > datetime.fromisoformat(approval["expires_at"]):
        proposal.state = "expired"
        if commit: db.commit()
        raise HTTPException(410, "Proposal approval expired")
    # Deterministic lock order: ascending entity id inside the transaction.
    entity_ids = sorted(UUID(k) for k in proposal.targets)
    entities = {e.id: e for e in db.query(ResearchEntity).filter(ResearchEntity.id.in_(entity_ids),
                                                                ResearchEntity.project_id == project_id).with_for_update().all()}
    for entity_id in entity_ids:
        entity = entities.get(entity_id)
        if not entity or entity.revision != proposal.targets[str(entity_id)]:
            proposal.state = "stale"
            if commit: db.commit()
            raise HTTPException(409, "Proposal target revisions changed; returned to review")
    applied = {}
    for step in proposal.payload.get("edits", []):
        entity_id = UUID(step["entity_id"])
        result = research_entities.revise_entity(db, project_id, actor_id, entity_id,
                                                 proposal.targets[str(entity_id)], step["payload"],
                                                 origin=proposal.origin, provenance={key: value for key, value in proposal.payload.items()
                                                                                     if key in ("client_identity", "content_sha256", "declared_model", "request_id", "message_id")},
                                                 commit=False)
        applied[str(entity_id)] = result
    receipt = {"applied": applied, "proposal_sha256": proposal.payload_sha256,
               "approver_id": approval["approver_id"], "applied_at": datetime.now(timezone.utc).isoformat()}
    proposal.state = "applied"; proposal.receipt = receipt
    if commit: db.commit()
    return {"receipt": receipt, "replayed": False}
