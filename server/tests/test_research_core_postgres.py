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
from app.services import metered, research_access, research_convert, research_entities, research_proposals, research_review

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
            conn.execute(cls.text("CREATE SEQUENCE IF NOT EXISTS research_event_seq"))
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
            # Mapped occurrences are accounted under retained candidates only (R26).
            non_retained_report = ReviewReport(id=uuid4(), project_id=project)
            db.add(non_retained_report); db.commit()
            non_retained_candidate = ReviewCandidate(id=uuid4(), project_id=project,
                                                     report_id=non_retained_report.id, retained=False)
            db.add(non_retained_candidate); db.commit()
            with self.assertRaises(HTTPException) as non_retained_map:
                research_review.map_occurrences(db, project, owner, non_retained_candidate.id,
                                                UUID("22000000-0000-4000-8000-000000000004"), [])
            self.assertEqual(non_retained_map.exception.status_code, 422)
            # A mapping cannot place an occurrence or candidate into an earlier snapshot
            # than the acquisition set that introduced it.
            with self.assertRaises(HTTPException) as premature:
                research_review.map_occurrences(db, project, owner, UUID("66000000-0000-4000-8000-000000000002"),
                                                later_occurrence.id, [], protocol_version=1)
            self.assertEqual(premature.exception.status_code, 422)
            # The candidate guard itself: a v1 occurrence mapped onto the v2 candidate.
            with self.assertRaises(HTTPException) as premature_candidate:
                research_review.map_occurrences(db, project, owner, later_candidate.id,
                                                UUID("22000000-0000-4000-8000-000000000004"), [],
                                                protocol_version=1)
            self.assertEqual(premature_candidate.exception.status_code, 422)
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

    async def test_cross_candidate_occurrence_remap_is_refused(self):
        # R46: one retained occurrence must not represent two active candidates. A remap that
        # claims another candidate's representative would let both candidates screen/count the
        # same occurrence (retained_occurrences < retained_candidates). map_occurrences refuses
        # it; consolidating two live candidates is an identity merge. Removing the ownership
        # guard lets the cross-candidate remap commit and breaks conservation.
        s = self.seed()
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            db.commit()
            report_a, report_b = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([report_a, report_b]); db.commit()
            candidate_a, candidate_b = uuid4(), uuid4()
            db.add_all([ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a.id),
                        ReviewCandidate(id=candidate_b, project_id=s.project, report_id=report_b.id)])
            db.commit()
            occurrence_1, occurrence_2 = uuid4(), uuid4()
            db.add_all([ReviewOccurrence(id=occurrence_1, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-1"),
                        ReviewOccurrence(id=occurrence_2, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-2")])
            db.commit()
            research_review.map_occurrences(db, s.project, s.owner, candidate_a, occurrence_1, [])
            research_review.map_occurrences(db, s.project, s.owner, candidate_b, occurrence_2, [])
            research_review.record_decision(db, s.project, s.owner, candidate_a, "title_abstract", 1, "included")
            research_review.record_decision(db, s.project, s.owner, candidate_b, "title_abstract", 1, "included")
            before = research_review.flow_counts(db, s.project, s.owner, 1)
            # Two live candidates, each with its own distinct retained representative.
            self.assertEqual((before["retained_candidates"], before["retained_occurrences"], before["screened"]), (2, 2, 2))
            # B tries to retain A's representative O1 and remove its own O2: cross-candidate claim.
            with self.assertRaises(HTTPException) as conflict:
                research_review.map_occurrences(db, s.project, s.owner, candidate_b, occurrence_1, [occurrence_2])
            self.assertEqual(conflict.exception.status_code, 409)
            # The refused remap recorded no event; counts and conservation are unchanged.
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "occurrence_map").count(), 2)
            self.assertEqual(research_review.flow_counts(db, s.project, s.owner, 1), before)
            # A within-candidate remap (B swaps its own representative for a fresh occurrence)
            # is still allowed — the guard rejects cross-candidate claims, not remapping itself.
            occurrence_3 = uuid4()
            db.add(ReviewOccurrence(id=occurrence_3, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-3"))
            db.commit()
            research_review.map_occurrences(db, s.project, s.owner, candidate_b, occurrence_3, [occurrence_2])
            remapped = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual((remapped["identified_occurrences"], remapped["duplicate_removals"], remapped["retained_occurrences"]), (3, 1, 2))
            self.assertEqual(remapped["identified_occurrences"], remapped["duplicate_removals"] + remapped["retained_occurrences"])
            # A merge folds A's occurrences into B for counting, but ownership stays with the
            # raw candidate: B cannot re-claim A's representative O1 via a remap. Allowing it
            # would let a later split restore two candidates sharing O1 (R47). Consolidation
            # is the merge itself; the refused remap records no event and conservation holds.
            research_review.merge_reports(db, s.project, s.owner, report_a.id, report_b.id, "Fixture: same report", protocol_version=1)
            with self.assertRaises(HTTPException) as post_merge:
                research_review.map_occurrences(db, s.project, s.owner, candidate_b, occurrence_1, [])
            self.assertEqual(post_merge.exception.status_code, 409)
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "occurrence_map").count(), 3)
            merged = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual(merged["identified_occurrences"], merged["duplicate_removals"] + merged["retained_occurrences"])

    async def test_backdated_mapping_cannot_bypass_later_ownership(self):
        # R47 hole 1: ownership is global across every protocol version. A→O1 recorded at v2
        # must block B→O1 backdated to v1; a per-snapshot ownership scan misses the later claim
        # and lets two screened candidates share one retained occurrence. Restoring the version
        # filter lets the backdated remap commit (the 409 assertion and the v2 counts both fail).
        s = self.seed()
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            research_review.create_protocol(db, s.project, s.owner, version=2, screening_modes={}, commit=False)
            db.commit()
            report_a, report_b = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([report_a, report_b]); db.commit()
            candidate_a, candidate_b = uuid4(), uuid4()
            db.add_all([ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a.id),
                        ReviewCandidate(id=candidate_b, project_id=s.project, report_id=report_b.id)])
            db.commit()
            occurrence_1, occurrence_2 = uuid4(), uuid4()
            db.add_all([ReviewOccurrence(id=occurrence_1, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-1"),
                        ReviewOccurrence(id=occurrence_2, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-2")])
            db.commit()
            research_review.map_occurrences(db, s.project, s.owner, candidate_a, occurrence_1, [], protocol_version=2)
            research_review.map_occurrences(db, s.project, s.owner, candidate_b, occurrence_2, [], protocol_version=1)
            research_review.record_decision(db, s.project, s.owner, candidate_a, "title_abstract", 2, "included")
            research_review.record_decision(db, s.project, s.owner, candidate_b, "title_abstract", 1, "included")
            # B backdates a claim on A's representative O1 (recorded at v2) into the v1 snapshot.
            with self.assertRaises(HTTPException) as backdated:
                research_review.map_occurrences(db, s.project, s.owner, candidate_b, occurrence_1, [occurrence_2], protocol_version=1)
            self.assertEqual(backdated.exception.status_code, 409)
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "occurrence_map").count(), 2)
            v2 = research_review.flow_counts(db, s.project, s.owner, 2)
            self.assertEqual((v2["retained_candidates"], v2["retained_occurrences"], v2["screened"]), (2, 2, 2))
            self.assertEqual(v2["identified_occurrences"], v2["duplicate_removals"] + v2["retained_occurrences"])

    async def test_split_cannot_restore_shared_occurrence_ownership(self):
        # R47 hole 2: ownership is keyed by raw candidate id, not the merge-resolved
        # representative. After A→O1, B→O2 and merge A into B, the remap B→O1 must be refused;
        # under merge-aware ownership it succeeds and a later split leaves A and B both retaining
        # O1. Restoring merge-aware identity lets the remap commit (409 assertion and counts fail).
        s = self.seed()
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            db.commit()
            report_a, report_b = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([report_a, report_b]); db.commit()
            candidate_a, candidate_b = uuid4(), uuid4()
            db.add_all([ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a.id),
                        ReviewCandidate(id=candidate_b, project_id=s.project, report_id=report_b.id)])
            db.commit()
            occurrence_1, occurrence_2 = uuid4(), uuid4()
            db.add_all([ReviewOccurrence(id=occurrence_1, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-1"),
                        ReviewOccurrence(id=occurrence_2, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-2")])
            db.commit()
            research_review.map_occurrences(db, s.project, s.owner, candidate_a, occurrence_1, [])
            research_review.map_occurrences(db, s.project, s.owner, candidate_b, occurrence_2, [])
            research_review.record_decision(db, s.project, s.owner, candidate_a, "title_abstract", 1, "included")
            research_review.record_decision(db, s.project, s.owner, candidate_b, "title_abstract", 1, "included")
            research_review.merge_reports(db, s.project, s.owner, report_a.id, report_b.id, "Fixture: same report", protocol_version=1)
            # While A is merged into B, B still cannot claim A's raw representative O1.
            with self.assertRaises(HTTPException) as post_merge:
                research_review.map_occurrences(db, s.project, s.owner, candidate_b, occurrence_1, [occurrence_2])
            self.assertEqual(post_merge.exception.status_code, 409)
            # Splitting A back out restores two independent candidates, each with its own occurrence.
            research_review.split_report(db, s.project, s.owner, report_a.id, "Fixture: identity review failed", protocol_version=1)
            counts = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual((counts["retained_candidates"], counts["retained_occurrences"], counts["screened"]), (2, 2, 2))
            self.assertEqual(counts["identified_occurrences"], counts["duplicate_removals"] + counts["retained_occurrences"])
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "occurrence_map").count(), 2)

    async def test_concurrent_occurrence_claims_single_winner(self):
        # R47 hole 3: ownership validation and insertion must serialize. The winner claims a
        # fresh occurrence and holds its transaction (and the occurrence-row lock) open; the
        # loser blocks on that lock, then re-reads the committed claim and is refused (409).
        # Removing with_for_update lets both candidates retain the occurrence (the loser returns
        # 200 and two events commit), so the outcome assertions fail.
        import time
        s = self.seed()
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            db.commit()
            report_a, report_b = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([report_a, report_b]); db.commit()
            candidate_a, candidate_b = uuid4(), uuid4()
            db.add_all([ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a.id),
                        ReviewCandidate(id=candidate_b, project_id=s.project, report_id=report_b.id)])
            db.commit()
            occurrence = uuid4()
            db.add(ReviewOccurrence(id=occurrence, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-1"))
            db.commit()
        winner = self.Session()
        try:
            research_review.map_occurrences(winner, s.project, s.owner, candidate_a, occurrence, [], commit=False)
            def loser_claim():
                with self.Session() as db:
                    try:
                        research_review.map_occurrences(db, s.project, s.owner, candidate_b, occurrence, [])
                        return 200
                    except HTTPException as error:
                        return error.status_code
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(loser_claim)
                time.sleep(0.5)
                self.assertFalse(future.done())  # blocked on the occurrence-row lock the winner holds
                winner.commit()  # release the lock with A's claim committed
                self.assertEqual(future.result(timeout=10), 409)
        finally:
            winner.close()
        with self.Session() as db:
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "occurrence_map").count(), 1)
            counts = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual(counts["retained_occurrences"], 1)
            self.assertEqual(counts["identified_occurrences"], counts["duplicate_removals"] + counts["retained_occurrences"])

    async def test_remap_must_retire_previous_representative(self):
        # R48 finding 1: a candidate retains exactly one representative. A→O1 then A→O2 with no
        # removal would leave A holding two retained representatives (retained_occurrences >
        # retained_candidates). Replacing the representative must record the previous one as
        # removed. Removing the single-representative guard lets the bare replacement commit.
        s = self.seed()
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            db.commit()
            report_a, report_b = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([report_a, report_b]); db.commit()
            candidate_a, candidate_b = uuid4(), uuid4()
            db.add_all([ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a.id),
                        ReviewCandidate(id=candidate_b, project_id=s.project, report_id=report_b.id)])
            db.commit()
            o1, o2, o3 = uuid4(), uuid4(), uuid4()
            db.add_all([ReviewOccurrence(id=o1, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-1"),
                        ReviewOccurrence(id=o2, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-2"),
                        ReviewOccurrence(id=o3, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-3")])
            db.commit()
            research_review.map_occurrences(db, s.project, s.owner, candidate_a, o1, [])
            research_review.map_occurrences(db, s.project, s.owner, candidate_b, o3, [])
            research_review.record_decision(db, s.project, s.owner, candidate_a, "title_abstract", 1, "included")
            research_review.record_decision(db, s.project, s.owner, candidate_b, "title_abstract", 1, "included")
            before = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual((before["retained_candidates"], before["retained_occurrences"], before["screened"]), (2, 2, 2))
            # A replaces its representative O1 with O2 but does not remove O1: refused.
            with self.assertRaises(HTTPException) as bare:
                research_review.map_occurrences(db, s.project, s.owner, candidate_a, o2, [])
            self.assertEqual(bare.exception.status_code, 409)
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "occurrence_map").count(), 2)
            self.assertEqual(research_review.flow_counts(db, s.project, s.owner, 1), before)
            # The replacement is allowed when it retires the previous representative O1.
            research_review.map_occurrences(db, s.project, s.owner, candidate_a, o2, [o1])
            after = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual((after["identified_occurrences"], after["duplicate_removals"], after["retained_occurrences"], after["retained_candidates"]), (3, 1, 2, 2))
            self.assertEqual(after["identified_occurrences"], after["duplicate_removals"] + after["retained_occurrences"])

    async def test_concurrent_remaps_single_winner(self):
        # R48 finding 1 (concurrent): two replacements of A's representative race. The occurrence
        # row lock serializes them; the loser re-reads A's committed representative and, still
        # removing only the original O1, would leave two representatives — refused (409). Removing
        # with_for_update lets both replacements commit (two retained representatives on A).
        import time
        s = self.seed()
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            db.commit()
            report_a = ReviewReport(id=uuid4(), project_id=s.project)
            db.add(report_a); db.commit()
            candidate_a = uuid4()
            db.add(ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a.id)); db.commit()
            o1, o2, o3 = uuid4(), uuid4(), uuid4()
            db.add_all([ReviewOccurrence(id=o1, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-1"),
                        ReviewOccurrence(id=o2, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-2"),
                        ReviewOccurrence(id=o3, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-3")])
            db.commit()
            research_review.map_occurrences(db, s.project, s.owner, candidate_a, o1, [])
        winner = self.Session()
        try:
            research_review.map_occurrences(winner, s.project, s.owner, candidate_a, o2, [o1], commit=False)
            def loser_remap():
                with self.Session() as db:
                    try:
                        research_review.map_occurrences(db, s.project, s.owner, candidate_a, o3, [o1])
                        return 200
                    except HTTPException as error:
                        return error.status_code
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(loser_remap)
                time.sleep(0.5)
                self.assertFalse(future.done())  # blocked on the O1 row lock the winner holds
                winner.commit()
                self.assertEqual(future.result(timeout=10), 409)
        finally:
            winner.close()
        with self.Session() as db:
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "occurrence_map").count(), 2)
            counts = research_review.flow_counts(db, s.project, s.owner, 1)
            # A keeps exactly one retained representative (O2); O1 is retired. The loser's O3 was
            # never mapped, so it stays an identified-but-unmapped occurrence (not a removal).
            self.assertEqual((counts["retained_candidates"], counts["retained_occurrences"], counts["duplicate_removals"]), (1, 1, 1))

    async def test_backdated_merge_cannot_discard_later_conflicts(self):
        # R48 finding 2: a merge affects every snapshot from its version onward. v2 decisions
        # include A and exclude B; merging A into B at v1 must not silently discard that later
        # conflict (requires_adjudication=False would leave v2 with zero pending). The backdated
        # merge is refused; merging at v2 records the conflict and forces adjudication. Removing
        # the later-snapshot conflict check lets the v1 merge commit and drops the v2 conflict.
        s = self.seed()
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            research_review.create_protocol(db, s.project, s.owner, version=2, screening_modes={}, commit=False)
            db.commit()
            report_a, report_b = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([report_a, report_b]); db.commit()
            candidate_a, candidate_b = uuid4(), uuid4()
            db.add_all([ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a.id),
                        ReviewCandidate(id=candidate_b, project_id=s.project, report_id=report_b.id)])
            db.commit()
            # Conflicting decisions exist only in the later (v2) snapshot.
            research_review.record_decision(db, s.project, s.owner, candidate_a, "title_abstract", 2, "included")
            research_review.record_decision(db, s.project, s.owner, candidate_b, "title_abstract", 2, "excluded")
            with self.assertRaises(HTTPException) as backdated:
                research_review.merge_reports(db, s.project, s.owner, report_a.id, report_b.id, "Fixture: backdated", protocol_version=1)
            self.assertEqual(backdated.exception.status_code, 409)
            # No merge recorded; the reports keep their independent identities.
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "report_merge").count(), 0)
            self.assertNotEqual(db.get(ReviewReport, report_a.id).identity_state, "merged")
            self.assertIsNone(db.get(ReviewReport, report_a.id).merged_into)
            # Merging at the current version records the conflict and forces adjudication.
            result = research_review.merge_reports(db, s.project, s.owner, report_a.id, report_b.id, "Fixture: current", protocol_version=2)
            self.assertTrue(result["requires_adjudication"])
            v2 = research_review.flow_counts(db, s.project, s.owner, 2)
            self.assertEqual((v2["included_reports"], v2["pending_adjudication"]), (0, 1))

    async def test_concurrent_first_mappings_single_winner(self):
        # R49 finding 1: two FIRST mappings onto one candidate lock disjoint occurrence rows, so
        # the occurrence lock alone cannot serialize them — both read an empty history and both
        # pass the single-representative guard. The candidate-row lock serializes them; the loser
        # re-reads the winner's committed representative and is refused (409). Removing the
        # candidate lock lets both first mappings commit (two retained representatives on A).
        import time
        s = self.seed()
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            db.commit()
            report_a = ReviewReport(id=uuid4(), project_id=s.project)
            db.add(report_a); db.commit()
            candidate_a = uuid4()
            db.add(ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a.id)); db.commit()
            o1, o2 = uuid4(), uuid4()
            db.add_all([ReviewOccurrence(id=o1, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-1"),
                        ReviewOccurrence(id=o2, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-2")])
            db.commit()
        winner = self.Session()
        try:
            research_review.map_occurrences(winner, s.project, s.owner, candidate_a, o1, [], commit=False)
            def loser_first_mapping():
                with self.Session() as db:
                    try:
                        research_review.map_occurrences(db, s.project, s.owner, candidate_a, o2, [])
                        return 200
                    except HTTPException as error:
                        return error.status_code
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(loser_first_mapping)
                time.sleep(0.5)
                self.assertFalse(future.done())  # blocked on the candidate-row lock the winner holds
                winner.commit()
                self.assertEqual(future.result(timeout=10), 409)
        finally:
            winner.close()
        with self.Session() as db:
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "occurrence_map").count(), 1)
            counts = research_review.flow_counts(db, s.project, s.owner, 1)
            # A keeps exactly one retained representative (O1); the loser's O2 was never mapped,
            # so it stays an identified-but-unmapped occurrence (not a removal).
            self.assertEqual((counts["retained_candidates"], counts["retained_occurrences"], counts["duplicate_removals"]), (1, 1, 0))

    async def test_backdated_remap_cannot_break_historical_snapshot(self):
        # R49 finding 2: the single-representative guard must hold at EVERY affected snapshot, not
        # just the final global replay. v1 retains O1 (removes O2,O3); v3 retains O2 (removes O1);
        # a backdated v2 retain O3 (remove O2) leaves O1 and O3 both retained at v2 — conservation
        # holds but the candidate carries two representatives. The v2 remap is refused. Removing
        # the per-snapshot validation (global-only) lets the v2 remap commit.
        s = self.seed()
        with self.Session() as db:
            for version in (1, 2, 3):
                research_review.create_protocol(db, s.project, s.owner, version=version, screening_modes={}, commit=False)
            db.commit()
            report_a = ReviewReport(id=uuid4(), project_id=s.project)
            db.add(report_a); db.commit()
            candidate_a = uuid4()
            db.add(ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a.id)); db.commit()
            o1, o2, o3 = uuid4(), uuid4(), uuid4()
            db.add_all([ReviewOccurrence(id=o1, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-1"),
                        ReviewOccurrence(id=o2, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-2"),
                        ReviewOccurrence(id=o3, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-3")])
            db.commit()
            research_review.map_occurrences(db, s.project, s.owner, candidate_a, o1, [o2, o3], protocol_version=1)
            research_review.map_occurrences(db, s.project, s.owner, candidate_a, o2, [o1], protocol_version=3)
            v2_before = research_review.flow_counts(db, s.project, s.owner, 2)
            self.assertEqual((v2_before["identified_occurrences"], v2_before["duplicate_removals"],
                              v2_before["retained_occurrences"], v2_before["retained_candidates"]), (3, 2, 1, 1))
            with self.assertRaises(HTTPException) as backdated:
                research_review.map_occurrences(db, s.project, s.owner, candidate_a, o3, [o2], protocol_version=2)
            self.assertEqual(backdated.exception.status_code, 409)
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "occurrence_map").count(), 2)
            self.assertEqual(research_review.flow_counts(db, s.project, s.owner, 2), v2_before)

    async def test_decision_on_merged_away_candidate_refused(self):
        # R49 finding 3: after an unflagged A→B merge at v1, a later v2 decision including A and
        # excluding B would silently drop A's inclusion (A left the retained set). A decision on a
        # candidate merged away at the requested snapshot is refused; the representative B decides.
        # Removing the merged-away guard lets the source decision commit and vanish from counts.
        s = self.seed()
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            research_review.create_protocol(db, s.project, s.owner, version=2, screening_modes={}, commit=False)
            db.commit()
            report_a, report_b = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([report_a, report_b]); db.commit()
            candidate_a, candidate_b = uuid4(), uuid4()
            db.add_all([ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a.id),
                        ReviewCandidate(id=candidate_b, project_id=s.project, report_id=report_b.id)])
            db.commit()
            result = research_review.merge_reports(db, s.project, s.owner, report_a.id, report_b.id, "Fixture: unflagged", protocol_version=1)
            self.assertFalse(result["requires_adjudication"])  # no decisions yet at merge time
            with self.assertRaises(HTTPException) as merged_away:
                research_review.record_decision(db, s.project, s.owner, candidate_a, "title_abstract", 2, "included")
            self.assertEqual(merged_away.exception.status_code, 409)
            self.assertEqual(db.query(ReviewDecision).filter(ReviewDecision.candidate_id == candidate_a).count(), 0)
            # The representative decides normally; counts reflect B only, with no silent omission.
            research_review.record_decision(db, s.project, s.owner, candidate_b, "title_abstract", 2, "excluded")
            v2 = research_review.flow_counts(db, s.project, s.owner, 2)
            self.assertEqual((v2["screened"], v2["title_abstract_excluded"], v2["pending_adjudication"]), (1, 1, 0))

    async def test_concurrent_decision_merge_serialization(self):
        # R49 finding 3 (concurrent): a decision on A races the A→B merge. The report-row lock
        # serializes them; the loser re-reads the committed merge and is refused (409) instead of
        # recording a decision on the just-merged-away candidate. Removing the report lock lets the
        # decision commit against the merged source.
        import time
        s = self.seed()
        report_a_id, report_b_id = uuid4(), uuid4()
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            research_review.create_protocol(db, s.project, s.owner, version=2, screening_modes={}, commit=False)
            db.commit()
            db.add_all([ReviewReport(id=report_a_id, project_id=s.project), ReviewReport(id=report_b_id, project_id=s.project)]); db.commit()
            candidate_a = uuid4()
            db.add_all([ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a_id),
                        ReviewCandidate(id=uuid4(), project_id=s.project, report_id=report_b_id)]); db.commit()
        winner = self.Session()
        try:
            research_review.merge_reports(winner, s.project, s.owner, report_a_id, report_b_id, "Fixture: racing merge", protocol_version=1, commit=False)
            def loser_decision():
                with self.Session() as db:
                    try:
                        research_review.record_decision(db, s.project, s.owner, candidate_a, "title_abstract", 2, "included")
                        return 200
                    except HTTPException as error:
                        return error.status_code
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(loser_decision)
                time.sleep(0.5)
                self.assertFalse(future.done())  # blocked on the report-row lock the merge holds
                winner.commit()
                self.assertEqual(future.result(timeout=10), 409)
        finally:
            winner.close()
        with self.Session() as db:
            self.assertEqual(db.query(ReviewDecision).filter(ReviewDecision.candidate_id == candidate_a).count(), 0)
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "report_merge").count(), 1)

    async def test_backdated_merge_cannot_create_cycle_at_later_snapshot(self):
        # R50 finding 1: cycle validation must hold at EVERY affected snapshot. A→B at v3, split A
        # at v4, then B→A backdated to v1 leaves both edges active at v3 (the split only removes
        # A→B from v4 onward), collapsing the representative set to zero. The backdated merge is
        # refused and v3 is preserved. Collapsing the cycle loop to the requested snapshot lets it commit.
        s = self.seed()
        with self.Session() as db:
            for version in (1, 3, 4):
                research_review.create_protocol(db, s.project, s.owner, version=version, screening_modes={}, commit=False)
            db.commit()
            report_a, report_b = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([report_a, report_b]); db.commit()
            candidate_a, candidate_b = uuid4(), uuid4()
            db.add_all([ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a.id),
                        ReviewCandidate(id=candidate_b, project_id=s.project, report_id=report_b.id)]); db.commit()
            o1, o2 = uuid4(), uuid4()
            db.add_all([ReviewOccurrence(id=o1, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-1"),
                        ReviewOccurrence(id=o2, project_id=s.project, provider="fixture", search_ref="s", external_hit_id="hit-2")])
            db.commit()
            research_review.map_occurrences(db, s.project, s.owner, candidate_a, o1, [], protocol_version=1)
            research_review.map_occurrences(db, s.project, s.owner, candidate_b, o2, [], protocol_version=1)
            research_review.merge_reports(db, s.project, s.owner, report_a.id, report_b.id, "Fixture: A into B", protocol_version=3)
            research_review.split_report(db, s.project, s.owner, report_a.id, "Fixture: split A", protocol_version=4)
            v3_before = research_review.flow_counts(db, s.project, s.owner, 3)
            self.assertEqual(v3_before["identified_occurrences"],
                             v3_before["duplicate_removals"] + v3_before["retained_occurrences"])
            self.assertEqual(v3_before["retained_candidates"], 1)
            with self.assertRaises(HTTPException) as cycle:
                research_review.merge_reports(db, s.project, s.owner, report_b.id, report_a.id, "Fixture: backdated B into A", protocol_version=1)
            self.assertEqual(cycle.exception.status_code, 409)
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "report_merge").count(), 1)
            self.assertEqual(research_review.flow_counts(db, s.project, s.owner, 3), v3_before)

    async def test_backdated_decision_cannot_invalidate_later_merge(self):
        # R50 finding 2: exclude B at v1, merge A→B at v2 unflagged, then include A at v1. The
        # merged-away guard covers v1 (A is not merged there), but A's backdated inclusion applies
        # at the v2 merge snapshot and silently drops from counts. The decision is refused; v2 keeps
        # B's exclusion with no pending adjudication. Removing the backdated-conflict guard lets it commit.
        s = self.seed()
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            research_review.create_protocol(db, s.project, s.owner, version=2, screening_modes={}, commit=False)
            db.commit()
            report_a, report_b = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([report_a, report_b]); db.commit()
            candidate_a, candidate_b = uuid4(), uuid4()
            db.add_all([ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a.id),
                        ReviewCandidate(id=candidate_b, project_id=s.project, report_id=report_b.id)]); db.commit()
            research_review.record_decision(db, s.project, s.owner, candidate_b, "title_abstract", 1, "excluded")
            result = research_review.merge_reports(db, s.project, s.owner, report_a.id, report_b.id, "Fixture: unflagged", protocol_version=2)
            self.assertFalse(result["requires_adjudication"])
            with self.assertRaises(HTTPException) as backdated:
                research_review.record_decision(db, s.project, s.owner, candidate_a, "title_abstract", 1, "included")
            self.assertEqual(backdated.exception.status_code, 409)
            self.assertEqual(db.query(ReviewDecision).filter(ReviewDecision.candidate_id == candidate_a).count(), 0)
            v2 = research_review.flow_counts(db, s.project, s.owner, 2)
            self.assertEqual((v2["screened"], v2["title_abstract_excluded"], v2["pending_adjudication"]), (1, 1, 0))

    async def test_merge_conflict_scan_includes_decision_versions(self):
        # R50 finding 3: with only protocol v1, opposing A/B decisions at v2 (via _protocol_for's
        # fallback) must still force adjudication. A backdated v1 merge scans later snapshots; the
        # boundary set must include decision versions, not just protocol rows, or the v2 disagreement
        # is missed and the merge succeeds unflagged. Reverting to protocol-only lets the v1 merge commit.
        s = self.seed()
        with self.Session() as db:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            db.commit()
            report_a, report_b = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([report_a, report_b]); db.commit()
            candidate_a, candidate_b = uuid4(), uuid4()
            db.add_all([ReviewCandidate(id=candidate_a, project_id=s.project, report_id=report_a.id),
                        ReviewCandidate(id=candidate_b, project_id=s.project, report_id=report_b.id)]); db.commit()
            research_review.record_decision(db, s.project, s.owner, candidate_a, "title_abstract", 2, "included")
            research_review.record_decision(db, s.project, s.owner, candidate_b, "title_abstract", 2, "excluded")
            with self.assertRaises(HTTPException) as backdated:
                research_review.merge_reports(db, s.project, s.owner, report_a.id, report_b.id, "Fixture: backdated", protocol_version=1)
            self.assertEqual(backdated.exception.status_code, 409)
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "report_merge").count(), 0)
            result = research_review.merge_reports(db, s.project, s.owner, report_a.id, report_b.id, "Fixture: at v2", protocol_version=2)
            self.assertTrue(result["requires_adjudication"])

    async def test_split_refreshes_cached_report_state(self):
        # R50 finding 4 (minor): a retained session caches A as unmerged; another session merges it.
        # Splitting through the SAME retained session must lock and refresh the committed identity
        # state rather than trust the stale cached instance. Removing db.refresh raises a spurious 409.
        s = self.seed()
        db = self.Session()
        try:
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            db.commit()
            report_a, report_b = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([report_a, report_b]); db.commit()
            db.add_all([ReviewCandidate(id=uuid4(), project_id=s.project, report_id=report_a.id),
                        ReviewCandidate(id=uuid4(), project_id=s.project, report_id=report_b.id)]); db.commit()
            cached = db.get(ReviewReport, report_a.id)  # strong reference keeps the stale instance in the identity map
            self.assertEqual(cached.identity_state, "unreviewed")
            report_a_id, report_b_id = report_a.id, report_b.id
            with self.Session() as other:
                research_review.merge_reports(other, s.project, s.owner, report_a_id, report_b_id, "Fixture: merge elsewhere", protocol_version=1)
            # db still holds the pre-merge cached instance; the split must re-read committed state.
            research_review.split_report(db, s.project, s.owner, report_a_id, "Fixture: split through retained session", protocol_version=1)
            self.assertEqual(db.get(ReviewReport, report_a_id).identity_state, "unreviewed")
            self.assertEqual(db.query(ReviewMappingEvent).filter(ReviewMappingEvent.project_id == s.project,
                                                                 ReviewMappingEvent.kind == "report_split").count(), 1)
        finally:
            db.close()

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
            counts_before = research_review.flow_counts(db, s.project, s.owner, 1)  # pre-merge snapshot
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
            # R23: a merge onto a candidate absent from the requested snapshot is rejected
            # and preserves the current snapshot exactly.
            counts_stable = research_review.flow_counts(db, s.project, s.owner, 1)
            late_report2 = ReviewReport(id=uuid4(), project_id=s.project)
            db.add(late_report2); db.commit()
            late_candidate2 = ReviewCandidate(id=uuid4(), project_id=s.project, report_id=late_report2.id,
                                              selected_version_id=None, protocol_version=2)
            db.add(late_candidate2); db.commit()
            with self.assertRaises(HTTPException) as snapshot2:
                research_review.merge_reports(db, s.project, s.owner, target.id, late_report2.id,
                                              "Fixture: onto later candidate", protocol_version=1)
            self.assertEqual(snapshot2.exception.status_code, 422)
            self.assertEqual(research_review.flow_counts(db, s.project, s.owner, 1), counts_stable)
            # R24: a non-retained merge target is refused — folding occurrences into it
            # would remove them from accounting.
            non_retained_report = ReviewReport(id=uuid4(), project_id=s.project)
            db.add(non_retained_report); db.commit()
            non_retained = ReviewCandidate(id=uuid4(), project_id=s.project, report_id=non_retained_report.id,
                                           selected_version_id=None, protocol_version=1, retained=False)
            db.add(non_retained); db.commit()
            conservation_before = research_review.flow_counts(db, s.project, s.owner, 1)
            with self.assertRaises(HTTPException) as non_retained_refused:
                research_review.merge_reports(db, s.project, s.owner, source.id, non_retained_report.id,
                                              "Fixture: onto non-retained", protocol_version=1)
            self.assertEqual(non_retained_refused.exception.status_code, 422)
            self.assertEqual(research_review.flow_counts(db, s.project, s.owner, 1), conservation_before)
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
            # A v2 decision does not exist in the v1 snapshot (historical read regression).
            research_review.amend_protocol(db, s.project, s.owner, new_version=2, commit=False)
            db.commit()
            research_review.record_decision(db, s.project, reviewer_1, candidate.id, "fulltext", 2, "included")
            historical = research_review.visible_decisions(db, s.project, reviewer_2, 1)
            self.assertEqual([d for d in historical if d.protocol_version == 2], [])
            # Adjudication evaluates the latest applicable cohort only: v1 dual excludes
            # plus a lone v2 inclusion do not combine into a fabricated disagreement.
            with self.assertRaises(HTTPException) as cohort:
                research_review.record_decision(db, s.project, s.owner, candidate.id, "fulltext", 2,
                                                "included", role="adjudication")
            self.assertEqual(cohort.exception.status_code, 409)
            # Decisions cannot predate the candidate's acquisition: a v2-introduced
            # candidate refuses a v1 decision.
            v2_report = ReviewReport(id=uuid4(), project_id=s.project)
            db.add(v2_report); db.commit()
            v2_candidate = ReviewCandidate(id=uuid4(), project_id=s.project, report_id=v2_report.id,
                                           selected_version_id=None, protocol_version=2)
            db.add(v2_candidate); db.commit()
            with self.assertRaises(HTTPException) as predate:
                research_review.record_decision(db, s.project, s.owner, v2_candidate.id, "title_abstract", 1, "included")
            self.assertEqual(predate.exception.status_code, 422)
            # The lone v2 submission is dual-hidden from the peer but visible to its author.
            self.assertEqual(len([d for d in research_review.visible_decisions(db, s.project, reviewer_2, 2)
                                  if d.protocol_version == 2]), 0)
            self.assertEqual(len([d for d in research_review.visible_decisions(db, s.project, reviewer_1, 2)
                                  if d.protocol_version == 2]), 1)
            # Disagreement exists, so the named adjudicator may now decide.
            research_review.record_decision(db, s.project, s.owner, candidate.id, "fulltext", 1, "included", role="adjudication")
            counts = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual(counts["included_reports"], 1)
            # A solo reviewer superseding their own submission does not fabricate a
            # disagreement for adjudication (effective decisions only).
            with self.Session() as db:
                report2 = ReviewReport(id=uuid4(), project_id=s.project)
                db.add(report2); db.commit()
                version2 = ReviewReportVersion(id=uuid4(), report_id=report2.id)
                db.add(version2); db.commit()
                candidate2 = ReviewCandidate(id=uuid4(), project_id=s.project, report_id=report2.id,
                                             selected_version_id=version2.id)
                db.add(candidate2); db.commit()
                # Solo stage permits repeated submissions by the same reviewer.
                research_review.record_decision(db, s.project, reviewer_1, candidate2.id, "title_abstract", 1, "excluded")
                research_review.record_decision(db, s.project, reviewer_1, candidate2.id, "title_abstract", 1, "included")
                with self.assertRaises(HTTPException) as fabricated:
                    research_review.record_decision(db, s.project, s.owner, candidate2.id, "title_abstract", 1,
                                                    "excluded", role="adjudication")
                self.assertEqual(fabricated.exception.status_code, 409)

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
            self.assertEqual((root.storage_generation, root.change_sequence), ("v2", 5))  # 4 created + the flip
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

    async def test_conversion_refreshes_cached_paper_across_replacement(self):
        # R45: conversion must refresh a cached Paper before hashing. Session A caches the
        # original bytes and stays open while session B commits a replacement; converting
        # through A must leave the original capture unresolved, never certify stale bytes.
        # Removing research_convert's Paper refresh makes A bind a version against the old
        # bytes, so the unresolved assertions below fail.
        from app.database.models import Paper
        s = self.seed()
        original = "Title\nExact fixture result.\nLimitations."
        paper = self.seed_paper(s.project, s.owner, "Fixture C", original)
        document, ids = self._v1_document(paper)  # source_sha256 binds the ORIGINAL bytes
        self._write_v1_row(s.project, document)
        db_a = self.Session()
        try:
            cached = db_a.get(Paper, paper)
            self.assertEqual(cached.raw_content, original)
            with self.engine.begin() as conn:
                conn.execute(self.text("UPDATE papers SET raw_content = :raw WHERE id = :p"),
                             {"raw": "Title\nReplacement wording.\nLimitations.", "p": paper})
            manifest = research_convert.convert_project(db_a, s.project, s.owner)
            self.assertEqual(manifest["counts"]["source_versions"], 0)
            self.assertEqual(len(manifest["unresolved_sources"]), 1)
            self.assertEqual(manifest["unresolved_sources"][0]["reason"], "source_hash_mismatch")
            self.assertEqual(db_a.query(ResearchSourceVersion).filter_by(project_id=s.project).count(), 0)
            finding = db_a.get(ResearchEntity, UUID(ids["finding_id"]))
            self.assertNotIn("source_version_id", finding.payload["anchor"])
            self.assertIn("requires review", finding.payload["anchor"]["notes"])
        finally:
            db_a.close()

    async def test_same_transaction_adjudication_and_reference_validation(self):
        # R18: an adjudication recorded in the SAME transaction as the conflicting merge
        # still resolves it (durable shared-sequence ordering), and the contract payload
        # fields validate their references.
        s = self.seed()
        other = self.seed()
        self._write_v1_row(s.project, {"format": "openpaper/investigation", "version": 1, "case": {},
                                       "claims": [], "findings": [], "relations": [],
                                       "manuscript": {"title": "", "sections": []}})
        with self.Session() as db:
            research_convert.convert_project(db, s.project, s.owner)
            research_review.create_protocol(db, s.project, s.owner, version=1, screening_modes={}, commit=False)
            db.commit()  # solo modes: single decisions are final
            source, target = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([source, target]); db.commit()
            version_x, version_y = ReviewReportVersion(id=uuid4(), report_id=source.id), ReviewReportVersion(id=uuid4(), report_id=target.id)
            db.add_all([version_x, version_y]); db.commit()
            candidate_x, candidate_y = uuid4(), uuid4()
            db.add_all([ReviewCandidate(id=candidate_x, project_id=s.project, report_id=source.id, selected_version_id=version_x.id),
                        ReviewCandidate(id=candidate_y, project_id=s.project, report_id=target.id, selected_version_id=version_y.id)])
            db.commit()
            research_review.record_decision(db, s.project, s.owner, candidate_x, "title_abstract", 1, "included", commit=False)
            research_review.record_decision(db, s.project, s.owner, candidate_y, "title_abstract", 1, "included", commit=False)
            research_review.record_decision(db, s.project, s.owner, candidate_x, "fulltext", 1, "included", commit=False)
            research_review.record_decision(db, s.project, s.owner, candidate_y, "fulltext", 1, "excluded", commit=False)
            result = research_review.merge_reports(db, s.project, s.owner, source.id, target.id, "Fixture: conflict",
                                                   protocol_version=1, commit=False)
            self.assertTrue(result["requires_adjudication"])
            # Same transaction: the resolution still postdates the merge event.
            research_review.record_decision(db, s.project, s.owner, candidate_y, "fulltext", 1, "included",
                                            role="adjudication", commit=False)
            db.commit()
            counts = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual((counts["included_reports"], counts["pending_adjudication"]), (1, 0))
            # Contract payload fields persist, read back, and validate references.
            claim = research_entities.create_entity(db, s.project, s.owner, "claim", {"statement": "Anchor claim."})
            assumption = research_entities.create_entity(db, s.project, s.owner, "assumption",
                                                         {"text": "Fixture assumption.",
                                                          "basis_entity_ids": [claim["entity_id"]]})
            self.assertEqual(assumption["revision"], 1)
            gap = research_entities.create_entity(db, s.project, s.owner, "gap",
                                                  {"description": "Fixture gap.",
                                                   "blocking_entity_ids": [claim["entity_id"]]})
            loaded = research_entities.load_entity(db, s.project, s.owner, UUID(assumption["entity_id"]))
            self.assertEqual(loaded["entity"]["payload"]["basis_entity_ids"], [claim["entity_id"]])
            with self.assertRaises(HTTPException) as dangling:
                research_entities.create_entity(db, s.project, s.owner, "gap",
                                                {"description": "Dangling dependency.",
                                                 "blocking_entity_ids": [str(uuid4())]})
            self.assertEqual(dangling.exception.status_code, 422)
            with self.assertRaises(HTTPException) as cross_user:
                research_entities.create_entity(db, s.project, s.owner, "decision",
                                                {"text": "Fixture decision.", "decided_by": str(uuid4())})
            self.assertEqual(cross_user.exception.status_code, 422)
            decision = research_entities.create_entity(db, s.project, s.owner, "decision",
                                                       {"text": "Fixture decision.", "decided_by": str(s.owner)})
            self.assertIn("change_sequence", decision)

    async def test_merge_carries_unresolved_source_disagreement(self):
        # R25: merging a half-disagreed source (no adjudication) onto a decided target
        # forces adjudication on the merged candidate instead of erasing the disagreement.
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
            source, target = ReviewReport(id=uuid4(), project_id=s.project), ReviewReport(id=uuid4(), project_id=s.project)
            db.add_all([source, target]); db.commit()
            version_s, version_t = ReviewReportVersion(id=uuid4(), report_id=source.id), ReviewReportVersion(id=uuid4(), report_id=target.id)
            db.add_all([version_s, version_t]); db.commit()
            candidate_s, candidate_t = uuid4(), uuid4()
            db.add_all([ReviewCandidate(id=candidate_s, project_id=s.project, report_id=source.id, selected_version_id=version_s.id),
                        ReviewCandidate(id=candidate_t, project_id=s.project, report_id=target.id, selected_version_id=version_t.id)])
            db.commit()
            research_review.record_decision(db, s.project, s.owner, candidate_s, "title_abstract", 1, "included")
            research_review.record_decision(db, s.project, s.owner, candidate_t, "title_abstract", 1, "included")
            # Source reviewers disagree; no adjudication has been recorded.
            research_review.record_decision(db, s.project, reviewer_1, candidate_s, "fulltext", 1, "included")
            research_review.record_decision(db, s.project, reviewer_2, candidate_s, "fulltext", 1, "excluded")
            # Target decided by two agreeing reviewers.
            research_review.record_decision(db, s.project, reviewer_1, candidate_t, "fulltext", 1, "included")
            research_review.record_decision(db, s.project, reviewer_2, candidate_t, "fulltext", 1, "included")
            result = research_review.merge_reports(db, s.project, s.owner, source.id, target.id,
                                                   "Fixture: unresolved disagreement", protocol_version=1)
            self.assertTrue(result["requires_adjudication"])
            counts = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual((counts["included_reports"], counts["pending_adjudication"]), (0, 1))
            # The named adjudicator resolves the carried disagreement.
            research_review.record_decision(db, s.project, s.owner, candidate_t, "fulltext", 1, "included", role="adjudication")
            counts = research_review.flow_counts(db, s.project, s.owner, 1)
            self.assertEqual((counts["included_reports"], counts["pending_adjudication"]), (1, 0))

    async def test_conversion_waits_for_concurrent_first_save(self):
        # R25: conversion takes the same project lock as v1 saves, so a first save that
        # commits during conversion is converted (never overwritten by empty v2 storage).
        s = self.seed()
        paper = self.seed_paper(s.project, s.owner, "Fixture F", "Title\nExact fixture result.\nLimitations.")
        document, ids = self._v1_document(paper)
        from sqlalchemy import text as raw_text
        conn1 = self.engine.connect()
        tx1 = conn1.begin()
        conn1.execute(raw_text("SELECT id FROM project WHERE id = :p FOR UPDATE"), {"p": str(s.project)})
        conn1.execute(raw_text("INSERT INTO project_investigations (project_id, schema_version, revision, document) "
                                "VALUES (:p, 1, 1, :doc)"), {"p": str(s.project), "doc": json.dumps(document)})
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: _convert_in_session(self, s.project, s.owner))
            import time
            time.sleep(0.5)
            self.assertFalse(future.done())  # blocked on the project lock: ordered after the save
            tx1.commit()
            manifest = future.result(timeout=10)
        self.assertEqual(manifest["counts"]["claims"], 1)
        conn1.close()

    async def test_anchor_verification_refreshes_cached_paper(self):
        # R44: _verify_anchor refreshes the cached Paper — a retained session cannot
        # anchor a new quotation against old bytes after a committed replacement.
        s = self.seed()
        paper = self.seed_paper(s.project, s.owner, "Fixture I", "Title\nExact fixture result.\nLimitations.")
        document, ids = self._v1_document(paper)
        self._write_v1_row(s.project, document)
        db_a = self.Session()
        try:
            research_convert.convert_project(db_a, s.project, s.owner)
            # Session A caches the paper (old bytes) and stays open.
            cached_paper = db_a.get(__import__("app.database.models", fromlist=["Paper"]).Paper, paper)
            self.assertIn("Exact fixture result.", cached_paper.raw_content)
            with self.engine.begin() as conn:
                conn.execute(self.text("UPDATE papers SET raw_content = :raw WHERE id = :p"),
                             {"raw": "Title\nReplacement wording.\nLimitations.", "p": paper})
            # Session A anchors a NEW quotation against the replacement source through
            # its cached paper: the refresh must see the new bytes and reject the old
            # quotation with 409 (not accept it against stale bytes).
            from app.services.investigation import text_hash
            with self.assertRaises(HTTPException) as stale_bytes:
                research_entities.create_entity(db_a, s.project, s.owner, "finding",
                                                {"label": "Anchored after replacement",
                                                 "anchor": {"source_version_id": db_a.query(
                                                     __import__("app.database.models", fromlist=["ResearchSourceVersion"]).ResearchSourceVersion).filter_by(
                                                     project_id=s.project).first().id,
                                                     "start_line": 2, "end_line": 2,
                                                     "quote": "Exact fixture result.",
                                                     "quote_sha256": text_hash("Exact fixture result.")}})
            self.assertEqual(stale_bytes.exception.status_code, 409)
        finally:
            db_a.close()

    async def test_anchor_requires_current_project_source_access(self):
        # R45: a new or changed anchor must require the current ProjectPaper association.
        # Revoking project-source access refuses the anchor even though the global Paper
        # row and its bytes still exist. Removing _verify_anchor's association check lets
        # both writes below succeed against the still-present Paper, failing the assertions.
        from app.database.models import Paper, ResearchSourceVersion
        from app.services.investigation import text_hash
        s = self.seed()
        paper = self.seed_paper(s.project, s.owner, "Fixture R", "Title\nExact fixture result.\nLimitations.")
        document, ids = self._v1_document(paper)
        self._write_v1_row(s.project, document)
        with self.Session() as db:
            research_convert.convert_project(db, s.project, s.owner)
            version = db.query(ResearchSourceVersion).filter_by(project_id=s.project).one()
            anchor = {"source_version_id": str(version.id), "start_line": 2, "end_line": 2,
                      "quote": "Exact fixture result.", "quote_sha256": text_hash("Exact fixture result.")}
            created = research_entities.create_entity(db, s.project, s.owner, "finding",
                                                      {"label": "Before revocation", "anchor": anchor})
            self.assertEqual(created["revision"], 1)
            entity_id = created["entity_id"]
        with self.engine.begin() as conn:
            conn.execute(self.text("DELETE FROM project_paper WHERE project_id = :p AND paper_id = :paper"),
                         {"p": s.project, "paper": paper})
        with self.Session() as db:
            version = db.query(ResearchSourceVersion).filter_by(project_id=s.project).one()
            anchor = {"source_version_id": str(version.id), "start_line": 2, "end_line": 2,
                      "quote": "Exact fixture result.", "quote_sha256": text_hash("Exact fixture result.")}
            with self.assertRaises(HTTPException) as new_anchor:
                research_entities.create_entity(db, s.project, s.owner, "finding",
                                                {"label": "After revocation", "anchor": anchor})
            self.assertEqual(new_anchor.exception.status_code, 409)
            changed = {"source_version_id": str(version.id), "start_line": 1, "end_line": 1,
                       "quote": "Title", "quote_sha256": text_hash("Title")}
            with self.assertRaises(HTTPException) as changed_anchor:
                research_entities.revise_entity(db, s.project, s.owner, UUID(entity_id), 1,
                                                {"label": "Changed after revocation", "anchor": changed})
            self.assertEqual(changed_anchor.exception.status_code, 409)
            self.assertIsNotNone(db.get(Paper, paper))  # only the association is gone, not the Paper

    async def test_metered_rejects_malformed_quantities(self):
        s = self.seed()
        with self.Session() as db:
            # Price tables are global; this suite registers its own version so the test is
            # independent of the admission test's registrations.
            metered.register_price_table(db, {"synthesis_task": {"unit_prices": {"input_tokens": 0.00001, "output_tokens": 0.00003},
                                                                 "max_cost": 0.5}}, version=3)
            limits = {"max_inflight": 2}
            # Negative quantities cannot offset the cost cap (R25).
            with self.assertRaises(HTTPException) as negative:
                metered.reserve(db, s.project, s.owner, "synthesis_task",
                                {"units": {"input_tokens": 1000000, "output_tokens": -1000000}},
                                {}, idempotency_key="negative", limits=limits)
            self.assertEqual(negative.exception.status_code, 422)
            with self.assertRaises(HTTPException) as not_finite:
                metered.reserve(db, s.project, s.owner, "synthesis_task",
                                {"units": {"input_tokens": float("nan")}}, {}, idempotency_key="nan", limits=limits)
            self.assertEqual(not_finite.exception.status_code, 422)
            estimate = {"units": {"input_tokens": 10000, "output_tokens": 2000}}
            operation, _ = metered.reserve(db, s.project, s.owner, "synthesis_task", estimate,
                                           {"question": "fixture"}, idempotency_key="q-1", limits=limits)
            metered.admit(db, s.project, s.owner, operation.id)
            metered.start(db, s.project, s.owner, operation.id)
            with self.assertRaises(HTTPException) as negative_usage:
                metered.settle(db, s.project, s.owner, operation.id, {"units": {"input_tokens": -5}})
            self.assertEqual(negative_usage.exception.status_code, 422)
            metered.settle(db, s.project, s.owner, operation.id, {"units": {"input_tokens": 10432, "output_tokens": 1717}})
            self.assertEqual(operation.state, "completed")

    async def test_load_entity_redacts_with_cached_paper(self):
        # R42: the redaction check refreshes the cached Paper — a session retaining the
        # paper across a text-clearing commit still redacts (quotation never leaves the
        # server through current payload or history).
        s = self.seed()
        paper = self.seed_paper(s.project, s.owner, "Fixture H", "Title\nExact fixture result.\nLimitations.")
        document, ids = self._v1_document(paper)
        self._write_v1_row(s.project, document)
        with self.Session() as db:
            research_convert.convert_project(db, s.project, s.owner)
        db_a = self.Session()
        try:
            cached_paper = db_a.get(__import__("app.database.models", fromlist=["Paper"]).Paper, paper)
            self.assertIsNotNone(cached_paper)  # session A caches the paper and stays open
            with self.Session() as db:
                loaded = research_entities.load_entity(db, s.project, s.owner, UUID(ids["finding_id"]))
                self.assertIn("quote", loaded["entity"]["payload"]["anchor"])
            with self.engine.begin() as conn:
                conn.execute(self.text("UPDATE papers SET raw_content = NULL WHERE id = :p"), {"p": paper})
            # Session A redacts through its cached paper.
            loaded = research_entities.load_entity(db_a, s.project, s.owner, UUID(ids["finding_id"]))
            self.assertNotIn("quote", loaded["entity"]["payload"]["anchor"])
            self.assertNotIn("Exact fixture result.", json.dumps(loaded))
        finally:
            db_a.close()

    async def test_load_entity_refreshes_cached_head(self):
        # R46: load_entity must refresh a cached entity head. Session A retains a strong
        # reference to the revision-1 head (the identity map is weak, so without a retained
        # reference the row would be re-fetched) while another session commits revision 2;
        # reading through A must return the committed head consistent with history [1, 2],
        # not a stale revision-1 head alongside newer history. Removing the head refresh
        # returns revision 1 with history [1, 2].
        s = self.seed()
        document, ids = self._v1_document(uuid4())
        self._write_v1_row(s.project, document)
        claim_id = UUID(ids["claim_id"])
        with self.Session() as db:
            research_convert.convert_project(db, s.project, s.owner)
        db_a = self.Session()
        try:
            cached_head = db_a.get(ResearchEntity, claim_id)  # strong reference keeps revision 1 cached
            self.assertEqual(cached_head.revision, 1)
            with self.Session() as db:
                research_entities.revise_entity(db, s.project, s.owner, claim_id, 1,
                                                {"statement": "Edited in another session."})
            self.assertEqual(cached_head.revision, 1)  # still the stale cached head in session A
            loaded = research_entities.load_entity(db_a, s.project, s.owner, claim_id)
            self.assertEqual(loaded["entity"]["revision"], 2)
            self.assertEqual(loaded["entity"]["payload"]["statement"], "Edited in another session.")
            self.assertEqual([h["revision"] for h in loaded["history"]], [1, 2])
        finally:
            db_a.close()

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
            history = db.query(ResearchEntityRevision).filter(ResearchEntityRevision.entity_id == UUID(ids["claim_id"])).order_by(ResearchEntityRevision.revision).all()
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

    async def test_stale_cached_entity_raises_412_not_integrity_error(self):
        # R36/R37: the locking read must observe the committed row even when the session
        # holds a cached instance. The caching session stays OPEN across the intervening
        # commit, and the stale write goes through the SAME cached session — without the
        # refresh this raises IntegrityError instead of 412.
        from unittest.mock import patch
        from fastapi import HTTPException
        s = self.seed()
        document, ids = self._v1_document(uuid4())
        self._write_v1_row(s.project, document)
        db_a = self.Session()
        try:
            research_convert.convert_project(db_a, s.project, s.owner)
            claim_id = UUID(ids["claim_id"])
            # Session A caches the entity at revision 1 and stays open.
            cached = db_a.get(ResearchEntity, claim_id)
            self.assertEqual(cached.revision, 1)
            # Session B commits revision 2 while A holds its cached instance.
            with self.Session() as db_b:
                research_entities.revise_entity(db_b, s.project, s.owner, claim_id, 1,
                                                {"statement": "Intervening edit."})
            # Session A revises with an expected revision of 1: the guard must observe
            # the committed revision 2 and raise 412 (never an IntegrityError).
            with patch.object(db_a, "commit", side_effect=RuntimeError("Rollback after 412")):
                with self.assertRaises(HTTPException) as stale:
                    research_entities.revise_entity(db_a, s.project, s.owner, claim_id, 1,
                                                    {"statement": "Stale-guard edit."})
            self.assertEqual(stale.exception.status_code, 412)
            db_a.rollback()  # discard the failed transaction from session A
            entity = db_a.get(ResearchEntity, claim_id)
            self.assertEqual((entity.revision, entity.payload["statement"]), (2, "Intervening edit."))
        finally:
            db_a.close()

    async def test_cached_role_demotion_and_cached_investigation_across_save(self):
        # R38: cached authorization and generation state must not bypass demotion or
        # cutover — both regressions retain cached rows across intervening commits.
        from unittest.mock import patch
        from fastapi import HTTPException
        s = self.seed()
        editor = uuid4()
        with self.engine.begin() as conn:
            conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"), {"u": editor, "e": str(editor) + "@test.invalid"})
            conn.execute(self.text("INSERT INTO project_role (id,project_id,user_id,role) VALUES (:id,:p,:u,'editor')"), {"id": uuid4(), "p": s.project, "u": editor})
        db_a = self.Session()
        try:
            # Session A caches the editor role.
            research_access.authorize(db_a, s.project, editor, write=True)
            # Session B demotes the editor to viewer.
            with self.engine.begin() as conn:
                conn.execute(self.text("UPDATE project_role SET role = 'viewer' WHERE project_id = :p AND user_id = :u"),
                             {"p": s.project, "u": editor})
            # Session A: the demotion is observed (403), never bypassed.
            with self.assertRaises(HTTPException) as demoted:
                research_access.authorize(db_a, s.project, editor, write=True)
            self.assertEqual(demoted.exception.status_code, 403)
        finally:
            db_a.close()
        # Cached investigation across an intervening save: conversion must convert the
        # SAVED document, not a stale cached one.
        paper = self.seed_paper(s.project, s.owner, "Fixture G", "Title\nOriginal wording.\nLimitations.")
        document_a, ids = self._v1_document(paper, quote="Original wording.")
        db_b = self.Session()
        try:
            db_b.add(ProjectInvestigation(project_id=s.project, schema_version=1, revision=1,
                                          document=document_a))
            db_b.commit()  # first save: revision 1 — session B caches it
            row_b = db_b.query(ProjectInvestigation).filter(ProjectInvestigation.project_id == s.project).first()
            self.assertEqual(row_b.revision, 1)
            # Session C (a third session) saves revision 2 while B retains its cache.
            document_c, _ = self._v1_document(paper, quote="Revised wording.")
            document_c["claims"] = [{"id": str(uuid4()), "statement": "Revised claim.", "reasoning": "", "caveats": ""}]
            document_c["findings"] = []
            document_c["relations"] = []
            with self.engine.begin() as conn:
                conn.execute(self.text("UPDATE project_investigations SET revision = 2, document = :doc WHERE project_id = :p"),
                             {"doc": json.dumps(document_c), "p": s.project})
            # Session B converts with its cached row: the refresh must observe revision 2
            # (without it, the stale revision-1 document would be converted).
            manifest = research_convert.convert_project(db_b, s.project, s.owner)
            self.assertEqual(manifest["v1_revision"], 2)
            self.assertEqual(manifest["counts"]["claims"], 1)
            entity = db_b.get(ResearchEntity, UUID(document_c["claims"][0]["id"]))
            self.assertEqual(entity.payload["statement"], "Revised claim.")
        finally:
            db_b.close()

    async def test_cached_state_cannot_bypass_guards(self):
        # R39: cached reports cannot bypass merge guards; cached roles cannot bypass
        # demotion; cached v1 roots cannot bypass cutover.
        from fastapi import HTTPException
        from app.database.models import ProjectRole, ResearchProject
        s = self.seed()
        editor = uuid4()
        with self.engine.begin() as conn:
            conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"), {"u": editor, "e": str(editor) + "@test.invalid"})
            conn.execute(self.text("INSERT INTO project_role (id,project_id,user_id,role) VALUES (:id,:p,:u,'editor')"), {"id": uuid4(), "p": s.project, "u": editor})
        # R40: three cached-state regressions, each sensitive to its refresh.
        from app.database.models import ProjectRole, ResearchProject
        from app.schemas.investigation import SaveInvestigation, InvestigationDocument
        # (1) Cached report across an intervening merge: session A caches X, session B
        # merges X into Y, session A merges X into Z through its cached row.
        report_x_id, report_y_id, report_z_id = uuid4(), uuid4(), uuid4()
        with self.Session() as db:
            db.add(ReviewProtocol(id=uuid4(), project_id=s.project, version=1, screening_modes={}))
            db.add_all([ReviewReport(id=report_x_id, project_id=s.project),
                        ReviewReport(id=report_y_id, project_id=s.project),
                        ReviewReport(id=report_z_id, project_id=s.project)])
            db.commit()  # parents before children: UOW has no relationship() ordering
            db.add_all([ReviewCandidate(id=uuid4(), project_id=s.project, report_id=report_x_id, protocol_version=1),
                        ReviewCandidate(id=uuid4(), project_id=s.project, report_id=report_y_id, protocol_version=1),
                        ReviewCandidate(id=uuid4(), project_id=s.project, report_id=report_z_id, protocol_version=1)])
            db.commit()
        db_a = self.Session()
        try:
            cached_x = db_a.get(ReviewReport, report_x_id)  # session A caches X
            self.assertIsNotNone(cached_x)
            with self.Session() as db_b:
                research_review.merge_reports(db_b, s.project, s.owner, report_x_id, report_y_id,
                                              "Fixture: X into Y", protocol_version=1)
            # Session A merges X into Z through its cached row: X is already merged — 409.
            with self.assertRaises(HTTPException) as stale_merge:
                research_review.merge_reports(db_a, s.project, s.owner, report_x_id, report_z_id,
                                              "Fixture: X into Z from cache", protocol_version=1)
            self.assertEqual(stale_merge.exception.status_code, 409)
        finally:
            db_a.close()
        with self.Session() as db:
            self.assertEqual(db.query(ReviewReport).filter(ReviewReport.merged_into == report_z_id).count(), 0)
        # (2) Cached editor role across a demotion: session A caches the role row,
        # session B demotes, session A's authorize observes 403.
        editor = uuid4()
        with self.engine.begin() as conn:
            conn.execute(self.text("INSERT INTO users (id,email,auth_provider,provider_user_id,is_active,is_blocked,is_email_verified) VALUES (:u,:e,'google',:e,true,false,true)"), {"u": editor, "e": str(editor) + "@test.invalid"})
            conn.execute(self.text("INSERT INTO project_role (id,project_id,user_id,role) VALUES (:id,:p,:u,'editor')"), {"id": uuid4(), "p": s.project, "u": editor})
        db_a = self.Session()
        try:
            role_a = db_a.query(ProjectRole).filter(ProjectRole.project_id == s.project,
                                                    ProjectRole.user_id == editor).first()
            self.assertEqual(role_a.role, "editor")  # strong reference retained
            with self.engine.begin() as conn:
                conn.execute(self.text("UPDATE project_role SET role = 'viewer' WHERE project_id = :p AND user_id = :u"),
                             {"p": s.project, "u": editor})
            with self.assertRaises(HTTPException) as demoted:
                research_access.authorize(db_a, s.project, editor, write=True)
            self.assertEqual(demoted.exception.status_code, 403)
        finally:
            db_a.close()
        # (3) Cached v1 root across a conversion (R43): TWO sessions each draw the v1
        # root and retain it across the flip; the legacy-save rejection and the
        # repeat-conversion rejection are exercised through separate cached sessions, so
        # neither refresh borrows freshness from the other.
        self._write_v1_row(s.project, {"format": "openpaper/investigation", "version": 1, "case": {},
                                       "claims": [], "findings": [], "relations": [],
                                       "manuscript": {"title": "", "sections": []}})
        db_save, db_convert = self.Session(), self.Session()
        try:
            research_access.advance_change_sequence(db_save, s.project)
            db_save.commit()
            research_access.advance_change_sequence(db_convert, s.project)
            db_convert.commit()
            # Strong references retained across the flip: both sessions hold the cached
            # v1 view while session db converts (R44).
            root_save = db_save.get(ResearchProject, s.project)
            root_convert = db_convert.get(ResearchProject, s.project)
            self.assertEqual((root_save.storage_generation, root_convert.storage_generation), ("v1", "v1"))
            with self.Session() as db_b:
                research_convert.convert_project(db_b, s.project, s.owner)
            # The cached views still show v1 (stale), while a fresh read shows v2.
            self.assertEqual((root_save.storage_generation, root_convert.storage_generation), ("v1", "v1"))
            with self.Session() as db:
                self.assertEqual(db.get(ResearchProject, s.project).storage_generation, "v2")
            with self.assertRaises(HTTPException) as cutover:
                __import__("app.services.investigation", fromlist=["save"]).save(
                    db_save, s.project, s.owner, SaveInvestigation(document=InvestigationDocument()),
                    f'"investigation:{s.project}:1"')
            self.assertEqual(cutover.exception.status_code, 409)
            with self.assertRaises(HTTPException) as repeat:
                research_convert.convert_project(db_convert, s.project, s.owner)
            self.assertEqual(repeat.exception.status_code, 409)
        finally:
            db_save.close(); db_convert.close()
        with self.Session() as db:
            root = db.get(ResearchProject, s.project)
            self.assertEqual(root.storage_generation, "v2")
            self.assertEqual(root.conversion_manifest["counts"]["claims"], 0)

    # ---------- C26/C27: proposals ----------    # ---------- C26/C27: proposals ----------    # ---------- C26/C27: proposals ----------

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
            # Both racers need v1 candidates: the membership guard requires them.
            db.add_all([ReviewCandidate(id=uuid4(), project_id=merge_project, report_id=report_a, protocol_version=1),
                        ReviewCandidate(id=uuid4(), project_id=merge_project, report_id=report_b, protocol_version=1)])
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

    async def test_conversion_fresh_root_persists_manifest(self):
        # R31: converting a project with NO research root takes the INSERT branch; the
        # durable manifest must be readable from a fresh session afterwards.
        s = self.seed()
        with self.Session() as db:
            self.assertIsNone(db.get(ResearchProject, s.project))
            self._write_v1_row(s.project, {"format": "openpaper/investigation", "version": 1, "case": {},
                                           "claims": [], "findings": [], "relations": [],
                                           "manuscript": {"title": "", "sections": []}})
        with self.Session() as db:
            manifest = research_convert.convert_project(db, s.project, s.owner)
        with self.Session() as db:  # fresh session: readback of persisted durability
            root = db.get(ResearchProject, s.project)
            self.assertIsNotNone(root.conversion_manifest)
            self.assertEqual(root.conversion_manifest["converter_version"], manifest["converter_version"])
            self.assertEqual(root.conversion_manifest["counts"]["claims"], 0)
            self.assertEqual(root.storage_generation, "v2")

    async def test_review_mutations_advance_change_sequence(self):
        # R27/R28: every committed review mutation advances the project change sequence
        # atomically (UPDATE ... RETURNING); failures roll the sequence back with the
        # transaction; cached sessions and concurrent initializations cannot lose draws.
        from app.database.models import ResearchProject
        from unittest.mock import patch
        s = self.seed()
        with self.Session() as db:
            sequence_at_start = db.get(ResearchProject, s.project)
            self.assertIsNone(sequence_at_start)  # root created by the first research mutation
            research_review.create_protocol(db, s.project, s.owner, version=1, commit=False)
            db.commit()
            report = ReviewReport(id=uuid4(), project_id=s.project)
            db.add(report); db.commit()  # parent before child
            candidate = ReviewCandidate(id=uuid4(), project_id=s.project, report_id=report.id)
            db.add(candidate); db.commit()
            occurrence = ReviewOccurrence(id=uuid4(), project_id=s.project, provider="fixture",
                                          search_ref="fixture-search", external_hit_id="hit-1")
            db.add(occurrence); db.commit()
            receipt = research_review.map_occurrences(db, s.project, s.owner, candidate.id, occurrence.id, [])
            self.assertEqual(receipt["change_sequence"], 2)
            research_review.record_decision(db, s.project, s.owner, candidate.id, "title_abstract", 1, "included")
            with self.Session() as db:
                root = db.get(ResearchProject, s.project)
                self.assertEqual(root.change_sequence, 3)  # mapping + decision each advanced it
            # A failure AFTER sequence advancement rolls the sequence back with the
            # transaction: no decision row, no sequence change.
            with self.Session() as db, patch.object(db, "commit", side_effect=RuntimeError("Synthetic failure")):
                with self.assertRaises(RuntimeError):
                    research_review.record_decision(db, s.project, s.owner, candidate.id, "title_abstract", 1, "included")
            with self.Session() as db:
                root = db.get(ResearchProject, s.project)
                self.assertEqual(root.change_sequence, 3)
                # Exactly the pre-existing decision: the failed write left no row.
                self.assertEqual(db.query(ReviewDecision).filter(ReviewDecision.candidate_id == candidate.id).count(), 1)
            # A cached ORM root cannot lose increments: this session read the root above.
            drawn = research_access.advance_change_sequence(db, s.project)
            self.assertEqual(drawn, 4)
            db.commit()
            # Conversion extends the sequence monotonically (4 + flip = 5) and enables
            # typed writes for the proposal section below.
            self._write_v1_row(s.project, {"format": "openpaper/investigation", "version": 1, "case": {},
                                           "claims": [], "findings": [], "relations": [],
                                           "manuscript": {"title": "", "sections": []}})
            with self.Session() as db:
                s_manifest = research_convert.convert_project(db, s.project, s.owner)
                self.assertEqual(s_manifest["change_sequence"], 5)
            # Concurrent mutations serialize without lost updates, including concurrent
            # initialization on a fresh project.
            from concurrent.futures import ThreadPoolExecutor
            fresh_project = uuid4()
            with self.engine.begin() as conn:
                conn.execute(self.text("INSERT INTO project (id, admin_id, title) VALUES (:p, :u, 'Seq race')"),
                             {"p": str(fresh_project), "u": str(s.owner)})
            def bump(_):
                with self.Session() as db:
                    sequence = research_access.advance_change_sequence(db, fresh_project)
                    db.commit()
                    return sequence
            with ThreadPoolExecutor(max_workers=3) as pool:
                sequences = sorted(pool.map(bump, range(3)))
            self.assertEqual(sequences, [1, 2, 3])  # concurrent initialization, no lost draws
            with self.Session() as db:
                self.assertEqual(db.get(ResearchProject, fresh_project).change_sequence, 3)
            # Conversion extends the sequence monotonically, even for empty storage.
            self._write_v1_row(fresh_project, {"format": "openpaper/investigation", "version": 1, "case": {},
                                               "claims": [], "findings": [], "relations": [],
                                               "manuscript": {"title": "", "sections": []}})
            with self.Session() as db:
                # The same session previously read the root: its cached ORM value must not
                # compute the increment (R29).
                cached = db.get(ResearchProject, fresh_project)
                self.assertEqual(cached.change_sequence, 3)
                # R35: the commit-to-return window is exercised — an intervening writer
                # draws immediately after the conversion's internal commit, before
                # convert_project returns. The RETURNING capture must keep the
                # conversion-time sequence (a post-commit read would report the newer one).
                real_commit = db.commit
                def commit_then_intervene():
                    real_commit()
                    with self.Session() as other:
                        research_access.advance_change_sequence(other, fresh_project)
                        other.commit()
                from unittest.mock import patch
                with patch.object(db, "commit", side_effect=commit_then_intervene):
                    manifest = research_convert.convert_project(db, fresh_project, s.owner)
                self.assertEqual(manifest["counts"]["claims"], 0)
                # The generation flip is itself a mutation: an empty conversion still
                # advances the sequence (R32): 3 prior advances + the flip = 4.
                self.assertEqual(manifest["change_sequence"], 4)
                # The intervening writer drew 5 during the commit-to-return window: the
                # root moved, but the manifest keeps the conversion-time value (R35).
                db.expire_all()
                root = db.get(ResearchProject, fresh_project)
                self.assertEqual((root.storage_generation, root.change_sequence), ("v2", 5))
                # The durable manifest is persisted on the fresh-root path and readable
                # from a fresh session (R30); its sequence is the in-transaction capture.
                self.assertEqual(root.conversion_manifest["converter_version"], manifest["converter_version"])
                self.assertEqual(root.conversion_manifest["counts"], manifest["counts"])
                self.assertEqual(root.conversion_manifest["change_sequence"], manifest["change_sequence"])
                self.assertEqual(root.conversion_manifest["change_sequence"], 4)
            with self.Session() as db:
                root = db.get(ResearchProject, fresh_project)
                self.assertGreater(root.change_sequence, manifest["change_sequence"])
                self.assertEqual(root.conversion_manifest["change_sequence"], manifest["change_sequence"])
            # Link receipts carry the committed sequence.
            with self.Session() as db:
                link_report = ReviewReport(id=uuid4(), project_id=fresh_project)
                link_study_row = ReviewStudy(id=uuid4(), project_id=fresh_project, description="Fixture study")
                db.add_all([link_report, link_study_row]); db.commit()
                receipt = research_review.link_study(db, fresh_project, s.owner, link_report.id,
                                                     link_study_row.id, "Fixture linkage")
            with self.Session() as db:
                self.assertEqual(receipt["change_sequence"], 6)  # conversion flip + intervening advance
                root = db.get(ResearchProject, fresh_project)
                self.assertEqual(root.change_sequence, 6)
            # Proposal and metered mutations advance the sequence and persist receipts
            # (R31/R32): creation, approval, replay recovery, and rollback. Root reads use
            # raw SQL: the identity map caches stale values after raw-SQL advances.
            from unittest.mock import patch
            from sqlalchemy import text as raw_text
            with self.Session() as db:
                claim_id = uuid4()
                db.add(ResearchEntity(id=claim_id, project_id=s.project, type="claim", revision=1,
                                      payload={"statement": "Sequence claim."}, created_by=s.owner))
                db.add(ResearchEntityRevision(id=uuid4(), entity_id=claim_id, revision=1,
                                              payload={"statement": "Sequence claim."}, origin="human",
                                              provenance={}, actor_id=s.owner))
                db.commit()
            def root_sequence():
                with self.Session() as db:
                    return db.execute(raw_text("SELECT change_sequence FROM research_projects WHERE project_id = :p"),
                                      {"p": str(s.project)}).scalar_one()
            before = root_sequence()
            print("DEBUG before:", before)
            with self.Session() as db:
                proposal_payload = {"edits": [{"entity_id": str(claim_id), "payload": {"statement": "Seq proposal."}}]}
                proposal, receipt = research_proposals.create_proposal(db, s.project, s.owner, "human",
                                                                       proposal_payload, {str(claim_id): 1},
                                                                       idempotency_key="seq-1")
                self.assertEqual(receipt["change_sequence"], before + 1)
                research_proposals.approve_proposal(db, s.project, s.owner, proposal.id)
                self.assertEqual(root_sequence(), before + 2)
                self.assertEqual(db.get(ResearchProposal, proposal.id).change_sequence, before + 2)
                # Replay recovers the persisted original receipt without a new mutation.
                replay, replay_receipt = research_proposals.create_proposal(db, s.project, s.owner, "human",
                                                                            proposal_payload, {str(claim_id): 1},
                                                                            idempotency_key="seq-1")
                self.assertTrue(replay_receipt["replayed"])
                self.assertEqual(replay_receipt["change_sequence"], before + 1)
                self.assertEqual(root_sequence(), before + 2)
                # Rollback after advancement: the proposal row and its sequence draw are
                # discarded together — nothing persists, nothing advances.
                research_proposals.create_proposal(db, s.project, s.owner, "human", proposal_payload,
                                                   {str(claim_id): 2}, idempotency_key="seq-rollback",
                                                   commit=False)
                db.rollback()
                self.assertEqual(root_sequence(), before + 2)
                self.assertEqual(db.query(ResearchProposal).filter(
                    ResearchProposal.idempotency_key == "seq-rollback").count(), 0)
                # Fresh-session create→approve→apply→creation-replay (R33): the creation
                # receipt survives application and replays with its original value.
                creation_sequence = before + 3  # seq-1 create (+1) and approve (+1) preceded this
                proposal2, receipt2 = research_proposals.create_proposal(db, s.project, s.owner, "human",
                                                                         proposal_payload, {str(claim_id): 1},
                                                                         idempotency_key="seq-2")
                self.assertEqual(receipt2["change_sequence"], creation_sequence)
                research_proposals.approve_proposal(db, s.project, s.owner, proposal2.id)
                proposal2_id = str(proposal2.id)  # capture inside the owning session
                research_proposals.apply_proposal(db, s.project, s.owner, proposal2.id)
            with self.Session() as db:
                row = db.get(ResearchProposal, UUID(proposal2_id))
                self.assertEqual(row.state, "applied")
                self.assertIsNotNone(row.applied_receipt)
                self.assertEqual(row.receipt["change_sequence"], creation_sequence)  # creation receipt preserved
                self.assertEqual(row.applied_receipt["applied"][str(claim_id)]["revision"], 2)
                replay2, replay2_receipt = research_proposals.create_proposal(db, s.project, s.owner, "human",
                                                                              proposal_payload, {str(claim_id): 1},
                                                                              idempotency_key="seq-2")
                self.assertTrue(replay2_receipt["replayed"])
                self.assertEqual(replay2_receipt["change_sequence"], creation_sequence)  # original value
            with self.Session() as db:
                root_sequence_check = db.execute(raw_text(
                    "SELECT change_sequence FROM research_projects WHERE project_id = :p"),
                    {"p": str(s.project)}).scalar_one()
                self.assertEqual(root_sequence_check, creation_sequence + 2)  # approve (+1) and apply edits (+1)
                # Metered reservations carry the sequence in their receipt.
                metered.register_price_table(db, {"bounded_task": {"unit_prices": {"calls": 1.0}, "max_cost": 10.0}},
                                             version=900)
                metered_operation, metered_receipt = metered.reserve(db, s.project, s.owner, "bounded_task",
                                                                     {"units": {"calls": 1}}, {}, idempotency_key="seq-1",
                                                                     limits={"max_inflight": 5})
                self.assertIn("change_sequence", metered_receipt)
                self.assertGreater(metered_receipt["change_sequence"], before + 2)
                # Metered replay recovers the persisted receipt; refusal rolls back.
                metered_replay, metered_replay_receipt = metered.reserve(db, s.project, s.owner, "bounded_task",
                                                                         {"units": {"calls": 1}}, {},
                                                                         idempotency_key="seq-1",
                                                                         limits={"max_inflight": 5})
                self.assertTrue(metered_replay_receipt["replayed"])
                self.assertEqual(metered_replay_receipt["change_sequence"],
                                 metered_receipt["change_sequence"])
                metered.reserve(db, s.project, s.owner, "bounded_task", {"units": {"calls": 1}},
                                {"n": "rollback"}, idempotency_key="metered-rollback",
                                limits={"max_inflight": 5}, commit=False)
                db.rollback()
            # Draws after the before-read: seq-1 create+approve, proposal2 create+approve,
            # the apply edit, and the metered reservation (+6); the two rollbacks discarded
            # their draws. Also duplicate migration-discipline headers removed below.
            self.assertEqual(root_sequence(), before + 6)

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


def _convert_in_session(test, project, owner):
    from app.services import research_convert
    with test.Session() as db:
        return research_convert.convert_project(db, project, owner)
