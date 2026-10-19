#!/usr/bin/env python3
"""Pure offline fail-closed tests for R2 ZIP numeric content and source-time limits."""
import csv
import datetime as dt
import hashlib
import io
import json
import unittest
import zipfile

from research.detector_h1h10_archived_candidate_content_audit import (
    audit_oi_csv,digest,inspect_archive,oi_columns,summarize,timestamp
)

def archive(files):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w",zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    b=stream.getvalue()
    m={"run_id":39100000000,"workflow":"fake","artifact_name":"fake",
       "archive_object_key":"research/39100000000/1-fake.zip",
       "archive_expected_sha256":hashlib.sha256(b).hexdigest(),"archive_bytes":len(b)}
    return b,m

def csv_series(day_count=7,one_gap=False):
    out=io.StringIO();w=csv.writer(out)
    w.writerow(["timestamp_utc","sum_open_interest","sum_open_interest_valid"])
    start=dt.datetime(2026,1,1,tzinfo=dt.timezone.utc)
    for i in range(day_count*288):
        if one_gap and i==200:continue
        t=start+dt.timedelta(minutes=i*5)
        w.writerow([t.isoformat(),"12345.3","1"])
    return out.getvalue()

class CandidateContentAuditTests(unittest.TestCase):
    def test_strict_datetime_utc_and_oi_column(self):
        self.assertIsNone(timestamp("2026-01-01T12:00:00"))
        self.assertIsNone(timestamp("not-a-time"))
        self.assertIsNone(oi_columns(["timestamp_utc","last_price"]))
        self.assertEqual(oi_columns(["timestamp_utc","sum_open_interest"]),"sum_open_interest")
    def test_seven_event_days_are_not_publication_proof(self):
        b,m=archive({"BTCUSDT_research_5m.csv":csv_series()})
        report=inspect_archive(b,m)
        self.assertEqual(report["archive_integrity"],"SHA256_AND_ZIP_CRC_VERIFIED")
        self.assertEqual(report["max_consecutive_288_event_label_days"],7)
        self.assertTrue(report["contains_7day_event_label_candidate"])
        self.assertFalse(report["candidate_7day_first_publication_verified"])
        self.assertEqual(report["files"][0]["original_source_publication"],"UNVERIFIED")
    def test_one_missing_label_breaks_full_day_chain(self):
        b,m=archive({"BTCUSDT_research_5m.csv":csv_series(one_gap=True)})
        report=inspect_archive(b,m)
        self.assertLess(report["max_consecutive_288_event_label_days"],7)
    def test_json_report_only_never_becomes_oi_series(self):
        b,m=archive({"quality.json":json.dumps({"status":"PASS","open_interest":123})})
        report=inspect_archive(b,m)
        self.assertEqual(report["observed_oi_series"],0)
        self.assertFalse(report["contains_7day_event_label_candidate"])
    def test_archive_sha_mismatch_rejected(self):
        b,m=archive({"data.json":"{}"})
        m["archive_expected_sha256"]="a"*64
        with self.assertRaisesRegex(ValueError,"ARCHIVE_SHA_OR_LENGTH_MISMATCH"):
            inspect_archive(b,m)
    def test_duplicate_source_event_timestamp_counted_not_synthesized(self):
        data=csv_series(1)+"2026-01-01T00:00:00+00:00,12000,1\n"
        b,m=archive({"BTCUSDT_research_5m.csv":data})
        row=inspect_archive(b,m)["files"][0]
        self.assertEqual(row["duplicate_event_labels"],1)
        self.assertEqual(row["unique_numeric_observations"],288)
    def test_invalid_mask_is_not_a_valid_oi_measurement(self):
        text="timestamp_utc,sum_open_interest,sum_open_interest_valid\n2026-01-01T00:00:00+00:00,123,0\n"
        b,m=archive({"BTCUSDT_research_5m.csv":text})
        row=inspect_archive(b,m)["files"][0]
        self.assertEqual(row["invalid_or_masked_oi"],1)
        self.assertEqual(row["unique_numeric_observations"],0)
    def test_summary_requires_sha_crc_for_verified_archives(self):
        b,m=archive({"small.json":json.dumps({"schema":"test"})})
        good=inspect_archive(b,m)
        summary=summarize([good,{"archive_integrity":"UNVERIFIED_ERROR"}])
        self.assertEqual(summary["archives_sha256_crc_pass"],1)
        self.assertEqual(summary["archives_with_errors"],1)
        self.assertFalse(summary["continuous_7day_publication_verified"])

if __name__=="__main__":unittest.main()
