"""Offline R2 provenance, missing-clock and PIT controls for 3-metric audit."""
import copy
import hashlib
import io
import json
import unittest
from research.detector_okx_3metric_receipt_audit import (
   check_one,verified_json,summarize,MAX_RUN_REPORTS)
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
if __name__=="__main__":unittest.main()
