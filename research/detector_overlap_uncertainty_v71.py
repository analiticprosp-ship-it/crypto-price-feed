#!/usr/bin/env python3
"""Detector v7.1: post-hoc month-cluster uncertainty audit of immutable v6.9/v7.0 reports.

RESEARCH ONLY. No orders, live signals, or portfolio writes.
This is not a randomized experiment or a test of execution profitability.
"""
import hashlib
import json
import os
import random
import statistics
from collections import defaultdict
from pathlib import Path

import boto3

SOURCE = (
    ("6.9", "research/detector/v6.9/runs/39107302260-1/comparison.json",
     "52c68895360938cf70f118a5465713f01e3391ce64bfb4ef2e613ef10c22524a", 22),
    ("7.0", "research/detector/v7.0/runs/39109768036-1/comparison.json",
     "7d4947d48e65aae303f3e927b1a9687cc140925cb2c739faa7899821a93a6eea", 12),
)
SEED = 710018
REPEATS = 12000
HORIZONS = ("4h", "24h")


def quantile(data, p):
    if not data:
        return None
    values = sorted(data)
    index = (len(values) - 1) * p
    low = int(index)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (index - low)


def rounded(value):
    return round(value, 6) if value is not None else None


def estimate(rows, horizon):
    # Same event-weighted estimator as v6.9 and v7.0: exclude a symbol-month
    # if either comparison group is empty. Source means are stored to 6 decimals.
    a_weight = b_weight = 0
    a_sum = b_sum = 0.0
    for record in rows:
        h = record["firstCandidateComparison"]["horizons"][horizon]
        if h["groupA"] > 0 and h["groupB"] > 0:
            a_weight += h["groupA"]
            b_weight += h["groupB"]
            a_sum += h["groupA"] * h["meanA"]
            b_sum += h["groupB"] * h["meanB"]
    if not a_weight or not b_weight:
        return None
    return a_sum / a_weight - b_sum / b_weight


def group_by_month(rows):
    months = defaultdict(list)
    for row in rows:
        months[row["month"]].append(row)
    return [months[month] for month in sorted(months)]


def clustered_analysis(rows, tag):
    months = group_by_month(rows)
    observed = [estimate(rows, h) for h in HORIZONS]
    if len(months) < 2 or any(x is None for x in observed):
        raise ValueError("CLUSTERS_OR_COMPARISON_MISSING:" + tag)
    rng = random.Random(int(hashlib.sha256((str(SEED) + tag).encode()).hexdigest()[:16], 16))
    samples = []
    for _ in range(REPEATS):
        selected = [row for _ in months for row in months[rng.randrange(len(months))]]
        pair = tuple(estimate(selected, h) for h in HORIZONS)
        if all(v is not None for v in pair):
            samples.append(pair)
    if len(samples) < int(REPEATS * .99):
        raise ValueError("BOOTSTRAP_TOO_MANY_EMPTY_GROUPS:" + tag)
    sd = [statistics.pstdev(sample[i] for sample in samples) for i in range(2)]
    if any(s <= 0 for s in sd):
        raise ValueError("ZERO_BOOTSTRAP_VARIANCE:" + tag)
    maxima = [max(abs((sample[i] - observed[i]) / sd[i]) for i in range(2)) for sample in samples]
    critical = quantile(maxima, .95)
    horizons = {}
    for i, horizon in enumerate(HORIZONS):
        values = [sample[i] for sample in samples]
        leave_one = [estimate([row for month in months if month is not excluded for row in month], horizon)
                     for excluded in months]
        horizons[horizon] = {
            "effectPctPoints": rounded(observed[i]),
            "clusterBootstrap95": [rounded(quantile(values, .025)), rounded(quantile(values, .975))],
            "pairedHorizonSimultaneous95": [rounded(observed[i] - critical * sd[i]),
                                            rounded(observed[i] + critical * sd[i])],
            "monthLeaveOneOutRange": [rounded(min(leave_one)), rounded(max(leave_one))],
            "monthLeaveOneOutPositive": sum(x > 0 for x in leave_one),
            "monthLeaveOneOutTotal": len(leave_one),
        }
    return {
        "calendarMonthClusters": len(months),
        "symbolMonths": len(rows),
        "resamples": len(samples),
        "horizons": horizons,
    }, samples


def main():
    client = boto3.client(
        "s3", endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="auto"
    )
    bucket = os.environ["R2_BUCKET"]
    refs = []
    all_rows = []
    for version, key, expected, count in SOURCE:
        blob = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        observed_sha = hashlib.sha256(blob).hexdigest()
        if observed_sha != expected:
            raise SystemExit("V71_REFERENCE_SHA_MISMATCH:" + version)
        doc = json.loads(blob)
        if doc.get("version") != version or len(doc.get("results", [])) != count:
            raise SystemExit("V71_REFERENCE_SHAPE_MISMATCH:" + version)
        refs.append({"version": version, "key": key, "sha256": observed_sha})
        all_rows.extend(doc["results"])
    groups = {name: [r for r in all_rows if r["cohort"] == name]
              for name in ("baseline", "extension", "holdout")}
    if [len(groups[n]) for n in groups] != [10, 12, 12]:
        raise SystemExit("V71_COHORT_COUNT_MISMATCH")
    expected_holdout = [f"2024-{month:02d}" for month in range(1, 7)]
    if sorted(set(r["month"] for r in groups["holdout"])) != expected_holdout:
        raise SystemExit("V71_HOLDOUT_MONTHS_CHANGED")
    if len({(r["symbol"], r["month"]) for r in all_rows}) != 34:
        raise SystemExit("V71_DUPLICATE_SOURCE_ROWS")

    analyses = {}
    samples = {}
    for name in ("baseline", "extension", "holdout", "all"):
        subset = groups[name] if name != "all" else all_rows
        analyses[name], samples[name] = clustered_analysis(subset, name)
        analyses[name]["assets"] = {
            symbol: {
                h: rounded(estimate([r for r in subset if r["symbol"] == symbol], h))
                for h in HORIZONS
            }
            for symbol in ("BTC", "ETH")
        }
    difference = {}
    for i, horizon in enumerate(HORIZONS):
        observed = estimate(groups["holdout"], horizon) - estimate(groups["extension"], horizon)
        draws = [a[i] - b[i] for a, b in zip(samples["holdout"], samples["extension"])]
        difference[horizon] = {
            "holdoutMinusExtensionPctPoints": rounded(observed),
            "monthClusterBootstrap95": [rounded(quantile(draws, .025)), rounded(quantile(draws, .975))],
        }

    report = {
        "version": "7.1",
        "status": "POST_HOC_EXPLORATORY_RESEARCH_ONLY",
        "researchOnly": True, "tradesEmitted": 0,
        "originalLiveDetectorParity": "NOT_ESTABLISHED",
        "sources": refs, "seed": SEED, "bootstrapRepeats": REPEATS,
        "estimator": "Unchanged event-weighted first-LONG Sweep minus non-Sweep return; six-decimal source monthly means",
        "resamplingUnit": "Calendar month, preserving all within-month first-day observations and paired BTC/ETH effects",
        "horizonsResampledTogether": list(HORIZONS),
        "analyses": analyses,
        "holdoutMinusExtension": difference,
        "limitations": [
            "Post-hoc uncertainty analysis after inspecting v7.0; NOT a new untouched holdout",
            "Month-resampling captures within-month overlap and BTC/ETH dependence, but assumes exchangeable month clusters",
            "Contiguous months may remain serially dependent; baseline has only 5, extension and holdout only 6 clusters",
            "No event-level non-overlap subsampling, time-series HAC, or pre-registered prospective confirmation",
            "Two-horizon simultaneous intervals are bootstrap approximations with few clusters",
            "Source group means are rounded to 6 decimals; group membership and candidate rules are unchanged",
            "Not a randomized intervention, causal result, executable signal, or proof of trading edge",
        ],
    }
    folder = Path("detector_v71_reports")
    folder.mkdir(exist_ok=True)
    raw = json.dumps(report, indent=2, ensure_ascii=False).encode()
    (folder / "comparison.json").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    run = os.environ.get("GITHUB_RUN_ID", "manual")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    prefix = f"research/detector/v7.1/runs/{run}-{attempt}/"
    manifest = {
        "version": "7.1", "status": "POST_HOC_EXPLORATORY_RESEARCH_PASS",
        "researchOnly": True, "tradesEmitted": 0,
        "reportSha256": digest, "prefix": prefix,
        "githubSha": os.environ.get("GITHUB_SHA"),
        "sourceSha256": {r["version"]: r["sha256"] for r in refs},
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
    for name in ("comparison.json", "manifest.json"):
        data = (folder / name).read_bytes()
        key = prefix + name
        client.put_object(Bucket=bucket, Key=key, Body=data, ContentType="application/json",
                          Metadata={"sha256": hashlib.sha256(data).hexdigest(), "research-only": "true"})
        readback = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        if readback != data:
            raise SystemExit("V71_R2_WRITEBACK_VERIFICATION_FAILED")
    summary = {
        "status": "V71_POST_HOC_RESEARCH_PASS_WRITEBACK_VERIFIED",
        "run": run, "reportSha256": digest, "prefix": prefix,
        "monthClusters": {n: analyses[n]["calendarMonthClusters"] for n in analyses},
        "holdout": analyses["holdout"], "all": analyses["all"],
        "holdoutMinusExtension": difference,
    }
    print(json.dumps(summary, ensure_ascii=False))
    markdown = ["# Detector v7.1 — исследовательская кластерная неопределённость", "",
                "**Режим:** post-hoc exploratory; не доказательство торгового преимущества.", "",
                f"**Статус:** {summary['status']}", f"**R2:** \`{prefix}\`",
                f"**SHA-256:** \`{digest}\`", "",
                "| Выборка | Месяцев-кластеров | Δ4h | 95% cluster CI 4h | Δ24h | 95% cluster CI 24h |",
                "|---|---:|---:|---|---:|---|"]
    for name in ("baseline", "extension", "holdout", "all"):
        entry = analyses[name]
        x, y = entry["horizons"]["4h"], entry["horizons"]["24h"]
        markdown.append(
            f"| {name} | {entry['calendarMonthClusters']} | {x['effectPctPoints']} | {x['clusterBootstrap95']} | "
            f"{y['effectPctPoints']} | {y['clusterBootstrap95']} |"
        )
    md = "\n".join(markdown) + "\n"
    (folder / "summary.md").write_text(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md)


if __name__ == "__main__":
    main()
