"""Fail-closed offline tests: current OKX specs are never historical PIT specs."""
import copy
import unittest
from research.detector_h1h10_okx_unit_receipts import (
    SYMBOLS, SCHEMA, extract, canonical, positive_string
)

START = 1792490000000
REC = START + 800


def fixture(sym="BTC-USDT-SWAP"):
    return {"code": "0", "data": [{
        "instId": sym, "instType": "SWAP", "ctType": "linear",
        "ctVal": "0.01", "ctMult": "1", "ctValCcy": "BTC",
        "settleCcy": "USDT", "lotSz": "0.01", "tickSz": "0.1",
        "listTime": "1660000000000", "state": "live", "instFamily": "BTC-USDT",
    }]}


class UnitReceiptGuard(unittest.TestCase):
    def test_all_three_are_current_only_and_not_historical(self):
        for sym in SYMBOLS:
            value = fixture(sym)
            value["data"][0]["ctValCcy"] = sym.split("-")[0]
            r = extract(value, sym, START, REC)
            self.assertEqual(r["current_spec_completeness"], "COMPLETE_CURRENT_FIELDS")
            self.assertEqual(r["historical_version_start_at"], None)
            self.assertFalse(r["units_safe_for_historical_oi_or_flow_conversion"])
            self.assertEqual(r["causal_h1h10_rows_authorized"], 0)

    def test_missing_contract_multiplier_blocks_conversion(self):
        x = fixture()
        x["data"][0]["ctMult"] = ""
        r = extract(x, SYMBOLS[0], START, REC)
        self.assertEqual(r["current_spec_completeness"], "PARTIAL_CURRENT_FIELDS")
        self.assertFalse(r["units_safe_for_historical_oi_or_flow_conversion"])

    def test_nonpositive_and_nonfinite_multiplier_blocks(self):
        for val in ("0", "-1", "nan", "inf", "", None, "abc"):
            self.assertFalse(positive_string(val))
        self.assertTrue(positive_string("1"))

    def test_cross_venue_spot_and_foreign_symbol_rejected(self):
        x = fixture()
        x["data"][0]["instType"] = "SPOT"
        with self.assertRaisesRegex(ValueError, "INSTRUMENT_ID_OR_VENUE_MISMATCH"):
            extract(x, SYMBOLS[0], START, REC)
        with self.assertRaisesRegex(ValueError, "FOREIGN_INSTRUMENT"):
            extract(fixture("BNB-USDT-SWAP"), "BNB-USDT-SWAP", START, REC)

    def test_future_received_clock_or_future_listing_rejected(self):
        x = fixture()
        with self.assertRaisesRegex(ValueError, "BAD_HTTP_RECEIPT_CLOCK"):
            extract(x, SYMBOLS[0], REC, START)
        x["data"][0]["listTime"] = str(REC + 1)
        with self.assertRaisesRegex(ValueError, "INVALID_LISTING_TIME"):
            extract(x, SYMBOLS[0], START, REC)

    def test_non_linear_rejected(self):
        x = fixture()
        x["data"][0]["ctType"] = "inverse"
        with self.assertRaisesRegex(ValueError, "UNEXPECTED_NONLINEAR"):
            extract(x, SYMBOLS[0], START, REC)

    def test_duplicate_or_wrong_id_source_rejected(self):
        x = fixture()
        x["data"].append(copy.deepcopy(x["data"][0]))
        with self.assertRaisesRegex(ValueError, "INSTRUMENT_CARDINALITY_UNEXPECTED"):
            extract(x, SYMBOLS[0], START, REC)
        x = fixture()
        x["data"][0]["instId"] = SYMBOLS[1]
        with self.assertRaisesRegex(ValueError, "INSTRUMENT_ID_OR_VENUE_MISMATCH"):
            extract(x, SYMBOLS[0], START, REC)

    def test_untrusted_api_status_rejected(self):
        x = fixture()
        x["code"] = "50001"
        with self.assertRaisesRegex(ValueError, "SOURCE_API_NOT_SUCCESS"):
            extract(x, SYMBOLS[0], START, REC)

    def test_no_numeric_normalization_or_unit_promotion(self):
        x = fixture()
        r = extract(x, SYMBOLS[0], START, REC)
        self.assertEqual(r["native_spec"]["ctVal"], "0.01")
        self.assertEqual(r["native_spec"]["ctValCcy"], "BTC")
        self.assertEqual(len(r["native_spec_sha256"]), 64)
        self.assertNotIn("oi_usd", r)
        self.assertNotIn("contract_usdt_notional", r)


if __name__ == "__main__":
    unittest.main()
