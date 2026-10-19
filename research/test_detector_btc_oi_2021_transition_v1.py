"""Offline guards: exact transition requires adjacent source-authentic daily labels."""
import unittest
from research import detector_btc_oi_2021_transition_v1 as m
def make(month,dup):
 return {"date_utc":f"2021-{month:02d}-01","status":"FULL_288_SOURCE_LABEL_SAMPLE",
  "quality":{"duplicate_label_count":288 if dup else 0,
    "duplicate_extra_rows":288 if dup else 0}}
class Transition(unittest.TestCase):
 def test_anchor_grid(self):
  self.assertEqual(len(m.FIRST_DAYS),7)
 def test_identify_adjacent_bracket(self):
  rows=[make(n,n<=3) for n in range(1,8)]
  self.assertEqual(m.bracket(rows),("2021-03-01","2021-04-01"))
 def test_no_anchor_history_claim_if_missing(self):
  rows=[make(n,n<=3) for n in range(1,8)]
  rows[2]["status"]="SAMPLE_ERROR"
  with self.assertRaises(ValueError):m.bracket(rows)
 def test_no_spontaneous_duplicate_return(self):
  rows=[make(n,n in (1,2,4)) for n in range(1,8)]
  with self.assertRaises(ValueError):m.bracket(rows)
 def test_bounded_month_bracket_leap(self):
  self.assertEqual(len(m.month_days("2024-02-01")),29)
 def test_partial_conflicts_cannot_be_single(self):
  row=make(5,False);row["quality"]["duplicate_label_count"]=3
  self.assertEqual(m.quality_key(row),"MIXED_DUPLICATION")
if __name__=="__main__":
 unittest.main()
