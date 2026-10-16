"""Integration proof: BTC onchain research cannot change Detector LONG/SHORT candidates."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from detector_onchain_context import build as build_onchain
import detector_signal_engine as engine
from test_detector_signal_engine import NOW,fixtures,iso

class TestOnchainNoninterference(unittest.TestCase):
    def test_altered_onchain_input_never_changes_candidates(self):
        a,b=fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"market-summary.json").write_text(json.dumps(a))
            (root/"detector-rest-flow.json").write_text(json.dumps(b))
            source=root/"onchain-import.json"
            with patch.object(engine,"ROOT",root),patch.object(engine,"ONCHAIN_SOURCE",source),patch.object(engine.time,"time",return_value=NOW/1000):
                source.write_text(json.dumps({"schemaVersion":"detector-onchain-observations-1.0","observations":[]}))
                engine.main()
                empty=json.loads((root/"detector-candidates.json").read_text())
                self.assertEqual(empty["onchainContext"]["status"],"NO_DATA")
                self.assertTrue(empty["onchainContext"]["noEffectOnCandidateRanking"])
                original=empty["candidates"]
                source.write_text(json.dumps({"schemaVersion":"detector-onchain-observations-1.0",
                                               "observations":[{"metricId":"BTC_UNKNOWN_CHART",
                                                                "valueBtc":999999999999}]}))
                engine.main()
                uncertain=json.loads((root/"detector-candidates.json").read_text())
                self.assertEqual(uncertain["onchainContext"]["status"],"NO_VALID_OBSERVATIONS")
                self.assertEqual(original,uncertain["candidates"])
                self.assertEqual(empty["coverage"],uncertain["coverage"])
                self.assertTrue(uncertain["notTradeApproval"])
                self.assertTrue((root/"detector-onchain-context.json").exists())

if __name__=="__main__":
    unittest.main()
