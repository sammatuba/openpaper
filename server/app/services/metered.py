"""Metered-operation admission/reservation/replay core (strategy 11.3, check C29).

No metered dispatch may run without an admitted reservation against an explicitly
registered price table AND explicitly configured limits. The shipped default has
no price-table row: every paid path is refused while deterministic work continues.
Admission is atomic per project (transaction-scoped advisory lock) and counts
uncertain completions as in-flight exposure because their reservations are retained.
Estimate and settled usage are stored separately; uncertain completion is never
silently retried. Dispatch is gated on a specific admitted operation via
`assert_dispatchable`; no database transaction spans a provider call.
"""
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from app.database.models import MeteredOperation, MeteredPriceTable
from . import research_access
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


def assert_dispatchable(db: Session, project_id, actor_id, operation_id):
    """The enforcement gate every metered caller must pass immediately before dispatch:
    current project authorization is rechecked inside the transaction, then the specific
    operation must be an admitted reservation by this actor and priced at its recorded
    table version. State changes or unpriced operations are refused."""
    research_access.authorize(db, project_id, actor_id, write=True)
    row = db.query(MeteredOperation).filter(MeteredOperation.id == operation_id,
                                            MeteredOperation.project_id == project_id).with_for_update().first()
    if not row: raise HTTPException(404, "Metered operation not found")
    if str(row.actor_id) != str(actor_id): raise HTTPException(403, "Metered operation belongs to another actor")
    if row.state != "admitted":
        raise HTTPException(409, f"Dispatch requires an admitted reservation; operation is {row.state}")
    table = db.query(MeteredPriceTable).filter(MeteredPriceTable.version == row.price_table_version).first()
    entry = (table.prices or {}).get(row.operation_type) if table else None
    if not entry or not entry.get("max_cost"):
        raise HTTPException(409, "operation_not_priceable", headers={"X-Metered-Operation": row.operation_type})
    return row


def _estimate_cost(estimate: dict, entry: dict):
    units = estimate.get("units") or {}
    unit_prices = entry.get("unit_prices") or {}
    unknown = [name for name in units if name not in unit_prices]
    if unknown: raise HTTPException(422, f"Unpriced units in estimate: {', '.join(sorted(unknown))}")
    return sum(units[name] * unit_prices[name] for name in units)


def reserve(db: Session, project_id, actor_id, operation_type: str, estimate: dict, payload, *,
            idempotency_key=None, limits=None, commit=True):
    """Admission requires explicit limits: `max_inflight` bounds the project's combined
    reserved/admitted/running/uncertain exposure atomically. Missing limits refuse."""
    research_access.authorize(db, project_id, actor_id, write=True)
    if not isinstance(limits, dict) or not isinstance(limits.get("max_inflight"), int) or limits["max_inflight"] < 1:
        raise HTTPException(422, "Metered admission requires configured limits (max_inflight)")
    table = active_price_table(db)
    entry = (table.prices or {}).get(operation_type) if table else None
    if not table or not entry or not entry.get("max_cost"):
        raise HTTPException(409, "operation_not_priceable", headers={"X-Metered-Operation": operation_type})
    digest = canonical_digest(payload)
    # Serialize admissions per project so concurrent reserves cannot exceed the cap.
    db.execute(text("SELECT pg_advisory_xact_lock(921747, hashtext(:key))"), {"key": str(project_id)})
    if idempotency_key:
        existing = db.query(MeteredOperation).filter(MeteredOperation.project_id == project_id,
                                                     MeteredOperation.operation_type == operation_type,
                                                     MeteredOperation.idempotency_key == idempotency_key).first()
        if existing:
            if existing.payload_sha256 != digest:
                raise HTTPException(409, "Idempotency key reused with a different payload")
            return existing, {"replayed": True}
    cost = _estimate_cost(estimate, entry)
    if cost > entry["max_cost"]: raise HTTPException(429, "Estimated cost exceeds the operation cap")
    inflight = db.query(func.count(MeteredOperation.id)).filter(
        MeteredOperation.project_id == project_id,
        MeteredOperation.state.in_(("reserved", "admitted", "running", "uncertain"))).scalar()
    if inflight >= limits["max_inflight"]: raise HTTPException(429, "In-flight metered operation cap reached")
    reservation = {"max_cost": entry["max_cost"], "price_table_version": table.version,
                   "estimated_cost": cost, "reserved_by": str(actor_id), "limits": dict(limits)}
    row = MeteredOperation(id=uuid4(), project_id=project_id, actor_id=actor_id,
                           operation_type=operation_type, price_table_version=table.version,
                           payload_sha256=digest, estimate=estimate, reservation=reservation,
                           state="reserved", idempotency_key=idempotency_key)
    db.add(row)
    if commit: db.commit()
    return row, {"replayed": False, "estimated_cost": cost}


def _transition(db: Session, operation_id, actor_id, current, target, project_id, *, usage=None, error_code=None):
    research_access.authorize(db, project_id, actor_id, write=True)
    row = db.query(MeteredOperation).filter(MeteredOperation.id == operation_id,
                                            MeteredOperation.project_id == project_id).with_for_update().first()
    if not row: raise HTTPException(404, "Metered operation not found")
    if str(row.actor_id) != str(actor_id): raise HTTPException(403, "Metered operation belongs to another actor")
    if row.state != current: raise HTTPException(409, f"Metered operation is {row.state}, expected {current}")
    row.state = target
    if usage is not None: row.usage = usage
    if error_code: row.error_code = error_code
    db.commit()
    return row


def admit(db: Session, project_id, actor_id, operation_id): return _transition(db, operation_id, actor_id, "reserved", "admitted", project_id)
def start(db: Session, project_id, actor_id, operation_id): return _transition(db, operation_id, actor_id, "admitted", "running", project_id)


def settle(db: Session, project_id, actor_id, operation_id, usage: dict):
    return _transition(db, operation_id, actor_id, "running", "completed", project_id, usage=usage)


def fail(db: Session, project_id, actor_id, operation_id, *, uncertain=False, error_code="failed"):
    """Failed operations are closed; uncertain completion retains the reservation
    pending reconciliation — the caller must not auto-retry the paid work."""
    target = "uncertain" if uncertain else "failed"
    return _transition(db, operation_id, actor_id, "running", target, project_id, error_code=error_code)


def cancel(db: Session, project_id, actor_id, operation_id):
    return _transition(db, operation_id, actor_id, "reserved", "cancelled", project_id)
