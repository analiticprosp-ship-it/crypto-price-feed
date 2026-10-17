#!/usr/bin/env python3
"""SHADOW v2.9 funding semantics audit. No forward-fill across unknown publication time."""
import csv,gzip,io,json,urllib.request,datetime as dt,collections,math
from pathlib import Path
OUT=Path("detector_tardis_funding_v29_results");OUT.mkdir(exist_ok=True)
CASES=[("binance-futures","BTCUSDT","2021-06-01"),("bybit","BTCUSDT","2021-06-01"),("okex-swap","BTC-USDT-SWAP","2021-06-01"),("bybit","SOLUSDT","2024-06-01"),("okex-swap","SOL-USDT-SWAP","2024-06-01"),("okex-swap","HYPE-USDT-SWAP","2026-09-01")]
UTC=dt.timezone.utc
def stamp(s):
 s=str(s or "").strip()
 try:
  n=float(s)
  if not math.isfinite(n):raise ValueError("nonfinite")
  scale=1e9 if abs(n)>=1e17 else 1e6 if abs(n)>=1e14 else 1e3 if abs(n)>=1e11 else 1
  return dt.datetime.fromtimestamp(n/scale,UTC)
 except ValueError:
  t=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
  if t.tzinfo is None:raise ValueError("naive")
  return t.astimezone(UTC)
def val(x):
 try:
  if x in ("",None):return None
  v=float(x);return v if math.isfinite(v) else None
 except (ValueError,TypeError):return None
def read(e,s,d):
 y,m,day=d.split("-");url=f"https://datasets.tardis.dev/v1/{e}/derivative_ticker/{y}/{m}/{day}/{s}.csv.gz"
 req=urllib.request.Request(url,headers={"User-Agent":"detector-shadow-funding-semantics-v29"})
 with urllib.request.urlopen(req,timeout=120) as response:
  with gzip.GzipFile(fileobj=response) as gz:
   yield from csv.DictReader(io.TextIOWrapper(gz,encoding="utf-8-sig",errors="replace",newline=""))
def run(e,s,d):
 start=dt.datetime.fromisoformat(d).replace(tzinfo=UTC);end=start+dt.timedelta(days=1)
 counts=collections.Counter();examples=[];rows=[];last=None;headers=set()
 for r in read(e,s,d):
  counts["rows"]+=1;headers.update(r)
  try:t=stamp(r.get("timestamp"))
  except Exception:counts["bad_timestamp"]+=1;continue
  if not start<=t<end:counts["outside_day"]+=1;continue
  if last is not None and t<last:counts["reversals"]+=1
  last=t
  actual=val(r.get("funding_rate"));predicted=val(r.get("predicted_funding_rate"))
  raw_next=r.get("funding_timestamp")
  next_t=None
  if raw_next not in ("",None):
   try:next_t=stamp(raw_next);counts["funding_timestamp_parsed"]+=1
   except Exception:counts["funding_timestamp_bad"]+=1
  if actual is not None:counts["actual_nonempty"]+=1
  if predicted is not None:counts["predicted_nonempty"]+=1
  if actual is not None or predicted is not None:
   rows.append((t,actual,predicted,next_t))
   if len(examples)<5:examples.append({"event_utc":t.isoformat(),"actual":actual,"predicted":predicted,"funding_timestamp":next_t.isoformat() if next_t else str(raw_next)[:50]})
 rows.sort(key=lambda x:x[0])
 # As-of: last observed event < cutoff; actual/predicted tracked independently.
 timeline=[];prev={"actual":None,"predicted":None};lastchange={"actual":None,"predicted":None};lastseen={"actual":None,"predicted":None};ix=0
 for m in range(5,1441,5):
  cutoff=start+dt.timedelta(minutes=m)
  while ix<len(rows) and rows[ix][0]<cutoff:
   t,a,p,ft=rows[ix];ix+=1
   for k,v in (("actual",a),("predicted",p)):
    if v is not None:
     if prev[k] is None or prev[k]!=v:lastchange[k]=t
     prev[k]=v;lastseen[k]=t
  item={"exchange":e,"symbol":s,"day":d,"cutoff_utc":cutoff.isoformat()}
  for k in ("actual","predicted"):
   item[k+"_seen"]=lastseen[k] is not None
   item[k+"_age_since_observation_sec"]=round((cutoff-lastseen[k]).total_seconds()) if lastseen[k] else ""
   item[k+"_age_since_change_sec"]=round((cutoff-lastchange[k]).total_seconds()) if lastchange[k] else ""
   item[k+"_value"]=prev[k] if lastseen[k] else ""
   if item[k+"_seen"]:counts[k+"_asof_5m"]+=1
   if lastseen[k] and (cutoff-lastseen[k]).total_seconds()<=3600:counts[k+"_fresh_60m_5m"]+=1
  timeline.append(item)
 return {"exchange":e,"symbol":s,"day":d,"status":"AUDITED","columns":"|".join(sorted(headers)),"examples":json.dumps(examples),**counts},timeline
summary=[];timeline=[]
for e,s,d in CASES:
 try:
  r,points=run(e,s,d);summary.append(r);timeline+=points;print(e,s,r.get("actual_asof_5m",0),r.get("predicted_asof_5m",0),flush=True)
 except Exception as ex:summary.append({"exchange":e,"symbol":s,"day":d,"status":"ERROR","error":str(ex)[:300]});print("ERROR",e,s,ex,flush=True)
def csvout(name,rows):
 fields=list(dict.fromkeys(k for r in rows for k in r))
 with (OUT/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
csvout("funding_semantics_summary.csv",summary);csvout("funding_asof_5m.csv",timeline)
(OUT/"manifest.json").write_text(json.dumps({"version":"v2.9","statuses":dict(collections.Counter(r["status"] for r in summary)),"rules":["actual funding_rate and predicted_funding_rate never merged","funding_timestamp parsed separately, not assumed publication timestamp","strict exchange event time < cutoff","no extrapolation before first observation","last observed funding retained without 60m expiry for diagnostic comparison only","receipt/publication availability NOT established","no trading replay or live changes"]},indent=2))
