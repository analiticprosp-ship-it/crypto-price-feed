#!/usr/bin/env python3
"""SHADOW v2.7: Tardis timestamp repair and point-in-time diagnostics.
All timestamps UTC. Never infer missing timestamps or fabricate history."""
import csv,gzip,json,urllib.request,urllib.error,datetime as dt,collections,io,math
from pathlib import Path
OUT=Path("detector_tardis_time_v27_results");OUT.mkdir(exist_ok=True)
CASES=[("binance-futures","BTCUSDT","2021-06-01"),("bybit","BTCUSDT","2021-06-01"),("okex-swap","BTC-USDT-SWAP","2021-06-01"),("bybit","SOLUSDT","2024-06-01"),("okex-swap","SOL-USDT-SWAP","2024-06-01"),("okex-swap","HYPE-USDT-SWAP","2026-09-01")]
UTC=dt.timezone.utc
def parse_stamp(raw):
 s=str(raw or "").strip()
 if not s:raise ValueError("empty")
 try:
  n=float(s)
  if not math.isfinite(n):raise ValueError("nonfinite")
  size=abs(n)
  if size>=1e17:scale=1e9;unit="ns"
  elif size>=1e14:scale=1e6;unit="us"
  elif size>=1e11:scale=1e3;unit="ms"
  else:scale=1;unit="s"
  return dt.datetime.fromtimestamp(n/scale,UTC),unit
 except ValueError:
  t=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
  if t.tzinfo is None:raise ValueError("naive_iso")
  return t.astimezone(UTC),"iso"
def url(e,s,d,k):
 y,m,day=d.split("-");return f"https://datasets.tardis.dev/v1/{e}/{k}/{y}/{m}/{day}/{s}.csv.gz"
def scan(e,s,d,k):
 r=dict(exchange=e,symbol=s,day=d,kind=k,status="ERROR",rows=0,parsed=0,invalid=0,out_of_day=0,reverse=0,duplicate_timestamps=0,distinct_timestamps=0,first_utc="",last_utc="",timestamp_examples="",timestamp_formats="",oi_nonempty=0,oi_distinct=0,oi_changes=0,funding_nonempty=0,funding_distinct=0,funding_changes=0,side_buy=0,side_sell=0,side_other=0,note="")
 raw_examples=[];units=collections.Counter();seen=set();last_time=None;values={"open_interest":set(),"funding_rate":set()};prev_values={};side=collections.Counter()
 maxrows=600000 if k=="derivative_ticker" else 12000
 try:
  req=urllib.request.Request(url(e,s,d,k),headers={"User-Agent":"detector-shadow-timestamp-audit/2.7"})
  with urllib.request.urlopen(req,timeout=90) as response:
   with gzip.GzipFile(fileobj=response) as gz:
    reader=csv.DictReader(io.TextIOWrapper(gz,encoding="utf-8-sig",errors="replace",newline=""))
    if "timestamp" not in (reader.fieldnames or []):raise ValueError("NO_TIMESTAMP_COLUMN")
    for row in reader:
     if r["rows"]>=maxrows:r["status"]="TRUNCATED_ROW_CAP";break
     r["rows"]+=1
     raw=row.get("timestamp","")
     if len(raw_examples)<4:raw_examples.append(str(raw))
     try:
      t,unit=parse_stamp(raw);units[unit]+=1;r["parsed"]+=1
      if t.date().isoformat()!=d:r["out_of_day"]+=1
      if last_time is not None and t<last_time:r["reverse"]+=1
      last_time=t
      if t in seen:r["duplicate_timestamps"]+=1
      else:seen.add(t)
      if not r["first_utc"]:r["first_utc"]=t.isoformat()
      r["last_utc"]=t.isoformat()
     except (ValueError,OverflowError,OSError):r["invalid"]+=1
     for key,label in (("open_interest","oi"),("funding_rate","funding")):
      v=row.get(key)
      if v not in ("",None):
       r[label+"_nonempty"]+=1;values[key].add(v)
       if key in prev_values and v!=prev_values[key]:r[label+"_changes"]+=1
       prev_values[key]=v
     if k=="trades":side[row.get("side","")]+=1
    else:r["status"]="FULL_DAY_PARSED"
  r["distinct_timestamps"]=len(seen);r["oi_distinct"]=len(values["open_interest"]);r["funding_distinct"]=len(values["funding_rate"])
  r["timestamp_examples"]="|".join(raw_examples);r["timestamp_formats"]=json.dumps(dict(units))
  r["side_buy"]=side.get("buy",0);r["side_sell"]=side.get("sell",0);r["side_other"]=sum(v for key,v in side.items() if key not in ("buy","sell"))
  if r["invalid"] or r["out_of_day"] or r["reverse"]:r["status"]="TIME_QUALITY_FAIL_"+r["status"]
  r["note"]="Changes count consecutive nonempty values only; repeated tickers are not independent OI observations. Trades are capped at 12000 rows."
 except Exception as exc:r["status"]="REQUEST_OR_PARSE_ERROR";r["note"]=str(exc)[:240]
 return r
rows=[]
for e,s,d in CASES:
 for k in ("derivative_ticker","trades"):
  r=scan(e,s,d,k);rows.append(r);print(e,s,d,k,r["status"],r["rows"],r["timestamp_formats"],flush=True)
with (OUT/"time_quality.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(OUT/"manifest.json").write_text(json.dumps({"stage":"v2.7","statuses":dict(collections.Counter(r["status"] for r in rows)),"no_live_changes":True,"no_replay":True,"rules":["UTC only; reject naive ISO","Unix seconds/ms/us/ns supported","No timestamp substitution or forward filling","Distinct timestamp != distinct OI observation","Full day only when FULL_DAY_PARSED; trades capped 12000","Historical point-in-time feature alignment and producer-rule audit still required"]},indent=2))
