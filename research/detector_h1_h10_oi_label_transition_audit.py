#!/usr/bin/env python3
"""Independently audit Binance UM daily metrics timestamp LABELS around 2026-06-25.

Checks the CSV first row and 00:00 UTC duplicates. Does not infer OI publication
time or stock/flow event semantics from labels alone.
"""
import csv
import datetime as dt
import io
import json
from pathlib import Path
import urllib.request
import zipfile

DAYS = ("2026-06-24", "2026-06-25", "2026-06-26")
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
OUT = Path("detector_h1_h10_oi_label_boundary")
OUT.mkdir(exist_ok=True)


def parse_time(raw):
    x = raw.strip().replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(x)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def load_day(sym, day):
    url = (f"https://data.binance.vision/data/futures/um/daily/metrics/"
           f"{sym}/{sym}-metrics-{day}.zip")
    req = urllib.request.Request(url, headers={"User-Agent": "Detector-H1-H10-Research/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        archive = r.read(5_000_001)
    if len(archive) > 5_000_000:
        raise ValueError("ARCHIVE_SIZE_LIMIT")
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        names = [n for n in z.namelist() if n.endswith(".csv") and "/" not in n]
        if len(names) != 1 or z.testzip() is not None:
            raise ValueError("CSV_ZIP_STRUCTURE_INVALID")
        with z.open(names[0]) as f:
            rows = list(csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig", newline="")))
    if not rows:
        raise ValueError("EMPTY_CSV")
    first = rows[0]
    has_header = first[0].strip().lower() in ("create_time", "timestamp")
    data = rows[1:] if has_header else rows
    if len(data) < 2:
        raise ValueError("NOT_ENOUGH_ROWS")
    times = [parse_time(r[0]) for r in data]
    if len(times) != len(set(times)):
        raise ValueError("DUPLICATE_IN_SINGLE_DAY")
    if times != sorted(times):
        raise ValueError("NONMONOTONIC_SOURCE_ROWS")
    labels = {t.isoformat(): r for t, r in zip(times, data)}
    return {
        "symbol": sym, "date": day, "source_url": url,
        "header_present": has_header,
        "header": first if has_header else None,
        "row_count": len(data), "first_label_utc": times[0].isoformat(),
        "last_label_utc": times[-1].isoformat(),
        "labels": labels,
        "csv_first_row_preserved": (not has_header) or first[0].strip().lower() in ("create_time", "timestamp"),
    }


def main():
    report = {
        "audit": "Binance UM 5m metrics CSV timestamp label transition, not real publication",
        "symbols": {}, "errors": [],
        "methodology": "Parse every CSV row including first data row; inspect UTC labels and duplicate boundaries",
        "publication_time_status": "ASOF_PUBLICATION_UNVERIFIED",
        "warning": "A label at T is NOT proof that its value was observable at T; stock/flow semantics require independent content alignment.",
    }
    for sym in SYMS:
        try:
            days = [load_day(sym, d) for d in DAYS]
            d24, d25, d26 = days
            for day_report in days:
                print("OI_CSV_FILE_BOUNDARIES", sym, json.dumps({
                    "date": day_report["date"],
                    "rows": day_report["row_count"],
                    "header_present": day_report["header_present"],
                    "first_label_utc": day_report["first_label_utc"],
                    "last_label_utc": day_report["last_label_utc"],
                }, ensure_ascii=False), flush=True)
            t = "2026-06-25T00:00:00+00:00"
            left = d24["labels"].get(t)
            right = d25["labels"].get(t)
            duplicate = bool(left and right)
            change = (
                d24["first_label_utc"] == "2026-06-24T00:05:00+00:00"
                and d24["last_label_utc"] == t
                and d25["first_label_utc"] == t
                and d25["last_label_utc"] == "2026-06-25T23:55:00+00:00"
                and d26["first_label_utc"] == "2026-06-26T00:00:00+00:00"
            )
            result = {
                "status": "LABEL_PATTERN_SHIFT_OBSERVED" if change else "LABEL_PATTERN_SHIFT_NOT_CONFIRMED",
                "csv_files": [{k:v for k,v in day.items() if k!="labels"} for day in days],
                "duplicate_2026_06_25_midnight": duplicate,
                "duplicate_content_equal": (left[2:] == right[2:]) if duplicate else None,
                "cross_file_boundary_rows": {
                    "left": left[:3] if left else None, "right": right[:3] if right else None,
                },
            }
            report["symbols"][sym] = result
            print("OI_CSV_LABEL_AUDIT", sym, json.dumps({k:v for k,v in result.items() if k!="csv_files"}, ensure_ascii=False), flush=True)
        except Exception as exc:
            report["errors"].append({"symbol": sym, "exception": type(exc).__name__, "detail": str(exc)[:100]})
            print("OI_CSV_LABEL_AUDIT_FAILED", sym, type(exc).__name__, flush=True)
    if report["errors"]:
        report["status"] = "SOURCE_OR_VALIDATION_ERROR"
    elif all(x["status"] == "LABEL_PATTERN_SHIFT_OBSERVED" for x in report["symbols"].values()):
        report["status"] = "CSV_LABEL_SHIFT_CONFIRMED_PUBLICATION_UNVERIFIED"
    else:
        report["status"] = "CSV_LABEL_SHIFT_UNCONFIRMED_PUBLICATION_UNVERIFIED"
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OI_CSV_LABEL_SUMMARY", json.dumps({"status": report["status"], "errors": report["errors"]}, ensure_ascii=False), flush=True)
    summary = __import__("os").environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Аудит временных меток OI, 24–26 июня 2026\n\n")
            f.write(f"- Статус: {report['status']}\n- Ошибки: {len(report['errors'])}\n")
            f.write("- Реальное время публикации OI: НЕ ПОДТВЕРЖДЕНО\n")
    if report["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
