"""Deterministic v1 -> typed research conversion (contract 6, check C10).

One transaction: lock the v1 investigation row, build typed records, verify the
comparison inside the transaction, then flip the authoritative storage generation
and write the manifest. Any mismatch or failure aborts with no partial state; the
v1 snapshot is retained read-only and never modified. Production cutover is not
part of this package.
"""
import json
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.database.models import (Paper, ProjectInvestigation, ResearchEntity, ResearchEntityRevision,
                                 ResearchProject, ResearchRelation, ResearchSourceVersion)
from . import research_access


CONVERTER_VERSION = "research_core_v1"


def _v1_claim_payload(claim):
    return {"statement": claim["statement"], "reasoning": claim.get("reasoning", ""),
            "caveats": claim.get("caveats", ""), "status": "provisional"}


def _v1_finding_payload(finding, source_version_id, unresolved):
    source = finding["source"]
    setup = finding.get("setup") or {}
    payload = {"label": finding["label"], "observed_result": finding.get("observed_result", ""),
               "author_interpretation": finding.get("author_interpretation", ""),
               "our_interpretation": finding.get("our_interpretation", ""),
               "limitations": finding.get("limitations", ""),
               "setup": {key: setup.get(key, "") for key in ("model", "task", "training", "intervention", "evaluation", "other")}}
    if source["kind"] == "anchored" and not unresolved:
        payload["anchor"] = {"source_version_id": source_version_id, "start_line": source["start_line"],
                             "end_line": source["end_line"], "quote": source["quote"],
                             "quote_sha256": source["quote_sha256"], "page_span": source.get("page_span")}
    elif source["kind"] == "unbound":
        payload["anchor"] = {"origin_locator": source.get("origin_locator", ""), "notes": source.get("notes", "")}
    elif source["kind"] == "redacted":
        payload["anchor"] = {"paper_id": source["paper_id"]}
    else:  # anchored but unbindable: hash mismatch — never auto-bind (strategy 10.3)
        payload["anchor"] = {"origin_locator": str(source["paper_id"]),
                             "notes": "v1 anchor unbound: source hash mismatch at conversion; requires review"}
    return payload


def convert_project(db: Session, project_id, actor_id):
    research_access.authorize(db, project_id, actor_id, write=True)
    root = db.query(ResearchProject).filter(ResearchProject.project_id == project_id).with_for_update().first()
    if root and root.storage_generation == "v2":
        raise HTTPException(409, "Project research storage is already converted")
    row = db.query(ProjectInvestigation).filter(ProjectInvestigation.project_id == project_id).with_for_update().first()
    document = json.loads(json.dumps(row.document)) if row else {}
    revision_at_read = row.revision if row else None
    claims = document.get("claims", [])
    findings = document.get("findings", [])
    relations = document.get("relations", [])
    sections = document.get("manuscript", {}).get("sections", [])

    # Source versions: each finding's own source hash is matched independently against the
    # paper's current bytes (strategy 10.3). One paper can therefore yield several versions
    # only if its current bytes match — a stale capture stays unresolved, never rebound.
    anchored_papers = sorted({f["source"]["paper_id"] for f in findings if f["source"]["kind"] == "anchored"})
    source_versions, unresolved, mappings = {}, [], {}
    if anchored_papers:
        from .investigation import text_hash
        papers = {str(p.id): p for p in db.query(Paper).filter(Paper.id.in_([UUID(pid) for pid in anchored_papers])).all()}
        for finding in findings:
            source = finding["source"]
            if source["kind"] != "anchored": continue
            paper = papers.get(source["paper_id"])
            key = (source["paper_id"], source["source_sha256"])
            if paper and paper.raw_content and text_hash(paper.raw_content) == source["source_sha256"]:
                if key not in source_versions:
                    lines = paper.raw_content.split("\n")
                    version = ResearchSourceVersion(id=uuid4(), project_id=project_id, paper_id=paper.id, kind="paper_text",
                                                    extractor="v1_raw_content", text_sha256=source["source_sha256"],
                                                    line_count=len(lines), byte_size=len(paper.raw_content.encode("utf-8")),
                                                    source_metadata={"title": paper.title or "", "authors": paper.authors or [],
                                                                     "publish_date": paper.publish_date, "doi": paper.doi})
                    db.add(version); db.flush()
                    source_versions[key] = str(version.id)
                mappings[finding["id"]] = {"source_version_id": source_versions[key], "unresolved": False}
            else:
                unresolved.append({"paper_id": source["paper_id"],
                                   "reason": "no_extracted_text" if paper and not paper.raw_content else "source_hash_mismatch",
                                   "expected": source["source_sha256"]})
                mappings[finding["id"]] = {"source_version_id": None, "unresolved": True}

    provenance = {"origin_label": f"v1 storage conversion ({CONVERTER_VERSION})", "reviewed": True}
    entity_ids = set()
    entity_rows, revision_rows = [], []
    for claim in claims:
        entity_ids.add(claim["id"])
        payload = _v1_claim_payload(claim)
        entity_rows.append(ResearchEntity(id=UUID(claim["id"]), project_id=project_id, type="claim", revision=1,
                                          payload=payload, archived=bool(claim.get("archived", False)), created_by=actor_id))
        revision_rows.append(ResearchEntityRevision(id=uuid4(), entity_id=UUID(claim["id"]), revision=1,
                                                    payload=payload, origin="imported",
                                                    provenance=provenance, actor_id=actor_id))
    for finding in findings:
        entity_ids.add(finding["id"])
        payload = _v1_finding_payload(finding, (mappings.get(finding["id"]) or {}).get("source_version_id"),
                                      bool((mappings.get(finding["id"]) or {}).get("unresolved")))
        entity_rows.append(ResearchEntity(id=UUID(finding["id"]), project_id=project_id, type="finding", revision=1,
                                          payload=payload, archived=bool(finding.get("archived", False)), created_by=actor_id))
        revision_rows.append(ResearchEntityRevision(id=uuid4(), entity_id=UUID(finding["id"]), revision=1, payload=payload,
                                                    origin="imported", provenance=provenance, actor_id=actor_id))
    for entity_row in entity_rows: db.add(entity_row)
    db.flush()  # entities before their revision rows regardless of mapper flush ordering
    for revision_row in revision_rows: db.add(revision_row)

    # In-transaction verification before any authority flip: text equality per record.
    claim_by_id = {c["id"]: c for c in claims}; finding_by_id = {f["id"]: f for f in findings}
    written = db.query(ResearchEntity).filter(ResearchEntity.project_id == project_id).all()
    if len(written) != len(claims) + len(findings):
        raise HTTPException(409, "Conversion count mismatch; aborted without partial state")
    for entity in written:
        original = claim_by_id.get(str(entity.id)) or finding_by_id.get(str(entity.id))
        if entity.type == "claim" and entity.payload["statement"] != original["statement"]:
            raise HTTPException(409, "Claim text changed during conversion; aborted")
        if entity.type == "finding":
            if entity.payload["label"] != original["label"]:
                raise HTTPException(409, "Finding text changed during conversion; aborted")
            anchor = entity.payload.get("anchor") or {}
            source = original["source"]
            if source["kind"] == "anchored" and not mappings[str(entity.id)]["unresolved"]:
                if anchor.get("quote") != source["quote"] or anchor.get("quote_sha256") != source["quote_sha256"]:
                    raise HTTPException(409, "Quotation snapshot changed during conversion; aborted")
    for relation in relations:
        if relation["claim_id"] not in claim_by_id or relation["finding_id"] not in finding_by_id:
            raise HTTPException(409, "Dangling v1 relation; aborted")
        db.add(ResearchRelation(id=UUID(relation["id"]), project_id=project_id, relation_type=relation["relation"],
                                source_id=UUID(relation["finding_id"]), target_id=UUID(relation["claim_id"]),
                                rationale=relation.get("rationale", "")))

    manifest = {"converter_version": CONVERTER_VERSION, "v1_revision": revision_at_read,
                "counts": {"claims": len(claims), "findings": len(findings), "relations": len(relations),
                           "sections": len(sections), "source_versions": len(source_versions)},
                "mappings": mappings, "unresolved_sources": unresolved,
                "manuscript_dependencies": [
                    {"block_id": block["id"], "kind": block["kind"], "claim_ids": block.get("claim_ids", []),
                     "finding_ids": block.get("finding_ids", []),
                     "quote_snapshot": ({"paper_id": block["quote_snapshot"]["paper_id"],
                                         "source_sha256": block["quote_snapshot"].get("source_sha256")}
                                        if block.get("quote_snapshot") and block["quote_snapshot"].get("kind") == "anchored" else None),
                     "provenance_origin": block.get("provenance", {}).get("kind", "human")}
                    for section in sections for block in section.get("blocks", [])]}
    if root is None:
        root = ResearchProject(project_id=project_id, storage_generation="v1", change_sequence=0)
        db.add(root); db.flush()
    created = len(claims) + len(findings) + len(relations) + len(source_versions)
    root.storage_generation = "v2"
    root.change_sequence = created
    root.conversion_manifest = manifest
    if row is not None and row.revision != revision_at_read:
        raise HTTPException(409, "v1 revision changed during conversion; aborted")
    db.commit()
    return manifest
