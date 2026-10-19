"""Offline guarantees for earliest-free Tardis catalog and receipt-safe OI."""
import unittest
from research import detector_tardis_earliest_free_oi_v1 as m
BASE=1577836800000000
def sample(*events):
    head="exchange,symbol,timestamp,local_timestamp,open_interest\n"
    return (head+"".join(f"okex-swap,BTC-USDT-SWAP,{a},{b},{v}\n" for a,b,v in events)).encode()

class EarliestFree(unittest.TestCase):
 def test_first_month_strictly_after_inception(self):
    self.assertEqual(m.first_free_date("2019-12-04T00:00:00Z"),"2020-01-01")
    self.assertEqual(m.first_free_date("2020-09-14T07:00:00Z"),"2020-10-01")
    self.assertEqual(m.first_free_date("2020-12-31T00:00:00Z"),"2021-01-01")
 def test_missing_timezone_for_catalog_fails(self):
    with self.assertRaises(ValueError):m.first_free_date("2020-01-01T00:00:00")
 def test_exact_catalog_and_data_type(self):
    obj={"datasets":{"symbols":[{"id":"BTC-USDT-SWAP","availableSince":"2019-12-04T00:00:00Z",
             "dataTypes":["derivative_ticker"]}]}}
    r=m.exact_catalog(obj,"okex-swap","BTC")
    self.assertEqual(r["id"],"BTC-USDT-SWAP")
    with self.assertRaises(ValueError):m.exact_catalog(obj,"okex-swap","ETH")
 def test_microsecond_2019_accepted(self):
    self.assertEqual(m.vendor_us("1577836800000000"),BASE)
    with self.assertRaises(ValueError):m.vendor_us("1577836800000")
 def test_asof_age_and_conservative_missing(self):
    rows=sample((BASE+300_000_000,BASE+300_000_000,"100"))
    r=m.measure(rows,"2020-01-01","okex-swap","BTC-USDT-SWAP")
    self.assertEqual(r["fresh_5m_vendor_asof_buckets"],1)
    self.assertEqual(r["stale_5m_buckets"],287)
    self.assertEqual(r["missing_5m_buckets"],0)
 def test_no_future_receipt_into_cutoff(self):
    rows=sample((BASE+400_000_000,BASE+400_000_000,"100"))
    r=m.measure(rows,"2020-01-01","okex-swap","BTC-USDT-SWAP")
    self.assertEqual(r["missing_5m_buckets"],1)
    self.assertEqual(r["fresh_5m_vendor_asof_buckets"],0)
 def test_event_after_receipt_not_used(self):
    rows=sample((BASE+600_000_000,BASE+300_000_000,"100"))
    r=m.measure(rows,"2020-01-01","okex-swap","BTC-USDT-SWAP")
    self.assertEqual(r["future_exchange_event_excluded"],1)
    self.assertEqual(r["missing_5m_buckets"],288)
 def test_open_interest_missing_preserved(self):
    rows=sample((BASE+300_000_000,BASE+300_000_000,""))
    r=m.measure(rows,"2020-01-01","okex-swap","BTC-USDT-SWAP")
    self.assertEqual(r["blank_open_interest_rows"],1)
    self.assertEqual(r["missing_5m_buckets"],288)
 def test_unordered_vendor_receipt_fails(self):
    rows=sample((BASE+600_000_000,BASE+600_000_000,"1"),
                (BASE+300_000_000,BASE+300_000_000,"1"))
    with self.assertRaises(ValueError):
        m.measure(rows,"2020-01-01","okex-swap","BTC-USDT-SWAP")
 def test_wrong_venue_rejected(self):
    rows=sample((BASE+300_000_000,BASE+300_000_000,"1"))
    with self.assertRaises(ValueError):
        m.measure(rows,"2020-01-01","bybit","BTC-USDT-SWAP")
if __name__=="__main__":
 unittest.main()
