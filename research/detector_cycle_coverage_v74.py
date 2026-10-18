#!/usr/bin/env python3
"""Detector v7.4: read-only archive completeness inventory for full 2020-Sep 2026 BTC/ETH cycle.
R2 writeback limited to a new research run path. No trading or live configuration changes.
"""
import concurrent.futures,datetime as dt,hashlib,json,os,re,urllib.error,urllib.request
from collections import defaultdict
from pathlib import Path
import boto3

START=(2020,1)
END=(2026,9)
SYMBOLS=("BTC","ETH","SOL","BNB","LINK","XRP","ADA","DOGE")
CORE=("BTC","ETH")
OLD=("2024-01","2024-02","2024-03","2024-04","2024-05","2024-06",
     "2024-09","2025-03","2025-09","2025-10","2025-11","2025-12",
     "2026-01","2026-02","2026-03","2026-04","2026-05","2026-06",
     "2026-07","2026-08","2026-09")
MONTHS=[f"{y}-{m:02d}" for y in range(2020,2027) for m in range(1,13) if START<=(y,m)<=END]
if len(MONTHS)!=81 or len(OLD)!=21:raise SystemExit("FIXED_MONTH_LIST_INVALID")
def sha(data):return hashlib.sha256(data).hexdigest()

def main():
 s3=boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
 bucket=os.environ["R2_BUCKET"]
 existing={}
 for symbol in SYMBOLS:
  prefix=f"binance/usdm/5m/{symbol}USDT/"
  item={}
  for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket,Prefix=prefix):
   for obj in page.get("Contents",[]):
    found=re.fullmatch(re.escape(prefix)+r"(20\d\d-(?:0[1-9]|1[0-2]))\.zip",obj["Key"])
    if found:item[found.group(1)]={"key":obj["Key"],"bytes":obj["Size"]}
  existing[symbol]=item
 def inspect(arg):
  symbol,month=arg
  key=f"binance/usdm/5m/{symbol}USDT/{month}.zip"
  result={"symbol":symbol,"month":month,"r2Exists":month in existing[symbol],
          "key":key,"testedBefore":month in OLD}
  if month in existing[symbol]:
   try:
    obj=s3.head_object(Bucket=bucket,Key=key)
    metadata=obj.get("Metadata",{})
    result.update(r2Status="METADATA_FULL" if metadata.get("quality")=="full"
      and re.fullmatch("[0-9a-f]{64}",metadata.get("sha256",""))
      and obj.get("ContentLength",0)>0 else "METADATA_UNVERIFIED",
      sizeBytes=obj.get("ContentLength",0),
      sourceSha256=metadata.get("sha256",""),sourceQuality=metadata.get("quality",""),
      rowCount=metadata.get("rows",""))
   except Exception as e:
    result.update(r2Status="HEAD_ERROR",error=type(e).__name__+":"+str(e)[:100])
  else:result["r2Status"]="NOT_STORED"
  if result["r2Status"]!="METADATA_FULL" and symbol in CORE:
   url=f"https://data.binance.vision/data/futures/um/monthly/klines/{symbol}USDT/5m/{symbol}USDT-5m-{month}.zip"
   req=urllib.request.Request(url,method="HEAD",headers={"User-Agent":"DetectorCycleCoverage-v7.4"})
   try:
    with urllib.request.urlopen(req,timeout=18) as response:
     result.update(originHead="HTTP_"+str(response.status),
       originBytes=response.headers.get("Content-Length",""))
   except urllib.error.HTTPError as e:result["originHead"]="HTTP_"+str(e.code)
   except Exception as e:result.update(originHead="UNVERIFIED",
                    originError=type(e).__name__+":"+str(e)[:90])
  return result
 tasks=[(sym,month) for sym in SYMBOLS for month in MONTHS]
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
  rows=list(pool.map(inspect,tasks))
 bysym={}
 for symbol in SYMBOLS:
  subset=[x for x in rows if x["symbol"]==symbol]
  statuses={s:sum(x["r2Status"]==s for x in subset)
    for s in ("METADATA_FULL","METADATA_UNVERIFIED","NOT_STORED","HEAD_ERROR")}
  byyear={str(y):{"fullMetadata":sum(x["r2Status"]=="METADATA_FULL" and x["month"].startswith(str(y)) for x in subset),
    "totalMonths":sum(x["month"].startswith(str(y)) for x in subset)}
    for y in range(2020,2027)}
  missing=[{"month":x["month"],"r2Status":x["r2Status"],"originHead":x.get("originHead","NOT_PROBED")}
    for x in subset if x["r2Status"]!="METADATA_FULL"]
  bysym[symbol]={"statuses":statuses,"byYear":byyear,"needsValidationOrBackfill":missing,
   "firstStored":min(existing[symbol]) if existing[symbol] else None,
   "lastStored":max(existing[symbol]) if existing[symbol] else None}
 core_pairs={month:all(next(x for x in rows if x["symbol"]==sym and x["month"]==month)["r2Status"]=="METADATA_FULL" for sym in CORE)
             for month in MONTHS}
 summary={"version":"7.4","status":"METADATA_AND_UPSTREAM_HEAD_INVENTORY_ONLY",
  "researchOnly":True,"tradesEmitted":0,"start":"2020-01","end":"2026-09","months":81,
  "core":["BTC","ETH"],"assetScope":list(SYMBOLS),
  "testedOldMonths":list(OLD),"oldMonthCount":21,
  "corePairedR2FullMetadataMonths":sum(core_pairs.values()),
  "coreMissingOrUnverifiedMonths":[m for m,ok in core_pairs.items() if not ok],
  "coreUntestedPairedR2FullMetadataMonths":[m for m,ok in core_pairs.items() if ok and m not in OLD],
  "coreMissingOrUnverifiedSymbolMonths":sum(bySym["statuses"]["NOT_STORED"]+
    bySym["statuses"]["METADATA_UNVERIFIED"]+bySym["statuses"]["HEAD_ERROR"] for sym,bySym in bysym.items() if sym in CORE),
  "bySymbol":bysym,
  "limitations":["HEAD and R2 metadata is not full-byte integrity audit",
   "Binance public HEAD status might be blocked by network and must not be confused with missing archive",
   "A month may be partial because a futures symbol was not listed at its start",
   "Do not backfill before verifying origin integrity and preserving source provenance",
   "Archived OHLCV cannot reveal true execution edge without fees/funding/slippage/market microstructure",
   "Prior 21 months were researched; this inventory is not a new signal backtest"]}
 folder=Path("detector_v74_reports");folder.mkdir(exist_ok=True)
 raw=json.dumps(summary,indent=2,ensure_ascii=False).encode()
 (folder/"coverage.json").write_bytes(raw)
 pref=f"research/detector/v7.4/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 manifest={"version":"7.4","researchOnly":True,"status":"COVERAGE_INVENTORY_PASS",
  "reportSha256":sha(raw),"prefix":pref,"githubSha":os.environ.get("GITHUB_SHA")}
 (folder/"manifest.json").write_text(json.dumps(manifest,indent=2))
 for fn in ("coverage.json","manifest.json"):
  blob=(folder/fn).read_bytes()
  key=pref+fn
  s3.put_object(Bucket=bucket,Key=key,Body=blob,ContentType="application/json",
      Metadata={"sha256":sha(blob),"research-only":"true"})
  if sha(s3.get_object(Bucket=bucket,Key=key)["Body"].read())!=sha(blob):
   raise SystemExit("V74_R2_WRITEBACK_VERIFICATION_FAILED:"+fn)
 brief={"status":"V74_CYCLE_INVENTORY_PASS_WRITEBACK_VERIFIED","prefix":pref,
  "reportSha256":sha(raw),"months":81,"pairedMetadataFull":summary["corePairedR2FullMetadataMonths"],
  "unverifiedOrMissing":summary["coreMissingOrUnverifiedMonths"],
  "untestedReadyByMetadata":summary["coreUntestedPairedR2FullMetadataMonths"],
  "bySymbol":{s:{"counts":bysym[s]["statuses"],"years":bysym[s]["byYear"],
                 "nonFullMonths":bysym[s]["needsValidationOrBackfill"]}
           for s in CORE}}
 print(json.dumps(brief,ensure_ascii=False),flush=True)
 if os.environ.get("GITHUB_STEP_SUMMARY"):
  with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
   f.write("# Detector v7.4 Cycle Coverage Inventory\n\n"
    "RESEARCH ONLY, no live changes.\n\n"
    "Paired BTC/ETH full-metadata months: "+str(summary["corePairedR2FullMetadataMonths"])+"/81\n\n"
    "R2: "+pref+"\n\nSHA-256: "+sha(raw)+"\n")
if __name__=="__main__":main()
