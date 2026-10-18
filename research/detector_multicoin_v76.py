#!/usr/bin/env python3
"""Retrospective major-alt cycle comparison v7.6, source months frozen from v7.4 inventory.
Research-only; does not alter live Detector, Futures, NAV, portfolio, trades, or limits.
"""
import argparse,json,os,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from detector_full_cycle_v75 import (ROOT,EXPECTED,HORIZONS,REFERENCES,
 sha,rnd,s3conn,get_versioned,stage,source_functions,agg,event_effect,overlaps,
 quantile)
ALTS=("SOL","BNB","LINK","XRP","ADA","DOGE")
AUDIT_KEY="research/detector/v7.4/runs/39114922267-1/coverage.json"
AUDIT_SHA="204941a9114910ea37cb53049c247e338f6b46d6ac5621c3460af23b779c4d2a"
PREREG="research/detector_v76_multicoin_prereg_2026-10-18.json"
PREREG_COMMIT="89897a1db3e013f57e7111d45b8ac999cc172858"
REPEATS=12000;SEED=760018
def prefix():
 return f"research/detector/v7.6/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
def verify(s3,bucket):
 raw=(ROOT/PREREG).read_bytes();d=json.loads(raw)
 if d["version"]!="7.6" or tuple(d["symbols"])!=ALTS or d["archivedInventory"]["sha256"]!=AUDIT_SHA:
  raise SystemExit("V76_PREREG_CHANGED")
 coverage=get_versioned(s3,bucket,AUDIT_KEY,AUDIT_SHA)
 if coverage["version"]!="7.4" or coverage["months"]!=81:
  raise SystemExit("V76_COVERAGE_CHANGED")
 return coverage,sha(raw)
def months_for(coverage,sym):
 z=coverage["bySymbol"][sym]
 excluded={x["month"] for x in z["needsValidationOrBackfill"]}
 selected=[m for m in EXPECTED if m not in excluded]
 if len(selected)!=z["statuses"]["METADATA_FULL"]:
  raise SystemExit("V76_MONTH_SELECTION_MISMATCH:"+sym)
 return selected,z["needsValidationOrBackfill"]

def year_list(events):
 return sorted({e["month"][:4] for e in events})
def calculate_asset(sym):
 s3=s3conn();bucket=os.environ["R2_BUCKET"]
 cov,prereg_sha=verify(s3,bucket)
 selected,excluded=months_for(cov,sym)
 fn=source_functions()
 analyze,read_month,events_fn=(fn[n] for n in ("analyze","read_month","events_and_regimes"))
 rows=[];events=[];errors=[]
 for month in selected:
  try:
   bars,digest=read_month(s3,bucket,sym,month)
   y,m=map(int,month.split("-"))
   nx=f"{y+1}-01" if m==12 else f"{y}-{m+1:02d}"
   if (datetime.fromtimestamp(bars[0]["t"]/1000,timezone.utc)!=
       datetime.fromisoformat(month+"-01").replace(tzinfo=timezone.utc)
       or datetime.fromtimestamp(bars[-1]["endMs"]/1000,timezone.utc)!=
       datetime.fromisoformat(nx+"-01").replace(tzinfo=timezone.utc)):
    raise ValueError("V76_FULL_MONTH_BOUNDARIES")
   rec={"symbol":sym,"month":month,"cohort":"alt_retrospective",
        "sourceSha256":digest,**analyze(bars),"status":"RESEARCH_PASS"}
   e=events_fn(bars,rec)
   for obj in e:obj["cohort"]="alt_retrospective"
   rows.append(rec);events+=e
  except Exception as exc:
   errors.append({"symbol":sym,"month":month,"reason":type(exc).__name__+":"+str(exc)[:150]})
 if errors or len(rows)!=len(selected):
  print("V76_ASSET_BLOCKED "+json.dumps({"symbol":sym,"errors":errors,"expected":len(selected),
   "actual":len(rows)},ensure_ascii=False),flush=True)
  raise SystemExit("V76_ASSET_SOURCE_REPLAY_BLOCKED")
 keybase=prefix()+f"assets/{sym}/"
 re=stage(s3,bucket,keybase+"records.json",json.dumps(rows,ensure_ascii=False,indent=2).encode())
 ev=stage(s3,bucket,keybase+"events.json",json.dumps(events,ensure_ascii=False,indent=2).encode())
 meta={"version":"7.6","symbol":sym,"researchOnly":True,"monthsTested":len(rows),
  "excludedInventoryMonths":excluded,"recordsSha256":re,"eventsSha256":ev,
  "preregistrationSha256":prereg_sha,"coverageSha256":AUDIT_SHA,"prefix":keybase,
  "firstEvents":len(events),"githubSha":os.environ.get("GITHUB_SHA")}
 mt=stage(s3,bucket,keybase+"manifest.json",meta)
 folder=Path("detector_v76_reports");folder.mkdir(exist_ok=True)
 result={"status":"V76_ASSET_RESEARCH_PASS_WRITEBACK_VERIFIED",
    "symbol":sym,"monthsTested":len(rows),"firstLongEvents":len(events),
    "excludedMonths":excluded,"summary":agg(rows),"prefix":keybase,"manifestSha256":mt}
 (folder/(sym+".json")).write_text(json.dumps(result,indent=2,ensure_ascii=False))
 print(json.dumps(result,ensure_ascii=False),flush=True)

def bootstrap(rows):
 quarters=defaultdict(list)
 for x in rows:
  q=(int(x["month"][5:])-1)//3+1
  quarters[x["month"][:4]+f"-Q{q}"].append(x)
 order=sorted(quarters)
 if len(order)!=27:raise SystemExit("V76_MISSING_QUARTERS")
 import random,hashlib
 rng=random.Random(SEED)
 observed=agg(rows)["horizons"]
 draws={h:[] for h in HORIZONS}
 for _ in range(REPEATS):
  selection=[e for _ in order for e in quarters[order[rng.randrange(len(order))]]]
  res=agg(selection)["horizons"]
  if all(res[h]["differencePctPoints"] is not None for h in HORIZONS):
   for h in HORIZONS:draws[h].append(res[h]["differencePctPoints"])
 if min(len(draws[h]) for h in HORIZONS)<.99*REPEATS:
  raise SystemExit("V76_BOOTSTRAP_EMPTY")
 return {"quarterClusters":len(order),"seed":SEED,"resamples":len(draws["4h"]),
  "horizons":{h:{"effectPctPoints":observed[h]["differencePctPoints"],
    "percentile95":[rnd(quantile(draws[h],.025)),rnd(quantile(draws[h],.975))]}
    for h in HORIZONS}}

def combine():
 s3=s3conn();bucket=os.environ["R2_BUCKET"]
 cov,prereg_sha=verify(s3,bucket)
 allrows=[];events=[];files=[];availability={}
 for sym in ALTS:
  selected,excluded=months_for(cov,sym)
  root=prefix()+f"assets/{sym}/"
  blob=s3.get_object(Bucket=bucket,Key=root+"manifest.json")["Body"].read()
  m=json.loads(blob)
  if m["version"]!="7.6" or m["symbol"]!=sym or m["preregistrationSha256"]!=prereg_sha:
   raise SystemExit("V76_ASSET_MANIFEST_MISMATCH")
  rows=get_versioned(s3,bucket,root+"records.json",m["recordsSha256"])
  month_events=get_versioned(s3,bucket,root+"events.json",m["eventsSha256"])
  if [r["month"] for r in rows]!=selected or len(month_events)!=m["firstEvents"]:
   raise SystemExit("V76_PINNED_MONTHS_CHANGED:"+sym)
  allrows+=rows;events+=month_events
  availability[sym]={"fullValidated":len(rows),"monthsMissingOrUnverified":excluded,
                      "firstValidated":selected[0] if selected else None}
  files.append({"symbol":sym,"manifestSha256":sha(blob),
    "recordsSha256":m["recordsSha256"],"eventsSha256":m["eventsSha256"],"prefix":root})
 if len({(r["symbol"],r["month"]) for r in allrows})!=len(allrows):
  raise SystemExit("V76_DUPLICATE_MONTHS")
 by_asset={sym:agg([r for r in allrows if r["symbol"]==sym]) for sym in ALTS}
 by_year={str(y):agg([r for r in allrows if r["month"].startswith(str(y))])
          for y in range(2020,2027)}
 by_era={"2020-2023":agg([r for r in allrows if r["month"]<"2024-01"]),
   "2024-2026":agg([r for r in allrows if r["month"]>="2024-01"])}
 by_regime={}
 for regime in ("UP","DOWN","SIDEWAYS"):
  sample=[e for e in events if e["regime"]==regime]
  by_regime[regime]={"n":len(sample),"sweep":sum(e["sweep"] for e in sample),
   "difference":{h:rnd(event_effect(sample,h)) for h in HORIZONS}}
 phases={}
 for sym in ALTS:
  per={};sub=[e for e in events if e["symbol"]==sym]
  for p in (0,1):
   series=[e for e in sub if e["parity"]==p]
   c=overlaps_one_symbol(series,sym)
   if c:raise SystemExit("V76_NONOVERLAP_BROKEN:"+sym)
   per[str(p)]={"first":len(series),"sweep":sum(e["sweep"] for e in series),
    "effect":{h:rnd(event_effect(series,h)) for h in HORIZONS},"24hOverlaps":0}
  phases[sym]=per
 report={"version":"7.6","status":"SELECTED_MAJOR_ALTS_HISTORICAL_RESEARCH_ONLY",
  "researchOnly":True,"tradesEmitted":0,"originalLiveDetectorParity":"NOT_ESTABLISHED",
  "preregistration":{"path":PREREG,"commit":PREREG_COMMIT,"sha256":prereg_sha},
  "inventory":{"key":AUDIT_KEY,"sha256":AUDIT_SHA},
  "from":"2020-01","to":"2026-09","symbols":ALTS,
  "symbolMonths":len(allrows),"firstLongEvents":len(events),
  "total":agg(allrows),"byAsset":by_asset,"byYear":by_year,"byEra":by_era,
  "sourceCoverage":availability,"sources":files,
  "regime":by_regime,"nonoverlapPhases":phases,
  "quarterBlockBootstrap":bootstrap(allrows),
  "limitations":["Survivorship bias: six present-day selected large assets, not full historical available universe",
   "Not all assets traded or have valid archives from January 2020; no prelisting price imputation",
   "Missing or incomplete months excluded by frozen source-quality rule and disclosed",
   "Different volumes and listings imply across-asset descriptive comparisons, not equal market exposure",
   "Historical data, not untouched prospective samples; fee/slippage/funding/OI/actual execution absent",
   "Quarter bootstrap approximate and serial dependence may persist; multiple testing matters",
   "No live Detector parity or authority to modify trading system"]}
 folder=Path("detector_v76_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(report,indent=2,ensure_ascii=False).encode()
 (folder/"comparison.json").write_bytes(raw)
 root=prefix()+"combined/"
 d=stage(s3,bucket,root+"comparison.json",raw)
 mt=stage(s3,bucket,root+"manifest.json",{"version":"7.6","researchOnly":True,
   "status":"MULTICOIN_HISTORICAL_RESEARCH_PASS","reportSha256":d,"prefix":root,
   "preregistrationSha256":prereg_sha,"source":files})
 brief={"status":"V76_MULTICOIN_RESEARCH_PASS_WRITEBACK_VERIFIED","prefix":root,
  "reportSha256":d,"manifestSha256":mt,"symbolMonths":len(allrows),
  "total":report["total"],"byAsset":by_asset,"byEra":by_era,
  "quarterBlockBootstrap":report["quarterBlockBootstrap"],
  "sourceCoverage":availability,"regime":by_regime}
 (folder/"summary.json").write_text(json.dumps(brief,indent=2,ensure_ascii=False))
 print(json.dumps(brief,ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write("# Detector v7.6 historical selected major alts\n\n"
    "Status: V76_MULTICOIN_RESEARCH_PASS_WRITEBACK_VERIFIED\n\n"
    "R2: "+root+"\n\nReport SHA-256: "+d+"\n")
def overlaps_one_symbol(events,sym):
 a=sorted((e for e in events if e["symbol"]==sym),key=lambda e:e["timestampMs"])
 return sum(left["timestampMs"]+86400000>right["timestampMs"] for left,right in zip(a,a[1:]))
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--symbol",choices=ALTS)
 ap.add_argument("--combine",action="store_true")
 a=ap.parse_args()
 if a.combine:combine()
 elif a.symbol:calculate_asset(a.symbol)
 else:raise SystemExit("V76_ARGUMENTS_INVALID")
if __name__=="__main__":main()
