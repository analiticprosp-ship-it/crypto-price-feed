#!/usr/bin/env python3
"""Guard expanded OI/price source identifiers and separate future labels."""
import unittest
from research.detector_tardis_expanded_three_day_price_join import (
  NEW_DAYS,SYMBOLS,SOURCE_ROOT,ROOT,verify_source_item
)

class ExpandedPriceJoinTests(unittest.TestCase):
 def good(self):
  day=NEW_DAYS[0];symbol=SYMBOLS[0]
  return {"day":day,"symbol":symbol,
    "original_key":f"{SOURCE_ROOT}/{day}/{symbol}.csv.gz",
    "derived_key":f"{SOURCE_ROOT}/{day}/derived/{symbol}_vendor_asof_5m.csv",
    "source_sha256":"a"*64,"derived_sha256":"b"*64}
 def test_new_dates_are_frozen_and_separate(self):
  self.assertEqual(NEW_DAYS,("2024-04-01","2025-07-01","2026-02-01"))
  self.assertNotIn("2026-10-01",NEW_DAYS)
  self.assertNotIn("oi-price-5m-join/v1",ROOT)
 def test_good_source_pass(self):
  x=self.good()
  self.assertIsNone(verify_source_item(x,NEW_DAYS[0],SYMBOLS[0]))
 def test_old_source_key_rejected(self):
  x=self.good();x["original_key"]="research/tardis-binance-oi-multiday/v1/2024-01-01/BTCUSDT.csv.gz"
  with self.assertRaisesRegex(ValueError,"SOURCE_EXPANSION_KEY_MISMATCH"):
   verify_source_item(x,NEW_DAYS[0],SYMBOLS[0])
 def test_wrong_symbol_fails(self):
  x=self.good()
  with self.assertRaisesRegex(ValueError,"SOURCE_EXPANSION_KEY_MISMATCH"):
   verify_source_item(x,NEW_DAYS[0],"ETHUSDT")
 def test_bad_sha_format_fails(self):
  x=self.good();x["source_sha256"]="fake"
  with self.assertRaisesRegex(ValueError,"SOURCE_HASH_INVALID"):
   verify_source_item(x,NEW_DAYS[0],SYMBOLS[0])

if __name__=="__main__":unittest.main()
