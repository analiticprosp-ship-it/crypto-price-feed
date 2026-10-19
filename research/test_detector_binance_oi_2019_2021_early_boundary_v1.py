"""Offline immutable research grid and earliest-depth provenance guards."""
import unittest
from research import detector_binance_oi_2019_2021_early_boundary_v1 as m

class EarliestBoundary(unittest.TestCase):
 def test_three_symbols_entire_years(self):
    a=m.exhaustive_month_grid()
    self.assertEqual(len(a),216)
    self.assertEqual(len(set(a)),216)
 def test_first_last(self):
    a=m.exhaustive_month_grid()
    self.assertIn((m.FAMILY,"BTCUSDT","2019-01-01"),a)
    self.assertIn((m.FAMILY,"SOLUSDT","2021-12-15"),a)
 def test_month_day_generator_leap(self):
    self.assertEqual(len(m.month_dates(2020,2)),29)
    self.assertEqual(m.month_dates(2020,2)[-1],"2020-02-29")
 def test_refinement_spans_both_months(self):
    a=m.refine_requests({"BTCUSDT":"2020-09","ETHUSDT":None,"SOLUSDT":None})
    self.assertEqual(len(a),61)
    self.assertIn((m.FAMILY,"BTCUSDT","2020-08-31"),a)
    self.assertIn((m.FAMILY,"BTCUSDT","2020-09-01"),a)
 def test_first_positive_from_unsorted(self):
    rows=[{"symbol":"ETHUSDT","date":"2021-12-15","http_status":200},
          {"symbol":"ETHUSDT","date":"2021-12-01","http_status":200},
          {"symbol":"BTCUSDT","date":"2020-08-01","http_status":404}]
    o=m.earliest_positive(rows)
    self.assertEqual(o["ETHUSDT"],"2021-12")
    self.assertIsNone(o["BTCUSDT"])
 def test_no_data_not_absolute_inception(self):
    self.assertIsNone(m.earliest_positive([])["SOLUSDT"])
 def test_only_first_month_refined(self):
    got=m.refine_requests({"BTCUSDT":"2021-01","ETHUSDT":"2021-12","SOLUSDT":None})
    self.assertEqual(len(got),31+31+30+31)
 def test_refinement_never_duplicates(self):
    got=m.refine_requests({"BTCUSDT":"2021-01","ETHUSDT":"2021-01","SOLUSDT":"2021-01"})
    self.assertEqual(len(set(got)),len(got))
 def test_historical_source_family_exact(self):
    self.assertEqual(m.FAMILY,"binance_usdm_metrics_oi")
 def test_bounded_budget(self):
    self.assertLessEqual(len(m.exhaustive_month_grid())+3*62,m.MAX_HEAD)
if __name__=="__main__":
 unittest.main()
