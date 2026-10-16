#!/usr/bin/env python3
"""SHADOW 2.1: actual historical OHLCV ZIP integrity sample; no synthetic Detector events."""
import csv,io,json,urllib.request,urllib.error,zipfile,datetime as dt,hashlib,math,time
from pathlib import Path
from collections import Counter
out=Path("detector_historical_integrity_v21_results");out.mkdir(exist_ok=True)
events=json.loads(Path("detector-signal-events.json").read_text())["events"]
symbols=sorted({e["symbol"] for e in events})
def url(s,y,m):
 p=s+"USDT";return f"https://data.binance.vision/data/spot/monthly/klines/{p}/5m/{p}-5m-{y}-{m:02d}.zip"
def request(u,method="GET"):
 for attempt in range(3):
  try:
   with urllib.request.urlopen(urllib.request.Request(u,method=method,headers={"User-Agent":"shadow-history-integrity/2.1"}),timeout=40) as r:
    return r.read(25000001) if method=="GET" else r.status
  except urllib.error.HTTPError as ex:
   if ex.code==404:return None
   if attempt==2:raise
  except Exception:
   if attempt==2:raise
  time.sleep(attempt+1)
def audit(s,y,m):
 r=dict(symbol=s,year=y,month=m,url=url(s,y,m),status="ERROR",rows=0,missing_internal=0,duplicate=0,bad_ohlc=0,bad_volume=0,out_of_month=0,irregular=0,sha256="",error="")
 try:
  b=request(r["url"])
  if not b:raise ValueError("archive_missing")
  if len(b)>25000000:raise ValueError("archive_over_25mb")
  r["sha256"]=hashlib.sha256(b).hexdigest()
  with zipfile.ZipFile(io.BytesIO(b)) as z:
   if z.testzip():raise ValueError("zip_crc")
   names=[n for n in z.namelist() if n.endswith(".csv")]
   if len(names)!=1:raise ValueError("csv_count")
   raw=z.read(names[0]).decode("utf-8-sig")
  start=int(dt.datetime(y,m,1,tzinfo=dt.timezone.utc).timestamp()*1000)
  end=int(dt.datetime(y+1,1,1,tzinfo=dt.timezone.utc).timestamp()*1000) if m==12 else int(dt.datetime(y,m+1,1,tzinfo=dt.timezone.utc).timestamp()*1000)
  seen=set();prev=None
  for a in csv.reader(io.StringIO(raw)):
   if not a:continue
   try:t=int(a[0])
   except ValueError:
    if a[0].lower().startswith("open"):continue
    raise
   if t>10**14:t//=1000
   o,h,l,c,v=map(float,a[1:6]);r["rows"]+=1
   if t in seen:r["duplicate"]+=1
   seen.add(t)
   if not start<=t<end:r["out_of_month"]+=1
   if not all(map(math.isfinite,(o,h,l,c,v))) or min(o,h,l,c)<=0 or h<max(o,l,c) or l>min(o,h,c):r["bad_ohlc"]+=1
   if not math.isfinite(v) or v<0:r["bad_volume"]+=1
   if prev is not None:
    if t<=prev or (t-prev)%300000:r["irregular"]+=1
    if t>prev+300000:r["missing_internal"]+=(t-prev)//300000-1
   prev=t
  if r["rows"]==0:raise ValueError("empty")
  r["status"]="PASS" if not any(r[k] for k in ("duplicate","bad_ohlc","bad_volume","out_of_month","irregular")) else "FAIL"
 except Exception as ex:r["error"]=str(ex)[:160]
 return r
rows=[];coverage=[]
for s in symbols:
 available=[]
 for y in range(2019,2027):
  for m in range(1,13):
   if (y,m)>(2026,9):continue
   try:status=request(url(s,y,m),"HEAD")
   except Exception:status="ERROR"
   coverage.append(dict(symbol=s,year=y,month=m,status="AVAILABLE" if status==200 else "NOT_FOUND" if status is None else "ERROR"))
   if status==200:available.append((y,m))
 if not available:continue
 for i in sorted({0,len(available)//2,len(available)-1}):
  y,m=available[i];r=audit(s,y,m);rows.append(r);print(s,y,m,r["status"],flush=True)
def write(name,records):
 if not records:return
 with (out/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
write("sample_archive_integrity.csv",rows)
write("month_coverage_recheck.csv",coverage)
write("feature_replay_gate.csv",[
 dict(feature="Binance spot OHLCV 5m",status="SAMPLED_ONLY",note="Only sampled ZIPs have contents audited"),
 dict(feature="OKX SWAP OHLCV",status="NOT_AUDITED",note="Original event evaluation venue differs"),
 dict(feature="BTC relative strength",status="CONDITIONAL",note="Needs aligned candles and exact original formula"),
 dict(feature="historical OI",status="UNVERIFIED",note="No point-in-time OI archive validated"),
 dict(feature="funding",status="UNVERIFIED",note="No historical source validated"),
 dict(feature="aggregated taker flow",status="UNVERIFIED",note="OHLCV volume cannot replace original flow"),
 dict(feature="exact detector signal replay",status="BLOCKED",note="Original full features and detection code not yet audited")])
manifest={"stage":"SAMPLED_HISTORICAL_INTEGRITY_V2.1","status_counts":dict(Counter(r["status"] for r in rows)),"samples":len(rows),"symbols":len(symbols),
 "rule":"first, median, last verified available monthly ZIP per symbol, through September 2026",
 "limitations":["Only sample months verified; no inference about other months","First listing month may be partial","No historical detector signals generated","No OI or taker-flow reconstructed","No live trading changes"]}
(out/"manifest.json").write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
