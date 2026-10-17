#!/usr/bin/env python3
"""Detector v4.1: PROVISIONAL broad-universe USD-M futures archive availability.
HEAD inventory only, never claim files downloaded. User's ~40 historic symbols not recovered.
Do not substitute spot or alter trading systems."""
import csv,json,urllib.request,urllib.error,concurrent.futures,collections,datetime as dt
from pathlib import Path
O=Path("detector_futures_universe_v41_results");O.mkdir(exist_ok=True)
CONFIRMED="BTC ETH BNB LINK XRP SOL AVAX AAVE INJ NEAR LDO APT SUI ENA HYPE".split()
# Candidate universe for discovery ONLY, NOT a recovered original list.
EXTRA="ADA DOGE DOT LTC BCH TRX ATOM UNI ETC FIL ICP OP ARB PEPE SHIB WIF FET RENDER RNDR SEI TIA JUP WLD STX GRT SAND MANA CRV DYDX".split()
SYMS=list(dict.fromkeys(CONFIRMED+EXTRA))
MONTHS=[f"{y}-{m:02d}" for y in range(2019,2027) for m in (1,4,7,10) if (y,m)<=(2026,10)]
def probe(symbol,month):
 url=f"https://data.binance.vision/data/futures/um/monthly/klines/{symbol}USDT/5m/{symbol}USDT-5m-{month}.zip"
 req=urllib.request.Request(url,method="HEAD",headers={"User-Agent":"detector-research-v41"})
 try:
  with urllib.request.urlopen(req,timeout=16) as r:return {"asset":symbol,"month":month,"status":"HTTP_"+str(r.status),"size_bytes":r.headers.get("Content-Length",""),"url":url}
 except urllib.error.HTTPError as e:return {"asset":symbol,"month":month,"status":"HTTP_"+str(e.code),"size_bytes":"","url":url}
 except Exception as e:return {"asset":symbol,"month":month,"status":"NETWORK_"+type(e).__name__,"size_bytes":"","url":url}
jobs=[(s,m) for s in SYMS for m in MONTHS];rows=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 for r in pool.map(lambda p:probe(*p),jobs):rows.append(r)
with (O/"quarterly_archive_inventory.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=["asset","month","status","size_bytes","url"]);w.writeheader();w.writerows(rows)
summary=[]
for sym in SYMS:
 rs=[r for r in rows if r["asset"]==sym];ok=[r["month"] for r in rs if r["status"]=="HTTP_200"]
 summary.append({"asset":sym,"universe_source":"confirmed_v2_15" if sym in CONFIRMED else "provisional_candidate_not_recovered","quarters_probed":len(rs),"quarter_archives_http_200":len(ok),"earliest_quarter_200":min(ok) if ok else "","latest_quarter_200":max(ok) if ok else "","gaps_or_unknown":sum(r["status"]!="HTTP_200" for r in rs),"full_monthly_continuity":"NOT_CHECKED","zip_integrity":"NOT_CHECKED"})
with (O/"universe_summary.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
(O/"manifest.json").write_text(json.dumps({"version":"4.1","confirmed_15":CONFIRMED,"provisional_extra":EXTRA,"total_candidate_assets":len(SYMS),"quarters_per_asset":len(MONTHS),"probes":len(rows),"statuses":dict(collections.Counter(r["status"] for r in rows)),"important":"Original ~40-asset list not yet recovered; provisional extra assets are not asserted to be the user's original list","data_source":"Binance USD-M futures 5m monthly ZIP availability, HEAD only","limits":["200 proves URL reachable, not ZIP integrity or data quality","Quarterly checks do not prove monthly continuity","No spot substitution, no taker parity, no historical OI/funding, no backtest","Live Detector/Futures/P&L/limits untouched"],"next":"Recover original universe from project archive and repo artifacts; then scan EVERY month for actual recovered symbols, download only missing validated perpetual data"},indent=2))
print(json.dumps({"assets":len(SYMS),"probes":len(rows),"status_counts":dict(collections.Counter(r["status"] for r in rows))}))
