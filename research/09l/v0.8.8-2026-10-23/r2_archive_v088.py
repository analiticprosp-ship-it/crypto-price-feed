#!/usr/bin/env python3
"""09L v0.8.8 append-only private R2 archive for derived first-day labels & event proxies."""
import datetime as dt,hashlib,json,os,pathlib
import boto3
from botocore.exceptions import ClientError
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"v0.8.8-2026-10-23"/"derived"/"r2"
ENV=("R2_ACCOUNT_ID","R2_ACCESS_KEY_ID","R2_SECRET_ACCESS_KEY","R2_BUCKET")
DAYS=("2026-02-01","2026-03-01","2026-04-01","2026-05-01")
VENUES=("bybit","okex-swap")
def client():
 if any(not os.getenv(k) for k in ENV):raise RuntimeError("R2_EXISTING_SECRETS_NOT_CONFIGURED")
 return boto3.client("s3",endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
  region_name="auto",aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])
def record(client,bucket,key,raw):
 sha=hashlib.sha256(raw).hexdigest()
 try:
  client.head_object(Bucket=bucket,Key=key);mode="ALREADY_EXISTS"
 except ClientError as e:
  if e.response.get("ResponseMetadata",{}).get("HTTPStatusCode")!=404:raise
  client.put_object(Bucket=bucket,Key=key,Body=raw,ContentType="application/json",
   Metadata={"sha256":sha,"scope":"09l-v088-shadow"})
  mode="WRITTEN"
 read=client.get_object(Bucket=bucket,Key=key)["Body"].read()
 if hashlib.sha256(read).hexdigest()!=sha:raise RuntimeError("R2_READBACK_FAILED")
 return {"status":"R2_READBACK_SHA256_PASS","sha256":sha,"r2_key":key,"mode":mode}
def main():
 c=client();bucket=os.environ["R2_BUCKET"];receipts=[]
 for venue in VENUES:
  for day in DAYS:
   specs=[
    (ROOT/"auto"/"v1"/"derived"/"v087_labels"/venue/(day+"_no_lookahead_trade_labels.json"),"no_lookahead_labels",{"LABELS_REGISTERED_EXPLORATORY","PARTIAL_LABELS_MISSING_ASOF_PRICE"}),
    (ROOT/"v0.8.8-2026-10-23"/"derived"/"liquidation_event_proxies"/venue/(day+"_first_message_behaviour.json"),"liquidation_behaviour_proxies",{"EVENT_PROXIES_EXPLORATORY"})]
   for p,kind,allowed in specs:
    if not p.is_file():
     receipts.append({"venue":venue,"day":day,"kind":kind,"status":"DERIVED_SOURCE_MISSING"});continue
    raw=p.read_bytes();j=json.loads(raw)
    if j.get("status") not in allowed:
     receipts.append({"venue":venue,"day":day,"kind":kind,"status":"SCIENTIFIC_SOURCE_GATE_FAILED","source_status":j.get("status")});continue
    if j.get("trading_canon_unchanged") is not True or j.get("venue")!=venue:
     raise ValueError("WRONG_DATA_SCOPE_OR_CANON")
    if j.get("source_day_utc",j.get("source_date_utc"))!=day:raise ValueError("WRONG_SOURCE_DATE")
    if kind=="no_lookahead_labels" and j.get("source",{}).get("status")!="OK":raise ValueError("INVALID_SOURCE")
    if kind=="liquidation_behaviour_proxies" and (j.get("trade_sources",{}).get("status")!="OK" or j.get("liquidation_source",{}).get("status")!="OK"):raise ValueError("INVALID_SOURCE")
    sha=hashlib.sha256(raw).hexdigest()
    rec=record(c,bucket,f"research/09l/v088/{kind}/{venue}/{day}/{sha}.json",raw)
    rec.update({"venue":venue,"day":day,"kind":kind,
      "source_status":j.get("status"),
      "eligible_cases":j.get("valid_behaviour_labels",sum(e["status"]=="LABEL_READY" for e in j.get("eight_clock_fixed_cases",[])))})
    receipts.append(rec)
 at=dt.datetime.now(dt.timezone.utc)
 n=sum(x["status"]=="R2_READBACK_SHA256_PASS" for x in receipts)
 receipt={"study":"09L v088 more dates & observed liq price proxy source archive",
  "created_at_utc":at.isoformat(),"status":"ARCHIVE_COMPLETE" if n==16 else "ARCHIVE_PARTIAL",
  "valid_r2_objects":n,"expected":16,"receipts":receipts,
  "r2_existing_bucket":True,"r2_prefix":"research/09l/v088",
  "model2_cluster_first_hit":"MISSING_NO_PIT","no_prospective_trading_claim":True,
  "trade_canon_mutation":False}
 raw=json.dumps(receipt,indent=2,ensure_ascii=False,sort_keys=True).encode()+b"\n"
 sha=hashlib.sha256(raw).hexdigest()
 receipt["manifest_receipt"]=record(c,bucket,f"research/09l/v088/manifests/{at:%Y/%m/%d}/{sha}.json",raw)
 OUT.mkdir(parents=True,exist_ok=True)
 p=OUT/(at.strftime("%Y%m%dT%H%M%S%fZ")+".json")
 with p.open("x",encoding="utf8") as f:json.dump(receipt,f,indent=2,ensure_ascii=False)
 print(json.dumps({"status":receipt["status"],"archived":n,"expected":16,
    "manifest_readback":receipt["manifest_receipt"]["status"],"receipt_file":str(p.relative_to(ROOT))}))
if __name__=="__main__":main()
