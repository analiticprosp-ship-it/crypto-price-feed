"""Offline checks of native Decimal OI equality in duplicated historical labels."""
import unittest
from research.detector_btc_2020_oi_duplicate_value_audit_v1 import audit

class DuplicateValues(unittest.TestCase):
    def test_exact_identical_pairs(self):
        x=b"create_time,sum_open_interest,foo\n2020-09-01 00:00:00,12.000,a\n2020-09-01 00:00:00,12.000,a\n"
        r=audit(x)
        self.assertEqual(r["pairs_same_native_oi"],1)
        self.assertEqual(r["pairs_same_complete_csv_row"],1)
        self.assertTrue(r["all_labels_exactly_twice"])
    def test_numeric_equal_but_other_fields_differ(self):
        x=b"create_time,sum_open_interest,foo\n2020-09-01 00:00:00,12.0,a\n2020-09-01 00:00:00,12.00,b\n"
        r=audit(x)
        self.assertEqual(r["pairs_same_native_oi"],1)
        self.assertEqual(r["pairs_same_complete_csv_row"],0)
        self.assertEqual(len(r["non_oi_field_discrepancy_examples"]),1)
    def test_conflicting_values_do_not_merge(self):
        x=b"create_time,sum_open_interest\n2020-09-01 00:00:00,12\n2020-09-01 00:00:00,13\n"
        r=audit(x)
        self.assertEqual(r["pairs_same_native_oi"],0)
        self.assertEqual(len(r["conflicting_native_oi_example"]),1)
    def test_group_size_three_not_accepted(self):
        x=b"create_time,sum_open_interest\n"+(b"2020-09-01 00:00:00,12\n"*3)
        r=audit(x)
        self.assertFalse(r["all_labels_exactly_twice"])
    def test_nonfinite_rejected(self):
        x=b"create_time,sum_open_interest\n2020-09-01 00:00:00,nan\n"
        with self.assertRaises(ValueError): audit(x)
if __name__=="__main__":
    unittest.main()
