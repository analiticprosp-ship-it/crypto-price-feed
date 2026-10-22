"""Strict bounded May 05-10 exploratory event-only extension; no PIT or holdout."""
import datetime as dt
import hashlib
import io
import unittest
import zipfile
from unittest import mock

from research.detector_h1h10_binance_flow_archive_pilot import DAYS, archive_url
from research.detector_h1h10_binance_aggtrades_first_verified import parse_day_zip
from research.detector_h1h10_binance_one_day_event_diagnostics import read_flow_5m
from research.detector_h1h10_binance_week_event_expansion import (
    DAYS_ADDITIONAL,SYMBOLS,MARKETS,choose_day,exact_publisher_file,
    join_day,run,read_prices,
)

DAY="2026-05-05"
START=int(dt.datetime.fromisoformat(DAY+"T00:00:00+00:00").timestamp()*1000)


def fake_zip(market,symbol,kind,day=DAY):
    base=int(dt.datetime.fromisoformat(day+"T00:00:00+00:00").timestamp()*1000)
    unit=1000 if market=="spot" else 1
    if kind=="aggTrades":
        header="agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n"
        raw=header+"".join(f"{i},100,2,{2*i},{2*i+1},{(base+i*300000+1000)*unit},{'false' if i%2==0 else 'true'}\n" for i in range(288))
        name=f"{symbol}-aggTrades-{day}.csv"
    else:
        header="open_time,open,high,low,close,volume,close_time,quote,n,trades,base,ignore\n"
        raw=header+"".join(f"{(base+i*300000)*unit},100,101,99,{100+i/10},1,{(base+(i+1)*300000)*unit-1},1,1,1,1,0\n" for i in range(288))
        name=f"{symbol}-5m-{day}.csv"
    buff=io.BytesIO()
    with zipfile.ZipFile(buff,"w",compression=zipfile.ZIP_DEFLATED) as f:
        f.writestr(name,raw)
    return buff.getvalue()


def loader(url,method,cap):
    parts=url.split("/")
    symbol=parts[-1].split("-")[0]
    day=DAY
    market="um" if "/futures/um/" in url else "spot"
    kind="aggTrades" if "aggTrades" in url else "klines"
    payload=fake_zip(market,symbol,kind)
    if method=="HEAD":
        return {"http":200,"bytes":len(payload)}
    if url.endswith(".CHECKSUM"):
        return (hashlib.sha256(payload).hexdigest()+"  "+url.rsplit("/",1)[-1].removesuffix(".CHECKSUM")).encode()
    return payload


class DiscoveryWeek(unittest.TestCase):
    def test_exact_extension_dates_only(self):
        self.assertEqual(DAYS_ADDITIONAL,tuple(f"2026-05-{x:02d}" for x in range(5,11)))
        with self.assertRaisesRegex(ValueError,"DAY_OUTSIDE"):
            choose_day("2026-07-05")
        with self.assertRaisesRegex(ValueError,"DAY_OUTSIDE"):
            choose_day("2026-05-04")
        with self.assertRaisesRegex(ValueError,"DAY_OUTSIDE"):
            choose_day("2026-09-01")

    def test_spot_and_um_native_clocks_on_new_day(self):
        for market in MARKETS:
            result, rows=parse_day_zip(fake_zip(market,"ETHUSDT","aggTrades"),market,"ETHUSDT",DAY)
            self.assertEqual(result["trades"],288)
            self.assertEqual(len(rows),288)
            self.assertEqual(result["historical_original_publication_time"],"UNVERIFIED")
        with self.assertRaisesRegex(ValueError,"AGGTRADE_UNAUTHORIZED"):
            parse_day_zip(fake_zip("spot","ETHUSDT","aggTrades"),"spot","ETHUSDT","2026-07-01")

    def test_full_price_has_288_censored_bars(self):
        for market in MARKETS:
            report,prices=read_prices(fake_zip(market,"SOLUSDT","klines"),market,"SOLUSDT",DAY)
            self.assertEqual(len(prices),288)
            self.assertEqual(report["rows"],288)
        with self.assertRaisesRegex(ValueError,"KLINE_CLOCK"):
            read_prices(fake_zip("um","SOLUSDT","klines"),"spot","SOLUSDT",DAY)

    def test_url_and_sha_checked_before_acceptance(self):
        url=archive_url("spot","aggTrades","ETHUSDT",DAY)
        payload,digest=exact_publisher_file(url,25000000,loader)
        self.assertEqual(digest,hashlib.sha256(payload).hexdigest())
        def compromised(u,m,cap):
            v=loader(u,m,cap)
            return b"tampered"+v if u.endswith(".zip") and m=="GET" else v
        with self.assertRaisesRegex(ValueError,"PUBLISHER_SHA_MISMATCH"):
            exact_publisher_file(url,25000000,compromised)

    def test_new_day_derived_reader_honors_mask_without_fill(self):
        _,rows=parse_day_zip(fake_zip("spot","ETHUSDT","aggTrades"),"spot","ETHUSDT",DAY)
        from research.detector_h1h10_binance_aggtrades_first_verified import flow_csv_bytes
        d=read_flow_5m(flow_csv_bytes(rows),DAY)
        self.assertEqual(len(d),288)
        self.assertEqual(d[0]["imbalance"],1)
        self.assertEqual(d[1]["imbalance"],-1)

    def test_h6_matching_requires_exact_four_fixed_panel(self):
        samples={(m,s):([100+i*.1 for i in range(288)],
                        {i:{"imbalance":.1} for i in range(288)})
                 for m in MARKETS for s in SYMBOLS}
        a=join_day(DAY,samples)
        self.assertEqual(a["h6_matched_coin_count"],2)
        self.assertEqual(a["causal_authorized"],0)
        self.assertEqual(a["h6_matched_coin"]["ETHUSDT"]["event_only_diagnostics"]["15m"]["event_only_sample_count"],284)
        del samples["um","SOLUSDT"]
        with self.assertRaisesRegex(ValueError,"EXPECTED_FOUR"):
            join_day(DAY,samples)

    def test_real_runner_simulates_four_complete_strict_evidence_sources(self):
        from research.detector_h1h10_binance_week_event_expansion import ROOT
        stored={}
        def store(s3,bucket,key,body):
            if key in stored and stored[key]!=body:
                raise ValueError("IMMUTABLE_TEST_COLLISION")
            stored[key]=body
            return hashlib.sha256(body).hexdigest()
        with mock.patch("research.detector_h1h10_binance_week_event_expansion.put_immutable",side_effect=store):
            a=run(DAY,object(),"bucket","123456","1",loader)
        self.assertEqual(a["status"],"COMPLETE_EVENT_ONLY_NOT_PIT",a["failed_sources"])
        self.assertEqual(a["actual_trades_verified"],1152)
        self.assertEqual(a["observed_event_flow_buckets"],1152)
        self.assertEqual(a["exploratory"]["h6_matched_coin_count"],2)
        self.assertEqual(a["causal_joint_rows_authorized"],0)
        self.assertFalse(a["holdout_consumed"])
        self.assertFalse(a["confirmatory_training_authorized"])
        self.assertTrue(all(x["historical_source_publication"]=="UNVERIFIED" for x in a["verified_sources"]))
        self.assertEqual(len([x for x in stored if "/raw-flow/" in x]),4)

    def test_corrupt_one_checksum_produces_incomplete_report_not_fake_panel(self):
        def bad_loader(url,method,cap):
            data=loader(url,method,cap)
            if "/um/daily/aggTrades/SOLUSDT/" in url and url.endswith(".CHECKSUM"):
                return ("0"*64+"  "+url.rsplit("/",1)[-1].removesuffix(".CHECKSUM")).encode()
            return data
        def store(_s3,_bucket,_key,body):
            return hashlib.sha256(body).hexdigest()
        with mock.patch("research.detector_h1h10_binance_week_event_expansion.put_immutable",side_effect=store):
            report=run(DAY,object(),"bucket","234567","1",bad_loader)
        self.assertEqual(report["status"],"INCOMPLETE_DO_NOT_JOIN")
        self.assertIsNone(report["exploratory"])
        self.assertEqual(len(report["failed_sources"]),1,report["failed_sources"])
        self.assertEqual(report["causal_joint_rows_authorized"],0)


if __name__=="__main__":
    unittest.main()
