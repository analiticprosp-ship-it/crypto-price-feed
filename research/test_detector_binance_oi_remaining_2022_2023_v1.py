"""Preregistered six-quarter Binance OI source calendar guards, offline."""
import unittest
from research import detector_binance_oi_remaining_2022_2023_v1 as m

class RemainingQuarters(unittest.TestCase):
 def test_six_quarters_only(self):
    self.assertEqual(m.QUARTERS,("2022Q2","2022Q3","2022Q4","2023Q2","2023Q3","2023Q4"))
 def test_days_q2_2022(self):
    ds,cases=m.days_and_cases("2022Q2")
    self.assertEqual((len(ds),ds[0],ds[-1]),(91,"2022-04-01","2022-06-30"))
    self.assertEqual(len(cases),273)
 def test_days_q3_2022(self):
    ds,cases=m.days_and_cases("2022Q3")
    self.assertEqual((len(ds),ds[0],ds[-1]),(92,"2022-07-01","2022-09-30"))
    self.assertEqual(len(cases),276)
 def test_days_q4_crosses_year(self):
    ds,cases=m.days_and_cases("2022Q4")
    self.assertEqual((len(ds),ds[0],ds[-1]),(92,"2022-10-01","2022-12-31"))
    self.assertEqual(len(cases),276)
 def test_2023_calendar_bounds(self):
    for quarter,start,end,count in (
        ("2023Q2","2023-04-01","2023-06-30",91),
        ("2023Q3","2023-07-01","2023-09-30",92),
        ("2023Q4","2023-10-01","2023-12-31",92)):
      ds,cases=m.days_and_cases(quarter)
      self.assertEqual((ds[0],ds[-1],len(ds),len(cases)),(start,end,count,count*3))
 def test_total_cases_no_repeats(self):
    all_cases=[]
    for q in m.QUARTERS:all_cases.extend(m.days_and_cases(q)[1])
    self.assertEqual(len(all_cases),1650)
    self.assertEqual(len(set(all_cases)),1650)
 def test_already_audited_quarters_not_repeated(self):
    for q in ("2022Q1","2023Q1","2024Q1"):
      with self.assertRaises(ValueError):m.days_and_cases(q)
 def test_bad_quarter_injection_rejected(self):
    with self.assertRaises(ValueError):m.days_and_cases("2022Q5")
 def test_missing_quality_not_silently_hidden(self):
    x={"symbol":"SOLUSDT","date_utc":"2022-07-23","calendar_quality":"PARTIAL_OR_SEMANTIC_ANOMALY",
       "status":"SOURCE_SAMPLE_PARTIAL","quality":{"missing_5m_labels":5,
       "invalid_or_missing_values":2,"duplicate_label_count":0}}
    a=m.derive_missing_dates([x],"2022Q3")
    self.assertEqual(len(a),1)
    self.assertEqual(a[0]["missing_5m_labels"],5)
    self.assertEqual(a[0]["invalid_oi_values"],2)
 def test_full_day_not_in_anomaly_calendar(self):
    x={"symbol":"ETHUSDT","date_utc":"2023-01-01","calendar_quality":"FULL_SINGLE_VALID",
       "status":"FULL_288_SOURCE_LABEL_SAMPLE"}
    self.assertEqual(m.derive_missing_dates([x],"2023Q2"),[])
 def test_all_venue_symbols_exact(self):
    self.assertEqual(m.SYMBOLS,("BTCUSDT","ETHUSDT","SOLUSDT"))

if __name__=="__main__":
 unittest.main()
