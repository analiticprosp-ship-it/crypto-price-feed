import json
import sys
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from detector_btc_exchange_flow_context import read_context
import detector_signal_engine as engine
from test_detector_signal_engine import fixtures,NOW

def test_data():
    today=datetime.fromtimestamp(NOW/1000,timezone.utc).date()
    rows=[]
    for i in range(35,0,-1):
        day=today-timedelta(days=i)
        rows.append({"dateUtc":day.isoformat(),"exchangeInflowBtc":3000.,
                     "exchangeOutflowBtc":2000.,"netflowBtc":1000.,"exchangeReserveBtc":2500000.})
    return {"schemaVersion":"btc-coinmetrics-exchange-flow-1.0",
            "generatedAt":datetime.fromtimestamp(NOW/1000,timezone.utc).isoformat(),
            "provider":"Coin Metrics Community","asset":"BTC","frequency":"1d",
            "researchOnly":True,"notTradeApproval":True,"notCohortAgeMetric":True,
            "metricSources":{s:{"sourceUrl":"https://community-api.coinmetrics.io/v4/"}
                             for s in ("FlowInExNtv","FlowOutExNtv","SplyExNtv")},
            "data":rows}

class TestExchangeContext(unittest.TestCase):
    def test_real_daily_context_separate_from_age(self):
        r=read_context(test_data(),now_ms=NOW,source_sha="abc")
        self.assertEqual(r["status"],"OBSERVED_DAILY_CONTEXT_ONLY")
        self.assertEqual(r["last7dNetflowBtc"],7000)
        self.assertEqual(r["last30dNetflowBtc"],30000)
        self.assertTrue(r["notAge1to3Years"])
        self.assertTrue(r["noEffectOnCandidateRanking"])
        self.assertFalse(r["tradePermission"])
    def test_missing_future_duplicate_and_reconciliation_guard(self):
        self.assertEqual(read_context({},now_ms=NOW)["status"],"NO_DATA")
        x=test_data();x["data"][-1]["netflowBtc"]=1001
        self.assertEqual(read_context(x,now_ms=NOW)["reason"],"NETFLOW_RECONCILIATION_FAILED")
        x=test_data();x["data"].append(dict(x["data"][-1]))
        self.assertEqual(read_context(x,now_ms=NOW)["reason"],"FUTURE_OR_DUPLICATE_DAILY_ROW")
        x=test_data();x["generatedAt"]="2036-10-16T00:00:00Z"
        self.assertEqual(read_context(x,now_ms=NOW)["reason"],"INVALID_SOURCE_PUBLICATION_TIME")
    def test_older_file_is_historical_not_current(self):
        x=test_data()
        x["generatedAt"]="2020-01-01T00:00:00Z"
        r=read_context(x,now_ms=NOW)
        self.assertEqual(r["status"],"STALE_HISTORICAL_CONTEXT_ONLY")
    def test_community_context_cannot_modify_candidate_list(self):
        price,taker=fixtures()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"market-summary.json").write_text(json.dumps(price))
            (root/"detector-rest-flow.json").write_text(json.dumps(taker))
            (root/"research").mkdir()
            (root/"research"/"btc-exchange-flows-coinmetrics.json").write_text(json.dumps(test_data()))
            with patch.object(engine,"ROOT",root),patch.object(engine.time,"time",return_value=NOW/1000):
                engine.main()
                full=json.loads((root/"detector-candidates.json").read_text())
                (root/"research"/"btc-exchange-flows-coinmetrics.json").unlink()
                engine.main()
                missing=json.loads((root/"detector-candidates.json").read_text())
            self.assertEqual(full["candidates"],missing["candidates"])
            self.assertEqual(full["coverage"],missing["coverage"])
            self.assertEqual(full["btcExchangeFlowContext"]["status"],"OBSERVED_DAILY_CONTEXT_ONLY")
            self.assertEqual(missing["btcExchangeFlowContext"]["status"],"NO_DATA")
            self.assertTrue(full["notTradeApproval"])

if __name__=="__main__":
    unittest.main()
