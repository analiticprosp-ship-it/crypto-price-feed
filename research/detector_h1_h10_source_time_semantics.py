#!/usr/bin/env python3
"""Independently inspect Binance archive timestamp semantics; no live availability claims."""
import csv,io,json,zipfile,urllib.request,datetime as dt,pathlib,collections
OUT=pathlib.Path("detector_h1_h10_source_time_semantics");OUT.mkdir(exist_ok=True)
report={"purpose":"Independent archive schema/timestamp audit","limits":["Archive timestamps do not prove publication latency or realtime availability","Hourly archive timestamps are inspected against their own UTC hour boundaries; masked-price construction still requires separate reconciliation"],"metrics":[],"hourly":[]}
def load(url,maxbytes=45_000_000):
 with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Detector-Research/1.0"}),timeout=90) as r:
  b=io.BytesIO()
  while True:
   c=r.read(1024*1024)
   if not c:break
   if b.tell()+len(c)>maxbytes:raise ValueError("archive_size_limit")
   b.write(c)
 with zipfile.ZipFile(b) as z:
  names=[n for n in z.namelist() if n.endswith(".csv")]
  if len(names)!=1:raise ValueError("csv_entries_not_one")
  with z.open(names[0]) as f:
   reader=csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig",newline=""))
   head=next(reader)
   rows=[]
   for i,row in enumerate(reader):
    if i<5:rows.append(row)
    else:break
 return {"zip_bytes":b.tell(),"header":head,"sample":rows}
for sym in ("BTCUSDT","ETHUSDT","SOLUSDT"):
 url=f"https://data.binance.vision/data/futures/um/daily/metrics/{sym}/{sym}-metrics-2026-09-01.zip"
 item={"symbol":sym,"url":url}
 try:
  a=load(url);item.update(a);item["status"]="READ"
  # ISO time from source sample, no claims about publication
  for row in a["sample"][:3]:
   item.setdefault("sample_create_time",[]).append(row[0] if row else "")
 except Exception as e:item.update({"status":"ERROR","error":str(e)})
 report["metrics"].append(item);print("METRICS",sym,item["status"],flush=True)
 for market in ("spot","futures/um"):
  url=f"https://data.binance.vision/data/{market}/monthly/klines/{sym}/1h/{sym}-1h-2026-09.zip"
  item={"symbol":sym,"market":market,"url":url}
  try:
   a=load(url);item.update(a);item["status"]="READ"
   parsed=[]
   for row in a["sample"]:
    try:
     t=int(row[0]);t=t//1000 if t>10**14 else t
     ts=dt.datetime.fromtimestamp(t/1000,dt.timezone.utc)
     parsed.append({"open_time":ts.isoformat(),"on_utc_hour":ts.minute==0 and ts.second==0,"raw_close_time":row[6] if len(row)>6 else None})
    except Exception as e:parsed.append({"error":str(e)})
   item["parsed"]=parsed
  except Exception as e:item.update({"status":"ERROR","error":str(e)})
  report["hourly"].append(item);print("HOURLY",sym,market,item["status"],flush=True)
(OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print("SUMMARY",json.dumps({"metrics_read":sum(x["status"]=="READ" for x in report["metrics"]),"hourly_read":sum(x["status"]=="READ" for x in report["hourly"])}),flush=True)
