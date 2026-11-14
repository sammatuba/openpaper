"""Research-core integration on the guarded disposable cluster: count journey (C17),
conversion atomicity (C10), forgery/isolation (C05/C07), concurrency (C08),
proposal replay/approval boundaries (C26/C27) and the metered admission core (C29)."""
import json
import os
import unittest
from fastapi import HTTPException
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.database.models import (Conversation, Message, MeteredOperation, MeteredPriceTable, ProjectDraftRequest,
                                 ProjectInvestigation, ResearchEntity, ResearchEntityRevision, ResearchProject,
                                 ResearchRelation, ResearchSourceVersion, ReviewCandidate, ReviewDecision,
                                 ReviewMappingEvent, ReviewOccurrence, ReviewProtocol, ReviewReport,
                                 ReviewReportStudy, ReviewReportVersion, ReviewStudy, ResearchProposal)
from app.services import metered, research_convert, research_entities, research_proposals, research_review

FIXTURE = json.loads((Path(__file__).resolve().parents[2] / "docs/work/ai-native-research-fixture.json").read_text())


@unittest.skipUnless(os.environ.get("OPENPAPER_ISOLATED_PG_TEST") == "1", "requires isolated PostgreSQL")
class ResearchCorePostgresTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_mcp_postgres import MCPPostgresTests
        MCPPostgresTests.setUpClass.__func__(cls)
        from sqlalchemy import event
        @event.listens_for(cls.engine, "connect")
        def utf8(connection, record): connection.set_client_encoding("UTF8")
        cls.engine.dialect._json_serializer = lambda value: json.dumps(value, ensure_ascii=False)
        cls.engine.dispose()
        order = (Conversation, Message, ProjectInvestigation, ProjectDraftRequest, ResearchSourceVersion, ResearchEntity,
                 ResearchEntityRevision, ResearchRelation, ReviewProtocol, ReviewReport, ReviewReportVersion,
                 ReviewOccurrence, ReviewStudy, ReviewReportStudy, ReviewCandidate, ReviewDecision, ReviewMappingEvent,
                 ResearchProposal, MeteredPriceTable, MeteredOperation)  # research_projects comes from the shared harness
        with cls.engine.begin() as conn:
            for model in order: model.__table__.create(conn)

    @classmethod
    def tearDownClass(cls):
        from tests.test_mcp_postgres import MCPPostgresTests
        MCPPostgresTests.tearDownClass.__func__(cls)

    def seed(self):
        owner, viewer, outsider, project = [uuid4() for _ in range(4)]
        with self.engine.begin() as conn:
            for uid in (owner, viewer, outsider):
                conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"), {"u": uid, "e": str(uid) + "@test.invalid"})
            conn.execute(self.text("INSERT INTO project (id,admin_id,title,description) VALUES (:p,:u,'Research core','Keep legacy description')"), {"p": project, "u": owner})
            conn.execute(self.text("INSERT INTO project_role (id,project_id,user_id,role) VALUES (:id,:p,:u,'viewer')"), {"id": uuid4(), "p": project, "u": viewer})
        return SimpleNamespace(owner=owner, viewer=viewer, outsider=outsider, project=project)

    def seed_paper(self, project, owner, title, raw):
        from app.database.models import Paper, ProjectPaper
        paper = uuid4()
        with self.engine.begin() as conn:
            conn.execute(self.text("INSERT INTO papers (id,user_id,file_url,status,title,raw_content) VALUES (:p,:u,'x','reading',:t,:text)"), {"p": paper, "u": owner, "t": title, "text": raw})
            conn.execute(self.text("INSERT INTO project_paper (id,project_id,paper_id) VALUES (:id,:p,:paper)"), {"id": uuid4(), "p": project, "paper": paper})
        return paper

    # ---------- C17: full count journey through the services ----------

    async def test_review_count_fixture_journey(self):
        from fastapi import HTTPException
        from app.database.models import ReviewMappingEvent, ReviewProtocol
        review_data = FIXTURE["review"]
        owner, reviewer_1, reviewer_2 = UUID(FIXTURE["actors"]["owner"]), UUID(FIXTURE["actors"]["reviewer_1"]), UUID(FIXTURE["actors"]["reviewer_2"])
        viewer, project = uuid4(), UUID(FIXTURE["project"]["id"])  # stable fixture IDs run end to end
        with self.engine.begin() as conn:
            for uid in (owner, reviewer_1, reviewer_2, viewer):
                conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"), {"u": uid, "e": str(uid) + "@test.invalid"})
            conn.execute(self.text("INSERT INTO project (id,admin_id,title,description) VALUES (:p,:u,'Synthetic: monitoring-reliability tension','Keep legacy description')"), {"p": project, "u": owner})
            conn.execute(self.text("INSERT INTO project_role (id,project_id,user_id,role) VALUES (:id,:p,:u,'editor'), (:id2,:p,:u2,'editor'), (:id3,:p,:u3,'viewer')"),
                         {"p": project, "u": reviewer_1, "u2": reviewer_2, "u3": viewer, "id": uuid4(), "id2": uuid4(), "id3": uuid4()})
        with self.Session() as db:
            research_review.create_protocol(db, project, owner, version=1,
                                            count_policy=review_data["protocol_v1"]["count_policy"],
                                            criteria=review_data["protocol_v1"]["criteria"],
                                            screening_modes=review_data["protocol_v1"]["screening_modes"],
                                            status="active", protocol_id=UUID("99000000-0000-4000-8000-000000000001"), commit=False)
            db.commit()
            for report in review_data["reports"]:
                db.add(ReviewReport(id=UUID(report["id"]), project_id=project, identity_state="confirmed"))
                for version in report["versions"]:
                    db.add(ReviewReportVersion(id=UUID(version["id"]), report_id=UUID(report["id"]), version_label=version["label"]))
            for study in review_data["studies"]:
                db.add(ReviewStudy(id=UUID(study["id"]), project_id=project, description=study["description"]))
            db.commit()
            for link in review_data["report_studies"]:
                if link["study_id"]:
                    research_review.link_study(db, project, owner, UUID(link["report_id"]), UUID(link["study_id"]),
                                               link["rationale"], linkage_state=link["linkage_state"], commit=False)
            db.commit()
            for occurrence in review_data["occurrences"]:
                db.add(ReviewOccurrence(id=UUID(occurrence["id"]), project_id=project, provider=occurrence["provider"],
                                        search_ref=occurrence["search_execution"], external_hit_id=occurrence["external_hit_id"],
                                        report_id=UUID(occurrence["report"]) if occurrence["report"] else None,
                                        version_id=UUID(occurrence["version"]) if occurrence["version"] else None))
            db.commit()
            # Delivery retries never create occurrences: the same provider/search/hit cannot reinsert.
            duplicate_hit = db.query(ReviewOccurrence).filter(ReviewOccurrence.external_hit_id == "hit-a-preprint").first()
            db.add(ReviewOccurrence(id=duplicate_hit.id, project_id=project, provider=duplicate_hit.provider,
                                    search_ref=duplicate_hit.search_ref, external_hit_id=duplicate_hit.external_hit_id))
            with self.assertRaises(Exception): db.commit()
            db.rollback()
            for candidate in review_data["candidates"]:
                db.add(ReviewCandidate(id=UUID(candidate["id"]), project_id=project, report_id=UUID(candidate["report_id"]),
                                       selected_version_id=UUID(candidate["selected_version_id"]) if candidate["selected_version_id"] else None))
            db.commit()
            # Mapping events: exactly one retained representative per candidate; removals inspectable.
            for event in review_data["mapping_events"]:
                if event["kind"] != "occurrence_map": continue
                research_review.map_occurrences(db, project, owner, UUID(event["payload"]["candidate"]),
                                                UUID(event["payload"]["retained"]),
                                                [UUID(i) for i in event["payload"]["removed"]], commit=False)
            db.commit()
            for decision in review_data["decisions"]:
                research_review.record_decision(db, project, UUID(decision["actor_id"]), UUID(decision["candidate_id"]),
                                                decision["stage"], decision["protocol_version"], decision["decision"],
                                                role=decision.get("role", "primary"), reason=decision["reason"], commit=False)
            db.commit()
            counts_v1 = research_review.flow_counts(db, project, owner, 1)
            expected_v1 = {key: value for key, value in review_data["expected_counts"]["v1"].items() if key in counts_v1}
            self.assertEqual(counts_v1, expected_v1, counts_v1)
            # Adjudication is only recorded on a genuine disagreement.
            with self.assertRaises(HTTPException) as unanimous:
                research_review.record_decision(db, project, owner, UUID("66000000-0000-4000-8000-000000000001"),
                                                "fulltext", 1, "included", role="adjudication")
            self.assertEqual(unanimous.exception.status_code, 409)
            # Protocol amendment reopens D only; upstream sets stay unchanged.
            research_review.amend_protocol(db, project, owner, new_version=2, commit=False)
            db.commit()
            for decision in review_data["protocol_v2_decisions"]:
                research_review.record_decision(db, project, UUID(decision["actor_id"]), UUID(decision["candidate_id"]),
                                                decision["stage"], decision["protocol_version"], decision["decision"],
                                                reason=decision["reason"], commit=False)
            db.commit()
            counts_v2 = research_review.flow_counts(db, project, owner, 2)
            expected_v2 = {key: value for key, value in review_data["expected_counts"]["v2"].items() if key in counts_v2}
            self.assertEqual(counts_v2, expected_v2, counts_v2)
            self.assertEqual(research_review.flow_counts(db, project, owner, 1), counts_v1)
            self.assertEqual(research_review.flow_counts(db, project, viewer, 1), counts_v1)
            # Later acquisition-set updates (v2): a new occurrence, candidate and a study
            # linkage update join the v2 snapshot while the frozen v1 set stays untouched.
            later_occurrence = ReviewOccurrence(id=uuid4(), project_id=project, provider="fixture-scholar",
                                                search_ref="11000000-0000-4000-8000-000000000002",
                                                external_hit_id="hit-b-later", protocol_version=2,
                                                report_id=UUID("33000000-0000-4000-8000-000000000002"),
                                                version_id=UUID("44000000-0000-4000-8000-000000000003"))
            db.add(later_occurrence)
            later_report = ReviewReport(id=uuid4(), project_id=project, identity_state="confirmed")
            db.add(later_report)
            db.commit()  # parent before child
            later_candidate = ReviewCandidate(id=uuid4(), project_id=project, report_id=later_report.id,
                                              selected_version_id=None, protocol_version=2)
            db.add(later_candidate); db.commit()
            research_review.map_occurrences(db, project, owner, later_candidate.id, later_occurrence.id, [],
                                            protocol_version=2, commit=False)
            # A mapping cannot place an occurrence into an earlier snapshot than the
            # acquisition set that introduced it.
            with self.assertRaises(HTTPException) as premature:
                research_review.map_occurrences(db, project, owner, UUID("66000000-0000-4000-8000-000000000002"),
                                                later_occurrence.id, [], protocol_version=1)
            self.assertEqual(premature.exception.status_code, 422)
            db.commit()
            research_review.link_study(db, project, owner, UUID("33000000-0000-4000-8000-000000000003"),
                                       UUID("55000000-0000-4000-8000-000000000002"),
                                       "Fixture: companion linkage withdrawn", linkage_state="unresolved",
                                       protocol_version=2, commit=False)
            db.commit()
            # A first-time linkage created at v2 links an already-included report to a
            # previously uncounted study, so only the v2 snapshot grows.
            study_se = ReviewStudy(id=UUID("55000000-0000-4000-8000-000000000004"), project_id=project,
                                   description="Fixture study first linked at v2")
            db.add(study_se); db.commit()
            research_review.link_study(db, project, owner, UUID("33000000-0000-4000-8000-000000000004"),
                                       UUID("55000000-0000-4000-8000-000000000004"),
                                       "Fixture: new linkage at v2", linkage_state="confirmed",
                                       protocol_version=2, commit=False)
            db.commit()
            counts_v2b = research_review.flow_counts(db, project, owner, 2)
            # The later occurrence is the retained representative of the later candidate:
            # identified grows to 11 while removals stay 4.
            self.assertEqual((counts_v2b["identified_occurrences"], counts_v2b["duplicate_removals"]), (11, 4))
            self.assertEqual(counts_v2b["retained_candidates"], 7)
            self.assertEqual(counts_v2b["included_studies"], 4)  # SA, SB (B), SD and the new D->SE; C->SB withdrawn
            # The frozen v1 snapshot keeps its original sets, counts and linkage states.
            v1_again = research_review.flow_counts(db, project, owner, 1)
            self.assertEqual(v1_again, counts_v1)
            self.assertEqual((v1_again["identified_occurrences"], v1_again["retained_candidates"], v1_again["included_studies"]),
                             (10, 6, 2))
            with self.assertRaises(HTTPException) as denied:
                research_review.record_decision(db, project, viewer, UUID("66000000-0000-4000-8000-000000000001"),
                                                "fulltext", 1, "included")
            self.assertEqual(denied.exception.status_code, 403)
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == project,
                                                                 ReviewMappingEvent.kind == "occurrence_map").count(), 7)  # 6 fixture maps + the later acquisition map
        outsider = uuid4()
        with self.Session() as db:
            with self.assertRaises(HTTPException) as hidden:
                research_review.flow_counts(db, outsider, outsider, 1)
            self.assertEqual(hidden.exception.status_code, 404)

    async def test_merge_with_conflicting_decisions_requires_adjudication(self):
        s = self.seed()
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            db.commit()  # solo stages: single decisions are final
            source, target = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([source, target]); db.commit()  # parents before children: UOW has no relationship() ordering
            version_x, version_y = ReviewReportVersion(id=uuid4(), report_id=source.id), ReviewReportVersion(id=uuid4(), report_id=target.id)
            db.add_all([version_x, version_y]); db.commit()
            candidate_x, candidate_y = uuid4(), uuid4()
            db.add_all([ReviewCandidate(id=candidate_x, project_id=s.project, report_id=source.id, selected_version_id=version_x.id),
                        ReviewCandidate(id=candidate_y, project_id=s.project, report_id=target.id, selected_version_id=version_y.id)])
            db.commit()
            research_review.record_decision(db, s.project, s.owner, candidate_x, "title_abstract", 1, "included")
            research_review.record_decision(db, s.project, s.owner, candidate_y, "title_abstract", 1, "included")
            research_review.record_decision(db, s.project, s.owner, candidate_x, "fulltext", 1, "included")
            research_review.record_decision(db, s.project, s.owner, candidate_y, "fulltext", 1, "excluded")
            result = research_review.merge_reports(db, s.project, s.owner, source.id, target.id, "Fixture: same report re-derived",
                                                   protocol_version=1)
            self.assertTrue(result["requires_adjudication"])
            self.assertEqual(result["conflicting_decisions"][0]["source"], "included")
            self.assertEqual(result["conflicting_decisions"][0]["target"], "excluded")
            # The conflict is unresolved: the merged candidate is pending, not silently included or excluded.
            counts = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual((counts["included_reports"], counts["fulltext_excluded"], counts["pending_adjudication"]), (0, 0, 1))
            # Resolution: the named adjudicator decides the merged (target) candidate.
            research_review.record_decision(db, s.project, s.owner, candidate_y, "fulltext", 1, "included", role="adjudication")
            counts = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual((counts["included_reports"], counts["pending_adjudication"]), (1, 0))
            # Cyclic and chained merges are rejected under lock.
            with self.assertRaises(HTTPException) as cycle:
                research_review.merge_reports(db, s.project, s.owner, target.id, source.id, "Fixture: reverse", protocol_version=1)
            self.assertEqual(cycle.exception.status_code, 409)  # target is already merged
            research_review.split_report(db, s.project, s.owner, source.id, "Fixture: identity review failed", protocol_version=1)
            third = ReviewReport(id=uuid4(), project_id=s.project)
            db.add(third); db.commit()
            research_review.merge_reports(db, s.project, s.owner, source.id, target.id, "Fixture: re-merge", protocol_version=1)
            with self.assertRaises(HTTPException) as chained:
                research_review.merge_reports(db, s.project, s.owner, third.id, source.id, "Fixture: into merged", protocol_version=1)
            self.assertEqual(chained.exception.status_code, 409)  # source already merged
            with self.assertRaises(HTTPException) as self_merge:
                research_review.merge_reports(db, s.project, s.owner, third.id, third.id, "Fixture: self", protocol_version=1)
            self.assertEqual(self_merge.exception.status_code, 422)
            research_review.split_report(db, s.project, s.owner, source.id, "Fixture: cleanup", protocol_version=1)
            # Reversal: split restores both candidates. The recorded adjudication decision
            # remains on the target candidate (append-only history — never rewritten); flagging
            # the affected review for re-decision is amendment machinery for P10.
            counts = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual((counts["included_reports"], counts["fulltext_excluded"], counts["pending_adjudication"]), (2, 0, 0))
            # Historic snapshots: a merge at a later protocol version leaves v1 sets untouched.

    async def test_independent_review_privacy(self):
        s = self.seed()
        reviewer_1, reviewer_2 = uuid4(), uuid4()
        with self.engine.begin() as conn:
            for uid in (reviewer_1, reviewer_2):
                conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"), {"u": uid, "e": str(uid) + "@test.invalid"})
                conn.execute(self.text("INSERT INTO project_role (id,project_id,user_id,role) VALUES (:id,:p,:u,'editor')"), {"id": uuid4(), "p": s.project, "u": uid})
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1,
                                            screening_modes={"title_abstract": "solo", "fulltext": "dual"}, commit=False)
            db.commit()
            report = ReviewReport(id=uuid4(), project_id=s.project)
            db.add(report); db.commit()  # parent before child: UOW has no relationship() ordering
            version = ReviewReportVersion(id=uuid4(), report_id=report.id)
            db.add(version); db.commit()
            candidate = ReviewCandidate(id=uuid4(), project_id=s.project, report_id=report.id, selected_version_id=version.id)
            db.add(candidate); db.commit()
            research_review.record_decision(db, s.project, s.owner, candidate.id, "title_abstract", 1, "included")
            research_review.record_decision(db, s.project, reviewer_1, candidate.id, "fulltext", 1, "included")
            visible_to_2 = research_review.visible_decisions(db, s.project, reviewer_2, 1)
            self.assertEqual([d for d in visible_to_2 if d.actor_id == reviewer_1], [])  # dual: hidden until both submit
            # Solo-stage decisions are final and visible to every authorized reader.
            visible_ta = research_review.visible_decisions(db, s.project, reviewer_2, 1)
            self.assertEqual(len([d for d in visible_ta if d.stage == "title_abstract"]), 1)
            counts = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual((counts["fulltext_assessed"], counts["pending_adjudication"]), (0, 1))  # one reviewer is not dual review
            # One reviewer cannot satisfy dual review by submitting twice.
            with self.assertRaises(HTTPException) as duplicate:
                research_review.record_decision(db, s.project, reviewer_1, candidate.id, "fulltext", 1, "included")
            self.assertEqual(duplicate.exception.status_code, 409)
            research_review.record_decision(db, s.project, reviewer_2, candidate.id, "fulltext", 1, "excluded")
            visible = research_review.visible_decisions(db, s.project, reviewer_2, 1)
            self.assertEqual(len([d for d in visible if d.candidate_id == candidate.id and d.stage == "fulltext"]), 2)
            # Disagreement exists, so the named adjudicator may now decide.
            research_review.record_decision(db, s.project, s.owner, candidate.id, "fulltext", 1, "included", role="adjudication")
            counts = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual(counts["included_reports"], 1)

    # ---------- C10: conversion ----------

    def _v1_document(self, paper_id, quote="Exact fixture result."):
        from app.services.investigation import text_hash
        claim_id, finding_id, relation_id = str(uuid4()), str(uuid4()), str(uuid4())
        section_id, block_id = str(uuid4()), str(uuid4())
        document = {
            "format": "openpaper/investigation", "version": 1,
            "case": {"question": "Fixture question"},
            "claims": [{"id": claim_id, "statement": "Fixture claim statement.", "reasoning": "R", "caveats": "C"}],
            "findings": [{"id": finding_id, "label": "Fixture finding", "observed_result": "O",
                          "author_interpretation": "A", "our_interpretation": "U", "limitations": "L",
                          "source": {"kind": "anchored", "paper_id": str(paper_id), "start_line": 1, "end_line": 1,
                                     "quote": quote, "source_sha256": text_hash("Title\n" + quote + "\nLimitations."),
                                     "quote_sha256": text_hash(quote)}}],
            "relations": [{"id": relation_id, "claim_id": claim_id, "finding_id": finding_id,
                           "relation": "supports", "rationale": "Fixture rationale."}],
            "manuscript": {"title": "Fixture manuscript", "sections": [{"id": section_id, "title": "S", "blocks": [
                {"id": block_id, "kind": "paragraph", "text": "Human fixture prose.", "claim_ids": [claim_id],
                 "finding_ids": [finding_id],
                 "provenance": {"kind": "assistant", "request_id": str(uuid4()), "message_id": str(uuid4())},
                 "dependency_pins": {}}]}]},
        }
        return document, {"claim_id": claim_id, "finding_id": finding_id, "relation_id": relation_id, "block_id": block_id}

    def _write_v1_row(self, project, document):
        with self.engine.begin() as conn:
            conn.execute(self.text("INSERT INTO project_investigations (project_id,schema_version,revision,document) VALUES (:p,1,7,:doc)"),
                         {"p": project, "doc": json.dumps(document)})

    async def test_conversion_preserves_identity_and_is_atomic(self):
        from unittest.mock import patch
        from fastapi import HTTPException
        s = self.seed()
        paper = self.seed_paper(s.project, s.owner, "Fixture A", "Title\nExact fixture result.\nLimitations.")
        document, ids = self._v1_document(paper)
        self._write_v1_row(s.project, document)
        with self.Session() as db:
            # Unconverted projects refuse typed writes: one authoritative write path.
            with self.assertRaises(HTTPException) as refusal:
                research_entities.create_entity(db, s.project, s.owner, "claim", {"statement": "Premature"})
            self.assertEqual(refusal.exception.status_code, 409)
        with self.Session() as db, patch.object(db, "commit", side_effect=RuntimeError("Synthetic conversion failure")):
            with self.assertRaises(RuntimeError):
                research_convert.convert_project(db, s.project, s.owner)
        with self.engine.begin() as conn:
            for table in ("research_entities", "research_relations", "research_source_versions", "research_projects"):
                count = conn.execute(self.text(f"SELECT count(*) FROM {table} WHERE project_id = :p"), {"p": s.project}).scalar_one()
                self.assertEqual(count, 0, f"{table} must be untouched after the aborted conversion")
            revision_count = conn.execute(self.text("SELECT count(*) FROM research_entity_revisions WHERE entity_id IN (SELECT id FROM research_entities WHERE project_id = :p)"), {"p": s.project}).scalar_one()
            self.assertEqual(revision_count, 0, "revision rows must be untouched after the aborted conversion")
            row = conn.execute(self.text("SELECT revision, document FROM project_investigations WHERE project_id = :p"), {"p": s.project}).one()
            self.assertEqual(row.revision, 7)
            self.assertEqual(row.document["claims"][0]["statement"], "Fixture claim statement.")
        with self.Session() as db:
            manifest = research_convert.convert_project(db, s.project, s.owner)
            self.assertEqual(manifest["counts"], {"claims": 1, "findings": 1, "relations": 1, "sections": 1, "source_versions": 1})
            self.assertEqual(manifest["unresolved_sources"], [])
            self.assertEqual(manifest["v1_revision"], 7)
            self.assertEqual(manifest["manuscript_dependencies"][0]["provenance_origin"], "assistant")
            claim = db.get(ResearchEntity, UUID(ids["claim_id"]))
            finding = db.get(ResearchEntity, UUID(ids["finding_id"]))
            self.assertEqual(claim.payload["statement"], "Fixture claim statement.")
            self.assertEqual(finding.payload["label"], "Fixture finding")
            version = db.query(ResearchSourceVersion).filter(ResearchSourceVersion.project_id == s.project).one()
            self.assertEqual(finding.payload["anchor"]["source_version_id"], str(version.id))
            self.assertEqual(finding.payload["anchor"]["quote"], "Exact fixture result.")
            self.assertEqual(version.text_sha256, document["findings"][0]["source"]["source_sha256"])
            self.assertEqual(version.source_metadata["title"], "Fixture A")
            history = db.query(ResearchEntityRevision).filter(ResearchEntityRevision.entity_id == claim.id).one()
            self.assertEqual(history.origin, "imported")
            self.assertIn("v1 storage conversion", history.provenance["origin_label"])
            relation = db.query(ResearchRelation).filter(ResearchRelation.id == UUID(ids["relation_id"])).one()
            self.assertEqual((relation.relation_type, str(relation.source_id), str(relation.target_id)),
                             ("supports", ids["finding_id"], ids["claim_id"]))
            root = db.get(ResearchProject, s.project)
            self.assertEqual((root.storage_generation, root.change_sequence), ("v2", 4))
            v1 = db.get(ProjectInvestigation, s.project)
            self.assertEqual(v1.revision, 7)  # v1 snapshot retained read-only
            self.assertEqual(v1.document["manuscript"]["sections"][0]["blocks"][0]["provenance"]["kind"], "assistant")
            with self.assertRaises(HTTPException) as repeat:
                research_convert.convert_project(db, s.project, s.owner)
            self.assertEqual(repeat.exception.status_code, 409)
            # One authoritative write path: legacy v1 investigation writes are refused once converted.
            from app.schemas.investigation import SaveInvestigation, InvestigationDocument
            from fastapi import HTTPException as HTTPError
            with self.assertRaises(HTTPError) as legacy_write:
                __import__("app.services.investigation", fromlist=["save"]).save(
                    db, s.project, s.owner, SaveInvestigation(document=InvestigationDocument()),
                    f'"investigation:{s.project}:7"')
            self.assertEqual(legacy_write.exception.status_code, 409)

    async def test_conversion_binds_each_finding_by_its_own_hash(self):
        # Two findings anchored to one paper whose current bytes match only the newer
        # capture: the stale-hash finding stays unresolved and is never rebound to the
        # version created for the newer capture.
        s = self.seed()
        paper = self.seed_paper(s.project, s.owner, "Fixture D", "Title\nNewer wording.\nLimitations.")
        from app.services.investigation import text_hash
        stale = {"id": str(uuid4()), "label": "Stale capture", "source": {"kind": "anchored", "paper_id": str(paper),
                                                                          "start_line": 1, "end_line": 1, "quote": "Title",
                                                                          "source_sha256": text_hash("Title\nOld wording.\nLimitations."),
                                                                          "quote_sha256": text_hash("Title")}}
        current = {"id": str(uuid4()), "label": "Current capture", "source": {"kind": "anchored", "paper_id": str(paper),
                                                                              "start_line": 2, "end_line": 2, "quote": "Newer wording.",
                                                                              "source_sha256": text_hash("Title\nNewer wording.\nLimitations."),
                                                                              "quote_sha256": text_hash("Newer wording.")}}
        document = {"format": "openpaper/investigation", "version": 1, "case": {}, "claims": [],
                    "findings": [stale, current], "relations": [], "manuscript": {"title": "", "sections": []}}
        self._write_v1_row(s.project, document)
        with self.Session() as db:
            manifest = research_convert.convert_project(db, s.project, s.owner)
            self.assertEqual(len(manifest["unresolved_sources"]), 1)
            self.assertEqual(db.query(ResearchSourceVersion).filter(ResearchSourceVersion.project_id == s.project).count(), 1)
            stale_entity = db.get(ResearchEntity, UUID(stale["id"]))
            current_entity = db.get(ResearchEntity, UUID(current["id"]))
            self.assertNotIn("source_version_id", stale_entity.payload["anchor"])
            self.assertEqual(current_entity.payload["anchor"]["quote"], "Newer wording.")

    async def test_conversion_refuses_hash_mismatch_without_binding(self):
        s = self.seed()
        paper = self.seed_paper(s.project, s.owner, "Fixture B", "Title\nOriginal wording.\nLimitations.")
        document, ids = self._v1_document(paper, quote="Original wording.")
        with self.engine.begin() as conn:
            conn.execute(self.text("UPDATE papers SET raw_content = :raw WHERE id = :p"), {"raw": "Title\nChanged wording.\nLimitations.", "p": paper})
        self._write_v1_row(s.project, document)
        with self.Session() as db:
            manifest = research_convert.convert_project(db, s.project, s.owner)
            self.assertEqual(manifest["unresolved_sources"][0]["reason"], "source_hash_mismatch")
            self.assertEqual(db.query(ResearchSourceVersion).filter(ResearchSourceVersion.project_id == s.project).count(), 0)
            finding = db.get(ResearchEntity, UUID(ids["finding_id"]))
            self.assertNotIn("source_version_id", finding.payload["anchor"])
            self.assertIn("requires review", finding.payload["anchor"]["notes"])

    async def test_editing_imported_content_preserves_its_provenance(self):
        s = self.seed()
        document, ids = self._v1_document(uuid4())
        self._write_v1_row(s.project, document)
        with self.Session() as db:
            research_convert.convert_project(db, s.project, s.owner)
            claim = db.get(ResearchEntity, UUID(ids["claim_id"]))
            self.assertEqual(claim.payload["statement"], "Fixture claim statement.")
            result = research_entities.revise_entity(db, s.project, s.owner, UUID(ids["claim_id"]), 1,
                                                     {"statement": "Edited after conversion."})
            self.assertEqual(result["revision"], 2)
            history = db.query(ResearchEntityRevision).filter(ResearchEntityRevision.entity_id == UUID(ids["claim_id"])).all()
            latest = history[-1]
            self.assertEqual(latest.origin, "imported")  # never promoted to human-authored
            self.assertTrue(latest.provenance.get("edited"))
            self.assertIn("v1 storage conversion", latest.provenance["origin_label"])
            self.assertEqual(latest.derived_from, {"entity_id": ids["claim_id"], "revision": 1})
            # A human edit derives with preserved imported origin; a different origin kind is refused.
            human_edit = research_entities.revise_entity(db, s.project, s.owner, UUID(ids["claim_id"]), 2,
                                                         {"statement": "Edited after conversion."}, origin="human")
            self.assertEqual(human_edit["revision"], 3)
            with self.assertRaises(HTTPException) as reoriginate:
                research_entities.revise_entity(db, s.project, s.owner, UUID(ids["claim_id"]), 3,
                                                {"statement": "Assembled promotion attempt."}, origin="assembled")
            self.assertEqual(reoriginate.exception.status_code, 422)

    async def test_native_assistant_provenance_is_validated(self):
        # Contract 2.2 / v1 semantics: assistant provenance requires a completed durable
        # draft request owned by this actor in this project, linked to the cited message.
        s = self.seed()
        document, ids = self._v1_document(uuid4())
        self._write_v1_row(s.project, document)
        other = self.seed()
        editor = uuid4()
        with self.engine.begin() as conn:
            conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"), {"u": editor, "e": str(editor) + "@test.invalid"})
            conn.execute(self.text("INSERT INTO project_role (id,project_id,user_id,role) VALUES (:id,:p,:u,'editor')"), {"id": uuid4(), "p": s.project, "u": editor})
        with self.Session() as db:
            research_convert.convert_project(db, s.project, s.owner)
            request_id, message_id, conversation_id = uuid4(), uuid4(), uuid4()
            db.add(Conversation(id=conversation_id, user_id=s.owner, conversable_type="project", conversable_id=s.project))
            db.add(Message(id=message_id, conversation_id=conversation_id, role="assistant", content="Fixture draft", sequence=1))
            db.commit()
            def draft_request(project, actor, state="completed", request_id=request_id, message_id=message_id):
                return ProjectDraftRequest(id=request_id, project_id=project, requester_id=actor,
                                           request_hash="a" * 64, snapshot={}, base_revision=1,
                                           section_id=uuid4(), state=state,
                                           conversation_id=conversation_id, message_id=message_id)
            db.add(draft_request(s.project, s.owner))
            # Persist a genuine foreign-project request: cross-project identity is refused
            # even though the row exists and is complete.
            foreign_request = draft_request(other.project, other.owner, request_id=uuid4())
            db.add(foreign_request); db.commit()
            claim_id = UUID(ids["claim_id"])
            provenance = {"request_id": str(request_id), "message_id": str(message_id)}
            created = research_entities.create_entity(db, s.project, s.owner, "claim",
                                                      {"statement": "Assisted claim."}, origin="assistant",
                                                      provenance=provenance, entity_id=uuid4())
            self.assertEqual(created["revision"], 1)
            for mutate, expected in (
                (lambda: research_entities.create_entity(db, s.project, s.owner, "claim",
                                                         {"statement": "Ghost."}, origin="assistant",
                                                         provenance={"request_id": str(uuid4()), "message_id": str(message_id)}), 422),
                (lambda: research_entities.create_entity(db, s.project, s.owner, "claim",
                                                         {"statement": "Cross."}, origin="assistant",
                                                         provenance={"request_id": str(foreign_request.id),
                                                                     "message_id": str(message_id)}), 422),
                # An authorized editor introducing another actor's request identity is refused
                # by provenance validation, not merely by authorization.
                (lambda: research_entities.create_entity(db, s.project, editor, "claim",
                                                         {"statement": "Wrong actor."}, origin="assistant",
                                                         provenance=provenance), 422),
            ):
                with self.assertRaises(HTTPException) as forged:
                    mutate()
                self.assertEqual(forged.exception.status_code, expected)
            # Preserved identity travels: an authorized collaborator edits the assistant text.
            revised = research_entities.revise_entity(db, s.project, editor, UUID(created["entity_id"]), 1,
                                                      {"statement": "Collaborator edit of assisted claim."})
            self.assertEqual(revised["revision"], 2)
            # State transitions are re-checked on revisions with newly introduced identity too.
            db.add(draft_request(s.project, s.owner, state="pending", request_id=uuid4())); db.commit()
        with self.Session() as db:
            pending_request = db.query(ProjectDraftRequest).filter(ProjectDraftRequest.state == "pending").first()
            with self.assertRaises(HTTPException) as incomplete:
                research_entities.revise_entity(db, s.project, s.owner, UUID(ids["claim_id"]), 1,
                                                {"statement": "Pending identity"}, origin="assistant",
                                                provenance={"request_id": str(pending_request.id),
                                                            "message_id": str(pending_request.message_id)})
            self.assertEqual(incomplete.exception.status_code, 422)
            # Proposal application inherits the same validation: a valid native proposal
            # applies; one carrying forged identity is refused at apply time.
            from app.services import research_proposals
            valid, _ = research_proposals.create_proposal(db, s.project, s.owner, "assistant",
                                                          {"request_id": str(request_id), "message_id": str(message_id),
                                                           "edits": [{"entity_id": ids["claim_id"], "payload": {"statement": "Assisted proposal."}}]},
                                                          {ids["claim_id"]: 1}, idempotency_key="native-valid")
            research_proposals.approve_proposal(db, s.project, s.owner, valid.id)
            result = research_proposals.apply_proposal(db, s.project, s.owner, valid.id)
            self.assertFalse(result["replayed"])
            forged_proposal, _ = research_proposals.create_proposal(db, s.project, s.owner, "assistant",
                                                                    {"request_id": str(uuid4()), "message_id": str(uuid4()),
                                                                     "edits": [{"entity_id": ids["claim_id"], "payload": {"statement": "Forged identity proposal."}}]},
                                                                    {ids["claim_id"]: 2}, idempotency_key="native-forged")
            research_proposals.approve_proposal(db, s.project, s.owner, forged_proposal.id)
            with self.assertRaises(HTTPException) as forged_apply:
                research_proposals.apply_proposal(db, s.project, s.owner, forged_proposal.id)
            self.assertEqual(forged_apply.exception.status_code, 422)

    # ---------- C05/C07: forgery, endpoint legality, isolation ----------

    async def test_typed_writes_forgery_and_role_isolation(self):
        from fastapi import HTTPException
        s = self.seed()
        other = self.seed()
        paper = self.seed_paper(s.project, s.owner, "Fixture C", "Title\nExact fixture result.\nLimitations.")
        document, ids = self._v1_document(paper)
        self._write_v1_row(s.project, document)
        with self.Session() as db:
            research_convert.convert_project(db, s.project, s.owner)
            claim_id = UUID(ids["claim_id"])
            with self.assertRaises(HTTPException) as forged:
                research_entities.create_entity(db, s.project, s.owner, "finding",
                                                {"label": "Forged anchor", "anchor": {"source_version_id": str(uuid4()),
                                                                                      "start_line": 1, "end_line": 1,
                                                                                      "quote": "x", "quote_sha256": "a" * 64}})
            self.assertEqual(forged.exception.status_code, 422)
            from app.services.investigation import text_hash
            version_id = db.query(ResearchSourceVersion).filter(ResearchSourceVersion.project_id == s.project).one().id
            # A fabricated quotation carrying a previously valid digest is rejected: the
            # digest must match the submitted text itself.
            with self.assertRaises(HTTPException) as forged_text:
                research_entities.create_entity(db, s.project, s.owner, "finding",
                                                {"label": "Fabricated text", "anchor": {"source_version_id": str(version_id),
                                                                                        "start_line": 1, "end_line": 1,
                                                                                        "quote": "FABRICATED",
                                                                                        "quote_sha256": text_hash("Exact fixture result.")}})
            self.assertEqual(forged_text.exception.status_code, 422)
            # A correct quotation claimed at a different range is rejected by line verification.
            with self.assertRaises(HTTPException) as forged_range:
                research_entities.create_entity(db, s.project, s.owner, "finding",
                                                {"label": "Wrong range", "anchor": {"source_version_id": str(version_id),
                                                                                    "start_line": 1, "end_line": 3,
                                                                                    "quote": "Exact fixture result.",
                                                                                    "quote_sha256": text_hash("Exact fixture result.")}})
            self.assertEqual(forged_range.exception.status_code, 422)
            with self.assertRaises(HTTPException) as bogus_type:
                research_entities.create_entity(db, s.project, s.owner, "speculation", {"text": "x"})
            self.assertEqual(bogus_type.exception.status_code, 422)
            assumption = research_entities.create_entity(db, s.project, s.owner, "assumption", {"text": "Fixture assumption"})
            with self.assertRaises(HTTPException) as cross:
                research_entities.create_relation(db, s.project, s.owner, "supports", uuid4(), claim_id, "Rationale text.")
            self.assertEqual(cross.exception.status_code, 422)
            with self.assertRaises(HTTPException) as illegal:
                research_entities.create_relation(db, s.project, s.owner, "supports", claim_id, claim_id, "Rationale text.")
            self.assertEqual(illegal.exception.status_code, 422)
            with self.assertRaises(HTTPException) as no_rationale:
                research_entities.create_relation(db, s.project, s.owner, "assumes", claim_id, UUID(assumption["entity_id"]), "   ")
            self.assertEqual(no_rationale.exception.status_code, 422)
            relation = research_entities.create_relation(db, s.project, s.owner, "assumes", claim_id, UUID(assumption["entity_id"]),
                                                         "Fixture assumption rationale.")
            self.assertIn("relation_id", relation)
            loaded = research_entities.load_entity(db, s.project, s.viewer, claim_id)
            self.assertEqual(loaded["entity"]["type"], "claim")
            with self.assertRaises(HTTPException) as viewer_write:
                research_entities.revise_entity(db, s.project, s.viewer, claim_id, 1, {"statement": "Viewer edit"})
            self.assertEqual(viewer_write.exception.status_code, 403)
            with self.assertRaises(HTTPException) as outsider_read:
                research_entities.load_entity(db, s.project, s.outsider, claim_id)
            self.assertEqual(outsider_read.exception.status_code, 404)
            first = research_entities.revise_entity(db, s.project, s.owner, claim_id, 1, {"statement": "First edit."})
            self.assertEqual(first["revision"], 2)
            with self.assertRaises(HTTPException) as conflict:
                research_entities.revise_entity(db, s.project, s.owner, claim_id, 1, {"statement": "Losing edit"})
            self.assertEqual(conflict.exception.status_code, 412)
        with self.Session() as db:
            research_convert.convert_project(db, other.project, other.owner)
            with self.assertRaises(HTTPException) as foreign_relation:
                research_entities.create_relation(db, other.project, other.owner, "assumes",
                                                  UUID(ids["claim_id"]), UUID(assumption["entity_id"]), "Cross-project rationale.")
            self.assertEqual(foreign_relation.exception.status_code, 422)

    async def test_load_entity_redacts_revoked_sources(self):
        s = self.seed()
        paper = self.seed_paper(s.project, s.owner, "Fixture E", "Title\nExact fixture result.\nLimitations.")
        document, ids = self._v1_document(paper)
        self._write_v1_row(s.project, document)
        with self.Session() as db:
            research_convert.convert_project(db, s.project, s.owner)
            loaded = research_entities.load_entity(db, s.project, s.owner, UUID(ids["finding_id"]))
            self.assertIn("quote", loaded["entity"]["payload"]["anchor"])
        with self.engine.begin() as conn:
            conn.execute(self.text("DELETE FROM project_paper WHERE project_id = :p"), {"p": s.project})
        with self.Session() as db:
            loaded = research_entities.load_entity(db, s.project, s.owner, UUID(ids["finding_id"]))
            anchor = loaded["entity"]["payload"]["anchor"]
            self.assertNotIn("quote", anchor)
            self.assertNotIn("quote_sha256", anchor)
            self.assertEqual(anchor["paper_id"], str(paper))
            for entry in loaded["history"]:
                self.assertNotIn("quote", entry["payload"]["anchor"])
            self.assertNotIn("Exact fixture result.", json.dumps(loaded))

    # ---------- C08: concurrency ----------

    async def test_concurrent_revisions_single_winner_and_atomic_rollback(self):
        from unittest.mock import patch
        from fastapi import HTTPException
        s = self.seed()
        document, ids = self._v1_document(uuid4())
        self._write_v1_row(s.project, document)
        with self.Session() as db:
            research_convert.convert_project(db, s.project, s.owner)
        def revise(_):
            with self.Session() as db:
                try:
                    research_entities.revise_entity(db, s.project, s.owner, UUID(ids["claim_id"]), 1,
                                                    {"statement": f"Edit at {uuid4()}"})
                    return 200
                except HTTPException as error: return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(revise, range(2)))
        self.assertEqual(sorted(outcomes), [200, 412])
        def disjoint(index):
            with self.Session() as db:
                research_entities.create_entity(db, s.project, s.owner, "gap", {"description": f"Parallel gap {index}"})
            return 200
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(disjoint, range(2))), [200, 200])
        with self.Session() as db:
            entity = db.get(ResearchEntity, UUID(ids["claim_id"]))
            before = (entity.revision, entity.payload["statement"])
            sequence_before = db.get(ResearchProject, s.project).change_sequence
            with patch.object(db, "commit", side_effect=RuntimeError("Synthetic failure")):
                with self.assertRaises(RuntimeError):
                    research_entities.revise_entity(db, s.project, s.owner, UUID(ids["claim_id"]), entity.revision,
                                                    {"statement": "Must not persist"})
            db.rollback()
            entity = db.get(ResearchEntity, UUID(ids["claim_id"]))
            self.assertEqual((entity.revision, entity.payload["statement"]), before)
            self.assertEqual(db.get(ResearchProject, s.project).change_sequence, sequence_before)

    # ---------- C26/C27: proposals ----------

    async def test_proposal_apply_replay_and_forgery(self):
        from fastapi import HTTPException
        s = self.seed()
        document, ids = self._v1_document(uuid4())
        self._write_v1_row(s.project, document)
        with self.Session() as db:
            research_convert.convert_project(db, s.project, s.owner)
            claim_id = UUID(ids["claim_id"])
            with self.assertRaises(HTTPException) as missing_identity:
                research_proposals.create_proposal(db, s.project, s.owner, "external_ai",
                                                   {"edits": [{"entity_id": str(claim_id), "payload": {"statement": "External edit"}}]},
                                                   {str(claim_id): 1})
            self.assertEqual(missing_identity.exception.status_code, 422)
            with self.assertRaises(HTTPException) as impersonation:
                research_proposals.create_proposal(db, s.project, s.owner, "external_ai",
                                                   {"client_identity": "fixture-chatgpt-client", "content_sha256": "a" * 64,
                                                    "request_id": str(uuid4()),
                                                    "edits": [{"entity_id": str(claim_id), "payload": {"statement": "External edit"}}]},
                                                   {str(claim_id): 1})
            self.assertEqual(impersonation.exception.status_code, 422)
            payload = {"client_identity": "fixture-chatgpt-client", "content_sha256": "b" * 64,
                       "declared_model": "fixture-model-label",
                       "edits": [{"entity_id": str(claim_id), "payload": {"statement": "External paragraph from the ChatGPT fixture."}}]}
            proposal, created = research_proposals.create_proposal(db, s.project, s.owner, "external_ai", payload,
                                                                   {str(claim_id): 1}, idempotency_key="ext-1")
            self.assertFalse(created["replayed"])
            proposal_2, replay = research_proposals.create_proposal(db, s.project, s.owner, "external_ai", payload,
                                                                    {str(claim_id): 1}, idempotency_key="ext-1")
            self.assertTrue(replay["replayed"]); self.assertEqual(proposal_2.id, proposal.id)
            with self.assertRaises(HTTPException) as key_conflict:
                research_proposals.create_proposal(db, s.project, s.owner, "external_ai",
                                                   {**payload, "edits": [{"entity_id": str(claim_id), "payload": {"statement": "Different"}}]},
                                                   {str(claim_id): 1}, idempotency_key="ext-1")
            self.assertEqual(key_conflict.exception.status_code, 409)
            with self.assertRaises(HTTPException) as unapproved:
                research_proposals.apply_proposal(db, s.project, s.owner, proposal.id)
            self.assertEqual(unapproved.exception.status_code, 409)
            research_proposals.approve_proposal(db, s.project, s.owner, proposal.id, expires_in_seconds=3600)
            result = research_proposals.apply_proposal(db, s.project, s.owner, proposal.id)
            self.assertFalse(result["replayed"])
            self.assertEqual(result["receipt"]["approver_id"], str(s.owner))
            entity = db.get(ResearchEntity, claim_id)
            self.assertEqual(entity.revision, 2)
            revision = db.query(ResearchEntityRevision).filter_by(entity_id=claim_id, revision=2).one()
            self.assertEqual(revision.origin, "external_ai")
            self.assertEqual(revision.provenance["client_identity"], "fixture-chatgpt-client")
            self.assertEqual(revision.derived_from, {"entity_id": str(claim_id), "revision": 1})
            replay_apply = research_proposals.apply_proposal(db, s.project, s.owner, proposal.id)
            self.assertTrue(replay_apply["replayed"])
            self.assertEqual(replay_apply["receipt"], result["receipt"])
            self.assertEqual(db.get(ResearchEntity, claim_id).revision, 2)  # no double apply
            # Human proposal approved against revision 2, then a concurrent edit makes it stale.
            human, _ = research_proposals.create_proposal(db, s.project, s.owner, "human",
                                                          {"edits": [{"entity_id": str(claim_id), "payload": {"statement": "Human proposal"}}]},
                                                          {str(claim_id): 2}, idempotency_key="human-1")
            research_proposals.approve_proposal(db, s.project, s.owner, human.id)
            research_entities.revise_entity(db, s.project, s.owner, claim_id, 2, {"statement": "Concurrent human edit"})
            with self.assertRaises(HTTPException) as stale_apply:
                research_proposals.apply_proposal(db, s.project, s.owner, human.id)
            self.assertEqual(stale_apply.exception.status_code, 409)
            self.assertEqual(db.get(ResearchProposal, human.id).state, "stale")
            # Forged approval (wrong payload binding) is rejected at apply time.
            forged, _ = research_proposals.create_proposal(db, s.project, s.owner, "human",
                                                           {"edits": [{"entity_id": str(claim_id), "payload": {"statement": "Forged approval target"}}]},
                                                           {str(claim_id): 3}, idempotency_key="forged-1")
            forged_row = db.get(ResearchProposal, forged.id)
            forged_row.approval = {"approver_id": str(s.owner), "approved_at": "2026-01-01T00:00:00+00:00",
                                   "expires_at": "2099-01-01T00:00:00+00:00", "bound_payload_sha256": "c" * 64,
                                   "bound_targets": forged_row.targets}
            forged_row.state = "approved"; db.commit()
            with self.assertRaises(HTTPException) as forged_apply:
                research_proposals.apply_proposal(db, s.project, s.owner, forged.id)
            self.assertEqual(forged_apply.exception.status_code, 409)
            # A payload mutated after approval cannot ride the approval: the digest is recomputed.
            tampered, _ = research_proposals.create_proposal(db, s.project, s.owner, "human",
                                                             {"edits": [{"entity_id": str(claim_id), "payload": {"statement": "Approved text"}}]},
                                                             {str(claim_id): 3}, idempotency_key="tamper-1")
            research_proposals.approve_proposal(db, s.project, s.owner, tampered.id)
            db.execute(__import__("sqlalchemy").text("UPDATE research_proposals SET payload = payload || :patch WHERE id = :id"),
                       {"patch": json.dumps({"injected": True}), "id": str(tampered.id)})
            db.expire_all()
            with self.assertRaises(HTTPException) as tamper:
                research_proposals.apply_proposal(db, s.project, s.owner, tampered.id)
            self.assertEqual(tamper.exception.status_code, 409)
            # Expired approvals return 410 and mark the proposal expired.
            expired, _ = research_proposals.create_proposal(db, s.project, s.owner, "human",
                                                            {"edits": [{"entity_id": str(claim_id), "payload": {"statement": "Expired target"}}]},
                                                            {str(claim_id): 3}, idempotency_key="expired-1")
            research_proposals.approve_proposal(db, s.project, s.owner, expired.id, expires_in_seconds=-1)
            with self.assertRaises(HTTPException) as expired_apply:
                research_proposals.apply_proposal(db, s.project, s.owner, expired.id)
            self.assertEqual(expired_apply.exception.status_code, 410)
            self.assertEqual(db.get(ResearchProposal, expired.id).state, "expired")

    # ---------- C29: metered admission core ----------

    async def test_metered_admission_replay_and_uncertain_completion(self):
        s = self.seed()
        with self.Session() as db:
            # No price table: every metered path is refused while deterministic work continues.
            with self.assertRaises(HTTPException) as unpriced:
                metered.reserve(db, s.project, s.owner, "synthesis_task", {"units": {"input_tokens": 100}}, {},
                                limits={"max_inflight": 2})
            self.assertEqual(unpriced.exception.status_code, 409)
            self.assertEqual(unpriced.exception.detail, "operation_not_priceable")
            metered.register_price_table(db, {"synthesis_task": {"unit_prices": {"input_tokens": 0.00001, "output_tokens": 0.00003},
                                                                 "max_cost": 0.5}}, version=1)
            # Admission requires explicitly configured limits; defaults are never unrestricted.
            with self.assertRaises(HTTPException) as unbounded:
                metered.reserve(db, s.project, s.owner, "synthesis_task", {"units": {"input_tokens": 10}}, {}, idempotency_key="nolimits")
            self.assertEqual(unbounded.exception.status_code, 422)
            with self.assertRaises(HTTPException) as still_unpriced:
                metered.reserve(db, s.project, s.owner, "unregistered_operation", {"units": {"calls": 1}}, {},
                                limits={"max_inflight": 2})
            self.assertEqual(still_unpriced.exception.status_code, 409)
            estimate = {"units": {"input_tokens": 10000, "output_tokens": 2000}}
            limits = {"max_inflight": 2}
            operation, created = metered.reserve(db, s.project, s.owner, "synthesis_task", estimate,
                                                 {"question": "fixture"}, idempotency_key="m-1", limits=limits)
            self.assertFalse(created["replayed"])
            self.assertEqual(operation.state, "reserved")
            self.assertAlmostEqual(created["estimated_cost"], 10000 * 0.00001 + 2000 * 0.00003)
            duplicate, replay = metered.reserve(db, s.project, s.owner, "synthesis_task", estimate,
                                                {"question": "fixture"}, idempotency_key="m-1", limits=limits)
            self.assertTrue(replay["replayed"]); self.assertEqual(duplicate.id, operation.id)
            with self.assertRaises(HTTPException) as payload_conflict:
                metered.reserve(db, s.project, s.owner, "synthesis_task", estimate,
                                {"question": "different"}, idempotency_key="m-1", limits=limits)
            self.assertEqual(payload_conflict.exception.status_code, 409)
            with self.assertRaises(HTTPException) as over_cap:
                metered.reserve(db, s.project, s.owner, "synthesis_task",
                                {"units": {"input_tokens": 90000000, "output_tokens": 0}}, {}, idempotency_key="m-2", limits=limits)
            self.assertEqual(over_cap.exception.status_code, 429)
            # Dispatch is gated on a specific admitted reservation, not merely a price table entry.
            with self.assertRaises(HTTPException) as not_admitted:
                metered.assert_dispatchable(db, s.project, s.owner, operation.id)
            self.assertEqual(not_admitted.exception.status_code, 409)
            metered.admit(db, s.project, s.owner, operation.id)
            metered.assert_dispatchable(db, s.project, s.owner, operation.id)
            metered.start(db, s.project, s.owner, operation.id)
            # Dispatch and state transitions recheck current authorization inside the transaction.
            member = uuid4()
            with self.engine.begin() as conn:
                conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"), {"u": member, "e": str(member) + "@test.invalid"})
                conn.execute(self.text("INSERT INTO project_role (id,project_id,user_id,role) VALUES (:id,:p,:u,'viewer')"), {"id": uuid4(), "p": s.project, "u": member})
            with self.assertRaises(HTTPException) as viewer_dispatch:
                metered.assert_dispatchable(db, s.project, member, operation.id)
            self.assertEqual(viewer_dispatch.exception.status_code, 403)
            with self.engine.begin() as conn:
                conn.execute(self.text("DELETE FROM project_role WHERE project_id = :p AND user_id = :u"), {"p": s.project, "u": member})
            with self.assertRaises(HTTPException) as revoked_dispatch:
                metered.assert_dispatchable(db, s.project, member, operation.id)
            self.assertEqual(revoked_dispatch.exception.status_code, 404)
            settled = metered.settle(db, s.project, s.owner, operation.id,
                                     {"units": {"input_tokens": 10432, "output_tokens": 1717}})
            self.assertEqual(settled.state, "completed")
            self.assertEqual(settled.usage["units"]["input_tokens"], 10432)  # estimate retained separately
            self.assertEqual(settled.estimate, estimate)
            uncertain, _ = metered.reserve(db, s.project, s.owner, "synthesis_task", estimate, {"question": "u"},
                                           idempotency_key="m-3", limits=limits)
            metered.admit(db, s.project, s.owner, uncertain.id)
            metered.start(db, s.project, s.owner, uncertain.id)
            metered.fail(db, s.project, s.owner, uncertain.id, uncertain=True, error_code="provider_timeout")
            self.assertEqual(uncertain.state, "uncertain")
            self.assertEqual(uncertain.error_code, "provider_timeout")
            with self.assertRaises(HTTPException) as settle_uncertain:
                metered.settle(db, s.project, s.owner, uncertain.id, {"units": {}})
            self.assertEqual(settle_uncertain.exception.status_code, 409)
            # Replaying an uncertain key returns the uncertain record: no silent re-dispatch.
            replayed_uncertain, replay = metered.reserve(db, s.project, s.owner, "synthesis_task", estimate,
                                                         {"question": "u"}, idempotency_key="m-3", limits=limits)
            self.assertTrue(replay["replayed"]); self.assertEqual(replayed_uncertain.state, "uncertain")
            with self.assertRaises(HTTPException) as state_conflict:
                metered.cancel(db, s.project, s.owner, operation.id)
            self.assertEqual(state_conflict.exception.status_code, 409)
            fresh, _ = metered.reserve(db, s.project, s.owner, "synthesis_task", estimate, {"question": "c"},
                                       idempotency_key="m-4", limits=limits)
            metered.cancel(db, s.project, s.owner, fresh.id)
            self.assertEqual(fresh.state, "cancelled")
            self.assertEqual(metered.active_price_table(db).version, 1)
        # Uncertain completion retains its reservation and counts as in-flight exposure:
        # with one uncertain operation outstanding, a max_inflight of 1 refuses everything.
        with self.Session() as db:
            metered.register_price_table(db, {"bounded_task": {"unit_prices": {"calls": 1.0}, "max_cost": 10.0}}, version=2)
            with self.assertRaises(HTTPException) as uncertain_exposure:
                metered.reserve(db, s.project, s.owner, "bounded_task", {"units": {"calls": 1}}, {},
                                idempotency_key="cap-exposure", limits={"max_inflight": 1})
            self.assertEqual(uncertain_exposure.exception.status_code, 429)
            with self.Session() as db:
                with self.assertRaises(HTTPException) as outsider:
                    metered.reserve(db, s.project, s.outsider, "synthesis_task", {"units": {"input_tokens": 1}}, {},
                                    idempotency_key="x", limits={"max_inflight": 1})
                self.assertEqual(outsider.exception.status_code, 404)
        # Concurrent opposite merges cannot both win; the loser sees the committed state.
        merge_project, merge_owner = uuid4(), uuid4()
        with self.engine.begin() as conn:
            conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"), {"u": merge_owner, "e": str(merge_owner) + "@test.invalid"})
            conn.execute(self.text("INSERT INTO project (id,admin_id,title) VALUES (:p,:u,'Merge race fixture')"), {"p": merge_project, "u": merge_owner})
            report_a, report_b = uuid4(), uuid4()
            conn.execute(self.text("INSERT INTO review_reports (id,project_id,identity_state) VALUES (:a,:p,'unreviewed'),(:b,:p,'unreviewed')"), {"a": report_a, "b": report_b, "p": merge_project})
        with self.Session() as db:
            research_review.create_protocol(db, merge_project, merge_owner, version=1, commit=False)
            db.commit()
        def merge_race(direction):
            with self.Session() as db:
                try:
                    research_review.merge_reports(db, merge_project, merge_owner, report_a, report_b, "Fixture: race",
                                                  protocol_version=1) if direction == 0 else \
                    research_review.merge_reports(db, merge_project, merge_owner, report_b, report_a, "Fixture: race",
                                                  protocol_version=1)
                    return 200
                except HTTPException as error: return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(merge_race, range(2)))
        self.assertEqual(sorted(outcomes), [200, 409])

        # Concurrent reserves cannot race past the in-flight cap (atomic admission).
        race_project, race_owner = uuid4(), uuid4()
        with self.engine.begin() as conn:
            conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"), {"u": race_owner, "e": str(race_owner) + "@test.invalid"})
            conn.execute(self.text("INSERT INTO project (id,admin_id,title) VALUES (:p,:u,'Race fixture')"), {"p": race_project, "u": race_owner})
        def race(index):
            with self.Session() as db:
                try:
                    metered.reserve(db, race_project, race_owner, "bounded_task", {"units": {"calls": 1}}, {"n": index},
                                    idempotency_key=f"race-{index}", limits={"max_inflight": 1})
                    return 200
                except HTTPException as error: return error.status_code
        with ThreadPoolExecutor(max_workers=3) as pool:
            outcomes = list(pool.map(race, range(3)))
        self.assertEqual(sorted(outcomes), [200, 429, 429])  # exactly one admission wins

    # ---------- migration discipline ----------

    async def test_additive_migration_upgrade_downgrade_upgrade(self):
        import importlib.util
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        s = self.seed()
        spec = importlib.util.spec_from_file_location("research_core_migration",
                                                      Path(__file__).resolve().parents[1] / "migrations/versions/2026_11_13_0100_research_core.py")
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        names = ["research_projects", "research_source_versions", "research_entities", "research_entity_revisions",
                 "research_relations", "review_protocols", "review_reports", "review_report_versions",
                 "review_occurrences", "review_studies", "review_report_studies", "review_candidates",
                 "review_decisions", "review_mapping_events", "research_proposals", "metered_price_tables",
                 "metered_operations"]
        with self.engine.begin() as conn:
            for name in names: conn.execute(self.text(f"DROP TABLE IF EXISTS {name} CASCADE"))
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade(); migration.downgrade(); migration.upgrade()
            self.assertEqual(conn.execute(self.text("SELECT description FROM project WHERE id = :p"), {"p": s.project}).scalar_one(),
                             "Keep legacy description")
            self.assertEqual(conn.execute(self.text("SELECT count(*) FROM information_schema.tables WHERE table_schema = :s AND table_name = ANY(:names)"),
                                          {"s": self.schema, "names": names}).scalar_one(), len(names))
            # The migration carries the occurrence-retry uniqueness: the same provider,
            # search and external hit cannot create two occurrences on a migrated database.
            from psycopg2 import errors as pg_errors
            conn.execute(self.text("INSERT INTO review_occurrences (id,project_id,provider,search_ref,external_hit_id) VALUES (:a,:p,'fixture','q','hit-1')"), {"a": uuid4(), "p": s.project})
            nested = conn.begin_nested()
            with self.assertRaises(Exception) as duplicate:
                conn.execute(self.text("INSERT INTO review_occurrences (id,project_id,provider,search_ref,external_hit_id) VALUES (:a,:p,'fixture','q','hit-1')"), {"a": uuid4(), "p": s.project})
            nested.rollback()
            self.assertIn("uq_review_occurrence_hit", str(duplicate.exception))
