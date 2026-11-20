#!/usr/bin/env python3
"""Read-only Parquet L2 schema and timestamp inspection; no unproven replay."""
import argparse,collections,datetime as dt,json,pathlib,hashlib
import pyarrow.parquet as pq
def main():
 p=argparse.ArgumentParser();p.add_argument("--raw-dir",required=True);p.add_argument("--receipts-dir",required=True);p.add_argument("--out",required=True);a=p.parse_args()
 raw=pathlib.Path(a.raw_dir);receipt=pathlib.Path(a.receipts_dir)
 manifest=json.loads((receipt/"probe_manifest.json").read_text())
 result=[]
 for r in manifest["rows"]:
  if r["status"]!="DOWNLOADED_UNVALIDATED_L2":continue
  file=raw/pathlib.Path(r["local_file"]).name
  x={"path_candidate":r["path_candidate"],"filename":file.name,"status":"NOT_VERIFIED"}
  try:
   h=hashlib.sha256()
   with file.open("rb") as f:
    for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
   if h.hexdigest()!=r["sha256"] or file.stat().st_size!=r["bytes"]:
    x["status"]="HASH_MISMATCH";result.append(x);continue
   pf=pq.ParquetFile(file)
   x.update(status="SCHEMA_READ_OK_SEQUENCE_UNTESTED",rows=pf.metadata.num_rows,row_groups=pf.num_row_groups,
    columns=[{"name":z.name,"type":str(z.type)} for z in pf.schema_arrow])
   if pf.metadata.num_rows==0:x["status"]="EMPTY_FILE"
  except Exception as e:x.update(status="PARQUET_READ_ERROR",error=str(e)[:300])
  result.append(x)
 out={"schema":"P3_L2_PARQUET_SCHEMA_AUDIT_V1","generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
 "note":"No order-book reconstruction, sequence continuity or +/-1pct depth validated","results":result}
 pathlib.Path(a.out).write_text(json.dumps(out,indent=2)+"\n")
 print(json.dumps(collections.Counter(x["status"] for x in result)))
 if any(x["status"]!="SCHEMA_READ_OK_SEQUENCE_UNTESTED" for x in result):raise SystemExit("Some files fail schema/hash validation")
if __name__=="__main__":main()
