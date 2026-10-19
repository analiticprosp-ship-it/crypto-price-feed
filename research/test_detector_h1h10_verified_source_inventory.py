#!/usr/bin/env python3
"""Fail-closed tests for H1-H10 pinned R2 inventory and time semantics."""
import csv,datetime as dt,io,unittest
from research.detector_h1h10_verified_source_inventory import (
 DAYS,SYMBOLS,OLD_DAYS,NEW_DAYS,parse_feature_pair,max_streak,
 summary_metrics,quantify_okx_runs
)

DAY="2026-02-01";SYM="BTCUSDT"
START=dt.datetime.fromisoformat(DAY+"T00:00:00+00:00")
def rows():
 f=[];l=[]
 for i in range(288):
  end=START+dt.timedelta(minutes=5*(i+1))
  decision=end+dt.timedelta(seconds=30)
  r={"day":DAY,"symbol":SYM,"decision_time_utc":decision.isoformat(),
   "bucket_end_utc":end.isoformat(),"open_interest":"100",
   "price_oi_feature_quality":"OK_VENDOR_ASOF","last_price":"80000",
   "oi_vendor_receipt_utc":(decision-dt.timedelta(seconds=1)).isoformat(),
   "last_price_vendor_receipt_utc":(decision-dt.timedelta(seconds=2)).isoformat(),
   "oi_age_seconds":"1"}
  label={"day":DAY,"symbol":SYM,"decision_time_utc":decision.isoformat()}
  for h in (15,60):
   valid=i+h//5<288
   label[f"future_last_price_return_{h}m"]="0.004" if valid else ""
   label[f"label_{h}m_available_at_utc"]=(decision+dt.timedelta(minutes=h)).isoformat() if valid else ""
  f.append(r);l.append(label)
 return f,l
def csv_bytes(data):
 fp=io.StringIO(newline="")
 w=csv.DictWriter(fp,fieldnames=list(data[0]))
 w.writeheader();w.writerows(data)
 return fp.getvalue().encode()

class InventoryGuards(unittest.TestCase):
 def test_seven_dates_sorted_and_not_continuous(self):
  self.assertEqual(DAYS,tuple(sorted(DAYS)))
  self.assertEqual(len(DAYS),7)
  self.assertEqual(len(OLD_DAYS),4)
  self.assertEqual(len(NEW_DAYS),3)
  self.assertEqual(max_streak(set(DAYS)),1)
 def test_flow_consecutive_days_are_three(self):
  self.assertEqual(max_streak({"2026-09-01","2026-09-02","2026-09-03"}),3)
  self.assertEqual(max_streak(set()),0)
 def test_paired_asof_csv_valid(self):
  f,l=rows()
  e=parse_feature_pair(DAY,SYM,csv_bytes(f),csv_bytes(l))
  self.assertEqual(e["feature_rows"],288)
  self.assertEqual(e["missing_vendor_asof"],0)
  self.assertEqual(e["missing_last_price"],0)
  self.assertEqual(e["missing_joint_features"],0)
 def test_future_vendor_receipt_is_rejected(self):
  f,l=rows()
  f[0]["oi_vendor_receipt_utc"]=(START+dt.timedelta(minutes=6)).isoformat()
  with self.assertRaisesRegex(ValueError,"FUTURE_VENDOR_RECEIPT"):
   parse_feature_pair(DAY,SYM,csv_bytes(f),csv_bytes(l))
 def test_cross_day_label_must_be_censored(self):
  f,l=rows()
  l[-1]["future_last_price_return_15m"]="99"
  with self.assertRaisesRegex(ValueError,"CROSS_DAY_FUTURE_LABEL"):
   parse_feature_pair(DAY,SYM,csv_bytes(f),csv_bytes(l))
 def test_slot_clock_mismatch_fails(self):
  f,l=rows()
  f[1]["decision_time_utc"]=f[0]["decision_time_utc"]
  with self.assertRaisesRegex(ValueError,"FEATURE_LABEL_ALIGNMENT_INVALID"):
   parse_feature_pair(DAY,SYM,csv_bytes(f),csv_bytes(l))
 def test_missing_price_is_not_converted_to_full_coverage(self):
  f,l=rows()
  f[0]["last_price"]=""
  f[0]["price_oi_feature_quality"]="INCOMPLETE_OR_STALE"
  result=parse_feature_pair(DAY,SYM,csv_bytes(f),csv_bytes(l))
  self.assertEqual(result["missing_joint_features"],1)
  self.assertEqual(result["missing_last_price"],1)
 def test_inventory_coverage_stats_do_not_fake_continuity(self):
  oi=[]
  for day in DAYS:
   for symbol in SYMBOLS:
    oi.append({"dataset":"open_interest_plus_last_price","status":"VERIFIED_VENDOR_RECEIPT_ONLY",
     "date_start_utc":day,"rows":288,"missing_intervals":0})
  flow=[]
  for market in ("spot","perp"):
   for symbol in SYMBOLS:
    for day in ("2026-09-01","2026-09-02","2026-09-03"):
     flow.append({"dataset":"taker_aggtrades_5m","status":"VERIFIED_EVENT_TIME_ONLY",
      "date_start_utc":day,"rows":288,"missing_intervals":0})
  metrics=summary_metrics(oi+flow,{"report_objects_read":2})
  self.assertEqual(metrics["oi_consecutive_day_streak_max"],1)
  self.assertEqual(metrics["flow_consecutive_day_streak_max"],3)
  self.assertEqual(metrics["oi_verified_5m_slots"],6048)
  self.assertEqual(metrics["target_calendar_days_without_pinned_vendor_oi_evidence"],
                   metrics["target_calendar_days"]-7)

if __name__=="__main__":unittest.main()
