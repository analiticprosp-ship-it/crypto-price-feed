"""Data-contract tests for public indicators table: never fake freshness/signals."""
import unittest
from datetime import datetime,timezone
from scripts.build_indicators_technical_table import (
    HOUR, P5, build, observed_oi, observed_taker, observed_nw, quality,
)
NOW=1_800_000_000_000
END=(NOW//P5)*P5-P5
STAMP=lambda t:datetime.fromtimestamp(t/1000,timezone.utc).isoformat()


def flow(end=END):
    return {"status":"OBSERVED","source":"OKX USDT-SWAP contract taker history",
            "recentClosed5m":[
                {"startMs":end-HOUR+i*P5,"endMs":end-HOUR+(i+1)*P5,
                 "buyBase":120,"sellBase":80}
                for i in range(12)]}


class TestIndicatorTable(unittest.TestCase):
    def test_freshness_exact_and_stale(self):
        self.assertEqual(quality(NOW-15*60000,NOW,15*60000),"FRESH")
        self.assertEqual(quality(NOW-16*60000,NOW,15*60000),"STALE")
        self.assertEqual(quality(NOW+60001,NOW,15*60000),"NO_TIMESTAMP")

    def test_completed_hour_and_gap(self):
        r=observed_taker({'taker':flow()},NOW)
        self.assertEqual(r["status"],"FRESH")
        self.assertEqual(r["imbalancePct"],20)
        self.assertEqual(r["closedBars"],12)
        s=flow(); s["recentClosed5m"].pop(5)
        self.assertEqual(observed_taker({'taker':s},NOW)["reason"],"GAPPED_1H_5M_BARS")
        old=observed_taker({'taker':flow(END-2*HOUR)},NOW)
        self.assertEqual(old["status"],"STALE")
        self.assertEqual(old["imbalancePct"],20)
        self.assertEqual(observed_taker({},NOW)["status"],"NO_DATA")

    def test_oi_keeps_stale_as_historical_not_live(self):
        d={"derivatives":{"openInterest":{"timestamp":NOW-40000,
                                          "deltaContractsPct1h":-0.9321}}}
        self.assertEqual(observed_oi(d,NOW)["status"],"FRESH")
        stale=observed_oi(d,NOW+30*60000)
        self.assertEqual(stale["status"],"STALE")
        self.assertEqual(stale["deltaContractsPct1h"],-0.9321)
        self.assertEqual(observed_oi({},NOW)["status"],"NO_DATA")

    def test_nw_not_promoted_to_luxalgo(self):
        d={"4H":{"status":"MODEL_OBSERVED_UNVERIFIED_PARITY",
                 "barClosedAtMs":NOW-60*60000,"center":99.3,
                 "upper":105.3,"lower":93.3,
                 "centerDirection":"DOWN",
                 "priceLocation":"IN_CHANNEL_BELOW_CENTER"}}
        x=observed_nw(d,NOW)
        self.assertEqual(x["4H"]["status"],"MODEL_OBSERVED_UNVERIFIED_PARITY")
        self.assertTrue(x["4H"]["notOriginalLuxAlgo"])
        self.assertEqual(x["1H"]["status"],"NO_DATA")

    def test_no_data_cannot_trigger_trade(self):
        out=build({}, {}, {}, {}, NOW)
        b=out["table"]["BTC"]
        self.assertEqual(b["price"]["status"],"NO_DATA")
        self.assertEqual(b["oi1h"]["status"],"NO_DATA")
        self.assertEqual(b["perpTaker1h"]["status"],"NO_DATA")
        self.assertEqual(b["nadarayaWatson"]["4H"]["status"],"NO_DATA")
        self.assertEqual(b["pifagorMFI"]["status"],"NOT_CONNECTED")
        self.assertEqual(b["bigGuyBurjKhalifa"]["status"],"NOT_CONNECTED")
        self.assertFalse(b["tradeAuthority"])
        self.assertTrue(out["noTradeApproval"])

    def test_integrated_rows_preserve_source_times(self):
        q={"generatedAt":STAMP(NOW-50000),
           "spot":{"quotes":[{"symbol":"BTC","ok":True,
                               "freshSourceCount":2,"systemPrice":82000}]}}
        oi={"generatedAt":STAMP(NOW-50000),
            "instruments":{"BTC":{"derivatives":{"openInterest":{
                "timestamp":NOW-50000,"deltaContractsPct1h":0.55}}}}}
        rest={"generatedAt":STAMP(NOW-50000),
              "instruments":{"BTC":{"taker":flow()}}}
        nw={"generatedAt":STAMP(NOW-50000),
            "instruments":{"BTC":{"4H":{
                "status":"MODEL_OBSERVED_UNVERIFIED_PARITY",
                "barClosedAtMs":NOW-2*HOUR,
                "center":82000,"upper":84000,"lower":80000}}}}
        x=build(q,oi,rest,nw,NOW)
        b=x["table"]["BTC"]
        self.assertEqual(b["price"]["status"],"FRESH")
        self.assertEqual(b["oi1h"]["deltaContractsPct1h"],0.55)
        self.assertEqual(b["perpTaker1h"]["imbalancePct"],20)
        self.assertEqual(b["nadarayaWatson"]["4H"]["status"],
                         "MODEL_OBSERVED_UNVERIFIED_PARITY")
        self.assertEqual(b["convergence"],
                         "UNVERIFIED_NO_ORIGINAL_PIFAGOR_AND_NO_SYNCHRONOUS_FULL_EVIDENCE")
        self.assertFalse(b["tradeAuthority"])


if __name__=="__main__":
    unittest.main()
