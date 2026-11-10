"""Replay the pinned FTX script offline with recovered, lossless input slices.

Run from any working directory. Only --output-dir is written; the original
script and results remain untouched. Missing/corrupt inputs fail closed.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked_bytes(path, expected_hash):
    data = path.read_bytes()
    if digest(data) != expected_hash:
        raise ValueError(f"SHA256 mismatch: {path.name}")
    return data


def validate_hourly(data, asset):
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
    if len(rows) != 96 or any(len(row) != 9 for row in rows):
        raise ValueError("Expected 96 original nine-column hourly rows")
    starts = [int(row[0]) for row in rows]
    expected = set(range(1667862000, 1668204000 + 1, 3600))
    if len(set(starts)) != 96 or set(starts) != expected:
        raise ValueError("Missing/duplicate/unexpected hourly timestamp")
    for row in rows:
        if row[2] != f"{asset}/USD":
            raise ValueError("Wrong asset or quote")
        o, h, low, close = map(float, row[3:7])
        if not all(math.isfinite(x) and x > 0 for x in (o, h, low, close)):
            raise ValueError("Non-finite or non-positive OHLC")
        if not low <= min(o, close) <= max(o, close) <= h:
            raise ValueError("Invalid OHLC bounds")


def replay(output_dir):
    manifest = json.loads((ROOT / "INPUT_MANIFEST.json").read_text())
    source = ROOT.parent / "continuation_20261102"
    recovered = {
        name: checked_bytes(ROOT / name, record["sha256"])
        for name, record in manifest["recovered_inputs"].items()
    }
    pinned = {
        name: checked_bytes(source / name, expected)
        for name, expected in manifest["pinned_existing_files"].items()
    }
    for asset in ("BTC", "ETH"):
        validate_hourly(recovered[f"inputs/mirror_bitstamp_{asset}_ftx_exact_rows.csv"], asset)
    output_dir = output_dir.resolve()
    # Never overwrite a historic or already generated result directory.
    output_dir.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="p3-ftx-replay-") as work:
        base = Path(work) / "P3"
        run = base / "continuation_20261102"
        for name, data in pinned.items():
            path = run / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for asset in ("BTC", "ETH"):
            path = base / "raw" / f"mirror_bitstamp_{asset}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(recovered[f"inputs/mirror_bitstamp_{asset}_ftx_exact_rows.csv"])
        previous = base / "continuation_20261101_spot/results/primary_spot_response.csv"
        previous.parent.mkdir(parents=True, exist_ok=True)
        previous.write_bytes(recovered["inputs/previous_primary_spot_response.csv"])
        result = subprocess.run(
            [sys.executable, str(run / "phase_uncertainty.py")],
            text=True, capture_output=True, check=True,
        )
        outputs = {}
        for name, expected in manifest["expected_outputs"].items():
            data = checked_bytes(run / "results" / name, expected)
            outputs[name] = {"sha256": digest(data), "byte_identical": True}
        # Publish results only after every comparison passes.
        for name in outputs:
            shutil.copyfile(run / "results" / name, output_dir / name)
        report = {
            "status": "PASS_EXACT_REPLAY_OF_PINNED_RESULTS",
            "input_manifest_sha256": digest((ROOT / "INPUT_MANIFEST.json").read_bytes()),
            "source_commit": manifest["source_commit"],
            "python": sys.version.split()[0],
            "output_checks": outputs,
            "usd_price_rows_per_asset": 96,
            "anchors": 24,
            "sensitivity_rows": 144,
            "new_independent_episodes": 0,
            "original_PIT": False,
            "causal_identification": False,
            "P1_status": "SHADOW_RESEARCH_CANDIDATE_NOT_ACCEPTED",
        }
        (output_dir / "REPLAY_VALIDATION.json").write_text(json.dumps(report, indent=2) + "\n")
        (output_dir / "execution.log").write_text(result.stdout + result.stderr)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="New directory; existing directories are rejected")
    args = parser.parse_args()
    try:
        print(json.dumps(replay(args.output_dir), indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"REPLAY_FAILED: {error}\n")


if __name__ == "__main__":
    main()
