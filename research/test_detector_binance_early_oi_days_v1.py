"""No-network guards for 2020-2024 Binance original OI sample integrity."""
import unittest
from research import detector_binance_early_oi_days_v1 as x
class Samples(unittest.TestCase):
 def test_frozen_22_cases(self):
  self.assertEqual(sum(len(q) for q in x.DATES.values()),22)
 def test_duplicate_identical_values_do_not_inflate(self):
  raw=(b"create_time,sum_open_interest,foo\n"
    b"2020-09-01 00:00:00,100,a\n2020-09-01 00:00:00,100,a\n")
  j=x.analyze_csv(raw,"2020-09-01")
  self.assertEqual(j["unique_source_5m_labels"],1)
  self.assertEqual(j["duplicate_extra_rows"],1)
  self.assertEqual(j["duplicate_oi_value_conflicts"],0)
  self.assertEqual(j["missing_5m_labels"],287)
 def test_equal_oi_different_other_field_conflicts(self):
  raw=(b"create_time,sum_open_interest,foo\n"
    b"2020-09-01 00:00:00,100,a\n2020-09-01 00:00:00,100,b\n")
  j=x.analyze_csv(raw,"2020-09-01")
  self.assertEqual(j["duplicate_complete_row_conflicts"],1)
 def test_conflicting_oi_does_not_dedup(self):
  raw=(b"create_time,sum_open_interest\n"
    b"2020-09-01 00:00:00,100\n2020-09-01 00:00:00,101\n")
  self.assertEqual(x.analyze_csv(raw,"2020-09-01")["duplicate_oi_value_conflicts"],1)
 def test_full_288(self):
  raw=b"create_time,sum_open_interest\n"+b"".join(
    f"2021-12-01 {h:02d}:{m:02d}:00,100\n".encode()
    for h in range(24) for m in range(0,60,5))
  j=x.analyze_csv(raw,"2021-12-01")
  self.assertEqual(j["unique_source_5m_labels"],288)
  self.assertEqual(j["missing_5m_labels"],0)
 def test_out_of_order_flag_not_silent_sort(self):
  raw=(b"create_time,sum_open_interest\n"
    b"2020-09-01 00:05:00,101\n2020-09-01 00:00:00,100\n")
  j=x.analyze_csv(raw,"2020-09-01")
  self.assertEqual(j["nonmonotonic_source_rows"],1)
  self.assertFalse(j["original_rows_mutated"])
if __name__=="__main__":unittest.main()
