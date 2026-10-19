#!/usr/bin/env python3
"""Bounded free-source archive boundary reconnaissance for Detector H1-H10.

HEAD 200 proves only that an archive endpoint responded; it does NOT prove
the contents, completeness, original exchange publication or PIT availability.
Never infer absolute source inception from sampled dates or a transient 404.
"""
from __future__ import annotations
import calendar
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
START_YEAR = 2017
END_YEAR = 2026
FAMILIES = {
    "binance_spot_1h_klines": ("monthly", "spot/monthly/klines/{s}/1h/{s}-1h-{d}.zip"),
    "binance_usdm_1h_klines": ("monthly", "futures/um/monthly/klines/{s}/1h/{s}-1h-{d}.zip"),
    "binance_spot_aggtrades": ("monthly", "spot/monthly/aggTrades/{s}/{s}-aggTrades-{d}.zip"),
    "binance_usdm_aggtrades": ("monthly", "futures/um/monthly/aggTrades/{s}/{s}-aggTrades-{d}.zip"),
    "binance_usdm_funding": ("daily", "futures/um/daily/fundingRate/{s}/{s}-fundingRate-{d}.zip"),
    "binance_usdm_metrics_oi": ("daily", "futures/um/daily/metrics/{s}/{s}-metrics-{d}.zip"),
}
ROOT = Path("detector_source_depth_boundary_v1")
R2_ROOT = "research/detector-source-depth-boundary/v1"
MAX_TASKS = 1500
URL_BASE = "https://data.binance.vision/data/"

def path_for(family, symbol, stamp):
    granularity, pattern = FAMILIES[family]
    if symbol not in SYMBOLS or len(stamp) != (7 if granularity == "monthly" else 10):
        raise ValueError("BAD_SOURCE_SPEC")
    return URL_BASE + pattern.format(s=symbol, d=stamp)

def outcome(status):
    if status == 200:
        return "ARCHIVE_HTTP_200_METADATA_ONLY"
    if status == 404:
        return "HTTP_404_AT_CHECK"
    return "UNVERIFIED_HTTP_" + str(status)

def head_one(item):
    family, symbol, stamp = item
    url = path_for(family, symbol, stamp)
    for attempt in range(2):
        req = urllib.request.Request(url, method="HEAD",
            headers={"User-Agent": "Detector-H1H10-Free-Archive-Boundary/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                code = r.status
                return {"family": family, "symbol": symbol, "date": stamp,
                        "url": url, "http_status": code, "status": outcome(code),
                        "content_length": r.headers.get("Content-Length"),
                        "last_modified": r.headers.get("Last-Modified")}
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt == 0:
                time.sleep(0.5)
                continue
            return {"family": family, "symbol": symbol, "date": stamp, "url": url,
                    "http_status": e.code, "status": outcome(e.code)}
        except Exception as e:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return {"family": family, "symbol": symbol, "date": stamp, "url": url,
                    "http_status": None, "status": "NETWORK_OR_HEAD_UNVERIFIED",
                    "error_type": type(e).__name__}
    raise AssertionError("unreachable")

def year_grid():
    return [(fam, sym, f"{year:04d}-01" if kind == "monthly"
             else f"{year:04d}-01-01")
            for fam, (kind, _) in FAMILIES.items()
            for sym in SYMBOLS for year in range(START_YEAR, END_YEAR + 1)]

def refinements(observations):
    """Sample the year preceding first positive January, WITHOUT monotonicity claims."""
    next_items = set()
    for fam, (kind, _) in FAMILIES.items():
        for sym in SYMBOLS:
            rows = [r for r in observations if r["family"] == fam and r["symbol"] == sym]
            found = sorted((r["date"] for r in rows
                           if r["status"] == "ARCHIVE_HTTP_200_METADATA_ONLY"))
            if not found:
                continue
            first_year = int(found[0][:4])
            if first_year <= START_YEAR:
                continue
            prior = first_year - 1
            for month in range(1, 13):
                date = f"{prior:04d}-{month:02d}"
                if kind == "daily":
                    date += "-01"
                next_items.add((fam, sym, date))
            # Explicit independent close-to-current control, never a first-published proof.
            next_items.add((fam, sym, "2026-09" if kind == "monthly" else "2026-10-01"))
    return next_items

def daily_refinements(observations):
    """For earliest observed daily month, check every day in that month and previous month."""
    requests = set()
    for fam, (kind, _) in FAMILIES.items():
        if kind != "daily":
            continue
        for sym in SYMBOLS:
            good = sorted(r["date"] for r in observations
                          if r["family"] == fam and r["symbol"] == sym
                          and r["status"] == "ARCHIVE_HTTP_200_METADATA_ONLY")
            if not good:
                continue
            d = dt.date.fromisoformat(good[0])
            # The preceding month is checked because its first day may predate listing.
            preceding = d.replace(day=1) - dt.timedelta(days=1)
            for year, month in ((d.year, d.month), (preceding.year, preceding.month)):
                for day in range(1, calendar.monthrange(year, month)[1] + 1):
                    requests.add((fam, sym, f"{year:04d}-{month:02d}-{day:02d}"))
    return requests

def summarize(results):
    summary = []
    for fam, (kind, _) in FAMILIES.items():
        for sym in SYMBOLS:
            rows = [r for r in results if (r["family"], r["symbol"]) == (fam, sym)]
            yes = sorted(r["date"] for r in rows
                         if r["status"] == "ARCHIVE_HTTP_200_METADATA_ONLY")
            errors = [r for r in rows if r["status"].startswith("UNVERIFIED") or
                      r["status"] == "NETWORK_OR_HEAD_UNVERIFIED"]
            summary.append({
                "family": fam, "venue": "Binance", "market": "spot" if "_spot_" in fam else "USDM_perpetual",
                "symbol": sym, "granularity": kind, "probed_dates": len(rows),
                "http_200_dates": len(yes),
                "earliest_observed_http_200": yes[0] if yes else None,
                "latest_observed_http_200": yes[-1] if yes else None,
                "unknown_or_failed_head_count": len(errors),
                "earliest_absolute_archive_date": "NOT_ESTABLISHED",
                "contents_crc_sha_schema_quality": "NOT_TESTED_IN_THIS_PROBE",
                "original_exchange_publication": "UNVERIFIED",
                "causal_PIT": "UNVERIFIED",
                "source_unit": "UNVERIFIED"})
    return summary

def save_r2(report, blob, checksum):
    vars_needed = ("R2_BUCKET", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
    if not all(os.environ.get(k) for k in vars_needed):
        return {"status": "NOT_CONFIGURED_NO_R2_WRITE"}
    import boto3
    cli = boto3.client("s3",
        endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="auto")
    key = R2_ROOT + "/" + str(os.environ.get("GITHUB_RUN_ID", "manual")) + "-" + str(os.environ.get("GITHUB_RUN_ATTEMPT", "1")) + ".json"
    cli.put_object(Bucket=os.environ["R2_BUCKET"], Key=key, Body=blob,
                   ContentType="application/json", Metadata={"sha256": checksum})
    back = cli.get_object(Bucket=os.environ["R2_BUCKET"], Key=key)["Body"].read(len(blob) + 1)
    if back != blob or hashlib.sha256(back).hexdigest() != checksum:
        raise ValueError("R2_READBACK_SHA256_MISMATCH")
    return {"status": "SHA256_READBACK_PASS", "key": key, "sha256": checksum}

def run():
    ROOT.mkdir(exist_ok=True)
    seen = {}
    def execute(items):
        new = sorted(set(items) - set(seen))
        if len(new) + len(seen) > MAX_TASKS:
            raise ValueError("SOURCE_HEAD_PROBE_BUDGET_EXCEEDED")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            for row in pool.map(head_one, new):
                seen[(row["family"], row["symbol"], row["date"])] = row
    execute(year_grid())
    execute(refinements(list(seen.values())))
    execute(daily_refinements(list(seen.values())))
    rows = sorted(seen.values(), key=lambda x: (x["family"], x["symbol"], x["date"]))
    report = {
        "schema": "detector-h1h10-free-source-depth-boundary-probe-v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "ARCHIVE_HTTP_METADATA_PROBE_ONLY",
        "target": "bounded historical-depth discovery, not production time series",
        "families": summarize(rows), "probes": rows,
        "methodology": "January for 2017-2026; 12 months before earliest January 200; two months day-by-day for daily data",
        "limitations": [
            "HEAD responses cannot establish actual archive contents or original publication time",
            "404 proves only a URL was not found at the queried instant, not a source inception date",
            "The sample-grid can miss older nonmonotonic or temporarily unavailable archives",
            "The earliest HTTP 200 in this sample is NOT the maximum verified obtainable history",
            "No content used for confirmatory H1-H10, P&L or live decisions",
            "Bybit OKX Tardis are separate source families and NOT covered by Binance HEAD results"],
        "edge_status": "EDGE_UNVALIDATED", "research_only": True,
        "trading_actions": False}
    blob = json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2).encode()
    checksum = hashlib.sha256(blob).hexdigest()
    (ROOT / "report.json").write_bytes(blob)
    state = save_r2(report, blob, checksum)
    print("DEPTH_BOUNDARY_SUMMARY", json.dumps({
        "status": report["status"], "series": len(report["families"]),
        "probes": len(rows), "head_200": sum(r["http_status"] == 200 for r in rows),
        "head_404": sum(r["http_status"] == 404 for r in rows),
        "unverified": sum(r["http_status"] not in (200, 404) for r in rows),
        "series_min_dates": [{"family": r["family"], "symbol": r["symbol"],
           "earliest_200": r["earliest_observed_http_200"],
           "unknown": r["unknown_or_failed_head_count"]} for r in report["families"]],
        "r2": state, "sha256": checksum}, ensure_ascii=False))
if __name__ == "__main__":
    run()
