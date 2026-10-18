#!/usr/bin/env python3
"""Detector v8.1 day-31 equivalent phase-recovery case study (research only).
No live price, trading, NAV, Futures, risk-limit, Master or other operational updates.
"""
import datetime as dt,hashlib,json,os,statistics
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
PREREG="research/detector_v81_recovery_checkpoint_prereg_2026-10-18.json"
V80_KEY="research/detector/v8.0/runs/39124773092-1/combined/phase_transitions.json"
V80_SHA="b4fb7e7bb0640e052c9c95dc405da8f406d3b051b476f56226abb7a813e86f10"
CONFIRM="RECOVERY_NOT_CONFIRMED"
H=(30,90,180)
def sha(b):return hashlib.sha256(b).hexdigest()
def f6(x):return round(float(x),6)
def connect():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def put(s,b,key,raw):
 dig=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType="application/json",
  Metadata={"sha256":dig,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=dig:raise SystemExit("V81_R2_READBACK_MISMATCH")
 return dig
def get(s,b,key,dig):
 raw=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(raw)!=dig:raise SystemExit("V81_SOURCE_SHA_CHANGED")
 return json.loads(raw)
def future(series,day,h):
 ending=day+dt.timedelta(days=h)
 if ending not in series:return {"status":"RIGHT_CENSORED"}
 base=series[day]["price"]
 points=[]
 for i in range(1,h+1):
  key=day+dt.timedelta(days=i)
  if key not in series:raise SystemExit("V81_FUTURE_DAILY_GAP")
  points.append(series[key]["price"])
 return {"status":"OBSERVED","returnPct":f6(100*(points[-1]/base-1)),
  "maxAdverseClosePct":f6(100*(min(points)/base-1)),
  "maxFavorableClosePct":f6(100*(max(points)/base-1))}
def event_within(phase_events,day,h,phase,last):
 deadline=day+dt.timedelta(days=h)
 results=[x for x in phase_events if day<dt.date.fromisoformat(x["date"])<=min(last,deadline) and x["to"]==phase]
 if results:
  return {"status":"EVENT_OBSERVED","firstDate":results[0]["date"],
          "daysAfterCheckpoint":(dt.date.fromisoformat(results[0]["date"])-day).days}
 if deadline>last:return {"status":"RIGHT_CENSORED"}
 return {"status":"NO_EVENT_IN_WINDOW"}
def main():
 pinned=ROOT/PREREG
 prereg_bytes=pinned.read_bytes();p=json.loads(prereg_bytes)
 if p.get("version")!="8.1" or p["immutableV80"]!={"key":V80_KEY,"sha256":V80_SHA}:
  raise SystemExit("V81_PREREG_CHANGED")
 s=connect();bucket=os.environ["R2_BUCKET"]
 old=get(s,bucket,V80_KEY,V80_SHA)
 if old["version"]!="8.0" or old["transitions"]["phaseCount"]!=33:
  raise SystemExit("V81_PARENT_REPORT_CHANGED")
 stream={}
 for row in old["pastOnlyDailyTimelines"]:
  day=dt.date.fromisoformat(row["date"])
  if day in stream:raise SystemExit("V81_DUPLICATE_DAILY")
  stream[day]=row
 days=sorted(stream);latest=max(days)
 if latest!=dt.date(2026,10,17):raise SystemExit("V81_ASOF_CHANGED")
 if any((b-a).days!=1 for a,b in zip(days,days[1:])):raise SystemExit("V81_TIMELINE_GAP")
 cases=[]
 recoveries=[x for x in old["transitions"]["phaseEvents"] if x["to"]==CONFIRM]
 if len(recoveries)!=9:raise SystemExit("V81_RECOVERY_COHORT_CHANGED")
 for entry in recoveries:
  entered=dt.date.fromisoformat(entry["date"])
  point=entered+dt.timedelta(days=31)
  if point not in stream:raise SystemExit("V81_CHECKPOINT_MISSING")
  row=stream[point]
  entryprice=stream[entered]["price"];price=row["price"]
  outcomes={str(h):future(stream,point,h) for h in H}
  bear=event_within(old["transitions"]["phaseEvents"],point,90,"BTC_BEAR_PRICE_TREND",latest)
  bull=event_within(old["transitions"]["phaseEvents"],point,180,"BTC_BULL_PRICE_TREND",latest)
  cases.append({"recoveryConfirmed":entered.isoformat(),
   "checkpointUTC":point.isoformat(),"checkpointOffsetDays":31,
   "stateAtCheckpoint":row["phaseConfirmed"],"riskAtCheckpoint":row["riskConfirmed"],
   "riskScoreAtCheckpoint":row["riskScore"],
   "btcCheckpointReturnSinceConfirmationPct":f6(100*(price/entryprice-1)),
   "btcCheckpointPriceFuturesNonExecutable":price,
   "btc365dDrawdownPct":row["drawdown365ClosePct"],
   "btcTrailing90dReturnPct":row["return90Pct"],
   "btcAboveSMA200":price>row["sma200"],
   "phaseEntryRisk":entry["riskAtTransition"],
   "future":outcomes,"bearConfirmationInNext90d":bear,
   "bullConfirmationInNext180d":bull})
 current=cases[-1]
 if current["checkpointUTC"]!=latest.isoformat():
  raise SystemExit("V81_CURRENT_NOT_DAY31")
 hist=cases[:-1]
 def tally(subset):
  return {"cases":len(subset),
   "riskOnAtCheckpoint":sum(x["riskAtCheckpoint"]=="RISK_ON_PRICE_PROXY" for x in subset),
   "confirmedRecoveryAtCheckpoint":sum(x["stateAtCheckpoint"]==CONFIRM for x in subset),
   "observed90d":sum(x["future"]["90"]["status"]=="OBSERVED" for x in subset),
   "positive90d":sum(x["future"]["90"].get("returnPct",0)>0 for x in subset),
   "observedBearWithin90":sum(x["bearConfirmationInNext90d"]["status"]=="EVENT_OBSERVED" for x in subset),
   "observedBullWithin180":sum(x["bullConfirmationInNext180d"]["status"]=="EVENT_OBSERVED" for x in subset),
   "censoredBull180":sum(x["bullConfirmationInNext180d"]["status"]=="RIGHT_CENSORED" for x in subset)}
 bystate={s:tally([c for c in hist if c["stateAtCheckpoint"]==s])
  for s in ("RECOVERY_NOT_CONFIRMED","BTC_BEAR_PRICE_TREND","CONSOLIDATION_OR_TRANSITION","BTC_BULL_PRICE_TREND")}
 byera={"2020-2023":tally([c for c in hist if c["recoveryConfirmed"]<"2024-01-01"]),
        "2024-2026":tally([c for c in hist if c["recoveryConfirmed"]>="2024-01-01"])}
 report={"version":"8.1","status":"COMPARABLE_DAY31_RESEARCH_ONLY",
  "researchOnly":True,"tradesEmitted":0,
  "source":{"key":V80_KEY,"sha256":V80_SHA},
  "preregistration":{"path":PREREG,"sha256":sha(prereg_bytes)},
  "asOfUTC":latest.isoformat(),"checkpointDay":31,
  "totalRecoveries":len(cases),"historicalCompletedCheckpoints":len(hist),
  "historicalCohortSummary":tally(hist),"byCheckpointConfirmedPhase":bystate,
  "byEra":byera,"cases":cases,"current":current,
  "cautions":["The 31-day checkpoint was selected to match today's elapsed phase, not optimized for performance",
   "Recovery episodes may overlap, cannot treat sample as independent Bernoulli trials",
   "Only 8 earlier recovery cases have a 90-day historical checkpoint outcome; too few for probabilities",
   "Recent current case is right-censored for forward horizons; no imaginary future outcome",
   "Price path is Binance USDM perpetual BTC closed daily marks, not executable spot",
   "Source v8.0 rules were designed after seeing history; not a virgin out-of-sample sample",
   "No added historical ETF or macro liquidity data in this model: requires true point-in-time source/release",
   "No claim that this model has validated an early bull vs bear rally trading edge",
   "No live Detector or accounting writes; no changes to Futures, Spot, NAV, P&L, reserve, capital or trading limits"]}
 root=f"research/detector/v8.1/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 folder=Path("detector_v81_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"comparison.json").write_bytes(raw)
 dig=put(s,bucket,root+"comparison.json",raw)
 manifest={"version":"8.1","status":"COMPARABLE_DAY31_RESEARCH_PASS",
  "researchOnly":True,"reportSha256":dig,"prefix":root,
  "preregistrationSha256":sha(prereg_bytes)}
 msha=put(s,bucket,root+"manifest.json",json.dumps(manifest,indent=2).encode())
 brief={"status":"V81_RECOVERY_CHECKPOINT_PASS_WRITEBACK_VERIFIED",
   "prefix":root,"reportSha256":dig,"manifestSha256":msha,
   "historical":report["historicalCohortSummary"],
   "byPhase":bystate,"byEra":byera,
   "cases":cases,"current":current}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V81_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write("# Исследование v8.1 — восстановление BTC на 31 день\n\n"
    f"Статус: V81_RECOVERY_CHECKPOINT_PASS_WRITEBACK_VERIFIED\n\n"
    f"Наблюдений: {len(hist)} исторических + 1 текущий (правое цензурирование)\n\n"
    f"R2: {root}\n\nSHA-256: {dig}\n\nНе является разрешением торговли.\n")
if __name__=="__main__":main()
