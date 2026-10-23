"""Fail-closed exact Jan21 selected falling BTC prior-only source proof."""
import hashlib
import unittest
from research.detector_h1h10_selected_falling_jan21_flow import (
    DAY, PRIOR_SELECTION_PIN, confirm_selection, run
)
from research.test_detector_h1h10_regime_prewindow_three_dates import (
    synthetic_zip
)


def selected():
    return {"schema":PRIOR_SELECTION_PIN["schema"],"scope":"RESEARCH_ONLY",
        "selection":{"selected_date":DAY,"selection_status":"FIRST_PREDECLARED_FALLING_PREWINDOW"},
        "observed_candidates":[{"day":DAY,"status":"VERIFIED",
            "classification":{"day":DAY,"is_falling":True,"seven_day_prior_return":-.0736740371}}],
        "selected_day_aggtrades_downloaded":0,
        "selection_uses_eth_sol_flow":False,
        "locked_holdout_accessed":False,
        "causal_joint_rows_authorized":0,
        "trading_actions":False}


def loader(url,method,cap):
    market="um" if "/futures/um/" in url else "spot"
    kind="aggTrades" if "/aggTrades/" in url else "klines"
    symbol="ETHUSDT" if "/ETHUSDT/" in url else "SOLUSDT"
    raw=synthetic_zip(DAY,kind,market,symbol)
    if method=="HEAD":return {"http":200,"bytes":len(raw)}
    if url.endswith(".CHECKSUM"):
        return (hashlib.sha256(raw).hexdigest()+"  "+url.rsplit("/",1)[-1].removesuffix(".CHECKSUM")).encode()
    return raw


def writer(_s3,_bucket,key,body):
    return hashlib.sha256(body).hexdigest()


class SelectedFallingOnly(unittest.TestCase):
    def test_exact_prior_pin_required(self):
        v=selected()
        self.assertTrue(confirm_selection(v)["is_falling"])
        v["selection"]["selected_date"]="2026-02-04"
        with self.assertRaisesRegex(ValueError,"JAN21_BTC_SELECTION"):
            confirm_selection(v)

    def test_cannot_select_when_flow_used_to_choose_date(self):
        v=selected();v["selection_uses_eth_sol_flow"]=True
        with self.assertRaisesRegex(ValueError,"JAN21_BTC_SELECTION"):
            confirm_selection(v)

    def test_incomplete_earlier_price_selection_not_accepted(self):
        v=selected();v["observed_candidates"][0]["status"]="DATA_MISSING"
        with self.assertRaisesRegex(ValueError,"JAN21_BTC_SELECTION"):
            confirm_selection(v)

    def test_no_holdout_promotion(self):
        v=selected();v["locked_holdout_accessed"]=True
        with self.assertRaisesRegex(ValueError,"JAN21_BTC_SELECTION"):
            confirm_selection(v)

    def test_complete_original_flow_and_price_but_zero_causal_authority(self):
        report=run(object(),"bucket","998451","1",loader,writer,selected())
        self.assertEqual(report["status"],"COMPLETE_FALLING_EVENT_ONLY")
        self.assertEqual(report["verified_aggtrades"],1152)
        self.assertEqual(report["verified_5m_event_slots"],1152)
        self.assertEqual(len(report["source_files"]),4)
        self.assertEqual(len(report["h1_h6_h7_exploratory"]["matched_spot_perp_coins"]),2)
        self.assertEqual(report["causal_joint_rows_authorized"],0)
        self.assertFalse(report["trading_actions"])
        self.assertEqual(report["confirmatory_h1_h6_h7"],"BLOCKED")

    def test_corrupt_futures_trade_checksum_stops_joint_analysis(self):
        def corrupt(u,m,cap):
            if "/um/daily/aggTrades/SOLUSDT/" in u and u.endswith(".CHECKSUM"):
                return ("0"*64+"  "+u.rsplit("/",1)[-1].removesuffix(".CHECKSUM")).encode()
            return loader(u,m,cap)
        report=run(object(),"bucket","998452","1",corrupt,writer,selected())
        self.assertEqual(report["status"],"INCOMPLETE_NO_JOIN")
        self.assertIsNone(report["h1_h6_h7_exploratory"])
        self.assertEqual(len(report["failed_source_files"]),1)
        self.assertEqual(report["causal_joint_rows_authorized"],0)


if __name__=="__main__":
    unittest.main()
