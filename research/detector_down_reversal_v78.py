#!/usr/bin/env python3
"""Detector v7.8 — exploratory conditional Sweep after decline, archived first LONG/day.
Historical Binance USD-M 5m inputs. Research-only; no live signals or portfolio writes.
"""
import argparse,ast,hashlib,json,os,random,statistics,sys
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import boto3

ASSETS=("BTC","ETH","SOL","BNB","LINK","XRP","ADA","DOGE")
H=("1h","2h","4h")
DAYS=96
CONDITIONS=("DOWN_ALL","DOWN_MILD","DOWN_DEEP","DOWN_HIGH_VOLUME",
            "DOWN_BUY_DOMINANT","DOWN_HIGH_VOLUME_AND_BUY_DOMINANT")
REFERENCE="research/detector/v7.7/runs/39121256508-1/combined/comparison.json"
EXPECTED_SHA="cd8ad2853a78991891e8b74134d908d5326f0a0ddb41af1c059e2aab4fd17a7a"
PREREG="research/detector_v78_down_reversal_prereg_2026-10-18.json"
PREREG_COMMIT="62c286f900992d841643ab288f789ba0fd07dcfd"
BOOTSTRAPS=12000
SEED=780018

def sha(blob):return hashlib.sha256(blob).hexdigest()
def rnd(x):return round(float(x),6) if x is not None else None
def qnt(xs,p):
 xs=sorted(xs)
 pidx=(len(xs)-1)*p;lo=int(pidx)
 return xs[lo]+(xs[min(lo+1,len(xs)-1)]-xs[lo])*(pidx-lo)
def get_client():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def prefix():
 return f"research/detector/v7.8/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
def get(s3,bucket,key,digest):
 raw=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
 if sha(raw)!=digest:raise SystemExit("V78_SHA_MISMATCH:"+key)
 return json.loads(raw)
def put(s3,bucket,key,value):
 blob=value if isinstance(value,bytes) else json.dumps(value,indent=2,ensure_ascii=False).encode()
 h=sha(blob)
 s3.put_object(Bucket=bucket,Key=key,Body=blob,ContentType="application/json",
   Metadata={"sha256":h,"research-only":"true"})
 if sha(s3.get_object(Bucket=bucket,Key=key)["Body"].read())!=h:
  raise SystemExit("V78_WRITEBACK_FAILED:"+key)
 return h
def prereg():
 raw=(ROOT/PREREG).read_bytes();doc=json.loads(raw)
 if (doc["version"]!="7.8" or doc["assets"]!=list(ASSETS)
   or doc["immutableEventRef"]!={"key":REFERENCE,"sha256":EXPECTED_SHA}
   or tuple(doc["frozenConditions"])!=CONDITIONS):
  raise SystemExit("V78_PREREG_CHANGED")
 return sha(raw)
def source_v77(s3,bucket):
 doc=get(s3,bucket,REFERENCE,EXPECTED_SHA)
 if (doc["version"]!="7.7" or doc["assetMonths"]!=623
  or doc["firstLongEvents"]!=17678 or doc["firstSweepEvents"]!=3439):
  raise SystemExit("V78_V77_SHAPE_CHANGED")
 return doc
def immutable_archive_hashes(s3,bucket,v77,sym):
 # Exactly the original 5-minute source SHA-256 hashes from v7.5/v7.6;
 # reject any changed archive even when a few selected returns coincidentally match.
 if sym in ("BTC","ETH"):
  key,digest=v77["sourceReports"]["core"]
  base=get(s3,bucket,key,digest)
  rows=[]
  for year in base["sourceYears"]:
   rows.extend(get(s3,bucket,year["prefix"]+"records.json",year["recordsSha256"]))
 else:
  key,digest=v77["sourceReports"]["alts"]
  base=get(s3,bucket,key,digest)
  asset=next(x for x in base["sources"] if x["symbol"]==sym)
  rows=get(s3,bucket,asset["prefix"]+"records.json",asset["recordsSha256"])
 matched={row["month"]:row["sourceSha256"] for row in rows if row["symbol"]==sym}
 if len(matched)!=v77["assets"][sym]["monthCount"]:
  raise SystemExit("V78_ARCHIVE_SOURCE_MONTH_COUNT_CHANGED")
 return matched

def bars_reader():
 tree=ast.parse((ROOT/"research/detector_matched_controls_v65.py").read_text())
 f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="read_month")
 import csv,io,zipfile
 ns={"hashlib":hashlib,"csv":csv,"io":io,"zipfile":zipfile,"P5":300000}
 exec(compile(ast.Module(body=[f],type_ignores=[]),"<read_month>","exec"),ns)
 return ns["read_month"]
def first_events(s3,bucket,doc,sym):
 x=next((r for r in doc["assetSourceManifests"] if r["symbol"]==sym),None)
 if not x:raise SystemExit("V78_NO_SOURCE_ASSET")
 events=get(s3,bucket,x["prefix"]+"events.json",x["eventsSha256"])
 months=get(s3,bucket,x["prefix"]+"months.json",x["monthsSha256"])
 if len(months)!=doc["assets"][sym]["monthCount"]:
  raise SystemExit("V78_SOURCE_MONTH_COUNT_CHANGED")
 if sum(m["firstLong"] for m in months)!=len(events):raise SystemExit("V78_SOURCE_EVENT_COUNT_CHANGED")
 return months,events

def classify(fall,volume_ratio,buy_frac):
 # The original v7.7 regime is calculated separately and checked.
 down=fall< -1.0
 severity="DEEP" if fall<=-3.0 else "MILD"
 high_volume=volume_ratio is not None and volume_ratio>=1.50
 buy_dom=buy_frac is not None and buy_frac>=.55
 return {"fallPct":rnd(fall),"severity":severity if down else "NOT_DOWN",
  "volumeRatio":rnd(volume_ratio),"buyFraction":rnd(buy_frac),
  "volumeHigh":high_volume if volume_ratio is not None else None,
  "buyDominant":buy_dom if buy_frac is not None else None,
  "conditions":[c for c,ok in (
   ("DOWN_ALL",down),("DOWN_MILD",down and severity=="MILD"),
   ("DOWN_DEEP",down and severity=="DEEP"),
   ("DOWN_HIGH_VOLUME",down and high_volume),
   ("DOWN_BUY_DOMINANT",down and buy_dom),
   ("DOWN_HIGH_VOLUME_AND_BUY_DOMINANT",down and high_volume and buy_dom))
   if ok]}

def cell(sym,month,cond,events):
 row={"symbol":sym,"month":month,"condition":cond,
  "firstLong":len(events),"firstSweep":sum(bool(e["sweep"]) for e in events),
  "missingVolumeRatio":sum(e["volumeRatio"] is None for e in events),
  "missingBuyFraction":sum(e["buyFraction"] is None for e in events)}
 for h in H:
  a=[e[h] for e in events if e["sweep"]]
  b=[e[h] for e in events if not e["sweep"]]
  row[h]={"groupA":len(a),"groupB":len(b),
    "meanA":rnd(statistics.mean(a)) if a else None,
    "meanB":rnd(statistics.mean(b)) if b else None,
    "positiveA":sum(v>0 for v in a),"positiveB":sum(v>0 for v in b),
    "differencePctPoints":rnd(statistics.mean(a)-statistics.mean(b)) if a and b else None}
 return row
def agg(rows,h):
 left_n=right_n=0;left_sum=right_sum=0.0
 win_a=win_b=0;pos=neg=both=0
 for row in rows:
  data=row[h]
  a=data["groupA"];b=data["groupB"]
  if a and b:
   both+=1;left_n+=a;right_n+=b
   left_sum+=a*data["meanA"];right_sum+=b*data["meanB"]
   win_a+=data["positiveA"];win_b+=data["positiveB"]
   d=data["differencePctPoints"]
   pos+=d>0;neg+=d<0
 return {"nSweep":left_n,"nNonSweep":right_n,"comparableSymbolMonths":both,
  "symbolMonthsPositive":pos,"symbolMonthsNegative":neg,
  "differencePctPoints":rnd(left_sum/left_n-right_sum/right_n) if left_n and right_n else None,
  "sweepPositiveRatePct":rnd(win_a*100/left_n) if left_n else None,
  "nonSweepPositiveRatePct":rnd(win_b*100/right_n) if right_n else None}
def summarize(rows):
 return {h:agg(rows,h) for h in H}
def zero_support(rows):
 return {"events":sum(x["firstLong"] for x in rows),
   "sweep":sum(x["firstSweep"] for x in rows),
   "monthsWithAnyEvents":sum(x["firstLong"]>0 for x in rows)}

def calculate(sym):
 prereg_sha=prereg()
 s3=get_client();bucket=os.environ["R2_BUCKET"];doc=source_v77(s3,bucket)
 months,events=first_events(s3,bucket,doc,sym)
 original_archive_sha=immutable_archive_hashes(s3,bucket,doc,sym)
 read_month=bars_reader()
 bymonth=defaultdict(list)
 for e in events:bymonth[e["month"]].append(e)
 transformed=[];table=[];errors=[]
 for row in months:
  m=row["month"];current=bymonth[m]
  try:
   bars,archive_sha=read_month(s3,bucket,sym,m)
   if archive_sha!=original_archive_sha.get(m):raise ValueError("ARCHIVE_SHA_CHANGED")
   # The archived v7.7 source checks 5m ZIP sha, CRC, OHLCV, gaplessness;
   # original v7.7 also checked UTC full-month boundary.
   start=datetime.fromtimestamp(bars[0]["t"]/1000,timezone.utc)
   end=datetime.fromtimestamp(bars[-1]["endMs"]/1000,timezone.utc)
   y,mo=map(int,m.split("-"))
   next_month=f"{y+1}-01" if mo==12 else f"{y}-{mo+1:02d}"
   if start!=datetime.fromisoformat(m+"-01").replace(tzinfo=timezone.utc) or end!=datetime.fromisoformat(next_month+"-01").replace(tzinfo=timezone.utc):
    raise ValueError("MONTH_NOT_COMPLETE")
   positions={bar["t"]:i for i,bar in enumerate(bars)}
   for e in current:
    ts=e["timestampMs"]
    if ts not in positions:raise ValueError("EVENT_TIMESTAMP_MISSING")
    i=positions[ts]
    if i<96 or i+96>=len(bars):raise ValueError("EVENT_EDGE_INVALID")
    original={h:100*(bars[i+steps]["c"]/bars[i]["c"]-1) for h,steps in (("1h",4),("2h",8),("4h",16))}
    if any(abs(original[h]-e[h])>1e-9 for h in H):raise ValueError("FROZEN_RETURN_MISMATCH")
    trailing=100*(bars[i]["c"]/bars[i-96]["c"]-1)
    expected="UP" if trailing>1 else ("DOWN" if trailing< -1 else "SIDEWAYS")
    if e["regime"]!=expected:raise ValueError("FROZEN_REGIME_MISMATCH")
    trailing_vols=[b["v"] for b in bars[i-96:i]]
    median=statistics.median(trailing_vols)
    volratio=bars[i]["v"]/median if median>0 else None
    frac=bars[i]["buy"]/bars[i]["v"] if bars[i]["v"]>0 else None
    classification=classify(trailing,volratio,frac)
    transformed.append({**e,**classification})
   subset=[e for e in transformed if e["month"]==m]
   if (len(subset)!=row["firstLong"]
    or sum(e["sweep"] for e in subset)!=row["firstSweep"]):
    raise ValueError("SOURCE_COUNTS_CHANGED")
   for h in H:
    a=[e[h] for e in subset if e["sweep"]]
    b=[e[h] for e in subset if not e["sweep"]]
    orig=row[h]
    if ((len(a),len(b))!=(orig["groupA"],orig["groupB"])
     or (a and abs(statistics.mean(a)-orig["meanA"])>0.00000051)
     or (b and abs(statistics.mean(b)-orig["meanB"])>0.00000051)):
     raise ValueError("FROZEN_MEANS_CHANGED")
   for cond in CONDITIONS:
    events_here=[e for e in subset if cond in e["conditions"]]
    table.append(cell(sym,m,cond,events_here))
  except Exception as exc:
   errors.append({"symbol":sym,"month":m,"reason":type(exc).__name__+":"+str(exc)[:150]})
 if errors:
  print("V78_ASSET_BLOCKED "+json.dumps(errors,ensure_ascii=False),flush=True)
  raise SystemExit("V78_SOURCE_REPLAY_BLOCKED")
 if len(table)!=len(months)*len(CONDITIONS):
  raise SystemExit("V78_ROW_COUNT_MISMATCH")
 down=[e for e in transformed if "DOWN_ALL" in e["conditions"]]
 comparison=doc["perAssetRegimes"][sym]["DOWN"]
 if len(down)!=comparison["n"] or sum(x["sweep"] for x in down)!=comparison["nSweep"]:
  raise SystemExit("V78_DOWN_PARITY_CHANGED")
 for h in H:
  left=[e[h] for e in down if e["sweep"]]
  right=[e[h] for e in down if not e["sweep"]]
  diff=rnd(statistics.mean(left)-statistics.mean(right))
  if diff!=comparison["effects"][h]:raise SystemExit("V78_ORIGINAL_DOWN_DIFFERENCE_MISMATCH")
 root=prefix()+f"assets/{sym}/"
 cells_sha=put(s3,bucket,root+"cells.json",table)
 ev_sha=put(s3,bucket,root+"events.json",transformed)
 meta={"version":"7.8","researchOnly":True,"symbol":sym,
  "sourceV77":EXPECTED_SHA,"preregSha256":prereg_sha,
  "cellsSha256":cells_sha,"eventsSha256":ev_sha,
  "months":len(months),"firstLong":len(events),"downEvents":len(down),
  "downSweep":sum(x["sweep"] for x in down),"prefix":root,
  "githubSha":os.environ.get("GITHUB_SHA")}
 meta_sha=put(s3,bucket,root+"manifest.json",meta)
 folder=Path("detector_v78_reports");folder.mkdir(exist_ok=True)
 brief={"status":"V78_ASSET_RESEARCH_PASS_WRITEBACK_VERIFIED","asset":sym,
  "months":len(months),"events":len(events),"downEvents":len(down),
  "downSweep":sum(x["sweep"] for x in down),"down":summarize([r for r in table if r["condition"]=="DOWN_ALL"]),
  "manifestSha256":meta_sha}
 (folder/(sym+".json")).write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print(json.dumps(brief,ensure_ascii=False),flush=True)

def sim_down(rows):
 import numpy as np
 quarters=sorted({r["month"][:4]+"Q"+str((int(r["month"][5:])-1)//3+1) for r in rows})
 if len(quarters)!=27:raise SystemExit("V78_WRONG_CALENDAR_COVERAGE")
 keys={(sym,h):j for j,(sym,h) in enumerate((s,h) for s in ASSETS for h in H)}
 qi={v:i for i,v in enumerate(quarters)}
 shape=(len(quarters),len(keys))
 NA=np.zeros(shape);NB=np.zeros(shape);SA=np.zeros(shape);SB=np.zeros(shape)
 for row in rows:
  k=qi[row["month"][:4]+"Q"+str((int(row["month"][5:])-1)//3+1)]
  for h in H:
   d=row[h]
   if d["groupA"]>0 and d["groupB"]>0:
    i=keys[(row["symbol"],h)]
    NA[k,i]+=d["groupA"];NB[k,i]+=d["groupB"]
    SA[k,i]+=d["groupA"]*d["meanA"];SB[k,i]+=d["groupB"]*d["meanB"]
 if np.any(NA.sum(axis=0)<=0) or np.any(NB.sum(axis=0)<=0):
  raise SystemExit("V78_BOOTSTRAP_EMPTY_ASSET")
 baseline=SA.sum(axis=0)/NA.sum(axis=0)-SB.sum(axis=0)/NB.sum(axis=0)
 rng=np.random.default_rng(SEED)
 draws=np.zeros((BOOTSTRAPS,len(quarters)))
 for i in range(BOOTSTRAPS):
  draws[i]=np.bincount(rng.integers(len(quarters),size=len(quarters)),minlength=len(quarters))
 nA=draws@NA;nB=draws@NB
 if (nA<=0).any() or (nB<=0).any():
  raise SystemExit("V78_BOOTSTRAP_RANDOM_EMPTY")
 diffs=(draws@SA)/nA-(draws@SB)/nB
 sdev=diffs.std(axis=0)
 if (sdev<=0).any():raise SystemExit("V78_BOOTSTRAP_ZERO_VARIANCE")
 critical=np.quantile(np.max(np.abs((diffs-baseline)/sdev),axis=1),.95)
 result={}
 for (sym,h),i in keys.items():
  low=baseline[i]-critical*sdev[i];high=baseline[i]+critical*sdev[i]
  result.setdefault(sym,{})[h]={"effectPctPoints":rnd(baseline[i]),
   "percentile95":[rnd(np.quantile(diffs[:,i],.025)),rnd(np.quantile(diffs[:,i],.975))],
   "familywiseSimultaneous95":[rnd(low),rnd(high)],
   "adjustedLowerAboveZero":bool(low>0)}
 return {"quarterClusters":len(quarters),"draws":BOOTSTRAPS,"seed":SEED,
  "family":"8 assets x 3 horizons DOWN_ALL (24 tests)",
  "maxT95":rnd(critical),"assets":result}

def combine():
 prereg_sha=prereg();s3=get_client();bucket=os.environ["R2_BUCKET"]
 orig=source_v77(s3,bucket)
 allrows=[];events=[];sources=[]
 for sym in ASSETS:
  root=prefix()+f"assets/{sym}/"
  meta=json.loads(s3.get_object(Bucket=bucket,Key=root+"manifest.json")["Body"].read())
  if meta["version"]!="7.8" or meta["symbol"]!=sym or meta["preregSha256"]!=prereg_sha:
   raise SystemExit("V78_ASSET_MANIFEST_MISMATCH")
  rows=get(s3,bucket,root+"cells.json",meta["cellsSha256"])
  evs=get(s3,bucket,root+"events.json",meta["eventsSha256"])
  if len(rows)!=orig["assets"][sym]["monthCount"]*len(CONDITIONS) or len(evs)!=meta["firstLong"]:
   raise SystemExit("V78_ASSET_COUNT_MISMATCH")
  allrows+=rows;events+=evs
  sources.append({"asset":sym,"prefix":root,"cellsSha256":meta["cellsSha256"],
    "eventsSha256":meta["eventsSha256"]})
 if len(allrows)!=623*len(CONDITIONS) or len(events)!=17678 or sum(x["sweep"] for x in events)!=3439:
  raise SystemExit("V78_GLOBAL_COUNTS_CHANGED")
 down_rows=[r for r in allrows if r["condition"]=="DOWN_ALL"]
 if len(down_rows)!=623:raise SystemExit("V78_MISSING_DOWN_CELLS")
 down_events=[e for e in events if "DOWN_ALL" in e["conditions"]]
 if len(down_events)!=orig["regimes"]["DOWN"]["n"] or sum(x["sweep"] for x in down_events)!=orig["regimes"]["DOWN"]["nSweep"]:
  raise SystemExit("V78_DOWN_SOURCE_COUNT_CHANGED")
 for h in H:
  left=[e[h] for e in down_events if e["sweep"]]
  right=[e[h] for e in down_events if not e["sweep"]]
  if rnd(statistics.mean(left)-statistics.mean(right))!=orig["regimes"]["DOWN"]["effects"][h]:
   raise SystemExit("V78_DOWN_ORIGINAL_POOLED_EFFECT_CHANGED")
 boot=sim_down(down_rows)
 summaries={};recommend={}
 for cond in CONDITIONS:
  data=[r for r in allrows if r["condition"]==cond]
  summaries[cond]={"total":summarize(data),
   "support":zero_support(data),
   "byEra":{name:{"effects":summarize([r for r in data if (r["month"]<"2024-01")==(name=="2020-2023")]),
                    "support":zero_support([r for r in data if (r["month"]<"2024-01")==(name=="2020-2023")])}
            for name in ("2020-2023","2024-2026")},
   "byAsset":{sym:{"effects":summarize([r for r in data if r["symbol"]==sym]),
                   "eraEffects":{era:summarize([r for r in data if r["symbol"]==sym and
                     (r["month"]<"2024-01")==(era=="2020-2023")])
                    for era in ("2020-2023","2024-2026")}}
              for sym in ASSETS}}
 for sym in ASSETS:
  s=[r for r in down_rows if r["symbol"]==sym]
  byyear={str(y):summarize([r for r in s if r["month"].startswith(str(y))]) for y in range(2020,2027)}
  e1=summarize([r for r in s if r["month"]<"2024-01"])
  e2=summarize([r for r in s if r["month"]>="2024-01"])
  for h in H:
   positive=sum(x[h]["differencePctPoints"] is not None and x[h]["differencePctPoints"]>0 for x in byyear.values())
   years=sum(x[h]["differencePctPoints"] is not None for x in byyear.values())
   both=e1[h]["differencePctPoints"] is not None and e1[h]["differencePctPoints"]>0 and e2[h]["differencePctPoints"] is not None and e2[h]["differencePctPoints"]>0
   adj=boot["assets"][sym][h]["adjustedLowerAboveZero"]
   good=years==7 and positive>=5 and both and adj
   recommend.setdefault(sym,{})[h]={"classification":"PROSPECTIVE_CANDIDATE_ONLY" if good else "UNSTABLE_OR_INCONCLUSIVE",
    "positiveYears":positive,"eligibleYears":years,
    "bothErasPositive":bool(both),"adjusted95LowerAboveZero":adj,
    "years":byyear}
 severity={}
 for c in CONDITIONS:
  counts={}
  for era in ("2020-2023","2024-2026"):
   sub=[r for r in allrows if r["condition"]==c and (r["month"]<"2024-01")== (era=="2020-2023")]
   counts[era]={h:{"nSweepComparable":agg(sub,h)["nSweep"],
                    "nNonSweepComparable":agg(sub,h)["nNonSweep"],
                    "lowSupport":agg(sub,h)["nSweep"]<30 or agg(sub,h)["nNonSweep"]<30}
                for h in H}
  severity[c]=counts
 report={"version":"7.8","status":"POST_HOC_DOWN_SWEEP_CONDITIONAL_RESEARCH_ONLY",
  "researchOnly":True,"tradesEmitted":0,"originalLiveDetectorParity":"NOT_ESTABLISHED",
  "prereg":{"path":PREREG,"commit":PREREG_COMMIT,"sha256":prereg_sha},
  "sourceV77":{"key":REFERENCE,"sha256":EXPECTED_SHA},"sourceAssets":sources,
  "period":"2020-01..2026-09","assetMonths":623,"firstLongEvents":len(events),
  "firstSweepEvents":sum(x["sweep"] for x in events),
  "fallingRegimeN":len(down_events),"fallingRegimeSweepN":sum(x["sweep"] for x in down_events),
  "comparison":"Within asset + month + frozen DOWN + fixed feature condition; if a or b absent exclude entire cell from effect aggregation",
  "conditions":summaries,"supportByEra":severity,
  "adjustedBootstrapDownAll":boot,"historicalGates":recommend,
  "importantCaveats":[
   "Exploratory hypothesis was selected after inspecting v7.7 outcome; not a blind out-of-sample result",
   "Performance differences do not prove price reversal or profitable execution",
   "Day-first status selection is unchanged and may not match a live tradeable signal",
   "Buy imbalance uses taker BUY volume of closed candle; 15m volume ratio compares against previous 24h median",
   "Multi-condition and regime searches inflate multiple testing: max-t only covers DOWN_ALL 24 tests, not diagnostics",
   "One month with absent Sweep or control excludes that cell, creating conditional composition dependence",
   "Differences between eras are descriptive, not proven effect of ETF, liquidity or institutions",
   "Historical liquid surviving assets are not a representative universe; fees, slippage, funding absent",
   "No Futures or portfolio changes, no live trading authority"
  ]}
 folder=Path("detector_v78_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(report,indent=2,ensure_ascii=False).encode()
 (folder/"comparison.json").write_bytes(raw)
 root=prefix()+"combined/"
 report_sha=put(s3,bucket,root+"comparison.json",raw)
 manifest_sha=put(s3,bucket,root+"manifest.json",{"version":"7.8","status":"CONDITIONAL_RESEARCH_PASS",
   "researchOnly":True,"reportSha256":report_sha,
   "preregSha256":prereg_sha,"prefix":root})
 brief={"status":"V78_DOWN_REVERSAL_RESEARCH_PASS_WRITEBACK_VERIFIED",
  "reportSha256":report_sha,"manifestSha256":manifest_sha,"prefix":root,
  "events":len(events),"downEvents":len(down_events),"downSweep":sum(x["sweep"] for x in down_events),
  "conditionalSummary":{cond:{"total":res["total"],"byEra":res["byEra"],
    "byAsset":{s:res["byAsset"][s]["effects"] for s in ASSETS}} for cond,res in summaries.items()},
  "adjustedDownAll":boot,"gates":{s:{h:{k:v for k,v in k1.items() if k!="years"}
    for h,k1 in rec.items()} for s,rec in recommend.items()},"support":severity}
 (folder/"summary.json").write_text(json.dumps(brief,indent=2,ensure_ascii=False))
 print("V78_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  lines=["# Detector v7.8 — Sweep после снижения на 1–4 часа","","Статус: V78_DOWN_REVERSAL_RESEARCH_PASS_WRITEBACK_VERIFIED","",
   "Это post-hoc историческое исследование, не торговые сигналы.","",
   "R2: "+root,"","SHA-256: "+report_sha,"",
   "| Условие | Δ1h п.п. | Δ2h п.п. | Δ4h п.п. |",
   "|---|---:|---:|---:|"]
  for c,r in summaries.items():
   lines.append(f"| {c} | {r['total']['1h']['differencePctPoints']} | {r['total']['2h']['differencePctPoints']} | {r['total']['4h']['differencePctPoints']} |")
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:f.write("\n".join(lines)+"\n")

def main():
 parser=argparse.ArgumentParser();parser.add_argument("--asset",choices=ASSETS)
 parser.add_argument("--combine",action="store_true")
 args=parser.parse_args()
 if args.asset:calculate(args.asset)
 elif args.combine:combine()
 else:raise SystemExit("V78_INVALID_ARGUMENTS")
if __name__=="__main__":main()
