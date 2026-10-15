"""Root-cause diagnostics contract: HTTP failures must be visible without fake data."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import update_detector_rest_flow as mod

class TestDetectorSourceDiagnostics(unittest.TestCase):
    def test_http_error_codes_safe_and_bounded(self):
        e=HTTPError("https://example.org/test?token=SECRET",403,"Forbidden",None,None)
        self.assertEqual(mod.http_error_class(e),"HTTP_403")
        self.assertNotIn("SECRET",mod.http_error_class(e))
        self.assertEqual(mod.http_error_class(URLError("timeout")),"URL_str")

    def test_invalid_provider_payload_distinguished(self):
        self.assertEqual(mod.taker_result({"code":-1003,"msg":"provider failure"},1800000000000)["reason"],"BINANCE_API_-1003")
        self.assertEqual(mod.oi_result({"retCode":10006,"retMsg":"rate limit"},"SOL",1800000000000)["reason"],"BYBIT_API_10006")

    def test_no_valid_data_writes_diagnostics_not_feed(self):
        now=1800000000000
        bad={"symbol":"SOL","taker":{"status":"NO_DATA","reason":"HTTP_OR_PARSE_ERROR","error":"HTTP_403"},
             "openInterest":{"status":"NO_DATA","reason":"HTTP_OR_PARSE_ERROR","error":"HTTP_429"}}
        snap={"generatedAt":"2027-01-15T08:00:00+00:00","coverage":{"sourceObservationsValid":0},"instruments":{"SOL":bad}}
        with tempfile.TemporaryDirectory() as td:
            diag=Path(td)/"diagnostics.json"
            flow=Path(td)/"detector-rest-flow.json"
            with patch.object(mod,"DIAG",diag),patch.object(mod,"OUT",flow),patch.object(mod,"build",return_value=snap),patch.object(mod,"symbols_from_universe",return_value=["SOL"]),patch.object(mod.time,"time",return_value=now/1000):
                with self.assertRaisesRegex(RuntimeError,"ALL_SOURCES_UNAVAILABLE"):
                    mod.main()
            obj=json.loads(diag.read_text())
            self.assertEqual(obj["status"],"NO_VALID_SOURCE_OBSERVATIONS")
            self.assertEqual(obj["sources"]["SOL"]["taker"]["error"],"HTTP_403")
            self.assertTrue(obj["noTradeSignal"])
            self.assertFalse(flow.exists())

if __name__=="__main__":
    unittest.main()
