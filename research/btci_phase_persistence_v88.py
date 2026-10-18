#!/usr/bin/env python3
"""BTCI v8.8: episode-level persistence of fully closed weekly BTC trends.
All inputs fixed research sources. Outputs are descriptive, not actionable.
"""
import datetime as dt,hashlib,json,os,statistics
from collections import Counter
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PREREG="research/btci_v88_phase_persistence_prereg_2026-10-18.json"
P86=("research/btci/v8.6/runs/39130315439-1/extended_history.json",
 "9af82767fa8139685e784c131c075cec553298c4718ed4a40ac41412144248ca")
P87=("research/btci/v8.7/runs/39131902527-1/episodes.json",
 "260d7991a6567aa370cbef92c8b7294b520c5a6a1b626872c4c55ae9e6a3d5b8")
PARCH=("research/btci/v8.7/runs/39131902527-1/archive_manifest.json",
 "3705a179363c9fdf50fede363fb7062481ce15c60f62dfada226e5371e674fb4")
K=(1,2,4,8)
H=(4,13,26,52)
ASSETS=("btc","eth","sol","bnb","link","xrp","ada","doge")
ERAS=[("2011-2012","2011-01-01","2013-01-01"),
 ("2013-2016","2013-01-01","2017-01-01"),
 ("2017-2019","2017-01-01","2020-01-01"),
 ("2020-2023","2020-01-01","2024-01-01"),
 ("2024-2026","2024-01-01","2027-01-01")]
def sha(x):return hashlib.sha256(x).hexdigest()
def rnd(x):return round(float(x),6) if x is not None else None
def client():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
 aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def get(s,b,key,digest):
 raw=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(raw)!=digest:raise SystemExit("V88_PINNED_PARENT_SHA_MISMATCH:"+key)
 return json.loads(raw)
def put(s,b,key,obj):
 raw=obj if isinstance(obj,bytes) else json.dumps(obj,ensure_ascii=False,indent=2).encode()
 dg=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType="application/json",
  Metadata={"sha256":dg,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=dg:
  raise SystemExit("V88_CLOUD_READBACK_FAILED:"+key)
 return dg
def chk_prereg():
 raw=(ROOT/PREREG).read_bytes()
 p=json.loads(raw)
 if p["version"]!="8.8" or p["parents"]!={"v86":{"key":P86[0],"sha256":P86[1]},
   "v87":{"key":P87[0],"sha256":P87[1]},
   "dailyArchiveManifest":{"key":PARCH[0],"sha256":PARCH[1]}}:
  raise SystemExit("V88_FROZEN_REGISTRATION_CHANGED")
 return sha(raw)
def proxy26(a):
 z=a["future"]["26"]
 if z["status"]!="OBSERVED":return "RIGHT_CENSORED"
 r=z["returnPct"];dd=z["worstDailyClosePct"]
 if r>=20 and dd>-20:return "POSITIVE_26W_PATH_PROXY"
 if r<=-20 or dd<=-20:return "ADVERSE_26W_PATH_PROXY"
 return "MIXED_26W_PATH_PROXY"
def broaden(weeks,start,cutoff=13):
 if start+cutoff>=len(weeks):return {"status":"RIGHT_CENSORED"}
 missing=False
 for off in range(1,cutoff+1):
  row=weeks[start+off]
  if row["altBreadth"]["status"]!="AVAILABLE":missing=True
  broad=row["altBreadth"]["status"]=="AVAILABLE" and row["altBreadth"].get("broadParticipation",False)
  lost=not row["weeklyTrendConfirmed"]
  if broad or lost:
   if missing:return {"status":"DATA_CENSORED_BREADTH","firstObserved":"BROAD" if broad else "LOST_TREND","weeks":off}
   return {"status":"BROAD_FIRST" if broad else "LOST_TREND_FIRST","weeks":off}
 if missing:return {"status":"DATA_CENSORED_BREADTH"}
 return {"status":"NEITHER"}
def case(weeks,event,n):
 i=event["index"]
 assert weeks[i]["date"]==event["date"]
 if i+n-1>=len(weeks):
  return {"eventDate":event["date"],"thresholdWeeks":n,
   "status":"PENDING_NOT_ENOUGH_CLOSED_WEEKS","epoch":era(event["date"])}
 sub=weeks[i:i+n]
 if not all(t["weeklyTrendConfirmed"] for t in sub):
  return {"eventDate":event["date"],"thresholdWeeks":n,
   "status":"FAILED_PERSISTENCE_BEFORE_CONFIRMATION","epoch":era(event["date"]),
   "firstLossWeek":next(k for k,x in enumerate(sub) if not x["weeklyTrendConfirmed"])}
 confirmed=weeks[i+n-1]
 price0=weeks[i]["btcFixingPriceUSD"]
 price=confirmed["btcFixingPriceUSD"]
 return {"eventDate":event["date"],"thresholdWeeks":n,"status":"CONFIRMED",
 "epoch":era(event["date"]),"confirmationSundayUTC":confirmed["date"],
 "delayWeeks":n-1,"referenceConfirmBTCPrice":price,
 "recognitionPriceChangePct":rnd(100*(price/price0-1)),
 "breadthAtConfirmation":confirmed["altBreadth"],
 "broadeningAfterConfirmation13w":broaden(weeks,i+n-1),
 "future":{str(h):confirmed["future"][str(h)] for h in H},
 "pathClass26w":proxy26(confirmed)}
def era(d):
 return next(name for name,st,en in ERAS if st<=d<en)
def summarize(cases):
 states=Counter(x["status"] for x in cases)
 confirmed=[x for x in cases if x["status"]=="CONFIRMED"]
 costs=[x["recognitionPriceChangePct"] for x in confirmed]
 d={"rawEntries":len(cases),
    "confirmed":len(confirmed),
    "failedPersistence":states["FAILED_PERSISTENCE_BEFORE_CONFIRMATION"],
    "pendingMaturation":states["PENDING_NOT_ENOUGH_CLOSED_WEEKS"],
    "medianRecognitionPriceChangePct":rnd(statistics.median(costs)) if costs else None,
    "positiveRecognitionPriceChange":sum(x>0 for x in costs),
    "path26w":dict(Counter(x["pathClass26w"] for x in confirmed)),
    "breadthAtConfirm":dict(Counter(x["breadthAtConfirmation"]["status"] for x in confirmed)),
    "broadening13w":dict(Counter(x["broadeningAfterConfirmation13w"]["status"] for x in confirmed))}
 for h in H:
  zs=[x["future"][str(h)] for x in confirmed]
  vs=[z for z in zs if z["status"]=="OBSERVED"]
  r=[z["returnPct"] for z in vs]
  worst=[z["worstDailyClosePct"] for z in vs]
  d[str(h)]={"observed":len(vs),"rightCensored":len(zs)-len(vs),
    "medianForwardReturnPct":rnd(statistics.median(r)) if r else None,
    "positiveReturnCount":sum(v>0 for v in r),
    "medianWorstDailyCloseDrawdownPct":rnd(statistics.median(worst)) if worst else None,
    "interpretation":"SMALL_SAMPLE_DESCRIPTIVE" if len(vs)<20 else "RETROSPECTIVE_DESCRIPTIVE"}
 return d
def main():
 pre=chk_prereg()
 s=client();b=os.environ["R2_BUCKET"]
 v86=get(s,b,*P86);v87=get(s,b,*P87);archive=get(s,b,*PARCH)
 weeks=v86["weeklyRows"]
 if (len(weeks)!=814 or v87["trendTransitions"]!=77
    or len(v87["allEvents"])!=77 or v87["trendEntries"]["n"]!=39
    or archive["status"]!="DAILY_SOURCE_ARCHIVE_PASS_READBACK"
    or set(archive["assets"])!=set(ASSETS)):
  raise SystemExit("V88_SOURCE_STRUCTURE_NOT_ACCEPTED")
 if weeks[-1]["date"]!="2026-10-11":raise SystemExit("V88_LAST_COMPLETE_WEEK_CHANGED")
 dates=[dt.date.fromisoformat(x["date"]) for x in weeks]
 if any(y-x!=dt.timedelta(days=7) for x,y in zip(dates,dates[1:])):
  raise SystemExit("V88_WEEK_DATE_GAP")
 original=[x for x in v87["allEvents"] if x["event"]=="TREND_ENTER"]
 computed=[i for i in range(1,len(weeks)) if weeks[i]["weeklyTrendConfirmed"] and not weeks[i-1]["weeklyTrendConfirmed"]]
 if computed!=[x["index"] for x in original]:raise SystemExit("V88_ENTRY_MISMATCH_WITH_FROZEN_V87")
 allcases={str(n):[case(weeks,x,n) for x in original] for n in K}
 byconfirm={str(n):summarize(allcases[str(n)]) for n in K}
 byera={e:{str(n):summarize([z for z in allcases[str(n)] if z["epoch"]==e]) for n in K}
     for e,_,_ in ERAS}
 spaced=[];last_index=-100
 for e in original:
  if e["index"]-last_index>=13:spaced.append(e);last_index=e["index"]
 spaced_ids={e["date"] for e in spaced}
 spacing={str(n):summarize([x for x in allcases[str(n)] if x["eventDate"] in spaced_ids]) for n in K}
 initialFailures=[{"entry":x["date"],"nextLoss":x["nextTransitionDate"],
     "durationWeeks":x["durationWeeks"],"altBroadening":x.get("altBroadeningNext13Weeks")}
   for x in original if not x["durationCensored"] and x["durationWeeks"]<4]
 current={str(n):allcases[str(n)][-1] for n in K}
 if current["4"]["status"]!="CONFIRMED" or current["8"]["status"]!="PENDING_NOT_ENOUGH_CLOSED_WEEKS":
  raise SystemExit("V88_CURRENT_PHASE_MATURITY_NOT_AS_EXPECTED")
 report={"version":"8.8","status":"LONG_CYCLE_TREND_PERSISTENCE_RESEARCH_ONLY",
  "researchOnly":True,"noTradePermission":True,"asOfClosedSundayUTC":"2026-10-11",
  "sources":{"v86":{"key":P86[0],"sha256":P86[1]},
      "v87":{"key":P87[0],"sha256":P87[1]},
      "archive":{"key":PARCH[0],"sha256":PARCH[1]}},
  "preregistration":{"path":PREREG,"sha256":pre},
  "question":"Does requiring multiple fully closed consecutive weekly trend bars reduce early false weekly phase changes and how many weeks/gains does confirmation cost?",
  "comparisonByThresholdWeeks":byconfirm,
  "byEra":byera,"spacing13w":spacing,
  "earlyFailuresLessThan4w":initialFailures,
  "current":current,"casesByThresholdWeeks":allcases,
  "cautions":["Persistence confirmation is available only after N fully closed weeks, never backdated",
    "The 26-week +20% and worst-drawdown >-20% metric is an explicitly chosen price-path proxy, NOT true macro bull cycle ground truth",
    "Conditioning on surviving N weeks selects a different cohort; improving conditional results does not prove superior policy",
    "Lost weekly trend after confirmation need not mean major bear cycle",
    "Selected CoinMetrics BTC reference rate is historical backfill with unknown original published vintages",
    "Modern 8-asset breadth data incomplete before alt listings; UNKNOWN != zero",
    "Sample units share major market cycles. No independent OOS interval or predictive success probabilities",
    "ETF and macro publication vintages not verified or joined in this price-only study",
    "No Futures, Spot, NAV, P&L, capital, reserve, limit, runtime Detector or MASTER writeback"]}
 folder=Path("btci_v88_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"comparison.json").write_bytes(raw)
 root=f"research/btci/v8.8/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 dg=put(s,b,root+"comparison.json",raw)
 manifest={"version":"8.8","status":"PERSISTENCE_RESEARCH_PASS","researchOnly":True,
   "reportSha256":dg,"preregSha256":pre,"prefix":root}
 ms=put(s,b,root+"manifest.json",manifest)
 brief={"status":"V88_PERSISTENCE_RESEARCH_PASS_WRITEBACK_VERIFIED",
  "reportSha256":dg,"manifestSha256":ms,"prefix":root,
  "byConfirmation":byconfirm,"byEra":byera,"spacing13w":spacing,
  "current":current,"earlyFailuresLessThan4w":len(initialFailures)}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V88_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write("# BTCI v8.8 — устойчивость недельного тренда BTC\n\n"
    f"Только Research, входов: {len(original)}. Конфигурации: 1,2,4,8 недель.\n\n"
    f"R2: {root}\n\nSHA-256: {dg}\n")
if __name__=="__main__":main()
