"""Offline H1-H10 fastlane guard tests - no network / no R2 credentials."""
import copy,unittest
from research import detector_h1h10_fastlane as g

def valid():
    return {"joint_oi_source":{
      "schema":g.PINS["joint_oi_source"]["schema"],
      "joint_full_days":1734,"total_calendar_days":1750,
      "joint_excluded_days":16,"data_cutoff_last_day":"2026-10-16",
      "edge_status":"EDGE_UNVALIDATED","research_only":True,
      "pit_release_timestamp":"UNVERIFIED"}}
class GateTests(unittest.TestCase):
 def test_source_pass_but_confirmatory_blocked(self):
    x=g.assemble(valid())
    self.assertEqual(x["pipeline_gates"]["original_source_quality"],"PASS")
    self.assertEqual(x["pipeline_gates"]["venue_original_first_publication"],"UNVERIFIED")
    self.assertFalse(x["ready_for_confirmatory_h1_h10"])
    self.assertFalse(x["ready_for_trading"])
 def test_no_automatic_trading(self):
    x=g.evaluate(valid())
    self.assertIn("TRADE_ORDER",x["forbidden_automatic_actions"])
    self.assertNotIn("TRADE_ORDER",x["permitted_automatic_actions"])
 def test_no_automatic_expense(self):
    self.assertIn("PAID_SUBSCRIPTION",g.evaluate(valid())["forbidden_automatic_actions"])
 def test_cannot_infer_original_pit_from_source_labels(self):
    x=valid()
    x["joint_oi_source"]["pit_release_timestamp"]="PASS"
    with self.assertRaises(ValueError):g.evaluate(x)
 def test_source_coverage_mask_changed_fails_closed(self):
    x=valid();x["joint_oi_source"]["joint_full_days"]=1750
    with self.assertRaises(ValueError):g.evaluate(x)
 def test_invalid_oi_gate_changed_fails_closed(self):
    x=valid();x["joint_oi_source"]["joint_excluded_days"]=0
    with self.assertRaises(ValueError):g.evaluate(x)
 def test_modified_source_schema_fails_closed(self):
    x=valid();x["joint_oi_source"]["schema"]="made-up"
    with self.assertRaises(ValueError):g.evaluate(x)
 def test_trading_enabled_source_fails_closed(self):
    x=valid();x["joint_oi_source"]["research_only"]=False
    with self.assertRaises(ValueError):g.evaluate(x)
 def test_numeric_source_window_must_not_expand(self):
    x=valid();x["joint_oi_source"]["data_cutoff_last_day"]="2026-10-20"
    with self.assertRaises(ValueError):g.evaluate(x)
 def test_readiness_is_deterministic(self):
    x=valid()
    self.assertEqual(g.assemble(x),g.assemble(x))
 def test_frozen_source_sha_present(self):
    for p in g.PINS.values():
      self.assertEqual(len(p["sha256"]),64)
      self.assertTrue(p["key"].endswith(".json"))
 def test_no_stealth_rights_promotion(self):
    r=g.assemble(valid())
    self.assertTrue(r["spot_futures_nav_pnl_reserve_limits_unchanged"])
    self.assertEqual(r["edge_status"],"EDGE_UNVALIDATED")
if __name__=="__main__":unittest.main()
