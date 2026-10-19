"""Offline sample source lineage checks with no HTTP/R2 requests."""
import datetime as dt
import io
import zipfile
import unittest
from unittest.mock import patch
from research import detector_earliest_archive_byte_audit_v1 as m

class ArchiveSampleTests(unittest.TestCase):
    def test_timestamp_milliseconds_and_microseconds(self):
        self.assertEqual(m.parse_time("1577836800000")[0].isoformat(), "2020-01-01T00:00:00+00:00")
        self.assertEqual(m.parse_time("1735689600000000")[1], "us")
    def test_naive_source_not_pit(self):
        t,units=m.parse_time("2021-12-01 00:00:00")
        self.assertEqual(units, "naive_assumed_UTC_LABEL_ONLY")
        self.assertEqual(t.isoformat(), "2021-12-01T00:00:00+00:00")
    def test_price_no_header_and_quality(self):
        raw=b"1577836800000,5,7,3,6,100,1577840399999\n1577840400000,6,8,5,7,100,1577843999999\n"
        out=m.audit_csv("binance_usdm_1h_klines","2020-01",raw)
        self.assertEqual(out["rows"],2)
        self.assertEqual(out["source_fields"],"NO_HEADER")
    def test_bad_ohlc_fails(self):
        raw=b"1577836800000,5,4,3,6,100,1577840399999\n"
        with self.assertRaises(ValueError):
            m.audit_csv("binance_spot_1h_klines","2020-01",raw)
    def test_oi_requires_positive_and_label_only(self):
        raw=b"create_time,sum_open_interest\n2021-12-01 00:00:00,100\n2021-12-01 00:05:00,105\n"
        out=m.audit_csv("binance_usdm_metrics_oi","2021-12-01",raw)
        self.assertEqual(out["rows"],2)
        self.assertIn("naive_assumed_UTC_LABEL_ONLY",out["source_time_unit_forms"])
        with self.assertRaises(ValueError):
            m.audit_csv("binance_usdm_metrics_oi","2021-12-01",raw.replace(b",105",b",nan"))
    def test_funding_schema(self):
        raw=b"calc_time,funding_interval_hours,last_funding_rate\n1577836800000,8,-0.0001\n"
        out=m.audit_csv("binance_usdm_funding","2020-01",raw)
        self.assertEqual(out["rows"],1)
    def test_zip_crc_and_safe_csv(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w",compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("sample.csv",b"1,2,3\n")
        data,name=m.extract_zip(b.getvalue())
        self.assertEqual(name,"sample.csv")
        self.assertEqual(data,b"1,2,3\n")
    def test_publisher_sha_mismatch_protected(self):
        import hashlib
        content=b"sample-archive"
        with patch.object(m,"get_limited",return_value=(b"0"*64)+b"  file.zip"):
            check=m.publisher_hash("https://example.invalid/test.zip",hashlib.sha256(content).hexdigest())
        self.assertEqual(check["status"],"PUBLISHER_SHA256_MISMATCH")
    def test_no_aggtrades_mass_download(self):
        self.assertFalse(any("aggtrades" in name for name in m.ALLOWED_FAMILIES))

if __name__=="__main__":
    unittest.main()
