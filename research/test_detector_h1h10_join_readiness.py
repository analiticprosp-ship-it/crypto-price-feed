"""Offline anti-lookahead and source-clock parity tests."""
import copy
import unittest
from research.detector_h1h10_join_readiness import summarize,verify_inventory_local_and_r2

SHA="a"*64
DAYS=("2024-01-01","2024-04-01","2025-01-01","2025-07-01","2026-02-01","2026-09-01","2026-10-01")
SYMS=("BTCUSDT","ETHUSDT","SOLUSDT")
def sample():
    rows=[]
    for d in DAYS:
        for s in SYMS:
            rows.append({"date_start_utc":d,"date_end_utc":d,"symbol":s,
                "dataset":"open_interest_plus_last_price","market_type":"perpetual",
                "venue":"Binance USD-M via Tardis","time_basis":"vendor_receipt_asof_not_exchange_publication",
                "availability_status":"VENDOR_RECEIPT_VERIFIED_EXCHANGE_PUBLICATION_UNVERIFIED",
                "status":"VERIFIED_VENDOR_RECEIPT_ONLY",
                "source_sha256":SHA,"rows":288,"expected_rows":288,"missing_intervals":0})
    for d in ("2026-09-01","2026-09-02","2026-09-03"):
        for s in SYMS:
            for m in ("spot","perp"):
                rows.append({"date_start_utc":d,"date_end_utc":d,"symbol":s,
                    "dataset":"taker_aggtrades_5m","market_type":m,"venue":"Binance",
                    "time_basis":"trade_event_time_only_not_first_publication",
                    "availability_status":"AGGTRADES_PUBLICATION_UNVERIFIED",
                    "status":"VERIFIED_EVENT_TIME_ONLY",
                    "source_sha256":SHA,"rows":288,"expected_rows":288,"missing_intervals":0})
    return {"schema":"detector-h1h10-real-evidence-inventory-v1",
        "edge_status":"EDGE_UNVALIDATED","research_only":True,
        "trading_actions":False,"rows":rows}
class Guards(unittest.TestCase):
 def test_date_coincidences_do_not_qualify_as_causal(self):
    result=summarize(sample())
    self.assertEqual(result["vendor_oi_and_event_flow_date_coincidences"],6)
    self.assertEqual(result["overlap_dates_utc"],["2026-09-01"])
    self.assertEqual(result["clock_compatible_full_joint_asset_market_days"],0)
    self.assertEqual(result["causal_5m_features_eligible_for_locked_holdout"],0)
    self.assertFalse(result["holdout_and_model_training_authorized"])
 def test_missing_flow_5m_does_not_qualify(self):
    x=sample()
    x["rows"][-1]["missing_intervals"]=1
    self.assertEqual(summarize(x)["vendor_oi_and_event_flow_date_coincidences"],6)
    x["rows"][-6]["missing_intervals"]=1
    self.assertEqual(summarize(x)["vendor_oi_and_event_flow_date_coincidences"],5)
 def test_partial_oi_date_excluded(self):
    x=sample()
    x["rows"][15]["status"]="PARTIAL_VENDOR_RECEIPT_ONLY"
    self.assertEqual(summarize(x)["vendor_oi_and_event_flow_date_coincidences"],5)
 def test_event_time_claimed_as_publication_rejected(self):
    x=sample()
    x["rows"][-1]["time_basis"]="venue_exchange_release_pit"
    with self.assertRaisesRegex(ValueError,"FLOW_EVENT_VS_AVAILABILITY_CONFUSION"):summarize(x)
 def test_tardis_vendor_wrong_release_semantics_rejected(self):
    x=sample()
    x["rows"][0]["time_basis"]="exchange_first_release"
    with self.assertRaisesRegex(ValueError,"OI_AVAILABILITY_CLOCK_SEMANTICS_CHANGED"):summarize(x)
 def test_repeated_oi_rejected(self):
    x=sample()
    x["rows"][1]=copy.deepcopy(x["rows"][0])
    with self.assertRaisesRegex(ValueError,"DUPLICATE_OI_DAY_COIN"):summarize(x)
 def test_no_spot_perp_cross_market_mix(self):
    x=sample()
    x["rows"][-1]["market_type"]="other"
    with self.assertRaisesRegex(ValueError,"DUPLICATE_FLOW_OR_MARKET"):summarize(x)
 def test_trading_authority_cannot_be_claimed(self):
    x=sample();x["trading_actions"]=True
    with self.assertRaisesRegex(ValueError,"UNTRUSTED_OR_LIVE"):summarize(x)
 def test_bad_source_sha_is_not_accepted(self):
    x=sample();x["rows"][0]["source_sha256"]=""
    with self.assertRaisesRegex(ValueError,"SOURCE_HASH_MISSING"):summarize(x)
 def test_unsupported_coin_rejected(self):
    x=sample();x["rows"][0]["symbol"]="HYPEUSDT"
    with self.assertRaisesRegex(ValueError,"ROW_SYMBOL_OR_TYPE_INVALID"):summarize(x)
 def test_source_rows_must_be_complete(self):
    x=sample();x["rows"].pop()
    with self.assertRaisesRegex(ValueError,"SOURCE_ROW_COUNT_UNEXPECTED"):summarize(x)
 def test_repeated_flow_rejected(self):
    x=sample();x["rows"][-1]=copy.deepcopy(x["rows"][-2])
    with self.assertRaisesRegex(ValueError,"DUPLICATE_FLOW_OR_MARKET"):summarize(x)
if __name__=="__main__":unittest.main()
