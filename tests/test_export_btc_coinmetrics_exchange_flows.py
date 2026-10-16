import json
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from export_btc_coinmetrics_exchange_flows import get_export,decode_rows,source_url

NOW=datetime(2026,10,16,7,0,tzinfo=timezone.utc)
def getter(url):
    metric=url.split("metrics=")[1].split("&")[0]
    vals={"FlowInExNtv":[(14,2200),(15,1800)],
          "FlowOutExNtv":[(14,1700),(15,2400)],
          "SplyExNtv":[(14,2500000),(15,2499400)]}[metric]
    return json.dumps({"data":[{"asset":"btc","time":f"2026-10-{day:02d}T00:00:00Z",metric:str(v)}
                               for day,v in vals]}).encode()

class TestFreeBTCExchangeExport(unittest.TestCase):
    def test_source_is_community_and_yesterday_not_today(self):
        url=source_url("FlowInExNtv",NOW)
        self.assertIn("community-api.coinmetrics.io",url)
        self.assertIn("end_time=2026-10-15",url)
    def test_real_flow_and_same_day_netflow_only(self):
        r,d=get_export(now=NOW,fetch=getter)
        self.assertEqual(len(r["data"]),2)
        self.assertEqual(r["data"][0]["netflowBtc"],500)
        self.assertEqual(r["data"][1]["netflowBtc"],-600)
        self.assertEqual(r["data"][1]["exchangeReserveBtc"],2499400)
        self.assertTrue(r["notCohortAgeMetric"])
        self.assertTrue(r["notProofOfExecutedSales"])
        self.assertTrue(r["notImportedToDetectorCandidates"])
        self.assertEqual(d["metricResults"]["FlowInExNtv"]["status"],"OBSERVED")
    def test_no_flow_not_fake_netflow(self):
        def partial(url):
            if "FlowOutExNtv" in url:raise PermissionError("no source")
            return getter(url)
        r,d=get_export(now=NOW,fetch=partial)
        self.assertIsNone(r["data"][0]["netflowBtc"])
        self.assertEqual(d["metricResults"]["FlowOutExNtv"]["status"],"NO_DATA")
    def test_invalid_future_dup_and_negative(self):
        metric="FlowInExNtv"
        raw={"data":[{"asset":"btc","time":"2026-10-15T00:00:00Z",metric:"20"},
                     {"asset":"btc","time":"2026-10-16T00:00:00Z",metric:"1000000"}]}
        rows,status=decode_rows(json.dumps(raw).encode(),metric,NOW)
        self.assertEqual(status,"OK")
        self.assertEqual(len(rows),1)
        raw["data"].append({"asset":"btc","time":"2026-10-15T00:00:00Z",metric:"10"})
        self.assertEqual(decode_rows(json.dumps(raw).encode(),metric,NOW)[1],"DUPLICATED_DAY")
        raw["data"]=[{"asset":"btc","time":"2026-10-15T00:00:00Z",metric:"-10"}]
        self.assertEqual(decode_rows(json.dumps(raw).encode(),metric,NOW)[1],"NO_VALID_DAILY_ROWS")

if __name__=="__main__":
    unittest.main()
