#!/usr/bin/env python3
"""BTCI v8.18f official public Binance Vision BTCUSDT 1d historical
spot turnover/taker direction around crypto shocks, NOT liquidation volume.
"""
import csv,datetime as dt,hashlib,io,json,math,os,re,statistics,urllib.request,zipfile
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v818f_crypto_shock_binance_volume_prereg_2026-10-19.json"
PARENT=("research/btci/v8.18e/runs/39215131167-1/crypto_crisis_events.json","78608d81f46d52b520a51377068b7221d7bb957fc6d6cba689afcf41ae230bff")
def sha(b):return hashlib.sha256(b).hexdigest()
def d(s):return dt.date.fromisoformat(s)
def r6(x):return round(float(x),6)
def r2():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def chk(s,b,k,expected):
 body=s.get_object(Bucket=b,Key=k)["Body"].read()
 if sha(body)!=expected:raise SystemExit("V818F_PINNED_PARENT_SHA_INVALID")
 return json.loads(body)
def save(s,b,k,raw,kind):
 raw=raw if isinstance(raw,bytes) else json.dumps(raw,ensure_ascii=False,indent=2).encode()
 h=sha(raw)
 s.put_object(Bucket=b,Key=k,Body=raw,ContentType=kind,Metadata={"sha256":h,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=k)["Body"].read())!=h:raise SystemExit("V818F_R2_OBJECT_READBACK_FAIL")
 return {"r2Key":k,"sha256":h,"bytes":len(raw)}
def get(url,maxbytes=500000):
 request=urllib.request.Request(url,headers={"User-Agent":"BTCI-8.18f-financial-research","Accept":"application/octet-stream,text/plain"})
 with urllib.request.urlopen(request,timeout=35) as response:
  blob=response.read(maxbytes+1)
 if len(blob)>maxbytes:raise ValueError("BLOB_TOO_BIG")
 return blob
def source(month):
 base=f"https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-{month}.zip"
 content=get(base)
 check=get(base+".CHECKSUM",300).decode("utf-8","replace").strip()
 matches=re.findall(r"\b[a-fA-F0-9]{64}\b",check)
 if len(matches)!=1:raise ValueError("INVALID_OFFICIAL_CHECKSUM")
 if sha(content)!=matches[0].lower():raise ValueError("BINANCE_OFFICIAL_CHECKSUM_NOT_MATCHED")
 with zipfile.ZipFile(io.BytesIO(content)) as zipped:
  if zipped.testzip():raise ValueError("ZIP_CRC_FAILED")
  names=zipped.namelist()
  if names!=[f"BTCUSDT-1d-{month}.csv"]:raise ValueError("ZIP_FILENAME_UNEXPECTED")
  with zipped.open(names[0]) as f:rows=list(csv.reader(io.TextIOWrapper(f,encoding="utf-8")))
 out={}
 for line in rows:
  if len(line)!=12:raise ValueError("NOT_12_FIELDS")
  stamp=int(line[0])
  if not 1_000_000_000_000<=stamp<2_000_000_000_000:raise ValueError("BAD_2022_TIMESTAMP")
  dated=dt.datetime.fromtimestamp(stamp/1000,dt.timezone.utc)
  if (dated.hour,dated.minute,dated.second)!=(0,0,0):raise ValueError("BAD_DAILY_OPEN_TIME")
  ds=dated.date()
  if ds.strftime("%Y-%m")!=month:raise ValueError("WRONG_MONTH")
  amount=float(line[5]);quote=float(line[7]);takerbuy=float(line[9]);takerquote=float(line[10])
  for v in (amount,quote,takerbuy,takerquote):
   if not math.isfinite(v) or v<0:raise ValueError("NAN_OR_NEGATIVE_VOLUME")
  if amount<=0 or quote<=0 or takerbuy>amount or takerquote>quote:
   raise ValueError("CORRUPT_MARKET_VOLUME")
  if ds in out:raise ValueError("DUPLICATE_DAY")
  out[ds]={"date":ds.isoformat(),"btcVolume":amount,"quoteUSDT":quote,
   "takerBuyBTC":takerbuy,"takerSellBTC":amount-takerbuy,
   "takerImbalanceBTC":(2*takerbuy/amount-1),
   "trades":int(line[8]),"closeUSDT":float(line[4])}
 days=sorted(out)
 if any((b-a).days!=1 for a,b in zip(days,days[1:])):raise ValueError("MISSING_DAILY_KLINE")
 return out,content,check
def window(prices,first,last):
 a=d(first);b=d(last)
 days=[prices[a+dt.timedelta(days=k)] for k in range((b-a).days+1)]
 if len(days)!=14:raise ValueError("NOT_14_DAY_PERIOD")
 total=sum(x["btcVolume"] for x in days)
 buy=sum(x["takerBuyBTC"] for x in days)
 sell=sum(x["takerSellBTC"] for x in days)
 qt=sum(x["quoteUSDT"] for x in days)
 return {"from":first,"to":last,"days":len(days),
  "totalBTCVolume":r6(total),"meanDailyBTCVolume":r6(total/14),
  "medianDailyBTCVolume":r6(statistics.median(x["btcVolume"] for x in days)),
  "totalUSDTQuoteVolume":r6(qt),"meanDailyUSDTQuoteVolume":r6(qt/14),
  "totalTakerBuyBTC":r6(buy),"totalTakerSellBTC":r6(sell),
  "takerBuyVolumeSharePct":r6(buy/total*100),
  "takerSellVolumeSharePct":r6(sell/total*100),
  "weightedTakerImbalancePct":r6((buy-sell)/total*100),
  "largestDailyBaseVolume":max(days,key=lambda x:x["btcVolume"])["date"],
  "spotMarket":"Binance BTCUSDT only, not global volume or forced sell liquidations"}
def main():
 raw=(ROOT/PRE).read_bytes();p=json.loads(raw)
 if p["version"]!="8.18f" or p["parent"]!={"key":PARENT[0],"sha256":PARENT[1]}:
  raise SystemExit("PREREG_OR_PARENT_CHANGED")
 s=r2();bucket=os.environ["R2_BUCKET"]
 prev=chk(s,bucket,*PARENT)
 if prev["version"]!="8.18e" or prev["sample"]["events"]!=13:raise SystemExit("EVENT_PARENT_VERSION_CHANGED")
 folder=Path("btci_v818f_reports");folder.mkdir(exist_ok=True)
 prefix=f"research/btci/v8.18f/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 bydate={};sources={}
 for month in p["months"]:
  parsed,blob,ch=source(month)
  for ds,row in parsed.items():
   if ds in bydate:raise SystemExit("DUPLICATE_MONTH_DAY")
   bydate[ds]=row
  uploaded=save(s,bucket,prefix+f"source/BTCUSDT-1d-{month}.zip",blob,"application/zip")
  sources[month]={**uploaded,"officialBinanceChecksum":ch,"verifiedDailyKlines":len(parsed)}
  print("V818F_SOURCE",month,len(parsed),uploaded["sha256"],flush=True)
 windows={}
 for group,part in p["fixedWindows"].items():
  results={}
  for label,text in part.items():
   first,last=text.split("..")
   results[label]=window(bydate,first,last)
  pre=results["prior"]
  def ratio(q):return {"meanDailyBTCx":r6(q["meanDailyBTCVolume"]/pre["meanDailyBTCVolume"]),
   "meanDailyUSDTx":r6(q["meanDailyUSDTQuoteVolume"]/pre["meanDailyUSDTQuoteVolume"]),
   "deltaTakerBuySharePp":r6(q["takerBuyVolumeSharePct"]-pre["takerBuyVolumeSharePct"]),
   "deltaTakerSellSharePp":r6(q["takerSellVolumeSharePct"]-pre["takerSellVolumeSharePct"])}
  results["shockVsPrior"]=ratio(results["shock"])
  if "contagion" in results:results["contagionVsPrior"]=ratio(results["contagion"])
  windows[group]=results
  print("V818F_WINDOW",group,json.dumps(results["shockVsPrior"]),flush=True)
 result={"version":"8.18f","status":"BINANCE_OFFICIAL_CHECKSUM_VOLUME_COMPARISON_PASS",
  "researchOnly":True,"noTradeSignal":True,
  "preregistration":{"path":PRE,"sha256":sha(raw)},
  "eventStudyParent":{"key":PARENT[0],"sha256":PARENT[1]},
  "source":"official Binance public archive daily BTCUSDT spot klines",
  "sourceArchive":sources,
  "findings":windows,
  "dailyKlines":[{k:(r6(v) if isinstance(v,float) else v) for k,v in z.items()}
    for _,z in sorted(bydate.items())],
  "counts":{"months":len(sources),"days":len(bydate),"clusters":len(windows)},
  "noEvidenceOf":"Forced liquidation volume, proof of on-chain exchange deposit, total global Bitcoin net selling, cause of any single trade",
  "caveats":[
   "Every trade has a buyer and a seller; notional turnover cannot be called net sales. Taker-side aggression only reveals initiator of exchange orders.",
   "One exchange and one market pair BTCUSDT, not global all-pairs execution.",
   "Historical ZIP monthly published after those events; this retrospective study does NOT prove live November 2022 forecast availability.",
   "No original intraday public-news time alignment from 1d data, dates overlap between 2022 risk waves.",
   "Study conditions and dates chosen after seeing financial crises; not calibrated predictive probabilities.",
   "No changes Spot/Futures/NAV/P&L/reserve/capital/MASTER/Detector/trading limits."]}
 output=json.dumps(result,ensure_ascii=False,indent=2).encode()
 (folder/"official_spot_volumes.json").write_bytes(output)
 rs=save(s,bucket,prefix+"official_spot_volumes.json",output,"application/json")
 ms=save(s,bucket,prefix+"manifest.json",{
   "version":"8.18f","researchOnly":True,"status":"BINANCE_VOLUME_AUDITED",
   "reportSha256":rs["sha256"],"sourceArchives":sources,
   "preregistrationSha256":sha(raw)},"application/json")
 brief={"status":"V818F_BINANCE_VOLUMES_WRITEBACK_VERIFIED",
   "prefix":prefix,"reportSha256":rs["sha256"],
   "manifestSha256":ms["sha256"],"windows":windows,"sources":sources}
 (folder/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2))
 print("V818F_RESULT "+json.dumps(brief,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
