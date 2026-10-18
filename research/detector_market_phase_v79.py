#!/usr/bin/env python3
"""Research-only v7.9: UTC daily phase and selected-alt risk appetite price proxy.
Does not emit orders, account transactions, execution prices, or trading authority.
"""
import argparse,ast,calendar,csv,hashlib,io,json,os,re,sys,urllib.error,urllib.request,zipfile
from datetime import datetime,date,timezone,timedelta
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
SYMBOLS=("BTC","ETH","SOL","BNB","LINK","XRP","ADA","DOGE")
ALT=("SOL","BNB","LINK","XRP","ADA","DOGE")
PREREG="research/detector_v79_market_phase_prereg_2026-10-18.json"
PREREG_COMMIT="731a0fff03cf9fedb5de713e98834ce01c2983b9"
HIST=[f"{y}-{m:02d}" for y in (2025,2026) for m in range(1,13)
      if "2025-10"<=f"{y}-{m:02d}"<="2026-09"]
CUTOFF=date(2026,10,17)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def rounded(v):return round(v,6) if v is not None else None
def prereg():
 data=(ROOT/PREREG).read_bytes();doc=json.loads(data)
 if doc.get("version")!="7.9" or doc.get("symbols")!=list(SYMBOLS) or doc.get("decisionAsOfUTC")!=str(CUTOFF):
  raise SystemExit("V79_PREREG_MISMATCH")
 return sha(data)
def s3client():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
   aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
   aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def prefix():
 return f"research/detector/v7.9/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
def stage(s3,bucket,key,data):
 raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False,indent=2).encode()
 digest=sha(raw)
 s3.put_object(Bucket=bucket,Key=key,Body=raw,ContentType="application/json",
   Metadata={"sha256":digest,"research-only":"true"})
 if sha(s3.get_object(Bucket=bucket,Key=key)["Body"].read())!=digest:
  raise SystemExit("V79_R2_READBACK_FAILED:"+key)
 return digest
def get(s3,bucket,key,digest):
 blob=s3.get_object(Bucket=bucket,Key=key)["Body"].read()
 if sha(blob)!=digest:raise SystemExit("V79_FROZEN_SOURCE_SHA_MISMATCH:"+key)
 return json.loads(blob)
def read_archive():
 # Reuse validated v6.5 read-only full-month reader, only its AST function.
 fpath=ROOT/"research/detector_matched_controls_v65.py"
 tree=ast.parse(fpath.read_text())
 fun=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="read_month")
 env={"hashlib":hashlib,"csv":csv,"io":io,"zipfile":zipfile,"P5":300000}
 exec(compile(ast.Module(body=[fun],type_ignores=[]),"<v65 reader>","exec"),env)
 return env["read_month"]
def checksum_origin(url,blob):
 # Binance data public .CHECKSUM files normally supply SHA-256 of the ZIP.
 urlchecksum=url+".CHECKSUM"
 try:
  req=urllib.request.Request(urlchecksum,headers={"User-Agent":"CryptoDetectorCycleResearch-v79"})
  with urllib.request.urlopen(req,timeout=15) as r: txt=r.read(1000).decode("utf-8")
  dig=txt.split()[0].lower()
  if not re.fullmatch("[0-9a-f]{64}",dig):raise ValueError("UPSTREAM_CHECKSUM_INVALID")
  if dig!=sha(blob):raise ValueError("UPSTREAM_CHECKSUM_MISMATCH")
  return "UPSTREAM_SHA256_VERIFIED"
 except urllib.error.HTTPError as e:
  if e.code==404:return "UPSTREAM_CHECKSUM_NOT_PUBLISHED"
  raise
def fetch_daily_oct(symbol,day):
 date_s=day.isoformat()
 pair=symbol+"USDT"
 url=f"https://data.binance.vision/data/futures/um/daily/klines/{pair}/1d/{pair}-1d-{date_s}.zip"
 req=urllib.request.Request(url,headers={"User-Agent":"CryptoDetectorCycleResearch-v79"})
 with urllib.request.urlopen(req,timeout=35) as response:
  raw=response.read(1_000_001)
 if not raw or len(raw)>1_000_000:raise ValueError("PUBLIC_DAILY_ZIP_SIZE_OUT_OF_BOUNDS:"+date_s)
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  if z.testzip() is not None:raise ValueError("PUBLIC_DAILY_ZIP_BAD_CRC:"+date_s)
  files=[n for n in z.namelist() if n.endswith(".csv")]
  if len(files)!=1:raise ValueError("PUBLIC_DAILY_FILE_COUNT:"+date_s)
  rows=[]
  with z.open(files[0]) as f:
   for row in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")):
    if row and row[0].isdigit():rows.append(row)
  if len(rows)!=1:raise ValueError("PUBLIC_DAILY_ROW_COUNT:"+date_s)
  row=rows[0]
  dt=datetime.fromtimestamp(int(row[0])/1000,timezone.utc).date()
  if dt!=day:raise ValueError("PUBLIC_DAILY_TIME_MISMATCH:"+date_s)
  open_,high,low,close=map(float,row[1:5])
  if not (0<low<=min(open_,close)<=max(open_,close)<=high):
   raise ValueError("PUBLIC_DAILY_BAD_OHLC:"+date_s)
  if int(row[0])%86400000!=0:raise ValueError("PUBLIC_DAILY_TIME_NOT_UTC")
 quality=checksum_origin(url,raw)
 return {"day":date_s,"close":close,"sha256":sha(raw),
         "upstreamShaStatus":quality,"source":url}
def asset(sym):
 psha=prereg()
 s3=s3client();bucket=os.environ["R2_BUCKET"]
 read=read_archive()
 dailies=[];sources=[]
 for month in HIST:
  bars,blob_sha=read(s3,bucket,sym,month)
  y,m=map(int,month.split("-"))
  next_month=f"{y+1}-01" if m==12 else f"{y}-{m+1:02d}"
  expected=datetime.fromisoformat(month+"-01").replace(tzinfo=timezone.utc)
  expected_end=datetime.fromisoformat(next_month+"-01").replace(tzinfo=timezone.utc)
  if (datetime.fromtimestamp(bars[0]["t"]/1000,timezone.utc)!=expected or
   datetime.fromtimestamp(bars[-1]["endMs"]/1000,timezone.utc)!=expected_end):
   raise SystemExit("V79_R2_PARTIAL_MONTH:"+sym+"/"+month)
  last={}
  for bar in bars:
   d=datetime.fromtimestamp((bar["endMs"]-1)/1000,timezone.utc).date().isoformat()
   last[d]=bar["c"]
  if len(last)!=calendar.monthrange(y,m)[1]:
   raise SystemExit("V79_R2_DAILY_COVERAGE_MISSING:"+sym+"/"+month)
  for day,val in sorted(last.items()):
   dailies.append({"day":day,"close":val})
  sources.append({"month":month,"source":"BINANCE_USDM_5M_R2_FULL","sha256":blob_sha,"dailyBars":len(last)})
 for d in range(1,18):
  point=fetch_daily_oct(sym,date(2026,10,d))
  dailies.append({"day":point["day"],"close":point["close"]})
  sources.append({"month":point["day"],"source":"BINANCE_USDM_PUBLIC_1D",
    "sha256":point["sha256"],"upstreamShaStatus":point["upstreamShaStatus"]})
 dates=[date.fromisoformat(x["day"]) for x in dailies]
 if dates[0]!=date(2025,10,1) or dates[-1]!=CUTOFF or len(set(dates))!=len(dates):
  raise SystemExit("V79_DAILY_CUTOFF_OR_DUPLICATE")
 if any(b-a!=timedelta(days=1) for a,b in zip(dates,dates[1:])):
  raise SystemExit("V79_DAILY_GAP")
 if len(dailies)<366:raise SystemExit("V79_TOO_FEW_CLOSED_DAYS")
 raw=json.dumps(dailies,indent=2,ensure_ascii=False).encode()
 root=prefix()+f"assets/{sym}/"
 datas=stage(s3,bucket,root+"daily_closes.json",raw)
 manifest={"version":"7.9","symbol":sym,"status":"CLOSED_DAILY_COMPLETE",
  "researchOnly":True,"preregSha256":psha,
  "sourceDailySha256":datas,"cutoffUTC":str(CUTOFF),"dailyBars":len(dailies),
  "sources":sources,"lastPriceIsNonExecutableHistoricalBar":True}
 ms=stage(s3,bucket,root+"manifest.json",manifest)
 folder=Path("detector_v79_reports");folder.mkdir(exist_ok=True)
 summary={"status":"V79_ASSET_CLOSED_BAR_SOURCE_PASS","asset":sym,
  "cutoff":str(CUTOFF),"dailyBars":len(dailies),
  "dailySha256":datas,"manifestSha256":ms,
  "publicUpstreamChecksumsVerified":sum(x.get("upstreamShaStatus")=="UPSTREAM_SHA256_VERIFIED" for x in sources)}
 (folder/(sym+".json")).write_text(json.dumps(summary,indent=2,ensure_ascii=False))
 print(json.dumps(summary,ensure_ascii=False),flush=True)

def calculate(series):
 closes=[p["close"] for p in series]
 assert len(closes)>=366
 last=closes[-1]
 def sma(n,at=0):
  e=len(closes)-at
  return sum(closes[e-n:e])/n
 def ret(n):return 100*(last/closes[-(n+1)]-1)
 ma200=sma(200);ma50=sma(50)
 ma_slope=100*(ma200/sma(200,30)-1)
 drawdown=100*(last/max(closes[-365:])-1)
 streak=0
 for i in range(len(closes)-1,198,-1):
  n=sum(closes[i-199:i+1])/200
  if closes[i]<n:break
  streak+=1
 highs_new=max(closes[-30:]);highs_old=max(closes[-60:-30])
 lows_new=min(closes[-30:]);lows_old=min(closes[-60:-30])
 return {"cutoff":series[-1]["day"],"closeFuturesNonExecutable":last,
  "sma50":round(ma50,5),"sma200":round(ma200,5),
  "pctAbove200":rounded(100*(last/ma200-1)),
  "sma200Slope30dPct":rounded(ma_slope),
  "above200ConsecutiveClosedDays":streak,
  "return30dPct":rounded(ret(30)),"return90dPct":rounded(ret(90)),
  "rolling365dCloseDrawdownPct":rounded(drawdown),
  "higher30dHigh":highs_new>highs_old,"higher30dLow":lows_new>lows_old}

def evaluate():
 psha=prereg();s3=s3client();bucket=os.environ["R2_BUCKET"]
 data={};sources=[]
 for sym in SYMBOLS:
  root=prefix()+f"assets/{sym}/"
  manifest=json.loads(s3.get_object(Bucket=bucket,Key=root+"manifest.json")["Body"].read())
  if (manifest["version"]!="7.9" or manifest["symbol"]!=sym
      or manifest["cutoffUTC"]!=str(CUTOFF)
      or manifest["preregSha256"]!=psha):
   raise SystemExit("V79_ASSET_MANIFEST_INVALID:"+sym)
  dayseries=get(s3,bucket,root+"daily_closes.json",manifest["sourceDailySha256"])
  if len(dayseries)!=manifest["dailyBars"] or dayseries[-1]["day"]!=str(CUTOFF):
   raise SystemExit("V79_DAILY_SERIES_CHANGED:"+sym)
  data[sym]=calculate(dayseries)
  sources.append({"symbol":sym,"sha256":manifest["sourceDailySha256"],
    "dailyBars":len(dayseries),"publicChecksumVerified":sum(s.get("upstreamShaStatus")=="UPSTREAM_SHA256_VERIFIED" for s in manifest["sources"])})
 btc=data["BTC"]
 btc50pos=btc["closeFuturesNonExecutable"]>btc["sma50"] and btc["return30dPct"]>0
 btc50neg=btc["closeFuturesNonExecutable"]<btc["sma50"] and btc["return30dPct"]<0
 btc200pos=btc["closeFuturesNonExecutable"]>btc["sma200"] and btc["sma200Slope30dPct"]>0
 btc200neg=btc["closeFuturesNonExecutable"]<btc["sma200"] and btc["sma200Slope30dPct"]<0
 if btc200pos and btc["return90dPct"]>0:
  phase="RECOVERY_NOT_CONFIRMED" if btc["rolling365dCloseDrawdownPct"]<=-25 else "BTC_BULL_PRICE_TREND"
 elif btc200neg and btc["return90dPct"]<0:phase="BTC_BEAR_PRICE_TREND"
 elif btc["closeFuturesNonExecutable"]<btc["sma200"] and btc["return90dPct"]>0:phase="RECOVERY_NOT_CONFIRMED"
 else:phase="CONSOLIDATION_OR_TRANSITION"
 btc_vote=1 if btc50pos else (-1 if btc50neg else 0)
 rs={sym:rounded((1+data[sym]["return30dPct"]/100)/(1+btc["return30dPct"]/100)*100-100) for sym in SYMBOLS if sym!="BTC"}
 outperf=sum(rs[sym]>0 for sym in ALT)
 positive=sum(data[sym]["return30dPct"]>0 for sym in ALT)
 ethvote=1 if rs["ETH"]>0 else -1
 breadthvote=1 if outperf>=4 else (-1 if outperf<=2 else 0)
 usdvote=1 if positive>=4 else (-1 if positive<=2 else 0)
 score=btc_vote+ethvote+breadthvote+usdvote
 risk="RISK_ON_PRICE_PROXY" if score>=3 else ("RISK_OFF_PRICE_PROXY" if score<=-2 else "MIXED_PRICE_PROXY")
 result={"version":"7.9","researchOnly":True,"notTradeApproval":True,
  "status":"PRELIMINARY_UNCALIBRATED_PRICE_ONLY_MARKET_PHASE",
  "cutoffUTC":str(CUTOFF),"preregistration":{"path":PREREG,
     "commit":PREREG_COMMIT,"sha256":psha},
  "btcPhase":phase,"riskAppetiteProxy":risk,"riskScore":score,
  "riskVotes":{"btcPriceMomentum":btc_vote,"ETHvsBTC30d":ethvote,
   "altBreadthVsBTC":breadthvote,"altUSDPositiveBreadth":usdvote},
  "altBreadth":{"assets":list(ALT),"outperformBTC30d":outperf,
    "positiveUSD30d":positive,"relativePerformance30dPct":rs},
  "assets":data,"provenance":sources,
  "dataScope":"One Binance USDM perpetual venue; gapless R2 Oct25-Sep26 plus validated public UTC Oct1-17 daily",
  "notAvailable":["authenticated historical ETF net flow vintage",
   "historical weekly depth of orderbook","current open interest stress for all exchanges",
   "full universe capitalization-weighted alt breadth","real-time multi-venue executable spot quotes"],
  "limitations":[
   "Heuristic historical research-only score, not out-of-sample validated",
   "As of closed October 17 UTC, NOT October 18 live spot price",
   "Price-only alt basket of six surviving assets can have survivorship bias",
   "A risk appetite signal is not identical to bull-bear trend",
   "No authority to alter Futures, NAV, reserve, Spot or trading limits"
  ]}
 root=prefix()+"combined/"
 digest=stage(s3,bucket,root+"regime.json",result)
 mh=stage(s3,bucket,root+"manifest.json",{"version":"7.9",
  "status":"PRELIMINARY_PRICE_ONLY_RESEARCH_PASS",
  "researchOnly":True,"reportSha256":digest,"preregSha256":psha,
  "prefix":root,"cutoffUTC":str(CUTOFF)})
 folder=Path("detector_v79_reports");folder.mkdir(exist_ok=True)
 (folder/"regime.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print("V79_RESULT "+json.dumps({"status":"V79_PRICE_ONLY_RESEARCH_PASS_WRITEBACK_VERIFIED",
  "prefix":root,"reportSha256":digest,"manifestSha256":mh,
  "cutoff":str(CUTOFF),"phase":phase,"risk":risk,"riskScore":score,
  "btc":data["BTC"],"breadth":result["altBreadth"],"votes":result["riskVotes"]},
   ensure_ascii=False),flush=True)
 if os.getenv("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write(f"# Research-only market phase v7.9\n\nCutoff UTC: {CUTOFF}\n\nBTC phase: {phase}\n\nRisk appetite proxy: {risk}\n\nR2: {root}\n\nSHA-256: {digest}\n\nNot a trading approval.\n")
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--asset",choices=SYMBOLS)
 parser.add_argument("--combine",action="store_true")
 args=parser.parse_args()
 if args.asset:asset(args.asset)
 elif args.combine:evaluate()
 else:raise SystemExit("V79_ARGS_INVALID")
if __name__=="__main__":main()
