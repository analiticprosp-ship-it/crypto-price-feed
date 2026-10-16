"""Append-only-ish research event journal for Detector SHADOW candidates.

Preserve two separate real times:
- bar close: when a closed-candle condition is retrospectively established
- first detector evaluation: first observed run, never backdated to bar close.
GitHub commit/publication and ChatGPT alert arrival can be later, separately.
No trade approval, order triggers, portfolio or trading price ownership.
"""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import hashlib
import json

VERSION="detector-signal-events-1.0"
STATE="EARLY_CANDIDATE_SHADOW"
MADRID=ZoneInfo("Europe/Madrid")
RETAIN_DAYS=30
MAX_EVENTS=8000

def time_iso(ms, local=False):
    tz=MADRID if local else timezone.utc
    return datetime.fromtimestamp(ms/1000,timezone.utc).astimezone(tz).isoformat(timespec="milliseconds")

def utc_timestamp(value):
    if not isinstance(value,str):return None
    try:
        x=datetime.fromisoformat(value.replace("Z","+00:00"))
        return int(x.timestamp()*1000) if x.tzinfo is not None else None
    except (ValueError,OverflowError):return None

def event_id(record):
    raw=f"{record['symbol']}|{record['direction']}|{record['eventEndMs']}|{STATE}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

def annotate(report, prior, *, now_ms):
    """Augment snapshot and journal together. Errors refuse silent journal resets.

    First deployment imports the latest transient snapshot as a notification-
    suppressed baseline; first detection time is UNKNOWN for preexisting events.
    """
    if (not isinstance(report,dict) or report.get("researchOnly") is not True or
        report.get("notTradeApproval") is not True):
        raise ValueError("INVALID_RESEARCH_REPORT")
    if prior is not None and (not isinstance(prior,dict) or
                              prior.get("schemaVersion")!=VERSION or
                              not isinstance(prior.get("events"),list)):
        raise ValueError("INVALID_EXISTING_EVENT_JOURNAL")
    bootstrap=prior is None
    events=[] if bootstrap else list(prior["events"])
    seen={}
    for x in events:
        if not isinstance(x,dict) or not isinstance(x.get("eventId"),str):
            raise ValueError("INVALID_STORED_EVENT")
        if x["eventId"] in seen:
            raise ValueError("DUPLICATE_STORED_EVENT_ID")
        seen[x["eventId"]]=x
    added=0
    candidates=report.get("candidates")
    if not isinstance(candidates,list):raise ValueError("INVALID_CANDIDATES")
    for candidate in candidates:
        if (not isinstance(candidate,dict) or
            candidate.get("status")!=STATE or
            candidate.get("direction") not in ("LONG","SHORT") or
            not isinstance(candidate.get("symbol"),str)):
            raise ValueError("INVALID_CANDIDATE")
        bar_end=candidate.get("eventEndMs")
        if (not isinstance(bar_end,int) or isinstance(bar_end,bool) or
            bar_end>now_ms or now_ms-bar_end>35*60000):
            raise ValueError("CANDIDATE_OUTSIDE_VALID_CLOSED_BAR_WINDOW")
        key=event_id(candidate)
        old=seen.get(key)
        if old is None:
            record={
                "eventId":key,
                "symbol":candidate["symbol"],
                "direction":candidate["direction"],
                "status":STATE,
                "signalCandleClosedAtUtc":time_iso(bar_end),
                "signalCandleClosedAtMadrid":time_iso(bar_end,True),
                "signalCandleClosedAtMs":bar_end,
                "firstDetectedAtUtc":None if bootstrap else time_iso(now_ms),
                "firstDetectedAtMadrid":None if bootstrap else time_iso(now_ms,True),
                "detectionLagSeconds":None if bootstrap else round((now_ms-bar_end)/1000,3),
                "journalFirstRecordedAtUtc":time_iso(now_ms),
                "journalFirstRecordedAtMadrid":time_iso(now_ms,True),
                "notificationEligible":not bootstrap,
                "initialSnapshotBaseline":bootstrap,
                "sourceGeneratedAt":dict(report.get("sourceProvenance") or {}),
                "eventTimeDefinition":"CLOSED_15M_PRICE_BAR_END; NOT_PROVEN_INTRABAR_ONSET",
                "firstDetectedDefinition":"FIRST_CONFIRMED_GITHUB_ENGINE_EVALUATION; NOT_BAR_CLOSE_OR_PUSH_TIME",
                "publicationTimeKnown":False,
                "signalSourceFamilies":list(candidate.get("families") or []),
                "oiRole":candidate.get("oiRole"),
                "researchOnly":True,
                "notTradeApproval":True,
                "notExecutablePrice":True,
                "noProvenEdge":True
            }
            events.append(record)
            seen[key]=record
            if not bootstrap:added+=1
            old=record
        candidate["eventId"]=key
        candidate["signalCandleClosedAtUtc"]=old["signalCandleClosedAtUtc"]
        candidate["signalCandleClosedAtMadrid"]=old["signalCandleClosedAtMadrid"]
        candidate["firstDetectedAtUtc"]=old["firstDetectedAtUtc"]
        candidate["firstDetectedAtMadrid"]=old["firstDetectedAtMadrid"]
        candidate["detectionLagSeconds"]=old["detectionLagSeconds"]
        candidate["initialSnapshotBaseline"]=old["initialSnapshotBaseline"]
        candidate["notificationEligible"]=old["notificationEligible"]
        instrument=report.get("instruments",{}).get(candidate["symbol"])
        if isinstance(instrument,dict):
            model=instrument.get(candidate["direction"])
            if isinstance(model,dict):
                model["signalTiming"]={
                    "signalCandleClosedAtUtc":old["signalCandleClosedAtUtc"],
                    "firstDetectedAtUtc":old["firstDetectedAtUtc"],
                    "detectionLagSeconds":old["detectionLagSeconds"],
                    "eventId":key}
    # Retain 30 days of observations, enough to recover hourly checks and avoid
    # replay notifications on successive 15m snapshots.
    min_ms=now_ms-RETAIN_DAYS*86400*1000
    kept=[]
    for x in events:
        t=utc_timestamp(x.get("journalFirstRecordedAtUtc"))
        if t is not None and t>=min_ms:
            kept.append(x)
    events=kept[-MAX_EVENTS:]
    journal={
        "schemaVersion":VERSION,
        "generatedAtUtc":time_iso(now_ms),
        "timezone":"UTC; Europe/Madrid explicit per event",
        "status":"BOOTSTRAPPED_NO_ALERTS" if bootstrap else "ACTIVE",
        "researchOnly":True,"notTradeApproval":True,"notSystemPrice":True,
        "notificationTransport":"POLL_EXTERNAL; THIS_JSON_ITSELF_DOES_NOT_SEND_ALERTS",
        "eventMeaning":"CLOSED_15M_BAR_END; not intrabar onset; no post-hoc backdating",
        "firstDetectedMeaning":"WHEN_DETECTOR_FIRST_EVALUATED_AND_LOGGED; publication may lag",
        "retentionDays":RETAIN_DAYS,
        "newEventCount":added,
        "totalRetainedEvents":len(events),
        "events":events
    }
    report["signalJournal"]={
        "schemaVersion":VERSION,
        "status":journal["status"],
        "eventCount":len(events),
        "newEventCount":added,
        "eventLogFile":"detector-signal-events.json",
        "firstDetectedTimeDefinition":"FIRST_ENGINE_EVALUATION_UTC_NOT_SIGNAL_CANDLE_CLOSE",
        "marketConditionTimeDefinition":"LAST_CLOSED_15M_CANDLE_END_UTC",
        "researchOnly":True,"notTradeApproval":True,
        "noAutomaticExchangeOrders":True
    }
    return report,journal
