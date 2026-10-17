#!/usr/bin/env python3
"""Read-only source diagnostics for historical Binance USD-M 5m month anomalies."""
import argparse,csv,datetime as dt,io,json,urllib.request,zipfile,hashlib
p=argparse.ArgumentParser()
p.add_argument("--symbols",nargs="+",default=["XRPUSDT:2022-02","NEARUSDT:2022-02"])
a=p.parse_args()
def iso(ms):return dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc).isoformat()
def inspect(spec):
 pair,month=spec.split(":")
 y,m=map(int,month.split("-")); ny,nm=(y+1,1) if m==12 else (y,m+1)
 lo=int(dt.datetime(y,m,1,tzinfo=dt.timezone.utc).timestamp()*1000)
 hi=int(dt.datetime(ny,nm,1,tzinfo=dt.timezone.utc).timestamp()*1000)
 url=f"https://data.binance.vision/data/futures/um/monthly/klines/{pair}/5m/{pair}-5m-{month}.zip"
 req=urllib.request.Request(url,headers={"User-Agent":"DetectorResearch-v53-readonly"})
 with urllib.request.urlopen(req,timeout=120) as r:raw=r.read(100_000_001)
 if len(raw)>100_000_000:raise ValueError("SIZE_CAP")
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  if z.testzip():raise ValueError("CRC_FAILURE")
  names=[n for n in z.namelist() if n.lower().endswith(".csv")]
  if len(names)!=1:raise ValueError("CSV_COUNT")
  stamps=[]
  with z.open(names[0]) as f:
   for row in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")):
    if row and row[0].isdigit():stamps.append(int(row[0]))
 expected=set(range(lo,hi,300000)); observed=set(stamps)
 missing=sorted(expected-observed); extra=sorted(observed-expected)
 duplicate_count=len(stamps)-len(observed)
 jumps=[{"from":iso(x),"to":iso(y),"delta_minutes":(y-x)/60000} for x,y in zip(stamps,stamps[1:]) if y-x!=300000]
 complete=not missing and not extra and not duplicate_count and len(stamps)==len(expected)
 first_only=(stamps and stamps[0]>lo and stamps[-1]==hi-300000 and not extra and not duplicate_count and not jumps and len(stamps)==(hi-stamps[0])//300000)
 classification="FULL" if complete else "PARTIAL_START_UNVERIFIED_LISTING" if first_only else "HISTORICAL_GAP_OR_SOURCE_ANOMALY"
 return {"pair":pair,"month":month,"source":url,"zip_sha256":hashlib.sha256(raw).hexdigest(),"classification":classification,"rows":len(stamps),"expected_rows":len(expected),"first":iso(stamps[0]) if stamps else None,"last":iso(stamps[-1]) if stamps else None,"missing_count":len(missing),"missing_first_20":[iso(x) for x in missing[:20]],"missing_last_20":[iso(x) for x in missing[-20:]],"extra_count":len(extra),"duplicates":duplicate_count,"non_5m_transitions":jumps[:30],"limitations":"No independent listing verification; no data repair or trading changes"}
results=[]
for spec in a.symbols:
 try:results.append(inspect(spec))
 except Exception as e:results.append({"spec":spec,"classification":"DIAGNOSTIC_ERROR","error":str(e)[:250]})
import pathlib
pathlib.Path("detector_v53_reports").mkdir(exist_ok=True)
with open("detector_v53_reports/anomalies.json","w") as f:json.dump(results,f,indent=2)
print(json.dumps(results,indent=2))
if any(x["classification"]=="DIAGNOSTIC_ERROR" for x in results):raise SystemExit(1)
