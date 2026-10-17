#!/usr/bin/env python3
"""Detector SHADOW v3.3: trade-side semantics and historical 5m taker tape audit.
Sample-only, NO equivalence assertion to original REST aggregate without paired observations.
No trade signals, no trading authority."""
import csv,gzip,io,json,urllib.request,datetime as dt,collections,math
from pathlib import Path
OUT=Path("detector_tardis_taker_v33_results");OUT.mkdir(exist_ok=True)
CASES=[("binance-futures","BTCUSDT","2021-06-01"),("bybit","BTCUSDT","2021-06-01"),("okex-swap","BTC-USDT-SWAP","2021-06-01"),("bybit","SOLUSDT","2024-06-01"),("okex-swap","SOL-USDT-SWAP","2024-06-01"),("okex-swap","HYPE-USDT-SWAP","2026-09-01")]
UTC=dt.timezone.utc
def ts(v):
 s=str(v or "").strip()
 try:
  n=float(s)
  if not math.isfinite(n):raise ValueError("nonfinite")
  return dt.datetime.fromtimestamp(n/(1e9 if abs(n)>=1e17 else 1e6 if abs(n)>=1e14 else 1e3 if abs(n)>=1e11 else 1),UTC)
 except ValueError:
  d=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
  if d.tzinfo is None:raise ValueError("naive")
  return d.astimezone(UTC)
def run(ex,sym,day):
 y,m,d=day.split("-");url=f"https://datasets.tardis.dev/v1/{ex}/trades/{y}/{m}/{d}/{sym}.csv.gz"
 begin=dt.datetime.fromisoformat(day).replace(tzinfo=UTC);end=begin+dt.timedelta(days=1)
 cnt=collections.Counter();sides=collections.Counter();bars=collections.defaultdict(lambda:[0.0,0.0,0,0]);first=[];last=[];headers=[]
 with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"detector-taker-audit-v33"}),timeout=120) as r:
  with gzip.GzipFile(fileobj=r) as gz:
   reader=csv.DictReader(io.TextIOWrapper(gz,encoding="utf-8-sig",errors="replace",newline=""))
   headers=reader.fieldnames or []
   for row in reader:
    cnt["total_rows"]+=1
    if len(first)<3:first.append({k:row.get(k) for k in ("timestamp","local_timestamp","side","price","amount")})
    try:
     event=ts(row.get("timestamp"));local=ts(row.get("local_timestamp"))
     qty=float(row.get("amount"))
     if not math.isfinite(qty) or qty<=0:raise ValueError("qty")
    except Exception:cnt["invalid"]+=1;continue
    if not begin<=event<end:cnt["event_outside"]+=1;continue
    if local<event:cnt["negative_latency"]+=1;continue
    if local>=end:cnt["late_received"]+=1;continue
    side=str(row.get("side") or "").lower().strip();sides[side]+=1
    if side not in ("buy","sell"):cnt["unknown_side"]+=1;continue
    b=int(event.timestamp())//300*300
    idx=0 if side=="buy" else 1
    bars[b][idx]+=qty;bars[b][2+idx]+=1
    cnt["valid_trades"]+=1
    if len(last)>=3:last.pop(0)
    last.append({k:row.get(k) for k in ("timestamp","local_timestamp","side","price","amount")})
 out=[]
 for b,(buy,sell,n_buy,n_sell) in sorted(bars.items()):
  out.append({"exchange":ex,"symbol":sym,"date":day,"bar_start_utc":dt.datetime.fromtimestamp(b,UTC).isoformat(),"buy_base":round(buy,8),"sell_base":round(sell,8),"buy_trades":n_buy,"sell_trades":n_sell,"imbalance":round((buy-sell)/(buy+sell),6) if buy+sell else "","full_day_sample":True})
 # Any Tardis trade-side interpretation is a hypothesis until matched against native REST buy/sell.
 return {"exchange":ex,"symbol":sym,"date":day,"status":"AUDITED","header":json.dumps(headers),"sides":json.dumps(sides),"first_rows":json.dumps(first),"last_rows":json.dumps(last),"bars":len(out),**cnt},out
summary=[];rows=[]
for ex,sym,day in CASES:
 try:
  s,b=run(ex,sym,day);summary.append(s);rows+=b;print(ex,sym,s["valid_trades"],s["bars"],flush=True)
 except Exception as err:
  summary.append({"exchange":ex,"symbol":sym,"date":day,"status":"ERROR","error":str(err)[:400]});print("ERROR",ex,sym,err,flush=True)
def save(name,items):
 keys=list(dict.fromkeys(k for x in items for k in x))
 with (OUT/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(items)
save("taker_sample_summary.csv",summary);save("taker_5m_bars.csv",rows)
(OUT/"manifest.json").write_text(json.dumps({"version":"v3.3","statuses":dict(collections.Counter(x["status"] for x in summary)),"scope":"Full-day free Tardis trades samples for six historical cases","semantic_warning":"Tardis side field meaning not independently cross-validated with same-venue REST aggregate; do not assert parity","size_warning":"Trade amount may represent contracts rather than base coin; venue contract multiplier must be verified before equivalence claim","time_warning":"Trade bars by event timestamp; availability must be gated by local_timestamp for historical replay","coverage_warning":"Missing 5m bars and incomplete trade tape require separate checks; zero trades not imputed","guard":"SHADOW research only; no signals, trades, P&L, Futures or live modifications"},indent=2))
