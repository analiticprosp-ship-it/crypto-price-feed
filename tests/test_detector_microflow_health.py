import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from check_detector_microflow import validate

NOW=1800000000000

def iso(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()

def snapshot(age=20, trade_status="OBSERVED", coverage=1.0):
    block={"status":trade_status,"coverageRatio":coverage,
           "data":{"count":3,"deltaNotional":120.0} if trade_status=="OBSERVED" else None}
    return {"schemaVersion":"detector-microflow-pilot-0.1",
            "generatedAt":iso(NOW-age*1000),
            "lastCompleteMinuteEndMs":NOW-60_000,
            "researchOnly":True,"notTradeApproval":True,
            "notSystemPrice":True,"notForPricingOrNAV":True,
            "streams":{
                "spot":{"SOLUSDT":{"taker_trade":{"1m":dict(block)}},
                        "SUIUSDT":{"taker_trade":{"1m":dict(block)}}},
                "linear":{"SOLUSDT":{"taker_trade":{"1m":dict(block)}},
                          "SUIUSDT":{"taker_trade":{"1m":dict(block)}}},
            }}

class TestDetectorHealth(unittest.TestCase):
    def check(self, obj, mode="liveness"):
        return validate(obj,now_ms=NOW,mode=mode)

    def test_valid_live_and_ready(self):
        self.assertTrue(self.check(snapshot())["ok"])
        self.assertTrue(self.check(snapshot(),"readiness")["ok"])

    def test_old_or_future_stamp_does_not_pass(self):
        self.assertIn("STALE_OR_FUTURE_SNAPSHOT",self.check(snapshot(age=120))["errors"])
        self.assertIn("STALE_OR_FUTURE_SNAPSHOT",self.check(snapshot(age=-10))["errors"])

    def test_missing_stream_cannot_claim_healthy(self):
        obj=snapshot()
        del obj["streams"]["linear"]["SOLUSDT"]
        self.assertIn("SYMBOL_MISSING_linear.SOLUSDT",self.check(obj)["errors"])

    def test_warmup_live_not_ready(self):
        obj=snapshot(trade_status="NO_DATA_GAPPED_OR_WARMUP",coverage=.7)
        self.assertTrue(self.check(obj,"liveness")["ok"])
        self.assertFalse(self.check(obj,"readiness")["ok"])
        self.assertTrue(any("NO_TRADE_READINESS" in x for x in self.check(obj,"readiness")["errors"]))

    def test_unverified_silent_trade_topic_is_not_ready(self):
        obj=snapshot(trade_status="NO_TRADE_EVENTS_UNVERIFIED",coverage=1.)
        self.assertTrue(self.check(obj,"liveness")["ok"])
        self.assertFalse(self.check(obj,"readiness")["ok"])

    def test_fake_observed_with_zero_is_invalid(self):
        obj=snapshot()
        obj["streams"]["linear"]["SOLUSDT"]["taker_trade"]["1m"]["data"]["count"]=0
        self.assertIn("INVALID_OBSERVED_FLOW_linear.SOLUSDT",self.check(obj)["errors"])

    def test_missing_flag_or_non_null_unknown_is_invalid(self):
        obj=snapshot(trade_status="NO_TRADE_EVENTS_UNVERIFIED")
        obj["streams"]["spot"]["SOLUSDT"]["taker_trade"]["1m"]["data"]={"count":0}
        obj["notSystemPrice"]=False
        r=self.check(obj)
        self.assertFalse(r["ok"])
        self.assertIn("MISSING_RESEARCH_ONLY_GUARD_notSystemPrice",r["errors"])
        self.assertIn("MISSING_DATA_NOT_NULL_spot.SOLUSDT",r["errors"])

    def test_no_zero_freshness_on_unparseable_timestamp(self):
        obj=snapshot()
        obj["generatedAt"]="nonsense"
        self.assertIn("INVALID_GENERATED_AT",self.check(obj)["errors"])

    def test_window_too_old_fails_even_with_recent_filename(self):
        obj=snapshot()
        obj["lastCompleteMinuteEndMs"]=NOW-600_000
        self.assertIn("UNUSABLE_CLOSED_WINDOW",self.check(obj)["errors"])

if __name__=="__main__":
    unittest.main()
