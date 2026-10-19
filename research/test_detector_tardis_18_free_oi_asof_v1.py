"""Offline tests for causal Tardis receipt-asof source-quality measures."""
import gzip,hashlib,unittest
from research import detector_tardis_18_free_oi_asof_v1 as a

DAY="2024-01-01"
def feed(rows):
    h="exchange,symbol,timestamp,local_timestamp,open_interest\n"
    b="".join("bybit,BTCUSDT,"+str(e)+","+str(r)+","+str(oi)+"\n" for e,r,oi in rows)
    return (h+b).encode()
BASE=1704067200000000

class Quality(unittest.TestCase):
    def test_one_fresh_then_stale(self):
        data=feed([(BASE+300_000_000,BASE+300_000_000,12)])
        s=a.audit_5m(data,DAY,"bybit","BTCUSDT")
        self.assertEqual(s["fresh_oi_asof_buckets"],1)
        self.assertEqual(s["stale_over_120s_buckets"],287)
        self.assertEqual(s["missing_asof_buckets"],0)
        self.assertEqual(s["future_vendor_receipts_consumed"],0)
    def test_must_not_use_receipts_received_after_decision(self):
        data=feed([(BASE+300_000_000,BASE+400_000_000,12)])
        s=a.audit_5m(data,DAY,"bybit","BTCUSDT")
        self.assertEqual(s["missing_asof_buckets"],1)
        self.assertEqual(s["fresh_oi_asof_buckets"],0)
    def test_no_prior_day_warmup(self):
        s=a.audit_5m(feed([(BASE+20_000_000,BASE+20_000_000,10)]),DAY,"bybit","BTCUSDT")
        self.assertEqual(s["fresh_oi_asof_buckets"],0)
        self.assertGreater(s["stale_over_120s_buckets"],0)
    def test_newer_blank_field_does_not_erase_last_oi(self):
        data=feed([(BASE+300_000_000,BASE+300_000_000,100),
                   (BASE+301_000_000,BASE+301_000_000,"")])
        s=a.audit_5m(data,DAY,"bybit","BTCUSDT")
        self.assertEqual(s["fresh_oi_asof_buckets"],1)
        self.assertEqual(s["blank_oi_rows"],1)
    def test_future_exchange_event_excluded(self):
        data=feed([(BASE+600_000_000,BASE+300_000_000,9)])
        s=a.audit_5m(data,DAY,"bybit","BTCUSDT")
        self.assertEqual(s["event_timestamp_after_vendor_receipt_rows_excluded"],1)
        self.assertEqual(s["missing_asof_buckets"],288)
    def test_bad_source_symbol_fails(self):
        data=feed([(BASE+300_000_000,BASE+300_000_000,10)])
        with self.assertRaises(ValueError):a.audit_5m(data,DAY,"okex-swap","BTCUSDT")
    def test_receipt_order_reversal_fails(self):
        data=feed([(BASE+600_000_000,BASE+600_000_000,10),
                   (BASE+300_000_000,BASE+300_000_000,11)])
        with self.assertRaises(ValueError):a.audit_5m(data,DAY,"bybit","BTCUSDT")
    def test_source_microseconds_only(self):
        with self.assertRaises(ValueError):a.parse_us("1704067200000")
        self.assertEqual(a.parse_us("1704067200000000"),BASE)
    def test_raw_and_csv_sha_must_match(self):
        plain=feed([(BASE+300_000_000,BASE+300_000_000,100)])
        binary=gzip.compress(plain)
        out=a.checked_gzip(binary,hashlib.sha256(binary).hexdigest(),
                          hashlib.sha256(plain).hexdigest())
        self.assertEqual(out,plain)
        with self.assertRaises(ValueError):
            a.checked_gzip(binary,"0"*64,hashlib.sha256(plain).hexdigest())
    def test_empty_oi_all_missing(self):
        s=a.audit_5m(feed([(BASE+300_000_000,BASE+300_000_000,"")]),DAY,"bybit","BTCUSDT")
        self.assertEqual(s["missing_asof_buckets"],288)
    def test_invalid_numeric_counted_not_used(self):
        s=a.audit_5m(feed([(BASE+300_000_000,BASE+300_000_000,"nan")]),DAY,"bybit","BTCUSDT")
        self.assertEqual(s["invalid_oi_rows"],1)
        self.assertEqual(s["missing_asof_buckets"],288)
if __name__=="__main__":
    unittest.main()
