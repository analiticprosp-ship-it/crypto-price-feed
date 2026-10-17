#!/usr/bin/env python3
"""Download real Binance aggTrades for one day; 5m taker buy/sell volume, strict evidence."""
import collections,csv,datetime as dt,hashlib,io,json,pathlib,urllib.request,zipfile
DATE="2026-10-01";MAX_ZIP=300_000_000
OUT=pathlib.Path("detector_h1_h10_aggtrades_pilot");OUT.mkdir(exist_ok=True)
report={"date":DATE,"time_zone":"UTC","source":"Binance public data archive aggTrades","semantics":"isBuyerMaker=true => aggressive seller; false => aggressive buyer; quantity in base units, not USD","files":[]}
for market in ("spot","perp"):
 for sym in ("BTCUSDT","ETHUSDT","SOLUSDT"):
  prefix="spot" if market=="spot" else "futures/um"
  url=f"https://data.binance.vision/data/{prefix}/daily/aggTrades/{sym}/{sym}-aggTrades-{DATE}.zip"
  item={"market":market,"symbol":sym,"url":url,"status":"ERROR"}
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"Detector-Research/1.0"})
   with urllib.request.urlopen(req,timeout=120) as resp:
    size=int(resp.headers.get("Content-Length","0"))
    if size>MAX_ZIP:raise ValueError(f"ZIP_SIZE_LIMIT: {size}")
    buf=io.BytesIO();h=hashlib.sha256()
    while True:
     chunk=resp.read(1024*1024)
     if not chunk:break
     if buf.tell()+len(chunk)>MAX_ZIP:raise ValueError("ZIP_STREAM_LIMIT")
     buf.write(chunk);h.update(chunk)
   item["archive_sha256"]=h.hexdigest();item["zip_bytes"]=buf.tell()
   with zipfile.ZipFile(buf) as z:
    names=[n for n in z.namelist() if n.endswith(".csv")]
    if len(names)!=1:raise ValueError(f"CSV_ENTRY_COUNT: {len(names)}")
    stats=collections.defaultdict(lambda:[0,0.0,0.0,0.0,0.0])
    count=0;bad=0;first=None;last=None
    with z.open(names[0]) as raw:
     reader=csv.reader(io.TextIOWrapper(raw,encoding="utf-8-sig",newline=""))
     for r in reader:
      if not r:continue
      if r[0].lower() in ("agg_trade_id","aggtradeid","a"):continue
      if len(r)<7:bad+=1;continue
      try:
       price=float(r[1]);qty=float(r[2]);t=int(r[5]);maker=r[6].strip().lower()
       if t>10**14:t//=1000
       if maker not in ("true","false") or price<=0 or qty<=0:raise ValueError("invalid")
       if not (dt.datetime(2026,10,1,tzinfo=dt.timezone.utc).timestamp()*1000<=t<dt.datetime(2026,10,2,tzinfo=dt.timezone.utc).timestamp()*1000):raise ValueError("outside_day")
       slot=t//300000*300000
       v=stats[slot];v[0]+=1
       if maker=="false":v[1]+=qty;v[3]+=qty*price
       else:v[2]+=qty;v[4]+=qty*price
       count+=1;first=t if first is None else min(first,t);last=t if last is None else max(last,t)
      except (ValueError,IndexError,OverflowError):bad+=1
   path=OUT/f"{market}_{sym}_{DATE}_5m.csv"
   with path.open("w",newline="") as f:
    w=csv.writer(f);w.writerow(["timestamp_utc","trade_count","taker_buy_base","taker_sell_base","taker_buy_quote","taker_sell_quote","delta_quote","total_quote"])
    for slot,v in sorted(stats.items()):
     w.writerow([dt.datetime.fromtimestamp(slot/1000,dt.timezone.utc).isoformat(),v[0],format(v[1],".10g"),format(v[2],".10g"),format(v[3],".10g"),format(v[4],".10g"),format(v[3]-v[4],".10g"),format(v[3]+v[4],".10g")])
   item.update({"status":"DOWNLOADED_AGGREGATED","trades":count,"invalid_rows":bad,"occupied_5m_slots":len(stats),"first_trade_ms":first,"last_trade_ms":last,"output":path.name})
  except Exception as e:item["error"]=str(e)[:250]
  report["files"].append(item);print("AGGTRADES",json.dumps(item),flush=True)
(OUT/"manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print("SUMMARY",json.dumps({"success":sum(x["status"]=="DOWNLOADED_AGGREGATED" for x in report["files"]),"total":len(report["files"]),"trades":sum(x.get("trades",0) for x in report["files"])}),flush=True)
