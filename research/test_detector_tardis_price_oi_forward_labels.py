#!/usr/bin/env python3
"""No-lookahead tests for vendor-timestamp futures OI + price research."""
import csv
import gzip
import io
import unittest
from research.detector_tardis_price_oi_forward_labels import (
    price_snapshots,price_asof_by_bucket,build_join,iso,FIVE_US,DELAY_US
)
from research.detector_tardis_fourday_independent_audit import usec

DAY="2026-09-01";SYM="BTCUSDT"
START=usec(DAY+"T00:00:00+00:00")

def sample(prices):
    out="exchange,symbol,timestamp,local_timestamp,open_interest,last_price,mark_price\n"
    for receipt,last,mark in prices:
        out+=f"binance-futures,{SYM},{receipt-1_000},{receipt},100,{last},{mark}\n"
    return gzip.compress(out.encode())

def oi_csv():
    out=io.StringIO(newline="")
    fields=("symbol","decision_time_utc","bucket_end_utc","open_interest",
            "asof_quality","vendor_receipt_utc","observation_age_seconds")
    writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
    for i in range(288):
        boundary=START+(i+1)*FIVE_US
        decision=boundary+DELAY_US
        writer.writerow({"symbol":SYM,"decision_time_utc":iso(decision),
           "bucket_end_utc":iso(boundary),"open_interest":"100",
           "asof_quality":"OK_VENDOR_RECEIPT",
           "vendor_receipt_utc":iso(decision-1_000_000),
           "observation_age_seconds":"1.0"})
    return out.getvalue().encode()

def full_prices():
    return [(START+(i+1)*FIVE_US,100+i,100+i) for i in range(288)]

class PriceOIAsOfTests(unittest.TestCase):
    def test_future_price_timestamp_excluded_at_first_decision(self):
        first=START+FIVE_US+DELAY_US
        rows=[(first-1,100,100),(first+1,900,900)]
        records,stats=price_snapshots(sample(rows),DAY,SYM)
        snapshots=price_asof_by_bucket(records,DAY)
        self.assertEqual(snapshots[0]["last_price"]["value"],"100")
        self.assertEqual(snapshots[1]["last_price"]["value"],"900")

    def test_no_price_before_first_valid_receipt(self):
        t=START+FIVE_US+DELAY_US+1
        data,_=price_snapshots(sample([(t,100,100)]),DAY,SYM)
        prices=price_asof_by_bucket(data,DAY)
        self.assertEqual(prices[0]["last_price"]["value"],"")
        self.assertEqual(prices[1]["last_price"]["value"],"100")

    def test_invalid_or_zero_prices_fail_closed(self):
        data,stats=price_snapshots(sample([(START+FIVE_US,0,"NaN")]),DAY,SYM)
        p=price_asof_by_bucket(data,DAY)
        self.assertEqual(p[0]["last_price"]["value"],"")
        self.assertEqual(stats["last_price_valid"],0)

    def test_stale_price_not_forward_filled_into_features(self):
        data,_=price_snapshots(sample([(START+1_000_000,100,100)]),DAY,SYM)
        p=price_asof_by_bucket(data,DAY)
        self.assertEqual(p[0]["last_price"]["value"],"")
        self.assertFalse(p[0]["last_price"]["valid"])

    def test_forward_labels_separate_and_last_bucket_censored(self):
        data,_=price_snapshots(sample(full_prices()),DAY,SYM)
        p=price_asof_by_bucket(data,DAY)
        features,labels=build_join(DAY,SYM,oi_csv(),p)
        self.assertEqual(len(features),288)
        self.assertEqual(len(labels),288)
        self.assertNotIn("future_last_price_return_5m",features[0])
        self.assertEqual(features[0]["last_price"],"100")
        self.assertAlmostEqual(float(labels[0]["future_last_price_return_5m"]),.01)
        self.assertAlmostEqual(float(labels[0]["future_last_price_return_60m"]),.12)
        self.assertEqual(labels[287]["future_last_price_return_5m"],"")
        self.assertEqual(labels[277]["future_last_price_return_60m"],"")
        self.assertNotEqual(labels[276]["future_last_price_return_60m"],"")
        self.assertEqual(sum(bool(row["future_last_price_return_5m"]) for row in labels),287)
        self.assertEqual(sum(bool(row["future_last_price_return_15m"]) for row in labels),285)
        self.assertEqual(sum(bool(row["future_last_price_return_60m"]) for row in labels),276)

    def test_only_past_returns_in_features(self):
        data,_=price_snapshots(sample(full_prices()),DAY,SYM)
        features,_=build_join(DAY,SYM,oi_csv(),price_asof_by_bucket(data,DAY))
        self.assertEqual(features[0]["past_last_price_return_5m"],"")
        self.assertAlmostEqual(float(features[1]["past_last_price_return_5m"]),.01)
        self.assertEqual(features[11]["past_last_price_return_60m"],"")
        self.assertAlmostEqual(float(features[12]["past_last_price_return_60m"]),.12)

    def test_unverified_future_oi_timestamp_rejected(self):
        data,_=price_snapshots(sample(full_prices()),DAY,SYM)
        forged=oi_csv().decode()
        forged=forged.replace(iso(START+FIVE_US+DELAY_US-1_000_000),
            iso(START+FIVE_US+DELAY_US+1_000_000),1).encode()
        with self.assertRaisesRegex(ValueError,"LOOKAHEAD_OI_RECEIPT"):
            build_join(DAY,SYM,forged,price_asof_by_bucket(data,DAY))

if __name__=="__main__":unittest.main()
