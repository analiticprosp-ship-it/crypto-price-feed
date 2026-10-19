#!/usr/bin/env python3
"""BTCI v8.18c3: audit Coin Metrics archived Git vintages, never trading authority."""
import csv
import hashlib
import io
import json
import math
import os
import sys
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import boto3

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "research/btci_v818c3_historical_fork_pit_prereg_2026-10-19.json"
COLS = ("CapMVRVCur", "CapRealUSD", "CapMrktCurUSD", "PriceUSD", "SplyCur")
EMPTY = {"", "null", "none", "nan", "na"}

def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def numeric(s):
    if s is None or str(s).strip().lower() in EMPTY:
        return None
    x = float(s)
    return x if math.isfinite(x) else None

def extract_daily(raw, cols=COLS):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    fields = reader.fieldnames or []
    datekey = "time" if "time" in fields else "date" if "date" in fields else None
    if not datekey:
        raise ValueError("NO_DATE_FIELD")
    values = {}
    for row in reader:
        key = str(row.get(datekey) or "")[:10]
        date.fromisoformat(key)
        if key in values:
            raise ValueError("DUPLICATE_DATE_" + key)
        values[key] = {c: numeric(row.get(c)) if c in fields else None for c in cols}
    if not values:
        raise ValueError("EMPTY_CSV")
    return {
        "fields": fields, "dateField": datekey,
        "firstObservation": min(values), "lastObservation": max(values),
        "rowCount": len(values),
        "values": values
    }

def fetch_bytes(info):
    url = "https://raw.githubusercontent.com/{}/{}/{}/csv/btc.csv".format(
        info["owner"], info["repo"], info["sha"])
    last = None
    for attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": "btci-research-git-vintage-audit/1.0"})
            with urlopen(req, timeout=55) as reply:
                raw = reply.read(22_000_001)
            if len(raw) > 22_000_000:
                raise ValueError("CSV_EXCEEDS_22_MB")
            if info["bytes"] and len(raw) != info["bytes"]:
                raise ValueError("BYTE_COUNT_MISMATCH")
            observed = git_blob(raw)
            if observed != info["blob"]:
                raise ValueError("GIT_BLOB_SHA1_MISMATCH " + observed)
            return url, raw
        except (HTTPError, URLError, TimeoutError) as exc:
            last = str(exc)
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError("SOURCE_FETCH_UNAVAILABLE " + str(last))

def compare(a, b, col):
    if col not in a["fields"] or col not in b["fields"]:
        return {"status": "COLUMN_MISSING_IN_ONE_OR_BOTH"}
    both = 0
    different = 0
    one_null = 0
    examples = []
    for k in a["values"].keys() & b["values"].keys():
        av = a["values"][k][col]
        bv = b["values"][k][col]
        if (av is None) != (bv is None):
            one_null += 1
        elif av is not None:
            both += 1
            if not math.isclose(av, bv, rel_tol=1e-10, abs_tol=1e-10):
                different += 1
                if len(examples) < 4:
                    examples.append({"observationDate": k, "prior": av, "later": bv})
    examples.sort(key=lambda r: r["observationDate"])
    return {
        "status": "COMPARABLE", "bothNumeric": both,
        "changedNumericValues": different, "oneSideMissing": one_null,
        "examples": examples
    }

def selftest():
    assert git_blob(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"
    d = extract_daily(b"time,CapMVRVCur,CapRealUSD\n2020-01-01T00:00:00Z,1.25,\n2020-01-02T00:00:00Z,1.30,4\n")
    assert d["rowCount"] == 2 and d["values"]["2020-01-01"]["CapMVRVCur"] == 1.25
    assert compare(d, d, "CapMVRVCur")["changedNumericValues"] == 0
    missing = extract_daily(b"date,price(USD)\n2018-06-01,100\n")
    assert compare(missing, d, "CapMVRVCur")["status"] == "COLUMN_MISSING_IN_ONE_OR_BOTH"
    print("V818C3_SELFTEST_PASS", flush=True)

def main():
    rawspec = PREREG.read_bytes()
    spec = json.loads(rawspec)
    assert spec["version"] == "8.18c3" and spec["researchOnly"]
    sources = []
    recovered = []
    errors = []
    for info in spec["commits"]:
        try:
            url, raw = fetch_bytes(info)
            parsed = extract_daily(raw)
            fields = parsed["fields"]
            summary = {
                "label": info["label"], "commitSHA": info["sha"],
                "source": url, "gitBlobSHA1Verified": info["blob"],
                "contentSHA256": sha256(raw), "bytes": len(raw),
                "firstObservation": parsed["firstObservation"],
                "lastObservation": parsed["lastObservation"],
                "dateField": parsed["dateField"], "rowCount": parsed["rowCount"],
                "metricColumns": {c: c in fields for c in COLS},
                "sampleObservations": {
                    k: parsed["values"].get(k)
                    for k in spec["fixedAnchorDates"]
                    if k in parsed["values"]
                },
            }
            sources.append(summary)
            recovered.append((info["label"], parsed))
            print("V818C3_SOURCE " + json.dumps({
                "label": summary["label"], "rows": summary["rowCount"],
                "mvrv": summary["metricColumns"]["CapMVRVCur"],
                "realCap": summary["metricColumns"]["CapRealUSD"],
                "shaVerified": True}, ensure_ascii=False), flush=True)
        except Exception as exc:
            errors.append({"label": info["label"], "error": str(exc)[:500]})
            print("V818C3_SOURCE_FAILURE " + json.dumps(errors[-1]), flush=True)

    pairAudits = []
    for i in range(1, len(recovered)):
        prev_label, prev = recovered[i - 1]
        label, curr = recovered[i]
        pairAudits.append({
            "before": prev_label, "after": label,
            "overlapCalendarDates": len(prev["values"].keys() & curr["values"].keys()),
            "metrics": {col: compare(prev, curr, col) for col in COLS},
        })
    # Audit-log expansion only: reproduce the same preregistered pairwise statistics.
    for pa in pairAudits:
        reduced = {
            "before": pa["before"], "after": pa["after"],
            "overlapCalendarDates": pa["overlapCalendarDates"],
            "metrics": {
                col: {k: v for k, v in pa["metrics"][col].items()
                      if k in ("status", "bothNumeric", "changedNumericValues", "oneSideMissing")}
                for col in COLS
            },
        }
        print("V818C3_REVISION_COUNTS " + json.dumps(reduced, ensure_ascii=False), flush=True)
    available = [r["label"] for r in sources if r["metricColumns"]["CapMVRVCur"]]
    status = "GIT_BLOB_VERIFIED_HISTORIC_VINTAGES_NOT_ORIGINAL_FIRST_SEEN"
    if errors:
        status = "PARTIAL_SOURCE_FAILURE_GIT_VINTAGE"
    elif not available:
        status = "MVRV_ABSENT_FROM_ALL_FROZEN_VINTAGES"

    report = {
        "version": "8.18c3", "status": status, "researchOnly": True,
        "noTradeAuthority": True, "prereg": {
            "path": str(PREREG.relative_to(ROOT)), "sha256": sha256(rawspec)},
        "sources": spec["sources"], "completeSourceCoverage": not errors,
        "errors": errors, "vintages": sources,
        "pairwiseHistoricalRevisions": pairAudits,
        "earliestObservedMVRVContainingSnapshot": available[0] if available else None,
        "earliestObservedIsNotFirstPublication": True,
        "sourceInterpretation": [
            "Historical Git commit dates indicate original object history, but do not independently prove hosting/public first-seen times.",
            "Fork was created in December 2024; before-fork Git commits must be verified with external contemporaneous evidence before being upgraded to strong publication-time provenance.",
            "Observations predating a commit are backfilled rows, never evidence they were available at that observation date.",
            "Even present MVRV does not prove original CapRealUSD series column exists in the same CSV.",
            "No training, model-fit, BTC outcomes, threshold search or out-of-sample performance claims performed."
        ],
        "portfolioWriteback": {k: False for k in [
            "Spot","Futures","NAV","PnL","capital","reserve","MASTER","Detector","tradingLimits","orders"]},
    }
    out = Path("btci_v818c3_reports")
    out.mkdir(exist_ok=True)
    payload = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    (out / "historical_fork_git_vintages_FULL.json").write_bytes(payload)
    client = boto3.client("s3",
        endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        region_name="auto", aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
    bucket = os.environ["R2_BUCKET"]
    prefix = "research/btci/v8.18c3/runs/{}-{}/".format(
        os.environ["GITHUB_RUN_ID"], os.getenv("GITHUB_RUN_ATTEMPT", "1"))
    def put(key, body):
        digest = sha256(body)
        client.put_object(Bucket=bucket, Key=key, Body=body,
                          ContentType="application/json",
                          Metadata={"sha256": digest, "research-only": "true"})
        echo = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        if sha256(echo) != digest:
            raise RuntimeError("R2_SHA256_READBACK_FAIL")
        return {"key": key, "sha256": digest, "bytes": len(body)}
    rec = put(prefix + "historical_fork_git_vintages_FULL.json", payload)
    manifest_raw = (json.dumps({
        "version":"8.18c3", "researchOnly":True,"status":status,
        "preregSHA256":sha256(rawspec),"report":rec,
        "allGitBlobsVerified":not errors,"rawCsvNotRehosted":True,
        "portfolioWriteback":report["portfolioWriteback"]
    }, ensure_ascii=False, indent=2) + "\n").encode()
    man = put(prefix + "manifest.json", manifest_raw)
    result = {
        "status": status, "samples": len(sources), "sourceErrors": len(errors),
        "earliestSampleMVRV": report["earliestObservedMVRVContainingSnapshot"],
        "mvrvAvailability": {s["label"]:s["metricColumns"]["CapMVRVCur"] for s in sources},
        "reportSha256":rec["sha256"],"manifestSha256":man["sha256"], "prefix":prefix}
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("V818C3_RESULT " + json.dumps(result, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        selftest()
    else:
        main()
