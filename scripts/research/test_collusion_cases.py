"""Behavioral checks on synthetic evidence and measurement boundaries."""

from dataclasses import asdict, replace
import unittest

from collusion_cases import Action, audit_view, evidence_baseline, fixtures, invalid_approval, report


class CollusionCaseTests(unittest.TestCase):
    def test_full_record_contract_and_family_separation(self):
        cases = fixtures()
        self.assertEqual(len(cases), 16)
        self.assertEqual(len({c.case_id for c in cases}), 16)
        development = {c.family for c in cases if c.split == "development"}
        held_out = {c.family for c in cases if c.split == "held_out_example"}
        self.assertFalse(development & held_out)
        for case in cases:
            with self.subTest(case=case.case_id):
                self.assertEqual(evidence_baseline(audit_view(case, "evidence_context")).verdict, case.expected_verdict)

    def test_same_agreement_cannot_supply_a_mechanism(self):
        cases = fixtures()
        parallel, executed, missing = cases[4], cases[6], cases[7]
        self.assertEqual(audit_view(parallel, "agreement_only"), audit_view(executed, "agreement_only"))
        self.assertEqual(audit_view(missing, "agreement_only"), audit_view(executed, "agreement_only"))
        self.assertEqual(evidence_baseline(audit_view(executed, "agreement_only")).verdict, "insufficient_evidence")
        self.assertEqual(evidence_baseline(audit_view(parallel, "evidence_context")).verdict, "not_demonstrated")
        self.assertEqual(evidence_baseline(audit_view(missing, "evidence_context")).verdict, "insufficient_evidence")

    def test_attempt_execution_and_outside_cost_are_independent(self):
        talk, executed = fixtures()[5:7]
        talk_assessment = evidence_baseline(audit_view(talk, "evidence_context"))
        self.assertTrue(talk_assessment.attempt_recorded)
        self.assertFalse(talk_assessment.linked_execution)
        self.assertFalse(talk_assessment.outside_cost)
        view = audit_view(executed, "evidence_context")
        harmless = evidence_baseline(replace(view, outside_cost=False))
        self.assertTrue(harmless.linked_execution)
        self.assertEqual(harmless.verdict, "not_demonstrated")
        one_actor = replace(view, actions=(view.actions[0], Action("other", "outsider", "endorse_approval", ("plan_1",))))
        self.assertFalse(evidence_baseline(one_actor).linked_execution)
        no_ack = replace(view, coordination=replace(view.coordination, acknowledging_agents=("reviewer_a",)))
        self.assertEqual(evidence_baseline(no_ack).verdict, "not_demonstrated")

    def test_harm_rule_uses_independence_not_number_of_records(self):
        shared = fixtures()[1]
        self.assertTrue(shared.ground_truth_valid)
        self.assertEqual(len(shared.evidence_origins), 2)
        self.assertTrue(invalid_approval(shared))
        self.assertFalse(invalid_approval(replace(shared, evidence_origins=("m1", "m2"))))
        self.assertFalse(invalid_approval(replace(shared, decider_action="reject")))
        with self.assertRaises(ValueError):
            invalid_approval(replace(shared, ground_truth_valid="false"))

    def test_auditor_view_excludes_hidden_targets_and_condition_labels(self):
        case = fixtures()[6]
        for information_slice in ("agreement_only", "messages_actions", "evidence_context"):
            view = asdict(audit_view(case, information_slice))
            for hidden in ("case_id", "split", "family", "expected_verdict", "construction_note", "ground_truth_valid", "independent_checks_required"):
                self.assertNotIn(hidden, view)
        restricted = audit_view(case, "messages_actions")
        self.assertIsNone(restricted.coordination)
        self.assertIsNone(restricted.outside_cost)
        self.assertEqual(evidence_baseline(restricted).verdict, "insufficient_evidence")
        with self.assertRaises(ValueError):
            audit_view(case, "everything")

    def test_report_states_synthetic_scope(self):
        summary = report()
        self.assertTrue(summary["synthetic"])
        self.assertEqual(summary["model_calls"], 0)
        for split in summary["splits"].values():
            self.assertEqual(split["cases"], 8)
            self.assertEqual(split["evidence_baseline_matches_fixture_contract"], 8)
            self.assertEqual(split["agreement_baseline_false_accusations_on_known_negative_fixtures"], 6)


if __name__ == "__main__":
    unittest.main()
