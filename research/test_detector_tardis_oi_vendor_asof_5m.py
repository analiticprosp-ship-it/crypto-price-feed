#!/usr/bin/env python3
"""Offline anti-lookahead and cutoff boundary checks."""
import unittest
from research.detector_tardis_oi_vendor_asof_5m import DAY_US,FIVE_US,DELAY_US,latest_asof,produce

class VendorAsOfTests(unittest.TestCase):
 def source(self,local_us,oi,order):
  return {"local_us":local_us,"source_us":local_us-1000,
          "open_interest":str(oi),"order":order}
 def test_no_future_vendor_receipt_used(self):
  decision=DAY_US+FIVE_US+DELAY_US
  early=self.source(decision-1,100,0)
  later=self.source(decision+1,999,1)
  self.assertEqual(latest_asof([early,later],decision),early)
  rows,stats=produce("BTCUSDT",[early,later])
  self.assertEqual(rows[0]["open_interest"],"100")
  self.assertEqual(stats["future_receipt_used"],0)
 def test_boundary_is_inclusive(self):
  cutoff=DAY_US+FIVE_US+DELAY_US
  rows,stats=produce("BTCUSDT",[self.source(cutoff,42,0)])
  self.assertEqual(rows[0]["open_interest"],"42")
  self.assertEqual(stats["buckets"],288)
 def test_no_snapshot_before_cutoff_is_missing(self):
  late=self.source(DAY_US+FIVE_US+DELAY_US+1,1,0)
  rows,stats=produce("BTCUSDT",[late])
  self.assertEqual(rows[0]["asof_quality"],"MISSING_ASOF_OI")
  self.assertEqual(rows[1]["open_interest"],"1")
  self.assertEqual(stats["future_receipt_used"],0)
 def test_source_same_microsecond_tie_breaks_by_order(self):
  ts=DAY_US+10
  earlier=self.source(ts,11,0);later=self.source(ts,12,1)
  self.assertEqual(latest_asof([earlier,later],DAY_US+FIVE_US+DELAY_US),later)

if __name__=="__main__":unittest.main()
