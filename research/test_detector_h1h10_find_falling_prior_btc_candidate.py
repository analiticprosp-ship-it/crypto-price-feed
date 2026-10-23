"""Offline frozen earliest falling BTC regime prewindow sampling guard."""
import datetime as dt
import hashlib
import io
import unittest
import zipfile

from research.detector_h1h10_find_falling_prior_btc_candidate import (
    CANDIDATES, SOURCE_DAYS, previous_days, classify, find_first_falling,
    run
)


def body_for_day(day):
    begin=int(dt.datetime.fromisoformat(day+"T00:00:00+00:00").timestamp()*1000)
    scale=1000
    head="open_time,open,high,low,close,volume,close_time,q,n,t,b,c\n"
    # Only the *pre*-Feb4 close is lower, so first falling candidate is Feb4.
    close=95.0 if day=="2026-02-03" else 100.0
    rows=head+"".join(
        f"{(begin+i*300000)*scale},{100},101,90,{close},2,{(begin+(i+1)*300000)*scale-1},2,2,2,2,0\n"
        for i in range(288))
    buff=io.BytesIO()
    with zipfile.ZipFile(buff,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"BTCUSDT-5m-{day}.csv",rows)
    return buff.getvalue()


def fake_http(url,method,cap):
    day=url.rsplit("/",1)[-1].removesuffix(".CHECKSUM").removesuffix(".zip")[-10:]
    raw=body_for_day(day)
    if method=="HEAD":
        return {"http":200,"bytes":len(raw)}
    if url.endswith(".CHECKSUM"):
        return (hashlib.sha256(raw).hexdigest()+"  "+url.rsplit("/",1)[-1].removesuffix(".CHECKSUM")).encode()
    return raw


def fake_r2(s3,bucket,key,data):
    return hashlib.sha256(data).hexdigest()


class FirstBearSourceSelection(unittest.TestCase):
    def test_predeclared_candidates_all_before_locked_holdout(self):
        self.assertEqual(len(CANDIDATES),7)
        self.assertTrue(all(day<"2026-07-01" for day in CANDIDATES))
        self.assertTrue(all(day<"2026-07-01" for day in SOURCE_DAYS))
        with self.assertRaisesRegex(ValueError,"DATE_OUTSIDE_PREDECLARATION"):
            previous_days("2026-08-01")

    def test_btc_7day_window_closes_before_study_day(self):
        self.assertEqual(previous_days("2026-01-21"),("2026-01-14","2026-01-20"))
        self.assertEqual(previous_days("2026-06-24"),("2026-06-17","2026-06-23"))

    def test_threshold_exact_minus_three_is_not_falling(self):
        first=[100.]*288
        self.assertFalse(classify(CANDIDATES[0],first,[97.]*288)["is_falling"])
        self.assertTrue(classify(CANDIDATES[0],first,[96.99]*288)["is_falling"])
        self.assertFalse(classify(CANDIDATES[0],first,[102.]*288)["is_falling"])

    def test_no_skipping_bad_first_source_to_hunt_later_falling(self):
        a=[{"day":CANDIDATES[0],"status":"DATA_MISSING","classification":None}]
        selected=find_first_falling(a)
        self.assertEqual(selected["selection_status"],"BLOCKED_BY_EARLIER_MISSING_PRICE")
        self.assertIsNone(selected["selected_date"])

    def test_short_nonfalling_scan_cannot_claim_no_bear_dates(self):
        a=[{"day":CANDIDATES[0],"status":"VERIFIED",
            "classification":{"is_falling":False}}]
        with self.assertRaisesRegex(ValueError,"BEAR_PREMATURE_STOP"):
            find_first_falling(a)

    def test_bounded_runner_selects_second_date_by_only_btc_preprices(self):
        a=run(object(),"bucket","984512","1",fake_http,fake_r2)
        self.assertEqual(a["selection"]["selected_date"],CANDIDATES[1])
        self.assertEqual(a["selection"]["selection_status"],"FIRST_PREDECLARED_FALLING_PREWINDOW")
        self.assertEqual(len(a["observed_candidates"]),2)
        self.assertEqual(a["selected_day_aggtrades_downloaded"],0)
        self.assertFalse(a["selection_uses_eth_sol_flow"])
        self.assertFalse(a["locked_holdout_accessed"])
        self.assertEqual(a["causal_joint_rows_authorized"],0)
        self.assertFalse(a["trading_actions"])

    def test_fail_closed_if_initial_btc_source_corrupted(self):
        def corrupted(url,method,cap):
            if method=="GET" and url.endswith(".zip") and "2026-01-14" in url:
                return b"corrupted"
            return fake_http(url,method,cap)
        a=run(object(),"bucket","984513","1",corrupted,fake_r2)
        self.assertEqual(a["selection"]["selection_status"],"BLOCKED_BY_EARLIER_MISSING_PRICE")
        self.assertIsNone(a["selection"]["selected_date"])
        self.assertEqual(len(a["observed_candidates"]),1)
        self.assertEqual(a["causal_joint_rows_authorized"],0)


if __name__=="__main__":
    unittest.main()
