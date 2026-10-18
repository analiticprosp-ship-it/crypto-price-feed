#!/usr/bin/env python3
"""v7.3 preregistered unused retrospective chronological bridge; RESEARCH ONLY."""
import ast, hashlib, json, os, random, statistics, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
PREREG=ROOT/"research/detector_v73_prereg_2026-10-18.json"
PREREG_COMMIT="c47170b162b4ab672836a0295c48fb7a651ea09f"
SELECTED=("2025-10","2025-11","2025-12","2026-01")
REFERENCES=(
 ("6.9","research/detector/v6.9/runs/39107302260-1/comparison.json",
  "52c68895360938cf70f118a5465713f01e3391ce64bfb4ef2e613ef10c22524a",22),
 ("7.0","research/detector/v7.0/runs/39109768036-1/comparison.json",
  "7d4947d48e65aae303f3e927b1a9687cc140925cb2c739faa7899821a93a6eea",12),
)
SEED=730018
REPEATS=12000
HORIZONS=("4h","24h")

def digest(b):return hashlib.sha256(b).hexdigest()
def rounded(x):return round(x,6) if x is not None else None
def quantile(values,q):
 if not values:return None
 a=sorted(values);pos=(len(a)-1)*q;k=int(pos)
 return a[k]+(a[min(k+1,len(a)-1)]-a[k])*(pos-k)

# Import identical v6.8 replay/evaluation functions, never run a historical main.
v65=ast.parse((ROOT/"research/detector_matched_controls_v65.py").read_text())
keep=[n for n in v65.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.Assign,ast.FunctionDef))
      and not (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name)
      and t.id in ("s3","out") for t in n.targets))]
scope={"__file__":str(ROOT/"research/detector_matched_controls_v65.py")}
exec(compile(ast.Module(body=keep,type_ignores=[]),"<v65 definitions>","exec"),scope)
v68=ast.parse((ROOT/"research/detector_fixed_windows_v68.py").read_text())
functions=[n for n in v68.body if isinstance(n,ast.FunctionDef)
           and n.name in ("avg","rounded","percentile","analyze")]
scope.update(H={"4h":16,"24h":96},SEED=6808,datetime=datetime,timezone=timezone,
             random=random,statistics=statistics)
exec(compile(ast.Module(body=functions,type_ignores=[]),"<v68 definitions>","exec"),scope)
v69=ast.parse((ROOT/"research/detector_extension_v69.py").read_text())
aggregate_def=[n for n in v69.body if isinstance(n,ast.FunctionDef) and n.name=="aggregate"]
exec(compile(ast.Module(body=aggregate_def,type_ignores=[]),"<v69 aggregate>","exec"),scope)
read_month=scope["read_month"]
evaluate=scope["evaluate"]
regime=scope["regime"]
forward=scope["forward"]
analyze=scope["analyze"]
aggregate=scope["aggregate"]

def validate_prereg():
 raw=PREREG.read_bytes()
 doc=json.loads(raw)
 if (doc.get("version")!="7.3" or tuple(doc.get("months",[]))!=SELECTED
     or doc.get("mode")!="PREDECLARED_UNUSED_HISTORICAL_TIME_BLOCK"):
  raise SystemExit("V73_PREREG_INVALID")
 for version,key,sha,count in REFERENCES:
  p=doc["lockedSources"]["v"+version.replace(".","")]
  if p["key"]!=key or p["sha256"]!=sha:raise SystemExit("V73_PREREG_SOURCE_CHANGED")
 return digest(raw)

def events_and_regimes(bars,row):
 days={};total=0;any_sweep=set()
 for i in range(96,len(bars)-96):
  status,sweep=evaluate(bars,i)
  if status!="EARLY_CANDIDATE_SHADOW":continue
  total+=1
  day=datetime.fromtimestamp(bars[i]["t"]/1000,timezone.utc).date()
  if sweep:any_sweep.add(day)
  if day not in days:days[day]={"i":i,"sweep":bool(sweep),"regime":regime(bars,i)}
 check={"totalCandidates":total,"firstCandidates":len(days),
        "firstSweep":sum(e["sweep"] for e in days.values()),
        "daysWithSweep":len(any_sweep)}
 for k,v in check.items():
  if v!=row[k]:raise ValueError("REPLAY_PARITY:"+row["symbol"]+"/"+row["month"]+"/"+k)
 events=[]
 for day,item in sorted(days.items()):
  i=item["i"]
  events.append({"symbol":row["symbol"],"month":row["month"],"cohort":"temporal_bridge",
    "utcDay":day.isoformat(),"parity":day.toordinal()%2,"timestampMs":bars[i]["t"],
    "regime":item["regime"],"sweep":item["sweep"],
    "4h":forward(bars,i,16),"24h":forward(bars,i,96)})
 for h in HORIZONS:
  A=[e[h] for e in events if e["sweep"]]
  B=[e[h] for e in events if not e["sweep"]]
  old=row["firstCandidateComparison"]["horizons"][h]
  if (len(A),len(B))!=(old["groupA"],old["groupB"]):
   raise ValueError("V73_GROUP_COUNT_MISMATCH")
  if A and abs(statistics.mean(A)-old["meanA"])>0.00000051:
   raise ValueError("V73_A_RETURN_MISMATCH")
  if B and abs(statistics.mean(B)-old["meanB"])>0.00000051:
   raise ValueError("V73_B_RETURN_MISMATCH")
 return events

def event_effect(events,h):
 a=[e[h] for e in events if e["sweep"]]
 b=[e[h] for e in events if not e["sweep"]]
 return (statistics.mean(a)-statistics.mean(b)) if a and b else None

def bootstrap_months(rows,tag):
 cluster=defaultdict(list)
 for r in rows:cluster[r["month"]].append(r)
 months=sorted(cluster)
 if len(months)<2:raise SystemExit("V73_BOOTSTRAP_TOO_FEW_MONTHS:"+tag)
 baseline={h:aggregate(rows)[h]["differencePctPoints"] for h in HORIZONS}
 rng=random.Random(int(digest(f"{SEED}/{tag}".encode())[:16],16))
 draws={h:[] for h in HORIZONS}
 for _ in range(REPEATS):
  sample=[r for _ in months for r in cluster[months[rng.randrange(len(months))]]]
  stats=aggregate(sample)
  for h in HORIZONS:
   val=stats[h]["differencePctPoints"]
   if val is not None:draws[h].append(val)
 result={"monthClusters":len(months),"bootstrapDraws":{h:len(draws[h]) for h in HORIZONS}}
 for h in HORIZONS:
  if len(draws[h])<int(.95*REPEATS):raise SystemExit("V73_BOOTSTRAP_SPARSE:"+tag+"/"+h)
 result["horizons"]={h:{"effectPctPoints":baseline[h],
  "monthClusterPercentile95":[rounded(quantile(draws[h],.025)),
                             rounded(quantile(draws[h],.975))],
  "monthLeaveOneOut":[{"monthExcluded":month,
     "effectPctPoints":aggregate([r for r in rows if r["month"]!=month])[h]["differencePctPoints"]}
     for month in months]} for h in HORIZONS}
 return result

def count_overlap(events):
 total=0
 for symbol in ("BTC","ETH"):
  records=sorted((e for e in events if e["symbol"]==symbol),key=lambda x:x["timestampMs"])
  total+=sum(a["timestampMs"]+86400000>b["timestampMs"] for a,b in zip(records,records[1:]))
 return total

def secondary(events):
 assets={}
 for sym in ("BTC","ETH"):
  a=[x for x in events if x["symbol"]==sym]
  assets[sym]={"firstCandidates":len(a),"sweep":sum(x["sweep"] for x in a),
   "effectPctPoints":{h:rounded(event_effect(a,h)) for h in HORIZONS}}
 byregime={}
 for reg in ("UP","DOWN","SIDEWAYS"):
  a=[x for x in events if x["regime"]==reg]
  byregime[reg]={"firstCandidates":len(a),"sweep":sum(x["sweep"] for x in a),
   "effectPctPoints":{h:rounded(event_effect(a,h)) for h in HORIZONS}}
 phases={}
 for phase in (0,1):
  a=[x for x in events if x["parity"]==phase]
  overlaps=count_overlap(a)
  if overlaps:raise SystemExit("V73_PHASE_NONOVERLAP_FAILED")
  phases[str(phase)]={"n":len(a),"sweep":sum(x["sweep"] for x in a),
   "overlapPairs24h":0,"effectPctPoints":{h:rounded(event_effect(a,h)) for h in HORIZONS}}
 return {"assets":assets,"trailing24hRegime":byregime,
         "originalOverlapPairs24h":count_overlap(events),"nonOverlapUtcParity":phases}

def main():
 prereg_sha=validate_prereg()
 s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
 bucket=os.environ["R2_BUCKET"]
 previous=[];refs=[]
 for version,key,expected,n in REFERENCES:
  payload=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
  if digest(payload)!=expected:raise SystemExit("V73_REFERENCE_SHA_MISMATCH:"+version)
  doc=json.loads(payload)
  if doc.get("version")!=version or len(doc.get("results",[]))!=n:
   raise SystemExit("V73_REFERENCE_SHAPE_MISMATCH:"+version)
  previous.extend(doc["results"])
  refs.append({"version":version,"key":key,"sha256":expected})
 if len(previous)!=34 or len({(r["symbol"],r["month"]) for r in previous})!=34:
  raise SystemExit("V73_REFERENCE_DUPLICATES")
 oldmonths={r["month"] for r in previous}
 if oldmonths.intersection(SELECTED):raise SystemExit("V73_PREVIOUSLY_USED_MONTH")
 records=[];events=[];blocked=[]
 for symbol in ("BTC","ETH"):
  for month in SELECTED:
   try:
    bars,sha=read_month(s3,bucket,symbol,month)
    start=datetime.fromtimestamp(bars[0]["t"]/1000,timezone.utc)
    end=datetime.fromtimestamp(bars[-1]["endMs"]/1000,timezone.utc)
    y,m=map(int,month.split("-"))
    nextmonth=f"{y+1}-01" if m==12 else f"{y}-{m+1:02d}"
    if (start!=datetime.fromisoformat(month+"-01").replace(tzinfo=timezone.utc)
        or end!=datetime.fromisoformat(nextmonth+"-01").replace(tzinfo=timezone.utc)):
     raise ValueError("SOURCE_PARTIAL_MONTH")
    rec={"symbol":symbol,"month":month,"cohort":"temporal_bridge",
         "sourceSha256":sha,**analyze(bars),"status":"RESEARCH_PASS"}
    month_events=events_and_regimes(bars,rec)
    records.append(rec);events.extend(month_events)
   except Exception as e:
    blocked.append({"symbol":symbol,"month":month,"error":type(e).__name__+":"+str(e)[:180]})
 folder=Path("detector_v73_reports");folder.mkdir(exist_ok=True)
 if blocked or len(records)!=8:
  (folder/"blocked.json").write_text(json.dumps({"status":"V73_SOURCE_OR_REPLAY_BLOCKED",
    "preregisteredMonths":SELECTED,"errors":blocked},indent=2))
  raise SystemExit("V73_SOURCE_OR_REPLAY_BLOCKED "+json.dumps(blocked))
 groups={name:[r for r in previous if r["cohort"]==name]
         for name in ("baseline","extension","holdout")}
 if [len(groups[n]) for n in ("baseline","extension","holdout")]!=[10,12,12]:
  raise SystemExit("V73_COHORT_COUNTS_CHANGED")
 groups["temporal_bridge"]=records
 groups["all_previous"]=previous
 groups["all_with_bridge"]=previous+records
 summaries={name:aggregate(rows) for name,rows in groups.items()}
 intervals={name:bootstrap_months(rows,name) for name,rows in groups.items()}
 second=secondary(events)
 eventbytes=json.dumps(events,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
 (folder/"events.json").write_bytes(eventbytes)
 report={"version":"7.3","researchOnly":True,"tradesEmitted":0,
  "originalLiveDetectorParity":"NOT_ESTABLISHED",
  "status":"HISTORICAL_CHRONOLOGICAL_BRIDGE_RESEARCH_ONLY",
  "preregistration":{"path":str(PREREG.relative_to(ROOT)),
    "commit":PREREG_COMMIT,"sha256":prereg_sha,"fixedMonths":SELECTED},
  "references":refs,"source":"Binance USD-M Futures 5m BTC ETH full calendar monthly archives",
  "records":records,"comparison":summaries,"clusterUncertainty":intervals,
  "secondary":second,"eventCount":len(events),"eventSha256":digest(eventbytes),
  "limitations":["Retrospective unused historical interval, NOT actual forward prospective data",
   "Only four shared calendar months; bootstrap approximate and wide",
   "Adjacent calendar months and BTC/ETH remain statistically related",
   "UTC parity is a post-hoc robustness check, not independent replication",
   "Regime stratification is descriptive and underpowered",
   "No execution, fees, slippage, funding, OI, causality, or live parity",
   "Cannot promote to trading authority on the basis of this report"]}
 raw=json.dumps(report,indent=2,ensure_ascii=False).encode()
 (folder/"comparison.json").write_bytes(raw)
 prefix=f"research/detector/v7.3/runs/{os.getenv('GITHUB_RUN_ID','manual')}-{os.getenv('GITHUB_RUN_ATTEMPT','1')}/"
 manifest={"version":"7.3","status":"HISTORICAL_RESEARCH_PASS","researchOnly":True,
   "reportSha256":digest(raw),"eventSha256":digest(eventbytes),
   "preregistrationSha256":prereg_sha,"prefix":prefix,"githubSha":os.getenv("GITHUB_SHA")}
 (folder/"manifest.json").write_text(json.dumps(manifest,indent=2))
 for name in ("comparison.json","events.json","manifest.json"):
  blob=(folder/name).read_bytes()
  key=prefix+name
  s3.put_object(Bucket=bucket,Key=key,Body=blob,ContentType="application/json",
   Metadata={"sha256":digest(blob),"research-only":"true"})
  if digest(s3.get_object(Bucket=bucket,Key=key)["Body"].read())!=digest(blob):
   raise SystemExit("V73_R2_WRITEBACK_VERIFICATION_FAILED:"+name)
 summary={"status":"V73_RESEARCH_PASS_WRITEBACK_VERIFIED","run":os.getenv("GITHUB_RUN_ID"),
  "prefix":prefix,"reportSha256":digest(raw),"preregSha256":prereg_sha,
  "months":SELECTED,"comparison":summaries,"secondary":second,
  "bridgeMonthBootstrap":intervals["temporal_bridge"],
  "allMonthBootstrap":intervals["all_with_bridge"]}
 print(json.dumps(summary,ensure_ascii=False),flush=True)
 lines=["# Detector v7.3 — фиксированный неиспользованный исторический блок","",
  "Статус: V73_RESEARCH_PASS_WRITEBACK_VERIFIED","",
  "Пререгистрация: "+PREREG_COMMIT,"","R2: "+prefix,"",
  "SHA-256: "+digest(raw),"",
  "| Группа | Символ-месяцев | LONG | Sweep среди первых | Δ4h п.п. | Δ24h п.п. |",
  "|---|---:|---:|---:|---:|---:|"]
 for name in ("baseline","extension","holdout","temporal_bridge","all_previous","all_with_bridge"):
  z=summaries[name]
  lines.append("| "+name+" | "+str(z["months"])+" | "+str(z["candidates"])
   +" | "+str(z["firstSweep"])+" | "+str(z["4h"]["differencePctPoints"])
   +" | "+str(z["24h"]["differencePctPoints"])+" |")
 lines.append("\nРетроспективный анализ, не доказательство торгового преимущества.")
 md="\n".join(lines)+"\n"
 (folder/"summary.md").write_text(md)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:f.write(md)
if __name__=="__main__":main()
