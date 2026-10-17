#!/usr/bin/env python3
"""v5.0 post-audit: classify monthly archives with prior listing evidence, cross-month boundaries.
No source data mutations. No trading or historical signal replay.
"""
import argparse,csv,json,datetime as dt,collections,hashlib,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--input",default="detector_futures_bulk_v48");p.add_argument("--output",default="detector_futures_v50_audit");p.add_argument("--prior",default="research/detector_v50_baseline.json");a=p.parse_args()
root=Path(a.input);out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
baseline=json.loads(Path(a.prior).read_text()) if Path(a.prior).exists() else {"months":[]}
raw=list(csv.DictReader((root/"report"/"batch_inventory.csv").open()))
rows=baseline.get("months",[])+raw
# deduplicate by asset/month, preferring newest audit.
by={(r["asset"],r["month"]):dict(r) for r in rows}
first_verified={}
for r in by.values():
 if r["status"] in ("PASS_FULL_MONTH","PARTIAL_FIRST_MONTH_CANDIDATE","PARTIAL_FIRST_MONTH_CANDIDATE_REVIEWED","PARTIAL_LISTING_MONTH_CANDIDATE"):
  first_verified[r["asset"]]=min(first_verified.get(r["asset"],r["month"]),r["month"])
issues=[];boundaries=[]
for (asset,month),r in sorted(by.items()):
 status=r["status"];first=r.get("first_ms") or r.get("first_timestamp_ms");last=r.get("last_ms") or r.get("last_timestamp_ms")
 if status in ("PARTIAL_FIRST_MONTH_CANDIDATE","PARTIAL_LISTING_MONTH_CANDIDATE"):
  if month>first_verified.get(asset,month):
   r["status"]="HISTORICAL_GAP";r["classification_reason"]="partial month after verified earlier trading"
  else:
   r["status"]="LISTING_MONTH_CANDIDATE_UNVERIFIED";r["classification_reason"]="earliest verified available month; listing date not independently verified"
 if status=="QUALITY_FAIL":
  r["status"]="HISTORICAL_GAP_OR_QUALITY_FAIL";r["classification_reason"]="needs precise missing edge / row error review"
 if r["status"] not in ("PASS_FULL_MONTH","LISTING_MONTH_CANDIDATE_UNVERIFIED"):
  issues.append({"asset":asset,"month":month,"status":r["status"],"reason":r.get("classification_reason","")})
for asset in sorted({k[0] for k in by}):
 rr=sorted((r for (s,m),r in by.items() if s==asset and r.get("first_ms") and r.get("last_ms")),key=lambda r:r["month"])
 for prev,cur in zip(rr,rr[1:]):
  py,pm=map(int,prev["month"].split("-"));cy,cm=map(int,cur["month"].split("-"))
  adjacent=(cy*12+cm)-(py*12+pm)==1
  delta=(int(cur["first_ms"])-int(prev["last_ms"]))//60000
  b={"asset":asset,"from_month":prev["month"],"to_month":cur["month"],"adjacent_months":adjacent,"delta_minutes":delta,"contiguous":adjacent and delta==5}
  boundaries.append(b)
  if adjacent and delta!=5:issues.append({"asset":asset,"month":cur["month"],"status":"CROSS_MONTH_GAP","reason":f"delta {delta} minutes"})
# Check data archive SHA against manifest, without reading full archive into memory.
verified=0;missing=[]
for r in raw:
 if r["status"] not in ("PASS_FULL_MONTH","PARTIAL_FIRST_MONTH_CANDIDATE"):continue
 fp=root/"data"/f'{r["asset"]}USDT-5m-{r["month"]}.zip'
 if not fp.exists():missing.append(fp.name);continue
 h=hashlib.sha256()
 with fp.open("rb") as f:
  for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
 if h.hexdigest()!=r.get("zip_sha256"):issues.append({"asset":r["asset"],"month":r["month"],"status":"SHA_MISMATCH","reason":fp.name})
 else:verified+=1
def dumpcsv(name,rs):
 if not rs:return
 keys=list(dict.fromkeys(k for r in rs for k in r))
 with (out/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rs)
dumpcsv("inventory.csv",list(by.values()));dumpcsv("boundaries.csv",boundaries);dumpcsv("issues.csv",issues)
(out/"summary.json").write_text(json.dumps({"version":"5.0","current_batch_rows":len(raw),"cumulative_month_keys":len(by),"statuses":dict(collections.Counter(r["status"] for r in by.values())),"sha_verified_current":verified,"missing_current_data_zip":missing,"boundary_failures":[x for x in boundaries if x["adjacent_months"] and not x["contiguous"]],"issues":len(issues),"note":"Baseline inventory includes previous report metadata, not permanent raw ZIP retention. Cross-month checks require both adjacent reports."},indent=2))
print((out/"summary.json").read_text())
