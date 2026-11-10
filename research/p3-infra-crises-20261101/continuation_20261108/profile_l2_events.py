#!/usr/bin/env python3
"""P3 read-only L2 event profiling: inspect actual values, never infer book replay."""
import argparse,collections,datetime as dt,hashlib,json,pathlib
import pyarrow.parquet as pq
def safe(v):
 if isinstance(v,bytes):return "<binary>"
 if isinstance(v,(dt.datetime,dt.date)):return v.isoformat()
 s=str(v);return s[:160]
def main():
 p=argparse.ArgumentParser();p.add_argument("--raw-dir",required=True);p.add_argument("--receipts-dir",required=True);p.add_argument("--out",required=True);p.add_argument("--sample-rows",type=int,default=3000);a=p.parse_args()
 manifest=json.loads((pathlib.Path(a.receipts_dir)/"probe_manifest.json").read_text());root=pathlib.Path(a.raw_dir)
 results=[]
 for r in manifest["rows"]:
  x={"venue":r["venue"],"date":r["date"],"symbol":r["symbol_candidate"],"path":r["path_candidate"],"source_status":r["status"],"status":"NOT_DOWNLOADED"}
  if r["status"]!="DOWNLOADED_UNVALIDATED_L2":results.append(x);continue
  f=root/pathlib.Path(r["local_file"]).name
  try:
   h=hashlib.sha256()
   with f.open("rb") as fd:
    for b in iter(lambda:fd.read(1024*1024),b""):h.update(b)
   if h.hexdigest()!=r["sha256"] or f.stat().st_size!=r["bytes"]:raise ValueError("HASH_OR_SIZE_MISMATCH")
   pf=pq.ParquetFile(f)
   x.update(status="PROFILED_REPLAY_NOT_VALIDATED",total_rows=pf.metadata.num_rows,row_groups=pf.num_row_groups,columns=[{"name":field.name,"type":str(field.type)} for field in pf.schema_arrow])
   sample=pf.read_row_group(0).slice(0,a.sample_rows) if pf.num_row_groups else None
   if sample is not None:
    profiles=[]
    for col in sample.column_names:
     vals=sample.column(col).to_pylist()
     nonnull=[v for v in vals if v is not None]
     item={"column":col,"sample_nonnull":len(nonnull),"sample_null":len(vals)-len(nonnull)}
     if nonnull:
      item["examples"]=[safe(v) for v in nonnull[:3]]
      if all(isinstance(v,(str,int,float,bool,dt.datetime)) for v in nonnull):
       item["distinct_sample_count"]=len({safe(v) for v in nonnull})
       if any(k in col.lower() for k in ("time","stamp","date","seq","update","id")):
        try:item["sample_min"]=safe(min(nonnull));item["sample_max"]=safe(max(nonnull))
        except (TypeError,ValueError):pass
     profiles.append(item)
    x["column_profiles"]=profiles
  except Exception as e:x.update(status="PROFILE_ERROR",error=str(e)[:300])
  results.append(x)
 output={"schema":"P3_L2_EVENT_PROFILE_V1","generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"note":"Examples are for schema identification, NOT proof of sequence continuity or book depth. All statuses remain research-only.","results":results}
 pathlib.Path(a.out).write_text(json.dumps(output,indent=2,ensure_ascii=False)+"\n")
 print(json.dumps(dict(collections.Counter(x["status"] for x in results))))
 if any(x["status"]=="PROFILE_ERROR" for x in results):raise SystemExit("Some downloaded files could not be profiled")
if __name__=="__main__":main()
