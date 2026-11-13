"""Metered-operation admission/reservation/replay core (strategy 11.3, check C29).

No metered dispatch may run without an admitted reservation against an explicitly
registered price table. The shipped default has no price-table row: every paid path
is refused while deterministic work continues. Estimate and settled usage are stored
separately; uncertain completion retains the reservation pending reconciliation and
is never silently retried. No database transaction spans a provider call: callers
reserve/commit, dispatch outside, then settle/fail.
"""
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database.models import MeteredOperation, MeteredPriceTable
from .research_proposals import canonical_digest


def register_price_table(db: Session, prices: dict, *, version=None, commit=True):
    """Explicit administrative act: registers one price-table version. Not reachable
    from any user path; used by deployment tooling and tests."""
    if not isinstance(prices, dict) or not prices: raise HTTPException(422, "Price table must be non-empty")
    if version is None:
        current = db.query(func.max(MeteredPriceTable.version)).scalar()
        version = (current or 0) + 1
    if db.query(MeteredPriceTable).filter(MeteredPriceTable.version == version).first():
        raise HTTPException(409, "Price table version already exists")
    row = MeteredPriceTable(version=version, prices=prices)
    db.add(row)
    if commit: db.commit()
    return row


def active_price_table(db: Session):
    return db.query(MeteredPriceTable).order_by(MeteredPriceTable.version.desc()).first()


def assert_dispatchable(db: Session, operation_type: str):
    """The enforcement gate every metered caller must pass immediately before dispatch."""
    table = active_price_table(db)
    entry = (table.prices or {}).get(operation_type) if table else None
    if not table or not entry or not entry.get("max_cost"):
        raise HTTPException(409, "operation_not_priceable", headers={"X-Metered-Operation": operation_type})


def _estimate_cost(estimate: dict, entry: dict):
    units = estimate.get("units") or {}
    unit_prices = entry.get("unit_prices") or {}
    unknown = [name for name in units if name not in unit_prices]
    if unknown: raise HTTPException(422, f"Unpriced units in estimate: {', '.join(sorted(unknown))}")
    return sum(units[name] * unit_prices[name] for name in units)


def reserve(db: Session, project_id, actor_id, operation_type: str, estimate: dict, payload, *,
            idempotency_key=None, limits=None, commit=True):
    from . import research_access
    research_access.authorize(db, project_id, actor_id, write=True)
    table = active_price_table(db)
    entry = (table.prices or {}).get(operation_type) if table else None
    if not table or not entry or not entry.get("max_cost"):
        raise HTTPException(409, "operation_not_priceable", headers={"X-Metered-Operation": operation_type})
    digest = canonical_digest(payload)
    if idempotency_key:
        existing = db.query(MeteredOperation).filter(MeteredOperation.project_id == project_id,
                                                     MeteredOperation.operation_type == operation_type,
                                                     MeteredOperation.idempotency_key == idempotency_key).first()
        if existing:
            if existing.payload_sha256 != digest:
                raise HTTPException(409, "Idempotency key reused with a different payload")
            return existing, {"replayed": True}
    limits = limits or {}
    cost = _estimate_cost(estimate, entry)
    max_cost = entry["max_cost"]
    if cost > max_cost: raise HTTPException(429, "Estimated cost exceeds the operation cap")
    inflight_cap = limits.get("max_inflight")
    if inflight_cap is not None:
        inflight = db.query(func.count(MeteredOperation.id)).filter(
            MeteredOperation.project_id == project_id,
            MeteredOperation.state.in_(("reserved", "admitted", "running"))).scalar()
        if inflight >= inflight_cap: raise HTTPException(429, "In-flight metered operation cap reached")
    reservation = {"max_cost": max_cost, "price_table_version": table.version,
                   "estimated_cost": cost, "reserved_by": str(actor_id)}
    row = MeteredOperation(id=uuid4(), project_id=project_id, actor_id=actor_id,
                           operation_type=operation_type, price_table_version=table.version,
                           payload_sha256=digest, estimate=estimate, reservation=reservation,
                           state="reserved", idempotency_key=idempotency_key)
    db.add(row)
    if commit: db.commit()
    return row, {"replayed": False, "estimated_cost": cost}


def _transition(db: Session, operation_id, actor_id, current, target, project_id, *, usage=None, error_code=None):
    row = db.query(MeteredOperation).filter(MeteredOperation.id == operation_id,
                                            MeteredOperation.project_id == project_id).with_for_update().first()
    if not row: raise HTTPException(404, "Metered operation not found")
    if row.state != current: raise HTTPException(409, f"Metered operation is {row.state}, expected {current}")
    row.state = target
    if usage is not None: row.usage = usage
    if error_code: row.error_code = error_code
    db.commit()
    return row


def admit(db: Session, project_id, actor_id, operation_id): return _transition(db, operation_id, actor_id, "reserved", "admitted", project_id)
def start(db: Session, project_id, actor_id, operation_id): return _transition(db, operation_id, actor_id, "admitted", "running", project_id)


def settle(db: Session, project_id, actor_id, operation_id, usage: dict):
    row = _transition(db, operation_id, actor_id, "running", "completed", project_id, usage=usage)
    return row


def fail(db: Session, project_id, actor_id, operation_id, *, uncertain=False, error_code="failed"):
    """Failed operations are closed; uncertain completion retains the reservation
    pending reconciliation — the caller must not auto-retry the paid work."""
    target = "uncertain" if uncertain else "failed"
    row = _transition(db, operation_id, actor_id, "running", target, project_id, error_code=error_code)
    return row


def cancel(db: Session, project_id, actor_id, operation_id):
    return _transition(db, operation_id, actor_id, "reserved", "cancelled", project_id)
