"""Offline forensic label tests: never repair the input silently."""
import unittest
from research.detector_btc_early_oi_forensic_v1 import audit_records

class EarlyOITests(unittest.TestCase):
    def test_full_labels(self):
        data=b"create_time,sum_open_interest\n"+b"".join(
          f"2020-09-01 {h:02d}:{m:02d}:00,100\n".encode()
          for h in range(24) for m in range(0,60,5))
        result=audit_records(data)
        self.assertEqual(result["unique_valid_day_labels"],288)
        self.assertEqual(result["missing_5m_label_count"],0)
        self.assertEqual(result["duplicate_label_count"],0)
    def test_out_of_order_is_evidence_not_reordered(self):
        data=b"create_time,sum_open_interest\n2020-09-01 00:05:00,100\n2020-09-01 00:00:00,101\n"
        res=audit_records(data)
        self.assertEqual(len(res["reversal_examples"]),1)
        self.assertFalse(res["original_archive_reordered"])
    def test_duplicate_not_inflated_to_complete_day(self):
        data=b"create_time,sum_open_interest\n2020-09-01 00:00:00,100\n2020-09-01 00:00:00,100\n"
        res=audit_records(data)
        self.assertEqual(res["duplicate_extra_rows"],1)
        self.assertEqual(res["unique_valid_day_labels"],1)
        self.assertEqual(res["missing_5m_label_count"],287)
    def test_nonpositive_native_oi_captured(self):
        data=b"create_time,sum_open_interest\n2020-09-01 00:00:00,-1\n"
        self.assertEqual(audit_records(data)["invalid_oi_values"],1)
    def test_out_of_day_does_not_count(self):
        data=b"create_time,sum_open_interest\n2020-09-02 00:00:00,100\n"
        self.assertEqual(audit_records(data)["unique_valid_day_labels"],0)
        self.assertEqual(audit_records(data)["out_of_day_rows"],1)

if __name__=="__main__":
    unittest.main()
