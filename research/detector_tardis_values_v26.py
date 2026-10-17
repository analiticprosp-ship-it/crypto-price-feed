#!/usr/bin/env python3
"""SHADOW v2.6: full-day Tardis derivative ticker completeness + bounded trade samples.
Reports actual observed rows only. Does not infer continuous 5-7 year coverage."""
import csv,gzip,json,urllib.request,urllib.error,datetime as dt,collections,io,time
from pathlib import Path
OUT=Path("detector_tardis_values_v26_results");OUT.mkdir(exist_ok=True)
CASES=[("binance-futures","BTCUSDT","2021-06-01"),("bybit","BTCUSDT","2021-06-01"),("okex-swap","BTC-USDT-SWAP","2021-06-01"),("bybit","SOLUSDT","2024-06-01"),("okex-swap","SOL-USDT-SWAP","2024-06-01"),("okex-swap","HYPE-USDT-SWAP","2026-09-01")]
def url(e,s,d,k):
 y,m,day=d.split("-");return f"https://datasets.tardis.dev/v1/{e}/{k}/{y}/{m}/{day}/{s}.csv.gz"
def stream_csv(u,max_compressed=65000000,max_rows=300000,timeout=65):
 req=urllib.request.Request(u,headers={"User-Agent":"detector-shadow-value-audit/2.6"})
 with urllib.request.urlopen(req,timeout=timeout) as response:
  length=response.headers.get("Content-Length")
  if length and int(length)>max_compressed:raise ValueError("CONTENT_LENGTH_EXCEEDS_CAP:"+length)
  # Stream gzip rather than reading archive into memory.
  with gzip.GzipFile(fileobj=response) as g:
   reader=csv.DictReader(io.TextIOWrapper(g,encoding="utf-8-sig",errors="replace",newline=""))
   fields=reader.fieldnames or []
   for i,row in enumerate(reader):
    if i>=max_rows:yield fields,None;return
    yield fields,row
def audit(e,s,d,k):
 r=dict(exchange=e,symbol=s,day=d,kind=k,status="ERROR",rows=0,first_timestamp="",last_timestamp="",nonempty_oi=0,nonempty_funding=0,nonempty_predicted=0,side_buy=0,side_sell=0,other_side=0,fields="",note="")
 first=None;last=None;side=collections.Counter();ts_invalid=0;out_of_day=0;previous=None;reverse=0;oi_samples=[];fund_samples=[]
 try:
  for fields,row in stream_csv(url(e,s,d,k),max_rows=250000 if k=="derivative_ticker" else 12000):
   r["fields"]="|".join(fields)
   if row is None:r["status"]="TRUNCATED_ROW_CAP";break
   r["rows"]+=1
   stamp=row.get("timestamp","")
   try:
    t=dt.datetime.fromisoformat(stamp.replace("Z","+00:00"))
    if t.tzinfo is None:t=t.replace(tzinfo=dt.timezone.utc)
    if t.date().isoformat()!=d:out_of_day+=1
    if previous is not None and t<previous:reverse+=1
    previous=t
    if first is None:first=stamp
    last=stamp
   except Exception:ts_invalid+=1
   for col,key,examples in (("open_interest","nonempty_oi",oi_samples),("funding_rate","nonempty_funding",fund_samples),("predicted_funding_rate","nonempty_predicted",[])):
    value=row.get(col)
    if value not in ("",None):
     r[key]+=1
     if len(examples)<3:examples.append(value)
   if k=="trades":side[row.get("side","")]+=1
  if r["status"]=="ERROR":r["status"]="FULL_DAY_PARSED"
  r["first_timestamp"]=first or "";r["last_timestamp"]=last or ""
  r["side_buy"]=side.get("buy",0);r["side_sell"]=side.get("sell",0);r["other_side"]=sum(v for k,v in side.items() if k not in ("buy","sell"))
  r["note"]=f"invalid_timestamps={ts_invalid};out_of_day={out_of_day};reverse={reverse};oi_examples={oi_samples};funding_examples={fund_samples};trades_are_bounded_sample={k=='trades'}"
 except Exception as exc:r["status"]="REQUEST_OR_PARSE_ERROR";r["note"]=str(exc)[:240]
 return r
rows=[]
for e,s,d in CASES:
 for k in ("derivative_ticker","trades"):
  r=audit(e,s,d,k);rows.append(r);print(e,s,d,k,r["status"],r["rows"],r["nonempty_oi"],r["nonempty_funding"],flush=True)
with (OUT/"daily_value_audit.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(OUT/"manifest.json").write_text(json.dumps({"stage":"v2.6","counts":dict(collections.Counter(r["status"] for r in rows)),"no_historical_signal_replay":True,"no_live_changes":True,"caveats":["Derivative ticker capped at 250000 rows; only FULL_DAY_PARSED establishes full-day scan","Trade files capped at 12000 rows, never treated as complete daily taker volume","Values are source-native; do not assume original Detector's aggregated feature equivalence","One sample day does not establish multi-year continuous history"]},indent=2))
