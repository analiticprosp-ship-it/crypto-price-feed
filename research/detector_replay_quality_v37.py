#!/usr/bin/env python3
"""Detector v3.7: historical replay quality gate on six Tardis sample days.
No signal approval, no P&L, no synthetic missing periods."""
import csv,gzip,io,json,urllib.request,datetime as dt,collections,math
from pathlib import Path
OUT=Path("detector_replay_quality_v37_results");OUT.mkdir(exist_ok=True)
CASES=[("binance-futures","BTCUSDT","2021-06-01"),("bybit","BTCUSDT","2021-06-01"),("okex-swap","BTC-USDT-SWAP","2021-06-01"),("bybit","SOLUSDT","2024-06-01"),("okex-swap","SOL-USDT-SWAP","2024-06-01"),("okex-swap","HYPE-USDT-SWAP","2026-09-01")]
UTC=dt.timezone.utc
def timestamp(s):
 n=float(s);return dt.datetime.fromtimestamp(n/(1e9 if n>=1e17 else 1e6 if n>=1e14 else 1e3 if n>=1e11 else 1),UTC)
def calc(ex,sym,day):
 y,m,d=day.split("-");url=f"https://datasets.tardis.dev/v1/{ex}/trades/{y}/{m}/{d}/{sym}.csv.gz"
 start=dt.datetime.fromisoformat(day).replace(tzinfo=UTC);end=start+dt.timedelta(days=1)
 five=collections.defaultdict(lambda:{"trades":[],"buy":0.,"sell":0.,"received_max":None})
 errors=collections.Counter()
 with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"detector-replay-quality-v37"}),timeout=120) as response:
  with gzip.GzipFile(fileobj=response) as gz:
   for rec in csv.DictReader(io.TextIOWrapper(gz,encoding="utf-8-sig",errors="replace",newline="")):
    try:
     event=timestamp(rec["timestamp"]);receipt=timestamp(rec["local_timestamp"]);price=float(rec["price"]);qty=float(rec["amount"]);side=str(rec["side"]).lower()
     if not (start<=event<end):errors["outside_day"]+=1;continue
     if not (math.isfinite(price) and price>0 and math.isfinite(qty) and qty>0 and receipt>=event and side in ("buy","sell")):errors["invalid"]+=1;continue
     b=int(event.timestamp())//300*300;x=five[b];x["trades"].append((event,price));x[side]+=qty
     if x["received_max"] is None or receipt>x["received_max"]:x["received_max"]=receipt
    except Exception:errors["invalid"]+=1
 fifteen={}
 for q in range(int(start.timestamp()),int(end.timestamp()),900):
  f=[five.get(q+i*300) for i in range(3)]
  if any(x is None or not x["trades"] for x in f):continue
  tape=sorted(t for x in f for t in x["trades"]);p=[v for _,v in tape]
  fifteen[q]={"o":p[0],"h":max(p),"l":min(p),"c":p[-1]}
 rows=[]
 for q in range(int(start.timestamp()),int(end.timestamp()),900):
  end15=dt.datetime.fromtimestamp(q+900,UTC)
  r={"exchange":ex,"symbol":sym,"date":day,"bar_end_utc":end15.isoformat(),"classification":"UNAVAILABLE","reason":"","candidate_long_raw":False,"candidate_short_raw":False,"price_long":False,"price_short":False,"flow_long":False,"flow_short":False,"asof_ok":False,"source_equivalent":False,"future_15m_return_pct":"","future_60m_return_pct":""}
  prior=[fifteen.get(q-900*i) for i in range(12,0,-1)]
  current=fifteen.get(q);now=[five.get(q+i*300) for i in range(3)];prev=[five.get(q-900+i*300) for i in range(3)]
  if current is None or any(x is None for x in prior) or any(x is None for x in now+prev):
   r["reason"]="MISSING_WARMUP_OR_5M_BARS";rows.append(r);continue
  if any(x["received_max"]>end15 for x in now):
   r["reason"]="AFTER_BAR_RECEIPT";rows.append(r);continue
  low=min(x["l"] for x in prior);high=max(x["h"] for x in prior)
  loc=(current["c"]-current["l"])/(current["h"]-current["l"]) if current["h"]>current["l"] else None
  pl=(current["l"]<low and current["c"]>low) or (current["c"]>current["o"] and loc is not None and loc>=.6)
  ps=(current["h"]>high and current["c"]<high) or (current["c"]<current["o"] and loc is not None and loc<=.4)
  def imb(z):
   buy=sum(x["buy"] for x in z);sell=sum(x["sell"] for x in z)
   return round((buy-sell)/(buy+sell),6) if buy+sell else None
  a=imb(now);b=imb(prev)
  fl=a is not None and ((b is not None and a-b>=.15 and a>=.10) or (a<=-.10 and pl))
  fs=a is not None and ((b is not None and a-b<=-.15 and a<=-.10) or (a>=.10 and ps))
  long=pl and fl;short=ps and fs
  classification="CONFLICT" if long and short else "LONG_RAW" if long else "SHORT_RAW" if short else "WATCH" if pl or ps or fl or fs else "NO_EDGE"
  r.update({"classification":classification,"reason":"INPUT_EQUIVALENCE_NOT_PROVEN","candidate_long_raw":long,"candidate_short_raw":short,"price_long":pl,"price_short":ps,"flow_long":fl,"flow_short":fs,"asof_ok":True,"imbalance_raw":a,"prev_imbalance_raw":b})
  for mins,key in [(15,"future_15m_return_pct"),(60,"future_60m_return_pct")]:
   future=fifteen.get(q+mins*60)
   if future is not None:r[key]=round((future["c"]/current["c"]-1)*100,6)
  rows.append(r)
 return rows,{"exchange":ex,"symbol":sym,"day":day,"five_bars":len(five),"fifteen_bars":len(fifteen),"classes":dict(collections.Counter(r["classification"] for r in rows)),"errors":dict(errors)}
rows=[];summ=[]
for case in CASES:
 try:
  r,s=calc(*case);rows+=r;summ.append(s);print("AUDITED",*case,s["classes"],flush=True)
 except Exception as e:
  summ.append({"exchange":case[0],"symbol":case[1],"day":case[2],"status":"ERROR","error":str(e)[:200]});print("ERROR",case,e,flush=True)
def write(name,items):
 keys=list(dict.fromkeys(k for x in items for k in x))
 with (OUT/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
  for x in items:w.writerow({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in x.items()})
write("interval_classifications.csv",rows);write("case_summary.csv",summ)
(OUT/"manifest.json").write_text(json.dumps({"version":"3.7","scope":"6 one-day samples, including unavailable/no-edge intervals","classification_counts":dict(collections.Counter(r["classification"] for r in rows)),"historical_replay_approved":False,"no_strategy_performance_claim":True,"critical_limits":["No source parity: raw trade amounts and aggressor semantics unverified","Price bars reconstructed from trade tape, not original 15m source","No 5-7 year coverage","Future returns are descriptive research outcomes only; no fees/slippage/strategy win rates","Warmup from same day only; unavailable intervals are not NO_EDGE","Event timestamp vs collector receipt gate approximates historical availability only"],"no_live_changes":True},indent=2))
