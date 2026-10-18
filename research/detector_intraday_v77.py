#!/usr/bin/env python3
"""Historical research v7.7: immutable events, 1h/2h/4h, regimes and quarter-block stability.

Research only; NEVER modifies live Detector, Futures, NAV, trading limits or orders.
"""
import argparse, ast, hashlib, json, os, random, statistics, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import boto3

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
ASSETS=("BTC","ETH","SOL","BNB","LINK","XRP","ADA","DOGE")
HORIZONS={"1h":4,"2h":8,"4h":16}
FROZEN={
 "core":("research/detector/v7.5/runs/39115280960-1/combined/comparison.json",
         "07fccb39f6973c2f6f4fb297dc4d3d95cd6e3c06fca154a503c97e242f080e8f"),
 "alts":("research/detector/v7.6/runs/39115615591-1/combined/comparison.json",
         "1d8fd630f7fc0aec6e8308128a79f66344343b0d8a5b14280b6a58507340a95c"),
}
PREREG="research/detector_v77_intraday_robustness_prereg_2026-10-18.json"
PREREG_COMMIT="8acb26f6ec6544e5507f2ee413d9b6724c1b45ec"
REPEATS=12000
SEED=770018

def sha(x):return hashlib.sha256(x).hexdigest()
def rounded(x):return round(float(x),6) if x is not None else None
def quantile(arr,p):
 z=sorted(arr)
 k=(len(z)-1)*p;i=int(k)
 return z[i]+(z[min(i+1,len(z)-1)]-z[i])*(k-i)
def newclient():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def runprefix():
 return f"research/detector/v7.7/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
def get_checked(s3,bucket,key,expected):
 raw=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
 if sha(raw)!=expected:raise SystemExit("V77_SOURCE_SHA_MISMATCH:"+key)
 return json.loads(raw)
def write_checked(s3,bucket,key,obj):
 raw=obj if isinstance(obj,bytes) else json.dumps(obj,ensure_ascii=False,indent=2).encode()
 digest=sha(raw)
 s3.put_object(Bucket=bucket,Key=key,Body=raw,ContentType="application/json",
               Metadata={"sha256":digest,"research-only":"true"})
 if sha(s3.get_object(Bucket=bucket,Key=key)["Body"].read())!=digest:
  raise SystemExit("V77_WRITEBACK_MISMATCH:"+key)
 return digest
def load_prereg():
 raw=(ROOT/PREREG).read_bytes()
 doc=json.loads(raw)
 if doc["version"]!="7.7" or doc["instruments"]!=list(ASSETS):
  raise SystemExit("V77_PREREG_MISMATCH")
 for scope in FROZEN:
  ref=doc["sourceReports"]["btcEth" if scope=="core" else "alts"]
  if ref["key"]!=FROZEN[scope][0] or ref["sha256"]!=FROZEN[scope][1]:
   raise SystemExit("V77_PREREG_REFERENCE_CHANGED")
 return sha(raw)
def load_frozen(s3,bucket):
 core=get_checked(s3,bucket,*FROZEN["core"])
 alts=get_checked(s3,bucket,*FROZEN["alts"])
 if core["version"]!="7.5" or core["symbolMonths"]!=162 or core["eventCount"]!=4603:
  raise SystemExit("V77_CORE_REPORT_CHANGED")
 if alts["version"]!="7.6" or alts["symbolMonths"]!=461 or alts["firstLongEvents"]!=13075:
  raise SystemExit("V77_ALT_REPORT_CHANGED")
 return core,alts
def read_bars_fn():
 tree=ast.parse((ROOT/"research/detector_matched_controls_v65.py").read_text())
 fun=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="read_month")
 import csv,io,zipfile
 scope={"hashlib":hashlib,"csv":csv,"io":io,"zipfile":zipfile,"P5":300000}
 exec(compile(ast.Module(body=[fun],type_ignores=[]),"<unchanged v65 read_month>","exec"),scope)
 return scope["read_month"]

def extract_sources(s3,bucket,symbol,core,alts):
 if symbol in ("BTC","ETH"):
  records=[];events=[]
  for year in core["sourceYears"]:
   root=year["prefix"]
   yearrows=get_checked(s3,bucket,root+"records.json",year["recordsSha256"])
   yearevents=get_checked(s3,bucket,root+"events.json",year["eventsSha256"])
   records.extend(r for r in yearrows if r["symbol"]==symbol)
   events.extend(e for e in yearevents if e["symbol"]==symbol)
  expected=81
 else:
  source=next(x for x in alts["sources"] if x["symbol"]==symbol)
  root=source["prefix"]
  records=get_checked(s3,bucket,root+"records.json",source["recordsSha256"])
  events=get_checked(s3,bucket,root+"events.json",source["eventsSha256"])
  expected=alts["byAsset"][symbol]["symbolMonths"]
 if len(records)!=expected or len({r["month"] for r in records})!=expected:
  raise SystemExit("V77_SOURCE_ASSET_MONTHS_MISMATCH:"+symbol)
 return records,events

def month_stats(month,sym,subset):
 out={"symbol":sym,"month":month,"firstLong":len(subset),
      "firstSweep":sum(e["sweep"] for e in subset)}
 for h in HORIZONS:
  a=[e[h] for e in subset if e["sweep"]]
  b=[e[h] for e in subset if not e["sweep"]]
  out[h]={"groupA":len(a),"groupB":len(b),
          "meanA":rounded(statistics.mean(a)) if a else None,
          "meanB":rounded(statistics.mean(b)) if b else None,
          "differencePctPoints":rounded(statistics.mean(a)-statistics.mean(b)) if a and b else None}
 return out

def compute_asset(sym):
 prereg_sha=load_prereg()
 s3=newclient();bucket=os.environ["R2_BUCKET"]
 core,alts=load_frozen(s3,bucket)
 records,events=extract_sources(s3,bucket,sym,core,alts)
 bymonth=defaultdict(list)
 for e in events:bymonth[e["month"]].append(e)
 if sum(r["firstCandidates"] for r in records)!=len(events):
  raise SystemExit("V77_EVENT_COUNT_CHANGED")
 read_month=read_bars_fn()
 completed=[]
 for record in records:
  month=record["month"];origin=bymonth.get(month,[])
  if (len(origin)!=record["firstCandidates"] or
      sum(bool(e["sweep"]) for e in origin)!=record["firstSweep"]):
   raise SystemExit("V77_FIRST_EVENTS_CHANGED:"+sym+"/"+month)
  bars,digest=read_month(s3,bucket,sym,month)
  if digest!=record["sourceSha256"]:raise SystemExit("V77_ARCHIVE_SHA_CHANGED:"+sym+"/"+month)
  y,m=map(int,month.split("-"))
  nextmonth=f"{y+1}-01" if m==12 else f"{y}-{m+1:02d}"
  if (datetime.fromtimestamp(bars[0]["t"]/1000,timezone.utc)!=
      datetime.fromisoformat(month+"-01").replace(tzinfo=timezone.utc) or
      datetime.fromtimestamp(bars[-1]["endMs"]/1000,timezone.utc)!=
      datetime.fromisoformat(nextmonth+"-01").replace(tzinfo=timezone.utc)):
   raise SystemExit("V77_INCOMPLETE_MONTH:"+sym+"/"+month)
  indexes={bar["t"]:i for i,bar in enumerate(bars)}
  for e in origin:
   if e["timestampMs"] not in indexes:raise SystemExit("V77_EVENT_TIMESTAMP_MISSING")
   i=indexes[e["timestampMs"]]
   if i+96>=len(bars) or i<96:raise SystemExit("V77_EVENT_EDGE_INVALID")
   prices={h:100*(bars[i+steps]["c"]/bars[i]["c"]-1) for h,steps in HORIZONS.items()}
   original4=100*(bars[i+16]["c"]/bars[i]["c"]-1)
   original24=100*(bars[i+96]["c"]/bars[i]["c"]-1)
   if abs(original4-e["4h"])>1e-9 or abs(original24-e["24h"])>1e-9:
    raise SystemExit("V77_ORIGINAL_FORWARD_MISMATCH:"+sym+"/"+month)
   e.update(prices)
  row=month_stats(month,sym,origin)
  old=record["firstCandidateComparison"]["horizons"]["4h"]
  new=row["4h"]
  for key in ("groupA","groupB","meanA","meanB","differencePctPoints"):
   if old[key]!=new[key]:raise SystemExit("V77_FROZEN_MONTHLY_4H_PARITY:"+sym+"/"+month+"/"+key)
  completed.append(row)
 root=runprefix()+"assets/"+sym+"/"
 digest_rows=write_checked(s3,bucket,root+"months.json",completed)
 digest_events=write_checked(s3,bucket,root+"events.json",events)
 manifest={"version":"7.7","symbol":sym,"researchOnly":True,
  "preregSha256":prereg_sha,"sources":{"7.5":FROZEN["core"][1],"7.6":FROZEN["alts"][1]},
  "sourceMonths":len(completed),"eventCount":len(events),
  "monthsSha256":digest_rows,"eventsSha256":digest_events,
  "prefix":root,"githubSha":os.environ.get("GITHUB_SHA")}
 digest_manifest=write_checked(s3,bucket,root+"manifest.json",manifest)
 summary={"status":"V77_ASSET_INTRADAY_SOURCE_PARITY_PASS",
  "symbol":sym,"months":len(completed),"events":len(events),
  "manifestSha256":digest_manifest,"prefix":root}
 folder=Path("detector_v77_reports");folder.mkdir(exist_ok=True)
 (folder/(sym+".json")).write_text(json.dumps(summary,indent=2))
 print(json.dumps(summary,ensure_ascii=False),flush=True)

def agg(rows,h):
 a_n=b_n=0;a_sum=b_sum=0.0
 plus=minus=both=0
 for r in rows:
  z=r[h]
  if z["groupA"] and z["groupB"]:
   a_n+=z["groupA"];b_n+=z["groupB"]
   a_sum+=z["groupA"]*z["meanA"];b_sum+=z["groupB"]*z["meanB"]
   both+=1
   if z["differencePctPoints"]>0:plus+=1
   if z["differencePctPoints"]<0:minus+=1
 return {"nSweep":a_n,"nControl":b_n,"symbolMonthsWithBoth":both,
  "positiveSymbolMonths":plus,"negativeSymbolMonths":minus,
  "differencePctPoints":rounded(a_sum/a_n-b_sum/b_n) if a_n and b_n else None}

def byh(rows):
 return {h:agg(rows,h) for h in HORIZONS}

def event_diff(events,h):
 a=[x[h] for x in events if x["sweep"]]
 b=[x[h] for x in events if not x["sweep"]]
 return rounded(statistics.mean(a)-statistics.mean(b)) if a and b else None

def simultaneous_bootstrap(rows):
 import numpy as np
 quarters=sorted({r["month"][:4]+"Q"+str((int(r["month"][5:])-1)//3+1) for r in rows})
 if len(quarters)!=27:raise SystemExit("V77_WRONG_QUARTER_COVERAGE")
 indices={(sym,h):i for i,(sym,h) in enumerate((s,h) for s in ASSETS for h in HORIZONS)}
 n=len(indices);q=len(quarters);q_index={x:i for i,x in enumerate(quarters)}
 A=np.zeros((q,n),dtype=np.float64)
 B=np.zeros((q,n),dtype=np.float64)
 AS=np.zeros((q,n),dtype=np.float64)
 BS=np.zeros((q,n),dtype=np.float64)
 for row in rows:
  key=row["month"][:4]+"Q"+str((int(row["month"][5:])-1)//3+1)
  k=q_index[key]
  for h in HORIZONS:
   obj=row[h]
   if obj["groupA"] and obj["groupB"]:
    i=indices[(row["symbol"],h)]
    A[k,i]+=obj["groupA"];B[k,i]+=obj["groupB"]
    AS[k,i]+=obj["groupA"]*obj["meanA"];BS[k,i]+=obj["groupB"]*obj["meanB"]
 if np.any(A.sum(axis=0)==0) or np.any(B.sum(axis=0)==0):
  raise SystemExit("V77_FULL_SAMPLE_EMPTY_GROUP")
 observed=(AS.sum(axis=0)/A.sum(axis=0))-(BS.sum(axis=0)/B.sum(axis=0))
 rng=np.random.default_rng(SEED)
 counts=np.zeros((REPEATS,q),dtype=np.float64)
 for k in range(REPEATS):
  counts[k,:]=np.bincount(rng.integers(q,size=q),minlength=q)
 N_A=counts@A;N_B=counts@B
 if np.any(N_A==0) or np.any(N_B==0):raise SystemExit("V77_EMPTY_BOOTSTRAP_GROUPS")
 sims=(counts@AS)/N_A-(counts@BS)/N_B
 sd=sims.std(axis=0)
 if np.any(sd<=0):raise SystemExit("V77_BOOTSTRAP_ZERO_SD")
 maxima=np.max(np.abs((sims-observed)/sd),axis=1)
 critical=float(np.quantile(maxima,.95))
 result={}
 for (sym,h),i in indices.items():
  z=sims[:,i]
  result.setdefault(sym,{})[h]={
   "differencePctPoints":rounded(observed[i]),
   "percentile95":[rounded(np.quantile(z,.025)),rounded(np.quantile(z,.975))],
   "familywiseSimultaneous95":[rounded(observed[i]-critical*sd[i]),
     rounded(observed[i]+critical*sd[i])],
   "sd":rounded(sd[i]),
   "lowerSimultaneousAboveZero":bool(observed[i]-critical*sd[i]>0)}
 return {"quarterClusters":q,"resamples":REPEATS,"seed":SEED,
    "comparisonFamily":"8 assets x 3 horizons, 24 total, synchronized quarter max-t",
    "criticalMaxT":rounded(critical),"assets":result}

def stable_labels(rows,boot):
 report={}
 for sym in ASSETS:
  a=[r for r in rows if r["symbol"]==sym]
  era={"2020-2023":byh([r for r in a if r["month"]<"2024-01"]),
       "2024-2026":byh([r for r in a if r["month"]>="2024-01"])}
  years={str(y):byh([r for r in a if r["month"].startswith(str(y))]) for y in range(2020,2027)}
  gate={}
  for h in HORIZONS:
   count=sum(yr[h]["differencePctPoints"] is not None and
             yr[h]["differencePctPoints"]>0 for yr in years.values())
   eligible=sum(yr[h]["differencePctPoints"] is not None for yr in years.values())
   both=all(z[h]["differencePctPoints"] is not None and
            z[h]["differencePctPoints"]>0 for z in era.values())
   interval=boot["assets"][sym][h]
   passed=both and eligible==7 and count>=5 and interval["lowerSimultaneousAboveZero"]
   gate[h]={"positiveYears":count,"eligibleYears":eligible,
     "positiveBothEras":both,"simultaneousCIAboveZero":interval["lowerSimultaneousAboveZero"],
     "classification":"EXPLORATORY_PRIORITY_ONLY" if passed else "UNSTABLE_OR_INCONCLUSIVE"}
  report[sym]={"years":years,"eras":era,"gates":gate,
    "full":byh(a),"monthCount":len(a)}
 return report

def combine():
 prereg_sha=load_prereg()
 s3=newclient();bucket=os.environ["R2_BUCKET"]
 core,alts=load_frozen(s3,bucket)
 allrows=[];events=[];manifests=[]
 for sym in ASSETS:
  root=runprefix()+"assets/"+sym+"/"
  m=json.loads(s3.get_object(Bucket=bucket,Key=root+"manifest.json")["Body"].read())
  if m["symbol"]!=sym or m["version"]!="7.7" or m["preregSha256"]!=prereg_sha:
   raise SystemExit("V77_ASSET_MANIFEST_CHANGED")
  rows=get_checked(s3,bucket,root+"months.json",m["monthsSha256"])
  e=get_checked(s3,bucket,root+"events.json",m["eventsSha256"])
  expected=(core["byAsset"][sym]["symbolMonths"] if sym in ("BTC","ETH") else
            alts["byAsset"][sym]["symbolMonths"])
  if len(rows)!=expected or len(e)!=m["eventCount"]:raise SystemExit("V77_EXPECTED_MONTHS_CHANGED:"+sym)
  allrows+=rows;events+=e
  manifests.append({"symbol":sym,"prefix":root,"monthsSha256":m["monthsSha256"],
    "eventsSha256":m["eventsSha256"]})
 if len(allrows)!=623 or len(events)!=17678 or sum(e["sweep"] for e in events)!=3439:
  raise SystemExit("V77_FULL_SAMPLE_OR_EVENTS_CHANGED")
 if len({(r["symbol"],r["month"]) for r in allrows})!=623:
  raise SystemExit("V77_DUPLICATES")
 for sym in ASSETS:
  source=(core if sym in ("BTC","ETH") else alts)["byAsset"][sym]
  old=source["horizons"]["4h"]["differencePctPoints"]
  new=agg([r for r in allrows if r["symbol"]==sym],"4h")["differencePctPoints"]
  if abs(old-new)>0.000002:raise SystemExit("V77_4H_AGGREGATE_REPLAY_MISMATCH:"+sym)
 boot=simultaneous_bootstrap(allrows)
 studies=stable_labels(allrows,boot)
 epochs={"2020-2023":byh([r for r in allrows if r["month"]<"2024-01"]),
         "2024-2026":byh([r for r in allrows if r["month"]>="2024-01"])}
 byregime={}
 for reg in ("UP","DOWN","SIDEWAYS"):
  selected=[e for e in events if e["regime"]==reg]
  byregime[reg]={"n":len(selected),"nSweep":sum(e["sweep"] for e in selected),
    "effects":{h:event_diff(selected,h) for h in HORIZONS}}
 per_asset_regime={}
 for sym in ASSETS:
  per_asset_regime[sym]={}
  for reg in ("UP","DOWN","SIDEWAYS"):
   selected=[e for e in events if e["symbol"]==sym and e["regime"]==reg]
   per_asset_regime[sym][reg]={"n":len(selected),
    "nSweep":sum(e["sweep"] for e in selected),
    "effects":{h:event_diff(selected,h) for h in HORIZONS}}
 parities={}
 for sym in ASSETS:
  parities[sym]={}
  for p in (0,1):
   selected=sorted((e for e in events if e["symbol"]==sym and e["parity"]==p),key=lambda x:x["timestampMs"])
   # one event per alternate UTC day; even the 4h windows must not overlap
   overlap=sum(a["timestampMs"]+14400000>b["timestampMs"] for a,b in zip(selected,selected[1:]))
   if overlap:raise SystemExit("V77_NONOVERLAP_GUARD_FAILED")
   parities[sym][str(p)]={"n":len(selected),
     "nSweep":sum(e["sweep"] for e in selected),
     "effects":{h:event_diff(selected,h) for h in HORIZONS},"overlapPairs4h":0}
 report={"version":"7.7","status":"INTRADAY_CROSS_REGIME_HISTORICAL_RESEARCH_ONLY",
  "researchOnly":True,"tradesEmitted":0,"originalLiveDetectorParity":"NOT_ESTABLISHED",
  "preregistration":{"path":PREREG,"commit":PREREG_COMMIT,"sha256":prereg_sha},
  "sourceReports":FROZEN,"assetSourceManifests":manifests,
  "window":"2020-01 to 2026-09","assetMonths":623,"firstLongEvents":len(events),
  "firstSweepEvents":sum(e["sweep"] for e in events),
  "horizons":list(HORIZONS),"total":byh(allrows),"eras":epochs,
  "assets":studies,"quarterBlockBootstrap":boot,
  "regimes":byregime,"perAssetRegimes":per_asset_regime,"utcDayParity":parities,
  "limitations":[
   "1h/2h were chosen after inspecting 4h/24h retrospective findings: no virgin holdout",
   "No causal inference from era split; ETF events are context, not identified treatment",
   "Selected surviving assets can cause survivorship bias",
   "Within-quarter dependencies preserved, but adjacent-quarter dependence may remain",
   "Familywise simultaneous max-t is an exploratory approximate bootstrap with multiple tests",
   "Regime groups use trailing 24h close returns, not a complete measure of orderflow",
   "No fees, spread, slippage, funding, execution, OI, independent market data, or full live Detector parity",
   "No authority to create trades or alter a portfolio"
  ]}
 folder=Path("detector_v77_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"comparison.json").write_bytes(raw)
 root=runprefix()+"combined/"
 digest=write_checked(s3,bucket,root+"comparison.json",raw)
 manifest={"version":"7.7","status":"INTRADAY_RESEARCH_PASS","researchOnly":True,
  "reportSha256":digest,"preregSha256":prereg_sha,"prefix":root}
 msha=write_checked(s3,bucket,root+"manifest.json",manifest)
 summary={"status":"V77_INTRADAY_RESEARCH_PASS_WRITEBACK_VERIFIED","reportSha256":digest,
  "manifestSha256":msha,"prefix":root,"assetMonths":623,
  "firstLongEvents":len(events),"firstSweepEvents":sum(e["sweep"] for e in events),
  "total":report["total"],"eras":epochs,
  "assets":{sym:{"full":s["full"],"eras":s["eras"],"gates":s["gates"]}
            for sym,s in studies.items()},
  "bootstrap":boot,"regimes":byregime}
 (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print("V77_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
 if os.environ.get("GITHUB_STEP_SUMMARY"):
  lines=["# Detector v7.7 — 1h, 2h, 4h. Regime robustness audit","",
   "Status: V77_INTRADAY_RESEARCH_PASS_WRITEBACK_VERIFIED","",
   "SHA256: "+digest,"","R2: "+root,"",
   "| Asset | 1h Δpp | 2h Δpp | 4h Δpp | Robustness gate |",
   "|---|---:|---:|---:|---|"]
  for sym,x in studies.items():
   lines.append(f"| {sym} | {x['full']['1h']['differencePctPoints']} | {x['full']['2h']['differencePctPoints']} | {x['full']['4h']['differencePctPoints']} | "+
    ",".join(h for h in HORIZONS if x["gates"][h]["classification"]=="EXPLORATORY_PRIORITY_ONLY") +" |")
  lines.append("\nRESEARCH ONLY. Descriptive and exploratory; no trade authorization.")
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:f.write("\n".join(lines)+"\n")
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--asset",choices=ASSETS)
 parser.add_argument("--combine",action="store_true")
 a=parser.parse_args()
 if a.combine:combine()
 elif a.asset:compute_asset(a.asset)
 else:raise SystemExit("V77_ARGUMENTS_INVALID")
if __name__=="__main__":main()
