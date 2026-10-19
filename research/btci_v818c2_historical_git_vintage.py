#!/usr/bin/env python3
"""BTCI v8.18c2: compare pinned 2026 Coin Metrics Git CSV vintages. RESEARCH ONLY."""
import csv
import hashlib
import io
import json
import os
import sys
import urllib.request
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "research/btci_v818c2_historical_git_vintage_prereg_2026-10-19.json"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def parse_csv(raw):
    source = io.StringIO(raw.decode("utf-8-sig"), newline="")
    reader = csv.DictReader(source)
    if not reader.fieldnames or "time" not in reader.fieldnames:
        raise RuntimeError("MISSING_TIME_COLUMN")
    seen, rows, previous = set(), {}, ""
    for row in reader:
        stamp = row["time"][:10]
        date.fromisoformat(stamp)
        if stamp in seen or stamp < previous:
            raise RuntimeError("DUPLICATE_OR_UNSORTED_DATE:" + stamp)
        seen.add(stamp)
        rows[stamp] = row
        previous = stamp
    if len(rows) < 4000:
        raise RuntimeError("SOURCE_SEEMS_TRUNCATED")
    return {"rows": rows, "columns": reader.fieldnames,
            "first": next(iter(rows)), "last": previous}


def number(s):
    if s is None or not s.strip():
        return None
    try:
        v = Decimal(s)
        return v if v.is_finite() else None
    except InvalidOperation:
        return None


def compare(old, new, spec):
    overlap = sorted(set(old["rows"]) & set(new["rows"]))
    boundary = spec["historicalEligibleEndDate"]
    overlap = [d for d in overlap if d <= boundary]
    eras = spec["historicalEraIntervals"]
    payload = {}
    for col in spec["columnNames"]:
        if col not in old["columns"] or col not in new["columns"]:
            payload[col] = {"status": "COLUMN_NOT_IN_BOTH_VINTAGES",
                            "oldPresent": col in old["columns"],
                            "newPresent": col in new["columns"]}
            continue
        stats = {"status": "COMPARABLE", "bothNumbers": 0, "equal": 0,
                 "revised": 0, "oneMissing": 0, "bothMissing": 0,
                 "eraRevised": {a + ".." + b: 0 for a,b in eras}}
        top = []
        for d in overlap:
            a = number(old["rows"][d].get(col))
            b = number(new["rows"][d].get(col))
            if a is None or b is None:
                stats["bothMissing" if a is None and b is None else "oneMissing"] += 1
            else:
                stats["bothNumbers"] += 1
                if a == b:
                    stats["equal"] += 1
                else:
                    stats["revised"] += 1
                    for start, end in eras:
                        if start <= d <= end:
                            stats["eraRevised"][start + ".." + end] += 1
                    top.append((abs(a-b), d, str(a), str(b)))
        stats["largestAbsoluteChanges"] = [
            {"date": d, "earlier": a, "later": b, "absoluteDifference": str(delta)}
            for delta, d, a, b in sorted(top, reverse=True)[:7]
        ]
        payload[col] = stats
    cases = {}
    for d in ["2012-06-03", "2018-11-18", "2021-04-11", "2024-01-07", "2026-03-20"]:
        cases[d] = {
            col: {"earlier": old["rows"].get(d,{}).get(col),
                  "later": new["rows"].get(d,{}).get(col)}
            for col in spec["columnNames"]
        } if d in overlap else {"status": "OUTSIDE_SHARED_DATE_COHORT"}
    return {"overlapCountBeforeCutoff": len(overlap),
            "oldOnlyDates": len(set(old["rows"]) - set(new["rows"])),
            "newOnlyDates": len(set(new["rows"]) - set(old["rows"])),
            "columns": payload, "fixedExampleDates": cases}


def selftest():
    assert git_blob(b"Hello world\n") == "802992c4220de19a90767f3000a79a31b98d0df7"
    example = b"time,CapMVRVCur\n2019-01-01,2.00\n2019-01-02,2.1\n"
    data = parse_fixture(example)
    assert data["rows"]["2019-01-02"]["CapMVRVCur"] == "2.1"
    assert number("2.00") == number("2") and number("nan") is None
    print("V818C2_SELFTEST_PASS", flush=True)


def parse_fixture(raw):
    # Small local test deliberately bypasses full-source minimum length guard.
    rdr = csv.DictReader(io.StringIO(raw.decode()))
    return {"rows": {r["time"][:10]: r for r in rdr}, "columns": rdr.fieldnames}


def main():
    spec_raw = SPEC.read_bytes()
    spec = json.loads(spec_raw)
    if spec["version"] != "8.18c2" or not spec["researchOnly"]:
        raise RuntimeError("PREREG_MISMATCH")
    s3 = boto3.client(
        "s3",
        endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = os.environ["R2_BUCKET"]
    for parent in spec["priorResearch"]:
        data = s3.get_object(Bucket=bucket, Key=parent["key"])["Body"].read()
        if digest(data) != parent["sha256"]:
            raise RuntimeError("PARENT_SHA_MISMATCH:" + parent["key"])
    vintages = {}
    for item in spec["fixedSources"]:
        req = urllib.request.Request(item["rawURL"],
                                     headers={"User-Agent":"BTCI-research-asof-vintage-audit/1.0"})
        with urllib.request.urlopen(req, timeout=75) as response:
            raw = response.read()
        if git_blob(raw) != item["blobGitSHA1"]:
            raise RuntimeError("GIT_BLOB_SHA_MISMATCH:" + item["label"])
        p = parse_csv(raw)
        vintages[item["label"]] = {
            "parsed": p,
            "sourceMeta": {k:v for k,v in item.items() if k != "rawURL"},
            "sha256": digest(raw), "bytes": len(raw),
            "dateRows": len(p["rows"]), "first": p["first"], "last": p["last"],
            "columns": p["columns"]
        }
    old = vintages["EARLY"]
    new = vintages["LATE"]
    calculated = compare(old["parsed"], new["parsed"], spec)
    report = {
        "version":"8.18c2", "status":"HISTORICAL_GIT_VINTAGES_AUDITED_NO_PRE2026_PIT",
        "researchOnly": True, "signalsAuthorized": False, "outOfSample": False,
        "preregistration": {"path":SPEC.relative_to(ROOT).as_posix(),
                            "sha256":digest(spec_raw)},
        "source": spec["repository"],
        "oldestReachableMainCommit": spec["repositoryOldestReachableMainCommit"],
        "oldestReachableMainCommitDate": spec["oldestMainCommitDateUTC"],
        "gitMainReachableCommitsObserved":spec["observedReachableMainCommitCount"],
        "vintages": {k:{x:v for x,v in p.items() if x != "parsed"}
                    for k,p in vintages.items()},
        "comparison":calculated,
        "findings": [
            "This public main Git history starts in March 2026; it cannot prove MVRV as-of access during 2012-2025.",
            "An observation-time date on a 2026 stored CSV is not the metric's 2012-2025 original publication time.",
            "Any changed historical values are evidence of source revision across these two 2026 source snapshots only.",
            "Equal historical values across two 2026 snapshots do not establish pre-2026 point-in-time availability."
        ],
        "limitations":spec["limitations"],
        "priorResearchPinsVerified":True,
        "portfolioWriteback":{k:False for k in
            ("Spot","Futures","NAV","PnL","reserve","capital","MASTER",
             "Detector","tradingLimits","orders")}
    }
    folder = Path("btci_v818c2_reports")
    folder.mkdir(exist_ok=True)
    def dump(obj):
        return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode()
    prefix = ("research/btci/v8.18c2/runs/" + os.environ["GITHUB_RUN_ID"]
              + "-" + os.getenv("GITHUB_RUN_ATTEMPT","1") + "/")
    def archive(name, raw):
        path=prefix+name
        h=digest(raw)
        s3.put_object(Bucket=bucket, Key=path, Body=raw,
                      ContentType="application/json",
                      Metadata={"sha256":h,"research-only":"true"})
        verified=s3.get_object(Bucket=bucket,Key=path)["Body"].read()
        if digest(verified)!=h:
            raise RuntimeError("R2_SHA_READBACK_FAILURE:"+name)
        return {"key":path,"sha256":h,"bytes":len(raw)}
    raw = dump(report)
    (folder/"github_vintage_comparison_FULL.json").write_bytes(raw)
    item = archive("github_vintage_comparison_FULL.json",raw)
    manifest = archive("manifest.json",dump({
        "version":"8.18c2", "researchOnly":True, "preregSha256":digest(spec_raw),
        "report":item, "sourceSnapshotsSHA256":{
            k:v["sha256"] for k,v in vintages.items()},
        "rawCSVRepublished":False, "source":"Coin Metrics CC BY-NC 4.0"
    }))
    summary = {
        "status":report["status"], "oldestAvailableMainDate":"2026-03-26",
        "earlyRows":old["dateRows"],"lateRows":new["dateRows"],
        "comparedHistoricalDays":calculated["overlapCountBeforeCutoff"],
        "metricResults":{
            k:{"status":v["status"],"revised":v.get("revised"),
               "bothNumbers":v.get("bothNumbers")}
            for k,v in calculated["columns"].items()},
        "reportSha256":item["sha256"],"manifestSha256":manifest["sha256"],
        "prefix":prefix
    }
    (folder/"summary.json").write_bytes(dump(summary))
    print("V818C2_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)


if __name__ == "__main__":
    if "--self-test" in sys.argv: selftest()
    else: main()
