#!/usr/bin/env python3
"""Full 2020-Sep2026 BTC ETH historical re-evaluation v7.5.
One process per UTC year, then immutable-source verified combining phase. Research only.
No trading, portfolio, NAV, Futures or live Detector modifications.
"""
import argparse,ast,hashlib,json,os,random,statistics,sys
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
SEED=750018
REPEATS=12000
HORIZONS=("4h","24h")
PREREG="research/detector_v75_full_cycle_prereg_2026-10-18.json"
PREREG_COMMIT="81243056c3ec27148fe061bc09c4b0484f7f9f6e"
REFERENCES=(
 ("6.9","research/detector/v6.9/runs/39107302260-1/comparison.json","52c68895360938cf70f118a5465713f01e3391ce64bfb4ef2e613ef10c22524a",22,"results"),
 ("7.0","research/detector/v7.0/runs/39109768036-1/comparison.json","7d4947d48e65aae303f3e927b1a9687cc140925cb2c739faa7899821a93a6eea",12,"results"),
 ("7.3","research/detector/v7.3/runs/39112394369-1/comparison.json","9407e6826d3e2acecc1d051e3868c26b4541827f0918626ee27d28b2a81009a2",8,"records"),
)
EXPECTED=[f"{y}-{m:02d}" for y in range(2020,2027) for m in range(1,13) if (y,m)<=(2026,9)]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def rnd(x):return round(x,6) if x is not None else None
def quantile(a,p):
 if not a:return None
 v=sorted(a);q=(len(v)-1)*p;k=int(q)
 return v[k]+(v[min(k+1,len(v)-1)]-v[k])*(q-k)
def s3conn():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def check_prereg():
 raw=(ROOT/PREREG).read_bytes();d=json.loads(raw)
 if (d["version"]!="7.5" or d["mode"]!="FROZEN_FULL_HISTORICAL_CYCLE_REPLAY"
     or d["window"]["completeUTCMonths"]!=81 or d["window"]["btcEthSymbolMonths"]!=162):
  raise SystemExit("V75_PREREG_INVALID")
 return sha(raw)
def get_versioned(s3,bucket,key,expected_sha):
 raw=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
 if sha(raw)!=expected_sha:raise SystemExit("V75_SOURCE_SHA_MISMATCH:"+key)
 return json.loads(raw)
def stage(s3,bucket,path,data):
 blob=data if isinstance(data,bytes) else json.dumps(data,indent=2,ensure_ascii=False).encode()
 digest=sha(blob)
 s3.put_object(Bucket=bucket,Key=path,Body=blob,ContentType="application/json",
               Metadata={"sha256":digest,"research-only":"true"})
 other=s3.get_object(Bucket=bucket,Key=path)["Body"].read()
 if sha(other)!=digest:raise SystemExit("V75_R2_READBACK_MISMATCH:"+path)
 return digest
def prefix():
 return f"research/detector/v7.5/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
def source_functions():
 tree=ast.parse((ROOT/"research/detector_matched_controls_v65.py").read_text())
 keep=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.Assign,ast.FunctionDef))
       and not (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name)
       and t.id in ("s3","out") for t in n.targets))]
 scope={"__file__":str(ROOT/"research/detector_matched_controls_v65.py")}
 exec(compile(ast.Module(body=keep,type_ignores=[]),"<v65 definitions>","exec"),scope)
 v68=ast.parse((ROOT/"research/detector_fixed_windows_v68.py").read_text())
 keep=[n for n in v68.body if isinstance(n,ast.FunctionDef)
       and n.name in ("avg","rounded","percentile","analyze")]
 scope.update(H={"4h":16,"24h":96},SEED=6808,datetime=datetime,timezone=timezone,
              random=random,statistics=statistics)
 exec(compile(ast.Module(body=keep,type_ignores=[]),"<v68 definitions>","exec"),scope)
 v69=ast.parse((ROOT/"research/detector_extension_v69.py").read_text())
 keep=[n for n in v69.body if isinstance(n,ast.FunctionDef) and n.name=="aggregate"]
 exec(compile(ast.Module(body=keep,type_ignores=[]),"<v69 aggregate>","exec"),scope)
 v73=ast.parse((ROOT/"research/detector_temporal_bridge_v73.py").read_text())
 keep=[n for n in v73.body if isinstance(n,ast.FunctionDef) and n.name=="events_and_regimes"]
 scope["HORIZONS"]=HORIZONS
 exec(compile(ast.Module(body=keep,type_ignores=[]),"<v73 events>","exec"),scope)
 return scope

def evaluate_year(year):
 prereg_sha=check_prereg()
 s3=s3conn();bucket=os.environ["R2_BUCKET"]
 scope=source_functions()
 read_month,analyze,events_regime=(
  scope[x] for x in ("read_month","analyze","events_and_regimes"))
 months=[m for m in EXPECTED if int(m[:4])==year]
 records=[];events=[];errors=[]
 for month in months:
  for sym in ("BTC","ETH"):
   try:
    bars,digest=read_month(s3,bucket,sym,month)
    first=datetime.fromtimestamp(bars[0]["t"]/1000,timezone.utc)
    last=datetime.fromtimestamp(bars[-1]["endMs"]/1000,timezone.utc)
    y,m=map(int,month.split("-"))
    nx=f"{y+1}-01" if m==12 else f"{y}-{m+1:02d}"
    if first!=datetime.fromisoformat(month+"-01").replace(tzinfo=timezone.utc) or last!=datetime.fromisoformat(nx+"-01").replace(tzinfo=timezone.utc):
     raise ValueError("MONTH_BOUNDARY_INCOMPLETE")
    rec={"symbol":sym,"month":month,"cohort":"full_cycle","sourceSha256":digest,
         **analyze(bars),"status":"RESEARCH_PASS"}
    current=events_regime(bars,rec)
    for e in current:e["cohort"]="full_cycle"
    records.append(rec)
    events.extend(current)
   except Exception as e:
    errors.append({"symbol":sym,"month":month,"error":type(e).__name__+":"+str(e)[:160]})
 if errors or len(records)!=2*len(months):
  print("V75_YEAR_BLOCKED "+json.dumps({"year":year,"errors":errors,"expected":len(months)*2,
    "found":len(records)},ensure_ascii=False),flush=True)
  raise SystemExit("V75_YEAR_SOURCE_OR_REPLAY_BLOCKED")
 raw_records=json.dumps(records,indent=2,ensure_ascii=False).encode()
 raw_events=json.dumps(events,indent=2,ensure_ascii=False).encode()
 root=prefix()+f"years/{year}/"
 a=stage(s3,bucket,root+"records.json",raw_records)
 b=stage(s3,bucket,root+"events.json",raw_events)
 manifest={"version":"7.5","year":year,"researchOnly":True,"tradesEmitted":0,
  "months":len(months),"sourceRecords":len(records),"firstEvents":len(events),
  "recordsSha256":a,"eventsSha256":b,"preregistrationSha256":prereg_sha,
  "githubSha":os.getenv("GITHUB_SHA"),"prefix":root}
 c=stage(s3,bucket,root+"manifest.json",manifest)
 folder=Path("detector_v75_reports");folder.mkdir(exist_ok=True)
 (folder/f"year_{year}.json").write_text(json.dumps({"status":"V75_YEAR_RESEARCH_PASS_WRITEBACK_VERIFIED",
  "year":year,"records":len(records),"events":len(events),
  "manifestSha256":c,"prefix":root},indent=2))
 print(json.dumps({"status":"V75_YEAR_RESEARCH_PASS_WRITEBACK_VERIFIED",
  "year":year,"records":len(records),"events":len(events),"prefix":root,
  "recordsSha256":a,"eventsSha256":b,"manifestSha256":c},ensure_ascii=False),flush=True)

def agg(rows):
 valid={}
 for h in HORIZONS:
  a_n=b_n=0;a_sum=b_sum=0.0;positive=negative=both=0
  for record in rows:
   z=record["firstCandidateComparison"]["horizons"][h]
   if z["groupA"]>0 and z["groupB"]>0:
    a_n+=z["groupA"];b_n+=z["groupB"]
    a_sum+=z["groupA"]*z["meanA"];b_sum+=z["groupB"]*z["meanB"]
    both+=1
    if z["differencePctPoints"]>0:positive+=1
    if z["differencePctPoints"]<0:negative+=1
  valid[h]={"groupSweep":a_n,"groupOther":b_n,
    "differencePctPoints":rnd(a_sum/a_n-b_sum/b_n) if a_n and b_n else None,
    "symbolMonthsWithBothGroups":both,"symbolMonthsPositive":positive,"symbolMonthsNegative":negative}
 return {"symbolMonths":len(rows),"candidateTotal":sum(x["totalCandidates"] for x in rows),
  "firstLongTotal":sum(x["firstCandidates"] for x in rows),
  "firstSweepTotal":sum(x["firstSweep"] for x in rows),
  "horizons":valid}

def event_effect(events,h):
 x=[e[h] for e in events if e["sweep"]]
 y=[e[h] for e in events if not e["sweep"]]
 return statistics.mean(x)-statistics.mean(y) if x and y else None

def overlaps(events):
 v=0
 for sym in ("BTC","ETH"):
  a=sorted((e for e in events if e["symbol"]==sym),key=lambda e:e["timestampMs"])
  v+=sum(left["timestampMs"]+86400000>right["timestampMs"] for left,right in zip(a,a[1:]))
 return v

def bootstrap_quarters(records):
 blocks=defaultdict(list)
 for r in records:
  quarter=(int(r["month"][5:])-1)//3+1
  blocks[r["month"][:4]+f"-Q{quarter}"].append(r)
 keys=sorted(blocks)
 assert len(keys)==27
 base=agg(records)
 observed=[base["horizons"][h]["differencePctPoints"] for h in HORIZONS]
 rng=random.Random(SEED)
 samples={h:[] for h in HORIZONS}
 for _ in range(REPEATS):
  selected=[r for _ in keys for r in blocks[keys[rng.randrange(len(keys))]]]
  effects=agg(selected)["horizons"]
  if all(effects[h]["differencePctPoints"] is not None for h in HORIZONS):
   for h in HORIZONS:samples[h].append(effects[h]["differencePctPoints"])
 if any(len(samples[h])<REPEATS*.99 for h in HORIZONS):
  raise SystemExit("V75_BOOTSTRAP_TOO_MANY_EMPTY_GROUPS")
 sd={h:statistics.pstdev(samples[h]) for h in HORIZONS}
 if any(sd[h]<=0 for h in HORIZONS):raise SystemExit("V75_BOOTSTRAP_ZERO_VARIANCE")
 max_t=[max(abs((samples[h][i]-observed[j])/sd[h]) for j,h in enumerate(HORIZONS))
        for i in range(len(samples["4h"]))]
 critical=quantile(max_t,.95)
 return {"method":"27 synchronized calendar-quarter resampling blocks, BTC+ETH and 3 months together",
  "quarterClusters":len(keys),"draws":len(samples["4h"]),"bootstrapSeed":SEED,
  "horizons":{h:{"effectPctPoints":observed[j],
   "percentile95":[rnd(quantile(samples[h],.025)),rnd(quantile(samples[h],.975))],
   "simultaneousTwoHorizon95Approx":[rnd(observed[j]-critical*sd[h]),
                                      rnd(observed[j]+critical*sd[h])]}
     for j,h in enumerate(HORIZONS)},
  "limitations":["Adjacent quarter serial dependence not eliminated",
    "Bootstrap intervals exploratory, not execution-adjusted confidence about profitability"]}

def compare_42(s3,bucket,records):
 old={}
 hashes=[]
 for version,key,expected,n,field in REFERENCES:
  doc=get_versioned(s3,bucket,key,expected)
  some=doc.get(field,[])
  if doc["version"]!=version or len(some)!=n:raise SystemExit("V75_OLD_REPORT_SHAPE_CHANGED")
  for r in some:
   identity=(r["symbol"],r["month"])
   if identity in old:raise SystemExit("V75_OLD_REPORT_DUPLICATE")
   old[identity]=r
  hashes.append({"version":version,"sha256":expected,"key":key})
 if len(old)!=42:raise SystemExit("V75_OLD_42_MISMATCH")
 now={(r["symbol"],r["month"]):r for r in records}
 for key,oldrow in old.items():
  if key not in now:raise SystemExit("V75_OLD_MONTH_MISSING")
  fresh=now[key]
  for field in ("sourceSha256","totalCandidates","firstCandidates","firstSweep","daysWithSweep"):
   if fresh[field]!=oldrow[field]:
    raise SystemExit("V75_OLD_PARITY_FAIL:"+str(key)+":"+field)
  for h in HORIZONS:
   for field in ("groupA","groupB","meanA","meanB","differencePctPoints"):
    if fresh["firstCandidateComparison"]["horizons"][h][field]!=oldrow["firstCandidateComparison"]["horizons"][h][field]:
     raise SystemExit("V75_OLD_HORIZON_PARITY_FAIL:"+str(key)+":"+h+":"+field)
 return hashes

def combine():
 prereg_sha=check_prereg()
 s3=s3conn();bucket=os.environ["R2_BUCKET"]
 records=[];events=[];source_years=[]
 for year in range(2020,2027):
  base=prefix()+f"years/{year}/"
  manifest=s3.get_object(Bucket=bucket,Key=base+"manifest.json")["Body"].read()
  obj=json.loads(manifest)
  if obj["version"]!="7.5" or obj["year"]!=year or obj["preregistrationSha256"]!=prereg_sha:
   raise SystemExit("V75_YEAR_MANIFEST_MISMATCH:"+str(year))
  x=get_versioned(s3,bucket,base+"records.json",obj["recordsSha256"])
  y=get_versioned(s3,bucket,base+"events.json",obj["eventsSha256"])
  if len(x)!=obj["sourceRecords"] or len(y)!=obj["firstEvents"]:
   raise SystemExit("V75_YEAR_COUNT_MISMATCH")
  records+=x;events+=y
  source_years.append({"year":year,"prefix":base,"recordsSha256":obj["recordsSha256"],
      "eventsSha256":obj["eventsSha256"],"manifestSha256":sha(manifest)})
 if len(records)!=162 or len(events)!=sum(r["firstCandidates"] for r in records):
  raise SystemExit("V75_ALL_COUNTS_MISMATCH")
 identity={(r["symbol"],r["month"]) for r in records}
 if len(identity)!=162 or identity!={(sym,month) for sym in ("BTC","ETH") for month in EXPECTED}:
  raise SystemExit("V75_NOT_COMPLETE_81_MONTHS")
 previous_hashes=compare_42(s3,bucket,records)
 annual={str(year):agg([r for r in records if r["month"].startswith(str(year))])
         for year in range(2020,2027)}
 by_asset={sym:agg([r for r in records if r["symbol"]==sym])
           for sym in ("BTC","ETH")}
 eras={"2020-2023":agg([r for r in records if r["month"]<"2024-01"]),
       "2024-2026":agg([r for r in records if r["month"]>="2024-01"])}
 leave_year={str(year):agg([r for r in records if not r["month"].startswith(str(year))])
             for year in range(2020,2027)}
 by_regime={}
 for val in ("UP","DOWN","SIDEWAYS"):
  sample=[e for e in events if e["regime"]==val]
  by_regime[val]={"firstLong":len(sample),"firstSweep":sum(e["sweep"] for e in sample),
   "effectPctPoints":{h:rnd(event_effect(sample,h)) for h in HORIZONS}}
 phases={}
 for p in (0,1):
  sample=[e for e in events if e["parity"]==p]
  count=overlaps(sample)
  if count:raise SystemExit("V75_NON_OVERLAP_PHASE_INVALID")
  phases[str(p)]={"events":len(sample),"sweep":sum(e["sweep"] for e in sample),
    "overlaps24h":count,"eventWeightedEffect":{h:rnd(event_effect(sample,h)) for h in HORIZONS}}
 uncertainty=bootstrap_quarters(records)
 report={"version":"7.5","status":"COMPLETE_RETROSPECTIVE_CYCLE_RESEARCH_ONLY",
  "researchOnly":True,"tradesEmitted":0,"originalLiveDetectorParity":"NOT_ESTABLISHED",
  "preregistration":{"path":PREREG,"commit":PREREG_COMMIT,"sha256":prereg_sha},
  "start":"2020-01","end":"2026-09","utcMonths":81,"symbolMonths":162,
  "source":"Binance USD-M futures BTC ETH full verified 5m ZIPs via R2",
  "old42Parity":"EXACT_MATCH","oldReferences":previous_hashes,"sourceYears":source_years,
  "total":agg(records),"byYear":annual,"byAsset":by_asset,"byEra":eras,
  "leaveOneYearOut":leave_year,"trailing24hRegime":by_regime,
  "originalAdjacent24hOverlapPairs":overlaps(events),"nonOverlapUtcDayParity":phases,
  "quarterBlockBootstrap":uncertainty,"eventCount":len(events),
  "limitations":["Retrospective OHLCV-only evidence, NOT a prospective test",
   "2024–2028 cycle still incomplete as of October 2026",
   "2024 ETFs are a contextual breakpoint, no causal inference from era split",
   "Source ZIP internal SHA+CRC and 5m continuity verified; independent Binance CHECKSUM audit is a separate task",
   "No realized executions, orders, fees, funding, slippage, open interest or order-book context",
   "No full live Detector feature parity and no new trading authority",
   "Possible multiple hypothesis and regime selection biases, serial dependencies",
   "Historical pattern cannot be claimed to produce trading profits"]}
 folder=Path("detector_v75_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"comparison.json").write_bytes(raw)
 root=prefix()+"combined/"
 h=stage(s3,bucket,root+"comparison.json",raw)
 manifest={"version":"7.5","status":"FULL_CYCLE_HISTORICAL_RESEARCH_PASS",
   "researchOnly":True,"tradesEmitted":0,"reportSha256":h,"sourceYears":source_years,
   "preregSha256":prereg_sha,"prefix":root}
 m=stage(s3,bucket,root+"manifest.json",manifest)
 brief={"status":"V75_FULL_CYCLE_RESEARCH_PASS_WRITEBACK_VERIFIED",
   "reportSha256":h,"manifestSha256":m,"prefix":root,
   "months":81,"assetMonths":162,"old42Parity":"EXACT_MATCH",
   "total":report["total"],"byYear":annual,"byAsset":by_asset,
   "byEra":eras,"quarterBlockBootstrap":uncertainty,
   "nonOverlapUtcDayParity":phases,"trailing24hRegime":by_regime}
 (folder/"summary.json").write_text(json.dumps(brief,indent=2,ensure_ascii=False))
 print(json.dumps(brief,ensure_ascii=False),flush=True)
 if os.environ.get("GITHUB_STEP_SUMMARY"):
  lines=["# Detector v7.5 — full 2020–2026 retrospective historical cycle","",
   "Research only. No live trading authority.","",
   "Status: V75_FULL_CYCLE_RESEARCH_PASS_WRITEBACK_VERIFIED","",
   "R2: "+root,"","SHA256: "+h,"",
   "| Year | Candidates | First Sweep | Δ4h pp | Δ24h pp |",
   "|---|---:|---:|---:|---:|"]
  for year,x in annual.items():
   lines.append(f"| {year} | {x['candidateTotal']} | {x['firstSweepTotal']} | {x['horizons']['4h']['differencePctPoints']} | {x['horizons']['24h']['differencePctPoints']} |")
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:f.write("\n".join(lines)+"\n")
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--year",type=int);ap.add_argument("--combine",action="store_true")
 a=ap.parse_args()
 if a.combine:evaluate=combine
 elif a.year in range(2020,2027):evaluate=lambda:evaluate_year(a.year)
 else:raise SystemExit("V75_ARGUMENTS_INVALID")
 evaluate()
if __name__=="__main__":main()
