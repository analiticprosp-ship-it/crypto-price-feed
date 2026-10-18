#!/usr/bin/env python3
import unittest
from research.detector_h1_h10_oi_availability_poll import validate_rows, new_appearances


def sample(symbol, timestamp):
    return {"symbol": symbol, "timestamp": timestamp,
            "sumOpenInterest": "100.00", "sumOpenInterestValue": "2000.00"}


def observation(timestamps, receive_ms=1792341000000, symbol="BTCUSDT"):
    return {"symbol": symbol, "response_received_ms": receive_ms,
            "rows": [{"timestamp_ms": t, "row_sha256": "0" * 64} for t in timestamps]}


class OIAvailabilityTests(unittest.TestCase):
    def test_bootstrap_not_claimed_as_first_seen(self):
        points, bootstrap = new_appearances(None, observation([1792340000000]))
        self.assertTrue(bootstrap)
        self.assertEqual(points, [])

    def test_first_seen_is_upper_bound_only(self):
        prev = observation([1792339700000], 1792340010000)
        now = observation([1792339700000, 1792340000000], 1792340320000)
        points, bootstrap = new_appearances(prev, now)
        self.assertFalse(bootstrap)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["bound_type"], "QUERY_ABSENCE_TO_FIRST_OBSERVATION")
        self.assertEqual(points[0]["last_observed_absent_ms"], 1792340010000)
        self.assertGreater(points[0]["first_observed_ms"], 1792340010000)

    def test_no_invalid_lower_bound(self):
        prev = observation([1792339700000], 1792339900000)
        now = observation([1792340000000], 1792340320000)
        points, _ = new_appearances(prev, now)
        self.assertEqual(points[0]["bound_type"], "FIRST_OBSERVATION_ONLY")
        self.assertIsNone(points[0]["last_observed_absent_ms"])

    def test_reject_duplicate_source_timestamp(self):
        values = [sample("BTCUSDT", 1792340000000)] * 2
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            validate_rows(values, "BTCUSDT", 1792341000000)

    def test_reject_future_timestamp(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_OUT_OF_RANGE"):
            validate_rows([sample("BTCUSDT", 1792343000000)], "BTCUSDT", 1792341000000)


if __name__ == "__main__":
    unittest.main()
