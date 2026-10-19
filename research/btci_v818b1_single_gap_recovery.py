#!/usr/bin/env python3
"""BTCI v8.18b1: repair exactly one missing historical USD vintage (RESEARCH_ONLY).

Never re-fetch validated rows, mutate older R2 objects, or retune hypotheses.
"""
import hashlib
import json
import os
import runpy
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "research/btci_v818b1_single_gap_recovery_prereg_2026-10-19.json"
PARENT = ROOT / "research/btci_three_factor_asof_v818b.py"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def r2():
    client = boto3.client(
        "s3",
        endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    return client, os.environ["R2_BUCKET"]


def checked_get(client, bucket, entry):
    raw = client.get_object(Bucket=bucket, Key=entry["key"])["Body"].read()
    if sha(raw) != entry["sha256"]:
        raise RuntimeError("PINNED_R2_SHA_MISMATCH: " + entry["key"])
    return raw


def checked_put(client, bucket, key, raw, typ="application/json"):
    h = sha(raw)
    client.put_object(
        Bucket=bucket, Key=key, Body=raw, ContentType=typ,
        Metadata={"sha256": h, "research-only": "true"},
    )
    if sha(client.get_object(Bucket=bucket, Key=key)["Body"].read()) != h:
        raise RuntimeError("R2_READBACK_SHA_MISMATCH: " + key)
    return {"key": key, "sha256": h, "bytes": len(raw)}


def make_rows(parent_rows, old_rows, target_date=None, patched_usd=None, parent_module=None):
    if len(parent_rows) != 684 or len(old_rows) != 684:
        raise RuntimeError("FROZEN_PANEL_SIZE_MISMATCH")
    out = []
    for original, prior in zip(parent_rows, old_rows):
        if original["date"] != prior["date"] or original["outcomes"] != prior["outcomes"]:
            raise RuntimeError("FROZEN_PARENT_CHANGED")
        factors = dict(prior.get("newMacroFactors", {}))
        if original["date"] == target_date and patched_usd is not None:
            if "DTWEXBGS" in factors:
                raise RuntimeError("ATTEMPT_TO_OVERWRITE_VALID_FACTOR")
            factors["DTWEXBGS"] = patched_usd
        copied = dict(original)
        copied["newMacroFactors"] = factors
        copied["flags"] = parent_module["flags"](original, factors)
        out.append(copied)
    return out


def calculate(rows, m):
    studies = {
        "REAL_RATE": m["BASE"] + m["RATES"],
        "DOLLAR": m["BASE"] + (
            "DOLLAR_SOFT", "DOLLAR_STRONG",
            "ALL_OLD_USD_SOFT", "DOWN_OLD_USD_STRONG",
        ),
        "CURVE": m["BASE"] + m["CURVE"],
        "REAL_AND_USD": m["BASE"] + m["RATES"] + m["USD"],
    }
    return {
        name: {
            "all": m["calc"](rows, fields),
            "eras": {
                era: m["calc"]([r for r in rows if r["era"] == era], fields)
                for era in ("2012", "2013-2016", "2017-2019", "2020-2023", "2024-2025")
            },
            "lock13": m["lockSummary"](
                [r for r in rows if all(k in r["flags"] for k in fields)], 13, fields
            ),
            "lock26": m["lockSummary"](
                [r for r in rows if all(k in r["flags"] for k in fields)], 26, fields
            ),
        }
        for name, fields in studies.items()
    }


def selftest():
    module = runpy.run_path(str(PARENT))
    flags = {"A": True, "F": True, "BTC_FED": True,
             "STRICT_MACRO": False, "STRICT_ALL": False, "NEG_ALL": False}
    sample = {"date": "2020-05-03", "flags": flags, "outcomes": {}}
    records = [dict(sample, date=f"2020-05-{d:02d}") for d in range(1, 27)]
    records = records * 26 + records[:8]  # exactly 684 synthetic rows
    old = [{"date": r["date"], "outcomes": {}, "newMacroFactors": {}}
           for r in records]
    old[0]["newMacroFactors"]["DTWEXBGS"] = {
        "status": "ASOF_HISTORICAL_VALID", "changeFourWeek": -0.1,
    }
    no_patch = make_rows(records, old, parent_module=module)
    assert no_patch[0]["flags"]["DOLLAR_SOFT"] is True
    try:
        make_rows(records, old, records[0]["date"],
                  {"status": "ASOF_HISTORICAL_VALID", "changeFourWeek": 0.1}, module)
    except RuntimeError as exc:
        assert "ATTEMPT_TO_OVERWRITE_VALID_FACTOR" in str(exc)
    else:
        raise AssertionError("Valid source overwrite guard failed")
    print("V818B1_SELFTEST_PASS", flush=True)


def main():
    raw_spec = PREREG.read_bytes()
    spec = json.loads(raw_spec)
    if spec["version"] != "8.18b1" or not spec["researchOnly"]:
        raise RuntimeError("PREREG_GUARD_FAIL")
    module = runpy.run_path(str(PARENT))
    cloud, bucket = r2()
    pins = spec["immutableParents"]
    old_raw = checked_get(cloud, bucket, pins["macroReport"])
    usd_raw = checked_get(cloud, bucket, pins["usdAudit"])
    btc_raw = checked_get(cloud, bucket, pins["frozenBTC"])
    old = json.loads(old_raw)
    original = json.loads(btc_raw)
    frozen = original["weeklyPanel"]
    prior_rows = old["all684ResearchRows"]
    old_archive = old["officialFedHistoricalAsOfArchives"]["DTWEXBGS"]
    if old_archive["sha256"] != pins["usdAudit"]["sha256"]:
        raise RuntimeError("SOURCE_ARCHIVE_REFERENCE_MISMATCH")
    if old.get("qualityUnresolvedTransient", {}).get("DTWEXBGS") != 1:
        raise RuntimeError("NOT_EXACTLY_ONE_TRANSIENT")
    lines = [json.loads(z) for z in usd_raw.splitlines() if z.strip()]
    if len(lines) != spec["expected"]["requested"]:
        raise RuntimeError("SOURCE_AUDIT_ROW_COUNT_CHANGED")
    dates = [x["asOf"] for x in lines]
    if len(set(dates)) != len(dates):
        raise RuntimeError("DUPLICATE_HISTORICAL_SUNDAY")
    failed = [x for x in lines if x["audit"]["status"] != "ASOF_HISTORICAL_VALID"]
    good_count = len(lines) - len(failed)
    if len(failed) != 1 or good_count != 341:
        raise RuntimeError("SOURCE_STATUS_GUARD_FAILED")
    error = failed[0]
    if error["audit"]["status"] != spec["expected"]["missingStatus"]:
        raise RuntimeError("UNEXPECTED_ERROR_CLASS")
    target = error["asOf"]
    if target < "2019-02-03" or target not in {r["date"] for r in frozen}:
        raise RuntimeError("UNSUPPORTED_HISTORICAL_DATE")
    before_rows = make_rows(frozen, prior_rows, parent_module=module)
    before_results = calculate(before_rows, module)
    for name in before_results:
        if before_results[name]["all"] != old["studyResults"][name]["all"]:
            raise RuntimeError("PRE_REPAIR_STATISTICAL_REPLAY_MISMATCH: " + name)

    # This is the ONE and ONLY new historical FRED fetch. No other vintage is queried.
    candidate, raw = module["fetch"](
        "DTWEXBGS", target, os.environ["FRED_API_KEY"], 11
    )
    success = candidate["status"] == "ASOF_HISTORICAL_VALID"
    if success and (not raw or candidate["sunday"] != target or sha(raw) != candidate["rawSha256"]):
        raise RuntimeError("REPAIR_VINTAGE_BYTES_MISMATCH")
    after_rows = make_rows(
        frozen, prior_rows, target, candidate if success else None, module
    )
    after_results = calculate(after_rows, module)
    if success:
        for name in ("REAL_RATE", "CURVE"):
            if after_results[name] != before_results[name]:
                raise RuntimeError("UNTOUCHED_FACTOR_RECOMPUTED_DIFFERENTLY")
        if sum("DTWEXBGS" in r["newMacroFactors"] for r in after_rows) != 342:
            raise RuntimeError("USD_RECOVERY_COVERAGE_NOT_342")

    prefix = (
        "research/btci/v8.18b1/runs/"
        + os.environ["GITHUB_RUN_ID"] + "-"
        + os.getenv("GITHUB_RUN_ATTEMPT", "1") + "/"
    )
    recovered_archive = (
        checked_put(cloud, bucket, prefix + "source/recovered_DTWEXBGS_" + target + ".json", raw)
        if success else None
    )
    baseline = {
        name: {
            "beforeN": before_results[name]["all"]["n"],
            "afterN": after_results[name]["all"]["n"],
            "beforeUP26": before_results[name]["all"]["targetBaseRates"]["UP26"],
            "afterUP26": after_results[name]["all"]["targetBaseRates"]["UP26"],
            "beforeDOWN26": before_results[name]["all"]["targetBaseRates"]["DOWN26"],
            "afterDOWN26": after_results[name]["all"]["targetBaseRates"]["DOWN26"],
        }
        for name in before_results
    }
    status = "SOURCE_REPAIRED_SINGLE_GAP" if success else "SOURCE_REPAIR_UNRESOLVED"
    report = {
        "version": "8.18b1", "status": status,
        "researchOnly": True, "tradeAuthorized": False,
        "notOutOfSample": True, "noNewPredictiveHypothesis": True,
        "preregistration": {"path": PREREG.relative_to(ROOT).as_posix(), "sha256": sha(raw_spec)},
        "immutableParents": pins,
        "expectedTransient": {"date": target, "priorError": error["audit"]},
        "recovery": {"audit": candidate, "officialRawArchive": recovered_archive},
        "originalValidatedUsdRows": 341,
        "validatedUsdRowsAfterRepair": 342 if success else 341,
        "allOriginalWeeks": 684,
        "cohortComparisons": baseline,
        "fullRecalculatedStudyResults": after_results,
        "failureNotConvertedIntoNegativeEconomicSignal": True,
        "historicalPublicationClockVerified": False,
        "sourcePIT": "FRED_ALFRED_ASOF_SUNDAY_VINTAGE_DATE_ONLY",
        "interpretation": [
            "One targeted retry only; original 684 BTC historical outcomes never changed.",
            "Same dates for every base and conditional model; no new thresholds or optimization.",
            "Old v8.18b source and reports remain pinned and unchanged.",
            "Retrospective study, not OOS evidence; overlapping weeks and cycle dependence remain.",
            "Original daily publication times not independently authenticated.",
        ],
        "noChanges": {k: False for k in (
            "MASTER", "Detector", "Spot", "Futures", "NAV",
            "PnL", "capital", "reserve", "tradingLimits", "trades"
        )},
    }
    out = Path("btci_v818b1_reports")
    out.mkdir(exist_ok=True)
    body = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    (out / "single_gap_recovery_FULL.json").write_bytes(body)
    full = checked_put(cloud, bucket, prefix + "single_gap_recovery_FULL.json", body)
    man = {
        "version": "8.18b1", "status": status, "researchOnly": True,
        "preregSha256": sha(raw_spec), "parents": pins,
        "report": full, "sourceRecovery": recovered_archive,
    }
    manifest = checked_put(
        cloud, bucket, prefix + "manifest.json",
        (json.dumps(man, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    summary = {
        "status": status, "targetSunday": target, "source": candidate["status"],
        "validatedUsdRowsAfterRepair": report["validatedUsdRowsAfterRepair"],
        "reportSha256": full["sha256"], "manifestSha256": manifest["sha256"],
        "prefix": prefix, "matchedCohorts": baseline,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print("V818B1_RESULT " + json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        selftest()
    else:
        main()
