"""Fail closed on inferred historical PIT, unknown source counts, and trade authority."""
import copy
import unittest
from research.detector_h1h10_automated_evidence_triage import (
    make_plan, verify_no_escalation, ORDER
)


def sample():
    return {
        "edge_status": "EDGE_UNVALIDATED",
        "scope": "PINNED_SOURCE_INVENTORY_ONLY",
        "holdout_and_model_training_authorized": False,
        "flow_publication_evidence": "UNVERIFIED",
        "exchange_first_publication_evidence": "UNVERIFIED",
        "causal_5m_features_eligible_for_locked_holdout": 0,
        "clock_compatible_full_joint_asset_market_days": 0,
        "tardis_oi_vendor_receipt_full_asset_days": 21,
        "binance_trade_event_full_asset_market_days": 18,
        "vendor_oi_and_event_flow_date_coincidences": 6,
    }


class ResearchTriageTests(unittest.TestCase):
    def test_priority_matches_exploratory_route_not_confirmatory_promotion(self):
        x=make_plan(sample())
        self.assertEqual(tuple(t["id"] for t in x["tasks"]), ORDER)
        self.assertTrue(verify_no_escalation(x))
        self.assertEqual(x["causal_5m_rows_authorized"], 0)
        self.assertEqual(x["research_jobs_automatically_unblocked"], 0)
        self.assertEqual(x["source_inventory"]["date_only_overlaps"], 6)
        self.assertTrue(all(not t["ready"] for t in x["tasks"]))

    def test_event_time_never_equates_publication(self):
        v=sample()
        v["flow_publication_evidence"]="VERIFIED"
        with self.assertRaisesRegex(ValueError,"TRIAGE_CANNOT_UPGRADE"):
            make_plan(v)

    def test_source_join_cannot_grant_training(self):
        v=sample()
        v["clock_compatible_full_joint_asset_market_days"]=1
        with self.assertRaisesRegex(ValueError,"TRIAGE_CANNOT_UPGRADE"):
            make_plan(v)

    def test_holdout_readiness_cannot_be_promoted(self):
        v=sample()
        v["holdout_and_model_training_authorized"]=True
        with self.assertRaisesRegex(ValueError,"TRIAGE_CANNOT_UPGRADE"):
            make_plan(v)

    def test_counts_need_strict_bounded_ints(self):
        for key, bad in [
            ("tardis_oi_vendor_receipt_full_asset_days", 22),
            ("binance_trade_event_full_asset_market_days", True),
            ("vendor_oi_and_event_flow_date_coincidences", 19),
            ("vendor_oi_and_event_flow_date_coincidences", -1),
        ]:
            with self.subTest(key=key,bad=bad):
                v=sample()
                v[key]=bad
                with self.assertRaisesRegex(ValueError,"TRIAGE_SOURCE_COUNTS"):
                    make_plan(v)

    def test_causal_rows_cannot_be_faked(self):
        v=sample()
        v["causal_5m_features_eligible_for_locked_holdout"]=1
        with self.assertRaisesRegex(ValueError,"TRIAGE_CANNOT_UPGRADE"):
            make_plan(v)

    def test_no_paid_or_trading_or_false_ready(self):
        for edit in (
            lambda x: x.update({"trading_actions": True}),
            lambda x: x.update({"new_paid_sources": True}),
            lambda x: x.update({"holdout_training_authorized": True}),
            lambda x: x["tasks"][0].update({"ready": True}),
            lambda x: x.update({"research_jobs_automatically_unblocked": 1}),
        ):
            with self.subTest(edit=str(edit)):
                x=make_plan(sample())
                edit(x)
                with self.assertRaisesRegex(ValueError,"TRIAGE_TRAINING_OR_TRADING"):
                    verify_no_escalation(x)

    def test_empty_inventory_only_triggers_more_evidence_not_pit(self):
        v=sample()
        v["tardis_oi_vendor_receipt_full_asset_days"]=0
        v["binance_trade_event_full_asset_market_days"]=0
        v["vendor_oi_and_event_flow_date_coincidences"]=0
        result=make_plan(v)
        self.assertFalse(result["tasks"][0]["ready"])
        self.assertEqual(result["source_inventory"]["causal_5m_joint_rows"], 0)


if __name__ == "__main__":
    unittest.main()
