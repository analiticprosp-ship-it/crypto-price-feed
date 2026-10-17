#!/usr/bin/env python3
"""v3.6 research-only limited 15m reconstructed candidate probe.
Historical Tardis tape is NOT yet certified equivalent to native REST taker bars.
Uses native historical perpetual 15m OHLC from Tardis trades (not spot), with
strict completeness gates. No forward looking, no trading advice."""
import csv,gzip,io,json,urllib.request,datetime as dt,collections,math
from pathlib import Path
O=Path("detector_reconstruction_v36_results");O.mkdir(exist_ok=True)
CASES=[("binance-futures","BTCUSDT","2021-06-01"),("bybit","BTCUSDT","2021-06-01"),("okex-swap","BTC-USDT-SWAP","2021-06-01"),("bybit","SOLUSDT","2024-06-01"),("okex-swap","SOL-USDT-SWAP","2024-06-01"),("okex-swap","HYPE-USDT-SWAP","2026-09-01")]
UTC=dt.timezone.utc
def stamp(v):
 n=float(v);return dt.datetime.fromtimestamp(n/(1e9 if n>=1e17 else 1e6 if n>=1e14 else 1e3 if n>=1e11 else 1),UTC)
def run(ex,sym,day):
 y,m,d=day.split("-");url=f"https://datasets.tardis.dev/v1/{ex}/trades/{y}/{m}/{d}/{sym}.csv.gz"
 start=dt.datetime.fromisoformat(day).replace(tzinfo=UTC);end=start+dt.timedelta(days=1)
 bars=collections.defaultdict(lambda:{"prices":[],"buy":0.,"sell":0.,"n":0,"last_received":None})
 with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"detector-shadow-v36"}),timeout=120) as r:
  with gzip.GzipFile(fileobj=r) as gz:
   for row in csv.DictReader(io.TextIOWrapper(gz,encoding="utf-8-sig",errors="replace",newline="")):
    try:
     t=stamp(row["timestamp"]);receipt=stamp(row["local_timestamp"]);p=float(row["price"]);a=float(row["amount"]);side=row["side"].lower()
     if not(start<=t<end and p>0 and a>0 and math.isfinite(p) and math.isfinite(a) and receipt>=t and side in ("buy","sell")):continue
     b=int(t.timestamp())//300*300;v=bars[b];v["prices"].append((t,p));v[side]+=a;v["n"]+=1
     if v["last_received"] is None or receipt>v["last_received"]:v["last_received"]=receipt
    except Exception:continue
 results=[];five={}
 for b,v in bars.items():
  five[b]={"buy":v["buy"],"sell":v["sell"],"last_received":v["last_received"]}
 # 15m price OHLC: ordered event times; prior 12 complete closed 15m bars required.
 fifteen={}
 for b,v in bars.items():
  q=b//900*900;f=fifteen.setdefault(q,[]);f.extend(v["prices"])
 for q in fifteen:
  prices=[p for _,p in sorted(fifteen[q])]
  fifteen[q]={"o":prices[0],"h":max(prices),"l":min(prices),"c":prices[-1]}
 for q in sorted(fifteen):
  if q< int(start.timestamp())+13*900:continue
  prior=[fifteen.get(q-900*i) for i in range(12,0,-1)]
  five_now=[five.get(q+300*i) for i in range(3)]
  five_prev=[five.get(q-900+300*i) for i in range(3)]
  row={"exchange":ex,"symbol":sym,"day":day,"bar_end_utc":dt.datetime.fromtimestamp(q+900,UTC).isoformat(),"research_only":True,"historical_equivalence":"NOT_PROVEN","signal_status":"NOT_RECONSTRUCTABLE","reason":""}
  if any(x is None for x in prior) or any(x is None for x in five_now+five_prev):
   row["reason"]="MISSING_12_PRIOR_PRICE_BARS_OR_5M_FLOW";results.append(row);continue
  # Original signal engine gates on both 5m flow and price-source bar status.
  # Here the 15m price is reconstructed from trades and not native 15m OHLCV.
  last=fifteen[q];lo=min(x["l"] for x in prior);hi=max(x["h"] for x in prior)
  location=(last["c"]-last["l"])/(last["h"]-last["l"]) if last["h"]>last["l"] else None
  sweep_low=last["l"]<lo and last["c"]>lo
  sweep_high=last["h"]>hi and last["c"]<hi
  price_long=sweep_low or (last["c"]>last["o"] and location is not None and location>=.6)
  price_short=sweep_high or (last["c"]<last["o"] and location is not None and location<=.4)
  def imb(x):
   buy=sum(z["buy"] for z in x);sell=sum(z["sell"] for z in x)
   return round((buy-sell)/(buy+sell),6) if buy+sell else None
  now=imb(five_now);prev=imb(five_prev)
  flow_long=now is not None and ((prev is not None and now-prev>=.15 and now>=.10) or (now<=-.10 and price_long))
  flow_short=now is not None and ((prev is not None and now-prev<=-.15 and now<=-.10) or (now>=.10 and price_short))
  # Historical publication gate: all 5m trades must have arrived before end of 15m candle.
  asof_ok=all(z["last_received"]<=dt.datetime.fromtimestamp(q+900,UTC) for z in five_now)
  row.update({"price_long":price_long,"price_short":price_short,"flow_long_raw":flow_long,"flow_short_raw":flow_short,"imbalance_raw":now,"previous_imbalance_raw":prev,"last_close":last["c"],"candidate_long_raw":price_long and flow_long,"candidate_short_raw":price_short and flow_short,"asof_receipt_gate":asof_ok,"reason":"TRADE_RECONSTRUCTED_OHLC_NOT_NATIVE;FLOW_UNITS_SIDE_UNVERIFIED;NO_REPLAY_APPROVAL"})
  results.append(row)
 return results,{"exchange":ex,"symbol":sym,"date":day,"five_minute_bars":len(five),"fifteen_minute_bars":len(fifteen),"candidate_probe_rows":len(results),"gate":"NOT_EQUIVALENT"}
rows=[];summary=[]
for case in CASES:
 try:
  a,b=run(*case);rows+=a;summary.append(b);print("PROBED",*case,len(a),flush=True)
 except Exception as e:
  summary.append({"exchange":case[0],"symbol":case[1],"date":case[2],"gate":"ERROR","error":str(e)[:200]});print("ERROR",case,e,flush=True)
def write(name,items):
 keys=list(dict.fromkeys(k for x in items for k in x))
 with (O/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(items)
write("reconstructed_candidate_probe.csv",rows);write("case_summary.csv",summary)
(O/"manifest.json").write_text(json.dumps({"version":"v3.6","scope":"6 historical sample days, research-only reconstructed candidate probe","gate":"NOT_EQUIVALENT","signal_status":"NOT_RECONSTRUCTABLE","not_original_signals":True,"limitations":["Price OHLC from trades, not original venue 15m OHLCV feed","Tardis trade side and amount unit not proven identical to original REST aggregates","No full-history data, no calibrated predictive outcome","No historical publication parity for source market summary"],"no_live_changes":True},indent=2))
