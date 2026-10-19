"""Offline safety tests: no live API, no venue substitution, no fake history."""
import unittest
from unittest.mock import patch
from research import detector_multivenue_source_depth_v1 as m

class MultiVenueDepthTests(unittest.TestCase):
    def test_frozen_source_scope(self):
        self.assertEqual(m.SYMBOLS,("BTC","ETH","SOL"))
        self.assertEqual(len(m.TARDIS_EXCHANGES),5)
        self.assertEqual(len(m.VINTAGE_YEARS),7)
    def test_catalog_filters_grouped_and_unrelated(self):
        x={"datasets":{"symbols":[
            {"id":"BTCUSDT","availableSince":"2020-01-01","availableTo":"2026-10-01","dataTypes":["derivative_ticker","trades"]},
            {"id":"SOL-USDT-SWAP","availableSince":"2021-01-01","dataTypes":["trades"]},
            {"id":"SPOT","dataTypes":["trades"]},
            {"id":"DOGEUSDT","dataTypes":["quotes"]}]}}
        got=m.trim_catalog("binance-futures",x)
        self.assertEqual(got["matched_symbol_count"],2)
        self.assertEqual(got["matched_symbols"][0]["symbol"],"BTCUSDT")
        self.assertEqual(got["original_exchange_publication"],"UNVERIFIED")
    def test_catalog_schema_fail_closed(self):
        self.assertEqual(m.trim_catalog("bybit",{"datasets":{"symbols":{}}})["status"],
                         "SYMBOLS_METADATA_NOT_ARRAY")
        self.assertEqual(m.trim_catalog("bybit",{})["status"],
                         "DATASET_METADATA_MISSING_OR_SCHEMA_DIFFERENT")
        with self.assertRaises(ValueError):m.trim_catalog("bybit",[])
    def test_bybit_vintage_valid_rows_only(self):
        def fake(url,cap):
            self.assertIn("startTime=",url)
            return {"http":200,"status":"HTTP_JSON_RECEIVED","payload":{
               "retCode":0,"result":{"list":[{"timestamp":"1577836800000","openInterest":"1200"}]}}}
        with patch.object(m,"get_json",side_effect=fake):
            result=m.bybit_vintage("BTC",2020)
        self.assertEqual(result["status"],"BOUNDED_HISTORICAL_VALUES_OBSERVED")
        self.assertEqual(result["first_available_at"],"NOT_PROVEN")
    def test_bybit_refuses_wrong_year_rows(self):
        with patch.object(m,"get_json",return_value={"http":200,"status":"HTTP_JSON_RECEIVED",
              "payload":{"retCode":0,"result":{"list":[{"timestamp":"1577836800000","openInterest":"1200"}]}}}):
            result=m.bybit_vintage("BTC",2024)
        self.assertEqual(result["status"],"ROW_TIME_OR_VALUE_INVALID")
    def test_bybit_empty_is_not_absence_proof(self):
        with patch.object(m,"get_json",return_value={"http":200,"status":"HTTP_JSON_RECEIVED",
              "payload":{"retCode":0,"result":{"list":[]}}}):
            result=m.bybit_vintage("SOL",2020)
        self.assertEqual(result["status"],"NO_ROWS_IN_TEST_WINDOW_NOT_EARLIEST_PROOF")
    def test_okx_latest_never_claims_start(self):
        with patch.object(m,"get_json",return_value={"http":200,"status":"HTTP_JSON_RECEIVED",
              "payload":{"code":"0","data":[["1760000000000","135.75","1"]]}}):
            x=m.okx_latest("ETH","5m")
        self.assertEqual(x["historical_start"],"NOT_ESTABLISHED")
        self.assertEqual(x["original_publication_at"],"UNVERIFIED")
    def test_okx_provider_failure_distinct(self):
        with patch.object(m,"get_json",return_value={"http":200,"status":"HTTP_JSON_RECEIVED",
              "payload":{"code":"50001","msg":"invalid"}}):
            self.assertEqual(m.okx_latest("SOL","1D")["status"],
                             "PROVIDER_REJECTED_OR_UNAVAILABLE")
    def test_provider_network_error_not_zero_history(self):
        with patch.object(m,"get_json",return_value={"http":451,"status":"HTTP_ERROR_NOT_HISTORY_PROOF"}):
            self.assertEqual(m.tardis_catalog("bybit")["status"],
                             "CATALOG_UNAVAILABLE_NOT_DATA_ABSENCE")
    def test_invalid_numeric(self):
        self.assertFalse(m.maybe_numeric("nan"))
        self.assertFalse(m.maybe_numeric("infinity"))
        self.assertFalse(m.maybe_numeric(""))
        self.assertTrue(m.maybe_numeric("0"))
if __name__=="__main__":
    unittest.main()
