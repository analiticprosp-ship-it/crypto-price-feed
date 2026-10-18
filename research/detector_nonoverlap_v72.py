#!/usr/bin/env python3
"""Post-hoc Detector v7.2: first-LONG event reconstruction and disjoint 24h phase test.
Historical research only. Does not alter live Detector, Futures, NAV or portfolio.
"""
import ast, hashlib, json, os, random, statistics, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
tree=ast.parse((ROOT/"research/detector_matched_controls_v65.py").read_text())
keep=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.Assign,ast.FunctionDef))
      and not (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ("s3","out") for t in n.targets))]
ns={"__file__":str(ROOT/"research/detector_matched_controls_v65.py")}
exec(compile(ast.Module(body=keep,type_ignores=[]),"<v65 definitions>","exec"),ns)
read_month,evaluate,forward=(ns[x] for x in ("read_month","evaluate","forward"))
SOURCES=[
 ("6.9","research/detector/v6.9/runs/39107302260-1/comparison.json",
  "52c68895360938cf70f118a5465713f01e3391ce64bfb4ef2e613ef10c22524a",22),
 ("7.0","research/detector/v7.0/runs/39109768036-1/comparison.json",
  "7d4947d48e65aae303f3e927b1a9687cc140925cb2c739faa7899821a93a6eea",12)]
H={"4h":16,"24h":96}
SEED=720018
REPEATS=6000
def sha(data):return hashlib.sha256(data).hexdigest()
def rnd(x):return round(x,6) if x is not None else None
def quantile(data,p):
 s=sorted(data);v=(len(s)-1)*p;k=int(v)
 return s[k]+(s[min(k+1,len(s)-1)]-s[k])*(v-k)

def events_for(s3,bucket,source):
 sym,month=source["symbol"],source["month"]
 bars,source_sha=read_month(s3,bucket,sym,month)
 if source_sha!=source["sourceSha256"]:raise ValueError("SOURCE_SHA_CHANGED")
 y,m=map(int,month.split("-"))
 after=f"{y+1}-01" if m==12 else f"{y}-{m+1:02d}"
 if (datetime.fromtimestamp(bars[0]["t"]/1000,timezone.utc).isoformat()[:10]!=month+"-01"
     or datetime.fromtimestamp(bars[-1]["endMs"]/1000,timezone.utc).isoformat()[:10]!=after+"-01"):
  raise ValueError("SOURCE_PARTIAL_MONTH")
 first={};total=0;sweep_days=set()
 for i in range(96,len(bars)-96):
  status,sweep=evaluate(bars,i)
  if status!="EARLY_CANDIDATE_SHADOW":continue
  total+=1
  day=datetime.fromtimestamp(bars[i]["t"]/1000,timezone.utc).date()
  if sweep:sweep_days.add(day)
  if day not in first:first[day]=(i,bool(sweep))
 audit={"totalCandidates":total,"firstCandidates":len(first),
        "firstSweep":sum(s for i,s in first.values()),"daysWithSweep":len(sweep_days)}
 for name,v in audit.items():
  if source[name]!=v:raise ValueError("ORIGINAL_COUNT_MISMATCH:"+sym+month+name)
 events=[]
 for day,(i,sweep) in sorted(first.items()):
  events.append({"symbol":sym,"month":month,"cohort":source["cohort"],
   "utcDay":day.isoformat(),"phase":day.toordinal()%2,"timestampMs":bars[i]["t"],
   "sweep":sweep,"4h":forward(bars,i,16),"24h":forward(bars,i,96)})
 for h in H:
  a=[e[h] for e in events if e["sweep"]]
  b=[e[h] for e in events if not e["sweep"]]
  ref=source["firstCandidateComparison"]["horizons"][h]
  if (len(a),len(b))!=(ref["groupA"],ref["groupB"]):raise ValueError("ORIGINAL_GROUP_MISMATCH")
  if a and abs(statistics.mean(a)-ref["meanA"])>0.00000051:raise ValueError("ORIGINAL_MEAN_A_MISMATCH")
  if b and abs(statistics.mean(b)-ref["meanB"])>0.00000051:raise ValueError("ORIGINAL_MEAN_B_MISMATCH")
 return events

def estimate(data,h):
 a=[e[h] for e in data if e["sweep"]]
 b=[e[h] for e in data if not e["sweep"]]
 return statistics.mean(a)-statistics.mean(b) if a and b else None

def overlaps(data):
 count=0
 for symbol in ("BTC","ETH"):
  ev=sorted((x for x in data if x["symbol"]==symbol),key=lambda x:x["timestampMs"])
  count+=sum(a["timestampMs"]+86400000>b["timestampMs"] for a,b in zip(ev,ev[1:]))
 return count

def phase_audit(events,tag,phase):
 selected=[e for e in events if e["phase"]==phase]
 groups=defaultdict(list)
 for e in selected:groups[e["month"]].append(e)
 months=sorted(groups)
 observed={h:estimate(selected,h) for h in H}
 if len(months)<2 or any(v is None for v in observed.values()):raise ValueError("PHASE_MISSING_GROUPS:"+tag)
 rng=random.Random(int(sha(f"{SEED}/{tag}/{phase}".encode())[:16],16))
 drawn={h:[] for h in H}
 for _ in range(REPEATS):
  sample=[e for _ in months for e in groups[months[rng.randrange(len(months))]]]
  vals={h:estimate(sample,h) for h in H}
  if any(v is None for v in vals.values()):continue
  for h in H:drawn[h].append(vals[h])
 if min(len(x) for x in drawn.values())<.99*REPEATS:raise ValueError("BOOTSTRAP_TOO_MANY_EMPTY_GROUPS")
 return {"phase":phase,"events":len(selected),"sweep":sum(e["sweep"] for e in selected),
  "calendarMonthClusters":len(months),"assetEffects":{
   sym:{h:rnd(estimate([e for e in selected if e["symbol"]==sym],h)) for h in H}
   for sym in ("BTC","ETH")},
  "horizons":{h:{"effectPctPoints":rnd(observed[h]),
    "monthClusterBootstrap95":[rnd(quantile(drawn[h],.025)),rnd(quantile(drawn[h],.975))]}
    for h in H}}

def main():
 s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
 bucket=os.environ["R2_BUCKET"]
 rows=[];refs=[]
 for version,key,digest,count in SOURCES:
  content=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
  if sha(content)!=digest:raise SystemExit("V72_REFERENCE_SHA_MISMATCH")
  source=json.loads(content)
  if source.get("version")!=version or len(source.get("results",[]))!=count:
   raise SystemExit("V72_REFERENCE_SHAPE_MISMATCH")
  rows.extend(source["results"]);refs.append({"version":version,"key":key,"sha256":digest})
 if len(rows)!=34 or len({(r["symbol"],r["month"]) for r in rows})!=34:
  raise SystemExit("V72_SOURCE_ROWS_MISMATCH")
 events=[]
 for r in rows:events+=events_for(s3,bucket,r)
 if len(events)!=962 or sum(e["sweep"] for e in events)!=177:
  raise SystemExit("V72_EVENT_COUNT_MISMATCH")
 baseline_overlap=overlaps(events)
 disjoint={str(p):overlaps([e for e in events if e["phase"]==p]) for p in (0,1)}
 if any(disjoint.values()):raise SystemExit("V72_PHASE_OVERLAP_VIOLATION")
 summaries={}
 for tag in ("baseline","extension","holdout","all"):
  subset=events if tag=="all" else [e for e in events if e["cohort"]==tag]
  summaries[tag]={str(p):phase_audit(subset,tag,p) for p in (0,1)}
 folder=Path("detector_v72_reports");folder.mkdir(exist_ok=True)
 raw_events=json.dumps(events,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
 (folder/"events.json").write_bytes(raw_events)
 report={"version":"7.2","status":"POST_HOC_RESEARCH_ONLY","researchOnly":True,"tradesEmitted":0,
  "originalLiveDetectorParity":"NOT_ESTABLISHED","sources":refs,"assetMonths":len(rows),
  "firstLongEvents":len(events),"firstSweepEvents":sum(e["sweep"] for e in events),
  "originalAdjacent24hOverlaps":baseline_overlap,"phaseAdjacent24hOverlaps":disjoint,
  "eventsSha256":sha(raw_events),"seed":SEED,"bootstrapRepeats":REPEATS,
  "phase":"First eligible LONG per UTC day; split by global UTC date ordinal modulo 2, before observing outcomes",
  "estimator":"Pooled first-LONG sweep minus non-sweep means within each phase",
  "samples":summaries,
  "limitations":["Post-hoc, not a new independent holdout",
   "Disjoint 24h windows per asset inside a phase; BTC and ETH still correlated",
   "Month bootstrap jointly samples BTC and ETH, but adjacent months may be dependent",
   "Pooled phase estimator differs from v7.0's symbol-month exclusion rule",
   "Source first-LONG classification/return horizons unchanged",
   "No trading execution, costs, funding, OI, live parity or causal proof"]}
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"comparison.json").write_bytes(raw)
 prefix=f"research/detector/v7.2/runs/{os.getenv('GITHUB_RUN_ID','manual')}-{os.getenv('GITHUB_RUN_ATTEMPT','1')}/"
 manifest={"version":"7.2","status":"POST_HOC_RESEARCH_PASS","researchOnly":True,
  "reportSha256":sha(raw),"eventsSha256":sha(raw_events),"prefix":prefix,
  "githubSha":os.environ.get("GITHUB_SHA")}
 (folder/"manifest.json").write_text(json.dumps(manifest,indent=2))
 for name in ("comparison.json","events.json","manifest.json"):
  buf=(folder/name).read_bytes()
  key=prefix+name
  s3.put_object(Bucket=bucket,Key=key,Body=buf,ContentType="application/json",
                Metadata={"sha256":sha(buf),"research-only":"true"})
  if s3.get_object(Bucket=bucket,Key=key)["Body"].read()!=buf:
   raise SystemExit("V72_WRITEBACK_VERIFICATION_FAILED")
 print(json.dumps({"status":"V72_NONOVERLAP_RESEARCH_PASS_WRITEBACK_VERIFIED",
  "run":os.getenv("GITHUB_RUN_ID"),"prefix":prefix,"reportSha256":sha(raw),
  "eventsSha256":sha(raw_events),"overlapsOriginal":baseline_overlap,
  "overlapsPhases":disjoint,"samples":summaries},ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write("# Detector v7.2: non-overlapping historical phases\n\n"
    +"Status: V72_NONOVERLAP_RESEARCH_PASS_WRITEBACK_VERIFIED\n\n"
    +"SHA-256: "+sha(raw)+"\n\nR2: "+prefix+"\n\nResearch only; no trade authority.\n")
if __name__=="__main__":main()
