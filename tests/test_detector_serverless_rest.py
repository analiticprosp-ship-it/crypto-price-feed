import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from update_detector_rest_flow import taker_result, oi_result, one_symbol, build, P5

NOW=1800000000000
SYMBOL="SOL"
def taker_rows(n=8, gap=False):
    end=NOW-60_000  # most recent 5m candle should end before now
    last_start=(end//P5)*P5-P5
    rows=[]
    for k in range(n):
        t=last_start-(n-k-1)*P5
        rows.append({"timestamp":t,"buyVol":"2","sellVol":"1","buySellRatio":"2"})
    if gap:
        del rows[-2]
    return rows

def oi_fixture(stale=False):
    t=NOW-(30*60_000 if stale else P5)
    return {"retCode":0,"result":{"category":"linear","symbol":"SOLUSDT",
                                  "list":[{"timestamp":str(t),"openInterest":"110"},
                                          {"timestamp":str(t-15*60_000),"openInterest":"100"}]}}

class TestServerlessDetector(unittest.TestCase):
    def test_5m_15m_and_prior_window_are_real_aggregates(self):
        d=taker_result(taker_rows(),NOW)
        self.assertEqual(d["status"],"OBSERVED")
        self.assertEqual(d["window5m"]["deltaBase"],1)
        self.assertEqual(d["window15m"]["buyBase"],6)
        self.assertEqual(d["window15m"]["sellBase"],3)
        self.assertEqual(d["window15m"]["imbalance"],.333333)
        self.assertEqual(d["priorWindow15m"]["deltaBase"],3)
        self.assertTrue(d["notSpotFlow"])

    def test_missing_bar_blocks_complete_15m_claim(self):
        d=taker_result(taker_rows(gap=True),NOW)
        self.assertEqual(d["status"],"OBSERVED")
        self.assertIsNone(d["window15m"])

    def test_not_closed_not_counted(self):
        rows=taker_rows(6)
        rows.append({"timestamp":NOW-P5//2,"buyVol":"1000","sellVol":"1"})
        d=taker_result(rows,NOW)
        self.assertEqual(d["window5m"]["buyBase"],2)

    def test_stale_malformed_missing_and_negative_not_zero(self):
        self.assertEqual(taker_result([],NOW)["status"],"NO_DATA")
        self.assertEqual(taker_result("invalid",NOW)["status"],"NO_DATA")
        rows=taker_rows(1)
        rows[0]["timestamp"]=NOW-35*60_000
        self.assertEqual(taker_result(rows,NOW)["status"],"NO_DATA")
        rows=taker_rows(1)
        rows[0]["buyVol"]="-1"
        self.assertEqual(taker_result(rows,NOW)["status"],"NO_DATA")

    def test_explicit_zero_volume_not_conflated_with_missing(self):
        rows=taker_rows(1)
        rows[0]["buyVol"]="0"
        rows[0]["sellVol"]="0"
        d=taker_result(rows,NOW)
        self.assertEqual(d["status"],"OBSERVED")
        self.assertIsNone(d["window5m"]["imbalance"])

    def test_oi_observed_and_delta_same_venue(self):
        d=oi_result(oi_fixture(),SYMBOL,NOW)
        self.assertEqual(d["status"],"OBSERVED")
        self.assertEqual(d["deltaPct15m"],10.0)
        self.assertEqual(d["source"],"Bybit USDT linear")
        self.assertTrue(d["notTradeDirection"])

    def test_oi_old_mismatched_market_or_symbol_rejected(self):
        self.assertEqual(oi_result(oi_fixture(stale=True),SYMBOL,NOW)["status"],"NO_DATA")
        q=oi_fixture()
        q["result"]["symbol"]="BTCUSDT"
        self.assertEqual(oi_result(q,SYMBOL,NOW)["reason"],"SYMBOL_OR_MARKET_MISMATCH")
        q=oi_fixture()
        q["result"]["category"]="spot"
        self.assertEqual(oi_result(q,SYMBOL,NOW)["status"],"NO_DATA")
        self.assertEqual(oi_result({"retCode":10001},SYMBOL,NOW)["status"],"NO_DATA")

    def test_partial_sources_kept_explicitly_separate(self):
        def bad(_):raise TimeoutError()
        def good(_):return oi_fixture()
        result=one_symbol(SYMBOL,NOW,taker_fetch=bad,oi_fetch=good)
        self.assertEqual(result["taker"]["status"],"NO_DATA")
        self.assertEqual(result["taker"]["error"],"TimeoutError")
        self.assertEqual(result["openInterest"]["status"],"OBSERVED")

    def test_build_no_live_price_or_trade_authority(self):
        def t(_):return taker_rows()
        def o(_):return oi_fixture()
        data=build(["SOL"],NOW,taker_fetch=t,oi_fetch=o,max_workers=1)
        self.assertEqual(data["coverage"]["sourceObservationsValid"],2)
        self.assertTrue(data["notTradeApproval"])
        self.assertTrue(data["notSystemPrice"])
        self.assertTrue(data["notLiquidationStream"])
        self.assertNotIn("prices",data)

if __name__=="__main__":
    unittest.main()
