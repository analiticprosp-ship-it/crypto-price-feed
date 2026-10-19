"""Offline causal and source integrity regression tests for early Binance Tardis OI."""
import gzip,hashlib,unittest
from research import detector_tardis_binance_2020_monthly_oi_v1 as m

class FreeMonthly(unittest.TestCase):
 def test_grid_exactly_14_days(self):
  a=m.dates()
  self.assertEqual(len(a),14)
  self.assertEqual(a[0],"2019-12-01")
  self.assertEqual(a[-1],"2021-01-01")
  self.assertEqual(len(set(a)),14)
 def test_every_month_2020_explicit(self):
  for month in range(1,13):self.assertIn(f"2020-{month:02d}-01",m.dates())
 def test_exact_symbol_url(self):
  self.assertEqual(m.sample_url("2020-02-01","BTC"),
    "https://datasets.tardis.dev/v1/binance-futures/derivative_ticker/2020/02/01/BTCUSDT.csv.gz")
 def test_unapproved_date_rejected(self):
  with self.assertRaises(ValueError):m.sample_url("2020-02-02","BTC")
 def test_unapproved_coin_rejected(self):
  with self.assertRaises(ValueError):m.sample_url("2020-02-01","SOL")
 def test_prior_anchor_must_be_empty_and_sha_pinned(self):
  cases=[{"venue":"binance-futures","symbol":s,"first_free_month_after_listing":"2019-12-01",
    "status":"VERIFIED_VENDOR_RECEIPT_ASOF_EARLIEST_FREE_DAY",
    "source_sha256":"a"*64,"quality":{"fresh_5m_vendor_asof_buckets":0}} for s in ("BTCUSDT","ETHUSDT")]
  parent={"schema":"detector-tardis-earliest-free-oi-sample-v1","cases":cases}
  self.assertEqual(m.validate_pinned_prior(parent),{"BTCUSDT":"a"*64,"ETHUSDT":"a"*64})
 def test_prior_anchor_positive_oi_does_not_match(self):
  cases=[{"venue":"binance-futures","symbol":s,"first_free_month_after_listing":"2019-12-01",
    "status":"VERIFIED_VENDOR_RECEIPT_ASOF_EARLIEST_FREE_DAY",
    "source_sha256":"a"*64,
    "quality":{"fresh_5m_vendor_asof_buckets":1 if s=="BTCUSDT" else 0}} for s in ("BTCUSDT","ETHUSDT")]
  with self.assertRaises(ValueError):
   m.validate_pinned_prior({"schema":"detector-tardis-earliest-free-oi-sample-v1","cases":cases})
 def test_fresh_numeric_sample_not_first_catalog_date(self):
  source=[{"day":"2019-12-01","symbol":"BTCUSDT","status":"VENDOR_SAMPLE_SOURCE_CRC_SHA_PASS",
    "oi_quality":{"fresh_5m_vendor_asof_buckets":0}},
   {"day":"2020-01-01","symbol":"BTCUSDT","status":"VENDOR_SAMPLE_SOURCE_CRC_SHA_PASS",
    "oi_quality":{"fresh_5m_vendor_asof_buckets":150}},
   {"day":"2020-02-01","symbol":"BTCUSDT","status":"VENDOR_SAMPLE_SOURCE_CRC_SHA_PASS",
    "oi_quality":{"fresh_5m_vendor_asof_buckets":288}}]
  self.assertEqual(m.earliest_sample_with_fresh(source,"BTC"),"2020-01-01")
 def test_missing_fresh_never_invents_start(self):
  self.assertIsNone(m.earliest_sample_with_fresh([],"ETH"))
 def test_binary_gzip_measurement_keeps_empty_oi(self):
  day="2020-01-01"
  micro=1577836800000000
  plain=("exchange,symbol,timestamp,local_timestamp,open_interest\n"+
    f"binance-futures,BTCUSDT,{micro},{micro},\n").encode()
  compressed=gzip.compress(plain)
  def fetch(url,cap,timeout):
   return compressed,200
  r=m.sample_one(day,"BTC",fetch=fetch)
  self.assertEqual(r["status"],"VENDOR_SAMPLE_SOURCE_CRC_SHA_PASS")
  self.assertEqual(r["oi_quality"]["fresh_5m_vendor_asof_buckets"],0)
  self.assertEqual(r["oi_quality"]["missing_5m_buckets"],288)
  self.assertEqual(r["gzip_sha256"],hashlib.sha256(compressed).hexdigest())
 def test_invalid_http_never_fake_data(self):
  def fetch(url,cap,timeout):return b"",500
  r=m.sample_one("2020-03-01","ETH",fetch=fetch)
  self.assertEqual(r["status"],"SOURCE_UNVERIFIED")
if __name__=="__main__":
 unittest.main()
