#!/usr/bin/env python3
"""Offline forward-only timestamp and source-quality contract tests."""
import unittest
from research.detector_okx_oi_48h_pilot import changes,validate_oi_data,poll_with_retries,PollAttemptFailure

class OKXOIFirstObservedTests(unittest.TestCase):
 def row(self,t):
  return {"timestamp_ms":t,"sha256":"a"*64,"raw":[str(t),"100"]}
 def observed(self,labels,received):
  return {"symbol":"BTC-USDT-SWAP","response_received_ms":received,
          "rows":[self.row(x) for x in labels]}
 def test_bootstrap_has_no_historical_first_seen(self):
  self.assertEqual(changes(None,self.observed([1800000000000],1800000100000)),([],[],True))
 def test_previous_success_absence_is_bounded(self):
  old=self.observed([1800000000000],1800000410000)
  new=self.observed([1800000000000,1800000300000],1800000730000)
  points,revisions,bootstrap=changes(old,new)
  self.assertEqual(len(points),1)
  self.assertFalse(revisions or bootstrap)
  self.assertEqual(points[0]["last_observed_absent_ms"],1800000410000)
  self.assertEqual(points[0]["bound_type"],"ABSENT_ON_PREVIOUS_POLL")
 def test_no_false_lower_bound_before_label(self):
  old=self.observed([1800000000000],1800000150000)
  new=self.observed([1800000300000],1800000400000)
  points,_,_=changes(old,new)
  self.assertIsNone(points[0]["last_observed_absent_ms"])
  self.assertEqual(points[0]["bound_type"],"FIRST_OBSERVED_ONLY")
 def test_revision_is_not_new_timestamp(self):
  old=self.observed([1800000000000],1800000100000)
  new=self.observed([1800000000000],1800000350000)
  new["rows"][0]["sha256"]="b"*64
  first,revisions,_=changes(old,new)
  self.assertFalse(first)
  self.assertEqual(len(revisions),1)
 def test_future_timestamp_rejected(self):
  with self.assertRaisesRegex(ValueError,"LABEL_RANGE"):
   validate_oi_data({"code":"0","data":[["1800000400000","123"]]},"BTC-USDT-SWAP",1800000000000)
 def test_duplicate_source_label_rejected(self):
  with self.assertRaisesRegex(ValueError,"DUPLICATE"):
   validate_oi_data({"code":"0","data":[["1800000000000","1"],["1800000000000","2"]]},
                    "BTC-USDT-SWAP",1800000100000)
 def test_nonmonotonic_response_rejected(self):
  with self.assertRaisesRegex(ValueError,"NON_MONOTONIC"):
   changes(self.observed([1800000000000],1800000400000),
           self.observed([1800000300000],1800000200000))

class OKXRetrySafetyTests(unittest.TestCase):
 def observed(self):
  return {"symbol":"BTC-USDT-SWAP","response_received_ms":1800001000000,
          "rows":[{"timestamp_ms":1800000000000,"sha256":"a"*64,"raw":["1800000000000","1"]}]}
 def test_temporary_empty_response_retries_and_records_real_attempts(self):
  attempted=[]
  def fake(_):
   attempted.append(1)
   if len(attempted)<3:raise ValueError("OKX_OI_ROWS_INVALID")
   return self.observed()
  slept=[]
  result=poll_with_retries("BTC-USDT-SWAP",1800009000000,
    fetch=fake,sleeper=slept.append,clock=lambda:1800001000000)
  self.assertEqual(len(result["attempt_trace"]),3)
  self.assertEqual([x["status"] for x in result["attempt_trace"]],
                   ["FAILED","FAILED","PASS"])
  self.assertEqual(slept,[1,2])
 def test_persistent_empty_fails_and_retains_provenance(self):
  attempted=[]
  def fake(_):
   attempted.append(1)
   raise ValueError("OKX_OI_ROWS_INVALID")
  with self.assertRaises(PollAttemptFailure) as caught:
   poll_with_retries("BTC-USDT-SWAP",1800009000000,
     fetch=fake,sleeper=lambda _:None,clock=lambda:1800001000000)
  self.assertEqual(len(attempted),3)
  self.assertEqual(len(caught.exception.attempts),3)
 def test_structural_source_error_does_not_retry(self):
  attempted=[]
  def fake(_):
   attempted.append(1)
   raise ValueError("OKX_OI_DUPLICATE_TIMESTAMPS")
  with self.assertRaises(PollAttemptFailure) as caught:
   poll_with_retries("BTC-USDT-SWAP",1800009000000,
     fetch=fake,sleeper=lambda _:None,clock=lambda:1800001000000)
  self.assertEqual(len(attempted),1)
  self.assertFalse(caught.exception.attempts[0]["retryable"])
 def test_deadline_never_makes_source_request(self):
  attempted=[]
  with self.assertRaises(PollAttemptFailure) as caught:
   poll_with_retries("BTC-USDT-SWAP",1800000000000,
      fetch=lambda _:attempted.append(1),clock=lambda:1800000000000)
  self.assertEqual(attempted,[])
  self.assertEqual(len(caught.exception.attempts),0)
 def test_failed_http_451_is_not_retried(self):
  import urllib.error
  attempted=[]
  def fake(_):
   attempted.append(1)
   raise urllib.error.HTTPError("https://example.invalid",451,"unavailable",{},None)
  with self.assertRaises(PollAttemptFailure):
   poll_with_retries("BTC-USDT-SWAP",1800009000000,
    fetch=fake,sleeper=lambda _:None,clock=lambda:1800001000000)
  self.assertEqual(len(attempted),1)

if __name__=="__main__":
 unittest.main()
