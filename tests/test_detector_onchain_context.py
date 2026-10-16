"""Onchain research adapter: metric taxonomy, provenance, timing and no-signal gates."""
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from detector_onchain_context import build, validate

NOW=1800000000000
ISO=lambda m:datetime.fromtimestamp(m/1000,timezone.utc).isoformat()
HASH="a"*64

def record(metric="BTC_SPENT_OUTPUT_AGE_1Y_3Y",scope="ALL_CHAIN_MOVEMENT",
           kind="SPENT_OUTPUT_AGE_BANDS",exchange=False):
    return {"asset":"BTC","metricId":metric,"scope":scope,"metricKind":kind,
            "sourceType":"PROVIDER_EXPORT","provider":"CryptoQuant",
            "metricUrl":"https://cryptoquant.com/asset/btc/chart/network-i",
            "rawSourceSha256":HASH,
            "windowStartUtc":ISO(NOW-25*3600000),
            "windowEndUtc":ISO(NOW-3600000),
            "availableAtUtc":ISO(NOW-3400000),
            "retrievedAtUtc":ISO(NOW-3300000),
            "valueBtc":13000.0,"rollingAverageDays":7,
            "isExchangeTagged":exchange}

class TestDetectorOnchain(unittest.TestCase):
    def test_empty_is_honest_no_data(self):
        o=build({"schemaVersion":"detector-onchain-observations-1.0","observations":[]},now_ms=NOW)
        self.assertEqual(o["sourceStatus"],"NO_DATA")
        self.assertFalse(o["observations"])
        self.assertTrue(o["notTradeApproval"])
        self.assertTrue(o["doNotRankCandidates"])
        self.assertIsNone(o["longShortDirection"])
        self.assertIsNone(o["signalStrength"])

    def test_spent_output_movement_is_not_exchange_flow(self):
        r,e=validate(record(),NOW)
        self.assertIsNone(e)
        self.assertEqual(r["scope"],"ALL_CHAIN_MOVEMENT")
        self.assertFalse(r["exchangeLabeled"])
        self.assertIn("NOT_EVIDENCE_OF_EXECUTED_SALE",r["interpretation"])

    def test_separate_exchange_inflow_age_cohort(self):
        entry=record(metric="BTC_EXCHANGE_INFLOW_AGE_1Y_3Y",
                    scope="EXCHANGE_DEPOSITS_ONLY",kind="EXCHANGE_INFLOW_AGE_BANDS",
                    exchange=True)
        res,err=validate(entry,NOW)
        self.assertIsNone(err)
        self.assertTrue(res["exchangeLabeled"])
        self.assertEqual(res["metricKind"],"EXCHANGE_INFLOW_AGE_BANDS")
        context=build({"schemaVersion":"detector-onchain-observations-1.0",
                       "observations":[record(),entry]},now_ms=NOW)
        self.assertEqual(context["sourceStatus"],"PROVIDER_REPORTED_CONTEXT_ONLY")
        self.assertEqual(len(context["separatedScopes"]),2)
        self.assertEqual(context["evidenceFamily"],"ONCHAIN_SUPPLY_MOVEMENT_ONE_FAMILY")
        self.assertIsNone(context["signalStrength"])

    def test_screen_capture_not_provider_export(self):
        x=record();x["sourceType"]="SCREENSHOT_UNVERIFIED"
        res,err=validate(x,NOW)
        self.assertIsNone(res)
        self.assertEqual(err,"SCREENSHOT_OR_UNVERIFIED_SOURCE")

    def test_no_backdated_published_or_future_data(self):
        x=record();x["availableAtUtc"]=ISO(NOW+3600000)
        self.assertEqual(validate(x,NOW)[1],"LOOKAHEAD_OR_UNORDERED_TIMESTAMPS")
        x=record();x["retrievedAtUtc"]=ISO(NOW-4*3600000)
        self.assertEqual(validate(x,NOW)[1],"LOOKAHEAD_OR_UNORDERED_TIMESTAMPS")
        x=record();x["windowEndUtc"]=ISO(NOW-100*3600000)
        x["windowStartUtc"]=ISO(NOW-124*3600000)
        x["availableAtUtc"]=ISO(NOW-99*3600000)
        x["retrievedAtUtc"]=ISO(NOW-98*3600000)
        self.assertEqual(validate(x,NOW)[1],"OLDER_THAN_ONCHAIN_CONTEXT_TTL")

    def test_no_scope_fraud_or_unknown_metric(self):
        x=record();x["isExchangeTagged"]=True
        self.assertEqual(validate(x,NOW)[1],"EXCHANGE_TAG_CONTRADICTION")
        x=record();x["scope"]="EXCHANGE_DEPOSITS_ONLY"
        self.assertEqual(validate(x,NOW)[1],"METRIC_SCOPE_OR_ASSET_MISMATCH")
        x=record();x["metricId"]="BTC_PRICE_SPOT"
        self.assertEqual(validate(x,NOW)[1],"UNRECOGNIZED_METRIC")

    def test_dont_guess_smoothing_or_allow_fake_url(self):
        x=record();x["rollingAverageDays"]=None
        self.assertEqual(validate(x,NOW)[1],"SMOOTHING_UNDECLARED")
        x=record();x["metricUrl"]="https://cryptoquant.com.attacker.example/q"
        self.assertEqual(validate(x,NOW)[1],"INVALID_PROVENANCE_URL")
        x=record();x["rawSourceSha256"]="NO_HASH"
        self.assertEqual(validate(x,NOW)[1],"SOURCE_SHA256_MISSING")

    def test_negative_netflow_only_when_metric_is_netflow(self):
        x=record(metric="BTC_EXCHANGE_NETFLOW",scope="EXCHANGE_NET_MOVEMENT",
                 kind="EXCHANGE_NETFLOW",exchange=True)
        x["valueBtc"]=-1200
        self.assertIsNone(validate(x,NOW)[1])
        x=record();x["valueBtc"]=-100
        self.assertEqual(validate(x,NOW)[1],"INVALID_BTC_VOLUME")

if __name__=="__main__":
    unittest.main()
