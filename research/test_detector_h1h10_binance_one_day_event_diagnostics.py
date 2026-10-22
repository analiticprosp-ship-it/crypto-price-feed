"""Source-pin and no-PIT-promotion tests for H1 H6 H7 single-day diagnostics."""
import csv
import datetime as dt
import hashlib
import io
import unittest
import zipfile

from research.detector_h1h10_binance_one_day_event_diagnostics import (
    DAY, PRICE_PIN, FLOW_PIN, build, diagnostics, future_returns,
    kline_closes, pearson, read_flow_5m,
)

START=int(dt.datetime.fromisoformat(DAY+"T00:00:00+00:00").timestamp()*1000)
SYMS=("BTCUSDT","ETHUSDT","SOLUSDT")


def kline_bytes(market,sym):
    scale=1000 if market=="spot" else 1
    rows=[]
    for i in range(288):
        op=(START+i*300000)*scale
        end=(START+(i+1)*300000)*scale-1
        close=100 + i/10 + (i%9)/1000
        rows.append(",".join(map(str,(op,close,close+1,close-1,close,1,end,100,1,1,1,0))))
    if market=="spot":
        rows.insert(0,"open_time,open,high,low,close,volume,close_time,quote,number,trades,base,ignore")
    output=io.BytesIO()
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED) as f:
        f.writestr(f"{sym}-5m-{DAY}.csv","\n".join(rows)+"\n")
    return output.getvalue()


def flow_bytes(missing=None, shifted=False):
    out=io.StringIO(newline="")
    writer=csv.DictWriter(out,fieldnames=[
        "bucket_start_utc","aggtrade_count","taker_buy_base","taker_sell_base",
        "taker_buy_quote_usdt","taker_sell_quote_usdt",
        "net_taker_quote_usdt","total_quote_usdt","availability"])
    writer.writeheader()
    for i in range(288):
        if i==missing:continue
        t=START+300000*i+(1000 if shifted and i==3 else 0)
        writer.writerow({"bucket_start_utc":dt.datetime.fromtimestamp(t/1000,dt.timezone.utc).isoformat(),
                         "aggtrade_count":10,"taker_buy_base":2,"taker_sell_base":1,
                         "taker_buy_quote_usdt":200,"taker_sell_quote_usdt":100,
                         "net_taker_quote_usdt":100,"total_quote_usdt":300,
                         "availability":"EVENT_TIME_ONLY_FIRST_PUBLICATION_UNVERIFIED"})
    return out.getvalue().encode()


def fixtures():
    prices=[]
    flows=[]
    payload={}
    for market in ("spot","um"):
        for symbol in SYMS:
            original=kline_bytes(market,symbol)
            key=f"research/test-price-{market}-{symbol}.zip"
            payload[key]=original
            prices.append({"market":market,"symbol":symbol,"rows":288,
                           "source_time_basis":"BAR_OPEN_NOT_ORIGINAL_PUBLICATION",
                           "r2_object_key":key,"publisher_sha256":hashlib.sha256(original).hexdigest()})
        for symbol in SYMS[:2]:
            original=io.BytesIO()
            with zipfile.ZipFile(original,"w") as z:z.writestr("dummy.txt","has original SHA")
            data=original.getvalue()
            flow=flow_bytes()
            raw_key=f"research/test-flow-{market}-{symbol}.zip"
            derived_key=f"research/test-derived-{market}-{symbol}.csv"
            payload[raw_key]=data;payload[derived_key]=flow
            flows.append({"market":market,"symbol":symbol,
                          "status":"PUBLISHER_SHA_AND_SOURCE_EVENT_VERIFIED",
                          "raw_r2_key":raw_key,"derived_r2_key":derived_key,
                          "publisher_sha256":hashlib.sha256(data).hexdigest(),
                          "derived_sha256":hashlib.sha256(flow).hexdigest(),
                          "five_minute_slots_with_trades":288,
                          "causal_rows_authorized":0,
                          "historical_original_publication_time":"UNVERIFIED"})
    price_doc={"downloaded_verified_5m_price_archives":6,"historical_causal_pit":"BLOCKED",
               "locked_holdout_used":False,"verified_kline_samples":prices}
    flow_doc={"verified_zip_count":4,"utc_day":DAY,
              "historical_exchange_release_pit":"BLOCKED","locked_holdout_consumed":False,
              "files":flows}
    def load(key,expected,size_cap):
        value=payload[key]
        if hashlib.sha256(value).hexdigest()!=expected or len(value)>size_cap:
            raise ValueError("WRONG_SHA")
        return value
    return price_doc,flow_doc,load


class OneDayOnly(unittest.TestCase):
    def test_build_exact_four_flow_sources_and_two_h6_coin_pairs(self):
        a,b,load=fixtures()
        report=build(a,b,load)
        self.assertEqual(report["complete_price_asset_market_sources"],6)
        self.assertEqual(report["flow_asset_market_sources"],4)
        self.assertEqual({s for s,v in report["h6_spot_perp_same_coin"].items()
                          if v["status"]=="MATCHED_EVENT_LABELS_ONLY"},set(SYMS[:2]))
        self.assertEqual(report["independent_days"],1)
        self.assertFalse(report["training_authorized"])
        self.assertEqual(report["causal_h1_h6_h7_rows_authorized"],0)
        self.assertEqual(report["preregistered_h1_h6_h7_confirmatory"],"BLOCKED")
        for source in report["h1_h7_single_venue_flow_price"].values():
            self.assertEqual(source["event_only_diagnostics"]["15m"]["event_only_sample_count"],284)
            self.assertEqual(source["event_only_diagnostics"]["60m"]["event_only_sample_count"],275)

    def test_future_outcomes_are_censored_within_single_utc_day(self):
        close=[100+0.1*i for i in range(288)]
        flow={i:{"imbalance":0.1} for i in range(288)}
        self.assertEqual(len(future_returns(close,flow,3)),284)
        self.assertEqual(len(future_returns(close,flow,12)),275)
        self.assertNotIn(285,future_returns(close,flow,3))
        self.assertNotIn(287,future_returns(close,flow,12))

    def test_no_data_synthesis_across_missing_flow_bucket(self):
        rows=read_flow_5m(flow_bytes(missing=5))
        self.assertEqual(len(rows),287)
        self.assertNotIn(5,rows)
        stats=diagnostics([100+i/10 for i in range(288)],rows)
        self.assertEqual(stats["quality"]["missing_flow_slots"],1)
        self.assertEqual(stats["event_only_diagnostics"]["15m"]["event_only_sample_count"],283)

    def test_bad_5m_alignment_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"DERIVED_FLOW_CLOCK"):
            read_flow_5m(flow_bytes(shifted=True))

    def test_pearson_insufficient_and_constant_has_no_fake_significance(self):
        self.assertIsNone(pearson([(1,1),(2,2)]))
        self.assertIsNone(pearson([(1,2),(1,3),(1,4)]))
        self.assertAlmostEqual(pearson([(1,1),(2,2),(3,3)]),1.)

    def test_source_pit_promotion_is_rejected(self):
        a,b,load=fixtures()
        b["files"][0]["causal_rows_authorized"]=1
        with self.assertRaisesRegex(ValueError,"FLOW_HISTORICAL_PIT_PROMOTED"):
            build(a,b,load)

    def test_future_holdout_marked_used_fails(self):
        a,b,load=fixtures()
        b["locked_holdout_consumed"]=True
        with self.assertRaisesRegex(ValueError,"SOURCE_REPORT_COVERAGE_OR_PIT"):
            build(a,b,load)

    def test_source_price_file_sha_mismatch_fails_closed(self):
        a,b,load=fixtures()
        a["verified_kline_samples"][0]["publisher_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"WRONG_SHA"):
            build(a,b,load)

    def test_source_unverified_flow_missing_is_failure_not_zero_filled(self):
        a,b,load=fixtures()
        b["files"][0]["status"]="SOURCE_VERIFICATION_FAILED"
        with self.assertRaisesRegex(ValueError,"INVALID_FLOW_SOURCE_VERIFICATION"):
            build(a,b,load)

    def test_no_cash_trading_profitable_or_pvalues_in_report(self):
        a,b,load=fixtures()
        obj=build(a,b,load)
        self.assertEqual(obj["interpretation"],"PRELIMINARY_DESCRIPTIVE_SINGLE_PRE_HOLDOUT_DAY")
        for horizon in obj["h6_spot_perp_same_coin"][SYMS[0]]["event_only_diagnostics"].values():
            self.assertEqual(horizon["statistical_significance"],"NOT_TESTED_SINGLE_DAY")
            self.assertEqual(horizon["predictive_claim"],"PROHIBITED")
        self.assertFalse(obj["trading_actions"])


if __name__=="__main__":
    unittest.main()
