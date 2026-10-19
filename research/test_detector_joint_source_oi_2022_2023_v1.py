"""Offline 3-coin source-calendar intersection and fail-closed provenance tests."""
import copy,datetime as dt,unittest
from research import detector_joint_source_oi_2022_2023_v1 as m

def reports():
    docs={}
    for quarter in m.PINS:
        year=int(quarter[:4]);q=int(quarter[-1]);start=dt.date(year,1+3*(q-1),1)
        e=dt.date(year+int(q==4),1 if q==4 else 1+3*q,1)
        records=[];d=start
        while d<e:
            for sym in m.SYMBOLS:
                records.append({"symbol":sym,"date_utc":d.isoformat(),
                    "publisher_checksum_status":"PUBLISHER_SHA256_MATCH",
                    "status":"FULL_288_SOURCE_LABEL_SAMPLE",
                    "calendar_quality":"FULL_SINGLE_VALID",
                    "quality":{"invalid_or_missing_values":0,
                               "missing_5m_labels":0,"duplicate_label_count":0}})
            d+=dt.timedelta(days=1)
        schema=("detector-binance-usdm-pre2024-oi-quarter-calendar-v1" if q==1
                else "detector-binance-oi-2022-2023-rest-quarter-daily-sources-v1")
        doc={"quarter":quarter,"schema":schema}
        doc["records" if q==1 else "original_source_provenance"]=records
        docs[quarter]=doc
    return docs

class JointCalendar(unittest.TestCase):
 def test_source_grid_two_full_years(self):
    d=m.date_grid();self.assertEqual(len(d),730)
    self.assertEqual(d[0],"2022-01-01");self.assertEqual(d[-1],"2023-12-31")
 def test_exact_eight_quarter_pins(self):
    self.assertEqual(len(m.PINS),8)
 def test_expected_2190_individual_sources(self):
    r=m.reports_to_calendar(reports())
    self.assertEqual(len(r),2190)
 def test_all_clean_synthetic(self):
    d=m.derive(m.reports_to_calendar(reports()))
    self.assertEqual((d["three_coin_joint_full_days"],
       d["source_complete_asset_days"],d["partial_asset_days"]),(730,2190,0))
    self.assertEqual(d["three_coin_full_source_runs_longest_first"][0]["calendar_days"],730)
 def test_one_partial_asset_excludes_entire_day(self):
    r=m.reports_to_calendar(reports())
    x=r[("2022-03-07","BTCUSDT")]
    x["status"]="SOURCE_SAMPLE_PARTIAL"
    x["calendar_quality"]="PARTIAL_OR_SEMANTIC_ANOMALY"
    x["quality"]["invalid_or_missing_values"]=1
    d=m.derive(r)
    self.assertEqual(d["three_coin_joint_full_days"],729)
    self.assertEqual(d["source_complete_asset_days"],2189)
    self.assertEqual(d["three_coin_excluded_days"],1)
    self.assertEqual(d["invalid_native_oi_values"],1)
 def test_no_partial_imputation(self):
    r=m.reports_to_calendar(reports())
    r[("2023-07-17","ETHUSDT")]["quality"]["missing_5m_labels"]=1
    r[("2023-07-17","ETHUSDT")]["status"]="SOURCE_SAMPLE_PARTIAL"
    r[("2023-07-17","ETHUSDT")]["calendar_quality"]="PARTIAL_OR_SEMANTIC_ANOMALY"
    d=m.derive(r)
    self.assertFalse(d["daily_source_quality_mask"][562]["three_coin_full_source_day"])
 def test_missing_quarter_report_rejected(self):
    docs=reports();docs.pop("2023Q4")
    with self.assertRaises(ValueError):m.reports_to_calendar(docs)
 def test_duplicate_source_asset_day_rejected(self):
    docs=reports();docs["2022Q2"]["original_source_provenance"].append(copy.deepcopy(
        docs["2022Q2"]["original_source_provenance"][0]))
    with self.assertRaises(ValueError):m.reports_to_calendar(docs)
 def test_bad_publisher_sha_fails(self):
    docs=reports();docs["2022Q1"]["records"][0]["publisher_checksum_status"]="MISMATCH"
    with self.assertRaises(ValueError):m.reports_to_calendar(docs)
 def test_bad_quarter_schema_rejected(self):
    docs=reports();docs["2022Q1"]["schema"]="invented"
    with self.assertRaises(ValueError):m.reports_to_calendar(docs)
 def test_full_without_raw_source_288_proof_rejected(self):
    docs=reports();docs["2022Q1"]["records"][0]["status"]="SOURCE_SAMPLE_PARTIAL"
    with self.assertRaises(ValueError):m.reports_to_calendar(docs)
 def test_provenance_never_turns_into_pit(self):
    d=m.derive(m.reports_to_calendar(reports()))
    self.assertEqual(d["original_exchange_release_timestamp"],"UNVERIFIED")
    self.assertEqual(d["h1h10_confirmatory_trading_gate"],
                     "DENIED_SOURCE_QUALITY_NOT_PIT")
if __name__=="__main__":unittest.main()
