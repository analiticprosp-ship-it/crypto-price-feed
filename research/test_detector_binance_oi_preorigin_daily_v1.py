"""No-network regressions for exhaustive pre-origin archival URL evidence."""
import unittest
from research import detector_binance_oi_preorigin_daily_v1 as m

def rows(symbol,earlier=None,unknown=None):
    earlier=set(earlier or ())
    unknown=set(unknown or ())
    all_dates=m.grid(symbol)
    output=[]
    for _,s,d in all_dates:
        code=200 if (d==m.SOURCES[s] or d in earlier) else (429 if d in unknown else 404)
        output.append({"family":m.FAMILY,"symbol":s,"date":d,"http_status":code})
    return output

def audited():
    return {"status":"FULL_288_SOURCE_LABEL_SAMPLE",
            "publisher_checksum_status":"PUBLISHER_SHA256_MATCH"}
class DailyOrigin(unittest.TestCase):
 def test_btc_exhaustive_2019_and_2020_leap(self):
    a=m.grid("BTCUSDT")
    self.assertEqual((len(a),a[0][2],a[-1][2]),(610,"2019-01-01","2020-09-01"))
    self.assertIn((m.FAMILY,"BTCUSDT","2020-02-29"),a)
 def test_eth_exhaustive_all_prior_days(self):
    a=m.grid("ETHUSDT")
    self.assertEqual((len(a),a[0][2],a[-1][2]),(1066,"2019-01-01","2021-12-01"))
 def test_sol_exhaustive_all_prior_days(self):
    a=m.grid("SOLUSDT")
    self.assertEqual(len(a),1066)
 def test_no_unknown_may_be_overwritten(self):
    x=m.judge(rows("BTCUSDT",unknown=["2019-01-01"]),"BTCUSDT",audited())
    self.assertEqual(x["status"],"INCOMPLETE_OR_SOURCE_REVISED_NO_EARLIEST_CLAIM")
    self.assertEqual(x["http_unknown"],1)
 def test_earlier_positive_forces_new_source_proof(self):
    x=m.judge(rows("BTCUSDT",earlier=["2019-08-15"]),"BTCUSDT",audited())
    self.assertEqual(x["status"],"EARLIER_HTTP200_ARCHIVE_BYTE_VALIDATED_NOT_GENESIS")
    self.assertEqual(x["first_positive_http_day"],"2019-08-15")
 def test_all_404_before_pinned_positive_is_endpoint_only(self):
    x=m.judge(rows("ETHUSDT"),"ETHUSDT",audited())
    self.assertEqual(x["status"],"COMPLETE_PREORIGIN_DAILY_ENDPOINT_404_AT_CHECK")
    self.assertEqual(x["http_404"],1065)
    self.assertEqual(x["dataset_absolute_origin"],"NOT_PROVEN")
 def test_source_sha_mismatch_never_certified(self):
    x=m.judge(rows("SOLUSDT"),"SOLUSDT",{"status":"SOURCE_SAMPLE_PARTIAL",
       "publisher_checksum_status":"PUBLISHER_SHA256_MISMATCH"})
    self.assertEqual(x["status"],"INCOMPLETE_OR_SOURCE_REVISED_NO_EARLIEST_CLAIM")
 def test_no_positive_baseline_invalid(self):
    a=rows("BTCUSDT")
    a[-1]["http_status"]=404
    x=m.judge(a,"BTCUSDT",audited())
    self.assertEqual(x["status"],"INCOMPLETE_OR_SOURCE_REVISED_NO_EARLIEST_CLAIM")
 def test_no_mixed_symbol_or_duplicate_grid(self):
    a=rows("BTCUSDT")
    a[-1]=dict(a[-2])
    with self.assertRaises(ValueError):m.judge(a,"BTCUSDT",audited())
 def test_unknown_symbol_rejected(self):
    with self.assertRaises(ValueError):m.grid("XRPUSDT")
 def test_exact_pinned_parent_evidence(self):
    row={"schema":"detector-binance-oi-2019-2021-bounded-month-day-source-depth-v1",
         "series":[{"symbol":"BTCUSDT","first_http_200_tested_date":"2020-09-01",
                    "observed_http_grade":"EARLIEST_SHA_CRC_SOURCE_AUDITED"}]}
    a=m.pinned_baseline(row,"BTCUSDT")
    self.assertEqual(a["first_verified_positive"],"2020-09-01")
 def test_different_pinned_date_fails(self):
    row={"schema":"detector-binance-oi-2019-2021-bounded-month-day-source-depth-v1",
         "series":[{"symbol":"BTCUSDT","first_http_200_tested_date":"2020-08-30",
                    "observed_http_grade":"EARLIEST_SHA_CRC_SOURCE_AUDITED"}]}
    with self.assertRaises(ValueError):m.pinned_baseline(row,"BTCUSDT")

if __name__=="__main__":
    unittest.main()
