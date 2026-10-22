"""Offline bounds, source clocks, ZIP CRC and SHA contract tests."""
import datetime as dt
import hashlib
import io
import unittest
import zipfile

from research.detector_h1h10_binance_flow_archive_pilot import (
    DAYS, SYMBOLS, MARKETS, DATASETS, MAX_HEAD,
    archive_url, checksum_sha, validate_5m_zip,
)


def sample(market="spot",day=DAYS[0],missing=0,wrong_clock=False):
    first=int(dt.datetime.fromisoformat(day+"T00:00:00+00:00").timestamp()*1000)
    multiplier=1000 if market=="spot" else 1
    rows=[]
    for i in range(288-missing):
        op=(first+300000*i)*multiplier
        if wrong_clock and i==10: op+=1
        end=(first+300000*(i+1))*multiplier-1
        rows.append(",".join(map(str,[op,"100","101","99","100","1",
                                     end,"100","1","1","100","0"])))
    mem=io.BytesIO()
    with zipfile.ZipFile(mem,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"BTCUSDT-5m-{day}.csv","\n".join(rows)+"\n")
    return mem.getvalue()


class BoundedBinancePilot(unittest.TestCase):
    def test_source_scope_frozen_before_holdout(self):
        self.assertEqual(len(DAYS),7)
        self.assertLess(DAYS[-1],"2026-07-01")
        self.assertEqual(7*len(MARKETS)*len(SYMBOLS)*len(DATASETS),MAX_HEAD)

    def test_exact_official_symbol_venue_paths(self):
        u=archive_url("spot","aggTrades","BTCUSDT",DAYS[0])
        self.assertEqual(u,
          "https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-05-04.zip")
        self.assertIn("/futures/um/daily/klines/ETHUSDT/5m/",
                      archive_url("um","klines","ETHUSDT",DAYS[0]))
        with self.assertRaisesRegex(ValueError,"UNAPPROVED_ARCHIVE_SCOPE"):
            archive_url("coinm","aggTrades","BTCUSDT",DAYS[0])

    def test_pub_checksum_has_exact_filename_and_sha(self):
        name="BTCUSDT-5m-2026-05-04.zip"
        data=b"abcdef"
        digest=hashlib.sha256(data).hexdigest()
        self.assertEqual(checksum_sha((digest+" *"+name).encode(),name),digest)
        with self.assertRaisesRegex(ValueError,"PUBLISHER_CHECKSUM_FILENAME_MISMATCH"):
            checksum_sha((digest+"  ETHUSDT-5m-2026-05-04.zip").encode(),name)
        with self.assertRaisesRegex(ValueError,"PUBLISHER_CHECKSUM_INVALID"):
            checksum_sha(("X"*64+"  "+name).encode(),name)

    def test_spot_microsecond_and_um_millisecond_full_288(self):
        for market,unit in [("spot","microseconds"),("um","milliseconds")]:
            with self.subTest(market=market):
                result=validate_5m_zip(sample(market),market,"BTCUSDT",DAYS[0])
                self.assertEqual(result["rows"],288)
                self.assertEqual(result["timestamp_unit"],unit)
                self.assertTrue(result["publisher_zip_crc_verified"])

    def test_official_column_header_allowed_but_arbitrary_extra_row_is_not(self):
        raw=sample()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            original=z.read(z.namelist()[0]).decode()
        for header,allowed in [
            ("open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_base_volume,taker_buy_quote_volume,ignore",True),
            ("x,y,z,w,r,t,q",False),
        ]:
            mem=io.BytesIO()
            with zipfile.ZipFile(mem,"w",compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr(f"BTCUSDT-5m-{DAYS[0]}.csv",header+"\n"+original)
            if allowed:
                result=validate_5m_zip(mem.getvalue(),"spot","BTCUSDT",DAYS[0])
                self.assertEqual(result["rows"],288)
                self.assertTrue(result["publisher_csv_header_present"])
            else:
                with self.assertRaisesRegex(ValueError,"KLINE_NOT_FULL_DAY_COUNT"):
                    validate_5m_zip(mem.getvalue(),"spot","BTCUSDT",DAYS[0])

    def test_spot_milliseconds_cannot_masquerade_as_microseconds(self):
        with self.assertRaisesRegex(ValueError,"KLINE_CLOCK_OR_PRICE_INVALID"):
            validate_5m_zip(sample("um"),"spot","BTCUSDT",DAYS[0])

    def test_gaps_not_silently_filled(self):
        with self.assertRaisesRegex(ValueError,"KLINE_NOT_FULL_DAY"):
            validate_5m_zip(sample(missing=1),"spot","BTCUSDT",DAYS[0])

    def test_bad_label_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"KLINE_CLOCK_OR_PRICE_INVALID"):
            validate_5m_zip(sample(wrong_clock=True),"spot","BTCUSDT",DAYS[0])

    def test_foreign_archive_member_rejected(self):
        raw=sample()
        with self.assertRaisesRegex(ValueError,"KLINE_ZIP_MEMBER_INVALID"):
            validate_5m_zip(raw,"spot","ETHUSDT",DAYS[0])


if __name__=="__main__":
    unittest.main()
