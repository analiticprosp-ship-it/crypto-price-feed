#!/usr/bin/env python3
"""Independent RESEARCH_ONLY audit of 48h pilot expiry and ACTUAL self-disable.

Read-only GitHub API; SHA-verifies immutable R2 pilot configs; optionally
checks GitHub completed run job logs for the exact self-disable success marker.
Does NOT disable/re-enable either workflow, issue orders, or promote PIT.
A disabled workflow state alone NEVER proves which actor disabled it.
"""
import datetime as dt
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import boto3
from research.detector_okx_oi_48h_pilot import store

SCHEMA = "detector-h1h10-independent-pilot-expiry-v1"
PREFIX = "research/detector-okx-pilot-expiry-independent/v1"
DURATION_MS = 48 * 3600 * 1000
MAX_CONFIG_BYTES = 20000
MAX_LOG_BYTES = 3000000
MAX_POST_EXPIRY_RUNS = 8
REPO = "analiticprosp-ship-it/crypto-price-feed"
CONFIGS = {
    "oi_only": {
        "config": "research/oi-availability-okx/v1/pilot/config.json",
        "schema": "detector-okx-oi-5m-forward-48h-v1",
        "workflow": "detector-okx-oi-48h-pilot.yml",
        "stop_marker": "OKX_OI_48H_PILOT_CLOSED",
    },
    "oi_price_flow": {
        "config": "research/detector-okx-3metric-forward/v1/config.json",
        "schema": "detector-okx-3metric-prospective-v1",
        "workflow": "detector-okx-3metric-forward-48h.yml",
        "stop_marker": "THREE_METRIC_PILOT_STOPPED",
    },
}


def utc_ms_to_string(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat()


def validate_config(config, expected_schema, now_ms):
    if (not isinstance(config, dict)
        or config.get("schema") != expected_schema
        or config.get("research_only") is not True):
        raise ValueError("PILOT_EXPIRY_CONFIG_NOT_TRUSTED")
    start, end = config.get("start_ms"), config.get("end_ms")
    if (type(start) is not int or type(end) is not int
        or end - start != DURATION_MS
        or start < 1600000000000 or start > now_ms):
        raise ValueError("PILOT_EXPIRY_DURATION_OR_CLOCK_INVALID")
    return start, end


def classify(now_ms, config, workflow_state, stop_log_evidence=None):
    """Only 2 independent proofs (disabled state + stop log) qualify actual self-disable."""
    start, end = validate_config(config, config["schema"], now_ms)
    due = now_ms >= end
    if workflow_state not in ("active", "disabled_manually", "disabled_inactivity"):
        raise ValueError("GITHUB_WORKFLOW_STATE_UNKNOWN")
    if not due:
        label = "NOT_YET_DUE" if workflow_state == "active" else "DISABLED_BEFORE_EXPIRY_UNEXPLAINED"
    elif workflow_state == "active":
        label = "EXPIRED_BUT_GITHUB_WORKFLOW_ACTIVE"
    elif stop_log_evidence is True and workflow_state == "disabled_manually":
        label = "SELF_DISABLE_VERIFIED_STOP_LOG_AND_DISABLED_STATE"
    else:
        label = "DISABLED_OBSERVED_SELF_DISABLE_CAUSE_UNVERIFIED"
    return {
        "pilot_start_utc": utc_ms_to_string(start),
        "pilot_end_utc": utc_ms_to_string(end),
        "checked_at_utc": utc_ms_to_string(now_ms),
        "expiry_reached": due,
        "github_workflow_state": workflow_state,
        "stop_log_marker_verified": stop_log_evidence is True,
        "stop_log_marker_lookup": "VERIFIED" if stop_log_evidence is True else (
            "NOT_DUE" if not due else "UNVERIFIED"),
        "status": label,
        "self_disable_approved_as_actual": label == "SELF_DISABLE_VERIFIED_STOP_LOG_AND_DISABLED_STATE",
        "causal_h1h10_rows_authorized": 0,
    }


def read_r2_config(s3, bucket, key):
    obj = s3.get_object(Bucket=bucket, Key=key)
    if obj.get("ContentLength", MAX_CONFIG_BYTES + 1) > MAX_CONFIG_BYTES:
        raise ValueError("PILOT_EXPIRY_CONFIG_OVERSIZE")
    data = obj["Body"].read(MAX_CONFIG_BYTES + 1)
    digest = hashlib.sha256(data).hexdigest()
    if len(data) > MAX_CONFIG_BYTES or obj.get("Metadata", {}).get("sha256") != digest:
        raise ValueError("PILOT_EXPIRY_CONFIG_SHA_METADATA_MISMATCH")
    return json.loads(data), digest


def github_get(url, token, raw=False, cap=MAX_LOG_BYTES):
    if not url.startswith("https://api.github.com/repos/" + REPO + "/actions/"):
        raise ValueError("GITHUB_EXPIRY_UNAPPROVED_API_PATH")
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "H1H10-ResearchOnly-ExpiryAudit/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read(cap + 1)
    if len(data) > cap:
        raise ValueError("GITHUB_EXPIRY_API_RESPONSE_OVERSIZE")
    return data if raw else json.loads(data)


def github_workflow_state(token, workflow):
    url = "https://api.github.com/repos/" + REPO + "/actions/workflows/" + workflow
    response = github_get(url, token)
    if response.get("path") != ".github/workflows/" + workflow:
        raise ValueError("GITHUB_WORKFLOW_IDENTITY_UNVERIFIED")
    return response.get("state")


def stop_marker_from_completed_runs(token, workflow, end_ms, marker):
    """Check exact marker in successful run job logs occurring after expiry.

    If API/log proof is absent or fails, caller records UNVERIFIED; no guessing
    based on the GitHub workflow disabled state alone.
    """
    prefix = "https://api.github.com/repos/" + REPO + "/actions/"
    url = prefix + "workflows/" + workflow + "/runs?per_page=25"
    runs = github_get(url, token)
    seen = 0
    for run in runs.get("workflow_runs", []):
        when = run.get("run_started_at") or run.get("created_at")
        if not isinstance(when, str):
            continue
        start = int(dt.datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp() * 1000)
        if start < end_ms or run.get("conclusion") != "success":
            continue
        seen += 1
        if seen > MAX_POST_EXPIRY_RUNS:
            break
        job_url = prefix + "runs/" + str(run["id"]) + "/jobs?per_page=30"
        jobs = github_get(job_url, token)
        for job in jobs.get("jobs", []):
            if job.get("conclusion") != "success":
                continue
            # GET job logs redirects to GitHub-authorized downloadable log file.
            log_url = prefix + "jobs/" + str(job["id"]) + "/logs"
            log = github_get(log_url, token, raw=True)
            if marker.encode("ascii") in log:
                return True
    return False


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    if repo != REPO:
        raise ValueError("GITHUB_REPO_IDENTITY_MISMATCH")
    run = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    if not run.isdigit() or not attempt.isdigit():
        raise ValueError("INVALID_GITHUB_RUN_ID")
    token = os.environ["GH_TOKEN"]
    bucket = os.environ["R2_BUCKET"]
    s3 = boto3.client("s3",
        endpoint_url="https://" + os.environ["R2_ACCOUNT_ID"] + ".r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="auto")
    now = int(time.time() * 1000)
    states = {}
    for name, spec in CONFIGS.items():
        config, sha = read_r2_config(s3, bucket, spec["config"])
        validate_config(config, spec["schema"], now)
        state = github_workflow_state(token, spec["workflow"])
        stop = None
        err = None
        if now >= config["end_ms"] and state == "disabled_manually":
            try:
                stop = stop_marker_from_completed_runs(
                    token, spec["workflow"], config["end_ms"], spec["stop_marker"])
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
                err = type(exc).__name__
        result = classify(now, config, state, stop)
        result["config_key"] = spec["config"]
        result["config_sha256"] = sha
        result["workflow"] = spec["workflow"]
        result["stop_log_check_error_type"] = err
        states[name] = result
    report = {
        "schema": SCHEMA, "scope": "RESEARCH_ONLY",
        "edge_status": "EDGE_UNVALIDATED", "trading_actions": False,
        "checked_at_utc": utc_ms_to_string(now),
        "github_run_id": run, "attempt": attempt,
        "data_origin": "R2_SHA_PINNED_CONFIG_AND_LIVE_GITHUB_ACTIONS_GET",
        "self_disable_never_inferred_from_config_or_disabled_state_alone": True,
        "historical_pit_verified": False,
        "causal_h1h10_rows_authorized": 0,
        "states": states,
    }
    key = PREFIX + "/run-reports/" + run + "-" + attempt + ".json"
    sha = store(s3, bucket, key, report)
    print("H1H10_INDEPENDENT_PILOT_EXPIRY", json.dumps({
        "states": {k: v["status"] for k, v in states.items()},
        "r2_key": key, "sha256": sha,
        "historical_pit": "BLOCKED"}, sort_keys=True), flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fp:
            fp.write("## H1H10 Independent pilot expiry verification (RESEARCH_ONLY)\n\n")
            for k, v in states.items():
                fp.write(f"- {k}: {v['status']}; due at {v['pilot_end_utc']}\n")
            fp.write(f"\nR2: {key}; SHA256: {sha}\n\nHistorical PIT and H1–H10 edge BLOCKED.\n")


if __name__ == "__main__":
    main()
