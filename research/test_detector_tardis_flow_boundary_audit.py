#!/usr/bin/env python3
"""Offline source-event 5m aggregation timing tests; no publication-time proof."""
import datetime as dt
import unittest
from research.detector_tardis_flow_boundary_audit import validate_flow,audit,DAY,us

START=us(DAY+"T00:00:00+00:00")
def iso(usnum):
 return dt.datetime.fromtimestamp(usnum/1_000_000,dt.timezone.utc).isoformat()
def row(index,buy=100,sell=40):
 return {"timestamp_utc":iso(START+index*300_000_000),
         "aggtrade_count":"3","taker_buy_quote":str(buy),
         "taker_sell_quote":str(sell),
         "delta_quote":str(buy-sell),"total_quote":str(buy+sell)}
def price_row(i):
 end=START+(i+1)*300_000_000
 decision=end+30_000_000
 return {"symbol":"BTCUSDT","bucket_end_utc":iso(end),
    "decision_time_utc":iso(decision),
    "oi_vendor_receipt_utc":iso(decision-1_000_000),
    "last_price_vendor_receipt_utc":iso(decision-2_000_000),
    "price_oi_feature_quality":"OK_VENDOR_ASOF"}

class EventBoundaryTests(unittest.TestCase):
 def test_one_closed_bucket(self):
  got,stats=validate_flow([row(0)],DAY,"spot","BTCUSDT")
  self.assertEqual(len(got),1)
  self.assertEqual(stats["selected_5m_buckets"],1)
 def test_aggregation_identity_fail_closed(self):
  bad=row(0);bad["delta_quote"]="999"
  with self.assertRaisesRegex(ValueError,"ACCOUNTING"):
   validate_flow([bad],DAY,"spot","BTCUSDT")
 def test_unaligned_flow_bucket_rejected(self):
  bad=row(0);bad["timestamp_utc"]=iso(START+1_000_000)
  with self.assertRaisesRegex(ValueError,"NOT_ALIGNED"):
   validate_flow([bad],DAY,"spot","BTCUSDT")
 def test_duplicate_bucket_rejected(self):
  with self.assertRaisesRegex(ValueError,"DUPLICATE"):
   validate_flow([row(0),row(0)],DAY,"spot","BTCUSDT")
 def test_all_288_closed_buckets_match_vendor_features(self):
  flows,_=validate_flow([row(i) for i in range(288)],DAY,"spot","BTCUSDT")
  result=audit("BTCUSDT",flows,flows,[price_row(i) for i in range(288)])
  self.assertEqual(result["both_flow_and_price_oi_aligned"],288)
  self.assertEqual(result["closed_5m_boundary_violations"],0)
 def test_future_vendor_receipt_cannot_be_aligned(self):
  flows,_=validate_flow([row(i) for i in range(288)],DAY,"spot","BTCUSDT")
  features=[price_row(i) for i in range(288)]
  bad=features[0];bad["oi_vendor_receipt_utc"]=iso(START+330_000_001)
  with self.assertRaisesRegex(ValueError,"FUTURE_OI"):
   audit("BTCUSDT",flows,flows,features)
 def test_wrong_decision_boundary_rejected(self):
  flows,_=validate_flow([row(i) for i in range(288)],DAY,"spot","BTCUSDT")
  features=[price_row(i) for i in range(288)]
  features[0]["decision_time_utc"]=iso(START+300_000_000)
  with self.assertRaisesRegex(ValueError,"BOUNDARY_ALIGNMENT"):
   audit("BTCUSDT",flows,flows,features)

if __name__=="__main__":unittest.main()
