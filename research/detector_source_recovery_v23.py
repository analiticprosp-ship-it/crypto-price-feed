#!/usr/bin/env python3
"""SHADOW v2.3: probe alternative historical derivatives sources. No trading signals."""
import csv,json,time,datetime as dt,urllib.request,urllib.parse,urllib.error,os
from pathlib import Path
from collections import Counter
OUT=Path("detector_source_recovery_v23_results");OUT.mkdir(exist_ok=True)
events=json.loads(Path("detector-signal-events.json").read_text()).get("events",[])
symbols=sorted({e["symbol"] for e in events if e.get("symbol")})
days=["2021-06-15","2024-06-15","2026-09-15"]
def ms(day):return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp()*1000)
def get(url,headers=None):
 for n in range(2):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"detector-shadow-source-recovery/2.3",**(headers or {})}),timeout=16) as r:
    return r.status,r.read(250000)
  except urllib.error.HTTPError as e:return e.code,e.read(2000)
  except Exception as e:
   if n:return "NETWORK_ERROR",str(e).encode()
   time.sleep(1)
def probe_bybit(sym,day):
 t=ms(day);params=urllib.parse.urlencode({"category":"linear","symbol":sym+"USDT","intervalTime":"5min","startTime":t,"endTime":t+86400000,"limit":200})
 u="https://api.bybit.com/v5/market/open-interest?"+params
 status,raw=get(u)
 r={"source":"BYBIT_OI","symbol":sym,"day":day,"http":status,"status":"ERROR","matching_records":0,"note":""}
 if status!=200:r["note"]=raw.decode(errors="replace")[:150];return r
 try:
  j=json.loads(raw);a=j.get("result",{}).get("list",[])
  valid=[x for x in a if t<=int(x["timestamp"])<t+86400000]
  r.update(status="WINDOW_VERIFIED" if valid else "EMPTY_OR_OUTSIDE_WINDOW",matching_records=len(valid),note="retCode="+str(j.get("retCode"))+"; returned="+str(len(a)))
  if j.get("retCode")!=0:r["status"]="PROVIDER_REJECTED";r["note"]+="; "+str(j.get("retMsg"))[:80]
 except Exception as e:r["note"]=str(e)[:150]
 return r
def probe_coinalyze(sym,day,key):
 r={"source":"COINALYZE_OI","symbol":sym,"day":day,"http":"NOT_RUN","status":"API_KEY_NOT_CONFIGURED","matching_records":0,"note":"Requires COINALYZE_API_KEY GitHub Actions secret; instrument symbols must be discovered before date probes"}
 # Do not guess exchange-specific instrument identifiers.
 return r
rows=[]
for sym in symbols:
 for day in days:
  r=probe_bybit(sym,day);rows.append(r);print(r,flush=True)
  rows.append(probe_coinalyze(sym,day,os.environ.get("COINALYZE_API_KEY","")))
with (OUT/"source_probes.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
# Public Binance spot 5m archive includes taker-buy base/quote volume in columns 9/10.
# This is a potential SINGLE-VENUE spot taker proxy, not the original aggregated multi-venue flow.
features=[
 {"feature":"Bybit historical OI","status":"PER_DATE_PROBE","note":"No inference of continuous historical coverage from three days"},
 {"feature":"Coinalyze historical OI","status":"KEY_AND_SYMBOL_DISCOVERY_REQUIRED","note":"No fabricated symbols or claims of coverage"},
 {"feature":"Tardis historical trades/OI/funding","status":"SAMPLE_OR_SUBSCRIPTION_REQUIRED","note":"Provider coverage/catalogue needs explicit validation; not probed in this run"},
 {"feature":"Binance spot taker buy volume","status":"AVAILABLE_IN_STANDARD_KLINE_SCHEMA","note":"Historical archive integrity sampled v2.1; taker buy is a one-venue proxy, not original aggregated flow"},
 {"feature":"Exact historical Detector replay","status":"BLOCKED","note":"Original producer rules and aligned point-in-time feature history not yet audited"}]
with (OUT/"recovery_options.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(features[0]));w.writeheader();w.writerows(features)
manifest={"stage":"v2.3","symbols":symbols,"days":days,"counts":dict(Counter(x["status"] for x in rows)),"shadow_only":True,"exact_detector_replay":False,"no_generated_signals":True,"no_live_changes":True}
(OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps(manifest,indent=2))
