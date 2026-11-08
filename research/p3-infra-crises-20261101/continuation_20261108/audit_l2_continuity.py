#!/usr/bin/env python3
"""P3 bounded-memory event continuity audit. Does NOT claim valid book replay."""
import argparse,collections,datetime as dt,json,pathlib
import pyarrow.parquet as pq
def main():
 p=argparse.ArgumentParser();p.add_argument("--raw-dir",required=True);p.add_argument("--receipts-dir",required=True);p.add_argument("--out",required=True);a=p.parse_args()
 manifest=json.loads((pathlib.Path(a.receipts_dir)/"probe_manifest.json").read_text());results=[]
 for r in manifest["rows"]:
  if r["status"]!="DOWNLOADED_UNVALIDATED_L2":continue
  f=pathlib.Path(a.raw_dir)/pathlib.Path(r["local_file"]).name
  x={"venue":r["venue"],"date":r["date"],"symbol":r["symbol_candidate"],"status":"NOT_TESTED"}
  try:
   pf=pq.ParquetFile(f);events=collections.Counter();prev_time=None;time_regressions=0;first_time=None;last_time=None
   prev_final=None;id_regressions=0;id_gaps=0;id_overlaps=0;id_comparisons=0;sample_issues=[]
   for batch in pf.iter_batches(batch_size=100000,columns=["event_type","event_time","first_update_id","final_update_id","prev_final_update_id"]):
    d=batch.to_pydict()
    for e,t,first,final,previous in zip(d["event_type"],d["event_time"],d["first_update_id"],d["final_update_id"],d["prev_final_update_id"]):
     events[str(e)]+=1
     if t is not None:
      if first_time is None:first_time=t
      if prev_time is not None and t<prev_time:time_regressions+=1
      prev_time=t;last_time=t
     if final is not None and prev_final is not None:
      id_comparisons+=1
      if final<prev_final:id_regressions+=1
      if first is not None and first>prev_final+1:id_gaps+=1
      if first is not None and first<=prev_final:id_overlaps+=1
      if previous is not None and previous!=prev_final and len(sample_issues)<10:
       sample_issues.append({"previous_id":previous,"observed_prior_final":prev_final,"current_first":first,"current_final":final})
     if final is not None:prev_final=final
   x.update(status="DIAGNOSTIC_ONLY_NOT_REPLAYED",events=dict(events),first_event_time=first_time,last_event_time=last_time,time_regressions=time_regressions,id_comparisons=id_comparisons,id_regressions=id_regressions,id_gaps_candidate=id_gaps,id_overlaps_candidate=id_overlaps,sample_prev_id_mismatches=sample_issues)
  except Exception as e:x.update(status="ERROR",error=str(e)[:300])
  results.append(x)
 out={"schema":"P3_L2_CONTINUITY_DIAGNOSTIC_V1","generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"caveat":"IDs may be per exchange, instrument, event type or snapshot; naive adjacency is NOT definitive continuity. No book reconstruction, checksums, depth or spreads validated.","results":results}
 pathlib.Path(a.out).write_text(json.dumps(out,indent=2,default=str)+"\n")
 print(json.dumps(dict(collections.Counter(x["status"] for x in results))))
 if any(x["status"]=="ERROR" for x in results):raise SystemExit("Continuity diagnostics errors")
if __name__=="__main__":main()
