"""Detector SHADOW fusion anti-lookahead, anti-double-count and no-data tests."""
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from detector_signal_engine import build,aligned_flow,oi_context,P5,P15

NOW=1800000000000
SYMBOL="SOL"
def iso(n):
    return datetime.fromtimestamp(n/1000,timezone.utc).isoformat()

def fixtures(direction="LONG"):
    t=NOW-P15
    if direction=="LONG":
        bar=dict(t=t,endMs=NOW,o=100.,h=103.,l=98.,c=102.,v=30.)
        prev=(1.,5.)
        curr=(5.,1.)
    else:
        bar=dict(t=t,endMs=NOW,o=100.,h=102.,l=97.,c=98.,v=30.)
        prev=(5.,1.)
        curr=(1.,5.)
    rows=[]
    for k in range(6):
        stamp=NOW-P15*2+k*P5
        buy,sell=prev if k<3 else curr
        rows.append(dict(startMs=stamp,endMs=stamp+P5,buyBase=buy,sellBase=sell))
    price={
        "schemaVersion":"1.0","generatedAt":iso(NOW-30000),
        "researchOnly":True,"notTradeApproval":True,
        "instruments":{
            SYMBOL:{
                "15m":{
                    "source":"OKX-primary","lastClosedOpen":t,
                    "lastClosedBar":bar,
                    "detectorFeatures":{
                        "status":"OHLCV_PROXY_ONLY",
                        "sourceBarClosedAt":NOW,"gapsInLast14":0,
                        "localStructure":{"sweptLowReclaimed":False,"sweptHighRejected":False}
                    },
                    "rsVsBTC":{"rsPctPoints":0.7}
                },
                "derivatives":{
                    "venue":"OKX","status":"PARTIAL","openInterest":{
                        "timestamp":NOW-60000,"deltaContractsPct15m":0.3,
                        "deltaContractsPct1h":0.7}
                }
            }
        }
    }
    flow={
        "schemaVersion":"detector-rest-flow-1.0",
        "generatedAt":iso(NOW-30000),
        "researchOnly":True,"notTradeApproval":True,"notSystemPrice":True,
        "instruments":{
            SYMBOL:{
                "taker":{
                    "status":"OBSERVED","source":"OKX USDT-SWAP contract taker history",
                    "instId":"SOL-USDT-SWAP","lastClosed5mEndMs":NOW,
                    "recentClosed5m":rows,
                    "window15m":{"imbalance":999.}, # must not be trusted for other windows
                },
                "openInterest":{"status":"NO_DATA"}
            }
        }
    }
    return price,flow

class TestDetectorFusion(unittest.TestCase):
    def test_early_long_requires_same_window_price_and_taker(self):
        a,b=fixtures()
        r=build(a,b,now_ms=NOW)
        self.assertTrue(r["dataGate"]["ok"])
        self.assertEqual(r["coverage"]["fullyAligned"],1)
        self.assertEqual(r["candidates"][0]["direction"],"LONG")
        self.assertEqual(r["instruments"]["SOL"]["LONG"]["status"],"EARLY_CANDIDATE_SHADOW")
        self.assertEqual(r["instruments"]["SOL"]["SHORT"]["status"],"NO_EDGE")
        self.assertEqual(r["instruments"]["SOL"]["flow"]["matchedEndMs"],NOW)
        self.assertEqual(r["instruments"]["SOL"]["flow"]["current"]["imbalance"],.666667)
        self.assertEqual(r["instruments"]["SOL"]["oi"]["status"],"ALIGNED_15M_OBSERVATION")

    def test_short_is_mirror_and_families_not_independent_votes(self):
        a,b=fixtures("SHORT")
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["candidates"][0]["direction"],"SHORT")
        x=r["instruments"]["SOL"]["SHORT"]
        self.assertEqual(set(x["families"]),{"PRICE_STRUCTURE","TAKER_VOLUME"})
        self.assertTrue(x["notIndependentStatisticalProof"])
        self.assertTrue(r["noValidatedProbability"])
        self.assertTrue(r["noExecutionLevels"])
        self.assertEqual(r["operationalStatus"],"SHADOW_ONLY_NO_TRADE_AUTHORITY")

    def test_no_exact_three_bars_no_signal(self):
        a,b=fixtures()
        del b["instruments"]["SOL"]["taker"]["recentClosed5m"][-2]
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["coverage"]["fullyAligned"],0)
        self.assertEqual(r["instruments"]["SOL"]["reason"],"NO_EXACT_3X5M_PRICE_WINDOW")
        self.assertEqual(r["candidates"],[])

    def test_never_join_different_venues_or_instruments(self):
        a,b=fixtures()
        b["instruments"]["SOL"]["taker"]["instId"]="BTC-USDT-SWAP"
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["instruments"]["SOL"]["reason"],"VENUE_OR_MARKET_MISMATCH")
        b["instruments"]["SOL"]["taker"]["instId"]="SOL-USDT-SWAP"
        b["instruments"]["SOL"]["taker"]["source"]="Binance USD-M perpetual"
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["instruments"]["SOL"]["reason"],"VENUE_OR_MARKET_MISMATCH")

    def test_later_taker_not_backcast_into_price_bar(self):
        a,b=fixtures()
        b["instruments"]["SOL"]["taker"]["recentClosed5m"]=b["instruments"]["SOL"]["taker"]["recentClosed5m"][-2:]
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["instruments"]["SOL"]["reason"],"NO_EXACT_3X5M_PRICE_WINDOW")
        self.assertFalse(r["candidates"])

    def test_stale_source_bar_and_future_source_prohibit_candidate(self):
        a,b=fixtures()
        a["generatedAt"]=iso(NOW-46*60*1000)
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["instruments"]["SOL"]["reason"],"PRICE_PUBLISH_STALE_OR_FUTURE")
        a,b=fixtures()
        a["instruments"]["SOL"]["15m"]["lastClosedBar"]["t"]-=P15
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["instruments"]["SOL"]["reason"],"PRICE_15M_STALE_OR_TIME_MISMATCH")
        a,b=fixtures()
        b["generatedAt"]=iso(NOW+10_000)
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["dataGate"]["reason"],"TAKER_PUBLISH_STALE_OR_FUTURE")

    def test_oi_never_fabricates_time_sync_or_direction(self):
        a,b=fixtures()
        a["instruments"]["SOL"]["derivatives"]["openInterest"]["timestamp"]=NOW+30_000
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["instruments"]["SOL"]["oi"]["status"],"POST_PRICE_BAR_CONTEXT_ONLY")
        self.assertFalse(r["instruments"]["SOL"]["oi"]["confirm15m"])
        self.assertIsNone(r["instruments"]["SOL"]["oi"]["fifteenMinuteDeltaContractsPct"])
        self.assertEqual(r["instruments"]["SOL"]["LONG"]["status"],"EARLY_CANDIDATE_SHADOW")
        a,b=fixtures()
        a["instruments"]["SOL"]["derivatives"]["openInterest"]["deltaContractsPct15m"]=None
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["instruments"]["SOL"]["oi"]["status"],"ONE_HOUR_OR_UNALIGNED_CONTEXT_ONLY")
        self.assertFalse(r["instruments"]["SOL"]["oi"]["confirm15m"])
        a,b=fixtures()
        del a["instruments"]["SOL"]["derivatives"]
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["instruments"]["SOL"]["oi"]["status"],"NO_DATA")
        self.assertEqual(r["instruments"]["SOL"]["LONG"]["status"],"EARLY_CANDIDATE_SHADOW")

    def test_duplicate_5m_and_invalid_quantity_veto(self):
        a,b=fixtures()
        z=b["instruments"]["SOL"]["taker"]["recentClosed5m"]
        z.append(dict(z[-1]))
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["instruments"]["SOL"]["reason"],"DUPLICATE_5M_BAR")
        a,b=fixtures()
        b["instruments"]["SOL"]["taker"]["recentClosed5m"][0]["buyBase"]=-10
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["instruments"]["SOL"]["reason"],"INVALID_5M_QUANTITY")

    def test_unknown_symbol_gets_no_data_not_fake_rank(self):
        a,b=fixtures()
        a["instruments"]["AVAX"]={"15m":None}
        b["instruments"]["HYPE"]={"taker":{"status":"NO_DATA"}}
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["coverage"]["symbols"],3)
        self.assertEqual(r["coverage"]["unavailable"],2)
        self.assertEqual(r["instruments"]["AVAX"]["reason"],"PRICE_15M_NOT_MONITORED")
        self.assertEqual(r["instruments"]["HYPE"]["reason"],"PRICE_15M_NOT_MONITORED")

    def test_missing_ohlcv_source_data_never_voted_by_rs_alone(self):
        a,b=fixtures()
        a["instruments"]["SOL"]["15m"]["detectorFeatures"]["status"]="GAPPED_HISTORY"
        r=build(a,b,now_ms=NOW)
        self.assertEqual(r["instruments"]["SOL"]["reason"],"PRICE_STRUCTURE_UNVERIFIED")
        self.assertEqual(r["coverage"]["shadowCandidates"],0)

if __name__=="__main__":
    unittest.main()
