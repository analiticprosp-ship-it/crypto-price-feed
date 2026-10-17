#!/usr/bin/env python3
"""Detector v4.0: Binance public USD-M perpetual monthly archive audit.
Uses official data.binance.vision futures/um (NOT spot). Bounded real ZIP downloads,
integrity/continuity and taker volume parity; no live trading changes."""
import csv,json,urllib.request,urllib.error,zipfile,io,collections,datetime as dt,hashlib
from pathlib import Path
O=Path("detector_free_historical_v40_results");O.mkdir(exist_ok=True)
CASES=[("BTCUSDT","2020-01"),("BTCUSDT","2021-06"),("BTCUSDT","2024-01"),("BTCUSDT","2026-09"),("ETHUSDT","2020-01"),("SOLUSDT","2021-06"),("SOLUSDT","2024-06"),("BNBUSDT","2022-01"),("LINKUSDT","2022-01"),("XRPUSDT","2022-01"),("AVAXUSDT","2022-01"),("AAVEUSDT","2022-01"),("INJUSDT","2022-01"),("NEARUSDT","2022-01"),("LDOUSDT","2023-01"),("APTUSDT","2023-01"),("SUIUSDT","2024-01"),("ENAUSDT","2025-01"),("HYPEUSDT","2026-09")]
# All URLs are explicit futures/um monthly klines; avoid downloading hundreds of GB.
def audit(sym,month):
 url=f"https://data.binance.vision/data/futures/um/monthly/klines/{sym}/5m/{sym}-5m-{month}.zip"
 base={"symbol":sym,"month":month,"venue":"BINANCE_USDM_PERPETUAL","url":url}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"detector-research-v40"}),timeout=45) as r:
   payload=r.read(28_000_001)
   if len(payload)>28_000_000:return dict(base,status="TOO_LARGE",bytes=len(payload))
  with zipfile.ZipFile(io.BytesIO(payload)) as z:
   if z.testzip():return dict(base,status="ZIP_CRC_FAIL",bytes=len(payload))
   names=[n for n in z.namelist() if n.endswith(".csv")]
   if len(names)!=1:return dict(base,status="UNEXPECTED_ZIP",bytes=len(payload))
   rows=list(csv.reader(io.TextIOWrapper(z.open(names[0]),encoding="utf-8-sig")))
  # Public archives can include a header; validate column positions before using.
  if rows and rows[0] and not rows[0][0].isdigit():rows=rows[1:]
  if not rows:return dict(base,status="EMPTY",bytes=len(payload))
  stamps=[];bad=0;bad_volume=0;nonzero=0
  for x in rows:
   try:
    t=int(x[0]);volume=float(x[5]);buy=float(x[9]);sell=volume-buy
    if volume<0 or buy<0 or sell < -1e-7*max(1,volume):bad_volume+=1
    if volume>0:nonzero+=1
    stamps.append(t)
   except (ValueError,IndexError):bad+=1
  # 2025+ archives may use microsecond timestamps.
  if stamps and stamps[0]>10**14:stamps=[t//1000 for t in stamps]
  gaps=sum(b-a!=300000 for a,b in zip(stamps,stamps[1:]))
  return dict(base,status="VALIDATED" if not bad and not bad_volume and not gaps else "QUALITY_FLAG",bytes=len(payload),rows=len(rows),first_timestamp_ms=stamps[0] if stamps else "",last_timestamp_ms=stamps[-1] if stamps else "",nonzero_volume_bars=nonzero,malformed_rows=bad,invalid_taker_volume=bad_volume,non_5m_steps=gaps,sha256=hashlib.sha256(payload).hexdigest(),source_fields="open_time,open,high,low,close,volume,close_time,quote_volume,trades,taker_buy_base,taker_buy_quote,ignore")
 except urllib.error.HTTPError as e:return dict(base,status="HTTP_"+str(e.code))
 except Exception as e:return dict(base,status="ERROR_"+type(e).__name__,detail=str(e)[:160])
results=[]
for i,(sym,month) in enumerate(CASES):
 r=audit(sym,month);results.append(r);print(i+1,len(CASES),sym,month,r["status"],flush=True)
fields=list(dict.fromkeys(k for r in results for k in r))
with (O/"futures_archive_audit.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(results)
(O/"manifest.json").write_text(json.dumps({"version":"4.0","archive_type":"Binance USD-M perpetual futures 5m monthly klines","tested":len(results),"statuses":dict(collections.Counter(r["status"] for r in results)),"source_parity":"PARTIAL_ONLY","existing_spot_research":"Previous v2.0-v2.1 spot archive inventory is not a perpetual substitute; do not download it again","critical_limitations":["5m futures klines taker_buy_base supports reconstructing buy/sell base volume on same venue, but does not establish equivalence with original takerlongshortRatio source","Native 15m OHLC and 5m flow must be aligned on closed bars; no lookahead","OHLCV alone does not supply historical OI/funding","Archive accessibility at sampled months does not prove continuous 5-7 year coverage","No replay signals, win rate, P&L, or live trading changes"],"next":"Extend monthly manifest only for symbols/months that pass integrity, then independently validate historical native taker ratio parity and OKX source"},indent=2))
