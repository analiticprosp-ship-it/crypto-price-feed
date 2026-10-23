"""H1H10 three-date prior-week regime gates and exact source-clock invariants."""
import datetime as dt
import hashlib
import io
import unittest
import zipfile
from unittest import mock

from research.detector_h1h10_regime_prewindow_three_dates import (
    PRECOMMITTED_DATES, SOURCE_ALLOWLIST, ROOT,
    choose_day, lead_dates, regime_prior_week, source_url,
    join, run
)

DAY="2026-02-18"


def synthetic_zip(day,kind,market,symbol):
    begin=int(dt.datetime.fromisoformat(day+"T00:00:00+00:00").timestamp()*1000)
    scale=1000 if market=="spot" else 1
    if kind=="aggTrades":
        header="agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n"
        data=header+"".join(
            f"{i},100,2,{i*2},{i*2+1},{(begin+i*300000+1500)*scale},{'false' if i%2==0 else 'true'}\n"
            for i in range(288))
        name=f"{symbol}-aggTrades-{day}.csv"
    else:
        header="open_time,open,high,low,close,volume,close_time,quote_asset_volume,number_of_trades,taker_buy_base_asset_volume,taker_buy_quote_asset_volume,ignore\n"
        data=header+"".join(
            f"{(begin+i*300000)*scale},{100+i*.1},200,50,{100+i*.1},2,{(begin+(i+1)*300000)*scale-1},100,1,1,1,0\n"
            for i in range(288))
        name=f"{symbol}-5m-{day}.csv"
    obj=io.BytesIO()
    with zipfile.ZipFile(obj,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name,data)
    return obj.getvalue()


def test_loader(url,method,cap):
    segment=url.split("/")
    market="um" if "/futures/um/" in url else "spot"
    kind="aggTrades" if "/aggTrades/" in url else "klines"
    symbol="BTCUSDT" if "/BTCUSDT/" in url else "ETHUSDT" if "/ETHUSDT/" in url else "SOLUSDT"
    stem=url.split("/")[-1].removesuffix(".CHECKSUM").removesuffix(".zip")
    day=stem[-10:]
    original=synthetic_zip(day,kind,market,symbol)
    if method=="HEAD":
        return {"http":200,"bytes":len(original)}
    if url.endswith(".CHECKSUM"):
        return (hashlib.sha256(original).hexdigest()+"  "+url.split("/")[-1].removesuffix(".CHECKSUM")).encode()
    return original


def fake_write(_s3,_bucket,key,data):
    return hashlib.sha256(data).hexdigest()


class FrozenRegimeTests(unittest.TestCase):
    def test_exact_three_separate_preholdout_dates(self):
        self.assertEqual(len(PRECOMMITTED_DATES),3)
        self.assertEqual(tuple(PRECOMMITTED_DATES),("2026-02-18","2026-04-15","2026-06-17"))
        self.assertTrue(all(d<"2026-07-01" for d in SOURCE_ALLOWLIST))
        for rejected in ("2026-07-01","2026-05-04","2026-10-16","2024-09-01"):
            with self.assertRaisesRegex(ValueError,"REGIME_UNFROZEN"):
                choose_day(rejected)

    def test_exact_prior_week_does_not_use_study_day(self):
        self.assertEqual(lead_dates("2026-02-18"),("2026-02-11","2026-02-17"))
        self.assertEqual(lead_dates("2026-04-15"),("2026-04-08","2026-04-14"))
        self.assertEqual(lead_dates("2026-06-17"),("2026-06-10","2026-06-16"))

    def test_predeclared_growth_fall_and_consolidation(self):
        def label(start,finish):
            return regime_prior_week(DAY,[start]*288,[finish]*288)
        self.assertEqual(label(100,104)["label"],"RISING")
        self.assertEqual(label(100,96)["label"],"FALLING")
        self.assertEqual(label(100,101)["label"],"CONSOLIDATING")
        self.assertEqual(label(100,103)["label"],"CONSOLIDATING")
        self.assertTrue(label(100,104)["day_to_be_analyzed_not_used_for_regime"])

    def test_prevent_btc_derivatives_and_holdout_urls(self):
        with self.assertRaisesRegex(ValueError,"REGIME_BTC_ONLY_SPOT_PRICE"):
            source_url("um","klines","BTCUSDT","2026-02-11")
        with self.assertRaisesRegex(ValueError,"UNAPPROVED_ARCHIVE_SCOPE"):
            source_url("spot","aggTrades","ETHUSDT","2026-07-12")
        with self.assertRaisesRegex(ValueError,"REGIME_SOURCE_IDENTITY"):
            source_url("spot","aggTrades","BNBUSDT",DAY)

    def test_missing_spot_perp_pair_never_synthetically_filled(self):
        panel={(m,s):([100+i/10 for i in range(288)],
                      {i:{"imbalance":0.1} for i in range(288)})
               for m in ("spot","um") for s in ("ETHUSDT","SOLUSDT")}
        a=join(DAY,panel)
        self.assertEqual(a["h6_pairs"],2)
        self.assertEqual(a["causal_authorized"],0)
        del panel["um","SOLUSDT"]
        with self.assertRaisesRegex(ValueError,"REGIME_FOUR"):
            join(DAY,panel)

    def test_runner_complete_and_no_trading_authority(self):
        with mock.patch("research.detector_h1h10_regime_prewindow_three_dates.put_immutable",side_effect=fake_write):
            report=run(DAY,object(),"bucket","987654","1",test_loader,fake_write)
        self.assertEqual(report["status"],"COMPLETE_DESCRIPTIVE_NOT_PIT")
        self.assertEqual(report["source_counts"]["study_venue_symbol_pairs"],4)
        self.assertEqual(report["source_counts"]["study_aggtrades"],1152)
        self.assertEqual(report["source_counts"]["flow_5m_slots"],1152)
        self.assertEqual(report["predeclared_btc_regime"]["label"],"RISING")
        self.assertEqual(len(report["receipts"]),6)
        self.assertFalse(report["confirmatory_training_allowed"])
        self.assertFalse(report["locked_holdout_used"])
        self.assertFalse(report["trading_actions"])
        self.assertEqual(report["causal_joint_rows_authorized"],0)
        self.assertEqual(report["exploratory"]["h6_pairs"],2)

    def test_one_checksum_tampered_blocks_entire_day(self):
        def corrupt(url,method,cap):
            if (method=="GET" and url.endswith(".CHECKSUM")
                and "/um/daily/aggTrades/SOLUSDT/" in url):
                original=test_loader(url,method,cap)
                return ("0"*64+"  "+url.rsplit("/",1)[-1].removesuffix(".CHECKSUM")).encode()
            return test_loader(url,method,cap)
        report=run(DAY,object(),"bucket","987655","1",corrupt,fake_write)
        self.assertEqual(report["status"],"INCOMPLETE_NOT_ANALYZABLE")
        self.assertIsNone(report["exploratory"])
        self.assertEqual(len(report["failures"]),1)
        self.assertEqual(report["causal_joint_rows_authorized"],0)
        self.assertEqual(report["predeclared_btc_regime"]["label"],"RISING")

    def test_missing_prior_btc_blocks_regime_not_lookahead_classification(self):
        def failed_btc(url,method,cap):
            if "/BTCUSDT/" in url and "2026-02-11" in url and method=="GET" and url.endswith(".zip"):
                return b"corrupt"
            return test_loader(url,method,cap)
        report=run(DAY,object(),"bucket","987656","1",failed_btc,fake_write)
        self.assertEqual(report["status"],"INCOMPLETE_NOT_ANALYZABLE")
        self.assertIsNone(report["predeclared_btc_regime"])
        self.assertEqual(report["causal_joint_rows_authorized"],0)


if __name__=="__main__":
    unittest.main()
