"""Review identity model: occurrence/report/candidate/study records, mapping events and
count-derived flow computation (strategy 6.1, fixture 17.1, check C17).

Counts are always computed from actual records and append-only mapping events —
never from a stored picture. Rules enforced here:

- Screening modes are declared per protocol stage (`solo` or `dual`). A dual-stage
  decision is final only when decisions from at least two DISTINCT reviewers agree;
  one reviewer cannot satisfy dual review, not even by submitting twice. Disagreement
  or an incomplete pair leaves the candidate pending, and pending candidates are never
  counted as included or excluded.
- Reversible report merges change the CURRENT representative sets from the merge's
  protocol version onward (historic snapshots keep their original sets). A merge with
  incompatible prior screening decisions forces an unresolved adjudication state on the
  merged candidate that affects counts until a named adjudicator decides; a
  report_split reverses the mapping.
- Adjudication is only recorded on a genuine disagreement: a stage the counts currently
  show as an open disagreement or an unresolved merge conflict. Counts, merge conflict
  detection and adjudication eligibility read one derivation (`_derive_decisions`).
- Historic snapshots are immutable: every versioned write targets the open snapshot (a
  version at or above the highest version any decision or mapping event carries). The full
  rule table, and what it makes impossible, is docs/work/RULES-review-versioning.md.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database.models import (ReviewCandidate, ReviewDecision, ReviewMappingEvent, ReviewOccurrence,
                                 ReviewProtocol, ReviewReport, ReviewReportStudy, ReviewReportVersion, ReviewStudy)
from . import research_access


def create_protocol(db: Session, project_id, actor_id, *, version, mode="literature", unit_of_analysis="report",
                    count_policy=None, criteria=None, screening_modes=None, parent_version_id=None,
                    status="active", protocol_id=None, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    if int(version) < 1: raise HTTPException(422, "Protocol versions start at 1")
    # Serialize before reading anything this insert depends on (R53): two creators of one version
    # must see each other (409, not a uniqueness error), and the mark must be the committed one.
    research_access.lock_project(db, project_id)
    exists = db.query(ReviewProtocol).filter(ReviewProtocol.project_id == project_id, ReviewProtocol.version == version).first()
    if exists: raise HTTPException(409, "Protocol version already exists")
    # A protocol row governs every snapshot from its version up to the next row. Inserting one at
    # or below a version that already carries review records would silently change the screening
    # mode those records were decided under, so a new protocol must open a new snapshot.
    high_water = _snapshot_high_water(db, project_id)
    if high_water and int(version) <= high_water:
        raise HTTPException(409, f"Protocol version {version} would re-govern closed snapshots: review records exist at "
                                 f"version {high_water}. Create version {high_water + 1} or later")
    row = ReviewProtocol(id=protocol_id or uuid4(), project_id=project_id, version=version, mode=mode,
                         unit_of_analysis=unit_of_analysis, count_policy=count_policy or {}, criteria=criteria or [],
                         screening_modes=screening_modes or {}, status=status, parent_version_id=parent_version_id)
    db.add(row)
    row.change_sequence = research_access.advance_change_sequence(db, project_id)
    db.flush()  # commit=False callers read this back in the same transaction (R54)
    if commit: db.commit()
    return row


def amend_protocol(db: Session, project_id, actor_id, *, new_version, criteria=None, status="active", commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    # The parent is read under the project lock: an amendment racing another must copy the
    # committed latest protocol, not the one it saw before waiting (R53).
    research_access.lock_project(db, project_id)
    current = db.query(ReviewProtocol).filter(ReviewProtocol.project_id == project_id).order_by(ReviewProtocol.version.desc()).first()
    if not current: raise HTTPException(404, "No review protocol to amend")
    # An amendment extends the chain: it copies the latest protocol, so it must sit above it (R54).
    if int(new_version) <= int(current.version):
        raise HTTPException(409, f"An amendment must be above the latest protocol (version {current.version})")
    amended = create_protocol(db, project_id, actor_id, version=new_version, mode=current.mode,
                              unit_of_analysis=current.unit_of_analysis, count_policy=current.count_policy,
                              criteria=current.criteria if criteria is None else criteria,
                              screening_modes=current.screening_modes,
                              parent_version_id=current.id, status=status, commit=False)
    db.add(ReviewMappingEvent(id=uuid4(), project_id=project_id, kind="protocol_amend",
                              payload={"from": str(current.id), "from_version": current.version,
                                       "to": str(amended.id), "to_version": new_version}, actor_id=actor_id))
    db.flush()  # draw the durable sequence anchor at call order
    if commit: db.commit()
    return amended


def map_occurrences(db: Session, project_id, actor_id, candidate_id, retained_occurrence_id, removed_occurrence_ids, *, protocol_version=1, commit=True):
    """Record one occurrence→candidate mapping: exactly one retained representative,
    every other mapped occurrence an inspectable removal. Sets must be disjoint."""
    research_access.authorize(db, project_id, actor_id, write=True)
    _require_open_snapshot(db, project_id, protocol_version)
    # Lock the candidate row before reading its mappings: two concurrent FIRST mappings onto the
    # same candidate lock disjoint occurrence rows and would otherwise both read an empty history
    # and both pass the single-representative guard. The candidate lock serializes them so the loser
    # re-reads the winner's committed representative (R49). Occurrence ownership locks still apply.
    candidate = db.query(ReviewCandidate).filter(ReviewCandidate.id == candidate_id, ReviewCandidate.project_id == project_id).with_for_update().first()
    if not candidate: raise HTTPException(404, "Review candidate not found")
    # Mapped occurrences are accounted under their candidate: a non-retained candidate
    # would remove them from flow accounting (R26).
    if not candidate.retained: raise HTTPException(422, "Cannot map occurrences onto a non-retained candidate")
    mapped = [str(retained_occurrence_id), *[str(i) for i in removed_occurrence_ids]]
    if len(set(mapped)) != len(mapped): raise HTTPException(422, "Mapping sets must be disjoint")
    # Lock the mapped occurrence rows in id order before reading ownership: competing claims
    # on the same occurrence serialize, so the loser re-reads the winner's committed mapping
    # instead of both inserting (R47). Ascending id avoids deadlock between overlapping sets.
    rows = db.query(ReviewOccurrence).filter(ReviewOccurrence.id.in_(mapped), ReviewOccurrence.project_id == project_id).order_by(ReviewOccurrence.id).with_for_update().all()
    if {str(r.id) for r in rows} != set(mapped): raise HTTPException(422, "Occurrences must belong to this project")
    # A mapping cannot place an occurrence or candidate into an earlier snapshot than the
    # acquisition set that introduced it (R13/R14).
    premature = [str(r.id) for r in rows if r.protocol_version > protocol_version]
    if premature: raise HTTPException(422, "Mapping protocol version predates the occurrence acquisition")
    if candidate.protocol_version > protocol_version:
        raise HTTPException(422, "Mapping protocol version predates the candidate acquisition")
    # An occurrence belongs to exactly one candidate. Ownership is global — every recorded
    # mapping at any protocol version — and keyed by raw candidate id, not the merge-resolved
    # representative: a backdated mapping cannot slip past a later claim, and a merge never
    # transfers ownership, so splitting a merge can never restore two candidates sharing one
    # occurrence (R47). Consolidating two live candidates is merge_reports, not a remap.
    owner = {}
    target = str(candidate_id)
    target_events = []
    prior = db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == project_id,
                                                ReviewMappingEvent.kind == "occurrence_map").all()
    for event in sorted(prior, key=_event_order):
        payload = event.payload or {}
        event_candidate = str(payload.get("candidate"))
        for occurrence_id in [payload.get("retained"), *payload.get("removed", [])]:
            if occurrence_id: owner[str(occurrence_id)] = event_candidate
        if event_candidate == target:
            target_events.append((int(payload.get("protocol_version", 1)),
                                  str(payload["retained"]) if payload.get("retained") else None,
                                  [str(i) for i in payload.get("removed", [])]))
    for occurrence_id in mapped:
        if occurrence_id in owner and owner[occurrence_id] != target:
            raise HTTPException(409, "Occurrence already belongs to another candidate; merge reports instead of remapping")
    # A candidate retains exactly one representative occurrence at EVERY affected snapshot. A
    # mapping at version V applies to all snapshots S >= V; replaying only the final global state
    # can hide a historical snapshot where the candidate carries two retained representatives
    # (R49: v1 retain O1; v3 retain O2/remove O1; v2 retain O3/remove O2 leaves O1 and O3 both
    # retained at v2). Validate each affected snapshot — the candidate row is locked above, so
    # this validation and the insert are atomic. The new event draws the next durable sequence,
    # so it replays last within every snapshot it enters.
    new_retained = str(retained_occurrence_id)
    new_removed = {str(i) for i in removed_occurrence_ids}
    snapshots = {protocol_version}
    snapshots.update(p.version for p in db.query(ReviewProtocol).filter(
        ReviewProtocol.project_id == project_id, ReviewProtocol.version >= protocol_version).all())
    snapshots.update(version for version, _r, _rm in target_events if version >= protocol_version)
    for snapshot in sorted(snapshots):
        retained_set = set()
        for version, retained_id, removed_ids in target_events:
            if version > snapshot: continue
            retained_set.difference_update(removed_ids)
            if retained_id: retained_set.add(retained_id)
        retained_set.difference_update(new_removed)
        retained_set.add(new_retained)
        if len(retained_set) != 1:
            raise HTTPException(409, "A candidate retains exactly one representative at every affected snapshot; record the previous representative as removed when replacing it")
    db.add(ReviewMappingEvent(id=uuid4(), project_id=project_id, kind="occurrence_map",
                              payload={"candidate": str(candidate_id), "retained": str(retained_occurrence_id),
                                       "removed": [str(i) for i in removed_occurrence_ids],
                                       "protocol_version": protocol_version}, actor_id=actor_id))
    db.flush()  # draw the durable sequence anchor at call order
    receipt = {"change_sequence": research_access.advance_change_sequence(db, project_id)}
    db.flush()  # commit=False callers read this back in the same transaction (R54)
    if commit: db.commit()
    return receipt


def _protocol_for(db: Session, project_id, protocol_version):
    protocol = db.query(ReviewProtocol).filter(ReviewProtocol.project_id == project_id,
                                               ReviewProtocol.version <= protocol_version).order_by(ReviewProtocol.version.desc()).first()
    if not protocol: raise HTTPException(404, "No review protocol covers this version")
    return protocol


_VERSIONED_EVENT_KINDS = ("occurrence_map", "report_merge", "report_split", "study_link")


def _snapshot_high_water(db: Session, project_id):
    """The highest protocol version any review RECORD of this project carries: decisions and
    versioned mapping events. Zero means nothing is recorded (versions start at 1, so zero is
    never a version). Protocol rows do not count: an amended protocol with nothing recorded
    under it yet has not closed the previous snapshot."""
    decisions = db.query(func.max(ReviewDecision.protocol_version)).join(
        ReviewCandidate, ReviewCandidate.id == ReviewDecision.candidate_id).filter(
        ReviewCandidate.project_id == project_id).scalar() or 0
    events = db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == project_id,
                                                 ReviewMappingEvent.kind.in_(_VERSIONED_EVENT_KINDS)).all()
    mapped = max((int((event.payload or {}).get("protocol_version", 1)) for event in events), default=0)
    return max(int(decisions), mapped)


def _require_open_snapshot(db: Session, project_id, protocol_version):
    """Historic snapshots are immutable (strategy 6.1: "historic flow snapshots retain their
    original sets"; a later change "cannot rewrite historical counts or final decisions").

    A snapshot closes as soon as any decision or versioned mapping event exists at a later
    protocol version. Every versioned review write — mapping, decision, study link, merge, split —
    must target the open snapshot: its version must be at or above the project's high-water mark.
    This one rule replaces the per-write simulations of "every later affected snapshot" (R48-R52):
    with no backdated writes there is no later snapshot a write could invalidate. Writers are
    serialized on the project root row first, so two writers cannot each pass the check against a
    stale mark. A governing protocol must already exist: a record written before any protocol
    would set the mark and then block the protocol that was meant to govern it (R53)."""
    if int(protocol_version) < 1: raise HTTPException(422, "Protocol versions start at 1")
    research_access.lock_project(db, project_id)
    high_water = _snapshot_high_water(db, project_id)
    if int(protocol_version) < high_water:
        raise HTTPException(409, f"Protocol snapshot {protocol_version} is closed: review records exist at version "
                                 f"{high_water}. Historic snapshots are immutable; record at version {high_water} or later")
    return _protocol_for(db, project_id, protocol_version)


def record_decision(db: Session, project_id, actor_id, candidate_id, stage, protocol_version, decision, *,
                    role="primary", reason="", cited_text=None, criterion_judgments=None, decision_id=None, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    protocol = _require_open_snapshot(db, project_id, protocol_version)
    candidate = db.query(ReviewCandidate).filter(ReviewCandidate.id == candidate_id, ReviewCandidate.project_id == project_id).first()
    if not candidate: raise HTTPException(404, "Review candidate not found")
    # Lock the candidate's report row so a concurrent merge serializes with this decision:
    # merge_reports locks the same rows, so the loser re-reads the committed merge state instead
    # of recording a decision on a candidate the merge just folded away (R49).
    db.query(ReviewReport).filter(ReviewReport.id == candidate.report_id,
                                  ReviewReport.project_id == project_id).with_for_update().first()
    if decision not in ("included", "excluded", "unclear"): raise HTTPException(422, "Invalid decision value")
    if candidate.protocol_version > protocol_version:
        raise HTTPException(422, "Decision protocol version predates the candidate acquisition")
    # A decision belongs to a live candidate at the requested snapshot. Once a report is merged
    # away its candidate leaves the retained set, so a later decision on it would be silently
    # omitted from counts (R49: include the merged source, exclude the representative, and the
    # inclusion vanishes). Decide on the current representative instead; pre-merge decisions and
    # adjudications on the representative are unaffected.
    merges, _decided, pending, _candidate_of = _decision_state(db, project_id, protocol_version)
    if _resolve_representative(merges, str(candidate.report_id)) != str(candidate.report_id):
        raise HTTPException(409, "Candidate is merged away at this protocol snapshot; record the decision on the current representative")
    prior = db.query(ReviewDecision).filter(ReviewDecision.candidate_id == candidate_id,
                                            ReviewDecision.stage == stage).all()
    if role == "adjudication":
        # The disagreement is looked up at the REQUESTED snapshot, not at the version of the
        # protocol row that governs it: with only protocol v1, a merge and opposing decisions
        # recorded at v2 are a v2 conflict and must be adjudicable at v2 (R52). It is the same
        # derivation the counts use: adjudicable means the counts show this stage as an open
        # disagreement right now, so a resolved or superseded conflict is not adjudicable (R53).
        if pending.get((str(candidate.id), stage)) not in _ADJUDICABLE:
            raise HTTPException(409, "Adjudication is only recorded on a genuine disagreement")
    elif (protocol.screening_modes or {}).get(stage, "solo") == "dual":
        mine = [d for d in prior if str(d.actor_id) == str(actor_id)
                and d.protocol_version == protocol_version and d.role != "adjudication"]
        if mine: raise HTTPException(409, "Reviewer already recorded a decision for this stage and protocol version")
    if stage == "fulltext" and candidate.selected_version_id is None and decision == "included":
        raise HTTPException(409, "Cannot include a report whose selected version was never retrieved")
    # No merge-conflict simulation here. The snapshot is open, so this decision cannot predate a
    # merge; it is recorded on the live representative and governs the merged candidate from this
    # version on, as an amendment cohort does in compute_flow_counts. A merge compares PRIOR
    # decisions only, at the moment it is recorded.
    row = ReviewDecision(id=decision_id or uuid4(), candidate_id=candidate_id, stage=stage,
                         protocol_version=protocol_version, actor_id=actor_id, decision=decision,
                         role=role, reason=reason, cited_text=cited_text,
                         criterion_judgments=criterion_judgments or [])
    db.add(row)
    db.flush()  # draw the durable sequence anchor at call order
    row.change_sequence = research_access.advance_change_sequence(db, project_id)
    db.flush()  # commit=False callers read this back in the same transaction (R54)
    if commit: db.commit()
    return row


def _merge_state(mapping_events, protocol_version):
    """Replay merge and split events up to a snapshot, in durable order (timestamps cannot replay
    events, R20). Returns the report→report merge map and, per CURRENT representative and stage,
    the conflicting merges attached to it. Conflicts follow the chain (R4: A→B then B→C keeps the
    A-vs-B adjudication pending on C), accumulate per representative and stage, and each keeps its
    own resolution boundary. A split removes the mapping and the conflicts its source caused."""
    merge_map, conflict_stages = {}, {}
    for event in sorted(mapping_events, key=_event_order):
        kind = field(event, "kind")
        payload = field(event, "payload") or {}
        if kind not in ("report_merge", "report_split") or int(payload.get("protocol_version", 1)) > protocol_version:
            continue
        source = str(payload["source"])
        if kind == "report_merge":
            merge_map[source] = str(payload["target"])
            for conflict in payload.get("conflicting_decisions", []):
                conflict_stages.setdefault(str(payload["target"]), {}).setdefault(conflict["stage"], []).append(
                    {"source": source, "version": int(payload.get("protocol_version", 1)),
                     "created_at": field(event, "created_at"), "event_sequence": field(event, "event_sequence")})
        else:
            merge_map.pop(source, None)
            for staged in conflict_stages.values():
                for stage in list(staged):
                    staged[stage] = [merge for merge in staged[stage] if merge["source"] != source]
                    if not staged[stage]: del staged[stage]
    chained = {}
    for target, staged in conflict_stages.items():
        bucket = chained.setdefault(_resolve_representative(merge_map, target), {})
        for stage, merges in staged.items():
            bucket.setdefault(stage, []).extend(merges)
    return merge_map, chained


_ADJUDICABLE = ("disagreement", "merge_conflict")


def _derive_decisions(candidate_ids, decisions, conflict_stages, report_of_candidate, protocol_version, mode_for):
    """THE derivation of screening outcomes at a snapshot. Counts, merge conflict detection and
    adjudication eligibility all read this result, so they cannot disagree (R53).

    Returns (effective, pending): effective maps (candidate id, stage) to a decided value;
    pending maps it to the reason it is undecided — "merge_conflict" (a conflicting merge with
    no standing resolution), "disagreement" (the governing cohort differs) or "incomplete" (a
    dual stage with fewer than two distinct reviewers). A key in neither has no decision.

    Per candidate and stage, among records at or below the snapshot version:
    - An adjudication STANDS when it resolves after every conflicting merge attached to the
      candidate (R21/R22) and no screening decision exists at a higher protocol version. A
      standing adjudication decides the stage: it is final within its version (owner decision,
      2026-11-18), whatever is recorded at that version afterwards.
    - Otherwise a conflicting merge with no resolving adjudication leaves the stage pending.
    - Otherwise the screening cohort of the latest version governs under the stage's mode, each
      actor's latest submission counting once (R13/R17/R19): a solo stage decides on one agreed
      value, a dual stage needs two distinct reviewers who agree."""
    by_key = {}
    for decision in decisions:
        if int(field(decision, "protocol_version")) <= protocol_version:
            by_key.setdefault((str(field(decision, "candidate_id")), field(decision, "stage")), []).append(decision)
    version = lambda decision: int(field(decision, "protocol_version"))
    effective, pending = {}, {}
    for candidate_id in candidate_ids:
        flagged = conflict_stages.get(report_of_candidate.get(candidate_id, "")) or {}
        for stage in ("title_abstract", "fulltext"):
            key = (candidate_id, stage)
            rows, merges = by_key.get(key, []), flagged.get(stage, [])
            if not rows and not merges: continue
            screening = [row for row in rows if field(row, "role") != "adjudication"]
            standing = [row for row in rows if field(row, "role") == "adjudication"
                        and all(_resolves_after(row, merge) for merge in merges)]
            resolution = _latest_decision(standing) if standing else None
            newest = _latest_decision(screening) if screening else None
            if resolution is not None and (newest is None or version(resolution) >= version(newest)):
                effective[key] = field(resolution, "decision")
                continue
            if merges and resolution is None:
                pending[key] = "merge_conflict"
                continue
            if not screening: continue
            top = max(int(field(row, "protocol_version")) for row in screening)
            cohort = _latest_per_actor([row for row in screening if int(field(row, "protocol_version")) == top])
            values = {field(row, "decision") for row in cohort}
            if len(values) > 1: pending[key] = "disagreement"
            elif mode_for(stage) == "dual" and len(cohort) < 2: pending[key] = "incomplete"
            else: effective[key] = values.pop()
    return effective, pending


def _decision_state(db: Session, project_id, protocol_version):
    """Load a snapshot and derive it once: (merge map, effective, pending, report→candidate id)."""
    events = db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == project_id,
                                                 ReviewMappingEvent.kind.in_(("report_merge", "report_split"))).all()
    merge_map, conflict_stages = _merge_state(events, protocol_version)
    candidates = [row for row in db.query(ReviewCandidate).filter(ReviewCandidate.project_id == project_id).all()
                  if int(row.protocol_version or 1) <= protocol_version]
    decisions = db.query(ReviewDecision).join(ReviewCandidate, ReviewCandidate.id == ReviewDecision.candidate_id).filter(
        ReviewCandidate.project_id == project_id).all()
    protocol = db.query(ReviewProtocol).filter(ReviewProtocol.project_id == project_id,
                                               ReviewProtocol.version <= protocol_version).order_by(ReviewProtocol.version.desc()).first()
    modes = (protocol.screening_modes if protocol else None) or {}
    report_of_candidate = {str(row.id): str(row.report_id) for row in candidates}
    effective, pending = _derive_decisions(set(report_of_candidate), decisions, conflict_stages, report_of_candidate,
                                           protocol_version, lambda stage: modes.get(stage, "solo"))
    return merge_map, effective, pending, {report: candidate for candidate, report in report_of_candidate.items()}


def field(row, name):
    return row.get(name) if isinstance(row, dict) else getattr(row, name)


def as_time(value):
    if value is None: return datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try: return datetime.fromisoformat(value)
        except ValueError: return datetime.min.replace(tzinfo=timezone.utc)
    return value


def _resolves_after(decision, merge):
    """Does this adjudication resolve the merge event? Both bounds must hold (R21):
    the adjudication's protocol version covers the merge version, AND the durable
    shared-sequence order places it after the merge (same-transaction inserts still
    order strictly); version-then-timestamp otherwise."""
    if int(field(decision, "protocol_version")) < int(merge["version"]):
        return False
    res_seq, merge_seq = field(decision, "event_sequence"), field(merge, "event_sequence")
    if res_seq is not None and merge_seq is not None:
        return int(res_seq) > int(merge_seq)
    return (int(field(decision, "protocol_version")) > int(merge["version"])
            or (int(field(decision, "protocol_version")) == int(merge["version"])
                and as_time(field(decision, "created_at")) > as_time(merge.get("created_at"))))


def _latest_per_actor(rows):
    """Each actor's latest decision, deterministically by (protocol version, durable
    event order); repeated solo submissions cannot make counts order-dependent (R13/R19)."""
    grouped = {}
    for row in rows: grouped.setdefault(str(field(row, "actor_id")), []).append(row)
    return [_latest_decision(members) for members in grouped.values()]


def _event_order(row):
    """Durable ordering anchor: the shared event sequence when present (same-transaction
    inserts still order strictly); timestamp otherwise (pure-function inputs)."""
    seq = field(row, "event_sequence")
    if seq is not None: return (1, int(seq))
    return (0, as_time(field(row, "created_at")).timestamp())


def _latest_decision(rows):
    """Deterministic selection: highest protocol version, then durable event order —
    input order, wall-clock ties and UUID order never change the outcome (R19)."""
    return sorted(rows, key=lambda row: (int(field(row, "protocol_version")), _event_order(row)))[-1]


def _resolve_representative(merges, report):
    seen = set()
    while report in merges and report not in seen:
        seen.add(report); report = merges[report]
    return report


def visible_decisions(db: Session, project_id, actor_id, protocol_version):
    """Dual stages hide the other reviewers' decisions until decisions from at least two
    distinct reviewers exist for that candidate/stage/version; solo stages are visible."""
    research_access.authorize(db, project_id, actor_id)
    # Historical reads see only the decisions that existed at the requested snapshot (R14).
    rows = db.query(ReviewDecision).join(ReviewCandidate, ReviewCandidate.id == ReviewDecision.candidate_id).filter(
        ReviewCandidate.project_id == project_id, ReviewDecision.protocol_version <= protocol_version,
        ReviewCandidate.protocol_version <= protocol_version).order_by(ReviewDecision.created_at).all()
    protocols = {p.version: p for p in db.query(ReviewProtocol).filter(ReviewProtocol.project_id == project_id).all()}

    def mode_for(version, stage):
        candidates = [p for v, p in protocols.items() if v <= version]
        protocol = max(candidates, key=lambda p: p.version) if candidates else None
        return (protocol.screening_modes or {}).get(stage, "solo") if protocol else "solo"

    grouped = {}
    for row in rows:
        if mode_for(row.protocol_version, row.stage) == "dual":
            grouped.setdefault((row.candidate_id, row.stage, row.protocol_version, "dual"), []).append(row)
        else:
            grouped.setdefault((row.candidate_id, row.stage, row.protocol_version, "solo"), []).append(row)
    visible = []
    for key, group in grouped.items():
        if key[3] == "solo":
            visible.extend(group)  # solo decisions are final and visible
            continue
        primary = [r for r in group if r.role in ("primary", "secondary")]
        if len({str(r.actor_id) for r in primary}) < 2:
            visible.extend(r for r in group if r.actor_id == actor_id)
        else:
            visible.extend(group)
    return visible


def link_study(db: Session, project_id, actor_id, report_id, study_id, rationale, *, linkage_state="confirmed", protocol_version=1, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    _require_open_snapshot(db, project_id, protocol_version)
    report = db.query(ReviewReport).filter(ReviewReport.id == report_id, ReviewReport.project_id == project_id).first()
    study = db.query(ReviewStudy).filter(ReviewStudy.id == study_id, ReviewStudy.project_id == project_id).first()
    if not report or not study: raise HTTPException(422, "Report and study must belong to this project")
    if not (rationale or "").strip(): raise HTTPException(422, "Study linkage requires recorded rationale")
    existing = db.query(ReviewReportStudy).filter(ReviewReportStudy.report_id == report_id, ReviewReportStudy.study_id == study_id).first()
    if existing:
        existing.linkage_state = linkage_state; existing.rationale = rationale
    else:
        # A first-time linkage belongs to the acquisition-set update that introduced it.
        db.add(ReviewReportStudy(report_id=report_id, study_id=study_id, linkage_state=linkage_state,
                                 protocol_version=protocol_version, rationale=rationale))
    db.add(ReviewMappingEvent(id=uuid4(), project_id=project_id, kind="study_link",
                              payload={"report": str(report_id), "study": str(study_id),
                                       "linkage_state": linkage_state, "rationale": rationale,
                                       "protocol_version": protocol_version}, actor_id=actor_id))
    db.flush()  # draw the durable sequence anchor at call order
    change_sequence = research_access.advance_change_sequence(db, project_id)
    db.flush()  # commit=False callers read this back in the same transaction (R54)
    if commit: db.commit()
    return {"change_sequence": change_sequence}


def merge_reports(db: Session, project_id, actor_id, source_report_id, target_report_id, rationale, *, protocol_version, commit=True):
    """Reversible report merge: changes the current representative sets from this protocol
    version onward. Incompatible prior screening decisions force an unresolved adjudication
    state on the merged candidate until a named adjudicator decides. Both rows are locked
    in id order, the target must be an unmerged representative, and cycles are rejected."""
    research_access.authorize(db, project_id, actor_id, write=True)
    _require_open_snapshot(db, project_id, protocol_version)
    if source_report_id == target_report_id: raise HTTPException(422, "Merge requires two distinct project reports")
    # Deterministic lock order (ascending id) so concurrent merges cannot deadlock; a
    # locking read re-observes the latest committed state, so a racing opposite merge loses.
    first, second = sorted([UUID(str(source_report_id)), UUID(str(target_report_id))])
    db.query(ReviewReport).filter(ReviewReport.id == first).with_for_update().first()
    db.query(ReviewReport).filter(ReviewReport.id == second).with_for_update().first()
    source = db.query(ReviewReport).filter(ReviewReport.id == UUID(str(source_report_id)), ReviewReport.project_id == project_id).first()
    target = db.query(ReviewReport).filter(ReviewReport.id == UUID(str(target_report_id)), ReviewReport.project_id == project_id).first()
    if not source or not target: raise HTTPException(422, "Merge requires two distinct project reports")
    db.refresh(source); db.refresh(target)  # committed identity state, even when cached (R39)
    if source.identity_state == "merged": raise HTTPException(409, "Source report is already merged")
    if target.identity_state == "merged": raise HTTPException(409, "Target is already merged; merge into the current representative")
    # Both candidates must exist in the requested snapshot: merging onto (or from) a
    # candidate introduced by a later acquisition set would corrupt historic counts (R23).
    # The target must be retained — folding occurrences into a non-retained candidate
    # would remove them from accounting and break conservation (R24).
    for role, report in (("source", source), ("target", target)):
        candidate = db.query(ReviewCandidate).filter(ReviewCandidate.project_id == project_id,
                                                     ReviewCandidate.report_id == report.id).first()
        if not candidate or candidate.protocol_version > protocol_version:
            raise HTTPException(422, f"{role.capitalize()} candidate does not exist in the requested protocol snapshot")
        if role == "target" and not candidate.retained:
            raise HTTPException(422, "Merge target must be a retained candidate")
    # The snapshot is open (no record exists at a later version), so the merge graph at this
    # version is the only graph the new edge enters. A cycle exists iff the target already
    # reaches the source; a same-direction edge is redundant, not a cycle.
    merges_at_merge, effective, pending, candidate_of = _decision_state(db, project_id, protocol_version)
    visited = set()
    cursor = str(target.id)
    while cursor in merges_at_merge and cursor not in visited:
        visited.add(cursor)
        cursor = merges_at_merge[cursor]
        if cursor == str(source.id):
            raise HTTPException(409, "Merge would create a cycle between reports")
    # Conflicts are evaluated against the target's current representative, with the same derived
    # outcome the counts show for each side: comparing raw decisions would miss an adjudication a
    # later decision superseded, or a conflict an earlier merge left pending on either side (R53).
    target_rep = _resolve_representative(merges_at_merge, str(target.id))
    conflicts, stages = [], []
    for stage in ("title_abstract", "fulltext"):
        sides = [(candidate_of.get(report), stage) for report in (str(source.id), target_rep)]
        decided = [effective.get(side) for side in sides]
        # Decided values differ, or either side is undecided for any recorded reason — both force
        # adjudication on the merged candidate; an unresolved state must not vanish in the merge (R25).
        if any(side in pending for side in sides) or (decided[0] and decided[1] and decided[0] != decided[1]):
            conflicts.append({"stage": stage, "source": decided[0] or "unresolved", "target": decided[1] or "unresolved"})
            stages.append(stage)
    # No later-snapshot scan: the open-snapshot rule guarantees no decision, merge or split exists
    # above this version, so the conflicts recorded here are the complete picture.
    source.identity_state = "merged"; source.merged_into = target.id
    db.add(ReviewMappingEvent(id=uuid4(), project_id=project_id, kind="report_merge",
                              payload={"source": str(source.id), "target": str(target.id), "rationale": rationale,
                                       "conflicting_decisions": conflicts, "conflicting_stages": stages,
                                       "protocol_version": protocol_version}, actor_id=actor_id))
    db.flush()  # draw the durable sequence anchor at call order
    change_sequence = research_access.advance_change_sequence(db, project_id)
    db.flush()  # commit=False callers read this back in the same transaction (R54)
    if commit: db.commit()
    return {"conflicting_decisions": conflicts, "conflicting_stages": stages,
            "requires_adjudication": bool(conflicts), "change_sequence": change_sequence}


def split_report(db: Session, project_id, actor_id, source_report_id, rationale, *, protocol_version, commit=True):
    """Reverse a merge: the source report returns to its own candidate and its decisions."""
    research_access.authorize(db, project_id, actor_id, write=True)
    _require_open_snapshot(db, project_id, protocol_version)
    # Lock and refresh the report so a retained session re-reads the committed identity state:
    # another session may have merged it since this instance was cached (R50, mirrors R39).
    source = db.query(ReviewReport).filter(ReviewReport.id == source_report_id, ReviewReport.project_id == project_id).with_for_update().first()
    if not source: raise HTTPException(404, "Report not found")
    db.refresh(source)
    if source.identity_state != "merged": raise HTTPException(409, "Report is not merged")
    source.identity_state = "unreviewed"; source.merged_into = None
    db.add(ReviewMappingEvent(id=uuid4(), project_id=project_id, kind="report_split",
                              payload={"source": str(source.id), "rationale": rationale,
                                       "protocol_version": protocol_version}, actor_id=actor_id))
    db.flush()  # draw the durable sequence anchor at call order
    change_sequence = research_access.advance_change_sequence(db, project_id)
    db.flush()  # commit=False callers read this back in the same transaction (R54)
    if commit: db.commit()
    return {"change_sequence": change_sequence}


def compute_flow_counts(occurrences, mapping_events, candidates, decisions, report_studies, protocol_version,
                        screening_modes=None):
    """Pure count derivation (unit-testable without a database). Inputs are mappings/lists
    of plain dicts or model rows with the relevant attributes. Merges apply from their
    recorded protocol version onward; historic snapshots keep their original sets."""
    screening_modes = screening_modes or {}

    def mode_for(stage): return screening_modes.get(stage, "solo")

    def as_time(value):
        if value is None: return datetime.min.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try: return datetime.fromisoformat(value)
            except ValueError: return datetime.min.replace(tzinfo=timezone.utc)
        return value

    # Occurrence mapping state derives from versioned mapping events in durable order: a
    # later mapping of the same occurrence supersedes the earlier one, so the retained and
    # removed sets stay disjoint under supported remapping updates (R12); equal timestamps
    # cannot replay a split before its merge (R20).
    mapping_events = sorted(mapping_events, key=_event_order)
    occurrence_state = {}
    for event in mapping_events:
        payload = field(event, "payload") or {}
        if field(event, "kind") == "occurrence_map" and int(payload.get("protocol_version", 1)) <= protocol_version:
            for occurrence_id in payload.get("removed", []): occurrence_state[str(occurrence_id)] = "removed"
            if payload.get("retained"): occurrence_state[str(payload["retained"])] = "retained"
    merge_map, conflict_stages = _merge_state(mapping_events, protocol_version)
    # Frozen acquisition sets: occurrences, candidates and study linkages join the review
    # through versioned updates; a snapshot at protocol version V sees exactly the sets
    # that existed then (strategy 6.1).
    occurrences = [o for o in occurrences if int(field(o, "protocol_version") or 1) <= protocol_version]
    snapshot_ids = {str(field(o, "id")) for o in occurrences}
    identified = len(snapshot_ids)
    duplicate_removals = sum(1 for oid, state in occurrence_state.items() if state == "removed" and oid in snapshot_ids)
    merged_sources = set(merge_map)
    candidates = [c for c in candidates if int(field(c, "protocol_version") or 1) <= protocol_version]
    retained = [c for c in candidates if field(c, "retained") and str(field(c, "report_id")) not in merged_sources]
    representatives = {str(field(c, "report_id")) for c in retained}
    report_of_candidate = {str(field(c, "id")): str(field(c, "report_id")) for c in candidates}
    # Occurrence mapping conservation (R11): every identified occurrence is a recorded
    # duplicate removal or maps — through merge chains — onto a representative candidate;
    # a merge folds the source's occurrences into the target instead of losing them.
    mapped_occurrences = set()
    for event in mapping_events:
        if field(event, "kind") != "occurrence_map": continue
        payload = field(event, "payload") or {}
        if int(payload.get("protocol_version", 1)) > protocol_version: continue
        candidate_report = report_of_candidate.get(str(payload.get("candidate")))
        if candidate_report is None: continue
        if _resolve_representative(merge_map, candidate_report) in representatives:
            if payload.get("retained") and str(payload["retained"]) in snapshot_ids:
                mapped_occurrences.add(str(payload["retained"]))
            for occurrence_id in payload.get("removed", []): mapped_occurrences.discard(str(occurrence_id))
    # Study linkage states derive from the base rows plus versioned study_link events.
    link_states = {}
    for link in report_studies:
        # Base linkage rows only enter snapshots at or after the version that created them.
        if field(link, "study_id") and int(field(link, "protocol_version") or 1) <= protocol_version:
            link_states[(str(field(link, "report_id")), str(field(link, "study_id")))] = field(link, "linkage_state")
    for event in mapping_events:
        if field(event, "kind") != "study_link": continue
        payload = field(event, "payload") or {}
        if int(payload.get("protocol_version", 1)) > protocol_version: continue
        link_states[(str(payload.get("report")), str(payload.get("study")))] = payload.get("linkage_state")
    versioned_links = [{"report_id": report, "study_id": study, "linkage_state": state}
                       for (report, study), state in link_states.items()]
    candidate_ids = {str(field(c, "id")) for c in retained}

    effective, pending = _derive_decisions(candidate_ids, decisions, conflict_stages, report_of_candidate,
                                           protocol_version, mode_for)

    screened = [c for c in retained if (str(field(c, "id")), "title_abstract") in effective]
    ta_excluded = [c for c in screened if effective[(str(field(c, "id")), "title_abstract")] == "excluded"]
    sought = [c for c in screened if effective[(str(field(c, "id")), "title_abstract")] == "included"]
    not_retrieved = [c for c in sought
                     if field(c, "selected_version_id") is None
                     or effective.get((str(field(c, "id")), "fulltext")) == "unclear"]
    assessed = [c for c in sought if c not in not_retrieved and (str(field(c, "id")), "fulltext") in effective]
    ft_excluded = [c for c in assessed if effective[(str(field(c, "id")), "fulltext")] == "excluded"]
    included = [c for c in assessed if effective[(str(field(c, "id")), "fulltext")] == "included"]
    included_reports = {str(field(c, "report_id")) for c in included}
    studies = set()
    for link in versioned_links:
        # A merged source report's links resolve through its representative (R11):
        # merging A into B keeps A's confirmed study links counted, once.
        link_rep = _resolve_representative(merge_map, str(field(link, "report_id")))
        if field(link, "linkage_state") == "confirmed" and link_rep in included_reports:
            studies.add(str(field(link, "study_id")))
    return {
        "identified_occurrences": identified,
        "duplicate_removals": duplicate_removals,
        "retained_candidates": len(retained),
        "retained_occurrences": len(mapped_occurrences),
        "screened": len(screened),
        "title_abstract_excluded": len(ta_excluded),
        "reports_sought": len(sought),
        "not_retrieved": len(not_retrieved),
        "fulltext_assessed": len(assessed),
        "fulltext_excluded": len(ft_excluded),
        "included_reports": len(included_reports),
        "included_studies": len(studies),
        "pending_adjudication": len({candidate for candidate, _stage in pending}),
    }


def flow_counts(db: Session, project_id, actor_id, protocol_version):
    research_access.authorize(db, project_id, actor_id)
    protocol = db.query(ReviewProtocol).filter(ReviewProtocol.project_id == project_id,
                                               ReviewProtocol.version <= protocol_version).order_by(ReviewProtocol.version.desc()).first()
    # Frozen acquisition sets: an occurrence belongs to the acquisition-set update that
    # introduced it; historic snapshots keep their original sets (strategy 6.1).
    occurrences = db.query(ReviewOccurrence).filter(ReviewOccurrence.project_id == project_id,
                                                    ReviewOccurrence.protocol_version <= protocol_version).all()
    events = db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == project_id).order_by(
        ReviewMappingEvent.event_sequence).all()
    candidates = db.query(ReviewCandidate).filter(ReviewCandidate.project_id == project_id).all()
    decisions = db.query(ReviewDecision).join(ReviewCandidate, ReviewCandidate.id == ReviewDecision.candidate_id).filter(
        ReviewCandidate.project_id == project_id).all()
    links = db.query(ReviewReportStudy).join(ReviewReport, ReviewReport.id == ReviewReportStudy.report_id).filter(
        ReviewReport.project_id == project_id).all()
    return compute_flow_counts(occurrences, events, candidates, decisions, links, protocol_version,
                               screening_modes=protocol.screening_modes if protocol else None)
