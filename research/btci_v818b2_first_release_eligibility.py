#!/usr/bin/env python3
"""BTCI v8.18b2: source first-publication eligibility, research-only; no FRED fetching."""
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "research/btci_v818b2_first_release_eligibility_prereg_2026-10-19.json"
FIRST_RELEASE = date(2019, 2, 4)
ONLY_INVALID_SUNDAY = date(2019, 2, 3)


def sha(v):
    return hashlib.sha256(v).hexdigest()


def category(asof, status):
    when = date.fromisoformat(asof)
    if when < FIRST_RELEASE:
        if when != ONLY_INVALID_SUNDAY or status != "HTTP_BLOCKED":
            raise ValueError("UNEXPECTED_PREPUBLICATION_OBSERVATION")
        return "INELIGIBLE_PRIOR_TO_FIRST_OFFICIAL_RELEASE"
    if status != "ASOF_HISTORICAL_VALID":
        raise ValueError("POST_RELEASE_SOURCE_ERROR_MUST_NOT_BE_WAIVED")
    return "VALID_ASOF_VINTAGE"


def selftest():
    assert category("2019-02-03", "HTTP_BLOCKED") == "INELIGIBLE_PRIOR_TO_FIRST_OFFICIAL_RELEASE"
    assert category("2019-02-10", "ASOF_HISTORICAL_VALID") == "VALID_ASOF_VINTAGE"
    for asof, quality in [
        ("2019-02-10", "HTTP_BLOCKED"),
        ("2019-01-27", "ASOF_HISTORICAL_VALID"),
    ]:
        try:
            category(asof, quality)
        except ValueError:
            pass
        else:
            raise AssertionError("PREPUBLICATION_GUARD_BYPASSED")
    print("V818B2_SELFTEST_PASS", flush=True)


def main():
    spec_raw = SPEC.read_bytes()
    spec = json.loads(spec_raw)
    if spec["version"] != "8.18b2" or not spec["researchOnly"]:
        raise RuntimeError("PREREG_VERSION_GUARD_FAILED")
    client = boto3.client(
        "s3",
        endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = os.environ["R2_BUCKET"]

    def get(entry):
        raw = client.get_object(Bucket=bucket, Key=entry["key"])["Body"].read()
        if sha(raw) != entry["sha256"]:
            raise RuntimeError("PINNED_PARENT_SHA_MISMATCH: " + entry["key"])
        return raw

    def put(key, raw):
        dg = sha(raw)
        client.put_object(
            Bucket=bucket, Key=key, Body=raw, ContentType="application/json",
            Metadata={"sha256": dg, "research-only": "true"},
        )
        echo = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        if sha(echo) != dg:
            raise RuntimeError("R2_SHA_READBACK_MISMATCH")
        return {"key": key, "sha256": dg, "bytes": len(raw)}

    pinned = spec["pins"]
    previous = json.loads(get(pinned["v818bReport"]))
    failed_repair = json.loads(get(pinned["v818b1Research"]))
    source = [
        json.loads(v) for v in get(pinned["v818bUsdAudit"]).splitlines() if v.strip()
    ]
    if (len(source) != 342 or
        previous["qualityUnresolvedTransient"]["DTWEXBGS"] != 1 or
        failed_repair["status"] != "SOURCE_REPAIR_UNRESOLVED" or
        failed_repair["expectedTransient"]["date"] != "2019-02-03"):
        raise RuntimeError("PARENT_QUALITY_STATE_CHANGED")
    seen = set()
    records = []
    for rec in source:
        asof = rec["asOf"]
        if asof in seen:
            raise RuntimeError("DUPLICATE_ASOF")
        seen.add(asof)
        records.append({
            "asofSunday": asof,
            "previousStatus": rec["audit"]["status"],
            "auditedEligibility": category(asof, rec["audit"]["status"]),
            "sourceRawSha256": rec["audit"].get("rawSha256"),
        })
    valid = sum(r["auditedEligibility"] == "VALID_ASOF_VINTAGE" for r in records)
    excluded = [r for r in records if r["auditedEligibility"] != "VALID_ASOF_VINTAGE"]
    if valid != 341 or len(excluded) != 1 or excluded[0]["asofSunday"] != "2019-02-03":
        raise RuntimeError("ELIGIBLE_341_OF_341_GUARD_FAILED")
    panel = previous["all684ResearchRows"]
    if len(panel) != 684 or any("DTWEXBGS" in r.get("newMacroFactors", {}) for r in panel if r["date"] == "2019-02-03"):
        raise RuntimeError("HISTORY_PANEL_OVERWRITE_OR_SIZE_CHANGED")
    source_stats = {
        "firstOfficialRelease": FIRST_RELEASE.isoformat(),
        "requestedUnderOriginalPrereg": 342,
        "actuallyPITEligible": 341,
        "validWithinEligible": 341,
        "prePublicationExclusions": 1,
        "prePublicationSunday": "2019-02-03",
        "fetchedAdditionalObservations": 0,
        "newRetrospectiveValuesImputed": 0,
    }
    preserved_json = json.dumps(
        previous["studyResults"], ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode()
    report = {
        "version": "8.18b2",
        "status": "PUBLICATION_ELIGIBILITY_CORRECTED_NO_NEW_DATA",
        "researchOnly": True, "tradeAuthorized": False, "notOOS": True,
        "preregistration": {"path": SPEC.relative_to(ROOT).as_posix(),
                            "sha256": sha(spec_raw)},
        "pinnedPriorSourceResearch": pinned,
        "sourceAuthority": spec["sourceAuthority"],
        "sourceEligibility": source_stats,
        "eachAsOfClassification": records,
        "immutablePriorStudyResultsSha256": sha(preserved_json),
        "priorStudiesUnchanged": previous["studyResults"],
        "parent684RowsUnchanged": True,
        "finding": (
            "DTWEXBGS published 2019-02-04; 2019-02-03 Sunday is "
            "pre-publication, not a missing negative economic signal. "
            "Backfilled pre-2019 data were never public as DTWEXBGS then."
        ),
        "remainingLimitations": [
            "DTWEXBGS original as-of coverage 2012-2018 unavailable, no silent substitution.",
            "Original H.10 release intraday clock not audited.",
            "June 2019 indexation changes and older goods-only dollar variants remain distinct.",
            "The 341 validated Sundays are dependent weekly historical samples, not 341 independent out-of-sample forecasts.",
            "Past macro BTC phase classifications not directly executable trades.",
        ],
        "portfolioWriteback": {k: False for k in (
            "Spot", "Futures", "NAV", "PnL", "capital",
            "reserve", "MASTER", "Detector", "tradingLimits", "orders"
        )},
    }
    out = Path("btci_v818b2_reports")
    out.mkdir(exist_ok=True)
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    (out / "publication_eligibility_FULL.json").write_bytes(raw)
    prefix = (
        "research/btci/v8.18b2/runs/"
        + os.environ["GITHUB_RUN_ID"] + "-"
        + os.getenv("GITHUB_RUN_ATTEMPT", "1") + "/"
    )
    result = put(prefix + "publication_eligibility_FULL.json", raw)
    manifest_raw = (json.dumps({
        "version": "8.18b2", "researchOnly": True, "status": report["status"],
        "preregSha256": sha(spec_raw), "fullReport": result,
        "pinnedParents": pinned,
    }, ensure_ascii=False, indent=2) + "\n").encode()
    manifest = put(prefix + "manifest.json", manifest_raw)
    summary = {
        "status": report["status"],
        "asofPrepublication": "2019-02-03",
        "actualEligible": 341, "valid": 341,
        "sourceRequeries": 0,
        "priorStudyResultsSha256": sha(preserved_json),
        "reportSha256": result["sha256"],
        "manifestSha256": manifest["sha256"],
        "prefix": prefix,
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print("V818B2_RESULT " + json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        selftest()
    else:
        main()
