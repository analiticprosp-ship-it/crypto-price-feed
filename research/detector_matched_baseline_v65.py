#!/usr/bin/env python3
"""v6.5 research-only multi-month matched baseline and past-only regime test."""
import csv,hashlib,io,json,os,random,statistics,sys,zipfile
from pathlib import Path
from collections import defaultdict
import boto3
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
from build_market_summary import detector_features
from detector_signal_engine import direction_models
P5=300000;P15=900000;H={"15m":1,"1h":4,"4h":16,"24h":96}
MONTHS=["2026-%02d"%m for m in range(1,10)]
SEED=650026;REGIME_LOOKBACK=96;REGIME_THRESHOLD_PCT=1.0
def stats(values):
 if not values:return {"n":0,"meanPct":None,"medianPct":None,"positivePct":None}
 return {"n":len(values),"meanPct":round(statistics.mean(values),6),"medianPct":round(statistics.median(values),6),"positivePct":round(100*sum(x>0 for x in values)/len(values),4)}
def flow(b):
 v=b["v"];buy=b["buy"]
 return {"buyBase":buy,"sellBase":v-buy,"imbalance":round((2*buy-v)/v,6) if v else None}
def decision(bars,i):
 b=bars[i];f=detector_features(bars[:i+1],"15m")
 if f.get("sourceBarClosedAt")!=b["endMs"] or f.get("status")!="OHLCV_PROXY_ONLY":raise ValueError("FEATURE_GUARD")
 matched={"current":flow(b),"previous":flow(bars[i-1]),"matchedStartMs":b["t"],"matchedEndMs":b["endMs"],"sameWindow":True}
 d,reason=direction_models(b,f,matched)
 if d is None:raise ValueError(reason)
 return d["LONG"]["status"]=="EARLY_CANDIDATE_SHADOW",bool(f["localStructure"]["sweptLowReclaimed"])
def parse_month(raw):
 data=[]
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  if z.testzip():raise ValueError("ZIP_CRC")
  names=[n for n in z.namelist() if n.endswith(".csv")]
  if len(names)!=1:raise ValueError("CSV_COUNT")
  with z.open(names[0]) as f:
   for row in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")):
    if not row or not row[0].isdigit():continue
    t=int(row[0]);o,h,l,c,v,buy=map(float,[row[1],row[2],row[3],row[4],row[5],row[9]])
    if not(0<l<=min(o,c)<=max(o,c)<=h and 0<=buy<=v):raise ValueError("BAD_BAR")
    if data and t-data[-1][0]!=P5:raise ValueError("GAP")
    data.append((t,o,h,l,c,v,buy))
 if len(data)%3:raise ValueError("PARTIAL_15M")
 out=[]
 for j in range(0,len(data),3):
  x=data[j:j+3];t=x[0][0]
  if t%P15 or [r[0] for r in x]!=[t,t+P5,t+2*P5]:raise ValueError("ALIGNMENT")
  v=sum(r[5] for r in x)
  out.append({"t":t,"endMs":t+P15,"o":x[0][1],"h":max(r[2] for r in x),"l":min(r[3] for r in x),"c":x[-1][4],"v":v,"buy":sum(r[6] for r in x)})
 return out
s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
reports=[]
for sym in ("BTC","ETH"):
 r={"symbol":sym,"status":"BLOCKED","months":[]}
 try:
  bars=[];month_starts={};sha_by_month={}
  for month in MONTHS:
   key=f"binance/usdm/5m/{sym}USDT/{month}.zip"
   head=s3.head_object(Bucket=os.environ["R2_BUCKET"],Key=key)
   raw=s3.get_object(Bucket=os.environ["R2_BUCKET"],Key=key)["Body"].read()
   sha=hashlib.sha256(raw).hexdigest()
   if head["Metadata"].get("quality")!="full" or head["Metadata"].get("sha256")!=sha:raise ValueError("SOURCE_GUARD "+month)
   part=parse_month(raw)
   if bars and part[0]["t"]-bars[-1]["t"]!=P15:raise ValueError("CROSS_MONTH_GAP "+month)
   month_starts[month]=len(bars);sha_by_month[month]=sha;bars.extend(part)
   r["months"].append({"month":month,"bars":len(part),"sha256":sha})
  # Restrict outcome to within available history; use January to warm up.
  allrows=[]
  for i in range(max(14,REGIME_LOOKBACK),len(bars)):
   b=bars[i];month=next((m for m in MONTHS if b["t"]>=bars[month_starts[m]]["t"] and (m==MONTHS[-1] or b["t"]<bars[month_starts[MONTHS[MONTHS.index(m)+1]]]["t"])),None)
   past_pct=100*(b["c"]/bars[i-REGIME_LOOKBACK]["c"]-1)
   regime="UP" if past_pct>REGIME_THRESHOLD_PCT else "DOWN" if past_pct< -REGIME_THRESHOLD_PCT else "SIDEWAYS"
   long,sweep=decision(bars,i)
   allrows.append({"i":i,"month":month,"regime":regime,"long":long,"sweep":sweep,"endMs":b["endMs"]})
  # Matched control: for each candidate choose one deterministic non-candidate in
  # same symbol/month/past-only regime, from eligible bars with complete 24h future.
  rng=random.Random(SEED+(1 if sym=="ETH" else 0))
  controls=defaultdict(list)
  for x in allrows:
   if not x["long"] and x["i"]+96<len(bars):controls[(x["month"],x["regime"])].append(x)
  candidates=[x for x in allrows if x["long"]]
  paired=[];unmatched=defaultdict(int)
  for x in candidates:
   if x["i"]+96>=len(bars):
    unmatched["CENSORED_24H"]+=1;continue
   pool=controls[(x["month"],x["regime"])]
   if not pool:unmatched["NO_MATCH_SAME_MONTH_REGIME"]+=1;continue
   y=pool[rng.randrange(len(pool))]
   paired.append((x,y))
  # Separate strict non-overlap pairs: candidate intervals >=24h apart;
  # controls are not claimed independent; no bootstrap significance.
  independent=[];last=-10000
  for pair in paired:
   if pair[0]["i"]-last>=96:independent.append(pair);last=pair[0]["i"]
  def analyze(pairs):
   output={}
   for h,n in H.items():
    rows=[]
    for a,b in pairs:
     if a["i"]+n>=len(bars) or b["i"]+n>=len(bars):continue
     ret=lambda x:100*(bars[x["i"]+n]["c"]/bars[x["i"]]["c"]-1)
     rows.append((a,ret(a),ret(b)))
    groups={"ALL":rows,"SWEEP":[z for z in rows if z[0]["sweep"]],"NO_SWEEP":[z for z in rows if not z[0]["sweep"]]}
    for regime in ("UP","DOWN","SIDEWAYS"):groups["REGIME_"+regime]=[z for z in rows if z[0]["regime"]==regime]
    output[h]={name:{"candidate":stats([z[1] for z in items]),"matchedControl":stats([z[2] for z in items]),"pairedDifferencePctPoints":stats([z[1]-z[2] for z in items])} for name,items in groups.items()}
   return output
  # Deterministic prefix check for each candidate, as in v6.4.
  fails=[x["endMs"] for x in candidates if decision(bars[:x["i"]+1],x["i"])!=(True,x["sweep"])]
  if fails:raise ValueError("PREFIX_FAILURE")
  r.update(status="MATCHED_BASELINE_RESEARCH_PASS",closed15m=len(bars),evaluated=len(allrows),candidates=len(candidates),sweepCandidates=sum(x["sweep"] for x in candidates),matchedPairs=len(paired),nonOverlappingPairs=len(independent),unmatched=dict(unmatched),prefixChecks=len(candidates),prefixFailures=0,regimeRule="previous 96 closed 15m bars: >+1% UP, <-1% DOWN, otherwise SIDEWAYS",controlRule="seeded uniform sampling with replacement among noncandidate 15m bars in same month and past-only regime; full 24h future required",seed=SEED+(1 if sym=="ETH" else 0),allMatched=analyze(paired),nonOverlappingCandidates=analyze(independent))
 except Exception as ex:r["error"]=str(ex)
 reports.append(r)
Path("detector_v65_reports").mkdir(exist_ok=True)
payload={"version":"6.5","researchOnly":True,"tradesEmitted":0,"liveDetectorParity":"NOT_ESTABLISHED","outcomeIsNotTradePnl":True,"limitations":["Control sampling with replacement; pairs are not independent","Greedy non-overlap applies to candidates only, not controls","Same-month matching may reflect market drift and selection effects","No p-values, significance, or out-of-sample claim","Future prices are used only for evaluation and eligibility censoring, not signals/regimes","Only Jan-Sep 2026; no guarantee of all market regimes","Binance USD-M futures; no historical OI/funding"],"results":reports}
Path("detector_v65_reports/matched_market_baseline.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2))
print(json.dumps([{k:v for k,v in r.items() if k not in ("allMatched","nonOverlappingCandidates")} for r in reports],indent=2))
if any(r["status"]!="MATCHED_BASELINE_RESEARCH_PASS" for r in reports):raise SystemExit(1)
