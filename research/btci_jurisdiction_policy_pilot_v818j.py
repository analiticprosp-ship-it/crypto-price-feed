#!/usr/bin/env python3
"""BTCI 8.18j research-only pilot of 4 official jurisdiction policy dates vs
BTC PriceUSD. NOT an estimate of Korea altcoin response or China flows.
"""
import datetime as dt,hashlib,json,os,statistics
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
SPEC="research/btci_v818j_jurisdiction_liquidity_policy_asymmetry_prereg_2026-10-19.json"
ARCH=("research/btci/v8.7/runs/39131902527-1/archive_manifest.json","3705a179363c9fdf50fede363fb7062481ce15c60f62dfada226e5371e674fb4")
def sha(v):return hashlib.sha256(v).hexdigest()
def day(s):return dt.date.fromisoformat(s)
def round4(v):return round(float(v),4)
def cli():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def chk(s,b,k,h):
 z=s.get_object(Bucket=b,Key=k)["Body"].read()
 if sha(z)!=h:raise SystemExit("PARENT_SHA_MISMATCH")
 return json.loads(z)
def put(s,b,k,z):
 raw=z if isinstance(z,bytes) else json.dumps(z,ensure_ascii=False,indent=2).encode()
 h=sha(raw)
 s.put_object(Bucket=b,Key=k,Body=raw,ContentType="application/json",Metadata={"sha256":h,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=k)["Body"].read())!=h:raise SystemExit("R2_READBACK_FAILED")
 return h
def main():
 spec_raw=(ROOT/SPEC).read_bytes();p=json.loads(spec_raw)
 if p["version"]!="8.18j" or len(p["historicalSourceAnchorEvents"])!=4:raise SystemExit("SPEC_UNEXPECTED")
 s=cli();b=os.environ["R2_BUCKET"];manifest=chk(s,b,*ARCH)
 z=manifest["assets"]["btc"]["normalized"];raw=s.get_object(Bucket=b,Key=z["r2Key"])["Body"].read()
 if sha(raw)!=z["sha256"]:raise SystemExit("BTC_ORIGINAL_ARCHIVE_SHA_INVALID")
 btc={day(y["day"]):float(y["priceUSD"]) for y in json.loads(raw)}
 def at(d):
  if d not in btc:raise SystemExit("BTC_DATE_MISSING:"+d.isoformat())
  return btc[d]
 def r(a,base):return round4(100*(a/base-1))
 dates=[]
 for e in p["historicalSourceAnchorEvents"]:
  d=day(e["date"]);pre=at(d-dt.timedelta(days=1))
  p7=at(d-dt.timedelta(days=8))
  p30=at(d-dt.timedelta(days=31))
  record={"id":e["id"],"jurisdiction":e["jurisdiction"],"date":e["date"],
   "source":e["source"],"sourceStatus":"ORIGINAL_OFFICIAL_DATE_INTRADAY_UNVERIFIED",
   "legalContext":e.get("baseline"),"interpretation":e["special"],
   "btcPrior7Pct":r(pre,p7),"btcPrior30Pct":r(pre,p30),
   "btcDay0Pct":r(at(d),pre)}
  for h in (1,3,7,30):
   path=[at(d+dt.timedelta(days=i)) for i in range(h+1)]
   record[f"btcClosePlus{h}dPct"]=r(path[-1],pre)
   record[f"btcWorstCloseThrough{h}dPct"]=r(min(path),pre)
   record[f"btcBestCloseThrough{h}dPct"]=r(max(path),pre)
  dates.append(record)
 report={
  "version":"8.18j","researchOnly":True,"status":"FOUR_OFFICIAL_POLICY_EVENTS_BTC_ONLY_PILOT",
  "source":{"manifest":ARCH[0],"manifestSHA":ARCH[1],"BTCarchive":z["r2Key"],"BTCSHA":z["sha256"]},
  "preregistration":{"path":SPEC,"sha256":sha(spec_raw)},
  "events":dates,
  "coverage":{"events":len(dates),"btcPriceOnly":True,"actualRegionalCapitalWeightsAvailable":False,
   "koreanKRWAltVolumePIT":False,"mainlandChinaCapitalFlowPIT":False,
   "publicationTimeIntradayPIT":False},
  "limits":[
   "Four policy announcements preselected after events and observed history; cannot estimate prediction skill, cross-country impact or causality.",
   "PriceUSD is retrospective daily reference, not tradable exchange fills or exact intraday announcement reaction.",
   "South Korea KRW altcoin premiums, local trading volume and institutional capital weight NOT sourced; never infer from BTC alone.",
   "One-day China BTC response does not prove China controls BTC global market; specific 2021 restriction may have materially new enforceable effects.",
   "Hong Kong must be distinct from mainland China and Korea regulatory clarity may have compliance costs.",
   "No market-cap weights assigned or fitted, no forward-looking trading signal, no exact economic surprise estimate."],
  "unchanged":{"Spot":True,"Futures":True,"NAV":True,"PnL":True,"capital":True,"reserve":True,"MASTER":True,"Detector":True,"limits":True}
 }
 folder=Path("btci_v818j_reports");folder.mkdir(exist_ok=True)
 blob=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"jurisdiction_pilot.json").write_bytes(blob)
 prefix=f"research/btci/v8.18j/runs/{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 dig=put(s,b,prefix+"jurisdiction_pilot.json",blob)
 mani=put(s,b,prefix+"manifest.json",{"version":"8.18j","researchOnly":True,"reportSha256":dig,
  "preregSha256":sha(spec_raw),"status":report["status"]})
 summary={"status":"V818J_FOUR_POLICY_DATE_BTC_AUDIT_PASS_READBACK","prefix":prefix,
  "reportSha256":dig,"manifestSha256":mani,"events":dates}
 (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print("V818J_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
