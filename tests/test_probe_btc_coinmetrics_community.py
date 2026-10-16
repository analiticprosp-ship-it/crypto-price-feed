import json
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import probe_btc_coinmetrics_community as p

NOW=datetime(2026,10,16,12,0,tzinfo=timezone.utc)
def response(url):
    metric=url.split("metrics=")[1].split("&")[0]
    vals=["2026-10-12","2026-10-13","2026-10-14","2026-10-15"]
    return json.dumps({"data":[{"asset":"btc","time":v+"T00:00:00.000000000Z",metric:str((i+1)*2)}
                               for i,v in enumerate(vals)]}).encode()

class TestBTCCommunityProbe(unittest.TestCase):
    def test_public_proxies_not_mislabeled_exchange_flow(self):
        out,diag=p.collect(now=NOW,getter=response)
        self.assertEqual(out["coverage"]["validMetrics"],3)
        self.assertEqual(diag["status"],"DATA_OBSERVED")
        self.assertTrue(out["notExchangeInflow"])
        self.assertTrue(out["notCryptoQuantSpentAge1to3"])
        self.assertTrue(out["notVerifiedPointInTime"])
        self.assertIsNone(out.get("tradeSignal"))
        self.assertEqual(out["metrics"]["CDD"]["unit"],"BTC-days")
        self.assertEqual(out["metrics"]["SplyAct1Yr"]["unit"],"BTC")
        self.assertIn("CC BY-NC",out["attribution"])
    def test_missing_metric_kept_missing_and_diagnostic(self):
        def partial(url):
            if "SplyAct3Yr" in url:raise RuntimeError("source offline")
            return response(url)
        data,diag=p.collect(now=NOW,getter=partial)
        self.assertEqual(data["coverage"]["validMetrics"],2)
        self.assertNotIn("SplyAct3Yr",data["metrics"])
        self.assertEqual(diag["statusByMetric"]["SplyAct3Yr"]["reason"],"RuntimeError")
    def test_no_false_future_and_no_duplicate_times(self):
        raw=json.loads(response(p.endpoint("CDD","2026-10-10","2026-10-16")))
        raw["data"].append({"asset":"btc","time":"2026-10-17T00:00:00Z","CDD":"999"})
        rows,status=p.read_metric(raw,"CDD",NOW)
        self.assertEqual(status,"OK")
        self.assertEqual(len(rows),4)
        raw["data"].append(dict(raw["data"][0]))
        rows,status=p.read_metric(raw,"CDD",NOW)
        self.assertEqual(status,"DUPLICATE_DAY_IN_SOURCE")
        self.assertEqual(rows,[])
    def test_empty_payload_and_pagination_not_published(self):
        self.assertEqual(p.read_metric({"data":[]},"CDD",NOW)[1],"NO_VALID_ROWS")
        self.assertEqual(p.read_metric({"data":[],"next_page_url":"https://next.example"},"CDD",NOW)[1],
                         "PAGINATION_REQUIRED_NOT_SILENTLY_TRUNCATED")
    def test_unauthorized_or_invalid_not_fabricated(self):
        data,diag=p.collect(now=NOW,getter=lambda url:b"invalid")
        self.assertEqual(data["coverage"]["validMetrics"],0)
        self.assertEqual(diag["status"],"ALL_SOURCES_UNAVAILABLE")
        self.assertEqual(diag["statusByMetric"]["CDD"]["reason"],"INVALID_JSON")
    def test_no_future_or_negative_or_bool(self):
        raw={"data":[{"asset":"btc","time":"2026-10-15T00:00:00Z","CDD":"-1"},
                     {"asset":"btc","time":"2026-10-14T00:00:00Z","CDD":True},
                     {"asset":"btc","time":"2026-10-13T00:00:00Z","CDD":"3"}]}
        rows,status=p.read_metric(raw,"CDD",NOW)
        self.assertEqual(status,"OK")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["value"],3)
if __name__=="__main__":unittest.main()
