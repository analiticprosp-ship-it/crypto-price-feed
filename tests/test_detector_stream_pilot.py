import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from detector_stream_pilot import EventStore, MINUTE, parse_events

NOW=1800000000000  # divisible by minute (closed-window fixture)
SYMBOLS={"SOLUSDT","SUIUSDT"}

def trade(ts, ident="t1", side="Buy", sym="SOLUSDT", price="100", qty="2"):
    return {"topic":f"publicTrade.{sym}","data":[
        {"T":ts,"s":sym,"S":side,"p":price,"v":qty,"i":ident}]}

def liquidation(ts, side="Buy", sym="SOLUSDT"):
    return {"topic":f"allLiquidation.{sym}","data":[
        {"T":ts,"s":sym,"S":side,"p":"90","v":"3"}]}

class TestDetectorStreamPilot(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=EventStore(Path(self.tmp.name)/"events.sqlite")
    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()
    def test_side_and_notional_for_trades(self):
        e=parse_events(trade(NOW-2000),market="linear",allowed=SYMBOLS,received_ms=NOW)
        self.assertEqual(len(e),1)
        self.assertEqual(e[0][1],"taker_trade")
        self.assertEqual(e[0][5],"Buy")
        self.assertEqual(e[0][7],200)
    def test_side_for_liquidation_is_position_side(self):
        e=parse_events(liquidation(NOW-3000),market="linear",allowed=SYMBOLS,received_ms=NOW)
        self.assertEqual(e[0][1],"liquidation")
        self.assertEqual(e[0][5],"Buy")
        self.assertEqual(len(parse_events(liquidation(NOW-3000),market="spot",
                                          allowed=SYMBOLS,received_ms=NOW)),0)
    def test_no_wrong_symbol_topic_or_invalid_price(self):
        self.assertEqual(parse_events(trade(NOW-1000,sym="BTCUSDT"),market="spot",
                         allowed=SYMBOLS,received_ms=NOW),[])
        bad=trade(NOW-1000,price="-1")
        self.assertEqual(parse_events(bad,market="spot",allowed=SYMBOLS,received_ms=NOW),[])
        bad=trade(NOW-1000)
        bad['data'][0]['s']="ETHUSDT"
        self.assertEqual(parse_events(bad,market="spot",allowed=SYMBOLS,received_ms=NOW),[])
    def test_future_old_and_missing_trade_id_rejected(self):
        for ts in (NOW+6000,NOW-121000):
            self.assertEqual(parse_events(trade(ts),market="spot",
                         allowed=SYMBOLS,received_ms=NOW),[])
        pkt=trade(NOW-2000)
        del pkt['data'][0]['i']
        self.assertEqual(parse_events(pkt,market="spot",allowed=SYMBOLS,
                                      received_ms=NOW),[])
    def test_duplicate_events_are_not_counted_twice(self):
        events=parse_events(trade(NOW-1000),market="spot",allowed=SYMBOLS,received_ms=NOW)
        self.assertEqual(self.store.ingest(events),1)
        self.assertEqual(self.store.ingest(events),0)
        self.assertEqual(self.store.stats("spot","taker_trade","SOLUSDT",NOW-MINUTE,NOW)["count"],1)
    def test_zero_not_fabricated_while_warming_up(self):
        self.store.subscribe_confirmed("spot",NOW-30_000)
        snap=self.store.snapshot(["SOLUSDT"],at=NOW)
        w=snap["streams"]["spot"]["SOLUSDT"]["taker_trade"]["1m"]
        self.assertEqual(w["status"],"NO_DATA_GAPPED_OR_WARMUP")
        self.assertIsNone(w["data"])
        self.assertEqual(w["coverageRatio"],0.5)
    def test_full_coverage_zeros_legitimate_and_windows_are_closed(self):
        self.store.subscribe_confirmed("spot",NOW-17*MINUTE)
        self.store.subscribe_confirmed("linear",NOW-17*MINUTE)
        es=parse_events(trade(NOW-1_000),market="spot",allowed=SYMBOLS,received_ms=NOW)
        self.store.ingest(es)
        snap=self.store.snapshot(["SOLUSDT"],at=NOW)
        spot=snap["streams"]["spot"]["SOLUSDT"]["taker_trade"]
        self.assertEqual(spot["1m"]["status"],"OBSERVED")
        self.assertEqual(spot["5m"]["data"]["deltaNotional"],200)
        perp=snap["streams"]["linear"]["SOLUSDT"]["liquidation"]["15m"]
        self.assertEqual(perp["status"],"OBSERVED")
        self.assertEqual(perp["data"]["count"],0)
        self.assertIsNone(perp["data"]["deltaNotional"])
        self.assertEqual(snap["lastCompleteMinuteEndMs"],NOW)
        self.assertTrue(snap["notTradeApproval"])
    def test_no_trade_event_does_not_prove_zero_taker_flow(self):
        self.store.subscribe_confirmed("spot",NOW-16*MINUTE)
        snap=self.store.snapshot(["SOLUSDT"],at=NOW)
        block=snap["streams"]["spot"]["SOLUSDT"]["taker_trade"]["15m"]
        self.assertEqual(block["status"],"NO_TRADE_EVENTS_UNVERIFIED")
        self.assertIsNone(block["data"])

    def test_connection_gap_blocks_missing_window(self):
        self.store.subscribe_confirmed("linear",NOW-120_000)
        self.store.disconnected("linear",NOW-90_000)
        self.store.subscribe_confirmed("linear",NOW-70_000)
        snap=self.store.snapshot(["SOLUSDT"],at=NOW)
        block=snap["streams"]["linear"]["SOLUSDT"]["taker_trade"]["1m"]
        self.assertEqual(block["status"],"OBSERVED")
        self.assertEqual(snap["streams"]["linear"]["SOLUSDT"]["taker_trade"]["5m"]["status"],
                         "NO_DATA_GAPPED_OR_WARMUP")
    def test_liquidation_dedup_and_price_quality(self):
        e=parse_events(liquidation(NOW-2000),market="linear",allowed=SYMBOLS,received_ms=NOW)
        self.assertEqual(self.store.ingest(e),1)
        self.assertEqual(self.store.ingest(e),0)
        data=self.store.stats("linear","liquidation","SOLUSDT",NOW-MINUTE,NOW)
        self.assertEqual(data["count"],1)
        self.assertEqual(data["sideMeaning"],"POSITION_SIDE_BUY_IS_LIQUIDATED_LONG")
        self.assertIn("BANKRUPTCY_PRICE",data["notionalQuality"])
    def test_market_data_is_not_mixed(self):
        e=parse_events(trade(NOW-1000),market="linear",allowed=SYMBOLS,received_ms=NOW)
        self.store.ingest(e)
        self.assertEqual(self.store.stats("spot","taker_trade","SOLUSDT",NOW-MINUTE,NOW)["count"],0)
        self.assertEqual(self.store.stats("linear","taker_trade","SOLUSDT",NOW-MINUTE,NOW)["count"],1)

if __name__=="__main__":
    unittest.main()
