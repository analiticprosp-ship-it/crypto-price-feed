#!/usr/bin/env python3
"""Offline guards for extra FREE first-of-month Tardis vendor as-of days."""
import unittest
from unittest import mock

from research import detector_tardis_vendor_asof_multiday as vetted
from research.detector_tardis_expansion_free_three_days import NEW_DAYS,ROOT,configure


class ExpansionStudy(unittest.TestCase):
 def test_free_three_dates_are_locked(self):
  self.assertEqual(NEW_DAYS,("2024-04-01","2025-07-01","2026-02-01"))
  self.assertEqual(ROOT,"research/tardis-binance-oi-expansion/v1")
  self.assertEqual(len(set(NEW_DAYS)),3)
 def test_reused_source_rejects_unlisted_dates(self):
  with mock.patch.object(vetted,"DAYS",NEW_DAYS):
   self.assertIn("/2025/07/01/BTCUSDT.csv.gz",vetted.sample_url("2025-07-01","BTCUSDT"))
   with self.assertRaisesRegex(ValueError,"UNAPPROVED"):
    vetted.sample_url("2025-06-01","BTCUSDT")
 def test_asof_future_receipt_is_excluded(self):
  day="2026-02-01";start=vetted.epoch_us(day)
  decision=start+vetted.BUCKET_US+vetted.DELAY_US
  points=[(decision-1,0,decision-1000,"100"),(decision+1,1,decision,"999")]
  bars,summary=vetted.asof_5m(points,day,"BTCUSDT")
  self.assertEqual(bars[0]["open_interest"],"100")
  self.assertEqual(summary["future_vendor_receipts"],0)
 def test_original_archive_root_cannot_be_repointed_silently(self):
  with mock.patch.object(vetted,"ROOT","research/another-origin/v1"):
   with self.assertRaisesRegex(ValueError,"BASELINE_SOURCE_IMPLEMENTATION_CHANGED"):
    configure()
 def test_configuration_keeps_expansion_separate(self):
  with mock.patch.object(vetted,"DAYS",("2024-01-01","2025-01-01","2026-09-01")):
   with mock.patch.object(vetted,"ROOT","research/tardis-binance-oi-multiday/v1"):
    with mock.patch.object(vetted,"OUT",None):
     dates,root=configure()
     self.assertEqual(dates,NEW_DAYS)
     self.assertEqual(root,ROOT)
     self.assertNotEqual(root,"research/tardis-binance-oi-multiday/v1")

if __name__=="__main__":unittest.main()
