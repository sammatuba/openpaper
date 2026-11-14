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
- Adjudication is only recorded on a genuine disagreement, where the decisions of
  reports currently merged into the candidate count toward the conflict.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.database.models import (ReviewCandidate, ReviewDecision, ReviewMappingEvent, ReviewOccurrence,
                                 ReviewProtocol, ReviewReport, ReviewReportStudy, ReviewReportVersion, ReviewStudy)
from . import research_access


def create_protocol(db: Session, project_id, actor_id, *, version, mode="literature", unit_of_analysis="report",
                    count_policy=None, criteria=None, screening_modes=None, parent_version_id=None,
                    status="active", protocol_id=None, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    exists = db.query(ReviewProtocol).filter(ReviewProtocol.project_id == project_id, ReviewProtocol.version == version).first()
    if exists: raise HTTPException(409, "Protocol version already exists")
    row = ReviewProtocol(id=protocol_id or uuid4(), project_id=project_id, version=version, mode=mode,
                         unit_of_analysis=unit_of_analysis, count_policy=count_policy or {}, criteria=criteria or [],
                         screening_modes=screening_modes or {}, status=status, parent_version_id=parent_version_id)
    db.add(row)
    if commit: db.commit()
    return row


def amend_protocol(db: Session, project_id, actor_id, *, new_version, criteria=None, status="active", commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    current = db.query(ReviewProtocol).filter(ReviewProtocol.project_id == project_id).order_by(ReviewProtocol.version.desc()).first()
    if not current: raise HTTPException(404, "No review protocol to amend")
    amended = create_protocol(db, project_id, actor_id, version=new_version, mode=current.mode,
                              unit_of_analysis=current.unit_of_analysis, count_policy=current.count_policy,
                              criteria=current.criteria if criteria is None else criteria,
                              screening_modes=current.screening_modes,
                              parent_version_id=current.id, status=status, commit=False)
    db.add(ReviewMappingEvent(id=uuid4(), project_id=project_id, kind="protocol_amend",
                              payload={"from": str(current.id), "from_version": current.version,
                                       "to": str(amended.id), "to_version": new_version}, actor_id=actor_id))
    if commit: db.commit()
    return amended


def map_occurrences(db: Session, project_id, actor_id, candidate_id, retained_occurrence_id, removed_occurrence_ids, *, protocol_version=1, commit=True):
    """Record one occurrence→candidate mapping: exactly one retained representative,
    every other mapped occurrence an inspectable removal. Sets must be disjoint."""
    research_access.authorize(db, project_id, actor_id, write=True)
    candidate = db.query(ReviewCandidate).filter(ReviewCandidate.id == candidate_id, ReviewCandidate.project_id == project_id).first()
    if not candidate: raise HTTPException(404, "Review candidate not found")
    mapped = [str(retained_occurrence_id), *[str(i) for i in removed_occurrence_ids]]
    if len(set(mapped)) != len(mapped): raise HTTPException(422, "Mapping sets must be disjoint")
    rows = db.query(ReviewOccurrence).filter(ReviewOccurrence.id.in_(mapped), ReviewOccurrence.project_id == project_id).all()
    if {str(r.id) for r in rows} != set(mapped): raise HTTPException(422, "Occurrences must belong to this project")
    # A mapping cannot place an occurrence into an earlier snapshot than the acquisition
    # set that introduced it (R13).
    premature = [str(r.id) for r in rows if r.protocol_version > protocol_version]
    if premature: raise HTTPException(422, "Mapping protocol version predates the occurrence acquisition")
    db.add(ReviewMappingEvent(id=uuid4(), project_id=project_id, kind="occurrence_map",
                              payload={"candidate": str(candidate_id), "retained": str(retained_occurrence_id),
                                       "removed": [str(i) for i in removed_occurrence_ids],
                                       "protocol_version": protocol_version}, actor_id=actor_id))
    if commit: db.commit()


def _protocol_for(db: Session, project_id, protocol_version):
    protocol = db.query(ReviewProtocol).filter(ReviewProtocol.project_id == project_id,
                                               ReviewProtocol.version <= protocol_version).order_by(ReviewProtocol.version.desc()).first()
    if not protocol: raise HTTPException(404, "No review protocol covers this version")
    return protocol


def record_decision(db: Session, project_id, actor_id, candidate_id, stage, protocol_version, decision, *,
                    role="primary", reason="", cited_text=None, criterion_judgments=None, decision_id=None, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    candidate = db.query(ReviewCandidate).filter(ReviewCandidate.id == candidate_id, ReviewCandidate.project_id == project_id).first()
    if not candidate: raise HTTPException(404, "Review candidate not found")
    if decision not in ("included", "excluded", "unclear"): raise HTTPException(422, "Invalid decision value")
    protocol = _protocol_for(db, project_id, protocol_version)
    prior = db.query(ReviewDecision).filter(ReviewDecision.candidate_id == candidate_id,
                                            ReviewDecision.stage == stage).all()
    if role == "adjudication":
        if not _has_conflict(db, project_id, candidate, stage, protocol):
            raise HTTPException(409, "Adjudication is only recorded on a genuine disagreement")
    elif (protocol.screening_modes or {}).get(stage, "solo") == "dual":
        mine = [d for d in prior if str(d.actor_id) == str(actor_id)
                and d.protocol_version == protocol_version and d.role != "adjudication"]
        if mine: raise HTTPException(409, "Reviewer already recorded a decision for this stage and protocol version")
    if stage == "fulltext" and candidate.selected_version_id is None and decision == "included":
        raise HTTPException(409, "Cannot include a report whose selected version was never retrieved")
    row = ReviewDecision(id=decision_id or uuid4(), candidate_id=candidate_id, stage=stage,
                         protocol_version=protocol_version, actor_id=actor_id, decision=decision,
                         role=role, reason=reason, cited_text=cited_text,
                         criterion_judgments=criterion_judgments or [])
    db.add(row)
    if commit: db.commit()
    return row


def _current_merges(db: Session, project_id, protocol_version):
    """Current report→report merge mapping and per-stage conflict sources from mapping
    events, applying only to protocol versions at or after each merge event. Splits
    remove a mapping. Events apply in creation order."""
    events = db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == project_id,
                                                 ReviewMappingEvent.kind.in_(("report_merge", "report_split"))).all()
    events.sort(key=lambda e: e.created_at or datetime.min.replace(tzinfo=timezone.utc))
    merges, conflict_stages = {}, {}
    for event in events:
        payload = event.payload or {}
        if int(payload.get("protocol_version", 1)) > protocol_version: continue
        if event.kind == "report_merge":
            merges[str(payload["source"])] = str(payload["target"])
            for conflict in payload.get("conflicting_decisions", []):
                conflict_stages.setdefault(str(payload["target"]), {}).setdefault(conflict["stage"], set()).add(str(payload["source"]))
        elif event.kind == "report_split":
            source = str(payload["source"])
            merges.pop(source, None)
            for staged in conflict_stages.values():
                for stage in list(staged):
                    staged[stage].discard(source)
                    if not staged[stage]: del staged[stage]

    def _representative(report):
        seen = set()
        while report in merges and report not in seen:
            seen.add(report); report = merges[report]
        return report

    # Conflicts and membership follow the chain: a report merged into a later
    # representative carries its unresolved conflicts there (R4: A→B then B→C must not
    # erase the pending adjudication recorded against B).
    chained_conflicts, incoming = {}, {}
    for source_report, target in merges.items():
        incoming.setdefault(_representative(target), set()).add(source_report)
    for target, staged in conflict_stages.items():
        for stage, sources in staged.items():
            rep = _representative(target)
            chained_conflicts.setdefault(rep, {}).setdefault(stage, set()).update(sources)
            incoming.setdefault(rep, set()).update(sources)
    return merges, chained_conflicts, incoming


def field(row, name):
    return row.get(name) if isinstance(row, dict) else getattr(row, name)


def as_time(value):
    if value is None: return datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try: return datetime.fromisoformat(value)
        except ValueError: return datetime.min.replace(tzinfo=timezone.utc)
    return value


def _latest_per_actor(rows):
    """Each actor's latest decision, deterministically by (protocol version, timestamp,
    id); repeated solo submissions cannot make counts order-dependent (R13)."""
    grouped = {}
    for row in rows: grouped.setdefault(str(field(row, "actor_id")), []).append(row)
    latest = []
    for members in grouped.values():
        latest.append(sorted(members, key=lambda row: (int(field(row, "protocol_version")),
                                                       as_time(field(row, "created_at")),
                                                       str(field(row, "id"))))[-1])
    return latest


def _latest_decision(rows):
    """Deterministic adjudication selection: highest protocol version, then latest
    timestamp, then id — input order never changes the outcome (R12)."""
    return sorted(rows, key=lambda row: (int(field(row, "protocol_version")),
                                         as_time(field(row, "created_at")),
                                         str(field(row, "id"))))[-1]


def _resolve_representative(merges, report):
    seen = set()
    while report in merges and report not in seen:
        seen.add(report); report = merges[report]
    return report


def _candidate_of_report(db: Session, project_id, report_id):
    row = db.query(ReviewCandidate).filter(ReviewCandidate.project_id == project_id,
                                           ReviewCandidate.report_id == report_id).first()
    return row.id if row else None


def _has_conflict(db: Session, project_id, candidate, stage, protocol):
    """Genuine disagreement among this candidate's decisions and the decisions of every
    report that feeds into it through the current merge chain, at this or an inherited
    conflicting stage."""
    merges, conflict_stages, incoming = _current_merges(db, project_id, protocol.version)
    report = str(candidate.report_id)
    merged_sources = set(incoming.get(report, set()))
    merged_sources |= (conflict_stages.get(report) or {}).get(stage, set())
    decisions = db.query(ReviewDecision).join(ReviewCandidate, ReviewCandidate.id == ReviewDecision.candidate_id).filter(
        ReviewCandidate.project_id == project_id).all()
    by_candidate = {}
    for row in decisions: by_candidate.setdefault(str(row.candidate_id), []).append(row)
    relevant = list(by_candidate.get(str(candidate.id), []))
    for source in merged_sources:
        candidate_id = _candidate_of_report(db, project_id, source)
        if candidate_id: relevant.extend(by_candidate.get(str(candidate_id), []))
    values = {row.decision for row in relevant
              if row.stage == stage and row.role != "adjudication" and row.protocol_version <= protocol.version}
    return len(values) > 1


def visible_decisions(db: Session, project_id, actor_id, protocol_version):
    """Dual stages hide the other reviewers' decisions until decisions from at least two
    distinct reviewers exist for that candidate/stage/version; solo stages are visible."""
    research_access.authorize(db, project_id, actor_id)
    rows = db.query(ReviewDecision).join(ReviewCandidate, ReviewCandidate.id == ReviewDecision.candidate_id).filter(
        ReviewCandidate.project_id == project_id).order_by(ReviewDecision.created_at).all()
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
    if commit: db.commit()


def merge_reports(db: Session, project_id, actor_id, source_report_id, target_report_id, rationale, *, protocol_version, commit=True):
    """Reversible report merge: changes the current representative sets from this protocol
    version onward. Incompatible prior screening decisions force an unresolved adjudication
    state on the merged candidate until a named adjudicator decides. Both rows are locked
    in id order, the target must be an unmerged representative, and cycles are rejected."""
    research_access.authorize(db, project_id, actor_id, write=True)
    if source_report_id == target_report_id: raise HTTPException(422, "Merge requires two distinct project reports")
    # Deterministic lock order (ascending id) so concurrent merges cannot deadlock; a
    # locking read re-observes the latest committed state, so a racing opposite merge loses.
    first, second = sorted([UUID(str(source_report_id)), UUID(str(target_report_id))])
    db.query(ReviewReport).filter(ReviewReport.id == first).with_for_update().first()
    db.query(ReviewReport).filter(ReviewReport.id == second).with_for_update().first()
    source = db.query(ReviewReport).filter(ReviewReport.id == UUID(str(source_report_id)), ReviewReport.project_id == project_id).first()
    target = db.query(ReviewReport).filter(ReviewReport.id == UUID(str(target_report_id)), ReviewReport.project_id == project_id).first()
    if not source or not target: raise HTTPException(422, "Merge requires two distinct project reports")
    if source.identity_state == "merged": raise HTTPException(409, "Source report is already merged")
    if target.identity_state == "merged": raise HTTPException(409, "Target is already merged; merge into the current representative")
    merges, _conflicts, _incoming = _current_merges(db, project_id, protocol_version)
    visited = set()
    cursor = str(target.id)
    while cursor in merges and cursor not in visited:
        visited.add(cursor)
        cursor = merges[cursor]
        if cursor == str(source.id):
            raise HTTPException(409, "Merge would create a cycle between reports")
    if _resolve_representative(merges, str(source.id)) == str(target.id):
        raise HTTPException(409, "Merge would create a cycle between reports")
    protocol = _protocol_for(db, project_id, protocol_version)
    conflicts, stages = [], []
    for stage in ("title_abstract", "fulltext"):
        source_decision = _effective(db, source.id, stage, protocol_version, protocol)
        target_decision = _effective(db, target.id, stage, protocol_version, protocol)
        if source_decision[0] and target_decision[0] and source_decision[0] != target_decision[0]:
            conflicts.append({"stage": stage, "source": source_decision[0], "target": target_decision[0]})
            stages.append(stage)
    source.identity_state = "merged"; source.merged_into = target.id
    db.add(ReviewMappingEvent(id=uuid4(), project_id=project_id, kind="report_merge",
                              payload={"source": str(source.id), "target": str(target.id), "rationale": rationale,
                                       "conflicting_decisions": conflicts, "conflicting_stages": stages,
                                       "protocol_version": protocol_version}, actor_id=actor_id))
    if commit: db.commit()
    return {"conflicting_decisions": conflicts, "conflicting_stages": stages, "requires_adjudication": bool(conflicts)}


def split_report(db: Session, project_id, actor_id, source_report_id, rationale, *, protocol_version, commit=True):
    """Reverse a merge: the source report returns to its own candidate and its decisions."""
    research_access.authorize(db, project_id, actor_id, write=True)
    source = db.query(ReviewReport).filter(ReviewReport.id == source_report_id, ReviewReport.project_id == project_id).first()
    if not source: raise HTTPException(404, "Report not found")
    if source.identity_state != "merged": raise HTTPException(409, "Report is not merged")
    source.identity_state = "unreviewed"; source.merged_into = None
    db.add(ReviewMappingEvent(id=uuid4(), project_id=project_id, kind="report_split",
                              payload={"source": str(source.id), "rationale": rationale,
                                       "protocol_version": protocol_version}, actor_id=actor_id))
    if commit: db.commit()


def _effective(db: Session, report_id, stage, protocol_version, protocol):
    """Effective final decision for a report/stage: adjudication wins; otherwise dual stages
    need decisions from two distinct reviewers that agree; solo stages decide on one. Returns
    (decision|None, state)."""
    rows = db.query(ReviewDecision).join(ReviewCandidate, ReviewCandidate.id == ReviewDecision.candidate_id).filter(
        ReviewCandidate.report_id == report_id, ReviewDecision.stage == stage,
        ReviewDecision.protocol_version <= protocol_version).order_by(ReviewDecision.protocol_version.desc()).all()
    by_version = {}
    for row in rows: by_version.setdefault(row.protocol_version, []).append(row)
    for version in sorted(by_version, reverse=True):
        group = by_version[version]
        adjudication = [r for r in group if r.role == "adjudication"]
        if adjudication: return _latest_decision(adjudication).decision, "decided"
        distinct = _latest_per_actor([row for row in group if row.role in ("primary", "secondary")])
        values = {r.decision for r in distinct}
        if (protocol.screening_modes or {}).get(stage, "solo") == "dual":
            if len(distinct) >= 2:
                if len(values) == 1: return values.pop(), "decided"
                return None, "adjudication"
            return None, "pending_dual"
        if len(distinct) >= 1 and len(values) == 1: return values.pop(), "decided"
        if len(values) > 1: return None, "adjudication"
    return None, "absent"


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

    # Occurrence mapping state derives from versioned mapping events in order: a later
    # mapping of the same occurrence supersedes the earlier one, so the retained and
    # removed sets stay disjoint under supported remapping updates (R12).
    occurrence_state = {}
    merge_map, conflict_stages = {}, {}
    for event in mapping_events:
        kind = field(event, "kind")
        payload = field(event, "payload") or {}
        if kind == "occurrence_map" and int(payload.get("protocol_version", 1)) <= protocol_version:
            for occurrence_id in payload.get("removed", []): occurrence_state[str(occurrence_id)] = "removed"
            if payload.get("retained"): occurrence_state[str(payload["retained"])] = "retained"
        elif kind == "report_merge" and int(payload.get("protocol_version", 1)) <= protocol_version:
            merge_map[str(payload["source"])] = str(payload["target"])
            for conflict in payload.get("conflicting_decisions", []):
                stages = conflict_stages.setdefault(str(payload["target"]), {})
                # Track every conflicting merge: resolution requires an adjudication recorded
                # no earlier than the latest conflicting merge it must resolve.
                stages.setdefault(conflict["stage"], []).append(
                    {"source": str(payload["source"]), "version": int(payload.get("protocol_version", 1)),
                     "created_at": field(event, "created_at")})
        elif kind == "report_split" and int(payload.get("protocol_version", 1)) <= protocol_version:
            merge_map.pop(str(payload["source"]), None)
            for staged in conflict_stages.values():
                for stage in list(staged):
                    staged[stage] = [m for m in staged[stage] if m.get("source") != str(payload["source"])]
                    if not staged[stage]: del staged[stage]
    # Conflicts follow the merge chain to the final representative (R4): A→B then B→C
    # keeps the A-vs-B adjudication pending on C instead of erasing it. Accumulation is
    # per representative AND stage: several links resolving to one representative must
    # union their conflicts, each keeping its own resolution boundary.
    chained_conflicts = {}
    for target, staged in conflict_stages.items():
        rep = _resolve_representative(merge_map, target)
        bucket = chained_conflicts.setdefault(rep, {})
        for stage, merges_list in staged.items():
            bucket.setdefault(stage, []).extend(merges_list)
    conflict_stages = chained_conflicts
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

    effective, pending = {}, set()
    for candidate_id in candidate_ids:
        for stage in ("title_abstract", "fulltext"):
            rows = [d for d in decisions
                    if str(field(d, "candidate_id")) == candidate_id and field(d, "stage") == stage
                    and int(field(d, "protocol_version")) <= protocol_version]
            if not rows: continue
            top = max(int(field(d, "protocol_version")) for d in rows)
            group = [d for d in rows if int(field(d, "protocol_version")) == top]
            adjudication = [d for d in group if field(d, "role") == "adjudication"]
            if adjudication:
                effective[(candidate_id, stage)] = field(_latest_decision(adjudication), "decision")
                continue
            distinct = {str(field(row, "actor_id")): field(row, "decision")
                        for row in _latest_per_actor([row for row in group if field(row, "role") in ("primary", "secondary")])}
            values = set(distinct.values())
            if mode_for(stage) == "dual":
                if len(distinct) >= 2 and len(values) == 1: effective[(candidate_id, stage)] = values.pop()
                else: pending.add((candidate_id, stage))
            elif len(distinct) >= 1 and len(values) == 1: effective[(candidate_id, stage)] = values.pop()
            elif len(values) > 1: pending.add((candidate_id, stage))
        # A merge with conflicting decisions forces adjudication on the merged candidate.
        # An adjudication resolves a conflict only if it was recorded no earlier than the
        # latest conflicting merge it resolves (same-version requires a later timestamp).
        for stage, merges in (conflict_stages.get(report_of_candidate.get(candidate_id, "")) or {}).items():
            latest = max(merges, key=lambda m: (m["version"], as_time(m.get("created_at"))))
            qualifying = [d for d in decisions
                          if str(field(d, "candidate_id")) == candidate_id and field(d, "stage") == stage
                          and field(d, "role") == "adjudication" and int(field(d, "protocol_version")) <= protocol_version
                          and (int(field(d, "protocol_version")) > latest["version"]
                               or (int(field(d, "protocol_version")) == latest["version"]
                                   and as_time(field(d, "created_at")) > as_time(latest.get("created_at"))))]
            if qualifying: effective[(candidate_id, stage)] = field(_latest_decision(qualifying), "decision")
            else:
                pending.add((candidate_id, stage))
                effective.pop((candidate_id, stage), None)

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
    events = db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == project_id).order_by(ReviewMappingEvent.created_at).all()
    candidates = db.query(ReviewCandidate).filter(ReviewCandidate.project_id == project_id).all()
    decisions = db.query(ReviewDecision).join(ReviewCandidate, ReviewCandidate.id == ReviewDecision.candidate_id).filter(
        ReviewCandidate.project_id == project_id).all()
    links = db.query(ReviewReportStudy).join(ReviewReport, ReviewReport.id == ReviewReportStudy.report_id).filter(
        ReviewReport.project_id == project_id).all()
    return compute_flow_counts(occurrences, events, candidates, decisions, links, protocol_version,
                               screening_modes=protocol.screening_modes if protocol else None)
