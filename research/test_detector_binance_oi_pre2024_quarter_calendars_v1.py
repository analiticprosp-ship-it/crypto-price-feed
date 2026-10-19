"""Offline tests for two preregistered 2022/2023 source-quarter calendars."""
import unittest
from research import detector_binance_oi_pre2024_quarter_calendars_v1 as m

def full(duplicate=0,missing=0,invalid=0,conflict=0,status="FULL_288_SOURCE_LABEL_SAMPLE"):
    d={"status":status,"quality":{
      "duplicate_label_count":duplicate,"duplicate_extra_rows":duplicate,
      "duplicate_oi_value_conflicts":0,"duplicate_complete_row_conflicts":conflict,
      "invalid_or_missing_values":invalid,"out_of_day_rows":0,
      "unaligned_source_labels":0,"nonmonotonic_source_rows":0,
      "missing_5m_labels":missing}}
    d["source_quality_class"]=m.classify(d)
    d["calendar_quality"]=m.sample_quality(d)
    return d

class QuarterCalendar(unittest.TestCase):
 def test_2022_270_independent_asset_days(self):
    x=m.quarter_cases("2022Q1")
    self.assertEqual(len(x),270)
    self.assertEqual(x[0],("BTCUSDT","2022-01-01"))
    self.assertEqual(x[-1],("SOLUSDT","2022-03-31"))
    self.assertEqual(len(set(x)),270)
 def test_2023_270_independent_asset_days(self):
    x=m.quarter_cases("2023Q1")
    self.assertEqual(len(x),270)
    self.assertEqual(x[90],("ETHUSDT","2023-01-01"))
 def test_bad_quarter_cannot_expand_workload(self):
    with self.assertRaises(ValueError):m.quarter_cases("2024Q1")
 def test_full_single(self):
    self.assertEqual(m.sample_quality(full()),"FULL_SINGLE_VALID")
 def test_exact_double_explicitly_separate(self):
    self.assertEqual(m.sample_quality(full(duplicate=288)),"FULL_EXACT_DOUBLE_VALID")
 def test_partial_labels_never_called_full(self):
    self.assertEqual(m.sample_quality(full(missing=5,status="SOURCE_SAMPLE_PARTIAL")),"PARTIAL_OR_SEMANTIC_ANOMALY")
 def test_corrupt_numeric_blocks_full(self):
    self.assertEqual(m.sample_quality(full(invalid=10)),"PARTIAL_OR_SEMANTIC_ANOMALY")
 def test_publisher_failure_blocks_quarter(self):
    self.assertEqual(m.sample_quality(full(status="PUBLISHER_PROVENANCE_UNVERIFIED")),"SOURCE_UNVERIFIED")
 def test_conflicting_duplicate_never_certified(self):
    self.assertEqual(m.sample_quality(full(duplicate=288,conflict=1)),"PARTIAL_OR_SEMANTIC_ANOMALY")
 def test_tally_keeps_partial_and_missing(self):
    a=full()
    b=full(status="SOURCE_SAMPLE_PARTIAL",missing=3)
    d=m.report_counts([a,b])
    self.assertEqual(d["days_full_single_strict"],1)
    self.assertEqual(d["days_partial_or_semantic"],1)
    self.assertEqual(d["sum_missing_5m_labels"],3)
 def test_no_side_effect_in_case_generation(self):
    self.assertEqual(m.quarter_cases("2022Q1"),m.quarter_cases("2022Q1"))
if __name__=="__main__":
 unittest.main()
