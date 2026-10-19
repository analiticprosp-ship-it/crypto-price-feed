#!/usr/bin/env python3
"""Tests: original metrics labels, masks, and duplicate-aware source lineage."""
import collections
import io
import json
import unittest
import zipfile

from research.detector_metrics_413day_source_lineage import (
 label,numeric,compare_counts,metrics_labels,sorted_labels,json_member
)

def pack(items):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as z:
        for k,v in items.items():z.writestr(k,v)
    b.seek(0)
    return zipfile.ZipFile(b)

class SourceLineage(unittest.TestCase):
    def test_naive_source_timestamp_is_explicitly_flagged(self):
        ts,naive=label("2026-09-01 00:05:00")
        self.assertEqual(ts,"2026-09-01T00:05:00+00:00")
        self.assertTrue(naive)
        self.assertEqual(label("2026-09-01T00:05:00+00:00")[1],False)
    def test_numeric_masks_nan(self):
        self.assertIsNone(numeric(""))
        self.assertIsNone(numeric("NaN"))
        self.assertEqual(numeric("123.0"),"123.0")
    def test_multiset_compare_detects_duplicate_and_value_mutation(self):
        raw=collections.Counter({("2026-01-01T00:00:00+00:00","1.0"):2})
        same=collections.Counter(raw)
        self.assertTrue(compare_counts(raw,same)["numeric_and_label_multiset_match"])
        wrong=collections.Counter({("2026-01-01T00:00:00+00:00","2.0"):2})
        self.assertEqual(compare_counts(raw,wrong)["raw_valid_absent_from_sorted"],2)
        self.assertFalse(compare_counts(raw,wrong)["numeric_and_label_multiset_match"])
    def test_raw_source_and_masked_sort_truly_match(self):
        raw="source_date,create_time,sum_open_interest\n2026-01-01,2026-01-01 00:00:00,100\n2026-01-01,2026-01-01 00:05:00,101\n"
        sorted_csv="timestamp_utc,sum_open_interest,sum_open_interest_valid\n2026-01-01T00:00:00+00:00,100,1\n2026-01-01T00:05:00+00:00,101,1\n"
        with pack({"BTCUSDT_metrics_5m.csv":raw}) as original:
            with pack({"BTCUSDT_research_5m.csv":sorted_csv}) as derived:
                left,info=metrics_labels(original,"BTCUSDT")
                right,count=sorted_labels(derived,"BTCUSDT")
                self.assertTrue(compare_counts(left,right)["numeric_and_label_multiset_match"])
                self.assertEqual(info["naive_utc_labels"],2)
                self.assertEqual(count["sorted_rows"],2)
    def test_masked_record_is_not_treated_as_numeric(self):
        raw="source_date,create_time,sum_open_interest\n2026-01-01,2026-01-01 00:00:00,NaN\n"
        sorted_csv="timestamp_utc,sum_open_interest,sum_open_interest_valid\n2026-01-01T00:00:00+00:00,,0\n"
        with pack({"BTCUSDT_metrics_5m.csv":raw}) as original:
            with pack({"BTCUSDT_research_5m.csv":sorted_csv}) as derived:
                left,_=metrics_labels(original,"BTCUSDT")
                right,_=sorted_labels(derived,"BTCUSDT")
                self.assertEqual(sum(left.values()),0)
                self.assertEqual(sum(right.values()),0)
    def test_manifest_is_not_inferred_from_filename(self):
        with pack({"manifest.json":json.dumps({"source_run_id":123})}) as f:
            self.assertEqual(json_member(f,"manifest.json")["source_run_id"],123)
            with self.assertRaisesRegex(ValueError,"REQUIRED_ZIP_MEMBER_NOT_PRESENT"):
                json_member(f,"provenance.json")

if __name__=="__main__":unittest.main()
