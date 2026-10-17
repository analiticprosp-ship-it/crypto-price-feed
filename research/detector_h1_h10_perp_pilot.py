#!/usr/bin/env python3
"""Bounded, read-only discovery of historical futures flow/funding/OI sources."""
import csv,datetime as dt,hashlib,io,json,pathlib,urllib.error,urllib.request,zipfile
ROOT=pathlib.Path("detector_h1_h10_perp_pilot");ROOT.mkdir(exist_ok=True)
DAY="2026-10-01";SYMS=["BTCUSDT","ETHUSDT","SOLUSDT"]
TEMPLATES={
 "spot_aggTrades":"spot/daily/aggTrades/{s}/{s}-aggTrades-{d}.zip",
 "perp_aggTrades":"futures/um/daily/aggTrades/{s}/{s}-aggTrades-{d}.zip",
 "perp_fundingRate":"futures/um/daily/fundingRate/{s}/{s}-fundingRate-{d}.zip",
 "perp_metrics":"futures/um/daily/metrics/{s}/{s}-metrics-{d}.zip",
}
records=[]
for dataset,path in TEMPLATES.items():
 for sym in SYMS:
  url="https://data.binance.vision/data/"+path.format(s=sym,d=DAY)
  rec={"dataset":dataset,"symbol":sym,"date":DAY,"url":url,"status":"UNVERIFIED"}
  try:
   req=urllib.request.Request(url,method="HEAD",headers={"User-Agent":"Detector-H1-H10-Research/1.0"})
   with urllib.request.urlopen(req,timeout=20) as r:
    rec.update(http_status=r.status,content_length=r.headers.get("Content-Length"),last_modified=r.headers.get("Last-Modified"))
   if rec["http_status"]!=200:raise ValueError("HEAD_NOT_200")
   size=int(rec["content_length"] or 0)
   # Funding and metrics only: bounded sample download; large aggTrades require separate streaming job.
   if dataset not in ("perp_fundingRate","perp_metrics"):
    rec["status"]="AVAILABLE_METADATA_ONLY"
   elif size>6*1024*1024:
    rec["status"]="AVAILABLE_TOO_LARGE_FOR_PILOT"
   else:
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Detector-H1-H10-Research/1.0"}),timeout=30) as r:
     raw=r.read(6*1024*1024+1)
    if len(raw)>6*1024*1024:raise ValueError("ZIP_LIMIT")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
     names=[n for n in z.namelist() if n.endswith(".csv")]
     if len(names)!=1:raise ValueError("UNEXPECTED_CSV_COUNT")
     data=z.read(names[0])
    if len(data)>12*1024*1024:raise ValueError("CSV_LIMIT")
    rows=list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    rec.update(status="DOWNLOADED_UNVALIDATED_SEMANTICS",rows=len(rows),header=rows[0][:20] if rows else [],zip_sha256=hashlib.sha256(raw).hexdigest(),csv_sha256=hashlib.sha256(data).hexdigest())
    (ROOT/f"{dataset}_{sym}_{DAY}.csv").write_bytes(data)
  except urllib.error.HTTPError as e:rec.update(status=f"HTTP_{e.code}",error=str(e)[:180])
  except Exception as e:rec.update(status="ERROR",error=str(e)[:180])
  records.append(rec)
  print(json.dumps({k:rec.get(k) for k in ("dataset","symbol","status","rows","content_length","error")}),flush=True)
(ROOT/"manifest.json").write_text(json.dumps({"generated_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"scope":"bounded availability and schema pilot; no flow direction inference, no OI historical validation","records":records},ensure_ascii=False,indent=2))
print("SUMMARY",json.dumps({"total":len(records),"downloaded":sum(r["status"]=="DOWNLOADED_UNVALIDATED_SEMANTICS" for r in records),"metadata_only":sum(r["status"]=="AVAILABLE_METADATA_ONLY" for r in records),"missing_or_error":sum(r["status"].startswith(("HTTP_","ERROR")) for r in records)}))
