"""Append-only research-event ledger for independently detected SHADOW signals.

Three distinct times:
  barClosedAtUtc: 15m historical bar END (earliest valid confirmed bar signal).
  latestSourceGeneratedAtUtc: later of price/taker feed generation.
  firstDetectedAtUtc: GitHub engine time first observed as a candidate.
Never claim any precise intra-bar reversal time from 15m aggregates.
"""
import hashlib
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

VERSION="detector-signal-events-1.0"
MADRID=ZoneInfo("Europe/Madrid")
MAX_EVENTS=20000

def as_ms(value):
    try:
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
        return int(dt.timestamp()*1000) if dt.tzinfo else None
    except (TypeError, ValueError, OverflowError, AttributeError):
        return None

def iso(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat(timespec="milliseconds")

def madrid(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).astimezone(MADRID).isoformat(timespec="milliseconds")

def empty_ledger():
    return {"schemaVersion":VERSION,"initialized":False,"events":[]}

def add_signal_events(report,previous):
    """Immutable event identity; preserves first seen times across repeat runs.

    On first installation, seed active candidates as suppressed baseline, so
    the user never receives a misleading 'new' signal for an old 15m candle.
    """
    if not isinstance(previous,dict) or previous.get("schemaVersion")!=VERSION:
        raise ValueError("LEDGER_MISSING_OR_INVALID: do not overwrite historic identities")
    old=previous.get("events")
    if not isinstance(old,list) or previous.get("initialized") not in (True,False):
        raise ValueError("LEDGER_INVALID_STRUCTURE")
    entries=list(old)
    unique={}
    for event in entries:
        if not isinstance(event,dict) or not isinstance(event.get("id"),str) or event["id"] in unique:
            raise ValueError("LEDGER_DUPLICATE_OR_INVALID_ID")
        unique[event["id"]]=event
    now_ms=as_ms(report.get("generatedAt"))
    gate=report.get("dataGate") or {}
    if now_ms is None or not isinstance(gate,dict):
        raise ValueError("REPORT_GENERATION_TIME_INVALID")
    latest_pub=report.get("sourceProvenance") or {}
    pubs=[as_ms(latest_pub.get(k)) for k in
          ("marketSummaryGeneratedAt","takerRestGeneratedAt")]
    if (not all(isinstance(t,int) for t in pubs) or
        any(t>now_ms+5000 for t in pubs)):
        raise ValueError("PUBLISH_TIME_MISSING_OR_FUTURE")
    source_ms=max(pubs)
    candidates=report.get("candidates",[])
    if not isinstance(candidates,list):
        raise ValueError("REPORT_CANDIDATES_INVALID")
    if len(entries)>MAX_EVENTS:
        raise ValueError("LEDGER_CAPACITY_EXCEEDED: archive before next append")
    new=[]
    baseline=not previous["initialized"]
    if gate.get("ok") is True and report.get("researchOnly") is True and report.get("notTradeApproval") is True:
        for item in candidates:
            if not isinstance(item,dict) or item.get("status")!="EARLY_CANDIDATE_SHADOW":
                continue
            symbol=item.get("symbol");direction=item.get("direction");end=item.get("eventEndMs")
            if not isinstance(symbol,str) or not symbol.isalnum() or not 2<=len(symbol)<=15:
                continue
            if direction not in ("LONG","SHORT"):
                continue
            if not isinstance(end,int) or isinstance(end,bool) or end%900000!=0:
                continue
            if end>source_ms or source_ms>now_ms+5000 or end>now_ms:
                continue
            identity=f"shadow-v1|{symbol}|{direction}|{end}"
            ident=hashlib.sha256(identity.encode("ascii")).hexdigest()[:24]
            if ident in unique:
                continue
            state=("PREEXISTING_AT_FIRST_LEDGER_RUN" if baseline
                   else "NEW_SHADOW_CANDIDATE")
            lag_ms=now_ms-end
            event={
                "id":ident,
                "symbol":symbol,"direction":direction,
                "status":"EARLY_CANDIDATE_SHADOW",
                "eventTimeResolution":"CLOSED_15M_NOT_INTRABAR_TICK",
                "barStartAtUtc":iso(end-900000),
                "barClosedAtUtc":iso(end),
                "barClosedAtMadrid":madrid(end),
                "latestSourceGeneratedAtUtc":iso(source_ms),
                "firstDetectedAtUtc":iso(now_ms),
                "firstDetectedAtMadrid":madrid(now_ms),
                "lagBarCloseToDetectionSeconds":round(lag_ms/1000,3),
                "lagSourceGenerationToDetectionSeconds":round((now_ms-source_ms)/1000,3),
                "publicationLagAfterDetection":"GITHUB_COMMIT_AND_ALERT_DELIVERY_NOT_OBSERVED",
                "notificationStatus":state,
                "mayBeStaleAtDelivery":True,
                "alertEligible":not baseline,
                "researchOnly":True,"notTradeApproval":True,
                "noExecutionLevels":True
            }
            entries.append(event)
            unique[ident]=event
            if not baseline:
                new.append(event)
    if len(entries)>MAX_EVENTS:
        raise ValueError("LEDGER_CAPACITY_EXCEEDED: archive before next append")
    result={"schemaVersion":VERSION,"initialized":True,
            "eventCount":len(entries),"events":entries,
            "disclaimer":"First detected is GitHub engine evaluation time, not time of intra-bar price change or alert receipt. BarClosedAt is earliest close-based confirmation.",
            "researchOnly":True,"notTradeApproval":True}
    return result,new
