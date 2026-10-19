#!/usr/bin/env python3
"""Offline tests for missing 5m labels and independent day continuity."""
import csv,datetime as dt,io,unittest,zipfile
from research.detector_metrics_exact_gap_ledger import analyze_one_csv,calendar

def mockzip(drop=None,repeat=None):
    buf=io.StringIO();w=csv.writer(buf)
    w.writerow(["timestamp_utc","sum_open_interest","sum_open_interest_valid"])
    start=dt.datetime(2026,1,1,tzinfo=dt.timezone.utc)
    for i in range(3*288):
        if i==drop:continue
        t=start+dt.timedelta(minutes=5*i)
        w.writerow([t.isoformat(),"123.00","1"])
        if i==repeat:w.writerow([t.isoformat(),"123.00","1"])
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as z:z.writestr("sample.csv",buf.getvalue())
    b.seek(0)
    return zipfile.ZipFile(b)

class ExactGaps(unittest.TestCase):
    def test_all_three_days_full_and_contiguous(self):
        with mockzip() as z:
            result=analyze_one_csv(z,"sample.csv",dt.date(2026,1,1),dt.date(2026,1,3))
        self.assertEqual(result["complete_5m_days"],3)
        self.assertEqual(result["missing_5m_slots"],0)
        self.assertEqual(result["longest_consecutive_full_days"],3)
        self.assertEqual(result["longest_streak_first_day"],"2026-01-01")
        self.assertEqual(result["longest_streak_last_day"],"2026-01-03")
    def test_one_gap_exact_slot_not_filled(self):
        with mockzip(drop=300) as z:
            result=analyze_one_csv(z,"sample.csv",dt.date(2026,1,1),dt.date(2026,1,3))
        self.assertEqual(result["complete_5m_days"],2)
        self.assertEqual(result["missing_5m_slots"],1)
        self.assertEqual(result["incomplete_or_missing_days"],1)
        self.assertEqual(result["anomalous_days"][0]["first_missing_slots"],["01:00"])
        self.assertEqual(result["longest_consecutive_full_days"],1)
    def test_duplicate_does_not_inflate_bucket_count(self):
        with mockzip(repeat=3) as z:
            result=analyze_one_csv(z,"sample.csv",dt.date(2026,1,1),dt.date(2026,1,3))
        self.assertEqual(result["duplicate_label_rows"],1)
        self.assertEqual(result["missing_5m_slots"],0)
    def test_calendar_inclusive_boundaries(self):
        self.assertEqual(len(calendar(dt.date(2026,1,30),dt.date(2026,2,2))),4)

if __name__=="__main__":unittest.main()
