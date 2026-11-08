#!/usr/bin/env python3
"""P3 L2 metadata diagnostics. Counts event groups; no claim of valid order book replay."""
import argparse,collections,datetime as dt,json,pathlib
import pyarrow.parquet as pq
def main():
 p=argparse.ArgumentParser();p.add_argument("--raw-dir",required=True);p.add_argument("--receipts-dir",required=True);p.add_argument("--out",required=True);a=p.parse_args()
 manifest=json.loads((pathlib.Path(a.receipts_dir)/"probe_manifest.json").read_text());results=[]
 for r in manifest["rows"]:
  if r["status"]!="DOWNLOADED_UNVALIDATED_L2":continue
  f=pathlib.Path(a.raw_dir)/pathlib.Path(r["local_file"]).name
  x={"venue":r["venue"],"date":r["date"],"symbol":r["symbol_candidate"],"status":"NOT_ANALYZED"}
  try:
   pf=pq.ParquetFile(f);counts=collections.Counter();sides=collections.Counter();times=[];update_ids=[];nulls=collections.Counter()
   columns=["event_type","side","event_time","first_update_id","final_update_id","prev_final_update_id","last_update_id"]
   for batch in pf.iter_batches(batch_size=200000,columns=columns):
    data=batch.to_pydict();n=len(data["event_type"])
    for i in range(n):
     event=data["event_type"][i];counts[str(event)]+=1;sides[str(data["side"][i])]+=1
     t=data["event_time"][i]
     if t is not None:times.append(t)
     for col in columns[3:]:
      v=data[col][i]
      if v is None:nulls[col]+=1
      elif col=="final_update_id":update_ids.append(v)
   x.update(status="METADATA_COUNTS_ONLY",rows=sum(counts.values()),event_types=dict(counts),sides=dict(sides),null_update_ids=dict(nulls),event_time_min=min(times) if times else None,event_time_max=max(times) if times else None,final_update_id_min=min(update_ids) if update_ids else None,final_update_id_max=max(update_ids) if update_ids else None)
  except Exception as e:x.update(status="ERROR",error=str(e)[:300])
  results.append(x)
 out={"schema":"P3_L2_EVENT_COUNTS_V1","generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"note":"Event counts and ID ranges do not prove sequence continuity or replay validity","results":results}
 pathlib.Path(a.out).write_text(json.dumps(out,indent=2,default=str)+"\n")
 print(json.dumps(dict(collections.Counter(x["status"] for x in results))))
 if any(x["status"]=="ERROR" for x in results):raise SystemExit("L2 event diagnostic errors")
if __name__=="__main__":main()
