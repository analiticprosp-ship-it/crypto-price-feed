#!/usr/bin/env python3
"""BTCI v8.18d2. Check conditional BTC maximum peak-to-trough *after* rally,
and original-date 26w downside, from SHA-original 2010+ PriceUSD source.
MVRV signals are reconstructed in 2026, NOT historic PIT-tradable.
"""
import datetime as dt,hashlib,json,math,os,statistics,collections
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v818d2_mvrv_path_risk_prereg_2026-10-19.json"
PM=("research/btci/v8.18d/runs/39224537060-1/mvrv_exploratory.json","95249457f5574d62d9f55f41e80dfd582ad8d9885e13b14df9b2d8199092c7ff")
PB=("research/btci/v8.17.1/runs/39212878778-1/full_historical_rise_fall.json","539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091")
PA=("research/btci/v8.7/runs/39131902527-1/archive_manifest.json","3705a179363c9fdf50fede363fb7062481ce15c60f62dfada226e5371e674fb4")
MODELS=("BASE_BTC","BASE_STRICT","BTC_LOW2","BTC_HIGH3","STRICT_LOW2","STRICT_HIGH3","BASE_NEG")
def sha(b):return hashlib.sha256(b).hexdigest()
def day(s):return dt.date.fromisoformat(s)
def f6(v):return round(float(v),6) if v is not None else None
def med(v):return f6(statistics.median(v)) if v else None
def r2():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def get_raw(s,b,k,digest):
 raw=s.get_object(Bucket=b,Key=k)["Body"].read()
 if sha(raw)!=digest:raise SystemExit("V818D2_PARENT_SHA_CHANGED")
 return raw
def put(s,b,key,payload):
 raw=payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False,indent=2).encode()
 dig=sha(raw);s.put_object(Bucket=b,Key=key,Body=raw,ContentType="application/json",
   Metadata={"sha256":dig,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=dig:raise SystemExit("V818D2_R2_READBACK_MISMATCH")
 return dig
def path_stats(sunday,prices,horizon):
 start=prices.get(sunday)
 if start is None or start<=0:raise SystemExit("V818D2_BTC_START_MISSING")
 hi=start;worst=0;worstFrom=0
 firstUp50=None;firstDown35=None
 for n in range(1,horizon+1):
  date=sunday+dt.timedelta(days=n)
  v=prices.get(date)
  if v is None:raise SystemExit("V818D2_MISSING_DAILY_PRICE")
  hi=max(hi,v)
  worst=min(worst,100*(v/hi-1))
  worstFrom=min(worstFrom,100*(v/start-1))
  if firstUp50 is None and v>=1.5*start:firstUp50=n
  if firstDown35 is None and v<=0.65*start:firstDown35=n
 return {"worstPeakToTroughPct":f6(worst),"worstFromStartPct":f6(worstFrom),
   "firstUp50Day":firstUp50,"firstDown35Day":firstDown35}
def score(rows):
 result={"n":len(rows),"groups":{}}
 for name in MODELS:
  selected=[z for z in rows if z["flags"][name]]
  count=len(selected)
  def good(t):return sum(z["path"][t] for z in selected)
  result["groups"][name]={"n":count,
   "p2t20Within13":good("peakToTrough20In13"),
   "p2t35Within26":good("peakToTrough35In26"),
   "p2t50Within52":good("peakToTrough50In52"),
   "fromStartDown35In26":good("down35In26"),
   "up50DailyIn26":good("up50DailyIn26"),
   "up50WeeklyIn26":good("up50WeeklyIn26"),
   "medianFirstUp50Day":med([z["path"]["firstUp50Day"] for z in selected
     if z["path"]["firstUp50Day"] is not None]),
   "medianFirstDown35Day":med([z["path"]["firstDown35Day"] for z in selected
     if z["path"]["firstDown35Day"] is not None]),
   "p2t35Rate":f6(good("peakToTrough35In26")/count) if count else None}
 return result
def spaced(rows,m,lockweeks):
 res=[];last=None
 for z in rows:
  d=day(z["date"])
  if z["flags"][m] and (last is None or (d-last).days>=7*(lockweeks+1)):
   res.append(z);last=d
 return res
def main():
 rawpre=(ROOT/PRE).read_bytes();p=json.loads(rawpre)
 expected={"onchain":{"key":PM[0],"sha256":PM[1]},
   "btcLong":{"key":PB[0],"sha256":PB[1]},
   "archive":{"key":PA[0],"sha256":PA[1]}}
 if p["version"]!="8.18d2" or p["parents"]!=expected:
  raise SystemExit("V818D2_PREREG_CHANGED")
 s=r2();bucket=os.environ["R2_BUCKET"]
 mm=json.loads(get_raw(s,bucket,*PM))
 original=json.loads(get_raw(s,bucket,*PB))
 archive=json.loads(get_raw(s,bucket,*PA))
 if len(mm["weeklyPanel"])!=684 or len(original["weeklyPanel"])!=684:
  raise SystemExit("V818D2_ORIGINAL_684_MISMATCH")
 btc_meta=archive["assets"]["btc"]["normalized"]
 raw=get_raw(s,bucket,btc_meta["r2Key"],btc_meta["sha256"])
 prices={day(z["day"]):float(z["priceUSD"]) for z in json.loads(raw)}
 if len(prices)<5900:raise SystemExit("V818D2_DAILY_SOURCE_TOO_SHORT")
 baseline={z["date"]:z for z in original["weeklyPanel"]}
 sample=[]
 for row in mm["weeklyPanel"]:
  d=day(row["date"])
  x=baseline[row["date"]]
  if abs(prices[d]-x["btcPriceReferenceUSD"])>0.000003:
   raise SystemExit("V818D2_WEEKLY_DAILY_PRICE_CONFLICT:"+row["date"])
  windows={w:path_stats(d,prices,7*w) for w in (13,26,52)}
  q={
    "peakToTrough20In13":windows[13]["worstPeakToTroughPct"]<=-20,
    "peakToTrough35In26":windows[26]["worstPeakToTroughPct"]<=-35,
    "peakToTrough50In52":windows[52]["worstPeakToTroughPct"]<=-50,
    "down35In26":windows[26]["worstFromStartPct"]<=-35,
    "up50DailyIn26":windows[26]["firstUp50Day"] is not None,
    "up50WeeklyIn26":x["outcomes"]["UP26"],
    "firstUp50Day":windows[26]["firstUp50Day"],
    "firstDown35Day":windows[26]["firstDown35Day"],
    "firstWhich":"UP50" if windows[26]["firstUp50Day"] is not None and (
       windows[26]["firstDown35Day"] is None or windows[26]["firstUp50Day"]<windows[26]["firstDown35Day"])
     else "DOWN35" if windows[26]["firstDown35Day"] is not None else "NONE"
  }
  if q["down35In26"]!=x["outcomes"]["DOWN26"]:
   raise SystemExit("V818D2_DOWN26_FROZEN_TARGET_DISAGREES:"+row["date"])
  sample.append({"date":row["date"],"era":row["era"],
    "MVRV":row["MVRV_Tminus1d"],"flags":{m:row["flags"][m] for m in MODELS},
    "path":q,"dailyDrawdowns":windows})
 allmetrics=score(sample)
 years={e:score([z for z in sample if z["era"]==e]) for e in
        ("2012","2013-2016","2017-2019","2020-2023","2024-2025")}
 locks={str(n):score([*({z["date"]:z for m in MODELS for z in spaced(sample,m,n)}.values())])
         for n in ()} # Per-model below; avoids mismatched cross-model date lists
 selectedLock={str(n):{m:{
    "n":len(t:=spaced(sample,m,n)),
    "p2t35Within26":sum(z["path"]["peakToTrough35In26"] for z in t),
    "fromStartDown35In26":sum(z["path"]["down35In26"] for z in t),
    "up50DailyIn26":sum(z["path"]["up50DailyIn26"] for z in t),
    "medianFirstUp50Day":med([z["path"]["firstUp50Day"] for z in t
      if z["path"]["firstUp50Day"] is not None]),
    "alertDates":[z["date"] for z in t]}
      for m in MODELS} for n in (13,26)}
 result={"version":"8.18d2","researchOnly":True,
  "status":"BACKFILLED_MVRV_PATH_DRAWDOWN_SENSITIVITY_NOT_PIT",
  "parents":expected,"preregSha256":sha(rawpre),"BTCPriceSource":btc_meta,
  "same684WeeksNoReweighting":True,"historicalOriginalDown26FullyVerified":True,
  "primary":allmetrics,"eras":years,"lockouts":selectedLock,
  "dates":sample,
  "caveats":[
   "MVRV values retrospectively rebuilt and historical original publication vintage not verified; not live predictor.",
   "Peak-to-trough after a BTC price rally is distinct from falling 35% below first signal. BOTH can occur.",
   "Time-to-event is conditional on the target happening and does not imply deterministic lead time.",
   "Historical BTC PriceUSD is a reference daily fixing, not executable trade or futures liquidation price.",
   "These are overlapping market windows; lockouts lower dependence only partially. Same history not OOS.",
   "No Spot Futures NAV PnL capital reserve MASTER Detector risk limits modified."]}
 rootout=Path("btci_v818d2_reports");rootout.mkdir(exist_ok=True)
 blob=json.dumps(result,ensure_ascii=False,indent=2).encode()
 (rootout/"path_risk.json").write_bytes(blob)
 prefix=f"research/btci/v8.18d2/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 dig=put(s,bucket,prefix+"path_risk.json",blob)
 m=put(s,bucket,prefix+"manifest.json",{"version":"8.18d2","researchOnly":True,
  "reportSha256":dig,"originalDailySourceSha256":btc_meta["sha256"],
  "preregSha256":sha(rawpre),"status":result["status"]})
 summary={"status":"V818D2_HISTORICAL_BTC_PATH_RISK_VERIFIED_R2_READBACK_NOT_PIT",
  "prefix":prefix,"reportSha256":dig,"manifestSha256":m,
  "primary":allmetrics,"byEra":{er:{"n":q["n"],"groups":{k:v
        for k,v in q["groups"].items() if k in ("BASE_BTC","BTC_LOW2","BTC_HIGH3","BASE_STRICT","STRICT_LOW2")}}
     for er,q in years.items()},"lock14":selectedLock["13"]}
 (rootout/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print("V818D2_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
