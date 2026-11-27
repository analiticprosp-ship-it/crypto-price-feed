"""Report eligibility from saved observations; never promote missing data to zero."""
import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent


def audit():
    base = ROOT.parent
    # Repository layout and original portable archive layout both supported.
    books_root = base / "results"
    if not (books_root / "sparse_books.csv").exists():
        books_root = base / "update_20261101/results"
    books = pd.read_csv(books_root / "sparse_books.csv")
    cadence = json.loads((books_root / "book_cadence.json").read_text())
    funding = pd.read_csv(base / "continuation_20261102/results/primary_funding_windows.csv")
    binance = funding[(funding.side == "post") & (funding.event == "BINANCE_SECURITY_20261029")]
    rows = []
    for _, row in binance.iterrows():
        rows.append({
            "symbol": row.symbol,
            "window_hours": int(row.window_hours),
            "covered_interval_hours": float(row.covered_interval_hours),
            "coverage_fraction": float(row.window_coverage_fraction),
            "observed_whole_interval_sum_percent": (
                float(row.sum_realized_percent) if pd.notna(row.sum_realized_percent) else None
            ),
            "full_window_sum_percent": (
                float(row.sum_realized_percent)
                if row.window_coverage_fraction == 1 and pd.notna(row.sum_realized_percent) else None
            ),
        })
    return {
        "status": "READINESS_AUDIT_NOT_HYPOTHESIS_TEST",
        "books": {
            "valid_records": len(books),
            "by_venue_market": [
                {"venue": venue, "market": market, "records": int(count)}
                for (venue, market), count in books.groupby(["venue", "market"]).size().items()
            ],
            "all_records_marked_not_depth_1pct": bool(books.not_depth_1pct.all()),
            "median_capture_gap_hours": cadence["median_capture_gap_hours"],
            "max_capture_gap_hours": cadence["max_capture_gap_hours"],
            "no_six_consecutive_hourly_test_in_source": cadence["actual"],
            "top25_native_not_comparable_across_spot_and_swap": True,
        },
        "binance_post_funding": rows,
        "H1": {"status": "NOT_TESTABLE_WITH_CURRENT_PANEL", "result": None,
               "reason": "Sparse spread observations exist; comparable +/-1% depth and liquidations are missing."},
        "H2": {"status": "NOT_TESTABLE_WITH_CURRENT_PANEL", "result": None,
               "normalization_confirmed_at": None,
               "reason": "No comparable +/-1% depth or six consecutive hourly normalization observations."},
        "H3": {"status": "NOT_TESTABLE_WITH_CURRENT_PANEL", "result": None,
               "reason": "Synchronous flow identification and independently screened clean controls remain absent."},
        "P1_status": "SHADOW_RESEARCH_CANDIDATE_NOT_ACCEPTED",
        "new_market_data_collected": False,
        "PIT_promoted": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit()
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report, indent=2, allow_nan=False))
