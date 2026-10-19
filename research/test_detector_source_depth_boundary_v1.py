"""Offline guards for bounded source-depth probe: no real HTTP calls."""
import datetime as dt
import unittest
from research import detector_source_depth_boundary_v1 as p

class BoundaryProbe(unittest.TestCase):
    def test_expected_18_series(self):
        self.assertEqual(len(p.FAMILIES) * len(p.SYMBOLS), 18)
        self.assertEqual(len(p.year_grid()), 180)
    def test_no_fabricated_absolute_minimum(self):
        r = [{"family": "binance_usdm_metrics_oi", "symbol": "BTCUSDT", "date": "2024-01-01",
              "status": "ARCHIVE_HTTP_200_METADATA_ONLY"}]
        summary = next(x for x in p.summarize(r)
                       if x["family"] == "binance_usdm_metrics_oi" and x["symbol"] == "BTCUSDT")
        self.assertEqual(summary["earliest_observed_http_200"], "2024-01-01")
        self.assertEqual(summary["earliest_absolute_archive_date"], "NOT_ESTABLISHED")
        self.assertEqual(summary["causal_PIT"], "UNVERIFIED")
    def test_unknown_http_is_not_absent(self):
        self.assertEqual(p.outcome(404), "HTTP_404_AT_CHECK")
        self.assertEqual(p.outcome(403), "UNVERIFIED_HTTP_403")
        self.assertEqual(p.outcome(451), "UNVERIFIED_HTTP_451")
        self.assertEqual(p.outcome(200), "ARCHIVE_HTTP_200_METADATA_ONLY")
    def test_url_venue_specific(self):
        self.assertIn("/futures/um/daily/metrics/BTCUSDT/",
                      p.path_for("binance_usdm_metrics_oi", "BTCUSDT", "2024-01-01"))
        self.assertIn("/spot/monthly/aggTrades/ETHUSDT/",
                      p.path_for("binance_spot_aggtrades", "ETHUSDT", "2024-01"))
        with self.assertRaises(ValueError):
            p.path_for("binance_spot_aggtrades", "ETHUSDT", "2024-01-01")
    def test_refinement_prior_year_does_not_claim_origin(self):
        x = [{"family": "binance_spot_1h_klines", "symbol": "BTCUSDT",
              "date": "2020-01", "status": "ARCHIVE_HTTP_200_METADATA_ONLY"}]
        probes = p.refinements(x)
        self.assertIn(("binance_spot_1h_klines", "BTCUSDT", "2019-12"), probes)
        self.assertIn(("binance_spot_1h_klines", "BTCUSDT", "2026-09"), probes)
        self.assertNotIn(("binance_spot_1h_klines", "BTCUSDT", "2017-01"), probes)
    def test_daily_brackets_near_positive_date(self):
        x = [{"family": "binance_usdm_metrics_oi", "symbol": "SOLUSDT",
              "date": "2021-02-01", "status": "ARCHIVE_HTTP_200_METADATA_ONLY"}]
        probes = p.daily_refinements(x)
        self.assertIn(("binance_usdm_metrics_oi", "SOLUSDT", "2021-01-31"), probes)
        self.assertIn(("binance_usdm_metrics_oi", "SOLUSDT", "2021-02-28"), probes)
        self.assertNotIn(("binance_usdm_metrics_oi", "SOLUSDT", "2021-02-29"), probes)
    def test_no_network_or_r2_needed_for_summary(self):
        summary = p.summarize([])
        self.assertEqual(len(summary), 18)
        self.assertTrue(all(x["earliest_observed_http_200"] is None for x in summary))

if __name__ == "__main__":
    unittest.main()
