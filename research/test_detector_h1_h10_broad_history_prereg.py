#!/usr/bin/env python3
"""Offline frozen H1-H10 preregistration integrity and authority safeguards."""
import json
from pathlib import Path
import unittest

FILE=Path(__file__).with_name("detector_h1_h10_broad_history_prereg_v1_2026-10-19.json")

class FrozenH1H10(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.doc=json.loads(FILE.read_text(encoding="utf-8"))
 def test_h1_h10_unique_and_not_confirmed(self):
  h=self.doc["hypotheses"]
  self.assertEqual([x["id"] for x in h],[f"H{i}" for i in range(1,11)])
  self.assertTrue(all(x["status"]=="NOT_YET_CONFIRMATORY_TESTED" for x in h))
 def test_research_has_no_trading_authority(self):
  self.assertEqual(self.doc["authority"],"RESEARCH_ONLY")
  self.assertFalse(self.doc["trade_actions"])
  self.assertEqual(self.doc["edge_status"],"EDGE_UNVALIDATED")
 def test_known_exploratory_days_excluded_from_claim(self):
  self.assertIn("2026-09-01",self.doc["reused_discovery_dates"])
  self.assertIn("2026-10-01",self.doc["reused_discovery_dates"])
  self.assertTrue(self.doc["split"]["exclude_all_previously_viewed_dates"])
  self.assertEqual(self.doc["split"]["holdout_pristine_status"],"NOT_YET_CERTIFIED")
 def test_control_and_target_immutability(self):
  self.assertEqual(self.doc["targets"]["direction"]["primary_metric"],"Brier")
  self.assertEqual(self.doc["targets"]["magnitude"]["primary_metric"],"MAE")
  self.assertEqual(self.doc["targets"]["magnitude"]["target"],"abs future log return")
  self.assertIn("zero movement",self.doc["falsification_controls"]["magnitude"])
  self.assertEqual(self.doc["split"]["purge_embargo_hours"],24)
 def test_asof_and_multiple_testing_are_hard_gates(self):
  required=set(self.doc["datasets_must_have"])
  self.assertIn("source_event_at",required)
  self.assertIn("source_first_available_at_or_vendor_receipt_at",required)
  self.assertIn("ASOF_PUBLICATION_UNVERIFIED",self.doc["quality_fail_closed"])
  self.assertEqual(self.doc["significance"]["correction"],"Holm familywise 0.05")
  self.assertFalse(self.doc["significance"]["overlapping_5m_rows_are_independent"])

if __name__=="__main__":unittest.main()
