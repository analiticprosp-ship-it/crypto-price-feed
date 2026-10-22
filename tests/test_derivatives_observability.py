"""Deterministic contracts for one-hour derivatives observation bridge."""
import unittest

from scripts.build_derivatives_observability import (
    HOUR, P5, build, normalized_hour_taker, oi_hour_change,
)

NOW = 1_800_000_000_000
END = (NOW // P5) * P5 - P5
START = END - HOUR


def taker_rows():
    return [
        {"startMs": START + i * P5, "endMs": START + (i + 1) * P5,
         "buyBase": 12, "sellBase": 8}
        for i in range(12)
    ]


class TestTakerHour(unittest.TestCase):
    def source(self):
        return {
            "status": "OBSERVED", "source": "OKX USDT-SWAP contract taker history",
            "notSpotFlow": True,
            "recentClosed5m": taker_rows(),
        }

    def test_full_hour(self):
        result = normalized_hour_taker(self.source(), NOW)
        self.assertEqual(result["status"], "OBSERVED")
        self.assertEqual(result["imbalancePct"], 20.0)
        self.assertEqual(result["closedFiveMinuteBars"], 12)
        self.assertEqual(result["windowStartMs"], START)
        self.assertEqual(result["windowEndMs"], END)

    def test_gap_is_unavailable(self):
        source = self.source()
        source["recentClosed5m"].pop(5)
        result = normalized_hour_taker(source, NOW)
        self.assertEqual(result["status"], "NO_DATA")
        self.assertEqual(result["reason"], "INCOMPLETE_1H_5M_WINDOW")

    def test_stale_is_unavailable(self):
        result = normalized_hour_taker(self.source(), NOW + 30 * 60_000)
        self.assertEqual(result["status"], "NO_DATA")

    def test_negative_volume_rejected(self):
        source = self.source()
        source["recentClosed5m"][3]["sellBase"] = -1
        self.assertEqual(normalized_hour_taker(source, NOW)["status"], "NO_DATA")

    def test_missing_semantics_rejected(self):
        source = self.source()
        source["source"] = "unknown"
        self.assertEqual(normalized_hour_taker(source, NOW)["status"], "NO_DATA")


class TestOIHour(unittest.TestCase):
    def test_exact_hour_change(self):
        end = END
        data = {"openInterestHistory": [
            {"t": end - HOUR, "oiContracts": "1000"},
            {"t": end, "oiContracts": "1100"},
        ]}
        r = oi_hour_change(data, NOW)
        self.assertEqual(r["status"], "OBSERVED")
        self.assertEqual(r["deltaContractsPct1h"], 10.0)
        self.assertEqual(r["deltaContracts"], 100.0)
        self.assertFalse(r["crossVenueAggregationAllowed"])

    def test_no_backfill_or_fake_hour(self):
        data = {"openInterestHistory": [
            {"t": END - 10 * 60_000, "oiContracts": "1000"},
            {"t": END, "oiContracts": "1100"},
        ]}
        r = oi_hour_change(data, NOW)
        self.assertEqual(r["reason"], "NO_MATCHED_1H_OI_SAMPLE")

    def test_stale_and_invalid(self):
        self.assertEqual(oi_hour_change({"openInterestHistory": [
            {"t": END - HOUR, "oiContracts": "1000"},
            {"t": END, "oiContracts": "1100"},
        ]}, NOW + 30 * 60_000)["status"], "NO_DATA")
        self.assertEqual(oi_hour_change({"openInterestHistory": [
            {"t": END - HOUR, "oiContracts": "1000"},
            {"t": END, "oiContracts": "NaN"},
        ]}, NOW)["status"], "NO_DATA")


class TestBuilder(unittest.TestCase):
    def test_no_sources_never_promotes_any_signal(self):
        out = build({}, {}, NOW)
        btc = out["instruments"]["BTC"]
        self.assertEqual(btc["oi1h"]["status"], "NO_DATA")
        self.assertEqual(btc["taker1h"]["status"], "NO_DATA")
        self.assertEqual(btc["liquidations"]["status"], "NO_DATA")
        self.assertEqual(btc["pifagorMFI"]["status"], "NO_DATA")
        self.assertTrue(out["researchOnly"])
        self.assertTrue(out["notTradeApproval"])

    def test_combines_source_families_without_trading_authority(self):
        market = {"instruments": {"BTC": {"perpetual": {"openInterestHistory": [
            {"t": END - HOUR, "oiContracts": "1000"},
            {"t": END, "oiContracts": "1050"},
        ]}}}}
        rest = {"instruments": {"BTC": {"taker": TestTakerHour().source()}}}
        out = build(market, rest, NOW)["instruments"]["BTC"]
        self.assertEqual(out["oi1h"]["deltaContractsPct1h"], 5.0)
        self.assertEqual(out["taker1h"]["imbalancePct"], 20.0)
        self.assertEqual(out["bigGuyBurjKhalifa"]["status"], "NO_DATA")


if __name__ == "__main__":
    unittest.main()
