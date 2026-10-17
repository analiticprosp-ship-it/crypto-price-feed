#!/usr/bin/env python3
"""Detector historical v2.2: point-in-time feature source audit, SHADOW only.
No synthetic signals and no assumption that modern API history spans 2019."""
import csv,json,urllib.request,urllib.parse,urllib.error,datetime as dt,time
from pathlib import Path
from collections import Counter
OUT=Path("detector_historical_features_v22_results");OUT.mkdir(exist_ok=True)
events=json.loads(Path("detector-signal-events.json").read_text()).get("events",[])
symbols=sorted({e.get("symbol") for e in events if e.get("symbol")})
# Representative three dates; every endpoint must return records timestamped in requested window.
dates=["2021-06-15","2024-06-15","2026-09-15"]
def milliseconds(day):return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp()*1000)
def fetch(url):
 for n in range(3):
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"detector-historical-source-audit/2.2"})
   with urllib.request.urlopen(req,timeout=18) as r:return json.loads(r.read(500000))
  except Exception as e:
   if n==2:return {"_error":type(e).__name__+":"+str(e)[:130]}
   time.sleep(n+1)
def audit(source,sym,day):
 t=milliseconds(day);end=t+86400000
 if source=="OKX_FUNDING":
  u="https://www.okx.com/api/v5/public/funding-rate-history?"+urllib.parse.urlencode({"instId":sym+"-USDT-SWAP","before":str(t),"after":str(end),"limit":"100"})
  field="fundingTime"
 elif source=="OKX_OI":
  # OKX public open-interest is current snapshot; no historical timestamp selector.
  return dict(source=source,symbol=sym,date=day,status="NO_HISTORICAL_ENDPOINT",records=0,earliest="",latest="",note="Current OI snapshot cannot be used as historical OI")
 elif source=="BINANCE_FUTURES_OI":
  u="https://fapi.binance.com/futures/data/openInterestHist?"+urllib.parse.urlencode({"symbol":sym+"USDT","period":"5m","startTime":t,"endTime":end,"limit":500})
  field="timestamp"
 elif source=="BINANCE_FUTURES_FUNDING":
  u="https://fapi.binance.com/fapi/v1/fundingRate?"+urllib.parse.urlencode({"symbol":sym+"USDT","startTime":t,"endTime":end,"limit":1000})
  field="fundingTime"
 else:raise ValueError(source)
 j=fetch(u)
 if isinstance(j,dict) and "_error" in j:return dict(source=source,symbol=sym,date=day,status="REQUEST_ERROR",records=0,earliest="",latest="",note=j["_error"])
 if isinstance(j,dict) and "data" in j:
  if j.get("code") not in (None,"0"):return dict(source=source,symbol=sym,date=day,status="PROVIDER_REJECTED",records=0,earliest="",latest="",note=str(j.get("msg",""))[:130])
  a=j.get("data") or []
 elif isinstance(j,list):a=j
 else:return dict(source=source,symbol=sym,date=day,status="PROVIDER_REJECTED",records=0,earliest="",latest="",note=str(j)[:130])
 timestamps=[]
 for x in a:
  try:timestamps.append(int(x[field]))
  except (ValueError,TypeError,KeyError):pass
 matching=[x for x in timestamps if t<=x<end]
 status="WINDOW_VERIFIED" if matching else "EMPTY_OR_OUTSIDE_WINDOW"
 return dict(source=source,symbol=sym,date=day,status=status,records=len(matching),
 earliest=dt.datetime.fromtimestamp(min(matching)/1000,dt.timezone.utc).isoformat() if matching else "",
 latest=dt.datetime.fromtimestamp(max(matching)/1000,dt.timezone.utc).isoformat() if matching else "",
 note=f"provider_records={len(a)}; timestamped_in_requested_day={len(matching)}")
rows=[]
for sym in symbols:
 for day in dates:
  for source in ("OKX_FUNDING","OKX_OI","BINANCE_FUTURES_OI","BINANCE_FUTURES_FUNDING"):
   r=audit(source,sym,day);rows.append(r);print(sym,day,source,r["status"],flush=True)
with (OUT/"historical_feature_probes.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ["source"]);w.writeheader();w.writerows(rows)
gates=[
 dict(feature="5m spot OHLCV",status="SAMPLED_VERIFIED_V21",reason="Source and integrity are separate from exact Detector venue"),
 dict(feature="BTC relative strength",status="CONDITIONAL",reason="Requires point-in-time aligned BTC candles and exact original formula"),
 dict(feature="aggregated taker buy/sell flow",status="NOT_RECONSTRUCTED",reason="Historical spot klines may expose taker-buy volume but are not necessarily original multi-venue flow"),
 dict(feature="OKX historical OI",status="UNVERIFIED",reason="Current OI endpoint cannot be backdated; no equivalent archived source verified"),
 dict(feature="historical funding",status="PER_DATE_PROBE_ONLY",reason="A verified day is not proof of complete multi-year coverage"),
 dict(feature="Binance historical futures OI",status="PER_DATE_PROBE_ONLY",reason="API retention and venue coverage must be measured"),
 dict(feature="exact Detector replay",status="BLOCKED_PENDING_SOURCE_AND_RULE_AUDIT",reason="All required point-in-time features and producer implementation not yet proven reproducible")]
with (OUT/"feature_replay_gates.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(gates[0]));w.writeheader();w.writerows(gates)
manifest={"stage":"V2.2_POINT_IN_TIME_FEATURE_PROBES","symbols":symbols,"dates":dates,
 "probe_status_counts":dict(Counter(r["status"] for r in rows)),
 "no_exact_replay":True,"no_generated_signals":True,
 "caveats":["Probe results do not establish continuous multi-year history",
 "Binance futures data cannot silently replace OKX original data",
 "Historical source must cover actual symbol listing and feature calculation window",
 "HTTP failure or geo restriction is not evidence that historical data never existed",
 "Current OI snapshots must never be assigned to historical timestamps",
 "No changes to live Detector, Futures, P&L, limits"]}
(OUT/"manifest.json").write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
