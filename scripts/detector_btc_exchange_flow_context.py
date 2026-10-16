"""Read-only BTC Coin Metrics DAILY exchange-flow context for Detector SHADOW.

Coin Metrics community keyless data are NOT CryptoQuant age cohorts.
Exchange tagging is approximate; zero trade/sale inference is forbidden.
"""
import datetime
import math

EXPECTED={"FlowInExNtv","FlowOutExNtv","SplyExNtv"}

def parse_iso(s):
    try:
        d=datetime.datetime.fromisoformat(s.replace("Z","+00:00"))
        return d if d.tzinfo is not None else None
    except (TypeError,ValueError,AttributeError):
        return None

def num(v):
    if isinstance(v,bool) or v is None:return None
    try:
        x=float(v)
        return x if math.isfinite(x) and x>=0 else None
    except (ValueError,TypeError):return None

def read_context(source, *, now_ms, source_sha=None):
    result={"status":"NO_DATA",
            "provider":"Coin Metrics Community",
            "evidenceFamily":"BTC_EXCHANGE_LABELED_FLOWS_ONE_FAMILY",
            "sourceSha256":source_sha,
            "asOfUtcDay":None,"lastDay":None,
            "last7dNetflowBtc":None,"last30dNetflowBtc":None,
            "validDays":0,
            "notExecutedSales":True,"notAge1to3Years":True,
            "notIntradayFlow":True,"notPointInTimeBacktestReady":True,
            "noEffectOnCandidateRanking":True,
            "noIndependentSignalVotes":True,
            "tradePermission":False}
    if not isinstance(source,dict) or source.get("schemaVersion")!="btc-coinmetrics-exchange-flow-1.0":
        result["reason"]="SOURCE_NOT_INSTALLED_OR_SCHEMA_MISMATCH"
        return result
    if (source.get("provider")!="Coin Metrics Community" or
        source.get("asset")!="BTC" or source.get("frequency")!="1d" or
        source.get("researchOnly") is not True or source.get("notTradeApproval") is not True or
        source.get("notCohortAgeMetric") is not True):
        result["reason"]="PROVENANCE_OR_NONTRADING_GUARDS_MISSING"
        return result
    sources=source.get("metricSources")
    if not isinstance(sources,dict) or not EXPECTED.issubset(sources):
        result["reason"]="SOURCE_METRICS_MISSING"
        return result
    source_time=parse_iso(source.get("generatedAt"))
    now=datetime.datetime.fromtimestamp(now_ms/1000,datetime.timezone.utc)
    if source_time is None or source_time>now+datetime.timedelta(seconds=5):
        result["reason"]="INVALID_SOURCE_PUBLICATION_TIME"
        return result
    rows=source.get("data")
    if not isinstance(rows,list):
        result["reason"]="INVALID_ROWS"
        return result
    by_date={}
    for record in rows:
        if not isinstance(record,dict):continue
        day=record.get("dateUtc")
        try:d=datetime.date.fromisoformat(day)
        except (ValueError,TypeError):continue
        if d>=now.date() or d in by_date:
            result["reason"]="FUTURE_OR_DUPLICATE_DAILY_ROW"
            return result
        a=num(record.get("exchangeInflowBtc"));b=num(record.get("exchangeOutflowBtc"))
        balance=num(record.get("exchangeReserveBtc"))
        if a is None or b is None or balance is None:continue
        published_net=record.get("netflowBtc")
        if isinstance(published_net,bool) or published_net is None:
            result["reason"]="DERIVED_NETFLOW_MISSING"
            return result
        try:val=float(published_net)
        except (TypeError,ValueError):continue
        if not math.isfinite(val) or abs((a-b)-val)>0.00001:
            result["reason"]="NETFLOW_RECONCILIATION_FAILED"
            return result
        by_date[d]={"exchangeInflowBtc":a,"exchangeOutflowBtc":b,
                    "netflowBtc":val,"exchangeReserveBtc":balance}
    if not by_date:
        result["reason"]="NO_VALID_DAILY_FLOW_ROWS"
        return result
    last=max(by_date)
    result["validDays"]=len(by_date)
    result["asOfUtcDay"]=last.isoformat()
    result["lastDay"]=by_date[last]
    result["sourceRetrievedAt"]=source.get("generatedAt")
    result["sourceAgeHours"]=round((now-source_time).total_seconds()/3600,2)
    for n,k in ((7,"last7dNetflowBtc"),(30,"last30dNetflowBtc")):
        dates=[last-datetime.timedelta(days=i) for i in range(n)]
        if all(d in by_date for d in dates):
            result[k]=round(sum(by_date[d]["netflowBtc"] for d in dates),8)
    if (now.date()-last).days<=2 and 0<=(now-source_time).total_seconds()<=48*3600:
        result["status"]="OBSERVED_DAILY_CONTEXT_ONLY"
    else:
        result["status"]="STALE_HISTORICAL_CONTEXT_ONLY"
    return result
