#!/usr/bin/env python3
"""Fail-closed source completeness, chronology, metrics for frozen 7day research."""
import unittest
from research.detector_seven_day_fixed_controls import (
 DAYS,NEW_DAYS,SYMBOLS,HORIZONS,source_catalog,evaluate_seven_days,summary
)
from research.detector_tardis_price_oi_chrono_ablation import BASE_FIELDS,OI_FIELD


def dummy_catalog():
 old={"schema":"detector-h1-h10-tardis-price-oi-forward-targets-v1",
      "days":["2024-01-01","2025-01-01","2026-09-01","2026-10-01"],
      "outputs":[]}
 new={"schema":"detector-tardis-expanded-three-day-price-oi-join-v1",
      "days":list(NEW_DAYS),"outputs":[]}
 for day in DAYS:
  target=old if day in old["days"] else new
  for sym in SYMBOLS:target["outputs"].append({"day":day,"symbol":sym})
 return old,new


def dummy_rows():
 samples={}
 for h in HORIZONS:
  sample=[]
  for day in DAYS:
   for symbol in SYMBOLS:
    for i in range(14):
     sample.append({"day":day,"symbol":symbol,
      "minute_index":i,
      BASE_FIELDS[0]:i*.0001,BASE_FIELDS[1]:(i%5)*.002,
      OI_FIELD:((i%3)-1)*.005,"y":int(i%2==0),
      "forward_return":.001 if i%2==0 else -.002})
  samples[h]=sample
 return samples

class FrozenSevenDayPanelTests(unittest.TestCase):
 def test_chronology_sorted_and_additions_distinct(self):
  self.assertEqual(DAYS,tuple(sorted(DAYS)))
  self.assertTrue(set(NEW_DAYS).issubset(DAYS))
  self.assertEqual(len(DAYS),7)
 def test_catalog_all_twenty_one_source_slots(self):
  old,new=dummy_catalog()
  self.assertEqual(len(source_catalog(old,new)),21)
 def test_duplicate_asset_day_rejected(self):
  old,new=dummy_catalog();new["outputs"].append(old["outputs"][0])
  with self.assertRaisesRegex(ValueError,"DUPLICATE_SOURCE_DAY_SYMBOL"):
   source_catalog(old,new)
 def test_missing_source_rejected(self):
  old,new=dummy_catalog();new["outputs"].pop()
  with self.assertRaisesRegex(ValueError,"SOURCE_COVERAGE_GAP"):
   source_catalog(old,new)
 def test_folds_and_all_controls_share_same_heldout_count(self):
  blocks=evaluate_seven_days(dummy_rows())
  self.assertEqual(len(blocks),2*6*3)
  for item in blocks:
   self.assertNotIn(item["held_day"],item["train_days"])
   self.assertEqual(item["n"],14)
   self.assertEqual(set(item["direction"]),
      {"fixed_half","train_only_prior","price_only","price_plus_oi"})
   self.assertEqual(set(item["magnitude"]),
      {"zero","train_mean","price_only","price_plus_oi"})
  totals=summary(blocks)
  self.assertEqual(totals["15m"]["observation_count"],6*3*14)
  self.assertEqual(len(totals["60m"]["per_held_day"]),6)

if __name__=="__main__":unittest.main()
