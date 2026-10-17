#!/usr/bin/env python3
"""Detector v4.2 — complete monthly Binance USD-M futures 5m URL inventory.
HEAD availability only; no claim of ZIP integrity, original universe or source parity.
Use prior v4.0 checks as historical evidence but do not mark downloads reused without artifact provenance."""
import csv,json,urllib.request,urllib.error,concurrent.futures,collections,datetime as dt
from pathlib import Path
O=Path("detector_futures_monthly_v42_results");O.mkdir(exist_ok=True)
CONFIRMED="BTC ETH BNB LINK XRP SOL AVAX AAVE INJ NEAR LDO APT SUI ENA HYPE".split()
EXTRA="ADA DOGE DOT LTC BCH TRX ATOM UNI ETC FIL ICP OP ARB PEPE SHIB WIF FET RENDER RNDR SEI TIA JUP WLD STX GRT SAND MANA CRV DYDX".split()
SYMS=list(dict.fromkeys(CONFIRMED+EXTRA))
MONTHS=[f"{y}-{m:02d}" for y in range(2019,2027) for m in range(1,13) if (y,m)<=(2026,9)]
def check(symbol,month):
 pair=symbol+"USDT";url=f"https://data.binance.vision/data/futures/um/monthly/klines/{pair}/5m/{pair}-5m-{month}.zip"
 req=urllib.request.Request(url,method="HEAD",headers={"User-Agent":"detector-perpetual-monthly-v42"})
 try:
  with urllib.request.urlopen(req,timeout=18) as r:return {"asset":symbol,"pair":pair,"month":month,"status":"HTTP_"+str(r.status),"bytes":r.headers.get("Content-Length",""),"url":url}
 except urllib.error.HTTPError as e:return {"asset":symbol,"pair":pair,"month":month,"status":"HTTP_"+str(e.code),"bytes":"","url":url}
 except Exception as e:return {"asset":symbol,"pair":pair,"month":month,"status":"NETWORK_"+type(e).__name__,"bytes":"","url":url}
jobs=[(s,m) for s in SYMS for m in MONTHS];rows=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 for r in pool.map(lambda p:check(*p),jobs):rows.append(r)
with (O/"monthly_archive_inventory.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=["asset","pair","month","status","bytes","url"]);w.writeheader();w.writerows(rows)
summ=[];gaps=[]
for s in SYMS:
 rr=[r for r in rows if r["asset"]==s];ok=[r["month"] for r in rr if r["status"]=="HTTP_200"]
 between=[r for r in rr if ok and min(ok)<=r["month"]<=max(ok)]
 missing=[r for r in between if r["status"]!="HTTP_200"]
 for r in missing:gaps.append({"asset":s,"month":r["month"],"status":r["status"],"interpretation":"MISSING_OR_UNVERIFIED_ARCHIVE_NOT_PROVEN_EXCHANGE_GAP"})
 summ.append({"asset":s,"universe_status":"prior_confirmed_15" if s in CONFIRMED else "provisional_candidate","months_probed":len(rr),"http_200_months":len(ok),"first_http_200":min(ok) if ok else "","last_http_200":max(ok) if ok else "","missing_between_first_last":len(missing),"months_before_first_or_after_last":len(rr)-len(between),"data_integrity":"NOT_CHECKED_BY_V42","download_status":"URL_ONLY_NOT_DOWNLOADED"})
with (O/"monthly_asset_summary.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(summ[0]));w.writeheader();w.writerows(summ)
with (O/"unverified_internal_months.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=["asset","month","status","interpretation"]);w.writeheader();w.writerows(gaps)
(O/"manifest.json").write_text(json.dumps({"version":"4.2","candidate_assets":len(SYMS),"monthly_requests":len(rows),"statuses":dict(collections.Counter(r["status"] for r in rows)),"original_40_asset_universe":"NOT_RECOVERED; 44 are provisional candidates","scope":"Binance USD-M perpetual futures 5m monthly URL inventory; through September 2026, last complete month","known_validated_from_prior_v40":"18/19 sample archives passed ZIP+5m+taker volume checks, not re-downloaded here","cautions":["HTTP 200 HEAD does not validate ZIP bytes or 5m integrity","404 may be listing, rename, denomination (1000SHIBUSDT/1000PEPEUSDT), or absent archive; not proof of no trading","RNDR/RENDER must be audited as separate symbols and mapped with verified contract metadata","Existing spot archive evidence is not perpetual data","No OHLC/taker parity, OI/funding, signals, P&L, or live changes"],"next":"Verify historical listing symbols and dates from primary venue, resolve missing months with bounded GET, then staged monthly downloads with SHA256 and provenance"},indent=2))
print(json.dumps({"assets":len(SYMS),"months":len(MONTHS),"requests":len(rows),"statuses":dict(collections.Counter(r["status"] for r in rows))}),flush=True)
