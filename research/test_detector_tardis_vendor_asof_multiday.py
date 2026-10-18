#!/usr/bin/env python3
"""Offline causal, date and quality tests for multi-day vendor snapshot features."""
import gzip
import unittest
from research.detector_tardis_vendor_asof_multiday import (
    epoch_us,parse,asof_5m,sample_url,BUCKET_US,DELAY_US
)

class MultidayVendorOI(unittest.TestCase):
    DAY="2025-01-01"
    SYM="BTCUSDT"
    def record(self,local,oi="99.7",symbol=SYM):
        return f"binance-futures,{symbol},{local-1000},{local},{oi}\n"
    def gz(self,records):
        data="exchange,symbol,timestamp,local_timestamp,open_interest\n"+records
        return gzip.compress(data.encode())

    def test_free_dates_approved_only(self):
        self.assertIn("2025/01/01",sample_url(self.DAY,self.SYM))
        with self.assertRaisesRegex(ValueError,"UNAPPROVED"):
            sample_url("2025-01-02",self.SYM)

    def test_day_bounds_and_source_counts(self):
        t=epoch_us(self.DAY)
        valid=self.record(t+1_000_000)
        out=self.record(t+86_400_000_000+500_000)
        records,counts=parse(self.gz(valid+out),self.DAY,self.SYM)
        self.assertEqual(counts["rows"],2)
        self.assertEqual(counts["valid_oi"],1)
        self.assertEqual(counts["outside_day"],1)
        self.assertEqual(len(records),1)

    def test_receipt_after_decision_cannot_enter_first_bucket(self):
        t=epoch_us(self.DAY)
        cutoff=t+BUCKET_US+DELAY_US
        records,_=parse(self.gz(self.record(cutoff+1)+""
                       +self.record(cutoff-1,oi="100")),
                       self.DAY,self.SYM)
        result,stats=asof_5m(records,self.DAY,self.SYM)
        self.assertEqual(result[0]["open_interest"],"100")
        self.assertEqual(stats["future_vendor_receipts"],0)

    def test_missing_before_first_vendor_receipt_not_filled(self):
        t=epoch_us(self.DAY)
        cutoff=t+BUCKET_US+DELAY_US
        records,_=parse(self.gz(self.record(cutoff+1)),
                        self.DAY,self.SYM)
        result,stats=asof_5m(records,self.DAY,self.SYM)
        self.assertEqual(result[0]["asof_quality"],"MISSING_VENDOR_ASOF")
        self.assertEqual(result[1]["open_interest"],"99.7")
        self.assertEqual(stats["missing"],1)

    def test_stale_quality_is_explicit(self):
        t=epoch_us(self.DAY)
        records,_=parse(self.gz(self.record(t+1_000_000)),self.DAY,self.SYM)
        result,stats=asof_5m(records,self.DAY,self.SYM)
        self.assertEqual(result[-1]["asof_quality"],"STALE_VENDOR_OVER_120S")
        self.assertGreater(stats["stale_over_120s"],0)

    def test_wrong_symbol_fails_closed(self):
        t=epoch_us(self.DAY)
        with self.assertRaisesRegex(ValueError,"SYMBOL_MISMATCH"):
            parse(self.gz(self.record(t+1_000_000,symbol="ETHUSDT")),self.DAY,self.SYM)

    def test_invalid_oi_never_replaces_valid(self):
        t=epoch_us(self.DAY)
        records,stats=parse(self.gz(self.record(t+1_000_000)+self.record(t+2_000_000,oi="NaN")),self.DAY,self.SYM)
        result,_=asof_5m(records,self.DAY,self.SYM)
        self.assertEqual(result[0]["open_interest"],"99.7")
        self.assertEqual(stats["blank_or_invalid_oi"],1)

if __name__=="__main__":unittest.main()
