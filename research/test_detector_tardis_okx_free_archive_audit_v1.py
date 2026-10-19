"""No-network regression guards for Tardis capture receipts and OKX vintage windows."""
import gzip, io, unittest
from unittest.mock import patch
from research import detector_tardis_okx_free_archive_audit_v1 as m

class SampleTests(unittest.TestCase):
 def meta(self):
  return {"exchange":"okex-swap","status":"CATALOG_SYMBOL_METADATA_OBSERVED",
    "matched_symbols":[{"symbol":"BTC-USDT-SWAP",
      "availableSince":"2019-12-04T00:00:00.000Z",
      "dataTypes":["derivative_ticker"]}]}
 def test_canonical_symbols(self):
  self.assertEqual(m.source_symbol("okex-swap","BTC"),"BTC-USDT-SWAP")
  self.assertEqual(m.source_symbol("bybit","SOL"),"SOLUSDT")
 def test_exact_catalog_match(self):
  self.assertEqual(m.verify_catalog(self.meta(),"okex-swap","BTC","2024-01-01")["symbol"],"BTC-USDT-SWAP")
 def test_pre_listing_is_not_missing_archive(self):
  self.assertIsNone(m.verify_catalog(self.meta(),"okex-swap","BTC","2019-01-01"))
 def test_receipt_gzip_and_5m(self):
  text=("exchange,symbol,timestamp,local_timestamp,open_interest\n"
    "okex-swap,BTC-USDT-SWAP,2024-01-01T00:00:01.000Z,2024-01-01T00:00:01.100Z,120\n"
    "okex-swap,BTC-USDT-SWAP,2024-01-01T00:05:01.000Z,2024-01-01T00:05:01.100Z,121\n")
  out=m.parse_tardis_csv(gzip.compress(text.encode()),"2024-01-01")
  self.assertEqual(out["rows"],2)
  self.assertEqual(out["unique_5m_receipt_buckets"],2)
  self.assertEqual(out["missing_open_interest_rows"],0)
  self.assertEqual(out["gzip_crc_eof_read"],"PASS")
 def test_timestamp_naive_not_pit(self):
  with self.assertRaises(ValueError):m.dt_utc("2024-01-01 01:00:00")
 def test_tampered_gzip_rejected(self):
  b=bytearray(gzip.compress(b"local_timestamp,timestamp\n"));b[-1]^=1
  with self.assertRaises((OSError,ValueError)):
   m.parse_tardis_csv(bytes(b),"2024-01-01")
 def test_wrong_catalog_never_download(self):
  d=self.meta()
  with self.assertRaises(ValueError):m.verify_catalog(d,"bybit","BTC","2024-01-01")
 def test_okx_returned_recent_not_vintage(self):
  payload=b'{"code":"0","data":[["1790000000000","12"]]}'
  with patch.object(m,"load_bytes",return_value=(payload,200)):
   item=m.okx_one("BTC",2021)
  self.assertEqual(item["status"],"OUT_OF_TARGET_OR_EMPTY_NO_DEPTH_PROOF")
  self.assertEqual(item["in_target_rows"],0)
 def test_okx_vintage_validated(self):
  payload=b'{"code":"0","data":[["1609459200000","12"]]}'
  with patch.object(m,"load_bytes",return_value=(payload,200)):
   item=m.okx_one("BTC",2021)
  self.assertEqual(item["status"],"HISTORICAL_WINDOW_SOURCE_LABELS_OBSERVED")
 def test_empty_not_reclassified_missing_history(self):
  with patch.object(m,"load_bytes",return_value=(b'{"code":"0","data":[]}',200)):
   item=m.okx_one("SOL",2021)
  self.assertEqual(item["status"],"OUT_OF_TARGET_OR_EMPTY_NO_DEPTH_PROOF")

if __name__=="__main__":
 unittest.main()
