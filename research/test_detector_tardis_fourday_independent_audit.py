#!/usr/bin/env python3
"""Independent replay regressions: derived rows must match latest raw vendor snapshot."""
import csv
import gzip
import io
import unittest
from research.detector_tardis_fourday_independent_audit import usec,raw_snapshots,verify_derived

DAY="2025-01-01"
SYMBOL="BTCUSDT"
T0=usec(DAY+"T00:00:00+00:00")

def iso(us):
    import datetime as dt
    return dt.datetime.fromtimestamp(us/1_000_000,dt.timezone.utc).isoformat()

def raw_file(data):
    rows="exchange,symbol,timestamp,local_timestamp,open_interest\n"
    for t,oi in data:
        rows+=f"binance-futures,{SYMBOL},{t-1000},{t},{oi}\n"
    return gzip.compress(rows.encode())

def derived_file(when,oi):
    out=io.StringIO(newline="")
    writer=csv.DictWriter(out,fieldnames=(
        "bucket_start_utc","bucket_end_utc","decision_time_utc","symbol",
        "open_interest","vendor_receipt_utc","source_event_utc",
        "observation_age_seconds","asof_quality"))
    writer.writeheader()
    for i in range(288):
        end=T0+(i+1)*300_000_000
        decision=end+30_000_000
        age=(decision-when)/1_000_000
        writer.writerow({
            "bucket_start_utc":iso(end-300_000_000),"bucket_end_utc":iso(end),
            "decision_time_utc":iso(decision),"symbol":SYMBOL,
            "open_interest":oi,"vendor_receipt_utc":iso(when),
            "source_event_utc":iso(when-1000),
            "observation_age_seconds":f"{age:.6f}",
            "asof_quality":"STALE_VENDOR_OVER_120S" if age>120 else "OK_VENDOR_RECEIPT"})
    return out.getvalue().encode()

class IndependentCausalReplayTests(unittest.TestCase):
    def test_every_bucket_replays_exact_source(self):
        when=T0+300_000_000
        raw=raw_snapshots(raw_file([(when,"123.5")]),DAY,SYMBOL)
        status=verify_derived(raw,derived_file(when,"123.5"),DAY,SYMBOL)
        self.assertEqual(status["verified_5m_buckets"],288)
        self.assertEqual(status["stale_gt120s"],287)

    def test_future_oi_in_derived_is_rejected(self):
        when=T0+300_000_000
        raw=raw_snapshots(raw_file([(when,"123.5")]),DAY,SYMBOL)
        tampered=derived_file(when,"999.0")
        with self.assertRaisesRegex(ValueError,"NOT_LATEST_ELIGIBLE"):
            verify_derived(raw,tampered,DAY,SYMBOL)

    def test_wrong_decision_time_is_rejected(self):
        when=T0+300_000_000
        raw=raw_snapshots(raw_file([(when,"123.5")]),DAY,SYMBOL)
        corrupted=derived_file(when,"123.5").decode().replace(
            iso(T0+330_000_000),iso(T0+300_000_000),1).encode()
        with self.assertRaisesRegex(ValueError,"TIME_BOUNDARY"):
            verify_derived(raw,corrupted,DAY,SYMBOL)

    def test_raw_symbol_must_match(self):
        raw=gzip.decompress(raw_file([(T0+300_000_000,"123.5")]))
        data=gzip.compress(raw.replace(b"BTCUSDT",b"ETHUSDT"))
        with self.assertRaisesRegex(ValueError,"RAW_SYMBOL"):
            raw_snapshots(data,DAY,SYMBOL)

if __name__=="__main__":unittest.main()
