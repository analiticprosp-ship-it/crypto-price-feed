#!/usr/bin/env python3
"""Research-only bounded historical 5m futures metrics expansion, 2024-2026."""
import csv,datetime as dt,hashlib,io,json,pathlib,urllib.error,urllib.request,zipfile
ROOT=pathlib.Path("detector_h1_h10_metrics_history");ROOT.mkdir(exist_ok=True)
START=dt.date(2024,1,1);END=dt.date(2026,10,16)
SYMS=("BTCUSDT","ETHUSDT","SOLUSDT")
dates=[];day=START
while day<=END:
 dates.append(day.isoformat());day+=dt.timedelta(days=1)
records=[]
for sym in SYMS:
 out=ROOT/f"{sym}_metrics_5m.csv"
 with out.open("w",newline="") as f:
  writer=csv.writer(f);header=None
  for day in dates:
   url=f"https://data.binance.vision/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{day}.zip"
   rec={"symbol":sym,"date":day,"status":"UNVERIFIED"}
   try:
    req=urllib.request.Request(url,headers={"User-Agent":"Detector-H1-H10-research/1.0"})
    with urllib.request.urlopen(req,timeout=12) as r:
     raw=r.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:raise ValueError("ZIP_LIMIT")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
     names=[n for n in z.namelist() if n.endswith(".csv")]
     if len(names)!=1:raise ValueError("CSV_COUNT")
     data=z.read(names[0])
    if len(data)>4*1024*1024:raise ValueError("CSV_LIMIT")
    rows=list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    if not rows:raise ValueError("EMPTY")
    if header is None:
     header=rows[0];writer.writerow(["source_date",*header])
    if rows[0]!=header:raise ValueError("SCHEMA_CHANGED")
    if len(rows)<2:raise ValueError("NO_RECORDS")
    for row in rows[1:]:
     if len(row)!=len(header):raise ValueError("BAD_ROW_WIDTH")
    for row in rows[1:]:writer.writerow([day,*row])
    rec.update(status="DOWNLOADED_SCHEMA_MATCHED_TIME_UNVALIDATED",rows=len(rows)-1,sha256=hashlib.sha256(data).hexdigest())
   except urllib.error.HTTPError as e:rec.update(status=f"HTTP_{e.code}")
   except Exception as e:rec.update(status="ERROR",error=str(e)[:120])
   records.append(rec)
   if len(records)%50==0:print("PROGRESS",json.dumps({"done":len(records),"downloaded":sum(r["status"].startswith("DOWNLOADED") for r in records),"missing":sum(r["status"]=="HTTP_404" for r in records)}),flush=True)
   if len(records)%100==0:(ROOT/"manifest.json").write_text(json.dumps({"records":records},indent=2))
(ROOT/"manifest.json").write_text(json.dumps({"scope":"2024-01-01 through 2026-10-16; source Binance futures metrics daily archives; semantic/time validity unverified","generated_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"records":records},indent=2))
summary={"attempted":len(records),"downloaded":sum(r["status"].startswith("DOWNLOADED") for r in records),"not_found":sum(r["status"]=="HTTP_404" for r in records),"errors":sum(r["status"]=="ERROR" for r in records)}
(ROOT/"summary.json").write_text(json.dumps(summary,indent=2));print("SUMMARY",json.dumps(summary),flush=True)
