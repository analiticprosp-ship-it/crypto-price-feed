#!/usr/bin/env python3
"""Detector v3.5: independent taker semantics/spec evidence audit.
No historical equivalence asserted without same-date native aggregate."""
import json,csv,urllib.request,urllib.parse,datetime as dt
from pathlib import Path
O=Path("detector_taker_parity_v35_results");O.mkdir(exist_ok=True)
CASES=[("binance-futures","BTCUSDT","2021-06-01"),("bybit","BTCUSDT","2021-06-01"),("okex-swap","BTC-USDT-SWAP","2021-06-01"),("bybit","SOLUSDT","2024-06-01"),("okex-swap","SOL-USDT-SWAP","2024-06-01"),("okex-swap","HYPE-USDT-SWAP","2026-09-01")]
def fetch(url):
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"detector-parity-audit-v35","Accept":"application/json"}),timeout=20) as r:
   body=r.read(400000)
   return {"status":"HTTP_200","json":json.loads(body)}
 except Exception as e:return {"status":("HTTP_"+str(e.code)) if hasattr(e,"code") else type(e).__name__,"error":str(e)[:120]}
def evidence(ex,sym,day):
 result={"exchange":ex,"symbol":sym,"historical_day":day,"historical_native_aggregate":"UNAVAILABLE","historical_unit":"UNVERIFIED","taker_side":"UNVERIFIED","equivalence":"NOT_PROVEN"}
 if ex=="okex-swap":
  p=urllib.parse.urlencode({"instType":"SWAP","instId":sym})
  x=fetch("https://www.okx.com/api/v5/public/instruments?"+p)
  result["current_instrument_http"]=x["status"]
  data=x.get("json",{}).get("data",[]) if isinstance(x.get("json"),dict) else []
  if data:
   z=data[0];result.update({"current_ctVal":z.get("ctVal"),"current_ctValCcy":z.get("ctValCcy"),"current_ctType":z.get("ctType"),"current_spec_status":"CURRENT_ONLY_NOT_HISTORICAL"})
  p=urllib.parse.urlencode({"instId":sym,"period":"5m","unit":"1","limit":"2"})
  q=fetch("https://www.okx.com/api/v5/rubik/stat/taker-volume-contract?"+p)
  result["current_native_taker_http"]=q["status"]
  data=q.get("json",{}).get("data",[]) if isinstance(q.get("json"),dict) else []
  result["current_native_taker_shape"]=[len(a) if isinstance(a,list) else None for a in data[:2]]
  result["current_native_taker_note"]="OKX endpoint order [ts, SELL, BUY], unit=1 BASE; current data cannot validate historical Tardis tape"
 elif ex=="binance-futures":
  p=urllib.parse.urlencode({"symbol":sym,"period":"5m","limit":"2"})
  q=fetch("https://fapi.binance.com/futures/data/takerlongshortRatio?"+p)
  result["current_native_taker_http"]=q["status"]
  result["current_native_taker_fields"]=list(q.get("json",[])[0].keys()) if isinstance(q.get("json"),list) and q["json"] else []
  result["current_native_taker_note"]="Live REST is not a historical paired comparison"
 else:
  result["native_taker_note"]="Bybit trade side must be independently documented; no historical aggregate assumed"
 return result
rows=[evidence(*case) for case in CASES]
with (O/"independent_source_evidence.csv").open("w",newline="") as f:
 keys=list(dict.fromkeys(k for row in rows for k in row));w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
 for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
(O/"manifest.json").write_text(json.dumps({"version":"v3.5","cases":len(rows),"gate":"NOT_PROVEN","purpose":"Independent public REST availability and current contract metadata; never confuse live with historical","necessary_for_pass":["Historical venue-specific contract size and historical amount unit provenance","Venue-native aggressor-side semantics documented","Same venue, same historical 5m period paired native aggregate or independently archived trusted aggregate","Correct closed bar timestamp and as-of availability"],"no_signals":True,"no_live_changes":True},indent=2))
print(json.dumps({"cases":len(rows),"gate":"NOT_PROVEN","sources":[[r["exchange"],r["symbol"],r.get("current_native_taker_http"),r.get("current_instrument_http")] for r in rows]}))
