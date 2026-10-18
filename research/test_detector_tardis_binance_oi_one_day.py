#!/usr/bin/env python3
"""Offline tests of Tardis local_timestamp as-of and OI schema guards."""
import gzip,unittest
from research.detector_tardis_binance_oi_one_day import inspect,DAY_START

class TardisOITests(unittest.TestCase):
 def csv(self,symbol="BTCUSDT",oi="100.25"):
  us=DAY_START+6*60*1_000_000
  csvstr=("exchange,symbol,timestamp,local_timestamp,open_interest\n"
          f"binance-futures,{symbol},{us-1000},{us},{oi}\n")
  return gzip.compress(csvstr.encode())
 def test_vendor_receipt_bucketing(self):
  r=inspect(self.csv(),"BTCUSDT")
  self.assertEqual(r["counts"]["rows"],1)
  self.assertEqual(r["counts"]["valid_open_interest"],1)
  self.assertEqual(r["five_minute_buckets_with_observed_oi"],1)
  self.assertEqual(r["counts"]["outside_local_day"],0)
 def test_bad_symbol_fails_closed(self):
  with self.assertRaisesRegex(ValueError,"SYMBOL_MISMATCH"):
   inspect(self.csv(symbol="ETHUSDT"),"BTCUSDT")
 def test_empty_oi_fails_closed(self):
  with self.assertRaisesRegex(ValueError,"SAMPLE_EMPTY"):
   inspect(self.csv(oi=""),"BTCUSDT")
 def test_missing_receipt_timestamp_fails_closed(self):
  with self.assertRaisesRegex(ValueError,"REQUIRED_TARDIS_HEADERS"):
   inspect(gzip.compress(b"exchange,symbol,timestamp,open_interest\n"),"BTCUSDT")

if __name__=="__main__":unittest.main()
