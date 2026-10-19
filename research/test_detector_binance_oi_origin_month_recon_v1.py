"""No-network guards on Binance first observed month boundary claims."""
import unittest
from research import detector_binance_oi_origin_month_recon_v1 as m

class SourceOrigin(unittest.TestCase):
 def test_24_months(self):
  self.assertEqual(len(m.YEAR_MONTHS),24)
  self.assertEqual(m.YEAR_MONTHS[0],(2020,1))
  self.assertEqual(m.YEAR_MONTHS[-1],(2021,12))
 def test_february_2020_leap(self):
  d=m.month_dates(2020,2)
  self.assertEqual((len(d),d[-1]),(29,"2020-02-29"))
 def test_february_2021(self):
  self.assertEqual(m.calendar_probes(2021,2),("2021-02-01","2021-02-15","2021-02-28"))
 def test_previous_month_cross_year(self):
  self.assertEqual(m.previous_month(2021,1),(2020,12))
 def test_url_is_exact(self):
  self.assertIn("/BTCUSDT/BTCUSDT-metrics-2020-09-01.zip",m.url_for("BTCUSDT","2020-09-01"))
 def test_unlisted_symbol_rejected(self):
  with self.assertRaises(ValueError):m.url_for("DOGEUSDT","2021-01-01")
 def test_no_source_positive_cannot_infer_absence(self):
  def fake(symbol,day):return {"http":404,"state":"404_AT_CHECK_TIME"}
  x=m.run_symbol("BTCUSDT",head=fake)
  self.assertEqual(x["status"],"NO_POSITIVE_MONTH_IN_BOUNDED_SAMPLES")
  self.assertEqual(len(x["month_sample_probes"]),72)
  self.assertEqual(x["original_exchange_publication"],"UNVERIFIED")
 def test_early_first_day_full_scan(self):
  def fake(sym,day):
   positive=day>="2020-09-09"
   return {"http":200 if positive else 404,"state":"SOURCE_ARCHIVE_EXISTS" if positive else "404_AT_CHECK_TIME"}
  def audit(sym,day):
   return {"status":"FULL_288_SOURCE_LABEL_SAMPLE","publisher_checksum_status":"PUBLISHER_SHA256_MATCH"}
  x=m.run_symbol("BTCUSDT",head=fake,byte_audit=audit)
  self.assertEqual(x["earliest_full_two_month_scan_positive"],"2020-09-09")
  self.assertEqual(x["status"],"FIRST_OBSERVED_ARCHIVE_BYTES_VERIFIED")
  self.assertEqual(x["historical_absolute_start"],"NOT_PROVEN")
 def test_unverified_first_zip_not_claimed(self):
  def fake(sym,day):
   return {"http":200,"state":"SOURCE_ARCHIVE_EXISTS"}
  def audit(sym,day):return {"status":"SOURCE_SAMPLE_PARTIAL","publisher_checksum_status":"PUBLISHER_SHA256_MISMATCH"}
  x=m.run_symbol("ETHUSDT",head=fake,byte_audit=audit)
  self.assertEqual(x["status"],"FIRST_ARCHIVE_SOURCE_NOT_FULLY_VERIFIED")
 def test_unknown_head_does_not_become_200(self):
  def fake(sym,day):return {"http":429,"state":"HTTP_ACCESS_OR_SOURCE_UNVERIFIED"}
  x=m.run_symbol("SOLUSDT",head=fake)
  self.assertEqual(x["status"],"NO_POSITIVE_MONTH_IN_BOUNDED_SAMPLES")
  self.assertEqual(len(x["day_boundary_probes"]),0)

if __name__=="__main__":
 unittest.main()
