"""Research-core unit tests: strict schemas, endpoint legality, provenance boundaries and
the exact strategy-17.1 review-count arithmetic over the golden fixture (no database)."""
import json
import unittest
from pathlib import Path
from uuid import uuid4

from app.schemas.research_core import (ALLOWED_ENDPOINTS, Anchor, ClaimPayload, FindingPayload, Provenance,
                                       endpoint_allowed, validate_payload, validate_provenance)
from app.services.research_review import compute_flow_counts

FIXTURE = json.loads((Path(__file__).resolve().parents[2] / "docs/work/ai-native-research-fixture.json").read_text())


class SchemaTests(unittest.TestCase):
    def test_claim_bounds_and_forbidden_extras(self):
        with self.assertRaises(Exception): ClaimPayload(statement="x" * 2001)
        with self.assertRaises(Exception): ClaimPayload(statement="ok", unknown="field")
        self.assertEqual(ClaimPayload(statement="ok").status, "provisional")

    def test_finding_anchor_variants_and_ordering(self):
        valid = {"label": "L", "anchor": {"source_version_id": str(uuid4()), "start_line": 2, "end_line": 2,
                                          "quote": "q", "quote_sha256": "a" * 64}}
        self.assertEqual(validate_payload("finding", valid)["anchor"]["start_line"], 2)
        for mutate, key in ((lambda a: a.update(start_line=3, end_line=2), "reversed"),
                            (lambda a: a.update(quote_sha256="short"), "digest"),
                            (lambda a: a.update(quote=""), "empty quote")):
            broken = json.loads(json.dumps(valid)); mutate(broken["anchor"])
            with self.assertRaises(Exception): validate_payload("finding", broken)
        with self.assertRaises(Exception): validate_payload("finding", {"label": "L", "anchor": {"kind": "bogus"}})
        unbound = validate_payload("finding", {"label": "L", "anchor": {"origin_locator": "loc", "notes": "n"}})
        self.assertIn("origin_locator", unbound["anchor"])

    def test_payload_types_are_enforced(self):
        with self.assertRaises(Exception): validate_payload("speculation", {"text": "x"})
        with self.assertRaises(Exception): validate_payload("claim", {"statement": ""})
        self.assertEqual(validate_payload("gap", {"description": "d"})["status"], "open")
        self.assertEqual(validate_payload("question", {"text": "q"})["status"], "open")

    def test_provenance_identity_boundaries(self):
        validate_provenance("external_ai", {"client_identity": "mcp-client", "content_sha256": "a" * 64})
        with self.assertRaises(ValueError):  # external without identity
            validate_provenance("external_ai", {})
        with self.assertRaises(ValueError):  # impersonation: external client plus native request ids
            validate_provenance("external_ai", {"client_identity": "c", "content_sha256": "a" * 64,
                                                "request_id": str(uuid4()), "message_id": str(uuid4())})
        with self.assertRaises(ValueError):  # native without durable request identity
            validate_provenance("assistant", {"request_id": str(uuid4())})
        validate_provenance("assistant", {"request_id": str(uuid4()), "message_id": str(uuid4())})
        with self.assertRaises(ValueError): validate_provenance("fabricated", {})

    def test_endpoint_legality_table_is_frozen_and_enforced(self):
        self.assertTrue(endpoint_allowed("supports", "finding", "claim"))
        self.assertFalse(endpoint_allowed("supports", "claim", "finding"))
        self.assertTrue(endpoint_allowed("derived_from", "claim", "claim"))
        self.assertTrue(endpoint_allowed("derived_from", "finding", "claim"))
        self.assertFalse(endpoint_allowed("cites", "finding", "claim"))
        self.assertFalse(endpoint_allowed("assumes", "finding", "claim"))
        for relation_type, endpoints in ALLOWED_ENDPOINTS.items():
            for source_type, targets in endpoints.items():
                for target_type in targets:
                    self.assertTrue(endpoint_allowed(relation_type, source_type, target_type))


class CountArithmeticTests(unittest.TestCase):
    """C17: the frozen 17.1 fixture reproduces exact counts from records and events only."""

    @staticmethod
    def _inputs(include_v2):
        review = FIXTURE["review"]
        decisions = list(review["decisions"]) + (list(review["protocol_v2_decisions"]) if include_v2 else [])
        links = [link for link in review["report_studies"] if link["study_id"]]
        return review["occurrences"], review["mapping_events"], review["candidates"], decisions, links

    def test_v1_exact_counts(self):
        counts = compute_flow_counts(*self._inputs(include_v2=False), protocol_version=1)
        expected = FIXTURE["review"]["expected_counts"]["v1"]
        for key, value in expected.items():
            if key in counts: self.assertEqual(counts[key], value, f"{key}: {counts[key]} != {value}")
        self.assertEqual(counts["identified_occurrences"],
                         counts["duplicate_removals"] + counts["retained_candidates"])
        self.assertEqual(counts["screened"], counts["title_abstract_excluded"] + counts["reports_sought"])
        self.assertEqual(counts["reports_sought"], counts["not_retrieved"] + counts["fulltext_assessed"])
        self.assertEqual(counts["fulltext_assessed"], counts["fulltext_excluded"] + counts["included_reports"])
        self.assertEqual(counts["included_reports"], 3)
        self.assertEqual(counts["included_studies"], 2)  # C describes SB: not independent corroboration

    def test_v2_amendment_reopens_only_affected_counts(self):
        counts = compute_flow_counts(*self._inputs(include_v2=True), protocol_version=2)
        expected = FIXTURE["review"]["expected_counts"]["v2"]
        for key, value in expected.items():
            if key in counts: self.assertEqual(counts[key], value, f"{key}: {counts[key]} != {value}")
        self.assertEqual(counts["included_studies"], 3)
        self.assertEqual(counts["fulltext_excluded"], 0)

    def test_v1_snapshot_unchanged_after_amendment(self):
        before = compute_flow_counts(*self._inputs(include_v2=False), protocol_version=1)
        after = compute_flow_counts(*self._inputs(include_v2=True), protocol_version=1)
        self.assertEqual(before, after)

    def test_disagreement_without_adjudication_is_pending_not_counted(self):
        review = FIXTURE["review"]
        decisions = [d for d in review["decisions"] if d["id"] != "77000000-0000-4000-8000-000000000013"]  # drop C adjudication
        counts = compute_flow_counts(review["occurrences"], review["mapping_events"], review["candidates"],
                                     decisions, [l for l in review["report_studies"] if l["study_id"]], protocol_version=1)
        self.assertEqual(counts["included_reports"], 2)
        self.assertEqual(counts["included_studies"], 2)

    def test_merge_adjudication_is_bound_to_the_conflict(self):
        # A pre-existing v1 adjudication does not satisfy a later conflicting v2 merge;
        # a v2 adjudication does. The v1 snapshot keeps its own sets (merge not applied).
        review = FIXTURE["review"]
        report_a, report_b = "33000000-0000-4000-8000-000000000001", "33000000-0000-4000-8000-000000000002"
        candidate_a, candidate_b = "66000000-0000-4000-8000-000000000001", "66000000-0000-4000-8000-000000000002"
        owner = FIXTURE["actors"]["owner"]
        base = list(review["decisions"])
        adjudication_v1 = {"candidate_id": candidate_b, "stage": "fulltext", "protocol_version": 1,
                           "actor_id": owner, "decision": "included", "role": "adjudication", "created_at": "2026-01-01T00:00:00Z"}
        merge_v2 = {"kind": "report_merge", "created_at": "2026-02-01T00:00:00Z",
                    "payload": {"source": report_a, "target": report_b, "conflicting_stages": ["fulltext"],
                                "conflicting_decisions": [{"stage": "fulltext", "source": "included", "target": "excluded"}],
                                "protocol_version": 2}}
        occurrences, events, candidates, links = review["occurrences"], list(review["mapping_events"]), review["candidates"], [l for l in review["report_studies"] if l["study_id"]]
        counts = compute_flow_counts(occurrences, events + [merge_v2], candidates, base + [adjudication_v1], links, 2,
                                     screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        # C's separate v1 adjudication stands; the merged candidate B is pending because
        # the pre-existing adjudication cannot satisfy the later conflicting merge.
        self.assertEqual((counts["included_reports"], counts["pending_adjudication"]), (1, 1))
        adjudication_v2 = {"candidate_id": candidate_b, "stage": "fulltext", "protocol_version": 2,
                           "actor_id": owner, "decision": "included", "role": "adjudication", "created_at": "2026-03-01T00:00:00Z"}
        counts = compute_flow_counts(occurrences, events + [merge_v2], candidates, base + [adjudication_v1, adjudication_v2], links, 2,
                                     screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        # B resolves via the v2 adjudication; C remains included through its own v1 adjudication.
        self.assertEqual((counts["included_reports"], counts["pending_adjudication"]), (2, 0))
        before = compute_flow_counts(occurrences, events, candidates, list(review["decisions"]), links, 1,
                                     screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual((before["included_reports"], before["fulltext_excluded"], before["pending_adjudication"]), (3, 1, 0))

    def test_merge_conserves_occurrence_accounting_and_study_links(self):
        # R11: merging A into B folds A's occurrences into B (conservation holds) and
        # A's confirmed study links keep counting through the representative.
        review = FIXTURE["review"]
        report_a = "33000000-0000-4000-8000-000000000001"
        merge = {"kind": "report_merge", "created_at": "2026-02-01T00:00:00Z",
                 "payload": {"source": report_a, "target": "33000000-0000-4000-8000-000000000002",
                             "conflicting_stages": [], "conflicting_decisions": [], "protocol_version": 1}}
        links = [l for l in review["report_studies"] if l["study_id"]]
        counts = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [merge],
                                     review["candidates"], list(review["decisions"]), links, 1,
                                     screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual(counts["identified_occurrences"], 10)
        self.assertEqual(counts["retained_candidates"], 5)
        self.assertEqual(counts["retained_occurrences"], 6)
        self.assertEqual(counts["identified_occurrences"],
                         counts["duplicate_removals"] + counts["retained_occurrences"])
        # A's SA link resolves through the representative: SA stays counted.
        self.assertEqual(counts["included_studies"], 2)
        self.assertEqual(counts["included_reports"], 2)
        split = {"kind": "report_split", "created_at": "2026-02-02T00:00:00Z",
                 "payload": {"source": report_a, "rationale": "Fixture: split back", "protocol_version": 1}}
        restored = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [merge, split],
                                       review["candidates"], list(review["decisions"]), links, 1,
                                       screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual((restored["retained_candidates"], restored["included_studies"]), (6, 2))
        self.assertEqual(restored["identified_occurrences"],
                         restored["duplicate_removals"] + restored["retained_occurrences"])

    def test_chained_merge_keeps_pending_adjudication_on_the_representative(self):
        # R4: A→B creates a pending conflict; merging B onward into C must carry the
        # unresolved conflict to C, not erase it with B's candidate.
        review = FIXTURE["review"]
        report_a, report_b, report_c = ("33000000-0000-4000-8000-000000000001",
                                        "33000000-0000-4000-8000-000000000002",
                                        "33000000-0000-4000-8000-000000000003")
        candidate_a, candidate_c = "66000000-0000-4000-8000-000000000001", "66000000-0000-4000-8000-000000000003"
        events = list(review["mapping_events"]) + [
            {"kind": "report_merge", "created_at": "2026-02-01T00:00:00Z",
             "payload": {"source": report_a, "target": report_b, "conflicting_stages": ["fulltext"],
                         "conflicting_decisions": [{"stage": "fulltext", "source": "included", "target": "excluded"}],
                         "protocol_version": 1}},
            {"kind": "report_merge", "created_at": "2026-02-02T00:00:00Z",
             "payload": {"source": report_b, "target": report_c, "conflicting_stages": [],
                         "conflicting_decisions": [], "protocol_version": 1}}]
        counts = compute_flow_counts(review["occurrences"], events, review["candidates"], list(review["decisions"]),
                                     [l for l in review["report_studies"] if l["study_id"]], 1,
                                     screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual(counts["pending_adjudication"], 1)
        self.assertEqual(counts["retained_candidates"], 4)  # A and B folded into C
        # Resolving the inherited conflict on C restores its inclusion.
        resolution = {"candidate_id": candidate_c, "stage": "fulltext", "protocol_version": 1,
                      "actor_id": FIXTURE["actors"]["owner"], "decision": "included",
                      "role": "adjudication", "created_at": "2026-02-03T00:00:00Z"}
        resolved = compute_flow_counts(review["occurrences"], events, review["candidates"],
                                       list(review["decisions"]) + [resolution],
                                       [l for l in review["report_studies"] if l["study_id"]], 1,
                                       screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual(resolved["pending_adjudication"], 0)
        self.assertEqual(resolved["included_reports"], counts["included_reports"] + 1)

    def test_later_acquisition_events_do_not_touch_historic_counts(self):
        # The DB layer filters occurrences and occurrence-map events by protocol version;
        # the pure function honours the recorded versions of the mapping events it gets.
        review = FIXTURE["review"]
        later_map = {"kind": "occurrence_map", "payload": {"candidate": "66000000-0000-4000-8000-000000000002",
                                                           "retained": "22000000-0000-4000-8000-000000000004",
                                                           "removed": ["22000000-0000-4000-8000-000000000011"],
                                                           "protocol_version": 2}}
        counts_v1 = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [later_map],
                                        review["candidates"], list(review["decisions"]),
                                        [l for l in review["report_studies"] if l["study_id"]], 1,
                                        screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual((counts_v1["identified_occurrences"], counts_v1["duplicate_removals"]), (10, 4))
        occurrences_v2 = list(review["occurrences"]) + [
            {"id": "22000000-0000-4000-8000-000000000011", "protocol_version": 2,
             "search_execution": "11000000-0000-4000-8000-000000000002"}]
        later_candidate = {"id": "66000000-0000-4000-8000-000000000007", "report_id": "33000000-0000-4000-8000-000000000002",
                           "selected_version_id": None, "retained": True, "protocol_version": 2}
        counts_v2 = compute_flow_counts(occurrences_v2, list(review["mapping_events"]) + [later_map],
                                        list(review["candidates"]) + [later_candidate], list(review["decisions"]),
                                        [l for l in review["report_studies"] if l["study_id"]], 2,
                                        screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual((counts_v2["identified_occurrences"], counts_v2["duplicate_removals"]), (11, 5))
        self.assertEqual(counts_v2["retained_candidates"], 7)
        # A study link first created at v2 leaks into no earlier snapshot.
        links_with_late = [l for l in review["report_studies"] if l["study_id"]] + [
            {"report_id": "33000000-0000-4000-8000-000000000002", "study_id": "55000000-0000-4000-8000-000000000003",
             "linkage_state": "confirmed", "protocol_version": 2}]
        counts_v2_late_link = compute_flow_counts(occurrences_v2, list(review["mapping_events"]) + [later_map],
                                                  list(review["candidates"]) + [later_candidate], list(review["decisions"]),
                                                  links_with_late, 2,
                                                  screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual(counts_v2_late_link["included_studies"], 3)  # B gains the new SD link at v2
        # v1 sees neither the later occurrence, the later candidate nor the late link.
        counts_v1_again = compute_flow_counts(occurrences_v2, list(review["mapping_events"]) + [later_map],
                                              list(review["candidates"]) + [later_candidate], list(review["decisions"]),
                                              links_with_late, 1,
                                              screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual((counts_v1_again["identified_occurrences"], counts_v1_again["retained_candidates"]), (10, 6))
        self.assertEqual(counts_v1_again["included_studies"], 2)
        # A versioned linkage withdrawal applies at v2 only.
        events_with_link = list(review["mapping_events"]) + [later_map, {
            "kind": "study_link", "payload": {"report": "33000000-0000-4000-8000-000000000001",
                                              "study": "55000000-0000-4000-8000-000000000001",
                                              "linkage_state": "unresolved", "protocol_version": 2}}]
        counts_v2_link = compute_flow_counts(occurrences_v2, events_with_link,
                                             list(review["candidates"]) + [later_candidate], list(review["decisions"]),
                                             [l for l in review["report_studies"] if l["study_id"]], 2,
                                             screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        # This scenario has no v2 reopen, so D stays excluded: included {A,B,C} map to
        # SA+SB (2). Withdrawing A->SA at v2 drops it to SB only (1); v1 keeps SA+SB.
        self.assertEqual(counts_v2_link["included_studies"], 1)
        self.assertEqual(counts_v1_again["included_studies"], 2)
        counts_v2_before = compute_flow_counts(occurrences_v2, list(review["mapping_events"]) + [later_map],
                                               list(review["candidates"]) + [later_candidate], list(review["decisions"]),
                                               [l for l in review["report_studies"] if l["study_id"]], 2,
                                               screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual(counts_v2_before["included_studies"], 2)

    def test_remapping_supersedes_prior_occurrence_state(self):
        # R12: a later mapping update that swaps a candidate's retained occurrence with one
        # of its duplicates supersedes the earlier mapping; sets stay disjoint and the
        # conservation identity holds at every snapshot.
        review = FIXTURE["review"]
        remap = {"kind": "occurrence_map", "created_at": "2026-02-01T00:00:00Z",
                 "payload": {"candidate": "66000000-0000-4000-8000-000000000002",
                             "retained": "22000000-0000-4000-8000-000000000007",  # former duplicate O07
                             "removed": ["22000000-0000-4000-8000-000000000004"],  # former representative O04
                             "protocol_version": 2}}
        links = [l for l in review["report_studies"] if l["study_id"]]
        counts_v2 = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [remap],
                                        review["candidates"], list(review["decisions"]), links, 2,
                                        screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual((counts_v2["identified_occurrences"], counts_v2["duplicate_removals"],
                          counts_v2["retained_occurrences"]), (10, 4, 6))
        self.assertEqual(counts_v2["identified_occurrences"],
                         counts_v2["duplicate_removals"] + counts_v2["retained_occurrences"])
        # The v1 snapshot keeps the original mapping.
        counts_v1 = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [remap],
                                        review["candidates"], list(review["decisions"]), links, 1,
                                        screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual((counts_v1["duplicate_removals"], counts_v1["retained_occurrences"]), (4, 6))

    def test_adjudication_selection_is_order_independent(self):
        # R12: two qualifying adjudications at different versions resolve deterministically
        # regardless of input order.
        review = FIXTURE["review"]
        owner = FIXTURE["actors"]["owner"]
        merged_source, merged_target = "33000000-0000-4000-8000-000000000001", "33000000-0000-4000-8000-000000000002"
        candidate_b = "66000000-0000-4000-8000-000000000002"
        merge = {"kind": "report_merge", "created_at": "2026-01-01T00:00:00Z",
                 "payload": {"source": merged_source, "target": merged_target,
                             "conflicting_stages": ["fulltext"],
                             "conflicting_decisions": [{"stage": "fulltext", "source": "included", "target": "excluded"}],
                             "protocol_version": 1}}
        links = [l for l in review["report_studies"] if l["study_id"]]
        base = list(review["decisions"])
        first = {"candidate_id": candidate_b, "stage": "fulltext", "protocol_version": 2,
                 "actor_id": owner, "decision": "included", "role": "adjudication",
                 "created_at": "2026-02-01T00:00:00Z", "id": "77000000-0000-4000-8000-000000000101"}
        second = {"candidate_id": candidate_b, "stage": "fulltext", "protocol_version": 3,
                  "actor_id": owner, "decision": "excluded", "role": "adjudication",
                  "created_at": "2026-03-01T00:00:00Z", "id": "77000000-0000-4000-8000-000000000102"}
        screening_modes = {"title_abstract": "solo", "fulltext": "dual"}
        forward = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [merge],
                                      review["candidates"], base + [first, second], links, 3, screening_modes=screening_modes)
        backward = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [merge],
                                       review["candidates"], base + [second, first], links, 3, screening_modes=screening_modes)
        self.assertEqual(forward["included_reports"], 1)  # the v3 exclusion decides
        self.assertEqual(backward, forward)

    def test_solo_repeat_submissions_are_order_independent(self):
        # R13: repeated solo submissions resolve to each actor's latest decision
        # deterministically; input order never changes counts.
        review = FIXTURE["review"]
        owner = FIXTURE["actors"]["owner"]
        candidate_a = "66000000-0000-4000-8000-000000000001"
        first = {"candidate_id": candidate_a, "stage": "title_abstract", "protocol_version": 1,
                 "actor_id": owner, "decision": "excluded", "role": "primary", "created_at": "2026-01-01T00:00:00Z"}
        second = {"candidate_id": candidate_a, "stage": "title_abstract", "protocol_version": 1,
                  "actor_id": owner, "decision": "included", "role": "primary", "created_at": "2026-01-02T00:00:00Z"}
        links = [l for l in review["report_studies"] if l["study_id"]]
        screening_modes = {"title_abstract": "solo", "fulltext": "dual"}
        forward = compute_flow_counts(review["occurrences"], review["mapping_events"], review["candidates"],
                                      list(review["decisions"]) + [first, second], links, 1, screening_modes=screening_modes)
        backward = compute_flow_counts(review["occurrences"], review["mapping_events"], review["candidates"],
                                       list(review["decisions"]) + [second, first], links, 1, screening_modes=screening_modes)
        self.assertEqual(forward, backward)
        self.assertEqual(forward["screened"], 6)  # the later 'included' wins
        self.assertEqual(forward["reports_sought"], 5)

    def test_snapshot_membership_guards_conservation(self):
        # R13: an occurrence outside the snapshot (mapped before its acquisition version)
        # never breaks conservation; the service refuses such mappings outright.
        review = FIXTURE["review"]
        premature_map = {"kind": "occurrence_map", "payload": {"candidate": "66000000-0000-4000-8000-000000000002",
                                                               "retained": "22000000-0000-4000-8000-000000000011",
                                                               "removed": ["22000000-0000-4000-8000-000000000004"],
                                                               "protocol_version": 1}}
        late_occurrence = {"id": "22000000-0000-4000-8000-000000000011", "protocol_version": 2}
        counts = compute_flow_counts(list(review["occurrences"]) + [late_occurrence],
                                     list(review["mapping_events"]) + [premature_map],
                                     review["candidates"], list(review["decisions"]),
                                     [l for l in review["report_studies"] if l["study_id"]], 1,
                                     screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual(counts["identified_occurrences"],
                         counts["duplicate_removals"] + counts["retained_occurrences"])

    def test_amendment_after_resolved_merge_governs_over_the_old_resolution(self):
        # R16: a resolved merge (v1 adjudication includes) followed by a newer v2 solo
        # exclusion: the latest cohort governs at v2; the v1 snapshot keeps the resolution.
        review = FIXTURE["review"]
        report_a, report_b = "33000000-0000-4000-8000-000000000001", "33000000-0000-4000-8000-000000000002"
        candidate_b = "66000000-0000-4000-8000-000000000002"
        owner = FIXTURE["actors"]["owner"]
        merge = {"kind": "report_merge", "created_at": "2026-02-01T00:00:00Z",
                 "payload": {"source": report_a, "target": report_b, "conflicting_stages": ["fulltext"],
                             "conflicting_decisions": [{"stage": "fulltext", "source": "included", "target": "excluded"}],
                             "protocol_version": 1}}
        resolution = {"candidate_id": candidate_b, "stage": "fulltext", "protocol_version": 1,
                      "actor_id": owner, "decision": "included", "role": "adjudication",
                      "created_at": "2026-02-02T00:00:00Z"}
        amendment = {"candidate_id": candidate_b, "stage": "fulltext", "protocol_version": 2,
                     "actor_id": owner, "decision": "excluded", "role": "primary",
                     "created_at": "2026-03-01T00:00:00Z"}
        links = [l for l in review["report_studies"] if l["study_id"]]
        screening_modes = {"title_abstract": "solo", "fulltext": "dual"}
        counts_v1 = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [merge],
                                        review["candidates"], list(review["decisions"]) + [resolution], links, 1,
                                        screening_modes=screening_modes)
        # A's candidate folds into B: the merged set is included via the resolution.
        self.assertEqual((counts_v1["included_reports"], counts_v1["pending_adjudication"]), (2, 0))
        counts_v2 = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [merge],
                                        review["candidates"],
                                        list(review["decisions"]) + [resolution, amendment], links, 2,
                                        screening_modes=screening_modes)
        # The resolution no longer governs: the single-reviewer v2 cohort cannot finalize
        # a dual stage, so B is pending (never included by the old adjudication); D stays
        # excluded from its v1 cohort and C remains included.
        self.assertEqual((counts_v2["fulltext_excluded"], counts_v2["included_reports"], counts_v2["pending_adjudication"]),
                         (1, 1, 1))

    def test_amendment_cohorts_enforce_dual_review_and_clear_pending(self):
        # R17: the superseding cohort is the full latest protocol version — both reviewers
        # participate under dual mode, disagreement stays pending and never coexists with
        # an included count for the same candidate.
        review = FIXTURE["review"]
        report_a, report_b = "33000000-0000-4000-8000-000000000001", "33000000-0000-4000-8000-000000000002"
        candidate_b = "66000000-0000-4000-8000-000000000002"
        owner = FIXTURE["actors"]["owner"]
        reviewer_1 = FIXTURE["actors"]["reviewer_1"]
        merge = {"kind": "report_merge", "created_at": "2026-02-01T00:00:00Z",
                 "payload": {"source": report_a, "target": report_b, "conflicting_stages": ["fulltext"],
                             "conflicting_decisions": [{"stage": "fulltext", "source": "included", "target": "excluded"}],
                             "protocol_version": 1}}
        resolution = {"candidate_id": candidate_b, "stage": "fulltext", "protocol_version": 1,
                      "actor_id": owner, "decision": "included", "role": "adjudication",
                      "created_at": "2026-02-02T00:00:00Z"}
        links = [l for l in review["report_studies"] if l["study_id"]]
        screening_modes = {"title_abstract": "solo", "fulltext": "dual"}
        # Incomplete dual amendment at v2 (one reviewer): pending, not finalized.
        single = {"candidate_id": candidate_b, "stage": "fulltext", "protocol_version": 2,
                  "actor_id": owner, "decision": "excluded", "role": "primary", "created_at": "2026-03-01T00:00:00Z"}
        counts = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [merge],
                                     review["candidates"], list(review["decisions"]) + [resolution, single], links, 2,
                                     screening_modes=screening_modes)
        self.assertEqual((counts["pending_adjudication"], counts["included_reports"]), (1, 1))
        # Complete dual amendment at v2 with agreement: decided; both submission orders equal.
        first = {"candidate_id": candidate_b, "stage": "fulltext", "protocol_version": 2,
                 "actor_id": owner, "decision": "excluded", "role": "primary", "created_at": "2026-03-01T00:00:00Z"}
        second = {"candidate_id": candidate_b, "stage": "fulltext", "protocol_version": 2,
                  "actor_id": reviewer_1, "decision": "excluded", "role": "primary", "created_at": "2026-03-01T00:00:01Z"}
        decided = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [merge],
                                      review["candidates"], list(review["decisions"]) + [resolution, first, second],
                                      links, 2, screening_modes=screening_modes)
        self.assertEqual((decided["pending_adjudication"], decided["fulltext_excluded"]), (0, 2))
        swapped = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [merge],
                                      review["candidates"], list(review["decisions"]) + [resolution, second, first],
                                      links, 2, screening_modes=screening_modes)
        self.assertEqual(swapped, decided)
        # A v1 cohort disagreeing after the resolution (same-version, later submissions)
        # stays pending and the resolution does not remain included.
        disagreeing = [{"candidate_id": candidate_b, "stage": "fulltext", "protocol_version": 1,
                        "actor_id": owner, "decision": "excluded", "role": "primary",
                        "created_at": "2026-02-03T00:00:00Z"},
                       {"candidate_id": candidate_b, "stage": "fulltext", "protocol_version": 1,
                        "actor_id": reviewer_1, "decision": "included", "role": "primary",
                        "created_at": "2026-02-03T00:00:00Z"}]
        pending_state = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [merge],
                                            review["candidates"], list(review["decisions"]) + [resolution] + disagreeing,
                                            links, 1, screening_modes=screening_modes)
        self.assertEqual(pending_state["pending_adjudication"], 1)
        self.assertEqual(pending_state["included_reports"], 1)  # only C; B is pending, not included

    def test_durable_ordering_beats_timestamps_and_uuid_order(self):
        # R19: equal timestamps and arbitrary UUIDs never change outcomes — the shared
        # event sequence orders merges, adjudications and repeated solo submissions.
        review = FIXTURE["review"]
        report_a, report_b, report_c = ("33000000-0000-4000-8000-000000000001",
                                        "33000000-0000-4000-8000-000000000002",
                                        "33000000-0000-4000-8000-000000000003")
        candidate_b, candidate_c = "66000000-0000-4000-8000-000000000002", "66000000-0000-4000-8000-000000000003"
        owner = FIXTURE["actors"]["owner"]
        merge1 = {"kind": "report_merge", "created_at": "2026-01-01T00:00:00Z", "event_sequence": 10,
                  "payload": {"source": report_a, "target": report_b, "conflicting_stages": ["fulltext"],
                              "conflicting_decisions": [{"stage": "fulltext", "source": "included", "target": "excluded"}],
                              "protocol_version": 1}}
        resolution = {"candidate_id": candidate_b, "stage": "fulltext", "protocol_version": 1,
                      "actor_id": owner, "decision": "included", "role": "adjudication",
                      "created_at": "2026-01-01T00:00:00Z", "event_sequence": 11}
        merge2 = {"kind": "report_merge", "created_at": "2026-01-01T00:00:00Z", "event_sequence": 12,
                  "payload": {"source": report_c, "target": report_b, "conflicting_stages": ["fulltext"],
                              "conflicting_decisions": [{"stage": "fulltext", "source": "included", "target": "excluded"}],
                              "protocol_version": 1}}
        links = [l for l in review["report_studies"] if l["study_id"]]
        screening_modes = {"title_abstract": "solo", "fulltext": "dual"}
        counts = compute_flow_counts(review["occurrences"], list(review["mapping_events"]) + [merge1, merge2],
                                     review["candidates"], list(review["decisions"]) + [resolution], links, 1,
                                     screening_modes=screening_modes)
        # The resolution covers the first conflict only; the second conflicting merge
        # (sequence 12) leaves the representative pending, and C folds into B.
        self.assertEqual((counts["included_reports"], counts["pending_adjudication"]), (0, 1))
        # Repeated solo submissions with equal timestamps: the later sequence wins even
        # when its UUID sorts lexicographically earlier.
        first = {"candidate_id": "66000000-0000-4000-8000-000000000001", "stage": "title_abstract",
                 "protocol_version": 1, "actor_id": owner, "decision": "included", "role": "primary",
                 "created_at": "2026-01-01T00:00:00Z", "event_sequence": 20,
                 "id": "ffffffff-0000-4000-8000-000000000001"}
        second = {"candidate_id": "66000000-0000-4000-8000-000000000001", "stage": "title_abstract",
                  "protocol_version": 1, "actor_id": owner, "decision": "excluded", "role": "primary",
                  "created_at": "2026-01-01T00:00:00Z", "event_sequence": 21,
                  "id": "00000000-0000-4000-8000-000000000002"}
        counts = compute_flow_counts(review["occurrences"], review["mapping_events"], review["candidates"],
                                     list(review["decisions"]) + [first, second], links, 1,
                                     screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual(counts["title_abstract_excluded"], 2)  # A (sequence 21 supersedes 20) and F

    def test_chained_merge_accumulates_conflicts_per_representative_and_stage(self):
        # R5: A→B conflicts at title/abstract; B→C conflicts at fulltext. Resolving only
        # the full-text conflict on C must leave the title/abstract conflict pending.
        review = FIXTURE["review"]
        report_a, report_b, report_c = ("33000000-0000-4000-8000-000000000001",
                                        "33000000-0000-4000-8000-000000000002",
                                        "33000000-0000-4000-8000-000000000003")
        candidate_c = "66000000-0000-4000-8000-000000000003"
        events = list(review["mapping_events"]) + [
            {"kind": "report_merge", "created_at": "2026-02-01T00:00:00Z",
             "payload": {"source": report_a, "target": report_b,
                         "conflicting_stages": ["title_abstract"],
                         "conflicting_decisions": [{"stage": "title_abstract", "source": "included", "target": "excluded"}],
                         "protocol_version": 1}},
            {"kind": "report_merge", "created_at": "2026-02-02T00:00:00Z",
             "payload": {"source": report_b, "target": report_c, "conflicting_stages": ["fulltext"],
                         "conflicting_decisions": [{"stage": "fulltext", "source": "included", "target": "excluded"}],
                         "protocol_version": 1}}]
        links = [l for l in review["report_studies"] if l["study_id"]]
        counts = compute_flow_counts(review["occurrences"], events, review["candidates"], list(review["decisions"]),
                                     links, 1, screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual(counts["pending_adjudication"], 1)
        self.assertEqual(counts["included_reports"], 0)
        fulltext_resolution = {"candidate_id": candidate_c, "stage": "fulltext", "protocol_version": 1,
                               "actor_id": FIXTURE["actors"]["owner"], "decision": "included",
                               "role": "adjudication", "created_at": "2026-02-03T00:00:00Z"}
        counts = compute_flow_counts(review["occurrences"], events, review["candidates"],
                                     list(review["decisions"]) + [fulltext_resolution], links, 1,
                                     screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual((counts["pending_adjudication"], counts["included_reports"]), (1, 0))
        ta_resolution = {"candidate_id": candidate_c, "stage": "title_abstract", "protocol_version": 1,
                         "actor_id": FIXTURE["actors"]["owner"], "decision": "included",
                         "role": "adjudication", "created_at": "2026-02-04T00:00:00Z"}
        counts = compute_flow_counts(review["occurrences"], events, review["candidates"],
                                     list(review["decisions"]) + [fulltext_resolution, ta_resolution], links, 1,
                                     screening_modes={"title_abstract": "solo", "fulltext": "dual"})
        self.assertEqual(counts["pending_adjudication"], 0)

    def test_unresolved_study_linkage_is_not_corroboration(self):
        review = FIXTURE["review"]
        links = [dict(link) for link in review["report_studies"] if link["study_id"]]
        for link in links:
            if link["linkage_state"] != "confirmed": link["linkage_state"] = "unresolved"
        counts = compute_flow_counts(review["occurrences"], review["mapping_events"], review["candidates"],
                                     list(review["decisions"]), links, protocol_version=1)
        self.assertEqual(counts["included_studies"], 2)
