#!/usr/bin/env python3
"""Check FRED ALFRED multi-vintage JSON schema. No outcomes inspected."""
import json, os, hashlib, urllib.parse, urllib.request, urllib.error, time
def req(series,ds,multiple):
 qs={"series_id":series,"api_key":os.environ["FRED_API_KEY"],"file_type":"json",
 "observation_start":"2024-08-01","observation_end":"2024-10-13","limit":10000}
 if multiple:
  qs.update(output_type=2,vintage_dates=",".join(ds))
 else:
  qs.update(realtime_start=ds[0],realtime_end=ds[0])
 url="https://api.stlouisfed.org/fred/series/observations?"+urllib.parse.urlencode(qs)
 with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"BTCI 8.18b vintage schema probe"}),timeout=45) as response:
  body=response.read(1500000)
 x=json.loads(body)
 rows=x.get("observations",[])
 print("BATCH_SCHEMA",json.dumps({"series":series,"multi":multiple,"requestDates":ds,
  "responseMeta":{k:v for k,v in x.items() if k not in ("observations","api_key")},
  "observationsCount":len(rows),"observationKeys":list(rows[0]) if rows else [],
  "observationSamples":rows[-3:] if rows else [],
  "sha256":hashlib.sha256(body).hexdigest()},ensure_ascii=False),flush=True)
def main():
 for s in ["DFII10","T10Y2Y","DTWEXBGS"]:
  dates=["2024-10-06","2024-10-13"]
  req(s,dates,True)
  req(s,[dates[0]],False)
  time.sleep(1.5)
if __name__=="__main__":main()
