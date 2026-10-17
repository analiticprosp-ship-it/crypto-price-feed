#!/usr/bin/env python3
"""Detector SHADOW v3.1: field-specific point-in-time coverage using collector timestamps.
No trading signals or claims of exact Detector replay."""
import csv,gzip,io,json,urllib.request,datetime as dt,collections,math,bisect
from pathlib import Path
OUT=Path("detector_tardis_field_asof_v31_results");OUT.mkdir(exist_ok=True)
CASES=[("binance-futures","BTCUSDT","2021-06-01"),("bybit","BTCUSDT","2021-06-01"),("okex-swap","BTC-USDT-SWAP","2021-06-01"),("bybit","SOLUSDT","2024-06-01"),("okex-swap","SOL-USDT-SWAP","2024-06-01"),("okex-swap","HYPE-USDT-SWAP","2026-09-01")]
UTC=dt.timezone.utc
def parse(s):
 s=str(s or "").strip()
 if not s:raise ValueError("empty")
 try:
  n=float(s)
  if not math.isfinite(n):raise ValueError("nonfinite")
  return dt.datetime.fromtimestamp(n/(1e9 if abs(n)>=1e17 else 1e6 if abs(n)>=1e14 else 1e3 if abs(n)>=1e11 else 1),UTC)
 except ValueError:
  t=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
  if t.tzinfo is None:raise ValueError("naive")
  return t.astimezone(UTC)
def val(x):
 try:
  if x is None or str(x).strip()=="":return None
  y=float(x)
  return y if math.isfinite(y) else None
 except (ValueError,TypeError):return None
def run(e,s,d):
 y,m,day=d.split("-");url=f"https://datasets.tardis.dev/v1/{e}/derivative_ticker/{y}/{m}/{day}/{s}.csv.gz"
 start=dt.datetime.fromisoformat(d).replace(tzinfo=UTC);end=start+dt.timedelta(days=1)
 c=collections.Counter();obs={"oi":[],"funding":[],"predicted":[]};examples=[]
 req=urllib.request.Request(url,headers={"User-Agent":"detector-shadow-field-asof-v31"})
 with urllib.request.urlopen(req,timeout=120) as f:
  with gzip.GzipFile(fileobj=f) as gz:
   for row in csv.DictReader(io.TextIOWrapper(gz,encoding="utf-8-sig",newline="",errors="replace")):
    c["rows"]+=1
    try:event=parse(row.get("timestamp"));local=parse(row.get("local_timestamp"))
    except Exception:c["bad_time"]+=1;continue
    if not start<=event<end:c["event_outside"]+=1;continue
    if local<event:c["negative_latency"]+=1;continue
    if local>=end:c["received_next_day"]+=1;continue
    for label,col in (("oi","open_interest"),("funding","funding_rate"),("predicted","predicted_funding_rate")):
     value=val(row.get(col))
     if value is not None:
      obs[label].append((local,event,value))
      c[label+"_valid_rows"]+=1
    if len(examples)<2:examples.append({"event":event.isoformat(),"received":local.isoformat()})
 for seq in obs.values():seq.sort(key=lambda z:(z[0],z[1]))
 points=[]
 for m in range(5,1441,5):
  cutoff=start+dt.timedelta(minutes=m)
  item={"exchange":e,"symbol":s,"day":d,"cutoff_utc":cutoff.isoformat()}
  for label,seq in obs.items():
   times=[z[0] for z in seq]
   i=bisect.bisect_left(times,cutoff)-1
   if i<0:item[label+"_seen"]=False;item[label+"_fresh60"]=False;item[label+"_age_sec"]="";continue
   age=(cutoff-seq[i][0]).total_seconds()
   item[label+"_seen"]=True;item[label+"_fresh60"]=age<=3600;item[label+"_age_sec"]=round(age,3)
   c[label+"_asof_points"]+=1
   if age<=3600:c[label+"_fresh60_points"]+=1
  points.append(item)
 return {"exchange":e,"symbol":s,"day":d,"status":"AUDITED","sample_timestamps":json.dumps(examples),**c},points
summ=[];pts=[]
for e,s,d in CASES:
 try:
  row,p=run(e,s,d);summ.append(row);pts.extend(p)
  print(e,s,"OI",row.get("oi_asof_points",0),"fund",row.get("funding_asof_points",0),flush=True)
 except Exception as ex:
  summ.append({"exchange":e,"symbol":s,"day":d,"status":"ERROR","error":str(ex)[:300]});print("ERROR",e,s,ex,flush=True)
def save(name,rows):
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with (OUT/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
save("field_coverage_summary.csv",summ);save("field_asof_5m.csv",pts)
(OUT/"manifest.json").write_text(json.dumps({"version":"v3.1","statuses":dict(collections.Counter(r["status"] for r in summ)),"constraints":["Field-specific availability: nonempty value with local_timestamp strictly before cutoff","Negative latency excluded, not corrected","No prior-day warmup; first interval may be unavailable","Funding last-observed and 60min-fresh are both reported; no assertion of settled vs predicted meaning","Collector arrival time is not original Detector receipt time","No trading signals or original producer formula replay","No changes to live detector, Futures, NAV or trading limits"]},indent=2))
