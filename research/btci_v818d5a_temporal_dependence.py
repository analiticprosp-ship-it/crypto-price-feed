#!/usr/bin/env python3
"""BTCI v8.18d5a: temporal source-witness overlap and horizon label maturity, no price outcomes."""
import hashlib,json,os,sys
from datetime import date,datetime,timedelta,timezone
from collections import defaultdict
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"research/btci_v818d5a_temporal_dependence_prereg_2026-10-19.json"

def sha(b):return hashlib.sha256(b).hexdigest()

def dateutc(s):
    x=datetime.fromisoformat(s.replace("Z","+00:00"))
    if x.utcoffset()!=timedelta(0):raise ValueError("UTC_ONLY")
    return x

def separated(days,h):
    out=[]
    for v in sorted(days):
        if not out or date.fromisoformat(v)>=date.fromisoformat(out[-1])+timedelta(weeks=h):
            out.append(v)
    return out

def report_for(days,last,h):
    m=[d for d in sorted(days) if date.fromisoformat(d)+timedelta(weeks=h)<=date.fromisoformat(last)]
    all_sep=separated(days,h)
    mature_sep=separated(m,h)
    return {"horizonWeeks":h,"allWitnessWeeks":len(days),"labelWindowMatureByLastPanelDate":len(m),
        "matureWitnessDates":m,
        "nonoverlapTimeSeparatedAll":len(all_sep),"nonoverlapTimeSeparatedAllDates":all_sep,
        "nonoverlapTimeSeparatedMature":len(mature_sep),"nonoverlapTimeSeparatedMatureDates":mature_sep,
        "meaning":"Dates separated by at least H weeks, no outcomes used; does not establish independent market events or predictive benefit"}

def selftest():
    assert separated(["2020-01-05","2020-01-12","2020-04-05","2020-07-05"],13)==["2020-01-05","2020-04-05","2020-07-05"]
    assert report_for(["2020-01-05","2020-04-05"],"2020-05-10",13)["labelWindowMatureByLastPanelDate"]==1
    assert report_for(["2020-01-05","2020-04-05"],"2020-05-10",26)["labelWindowMatureByLastPanelDate"]==0
    print("V818D5A_SELFTEST_PASS",flush=True)

def main():
    preg=SPEC.read_bytes()
    reg=json.loads(preg)
    if reg["version"]!="8.18d5a" or reg["scope"]!="RESEARCH_ONLY" or reg["tradeAuthorized"]:
        raise ValueError("PREREG_GUARD_FAILED")
    s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
        region_name="auto",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
    bucket=os.environ["R2_BUCKET"]
    def pinned(k):
        spec=reg["canonical"][k]
        raw=s3.get_object(Bucket=bucket,Key=spec["key"])["Body"].read()
        if sha(raw)!=spec["sha256"]:raise RuntimeError("SHA256_PINNED_PARENT_CHANGED_"+k)
        data=json.loads(raw)
        if not data.get("researchOnly") or data.get("tradeAuthorized"):
            raise ValueError("NOT_RESEARCH_PARENT_"+k)
        return data
    accepted=pinned("mvrv")
    base=pinned("btc")
    if accepted["version"]!="8.18d5" or accepted["independentlyDatedMvrvWeeks"]!=26:
        raise ValueError("ACCEPTED_CANONICAL_D5_CHANGED")
    weeks=base["weeklyPanel"]
    original=[w["date"] for w in weeks]
    ledger=accepted["weeklyProvenance"]
    if (len(original)!=684 or len(set(original))!=684 or original!=sorted(original)
        or [w["date"] for w in ledger]!=original):
        raise ValueError("684_DATE_PANEL_BROKEN")
    confirmed=[]
    witnesses=[]
    for w in ledger:
        if not w["hasIndependentlyDatedNumericMvrv"]:
            continue
        confirmed.append(w["date"])
        for e in w["asofEvidence"]:
            d=date.fromisoformat(w["date"])
            if d.weekday()!=6:
                raise ValueError("NOT_SUNDAY")
            pub=dateutc(e["availableUTC"])
            age=(d-date.fromisoformat(e["observed"])).days
            if not (pub<datetime.combine(d,datetime.min.time(),timezone.utc) and 2<=age<=7 and float(e["mvrv"])>0):
                raise ValueError("UPSTREAM_HISTORICAL_SOURCE_TIME_INVALID_"+w["date"])
            witnesses.append({"date":w["date"],"source":e["type"],"sourceAgeDays":age})
    if len(confirmed)!=26 or sorted(confirmed)!=accepted["verifiedDates"]:
        raise ValueError("ACCEPTED_WITNESSED_DATES_CHANGED")
    cutoff=original[-1]
    horizons={}
    for h in reg["predeclaredHorizonWeeks"]:
        horizons[str(h)]=report_for(confirmed,cutoff,h)
    result={
        "version":"8.18d5a","status":"CANONICAL_26_WEEK_PIT_EVIDENCE_TEMPORAL_SPACING_AUDITED",
        "researchOnly":True,"tradeAuthorized":False,
        "prereg":{"path":str(SPEC.relative_to(ROOT)),"sha256":sha(preg)},
        "acceptedCanonicalParentPins":reg["canonical"],"original684PanelUnchanged":True,
        "originalPanelLastSunday":cutoff,
        "sourceWitnessWeeks":len(confirmed),"unverifiedAsOfWeeks":684-len(confirmed),
        "allWitnessDates":confirmed,
        "horizons":horizons,
        "pitPublicationsVerifiedByIndependentArchive":26,
        "originalCoinMetricsMetricAPIReleaseClockVerified":0,
        "interpretation":[
            "Source availability of MVRV in a public GitHub/Wayback archival witness does not establish Coin Metrics original daily API initial release time.",
            "Greedy non-overlap time spacing is not statistical independence and does not estimate forecast performance.",
            "Maturity by last-panel date is a necessary calendar-window test, not proof that each BTC response target has independently available outcome observations.",
            "26 sparse public source observations cannot be used as a representative 684-week backtest.",
            "This adds no MVRV observations, no BTC outcome/return calculation, no threshold fitting and no live trading changes."
        ],
        "portfolioWriteback":reg["portfolioWriteback"]
    }
    out=Path("btci_v818d5a_reports")
    out.mkdir(exist_ok=True)
    body=(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
    (out/"temporal_spacing_of_26_MVRV_week_sources_FULL.json").write_bytes(body)
    prefix="research/btci/v8.18d5a/runs/{}-{}/".format(os.environ["GITHUB_RUN_ID"],os.getenv("GITHUB_RUN_ATTEMPT","1"))
    def put(name,data):
        key=prefix+name
        digest=sha(data)
        s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType="application/json",
                      Metadata={"sha256":digest,"research-only":"true"})
        if sha(s3.get_object(Bucket=bucket,Key=key)["Body"].read())!=digest:
            raise RuntimeError("R2_REPORT_SHA256_READBACK_MISMATCH")
        return {"key":key,"sha256":digest,"bytes":len(data)}
    saved=put("temporal_spacing_of_26_MVRV_week_sources_FULL.json",body)
    manifest=put("manifest.json",(json.dumps({"version":"8.18d5a","report":saved,
        "preregSHA256":sha(preg),"researchOnly":True,"canonicalV818d5Unchanged":True},ensure_ascii=False,indent=2)+"\n").encode())
    summary={"status":result["status"],"originalBTCIWeeks":684,"publicWitnessWeeks":26,
        "lastParentSunday":cutoff,
        "horizons":{h:{k:v for k,v in o.items() if "Dates" not in k} for h,o in horizons.items()},
        "reportSHA256":saved["sha256"],"manifestSHA256":manifest["sha256"],"prefix":prefix}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("V818D5A_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    if "--self-test" in sys.argv:selftest()
    else:main()
