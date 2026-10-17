#!/usr/bin/env python3
"""v3.4 Tardis contract unit and trade-side audit; SHADOW-only, no signals."""
import csv,gzip,io,json,urllib.request,urllib.parse,datetime as dt,collections,math
from pathlib import Path
O=Path("detector_taker_units_v34_results");O.mkdir(exist_ok=True)
CASES=[("binance-futures","BTCUSDT","2021-06-01"),("bybit","BTCUSDT","2021-06-01"),("okex-swap","BTC-USDT-SWAP","2021-06-01"),("bybit","SOLUSDT","2024-06-01"),("okex-swap","SOL-USDT-SWAP","2024-06-01"),("okex-swap","HYPE-USDT-SWAP","2026-09-01")]
UTC=dt.timezone.utc
def stamp(v):
 s=str(v).strip()
 try:
  n=float(s);scale=1e9 if abs(n)>=1e17 else 1e6 if abs(n)>=1e14 else 1e3 if abs(n)>=1e11 else 1
  return dt.datetime.fromtimestamp(n/scale,UTC)
 except ValueError:return dt.datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(UTC)
def get(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"detector-research-v34","Accept":"application/json"}),timeout=30) as r:return json.load(r)
def instrument(ex,sym):
 if ex!="okex-swap":return {"status":"NOT_REQUESTED","reason":"Non-OKX contract size requires separate historical spec"}
 try:
  j=get("https://www.okx.com/api/v5/public/instruments?"+urllib.parse.urlencode({"instType":"SWAP","instId":sym}))
  a=j.get("data") or []
  if str(j.get("code"))!="0" or not a:return {"status":"UNAVAILABLE"}
  x=a[0]
  return {"status":"CURRENT_SPEC_ONLY","ctVal":x.get("ctVal"),"ctValCcy":x.get("ctValCcy"),"ctType":x.get("ctType"),"lotSz":x.get("lotSz"),"instId":x.get("instId"),"warning":"Current contract specification NOT verified for historical date"}
 except Exception as e:return {"status":"ERROR","reason":str(e)[:180]}
def run(ex,sym,day):
 yy,mm,dd=day.split("-");url=f"https://datasets.tardis.dev/v1/{ex}/trades/{yy}/{mm}/{dd}/{sym}.csv.gz"
 start=dt.datetime.fromisoformat(day).replace(tzinfo=UTC);end=start+dt.timedelta(days=1)
 bars=collections.defaultdict(lambda:[0.,0.,0,0]);c=collections.Counter();samples={}
 with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"detector-research-v34"}),timeout=120) as response:
  with gzip.GzipFile(fileobj=response) as gz:
   rd=csv.DictReader(io.TextIOWrapper(gz,encoding="utf-8-sig",errors="replace",newline=""))
   fields=rd.fieldnames
   for row in rd:
    c["rows"]+=1
    try:
     t=stamp(row["timestamp"]);received=stamp(row["local_timestamp"]);amount=float(row["amount"]);price=float(row["price"])
     if not(math.isfinite(amount) and amount>0 and math.isfinite(price) and price>0):raise ValueError("amount/price")
    except Exception:c["invalid"]+=1;continue
    if not start<=t<end:c["outside_day"]+=1;continue
    if received<t:c["negative_latency"]+=1;continue
    if received>=end:c["received_next_day"]+=1;continue
    side=str(row.get("side","")).lower()
    if side not in ("buy","sell"):c["unknown_side"]+=1;continue
    if side not in samples:samples[side]={"side":side,"amount":amount,"price":price,"raw_row":{k:row.get(k) for k in ("timestamp","side","amount","price","id")}}
    b=int(t.timestamp())//300*300;x=bars[b];idx=0 if side=="buy" else 1
    x[idx]+=amount;x[2+idx]+=1;c["valid"]+=1
 data=[]
 for b,x in sorted(bars.items()):
  buy,sell,nb,ns=x
  data.append({"exchange":ex,"symbol":sym,"date":day,"bar_start_utc":dt.datetime.fromtimestamp(b,UTC).isoformat(),"raw_buy_amount":round(buy,8),"raw_sell_amount":round(sell,8),"raw_imbalance":round((buy-sell)/(buy+sell),6) if buy+sell else "","buy_trades":nb,"sell_trades":ns,"unit":"RAW_TARDIS_AMOUNT_NOT_CONFIRMED_BASE"})
 return {"exchange":ex,"symbol":sym,"date":day,"status":"AUDITED","rows":c["rows"],"valid":c["valid"],"invalid":c["invalid"],"outside_day":c["outside_day"],"negative_latency":c["negative_latency"],"received_next_day":c["received_next_day"],"unknown_side":c["unknown_side"],"bars":len(data),"fieldnames":json.dumps(fields),"examples":json.dumps(samples),"instrument_spec":json.dumps(instrument(ex,sym))},data
summ=[];bars=[]
for case in CASES:
 try:
  x,y=run(*case);summ.append(x);bars+=y;print("AUDITED",*case,x["valid"],x["bars"],flush=True)
 except Exception as e:
  summ.append({"exchange":case[0],"symbol":case[1],"date":case[2],"status":"ERROR","error":str(e)[:300]});print("ERROR",case,e,flush=True)
def write(name,items):
 keys=list(dict.fromkeys(k for r in items for k in r))
 with (O/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(items)
write("unit_side_summary.csv",summ);write("raw_5m_taker_bars.csv",bars)
(O/"manifest.json").write_text(json.dumps({"version":"3.4","scope":"Six free Tardis historical day samples","pass_criteria":{"tape_parsed":"valid trades and 288 five-minute bars per sample","historical_contract_unit":"Requires dated historical instrument specification and matching Tardis amount definition","side_semantics":"Requires venue documentation and independent paired same-day native taker REST or trusted venue aggregate","original_detector_equivalence":"NOT_TESTED unless native 5m REST aggregate available for same historical date"},"warnings":["Current OKX ctVal is NOT proof of 2021/2024/2026 ctVal","Trade-side buy/sell labels not independently verified as taker aggressor","Raw amount not automatically base coin or comparable across venues","Do not mix perpetual and spot trades","No signal backtest or live system modification"],"status":"PRELIMINARY_UNIT_SIDE_AUDIT_ONLY"},ensure_ascii=False,indent=2))
