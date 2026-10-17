#!/usr/bin/env python3
"""Diagnose Binance XRPUSDT 5m Feb 2022 source ZIP; no R2 writes."""
import csv, datetime as dt, io, json, urllib.request, zipfile
url="https://data.binance.vision/data/futures/um/monthly/klines/XRPUSDT/5m/XRPUSDT-5m-2022-02.zip"
with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"DetectorResearch-diagnostic"}),timeout=120) as f:raw=f.read(100_000_001)
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 assert z.testzip() is None
 names=[n for n in z.namelist() if n.endswith(".csv")]
 assert len(names)==1
 ts=[]
 for row in csv.reader(io.TextIOWrapper(z.open(names[0]),encoding="utf-8-sig")):
  if row and row[0].isdigit():ts.append(int(row[0]))
start=int(dt.datetime(2022,2,1,tzinfo=dt.timezone.utc).timestamp()*1000)
end=int(dt.datetime(2022,3,1,tzinfo=dt.timezone.utc).timestamp()*1000)
observed=set(ts); expected=set(range(start,end,300000))
fmt=lambda x:dt.datetime.fromtimestamp(x/1000,dt.timezone.utc).isoformat()
missing=sorted(expected-observed)
extra=sorted(observed-expected)
gaps=[{"after":fmt(a),"before":fmt(b),"missing_candles":(b-a)//300000-1} for a,b in zip(ts,ts[1:]) if b-a!=300000]
print(json.dumps({"asset":"XRP","month":"2022-02","rows":len(ts),"expected":len(expected),"first":fmt(ts[0]),"last":fmt(ts[-1]),"missing_count":len(missing),"missing_first_10":[fmt(x) for x in missing[:10]],"extra_count":len(extra),"extra_first_10":[fmt(x) for x in extra[:10]],"non_5m_transitions":gaps[:20]},indent=2))
