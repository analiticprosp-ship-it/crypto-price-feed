"""Pure offline policy for bounded H1-H10 research archive sync.

Never infer a failed upload from an expired/missing historical GitHub artifact;
never classify a network, checksum, auth or R2 readback error as a benign skip.
"""
import datetime as dt

OPERATIONAL_WORKFLOWS=frozenset({
    "Detector H1-H10 Research R2 Archive",
    "Detector H1-H10 Independent R2 Integrity Audit",
    "Detector H1-H10 Live OI Availability Research",
    "Detector H1-H10 Fastlane Gatekeeper",
})
MAX_ARTIFACT_BYTES=80_000_000
LOOKBACK_DAYS=7
MAX_PAGES=8

def is_research_candidate(run):
    return (isinstance(run,dict)
       and run.get("name","").startswith("Detector H1-H10 ")
       and run.get("name") not in OPERATIONAL_WORKFLOWS
       and run.get("head_branch")=="main"
       and run.get("conclusion")=="success"
       and isinstance(run.get("id"),int))

def artifact_plan(artifacts,maximum=MAX_ARTIFACT_BYTES):
    if not isinstance(artifacts,list):raise ValueError("ARTIFACT_API_SCHEMA_INVALID")
    usable=[];skips=[]
    for art in artifacts:
        if not isinstance(art,dict) or not isinstance(art.get("id"),int):
            raise ValueError("ARTIFACT_ID_MISSING")
        size=art.get("size_in_bytes")
        if not isinstance(size,int) or size<0:raise ValueError("ARTIFACT_SIZE_INVALID")
        if art.get("expired"):
            skips.append({"artifact_id":art["id"],"reason":"EXPIRED_GITHUB_RETENTION"})
        elif size==0:
            skips.append({"artifact_id":art["id"],"reason":"EMPTY_ARTIFACT"})
        elif size>maximum:
            skips.append({"artifact_id":art["id"],"reason":"ARTIFACT_EXCEEDS_SAFETY_CAP"})
        else:
            if not art.get("archive_download_url") or not art.get("name"):
                raise ValueError("ARTIFACT_DOWNLOAD_METADATA_MISSING")
            usable.append(art)
    return usable,skips

def no_artifact_classification(artifacts,skipped):
    if artifacts and skipped and all(q["reason"]=="EXPIRED_GITHUB_RETENTION" for q in skipped):
        return "HISTORICAL_ARTIFACTS_EXPIRED"
    if artifacts and skipped:
        return "NO_ELIGIBLE_ARTIFACTS"
    return "SUCCESSFUL_WORKFLOW_WITH_NO_ARTIFACT_OUTPUT"

def is_recent(iso_timestamp,now,lookback_days=LOOKBACK_DAYS):
    if not isinstance(iso_timestamp,str):raise ValueError("MISSING_RUN_TIMESTAMP")
    stamp=dt.datetime.fromisoformat(iso_timestamp.replace("Z","+00:00"))
    if stamp.tzinfo is None:raise ValueError("RUN_TIMESTAMP_NAIVE")
    return stamp >= now-dt.timedelta(days=lookback_days)

def select_since_cursor(batch,cursor):
    """Only unprocessed *newer* run IDs; fail-closed on pagination disorder."""
    if not isinstance(batch,list):raise ValueError("INVALID_RUN_LIST")
    values=[r.get("id") for r in batch]
    if any(not isinstance(x,int) for x in values):
        raise ValueError("GITHUB_RUN_ID_MISSING")
    if values!=sorted(values,reverse=True):
        raise ValueError("GITHUB_RUNS_NOT_DESCENDING")
    return [r for r in batch if r["id"]>cursor],bool(values and values[-1]<=cursor)
