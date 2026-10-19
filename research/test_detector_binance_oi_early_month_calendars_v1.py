"""Offline 123-day source calendar and immutable-duplicate quality guards."""
import unittest
from research import detector_binance_oi_early_month_calendars_v1 as m

def record(duplicates=0,missing=0,status="FULL_288_SOURCE_LABEL_SAMPLE"):
 return {"status":status,"quality":{
 "duplicate_label_count":duplicates,"duplicate_extra_rows":duplicates,
 "duplicate_oi_value_conflicts":0,"duplicate_complete_row_conflicts":0,
 "missing_5m_labels":missing}}

class Calendar(unittest.TestCase):
 def test_days_2020_leap(self):
  self.assertEqual(len(m.month_days(2020,2)),29)
 def test_september_2020_exact(self):
  self.assertEqual(m.month_days(2020,9)[0],"2020-09-01")
  self.assertEqual(m.month_days(2020,9)[-1],"2020-09-30")
 def test_cases_exact_nonrepeat(self):
  self.assertEqual(len(m.cases()),123)
  self.assertEqual(len(set(m.cases())),123)
 def test_regular_288_labels_single(self):
  self.assertEqual(m.classify(record()),"288_UNIQUE_SINGLE_ROWS_FULL_DAY")
 def test_exact_identical_doubles_no_silent_removal(self):
  self.assertEqual(m.classify(record(288)),"288_UNIQUE_IDENTICAL_DOUBLES_FULL_DAY")
 def test_partial_duplicate_flags(self):
  self.assertEqual(m.classify(record(8)),"SOURCE_DUPLICATE_REGIME_PARTIAL")
 def test_quality_partial_not_certified(self):
  self.assertEqual(m.classify(record(0,5,"SOURCE_SAMPLE_PARTIAL")),"SOURCE_UNVERIFIED_OR_PARTIAL")
 def test_total_missing_source(self):
  rows=[{**record(0), "source_quality_class":"288_UNIQUE_SINGLE_ROWS_FULL_DAY"},
        {**record(288,3,"SOURCE_SAMPLE_PARTIAL"),"source_quality_class":"SOURCE_UNVERIFIED_OR_PARTIAL"}]
  t=m.totals(rows)
  self.assertEqual(t["missing_5m_labels"],3)
  self.assertEqual(t["selected_source_days"],2)
 def test_failed_publisher_not_covered(self):
  x=record(0,0,"PUBLISHER_PROVENANCE_UNVERIFIED")
  self.assertEqual(m.classify(x),"SOURCE_UNVERIFIED_OR_PARTIAL")
if __name__=="__main__":
 unittest.main()
