#!/usr/bin/env python3
"""Research-only official public historical L2 URL and catalog diagnostic.
HEAD or bounded GET only; status is not proof of historical L2 coverage.
"""
import datetime as dt,json,pathlib,urllib.error,urllib.request
targets=[
 ("coinbase","Coinbase Exchange historical candles API (negative L2 control)","https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=3600&start=2026-10-29T12%3A00%3A00Z&end=2026-10-29T13%3A00%3A00Z"),
 ("coinbase","Coinbase Exchange current L2 API (negative historical control)","https://api.exchange.coinbase.com/products/BTC-USD/book?level=2"),
 ("gate","Gate official spot currency pair metadata","https://api.gateio.ws/api/v4/spot/currency_pairs/BTC_USDT"),
 ("mexc","MEXC official exchangeInfo","https://api.mexc.com/api/v3/exchangeInfo?symbol=BTCUSDT"),
 ("crypto_com","Crypto.com official instrument metadata","https://api.crypto.com/exchange/v1/public/get-instruments"),
 ("binance","Binance public data archive directory","https://data.binance.vision/?prefix=data/spot/daily/"),
 ("kraken","Kraken official downloadable historical OHLCVT (negative L2 control)","https://support.kraken.com/articles/360047124832-downloadable-historical-market-data-time-and-sales-"),
]
rows=[]
for venue,description,url in targets:
 row={"venue":venue,"description":description,"url":url,"status":"NOT_CHECKED","is_historical_l2":False}
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 P3-public-source-audit","Accept":"application/json,text/html,*/*"})
  with urllib.request.urlopen(req,timeout=20) as resp:
   sample=resp.read(4096)
   row.update(status="REACHABLE_NOT_HISTORICAL_L2",http_status=resp.status,content_type=resp.headers.get("Content-Type",""),sample_bytes=len(sample))
 except urllib.error.HTTPError as e:row.update(status="HTTP_ERROR",http_status=e.code)
 except Exception as e:row.update(status="NETWORK_ERROR",error_type=type(e).__name__)
 rows.append(row);print(venue,description,row["status"],row.get("http_status"),flush=True)
out=pathlib.Path("/tmp/p3-official-free-source");out.mkdir(parents=True,exist_ok=True)
(out/"manifest.json").write_text(json.dumps({"schema":"P3_OFFICIAL_FREE_SOURCE_DIAGNOSTIC_V1","generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"target_day":"2026-10-29","historical_l2_confirmed":False,"caveat":"This is a connectivity and official endpoint classification check, NOT proof of a historical L2 archive. Candles, trades, current books and metadata are explicitly excluded.","rows":rows},indent=2)+"\n")
