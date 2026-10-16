import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from probe_coinmetrics_btc_catalog import extract

class TestCommunityCatalog(unittest.TestCase):
    def test_catalog_real_metric_schema(self):
        sample={"data":[{"asset":"btc","metrics":[
            {"metric":"TxCnt","frequencies":[{"frequency":"1d","min_time":"2009-01-03","max_time":"2026-10-15"}]},
            {"metric":"SplyAct1Yr","frequencies":[{"frequency":"1d"}]}]}]}
        result,status=extract(sample)
        self.assertEqual(status,"OK")
        self.assertEqual(result["availableMetricCount"],2)
        self.assertTrue(result["candidateCheck"]["SplyAct1Yr"])
        self.assertFalse(result["candidateCheck"]["CDD"])
        self.assertTrue(result["relevant"])
    def test_invalid_catalog_does_not_guess(self):
        self.assertEqual(extract({"data":[]})[1],"BTC_METRICS_NOT_IN_CATALOG")
        self.assertEqual(extract({"message":"unavailable"})[1],"INVALID_CATALOG_RESPONSE")
        self.assertEqual(extract({"data":[{"asset":"btc","metrics":[{"metric":"./evil"}]}]})[1],
                         "BTC_CATALOG_NO_VALID_METRIC_IDS")

if __name__=="__main__":
    unittest.main()
