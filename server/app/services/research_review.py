"""Review identity model: occurrence/report/candidate/study records, mapping events and
count-derived flow computation (strategy 6.1, fixture 17.1, check C17).

Counts are always computed from actual records and append-only mapping events —
never from a stored picture. Disagreement without named adjudication leaves the
candidate pending; a reversible merge producing conflicting decisions also enters
adjudication rather than silently changing inclusion.
"""
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.database.models import (ReviewCandidate, ReviewDecision, ReviewMappingEvent, ReviewOccurrence,
                                 ReviewProtocol, ReviewReport, ReviewReportStudy, ReviewReportVersion, ReviewStudy)
from . import research_access


def create_protocol(db: Session, project_id, actor_id, *, version, mode="literature", unit_of_analysis="report",
                    count_policy=None, criteria=None, parent_version_id=None, status="active", protocol_id=None, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    exists = db.query(ReviewProtocol).filter(ReviewProtocol.project_id == project_id, ReviewProtocol.version == version).first()
    if exists: raise HTTPException(409, "Protocol version already exists")
    row = ReviewProtocol(id=protocol_id or uuid4(), project_id=project_id, version=version, mode=mode,
                         unit_of_analysis=unit_of_analysis, count_policy=count_policy or {}, criteria=criteria or [],
                         status=status, parent_version_id=parent_version_id)
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
                              parent_version_id=current.id, status=status, commit=False)
    db.add(ReviewMappingEvent(id=uuid4(), project_id=project_id, kind="protocol_amend",
                              payload={"from": str(current.id), "from_version": current.version,
                                       "to": str(amended.id), "to_version": new_version}, actor_id=actor_id))
    if commit: db.commit()
    return amended


def map_occurrences(db: Session, project_id, actor_id, candidate_id, retained_occurrence_id, removed_occurrence_ids, *, commit=True):
    """Record one occurrence→candidate mapping: exactly one retained representative,
    every other mapped occurrence an inspectable removal. Sets must be disjoint."""
    research_access.authorize(db, project_id, actor_id, write=True)
    candidate = db.query(ReviewCandidate).filter(ReviewCandidate.id == candidate_id, ReviewCandidate.project_id == project_id).first()
    if not candidate: raise HTTPException(404, "Review candidate not found")
    mapped = [str(retained_occurrence_id), *[str(i) for i in removed_occurrence_ids]]
    if len(set(mapped)) != len(mapped): raise HTTPException(422, "Mapping sets must be disjoint")
    rows = db.query(ReviewOccurrence).filter(ReviewOccurrence.id.in_(mapped), ReviewOccurrence.project_id == project_id).all()
    found = {str(r.id) for r in rows}
    if found != set(mapped): raise HTTPException(422, "Occurrences must belong to this project")
    db.add(ReviewMappingEvent(id=uuid4(), project_id=project_id, kind="occurrence_map",
                              payload={"candidate": str(candidate_id), "retained": str(retained_occurrence_id),
                                       "removed": [str(i) for i in removed_occurrence_ids]}, actor_id=actor_id))
    if commit: db.commit()


def record_decision(db: Session, project_id, actor_id, candidate_id, stage, protocol_version, decision, *,
                    role="primary", reason="", cited_text=None, criterion_judgments=None, decision_id=None, commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    candidate = db.query(ReviewCandidate).filter(ReviewCandidate.id == candidate_id, ReviewCandidate.project_id == project_id).first()
    if not candidate: raise HTTPException(404, "Review candidate not found")
    if decision not in ("included", "excluded", "unclear"): raise HTTPException(422, "Invalid decision value")
    if role == "adjudication":
        prior = db.query(ReviewDecision).filter(ReviewDecision.candidate_id == candidate_id,
                                                ReviewDecision.stage == stage).all()
        values = {d.decision for d in prior if d.role != "adjudication"}
        if len(values) < 2:
            raise HTTPException(409, "Adjudication is only recorded on a genuine disagreement")
    if stage == "fulltext" and candidate.selected_version_id is None and decision == "included":
        raise HTTPException(409, "Cannot include a report whose selected version was never retrieved")
    row = ReviewDecision(id=decision_id or uuid4(), candidate_id=candidate_id, stage=stage,
                         protocol_version=protocol_version, actor_id=actor_id, decision=decision,
                         role=role, reason=reason, cited_text=cited_text,
                         criterion_judgments=criterion_judgments or [])
    db.add(row)
    if commit: db.commit()
    return row


def visible_decisions(db: Session, project_id, actor_id, protocol_version):
    """Independent dual review hides the other reviewer's pending decision until both
    decisions for that candidate/stage exist (strategy 6.3)."""
    research_access.authorize(db, project_id, actor_id)
    rows = db.query(ReviewDecision).join(ReviewCandidate, ReviewCandidate.id == ReviewDecision.candidate_id).filter(
        ReviewCandidate.project_id == project_id, ReviewDecision.protocol_version == protocol_version).order_by(ReviewDecision.created_at).all()
    grouped = {}
    for row in rows: grouped.setdefault((row.candidate_id, row.stage), []).append(row)
    visible = []
    for key, group in grouped.items():
        dual = any(r.role in ("primary", "secondary") for r in group)
        if dual and len([r for r in group if r.role in ("primary", "secondary")]) < 2:
            visible.extend(r for r in group if r.actor_id == actor_id)
        else:
            visible.extend(group)
    return visible


def link_study(db: Session, project_id, actor_id, report_id, study_id, rationale, *, linkage_state="confirmed", commit=True):
    research_access.authorize(db, project_id, actor_id, write=True)
    report = db.query(ReviewReport).filter(ReviewReport.id == report_id, ReviewReport.project_id == project_id).first()
    study = db.query(ReviewStudy).filter(ReviewStudy.id == study_id, ReviewStudy.project_id == project_id).first()
    if not report or not study: raise HTTPException(422, "Report and study must belong to this project")
    if not (rationale or "").strip(): raise HTTPException(422, "Study linkage requires recorded rationale")
    existing = db.query(ReviewReportStudy).filter(ReviewReportStudy.report_id == report_id, ReviewReportStudy.study_id == study_id).first()
    if existing:
        existing.linkage_state = linkage_state; existing.rationale = rationale
    else:
        db.add(ReviewReportStudy(report_id=report_id, study_id=study_id, linkage_state=linkage_state, rationale=rationale))
    db.add(ReviewMappingEvent(id=uuid4(), project_id=project_id, kind="study_link",
                              payload={"report": str(report_id), "study": str(study_id),
                                       "linkage_state": linkage_state, "rationale": rationale}, actor_id=actor_id))
    if commit: db.commit()


def merge_reports(db: Session, project_id, actor_id, source_report_id, target_report_id, rationale):
    """Reversible report merge: records the event; incompatible prior screening decisions
    enter adjudication (return as conflicting) instead of choosing one silently."""
    research_access.authorize(db, project_id, actor_id, write=True)
    source = db.query(ReviewReport).filter(ReviewReport.id == source_report_id, ReviewReport.project_id == project_id).first()
    target = db.query(ReviewReport).filter(ReviewReport.id == target_report_id, ReviewReport.project_id == project_id).first()
    if not source or not target or source.id == target.id: raise HTTPException(422, "Merge requires two distinct project reports")
    if source.identity_state in ("merged",): raise HTTPException(409, "Source report is already merged")
    conflicts = []
    for stage in ("title_abstract", "fulltext"):
        source_decision = _effective(db, source.id, stage, None)
        target_decision = _effective(db, target.id, stage, None)
        if source_decision and target_decision and source_decision[0] != target_decision[0]:
            conflicts.append({"stage": stage, "source": source_decision[0], "target": target_decision[0]})
    source.identity_state = "merged"; source.merged_into = target.id
    db.add(ReviewMappingEvent(id=uuid4(), project_id=project_id, kind="report_merge",
                              payload={"source": str(source.id), "target": str(target.id), "rationale": rationale,
                                       "conflicting_decisions": conflicts}, actor_id=actor_id))
    db.commit()
    return {"conflicting_decisions": conflicts, "requires_adjudication": bool(conflicts)}


def _effective(db: Session, report_id, stage, protocol_version):
    """Effective final decision for a report/stage: adjudication wins; otherwise unanimous
    dual agreement; disagreement without adjudication is pending (None, 'adjudication')."""
    query = db.query(ReviewDecision).join(ReviewCandidate, ReviewCandidate.id == ReviewDecision.candidate_id).filter(
        ReviewCandidate.report_id == report_id, ReviewDecision.stage == stage)
    if protocol_version is not None: query = query.filter(ReviewDecision.protocol_version <= protocol_version)
    rows = query.order_by(ReviewDecision.protocol_version.desc()).all()
    by_version = {}
    for row in rows: by_version.setdefault(row.protocol_version, []).append(row)
    for version in sorted(by_version, reverse=True):
        group = by_version[version]
        adjudication = [r for r in group if r.role == "adjudication"]
        if adjudication: return adjudication[-1].decision, "decided"
        primary = [r for r in group if r.role in ("primary", "secondary")]
        values = {r.decision for r in primary}
        if len(primary) >= 2 and len(values) == 1: return values.pop(), "decided"
        if len(values) > 1: return None, "adjudication"
        if len(primary) == 1: return primary[0].decision, "pending_dual"
    return None, "absent"


def compute_flow_counts(occurrences, mapping_events, candidates, decisions, report_studies, protocol_version):
    """Pure count derivation (unit-testable without a database). Inputs are mappings/lists
    of plain dicts or model rows with the relevant attributes."""
    def field(row, name): return row.get(name) if isinstance(row, dict) else getattr(row, name)

    removed = set()
    for event in mapping_events:
        if field(event, "kind") != "occurrence_map": continue
        payload = field(event, "payload") or {}
        for occurrence_id in payload.get("removed", []): removed.add(str(occurrence_id))
    identified = len({str(field(o, "id")) for o in occurrences})
    duplicate_removals = len(removed)
    retained = [c for c in candidates if field(c, "retained")]
    candidate_ids = {str(field(c, "id")) for c in retained}

    def decision_rows():
        for d in decisions: yield d

    effective = {}
    for candidate_id in candidate_ids:
        for stage in ("title_abstract", "fulltext"):
            rows = [d for d in decision_rows()
                    if str(field(d, "candidate_id")) == candidate_id and field(d, "stage") == stage
                    and field(d, "protocol_version") <= protocol_version]
            if not rows: continue
            top = max(field(d, "protocol_version") for d in rows)
            group = [d for d in rows if field(d, "protocol_version") == top]
            adjudication = [d for d in group if field(d, "role") == "adjudication"]
            if adjudication:
                effective[(candidate_id, stage)] = field(adjudication[-1], "decision")
                continue
            primary = [d for d in group if field(d, "role") in ("primary", "secondary")]
            values = {field(d, "decision") for d in primary}
            if len(primary) >= 2 and len(values) == 1: effective[(candidate_id, stage)] = values.pop()
            elif len(values) > 1: effective[(candidate_id, stage)] = None  # pending adjudication
            elif len(primary) == 1: effective[(candidate_id, stage)] = field(primary[0], "decision")

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
    for link in report_studies:
        if field(link, "linkage_state") == "confirmed" and str(field(link, "report_id")) in included_reports:
            studies.add(str(field(link, "study_id")))
    return {
        "identified_occurrences": identified,
        "duplicate_removals": duplicate_removals,
        "retained_candidates": len(retained),
        "screened": len(screened),
        "title_abstract_excluded": len(ta_excluded),
        "reports_sought": len(sought),
        "not_retrieved": len(not_retrieved),
        "fulltext_assessed": len(assessed),
        "fulltext_excluded": len(ft_excluded),
        "included_reports": len(included_reports),
        "included_studies": len(studies),
    }


def flow_counts(db: Session, project_id, actor_id, protocol_version):
    research_access.authorize(db, project_id, actor_id)
    occurrences = db.query(ReviewOccurrence).filter(ReviewOccurrence.project_id == project_id).all()
    events = db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == project_id).all()
    candidates = db.query(ReviewCandidate).filter(ReviewCandidate.project_id == project_id).all()
    decisions = db.query(ReviewDecision).join(ReviewCandidate, ReviewCandidate.id == ReviewDecision.candidate_id).filter(
        ReviewCandidate.project_id == project_id).all()
    links = db.query(ReviewReportStudy).join(ReviewReport, ReviewReport.id == ReviewReportStudy.report_id).filter(
        ReviewReport.project_id == project_id).all()
    return compute_flow_counts(occurrences, events, candidates, decisions, links, protocol_version)
