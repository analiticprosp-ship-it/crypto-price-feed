#!/usr/bin/env python3
"""P3: exact Tardis L2 day access probe; never confuse metadata with downloadable data."""
import datetime as dt,json,os,pathlib,urllib.error,urllib.parse,urllib.request
out=pathlib.Path("/tmp/p3-tardis-day-access");out.mkdir(exist_ok=True)
venues={"coinbase":["BTC-USD","ETH-USD"],"gate-io":["BTC_USDT","ETH_USDT"],"crypto-com":["BTC_USDT","ETH_USDT"],"mexc":["BTCUSDT","ETHUSDT"]}
rows=[]
for venue,symbols in venues.items():
 for symbol in symbols:
  q={"exchange":venue,"dataType":"incremental_book_L2","date":"2026-10-29","symbol":symbol}
  key=os.getenv("TARDIS_API_KEY")
  if key:q["apiKey"]=key
  url="https://api.tardis.dev/v1/data-feeds/"+urllib.parse.quote(venue)+"/"+urllib.parse.quote(symbol,safe="")+"/"+urllib.parse.quote("2026-10-29")
  row={"provider":"tardis","venue":venue,"symbol_candidate":symbol,"date":"2026-10-29","status":"NOT_PROBED"}
  # HEAD only: test URL/auth without downloading multi-GB streams. Do not treat 200 as validated file.
  try:
   req=urllib.request.Request(url,method="HEAD",headers={"User-Agent":"P3-L2-historical-access-probe/1",**({"Authorization":"Bearer "+key} if key else {})})
   with urllib.request.urlopen(req,timeout=20) as response:row.update(status="HEAD_RESPONSE_ONLY",http_status=response.status,content_type=response.headers.get("Content-Type"))
  except urllib.error.HTTPError as e:row.update(status="HTTP_ERROR",http_status=e.code)
  except Exception as e:row.update(status="REQUEST_ERROR",error_type=type(e).__name__)
  rows.append(row);print(venue,symbol,row["status"],row.get("http_status"),flush=True)
(out/"access_manifest.json").write_text(json.dumps({"schema":"P3_TARDIS_DAY_ACCESS_DIAGNOSTIC_V1","caveat":"Endpoint path and HEAD support not verified. HTTP 404/405 is NOT proof of absent data. This diagnostic does not download L2.","generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"rows":rows},indent=2))
