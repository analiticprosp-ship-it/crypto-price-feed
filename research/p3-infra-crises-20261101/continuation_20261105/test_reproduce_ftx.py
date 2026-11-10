"""Failure checks protect missing-data and source-integrity boundaries."""
import tempfile
import unittest
from pathlib import Path

from reproduce_ftx import ROOT, checked_bytes, digest, validate_hourly


class InputIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.data = (ROOT / "inputs/mirror_bitstamp_BTC_ftx_exact_rows.csv").read_bytes()

    def test_original_slice_covers_complete_grid(self):
        validate_hourly(self.data, "BTC")

    def test_missing_row_is_not_imputed(self):
        with self.assertRaises(ValueError):
            validate_hourly(b"".join(self.data.splitlines(keepends=True)[1:]), "BTC")

    def test_duplicate_timestamp_is_rejected(self):
        rows = self.data.splitlines(keepends=True)
        rows[1] = rows[0]
        with self.assertRaises(ValueError):
            validate_hourly(b"".join(rows), "BTC")

    def test_wrong_quote_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_hourly(self.data.replace(b"BTC/USD", b"BTC/USDT"), "BTC")

    def test_corrupt_bytes_fail_hash(self):
        with tempfile.TemporaryDirectory() as work:
            p = Path(work) / "input.csv"
            p.write_bytes(self.data + b"\n")
            with self.assertRaises(ValueError):
                checked_bytes(p, digest(self.data))

    def test_missing_file_fails(self):
        with tempfile.TemporaryDirectory() as work:
            with self.assertRaises(FileNotFoundError):
                checked_bytes(Path(work) / "absent.csv", digest(self.data))


if __name__ == "__main__":
    unittest.main()
