#!/usr/bin/env python3
"""Read-only source diagnostics for unresolved monthly 5m archives."""
import argparse,csv,datetime as dt,hashlib,io,json,os,urllib.error,urllib.request,zipfile
p=argparse.ArgumentParser()
p.add_argument("--spec",action="append",default=[])
a=p.parse_args()
default=["SOLUSDT:2022-02","SOLUSDT:2022-04","SOLUSDT:2020-09","BNBUSDT:2020-02","LINKUSDT:2020-01","XRPUSDT:2022-02","NEARUSDT:2022-02"]
specs=a.spec or default
def iso(ms):return dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc).isoformat()
def check(spec):
 pair,month=spec.split(":");y,m=map(int,month.split("-"))
 ny,nm=(y+1,1) if m==12 else (y,m+1)
 lo=int(dt.datetime(y,m,1,tzinfo=dt.timezone.utc).timestamp()*1000)
 hi=int(dt.datetime(ny,nm,1,tzinfo=dt.timezone.utc).timestamp()*1000)
 url=f"https://data.binance.vision/data/futures/um/monthly/klines/{pair}/5m/{pair}-5m-{month}.zip"
 req=urllib.request.Request(url,headers={"User-Agent":"DetectorResearch-v56-readonly"})
 with urllib.request.urlopen(req,timeout=120) as r:raw=r.read(100_000_001)
 if len(raw)>100_000_000:raise ValueError("ZIP_TOO_LARGE")
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  if z.testzip():raise ValueError("ZIP_CRC")
  names=[n for n in z.namelist() if n.endswith(".csv")]
  if len(names)!=1:raise ValueError("CSV_COUNT")
  stamps=[];bad_ohlc=0;bad_examples=[]
  with z.open(names[0]) as f:
   for row in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")):
    if not row or not row[0].isdigit():continue
    ts=int(row[0]);stamps.append(ts)
    try:
     o,h,l,c=map(float,row[1:5]);v=float(row[5]);buy=float(row[9])
     if not(l<=min(o,c)<=max(o,c)<=h and 0<=buy<=v):
      bad_ohlc+=1
      if len(bad_examples)<5:bad_examples.append({"time":iso(ts),"ohlc":[o,h,l,c],"volume":v,"taker_buy_base":buy})
    except (ValueError,IndexError) as e:
     bad_ohlc+=1
     if len(bad_examples)<5:bad_examples.append({"time":iso(ts),"error":str(e)})
 expected=set(range(lo,hi,300000));observed=set(stamps)
 missing=sorted(expected-observed);extra=sorted(observed-expected)
 jumps=[{"from":iso(x),"to":iso(y),"delta_minutes":(y-x)/60000} for x,y in zip(stamps,stamps[1:]) if y-x!=300000]
 full=len(stamps)==len(expected) and not missing and not extra and not jumps
 start_partial=bool(stamps) and stamps[0]>lo and stamps[-1]==hi-300000 and not extra and not jumps
 status="FULL" if full else "START_PARTIAL_UNVERIFIED" if start_partial else "HISTORICAL_GAP_OR_ANOMALY"
 if bad_ohlc:status="BAD_OHLC_VOLUME"
 return {"spec":spec,"status":status,"url":url,"source_sha256":hashlib.sha256(raw).hexdigest(),"rows":len(stamps),"expected":len(expected),"first":iso(stamps[0]) if stamps else None,"last":iso(stamps[-1]) if stamps else None,"missing_count":len(missing),"missing_first":[iso(x) for x in missing[:8]],"missing_last":[iso(x) for x in missing[-8:]],"extra_count":len(extra),"duplicate_count":len(stamps)-len(observed),"jumps":jumps[:15],"bad_ohlc_volume_count":bad_ohlc,"bad_examples":bad_examples}
results=[]
for spec in specs:
 try:results.append(check(spec))
 except urllib.error.HTTPError as e:results.append({"spec":spec,"status":f"HTTP_{e.code}"})
 except Exception as e:results.append({"spec":spec,"status":"DIAGNOSTIC_ERROR","error":str(e)[:200]})
os.makedirs("detector_v56_reports",exist_ok=True)
with open("detector_v56_reports/source_diagnostics.json","w") as f:json.dump({"version":"5.6","results":results,"notes":["Source-only diagnostics; no R2 mutations","Partial start is not evidence of listing","Historical gaps are not filled","Trading code and positions unchanged"]},f,indent=2)
print(json.dumps(results,indent=2))
if any(r["status"]=="DIAGNOSTIC_ERROR" for r in results):raise SystemExit(1)
