#!/usr/bin/env python3
"""Read-only historical L2 source metadata and one free-day accessibility probe."""
import datetime as dt,json,os,pathlib,urllib.error,urllib.parse,urllib.request
OUT=pathlib.Path(os.environ.get("P3_OUT","/tmp/p3-source-catalog"));OUT.mkdir(parents=True,exist_ok=True)
venues=["coinbase","coinbase-pro","gate-io","cryptocom","mexc","kraken"]
rows=[]
for venue in venues:
 url="https://api.tardis.dev/v1/exchanges/"+urllib.parse.quote(venue,safe="")
 item={"provider":"tardis","venue_candidate":venue,"status":"NOT_CHECKED"}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"P3-source-coverage-research/1"}),timeout=20) as response:
   body=response.read(2000000);item["http_status"]=response.status
   obj=json.loads(body);item["status"]="METADATA_RECEIVED"
   item["exchange_id"]=obj.get("id");item["datasets"]=obj.get("datasets");item["available_since"]=obj.get("availableSince");item["available_to"]=obj.get("availableTo")
   item["symbols_btc_eth_candidates"]=[x for x in obj.get("availableSymbols",[]) if isinstance(x,str) and ("BTC" in x or "ETH" in x)][:30]
 except urllib.error.HTTPError as e:item.update(status="HTTP_ERROR",http_status=e.code)
 except Exception as e:item.update(status="REQUEST_ERROR",error_type=type(e).__name__)
 rows.append(item);print(venue,item["status"],item.get("http_status"),flush=True)
(OUT/"tardis_exchange_metadata.json").write_text(json.dumps({"schema":"P3_TARDIS_COVERAGE_METADATA_V1","generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"rows":rows},indent=2,default=str))
