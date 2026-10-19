#!/usr/bin/env python3
"""Coin Metrics company-owned free CSV alternative to HTTP403 community API.
Research-only source availability, not an as-of/predictive BTC model.
"""
import csv,datetime as dt,hashlib,io,json,os,urllib.request
from pathlib import Path
import boto3
ROOT=Path(__file__).resolve().parents[1]
PRE="research/btci_v818c1_coinmetrics_official_csv_prereg_2026-10-19.json"
PARENT=("research/btci/v8.18c/runs/39223566949-1/onchain_source_audit.json",
        "ca9091b66bc82ec3b9ef37e678eacd1b3c48afad58a0bf3310b86fd1e8763bf4")
def sha(raw):return hashlib.sha256(raw).hexdigest()
def blobsha(raw):return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\x00"+raw).hexdigest()
def cloud():
 return boto3.client("s3",endpoint_url="https://"+os.environ["R2_ACCOUNT_ID"]+".r2.cloudflarestorage.com",
 aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],region_name="auto")
def get(s,b,key,h):
 raw=s.get_object(Bucket=b,Key=key)["Body"].read()
 if sha(raw)!=h:raise SystemExit("V818C1_PARENT_SHA_MISMATCH")
 return json.loads(raw)
def write(s,b,key,data,kind="application/json"):
 raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False,indent=2).encode()
 dig=sha(raw)
 s.put_object(Bucket=b,Key=key,Body=raw,ContentType=kind,Metadata={"sha256":dig,"research-only":"true"})
 if sha(s.get_object(Bucket=b,Key=key)["Body"].read())!=dig:
  raise SystemExit("V818C1_R2_READBACK_FAILED")
 return dig
def main():
 pre=(ROOT/PRE).read_bytes();p=json.loads(pre)
 if p["version"]!="8.18c1" or p["parent"]!={"key":PARENT[0],"sha256":PARENT[1]}:
  raise SystemExit("V818C1_SPEC_MISMATCH")
 s=cloud();bucket=os.environ["R2_BUCKET"]
 old=get(s,bucket,*PARENT)
 if old["version"]!="8.18c" or old["fetched"]!=0:
  raise SystemExit("V818C1_SOURCE_FIRST_PILOT_MISMATCH")
 with urllib.request.urlopen(urllib.request.Request(p["originalArchive"],
  headers={"User-Agent":"BTCI-history-research-8.18c1","Accept":"text/csv"}),timeout=60) as response:
  raw=response.read(4_000_001)
 if len(raw)>4_000_000:raise SystemExit("V818C1_ARCHIVE_TOO_LARGE")
 git=blobsha(raw)
 if git!=p["originallyObservedGitBlobSHA1"]:
  raise SystemExit("V818C1_PINNED_ORIGINAL_GIT_BLOB_HAS_CHANGED")
 parsed=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
 head=parsed.fieldnames
 if not head or "time" not in head:raise SystemExit("V818C1_BAD_CSV_HEADER")
 all_dates={};duplicates=0
 for z in parsed:
  date=z["time"][:10]
  if date in all_dates:duplicates+=1
  all_dates[date]=z
 if duplicates:raise SystemExit("V818C1_DUPLICATE_DAYS")
 if len(all_dates)<5000:raise SystemExit("V818C1_SHORT_HISTORICAL_SOURCE")
 metric=[s for s in p["desiredMetrics"] if s in head]
 sample=[{"date":d,"dateInCSV":d in all_dates,
  "metrics":{metric:(all_dates.get(d) or {}).get(metric) if metric in head else None
             for metric in p["desiredMetrics"]}}
          for d in p["exactTests"]]
 prefix=f"research/btci/v8.18c1/runs/{os.environ.get('GITHUB_RUN_ID','manual')}-{os.environ.get('GITHUB_RUN_ATTEMPT','1')}/"
 original=write(s,bucket,prefix+"source/CoinMetrics_Official_btc.csv",raw,"text/csv")
 report={"version":"8.18c1","researchOnly":True,
  "status":"OFFICIAL_GITHUB_CSV_SOURCE_VERIFIED_BUT_METRIC_COVERAGE_AUDITED",
  "prior403Audit":{"key":PARENT[0],"sha256":PARENT[1]},
  "preregSha256":sha(pre),"source":{"origin":p["originalArchive"],
    "GitHubBlobSHA1":git,"csvSHA256":original,
    "r2Key":prefix+"source/CoinMetrics_Official_btc.csv"},
  "columns":head,"availableWantedMetrics":metric,
  "days":len(all_dates),"first":min(all_dates),"last":max(all_dates),
  "samples":sample,
  "vintageStatus":"HISTORICAL_RECONSTRUCTION_NOT_PIT_VERIFIED",
  "doNotScoreBackfilledCryptoFundamentalsAsOriginalEarlyWarnings":True,
  "license":"Company-owned Coin Metrics archive published CC BY-NC 4.0 for noncommercial research.",
  "noPortfolioWrites":True}
 folder=Path("btci_v818c1_reports");folder.mkdir(exist_ok=True)
 payload=json.dumps(report,ensure_ascii=False,indent=2).encode()
 (folder/"onchain_official_csv_source.json").write_bytes(payload)
 dg=write(s,bucket,prefix+"onchain_official_csv_source.json",payload)
 mh=write(s,bucket,prefix+"manifest.json",{
   "version":"8.18c1","researchOnly":True,"status":report["status"],
   "reportSha256":dg,"sourceSha256":original,"preregSha256":sha(pre)})
 summary={"status":"V818C1_OFFICIAL_CSV_SHA_R2_VERIFIED",
  "prefix":prefix,"reportSha256":dg,"manifestSha256":mh,
  "rawGitBlobSHA1":git,"availableWantedMetrics":metric,
  "columns":head,"nDays":len(all_dates),"samples":sample}
 (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 print("V818C1_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
