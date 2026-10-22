"""No-repainting, timestamps, gaps, and parity-warning tests for N-W pilot."""
import copy
import unittest
from scripts.build_nadaraya_watson_research import (
    TF_MS, MIN_BARS, MODEL_ID, UNVERIFIED, build, calculate,
)
P = TF_MS["1H"]
NOW = 201*P+5*60_000


def candles(n=100, step=0.8):
    return [
        {"t": (200-n+i)*P, "o": 100+i*step, "h": 102+i*step,
         "l": 99+i*step, "c": 101+i*step}
        for i in range(n)
    ]


class TestNadarayaWatson(unittest.TestCase):
    def test_causal_envelope_and_params(self):
        r = calculate(candles(), "1H", NOW)
        self.assertEqual(r["status"], "MODEL_OBSERVED_UNVERIFIED_PARITY")
        self.assertTrue(r["lower"] < r["center"] < r["upper"])
        self.assertEqual(r["modelID"], MODEL_ID)
        self.assertEqual(r["parityStatus"], UNVERIFIED)
        self.assertFalse(r["repainting"])
        self.assertTrue(r["closedCandleOnly"])
        self.assertEqual(r["inputCount"], MIN_BARS)
        self.assertFalse(r["crossBelowLower"])

    def test_future_bar_and_live_candle_ignored(self):
        seq = candles()
        base = calculate(seq, "1H", NOW)
        future = {"t": 201*P, "o": 1000, "h": 1200, "l": 900, "c": 1100}
        test = calculate(seq + [future], "1H", NOW)
        self.assertEqual(base["center"], test["center"])
        self.assertEqual(base["upper"], test["upper"])

    def test_historical_prefix_is_future_independent(self):
        seq = candles()
        past_now = NOW - 11*P
        baseline = calculate(seq[:-10], "1H", past_now)
        with_future = calculate(seq, "1H", past_now)
        self.assertEqual(baseline["center"], with_future["center"])
        self.assertEqual(baseline["upper"], with_future["upper"])
        self.assertEqual(baseline["barClosedAtMs"], with_future["barClosedAtMs"])

    def test_gap_or_insufficient_candles_is_unavailable(self):
        short = calculate(candles(MIN_BARS-1), "1H", NOW)
        self.assertEqual(short["reason"], "INSUFFICIENT_CLOSED_HISTORY")
        seq = candles()
        seq.pop(50)
        gap = calculate(seq, "1H", NOW)
        self.assertEqual(gap["reason"], "GAPPED_CANDLE_HISTORY")

    def test_stale_is_unavailable(self):
        r = calculate(candles(), "1H", NOW+3*P)
        self.assertEqual(r["status"], "NO_DATA")
        self.assertEqual(r["reason"], "STALE_LAST_CLOSED_BAR")

    def test_invalid_bars_are_unavailable_not_filled(self):
        seq=candles()
        seq[-3]["c"] = float("nan")
        r = calculate(seq, "1H", NOW)
        self.assertEqual(r["status"], "NO_DATA")

    def test_missing_block_does_not_fabricate(self):
        m = build({"instruments":{"BTC":{"perpetual":{"1H":{"ok":True,"candles":candles()}}}}},NOW)
        self.assertEqual(m["instruments"]["BTC"]["1H"]["status"],"MODEL_OBSERVED_UNVERIFIED_PARITY")
        self.assertEqual(m["instruments"]["ETH"]["1H"]["status"],"NO_DATA")
        self.assertTrue(m["researchOnly"])
        self.assertTrue(m["notBacktestParityClaim"])


if __name__ == "__main__":
    unittest.main()
