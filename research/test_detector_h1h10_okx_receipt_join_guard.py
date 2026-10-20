"""Offline tests: never silently promote an OKX label overlap to causal PIT."""
import copy
import unittest

from research.detector_h1h10_okx_receipt_join_guard import diagnose
from research.detector_okx_3metric_forward_48h import P5, SCHEMA, SYMBOLS, METRICS


BASE = 1700000100000


def fixture():
    polls, source_reports, gates = {}, {}, {}
    for symbol in SYMBOLS:
        gates[symbol] = {
            "source_label_triples": 1,
            "causal_5m_rows_authorized": 0,
            "training_authorized": False,
            "join_grade": "SOURCE_LABEL_OVERLAP_ONLY_NO_CAUSAL_PIT",
        }
        for metric in METRICS:
            name = symbol + "|" + metric
            data = {
                "oi": {"native_open_interest": "123", "units": "NATIVE_OI_INSTRUMENT_SIZE_UNVERIFIED",
                       "bucket_anchor_time_semantics": "UNVERIFIED_BY_SOURCE_RELEASE"},
                "price": {"source_bar_open_ms": BASE, "source_bar_nominal_end_ms": BASE + P5,
                          "confirm": "1", "open": "1", "close": "2"},
                "flow": {"sell_native": "1", "buy_native": "2", "side_order": "SELL_THEN_BUY",
                         "requested_unit": "1",
                         "bucket_anchor_time_semantics": "UNVERIFIED_BY_SOURCE_RELEASE"},
            }[metric]
            endpoint = {
                "oi": "/api/v5/rubik/stat/contracts/open-interest-history",
                "price": "/api/v5/market/candles",
                "flow": "/api/v5/rubik/stat/taker-volume-contract",
            }[metric]
            polls[name] = {
                "schema": SCHEMA, "metric": metric, "symbol": symbol, "provider": "OKX",
                "source_endpoint": endpoint, "research_only": True,
                "receipt_semantics": "LOCAL_HTTP_RESPONSE_OBSERVED_NOT_EXCHANGE_PUBLICATION",
                "request_start_ms": BASE + P5 + 1000,
                "response_received_ms": BASE + P5 + 2000,
                "rows": [{"label_ms": BASE, "raw_sha256": "a" * 64, "data": data}],
            }
            source_reports[name] = {
                "response_received_ms": BASE + P5 + 2000,
                "row_count": 1, "raw_sha256": "b" * 64,
                "raw_r2_key": "research/detector-okx-3metric-forward/v1/polls/fake/"
                              + symbol + "-" + metric + ".json",
            }
    report = {
        "schema": SCHEMA, "run": "123456", "attempt": "1",
        "scope": "RESEARCH_ONLY", "trading_actions": False,
        "status": "SOURCES_ALL_RECEIVED",
        "original_exchange_first_publication": "UNVERIFIED",
        "causal_join_training": "BLOCKED", "edge_status": "EDGE_UNVALIDATED",
        "source_reports": source_reports, "coverage_gate": gates,
    }
    return report, polls


class CandidateOnly(unittest.TestCase):
    def test_same_venue_overlap_remains_noncausal(self):
        report, polls = fixture()
        result = diagnose(report, polls, BASE + 2 * P5)
        self.assertEqual(result["causal_rows_authorized"], 0)
        self.assertFalse(result["training_authorized"])
        self.assertTrue(result["unknown_exchange_first_publication"])
        for coin in SYMBOLS:
            self.assertEqual(result["candidates"][coin]["cutoff_passed_candidates"], 1)
            self.assertEqual(result["candidates"][coin]["rows"][0]["status"], "JOIN_CANDIDATE_ONLY")

    def test_receipt_after_decision_is_rejected(self):
        report, polls = fixture()
        with self.assertRaisesRegex(ValueError, "FUTURE_OR_INVALID_HTTP_RECEIPT"):
            diagnose(report, polls, BASE + P5 + 1000)

    def test_future_nominal_bar_is_not_an_observation(self):
        report, polls = fixture()
        with self.assertRaisesRegex(ValueError, "FUTURE_OR_INVALID_HTTP_RECEIPT"):
            diagnose(report, polls, BASE + P5 - 500)

    def test_unconfirmed_price_excluded(self):
        report, polls = fixture()
        polls["BTC-USDT-SWAP|price"]["rows"][0]["data"]["confirm"] = "0"
        result = diagnose(report, polls, BASE + 2 * P5)
        self.assertEqual(result["candidates"]["BTC-USDT-SWAP"]["cutoff_passed_candidates"], 0)
        self.assertEqual(result["candidates"]["BTC-USDT-SWAP"]["rejected"]["price_bar_unconfirmed"], 1)

    def test_cross_venue_source_not_accepted(self):
        report, polls = fixture()
        polls["ETH-USDT-SWAP|flow"]["provider"] = "Binance"
        with self.assertRaisesRegex(ValueError, "SAME_VENUE_SOURCE_IDENTITY_MISSING"):
            diagnose(report, polls, BASE + 2 * P5)

    def test_native_unit_promotion_rejected(self):
        report, polls = fixture()
        polls["SOL-USDT-SWAP|oi"]["rows"][0]["data"]["units"] = "USD"
        with self.assertRaisesRegex(ValueError, "OI_UNIT_OR_ANCHOR_PROMOTED"):
            diagnose(report, polls, BASE + 2 * P5)

    def test_duplicate_source_label_rejected(self):
        report, polls = fixture()
        poll = polls["BTC-USDT-SWAP|flow"]
        poll["rows"].append(copy.deepcopy(poll["rows"][0]))
        report["source_reports"]["BTC-USDT-SWAP|flow"]["row_count"] = 2
        with self.assertRaisesRegex(ValueError, "LABEL_OR_ROW_SHA_INVALID"):
            diagnose(report, polls, BASE + 2 * P5)

    def test_unauthorized_training_and_missing_stream_rejected(self):
        report, polls = fixture()
        report["causal_join_training"] = "AUTHORIZED"
        with self.assertRaisesRegex(ValueError, "PIT_AUTHORITY_OR_SCOPE_MISMATCH"):
            diagnose(report, polls, BASE + 2 * P5)
        report["causal_join_training"] = "BLOCKED"
        del polls["BTC-USDT-SWAP|oi"]
        with self.assertRaisesRegex(ValueError, "ALL_NINE_SOURCES_REQUIRED"):
            diagnose(report, polls, BASE + 2 * P5)

    def test_source_label_matching_cannot_override_original_gate(self):
        report, polls = fixture()
        report["coverage_gate"]["BTC-USDT-SWAP"]["causal_5m_rows_authorized"] = 1
        with self.assertRaisesRegex(ValueError, "COLLECTOR_SOURCE_LABEL_COUNT_OR_PIT_PROMOTED"):
            diagnose(report, polls, BASE + 2 * P5)


if __name__ == "__main__":
    unittest.main()
