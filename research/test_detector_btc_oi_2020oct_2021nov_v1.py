"""Offline bounded original-source calendar tests, 2020Oct..2021Nov."""
import unittest
from research import detector_btc_oi_2020oct_2021nov_v1 as m

class BTC_Gap_Calendar(unittest.TestCase):
 def test_all_five_windows(self):
    self.assertEqual(len(m.SOURCE_WINDOWS),5)
    self.assertEqual(sum(m.COUNTS.values()),426)
 def test_2020_Q4(self):
    d=m.source_dates("2020Q4")
    self.assertEqual((len(d),d[0],d[-1]),(92,"2020-10-01","2020-12-31"))
 def test_2021_Q1(self):
    d=m.source_dates("2021Q1")
    self.assertEqual((len(d),d[0],d[-1]),(90,"2021-01-01","2021-03-31"))
 def test_2021_Q2(self):
    d=m.source_dates("2021Q2")
    self.assertEqual((len(d),d[0],d[-1]),(91,"2021-04-01","2021-06-30"))
 def test_2021_Q3(self):
    d=m.source_dates("2021Q3")
    self.assertEqual((len(d),d[0],d[-1]),(92,"2021-07-01","2021-09-30"))
 def test_2021_octnov_not_dec(self):
    d=m.source_dates("2021OCTNOV")
    self.assertEqual((len(d),d[0],d[-1]),(61,"2021-10-01","2021-11-30"))
    self.assertNotIn("2021-12-01",d)
 def test_all_426_distinct(self):
    d=[day for k in m.SOURCE_WINDOWS for day in m.source_dates(k)]
    self.assertEqual(len(d),426)
    self.assertEqual(len(set(d)),426)
    self.assertNotIn("2020-09-01",d)
    self.assertNotIn("2021-12-01",d)
 def test_external_quarter_is_rejected(self):
    with self.assertRaises(ValueError):m.source_dates("2021Q4")
 def test_no_earlier_prelisting_dates(self):
    self.assertEqual(min(day for k in m.SOURCE_WINDOWS for day in m.source_dates(k)),"2020-10-01")
 def test_no_non_btc_symbols(self):
    self.assertEqual(m.SYMBOL,"BTCUSDT")

if __name__=="__main__":
 unittest.main()
