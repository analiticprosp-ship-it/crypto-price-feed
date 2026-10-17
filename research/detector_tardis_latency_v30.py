#!/usr/bin/env python3
"""Detector SHADOW v3.0: audit exchange vs collector timestamps. Not replay."""
import csv,gzip,io,json,urllib.request,datetime as dt,collections,math
from pathlib import Path
OUT=Path("detector_tardis_latency_v30_results");OUT.mkdir(exist_ok=True)
CASES=[("binance-futures","BTCUSDT","2021-06-01"),("bybit","BTCUSDT","2021-06-01"),("okex-swap","BTC-USDT-SWAP","2021-06-01"),("bybit","SOLUSDT","2024-06-01"),("okex-swap","SOL-USDT-SWAP","2024-06-01"),("okex-swap","HYPE-USDT-SWAP","2026-09-01")]
UTC=dt.timezone.utc
def parse(x):
 s=str(x or "").strip()
 if not s:raise ValueError("empty")
 try:
  n=float(s)
  if not math.isfinite(n):raise ValueError("nonfinite")
  return dt.datetime.fromtimestamp(n/(1e9 if abs(n)>=1e17 else 1e6 if abs(n)>=1e14 else 1e3 if abs(n)>=1e11 else 1),UTC)
 except ValueError:
  t=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
  if t.tzinfo is None:raise ValueError("naive")
  return t.astimezone(UTC)
def quantile(a,q):
 if not a:return ""
 a.sort();return round(a[min(len(a)-1,int((len(a)-1)*q))],3)
def run(e,s,d):
 y,m,day=d.split("-");url=f"https://datasets.tardis.dev/v1/{e}/derivative_ticker/{y}/{m}/{day}/{s}.csv.gz"
 start=dt.datetime.fromisoformat(d).replace(tzinfo=UTC);end=start+dt.timedelta(days=1)
 c=collections.Counter();lags=[];examples=[];last_local=None;out=[]
 req=urllib.request.Request(url,headers={"User-Agent":"detector-shadow-latency-v30"})
 with urllib.request.urlopen(req,timeout=120) as f:
  with gzip.GzipFile(fileobj=f) as gz:
   for row in csv.DictReader(io.TextIOWrapper(gz,encoding="utf-8-sig",newline="",errors="replace")):
    c["rows"]+=1
    try:event=parse(row.get("timestamp"));local=parse(row.get("local_timestamp"))
    except Exception:c["missing_or_invalid_time"]+=1;continue
    if not start<=event<end:c["event_outside_day"]+=1;continue
    if local<event:c["negative_lag"]+=1
    if local>=end:c["local_next_day"]+=1
    if last_local is not None and local<last_local:c["local_reversals"]+=1
    last_local=local
    lag=(local-event).total_seconds();lags.append(lag)
    if lag>1:c["lag_over_1s"]+=1
    if lag>10:c["lag_over_10s"]+=1
    if lag>60:c["lag_over_60s"]+=1
    if len(examples)<4:examples.append({"event":event.isoformat(),"local":local.isoformat(),"lag_s":lag})
    # 5m availability: an observation is only available if local_timestamp < cutoff.
    out.append((event,local))
 out.sort(key=lambda x:x[1]);idx=0;eventseen=0;localcoverage=0
 for m in range(5,1441,5):
  cutoff=start+dt.timedelta(minutes=m)
  while idx<len(out) and out[idx][1]<cutoff:idx+=1
  if idx:localcoverage+=1
 return {"exchange":e,"symbol":s,"day":d,"status":"AUDITED","rows":c["rows"],"parsed":len(lags),"lag_min_s":quantile(lags,0),"lag_p50_s":quantile(lags,.5),"lag_p95_s":quantile(lags,.95),"lag_p99_s":quantile(lags,.99),"lag_max_s":quantile(lags,1),"collector_asof_5m_points":localcoverage,"examples":json.dumps(examples),**c}
rows=[]
for e,s,d in CASES:
 try:r=run(e,s,d);rows.append(r);print(e,s,r["status"],r["lag_p99_s"],flush=True)
 except Exception as ex:rows.append({"exchange":e,"symbol":s,"day":d,"status":"ERROR","note":str(ex)[:240]});print("ERROR",e,s,ex,flush=True)
fields=list(dict.fromkeys(k for r in rows for k in r))
with (OUT/"collector_latency.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
(OUT/"manifest.json").write_text(json.dumps({"version":"v3.0","status_counts":dict(collections.Counter(r["status"] for r in rows)),"research_only":True,"cautions":["local_timestamp is collector-side timestamp, not proof of actual original Detector availability","collector_asof_5m_points only checks whether any ticker arrived, not field-specific coverage","Negative latency, timestamp disorder and late records require investigation","Original Detector price family and aggregated taker flow are not recreated here","No signals or trading changes"]},indent=2))
