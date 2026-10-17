#!/usr/bin/env python3
"""Three consecutive days of real Binance aggTrades, 5m aggressive flow; research only."""
import collections,csv,datetime as dt,hashlib,io,json,pathlib,urllib.request,zipfile
DAYS=("2026-09-01","2026-09-02","2026-09-03")
OUT=pathlib.Path("detector_h1_h10_aggtrades_3day");OUT.mkdir(exist_ok=True)
MAX_ZIP=300_000_000
manifest={"dates":DAYS,"source":"Binance public aggTrades archives","flow_rule":"isBuyerMaker true means taker sell","datasets":[]}
for market in ("spot","perp"):
 for sym in ("BTCUSDT","ETHUSDT","SOLUSDT"):
  all_slots=collections.defaultdict(lambda:[0,0.,0.,0.,0.]);day_reports=[]
  for day in DAYS:
   prefix="spot" if market=="spot" else "futures/um"
   url=f"https://data.binance.vision/data/{prefix}/daily/aggTrades/{sym}/{sym}-aggTrades-{day}.zip"
   d={"date":day,"url":url,"status":"ERROR"}
   try:
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Detector-Research/1.0"}),timeout=120) as resp:
     length=int(resp.headers.get("Content-Length","0"))
     if length>MAX_ZIP:raise ValueError("zip_size_exceeds_limit")
     b=io.BytesIO();digest=hashlib.sha256()
     while True:
      c=resp.read(1048576)
      if not c:break
      if b.tell()+len(c)>MAX_ZIP:raise ValueError("zip_stream_exceeds_limit")
      b.write(c);digest.update(c)
    start=int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp()*1000)
    trades=0;invalid=0;day_slots=set()
    with zipfile.ZipFile(b) as z:
     names=[x for x in z.namelist() if x.endswith(".csv")]
     if len(names)!=1:raise ValueError("csv_entry_count_invalid")
     with z.open(names[0]) as f:
      for r in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig",newline="")):
       if not r or r[0].lower() in ("agg_trade_id","aggtradeid","a"):continue
       try:
        price=float(r[1]);qty=float(r[2]);t=int(r[5]);maker=r[6].lower()
        if t>10**14:t//=1000
        if not(start<=t<start+86400000 and price>0 and qty>0 and maker in ("true","false")):raise ValueError()
        slot=t//300000*300000
        v=all_slots[slot];v[0]+=1
        if maker=="false":v[1]+=qty;v[3]+=qty*price
        else:v[2]+=qty;v[4]+=qty*price
        day_slots.add(slot);trades+=1
       except (ValueError,IndexError,OverflowError):invalid+=1
    d.update({"status":"VERIFIED","archive_sha256":digest.hexdigest(),"aggtrades":trades,"invalid_rows":invalid,"occupied_5m_slots":len(day_slots),"zip_bytes":b.tell()})
   except Exception as e:d["error"]=str(e)[:200]
   day_reports.append(d);print("DAY",market,sym,json.dumps(d),flush=True)
  path=OUT/f"{market}_{sym}_2026-09-01_to_03_5m.csv"
  with path.open("w",newline="") as f:
   w=csv.writer(f);w.writerow(["timestamp_utc","aggtrade_count","taker_buy_base","taker_sell_base","taker_buy_quote","taker_sell_quote","delta_quote","total_quote"])
   for t,v in sorted(all_slots.items()):
    w.writerow([dt.datetime.fromtimestamp(t/1000,dt.timezone.utc).isoformat(),v[0],f"{v[1]:.12f}",f"{v[2]:.12f}",f"{v[3]:.12f}",f"{v[4]:.12f}",f"{v[3]-v[4]:.12f}",f"{v[3]+v[4]:.12f}"])
  manifest["datasets"].append({"market":market,"symbol":sym,"days":day_reports,"output":path.name,"occupied_5m_slots":len(all_slots),"expected_5m_slots":864})
  print("DATASET",market,sym,"slots",len(all_slots),flush=True)
(OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print("SUMMARY",json.dumps({"archives_verified":sum(d["status"]=="VERIFIED" for x in manifest["datasets"] for d in x["days"]),"archives_attempted":18,"total_aggtrades":sum(d.get("aggtrades",0) for x in manifest["datasets"] for d in x["days"])}),flush=True)
