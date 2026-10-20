"""Offline R2 provenance, missing-clock and PIT controls for 3-metric audit."""
import copy
import hashlib
import io
import json
import unittest
from research.detector_okx_3metric_receipt_audit import (
   check_one,verified_json,summarize,summarize_stream_receipts,MAX_RUN_REPORTS)
from research.detector_okx_3metric_forward_48h import SYMBOLS,METRICS,SCHEMA

def source(run="1001",stamp="2026-10-20T08:00:00+00:00"):
    return {"schema":SCHEMA,"run":run,"attempt":"1",
      "status":"SOURCES_ALL_RECEIVED","observed_at_utc":stamp,
      "scope":"RESEARCH_ONLY","trading_actions":False,
      "original_exchange_first_publication":"UNVERIFIED",
      "causal_join_training":"BLOCKED","edge_status":"EDGE_UNVALIDATED",
      "source_reports":{i+"|"+m:{
         "response_received_ms":1792483200000,"row_count":20}
          for i in SYMBOLS for m in METRICS},
      "coverage_gate":{i:{"join_grade":"SOURCE_LABEL_OVERLAP_ONLY_NO_CAUSAL_PIT",
          "training_authorized":False,"causal_5m_rows_authorized":0}
          for i in SYMBOLS}}
class FakeStream:
 def __init__(self,p):self.p=p
 def read(self,n):return self.p[:n]
class FakeS3:
 def __init__(self,payload,sha):
   self.payload=payload;self.sha=sha
 def get_object(self,**_):
   return {"ContentLength":len(self.payload),
       "Metadata":{"sha256":self.sha},"Body":FakeStream(self.payload)}
class ReceiptAuditTests(unittest.TestCase):
 def test_legacy_run_is_explicitly_not_raw_sha_linked(self):
    ok,legacy=check_one(None,None,source())
    self.assertEqual((ok,legacy),(0,9))
 def test_scheduled_spacing_15m_is_not_five_minute_pit(self):
    a=source("1001","2026-10-20T08:00:00+00:00")
    b=source("1002","2026-10-20T08:15:00+00:00")
    p=summarize([a,b])
    self.assertEqual(p["median_actual_run_spacing_seconds"],900)
    self.assertEqual(p["continuous_5m_pit_grade"],"UNVERIFIED")
    self.assertEqual(p["historical_h1h10_confirmation"],"BLOCKED")
 def test_long_delay_is_counted_not_interpolated(self):
    a=source("1001","2026-10-20T08:00:00+00:00")
    b=source("1002","2026-10-20T09:00:00+00:00")
    self.assertEqual(summarize([a,b])["gaps_over_20_minutes"],1)
 def test_empty_pilot_is_not_positive_availability(self):
    p=summarize([])
    self.assertIsNone(p["observed_start_utc"])
    self.assertEqual(p["reports"],0)
 def test_duplicate_run_fails_closed(self):
    with self.assertRaisesRegex(ValueError,"DUPLICATE_RUN"):
     summarize([source(),source()])
 def test_altered_pit_status_rejected(self):
    a=source();a["causal_join_training"]="PASS"
    with self.assertRaisesRegex(ValueError,"PIT_PROMOTED"):check_one(None,None,a)
 def test_unauthorized_training_rejected(self):
    a=source();a["coverage_gate"][SYMBOLS[0]]["training_authorized"]=True
    with self.assertRaisesRegex(ValueError,"JOINS_NOT_CAUSAL"):check_one(None,None,a)
 def test_missing_symbol_rejected(self):
    a=source();a["source_reports"]["ELON|oi"]=a["source_reports"].pop(SYMBOLS[0]+"|oi")
    with self.assertRaisesRegex(ValueError,"FOREIGN_SYMBOL"):check_one(None,None,a)
 def test_missing_raw_hash_and_key_is_not_reported_as_sha_verified(self):
    a=source()
    a["source_reports"][SYMBOLS[0]+"|oi"]["raw_sha256"]="a"*64
    a["source_reports"][SYMBOLS[0]+"|oi"]["raw_r2_key"]="wrong-key.json"
    with self.assertRaisesRegex(ValueError,"PROVENANCE_KEY"):check_one(None,None,a)
 def test_verified_source_with_correct_r2_metadata(self):
    p=json.dumps(source(),sort_keys=True).encode()
    h=hashlib.sha256(p).hexdigest()
    self.assertEqual(verified_json(FakeS3(p,h),"b","key.json")["schema"],SCHEMA)
 def test_sha256_mismatch_rejected(self):
    p=json.dumps(source(),sort_keys=True).encode()
    with self.assertRaisesRegex(ValueError,"SHA256_R2"):
     verified_json(FakeS3(p,"0"*64),"b","key.json")
 def test_per_stream_observed_gaps_are_individual_not_run_clock(self):
    a=source("1001","2026-10-20T08:00:00+00:00")
    b=source("1002","2026-10-20T08:15:00+00:00")
    for name in b["source_reports"]:
      b["source_reports"][name]["response_received_ms"] += 900000
    # Make BTC OI one minute earlier than the other streams in each run.
    name=SYMBOLS[0]+"|oi"
    a["source_reports"][name]["response_received_ms"] -= 60000
    b["source_reports"][name]["response_received_ms"] -= 60000
    summary=summarize_stream_receipts([a,b])
    self.assertEqual(summary["streams_expected"],9)
    self.assertEqual(summary["total_observed_intervals_across_streams"],9)
    self.assertEqual(summary["observed_gaps_over_5min_across_streams"],9)
    self.assertEqual(summary["observed_gaps_over_20min_across_streams"],0)
    self.assertEqual(summary["worst_actual_same_stream_gap_seconds"],900)
    self.assertFalse(summary["real_5m_collector_continuity_proven"])
    self.assertEqual(summary["causal_rows_authorized"],0)

 def test_missing_stream_not_filled_or_counted_as_real_receipt(self):
    a=source("1001","2026-10-20T08:00:00+00:00")
    b=source("1002","2026-10-20T08:15:00+00:00")
    b["status"]="PARTIAL_SOURCE_FAILURE"
    miss=SYMBOLS[1]+"|flow"
    del b["source_reports"][miss]
    for x in b["source_reports"].values():
      x["response_received_ms"] += 900000
    summary=summarize_stream_receipts([a,b])
    self.assertEqual(summary["source_audit"][miss]["observed_receipts"],1)
    self.assertEqual(summary["source_audit"][miss]["missing_run_reports_for_stream"],1)
    self.assertEqual(summary["source_audit"][miss]["observed_intervals"],0)
    self.assertEqual(summary["total_observed_intervals_across_streams"],8)
    self.assertEqual(summary["observed_gaps_over_5min_across_streams"],8)

 def test_same_stream_duplicate_actual_receipt_fails_closed(self):
    a=source("1001","2026-10-20T08:00:00+00:00")
    b=source("1002","2026-10-20T08:15:00+00:00")
    # Timestamp repeated in another run; do not interpret this as a new poll.
    with self.assertRaisesRegex(ValueError,"NINE_STREAM_DUPLICATE"):
      summarize_stream_receipts([a,b])

 def test_future_receipt_and_promoted_authority_rejected(self):
    a=source()
    a["source_reports"][SYMBOLS[0]+"|oi"]["response_received_ms"] += 10
    with self.assertRaisesRegex(ValueError,"NINE_STREAM_RECEIPT_AFTER_MANIFEST"):
      summarize_stream_receipts([a])
    a=source()
    a["causal_join_training"]="AUTHORIZED"
    with self.assertRaisesRegex(ValueError,"NINE_STREAM_AUDIT_AUTHORITY_INVALID"):
      summarize_stream_receipts([a])

 def test_zero_runs_never_establishes_continuity(self):
    s=summarize_stream_receipts([])
    self.assertFalse(s["all_nine_streams_observed"])
    self.assertFalse(s["real_5m_collector_continuity_proven"])
    self.assertEqual(s["total_observed_intervals_across_streams"],0)
    self.assertEqual(s["observed_gaps_over_5min_across_streams"],0)

if __name__=="__main__":unittest.main()
