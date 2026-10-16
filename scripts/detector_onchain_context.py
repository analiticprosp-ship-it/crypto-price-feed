#!/usr/bin/env python3
"""Detector on-chain BTC age/flows research SIDE-CAR. No API, trading or live signals.

Do NOT conflate old UTXO movement with deposits to exchanges or actual sales.
Only externally sourced machine-readable rows with explicit provenance and
available_at may be reviewed; screenshots/unknown metrics -> NO_DATA.
"""
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"research"/"detector-onchain-observations.json"
OUTPUT=ROOT/"detector-onchain-context.json"
METRICS={
    "BTC_SPENT_OUTPUT_AGE_1Y_3Y": ("ALL_CHAIN_MOVEMENT","SPENT_OUTPUT_AGE_BANDS"),
    "BTC_SPENT_OUTPUT_AGE_3Y_PLUS": ("ALL_CHAIN_MOVEMENT","SPENT_OUTPUT_AGE_BANDS"),
    "BTC_EXCHANGE_INFLOW_AGE_1Y_3Y": ("EXCHANGE_DEPOSITS_ONLY","EXCHANGE_INFLOW_AGE_BANDS"),
    "BTC_EXCHANGE_INFLOW_AGE_3Y_PLUS": ("EXCHANGE_DEPOSITS_ONLY","EXCHANGE_INFLOW_AGE_BANDS"),
    "BTC_EXCHANGE_INFLOW": ("EXCHANGE_DEPOSITS_ONLY","EXCHANGE_INFLOW"),
    "BTC_EXCHANGE_OUTFLOW": ("EXCHANGE_WITHDRAWALS_ONLY","EXCHANGE_OUTFLOW"),
    "BTC_EXCHANGE_NETFLOW": ("EXCHANGE_NET_MOVEMENT","EXCHANGE_NETFLOW")
}
MAX_SOURCE_LATENCY_MS=72*3600*1000
ISO=lambda ms:datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()

def parse_time(s):
    if not isinstance(s,str):return None
    try:
        v=datetime.fromisoformat(s.replace("Z","+00:00"))
        return int(v.timestamp()*1000) if v.tzinfo else None
    except (ValueError,OverflowError):return None

def vetted_link(url):
    if not isinstance(url,str) or len(url)>512:return False
    u=urlparse(url)
    if u.scheme!="https" or not u.hostname or u.username or u.password:return False
    return u.hostname in ("cryptoquant.com","www.cryptoquant.com","api.cryptoquant.com",
                          "glassnode.com","studio.glassnode.com","api.glassnode.com",
                          "docs.cryptoquant.com")

def validate(row,now_ms):
    if not isinstance(row,dict):return None,"MALFORMED_OBSERVATION"
    metric=row.get("metricId")
    if metric not in METRICS:return None,"UNRECOGNIZED_METRIC"
    scope,kind=METRICS[metric]
    if row.get("asset")!="BTC" or row.get("scope")!=scope or row.get("metricKind")!=kind:
        return None,"METRIC_SCOPE_OR_ASSET_MISMATCH"
    if row.get("sourceType")!="PROVIDER_EXPORT" or row.get("provider") not in ("CryptoQuant","Glassnode"):
        return None,"SCREENSHOT_OR_UNVERIFIED_SOURCE"
    if not vetted_link(row.get("metricUrl")):return None,"INVALID_PROVENANCE_URL"
    hash_value=row.get("rawSourceSha256")
    if not isinstance(hash_value,str) or len(hash_value)!=64 or any(ch not in "0123456789abcdef" for ch in hash_value):
        return None,"SOURCE_SHA256_MISSING"
    start=parse_time(row.get("windowStartUtc"));end=parse_time(row.get("windowEndUtc"))
    available=parse_time(row.get("availableAtUtc"));retrieved=parse_time(row.get("retrievedAtUtc"))
    if any(x is None for x in (start,end,available,retrieved)):
        return None,"TIMESTAMPS_MISSING"
    if not (0<end-start<=31*86400000 and end<=available<=retrieved<=now_ms+3000):
        return None,"LOOKAHEAD_OR_UNORDERED_TIMESTAMPS"
    if now_ms-end>MAX_SOURCE_LATENCY_MS:
        return None,"OLDER_THAN_ONCHAIN_CONTEXT_TTL"
    number=row.get("valueBtc")
    if isinstance(number,bool):return None,"INVALID_BTC_VOLUME"
    try:
        number=float(number)
    except (ValueError,TypeError):
        return None,"INVALID_BTC_VOLUME"
    if not math.isfinite(number) or (kind!="EXCHANGE_NETFLOW" and number<0):
        return None,"INVALID_BTC_VOLUME"
    smoother=row.get("rollingAverageDays")
    if not isinstance(smoother,int) or isinstance(smoother,bool) or not 1<=smoother<=30:
        return None,"SMOOTHING_UNDECLARED"
    if row.get("isExchangeTagged") is not (scope!="ALL_CHAIN_MOVEMENT"):
        return None,"EXCHANGE_TAG_CONTRADICTION"
    if kind=="SPENT_OUTPUT_AGE_BANDS" and row.get("isExchangeTagged") is True:
        return None,"MOVEMENT_MISLABELED_EXCHANGE_INFLOW"
    return {"asset":"BTC","metricId":metric,"scope":scope,"metricKind":kind,
            "sourceType":"PROVIDER_EXPORT","provider":row["provider"],"metricUrl":row["metricUrl"],
            "rawSourceSha256":hash_value,
            "windowStartUtc":row["windowStartUtc"],"windowEndUtc":row["windowEndUtc"],
            "availableAtUtc":row["availableAtUtc"],"retrievedAtUtc":row["retrievedAtUtc"],
            "valueBtc":number,"rollingAverageDays":smoother,
            "unit":"BTC", "exchangeLabeled":scope!="ALL_CHAIN_MOVEMENT",
            "sourceRevisionRisk":"EXCHANGE_ENTITY_LABELS_AND_AGE_BANDS_MAY_BE_REVISED",
            "sourceReviewStatus":"PROVIDER_REPORTED_NOT_INDEPENDENTLY_REPRODUCED",
            "interpretation":"RESEARCH_CONTEXT_NOT_EVIDENCE_OF_EXECUTED_SALE"},None

def build(source,*,now_ms,source_sha=None):
    result={"schemaVersion":"detector-onchain-context-1.0",
            "generatedAt":ISO(now_ms),
            "producerStatus":"RESEARCH_ONLY","researchOnly":True,
            "notTradeApproval":True,"notSystemPrice":True,
            "notPortfolioInput":True,"doNotRankCandidates":True,
            "signalStrength":None,"longShortDirection":None,
            "evidenceFamily":"ONCHAIN_SUPPLY_MOVEMENT_ONE_FAMILY",
            "ageVsHolderNote":"UTXO age since previous movement != independently identified investor's holding time",
            "sourceSha256":source_sha,"observations":[],"rejections":[],
            "sourceStatus":"NO_DATA",
            "scopeSeparation":"GENERAL_SPENT_OUTPUT_MOVEMENT_IS_NOT_EXCHANGE_INFLOW",
            "limitations":[
                "Onchain movements and exchange deposits are not completed market sales",
                "Exchange labeling/clustering may be revised; no point-in-time claim without vintages",
                "7-day average is smoothed history, not an instantaneous flow",
                "No API credentials or paid on-chain feed currently connected",
                "No score, probability, execution permission, or candidate direction from onchain context"
            ]}
    if not isinstance(source,dict) or source.get("schemaVersion")!="detector-onchain-observations-1.0":
        result["sourceStatus"]="SOURCE_MISSING_OR_SCHEMA_MISMATCH"
        return result
    entries=source.get("observations")
    if not isinstance(entries,list):
        result["sourceStatus"]="MALFORMED_OBSERVATIONS"
        return result
    for idx,row in enumerate(entries[:100]):
        data,error=validate(row,now_ms)
        if error:result["rejections"].append({"index":idx,"reason":error})
        else:result["observations"].append(data)
    if result["observations"]:
        result["sourceStatus"]="PROVIDER_REPORTED_CONTEXT_ONLY"
        result["separatedScopes"]=sorted(set(x["scope"] for x in result["observations"]))
    elif result["rejections"]:
        result["sourceStatus"]="NO_VALID_OBSERVATIONS"
    return result

def main():
    try:
        raw=SOURCE.read_bytes()
        source=json.loads(raw)
        digest=hashlib.sha256(raw).hexdigest()
    except (OSError,ValueError):
        source=None;digest=None
    result=build(source,now_ms=int(time.time()*1000),source_sha=digest)
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n")
    print("Detector BTC onchain context:",result["sourceStatus"],
          "valid:",len(result["observations"]),"rejected:",len(result["rejections"]))

if __name__=="__main__":
    main()
