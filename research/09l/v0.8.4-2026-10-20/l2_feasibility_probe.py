#!/usr/bin/env python3
"""09L v0.8.4C: feasibility audit only. No raw data published, no trading authority."""
import urllib.request,gzip,io,json,time
from pathlib import Path
u="https://datasets.tardis.dev/v1/bybit/incremental_book_L2/2026/10/01/BTCUSDT.csv.gz"
out={"study":"09L v0.8.4C L2 source feasibility","url":u,"date":"2026-10-20","status":"UNTESTED","raw_data_published":False,"trading_changes":"NONE"}
for method in ["HEAD","GET"]:
 try:
  r=urllib.request.urlopen(urllib.request.Request(u,method=method,headers={"User-Agent":"09L-research-feasibility-v084c"}),timeout=65)
  q={"method":method,"http":r.status,"content_length":r.headers.get("Content-Length"),"content_type":r.headers.get("Content-Type"),"accept_ranges":r.headers.get("Accept-Ranges")}
  if method=="GET":
   # limited decompression to verify schema; no full ingestion here
   stream=gzip.GzipFile(fileobj=r)
   line=stream.readline(2048).decode("utf-8","replace").strip()
   q["schema_columns"]=line.split(",") if line else []
   samples=[]
   for _ in range(3):
    s=stream.readline(2048).decode("utf8","replace").strip()
    if s:
     a=s.split(",")
     samples.append({"column_count":len(a),"sample_symbol":a[1] if len(a)>1 else None,"is_snapshot":a[4] if len(a)>4 else None})
   q["sample_rows_shape"]=samples
   r.close()
  out[method.lower()]=q
 except Exception as exc:out[method.lower()]={"status":"SOURCE_UNAVAILABLE_OR_ERROR","error":type(exc).__name__+": "+str(exc)[:250]}
out["status"]="SCHEMA_PROBED" if out.get("get",{}).get("schema_columns") else "SOURCE_UNAVAILABLE_OR_ERROR"
p=Path("research/09l/v0.8.4-2026-10-20/derived/l2_source_feasibility_2026-10-01.json")
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps(out,indent=2)+"\n")
print(json.dumps(out),flush=True)
