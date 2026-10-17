#!/usr/bin/env python3
"""Detector v4.4 Kaggle source audit. Research-only. No signal generation."""
import csv,io,json,zipfile,urllib.request,urllib.error,hashlib,collections,datetime as dt
from pathlib import Path
O=Path("detector_kaggle_parity_v44_results");O.mkdir(exist_ok=True)
DATASETS=["jesusgraterol/bitcoin-open-interest-binance-futures","jesusgraterol/bitcoin-funding-rate-binance-futures","jesusgraterol/bitcoin-taker-buy-sell-volume-binance-futures"]
def fetch(url,limit=30_000_000):
 with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"DetectorResearch-v44"}),timeout=50) as r:
  b=r.read(limit+1)
  if len(b)>limit:raise ValueError("SIZE_CAP")
  return b
def timestamp(s):
 s=str(s).strip()
 try:
  v=float(s)
  if v>1e15:v/=1e6
  elif v>1e12:v/=1e3
  elif v>1e9:pass
  else:return None
  return int(v)
 except:pass
 try:return int(dt.datetime.fromisoformat(s.replace("Z","+00:00")).replace(tzinfo=dt.timezone.utc).timestamp()) if "+" not in s and "Z" not in s else int(dt.datetime.fromisoformat(s.replace("Z","+00:00")).timestamp())
 except:return None
reports=[];samples=[];errors=[]
for ref in DATASETS:
 owner,slug=ref.split("/")
 try:
  b=fetch(f"https://www.kaggle.com/api/v1/datasets/download/{owner}/{slug}")
  if not zipfile.is_zipfile(io.BytesIO(b)):raise ValueError("NON_ZIP")
  with zipfile.ZipFile(io.BytesIO(b)) as z:
   for name in z.namelist():
    if not name.lower().endswith(".csv"):continue
    with z.open(name) as f:
     reader=csv.DictReader(io.TextIOWrapper(f,encoding="utf-8-sig",errors="replace"))
     cols=reader.fieldnames or [];n=0;times=[];duplicates=0;seen=set();invalid=0
     datecols=[c for c in cols if any(x in c.lower() for x in ("timestamp","time","date"))]
     for row in reader:
      n+=1
      t=timestamp(row.get(datecols[0],"")) if datecols else None
      if t is None:invalid+=1
      else:
       if t in seen:duplicates+=1
       seen.add(t);times.append(t)
      if n<=3:samples.append({"dataset":ref,"file":name,"row":n,"data":json.dumps(row,ensure_ascii=False)[:1200]})
     diffs=[b-a for a,b in zip(times,times[1:])]
     positive=[d for d in diffs if d>0]
     mode=collections.Counter(positive).most_common(1)
     step=mode[0][0] if mode else None
     gaps=sum(max(0,(d//step)-1) for d in positive if step and d>step and d%step==0)
     reports.append({"dataset":ref,"file":name,"archive_sha256":hashlib.sha256(b).hexdigest(),"rows":n,"columns":"|".join(cols),"time_column":datecols[0] if datecols else "","first_timestamp_utc":dt.datetime.fromtimestamp(min(times),dt.timezone.utc).isoformat() if times else "","last_timestamp_utc":dt.datetime.fromtimestamp(max(times),dt.timezone.utc).isoformat() if times else "","modal_step_seconds":step or "","duplicates":duplicates,"unparseable_timestamps":invalid,"out_of_order":sum(d<=0 for d in diffs),"estimated_missing_steps":gaps,"primary_source_parity":"NOT_PROVEN","unit_parity":"NOT_PROVEN"})
 except Exception as e:errors.append({"dataset":ref,"error":type(e).__name__+":"+str(e)[:220]})
# Public exchange primary control: monthly Binance Futures 5m candle BTC 2023-08, real ZIP and taker base.
try:
 url="https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m/BTCUSDT-5m-2023-08.zip"
 b=fetch(url,20_000_000)
 with zipfile.ZipFile(io.BytesIO(b)) as z:
  csvname=next(x for x in z.namelist() if x.endswith(".csv"))
  with z.open(csvname) as f:
   rows=list(csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")))
   if rows and not rows[0][0].isdigit():rows=rows[1:]
   n=len(rows);valid=0;bad=0
   for r in rows:
    try:
     vol=float(r[5]);buy=float(r[9])
     if 0<=buy<=vol:valid+=1
     else:bad+=1
    except:bad+=1
   reports.append({"dataset":"PRIMARY_BINANCE_FUTURES_5M","file":csvname,"archive_sha256":hashlib.sha256(b).hexdigest(),"rows":n,"columns":"Binance standard kline 12 columns","time_column":"open_time_ms","first_timestamp_utc":dt.datetime.fromtimestamp(int(rows[0][0])/1000,dt.timezone.utc).isoformat(),"last_timestamp_utc":dt.datetime.fromtimestamp(int(rows[-1][0])/1000,dt.timezone.utc).isoformat(),"modal_step_seconds":300,"duplicates":"","unparseable_timestamps":"","out_of_order":"","estimated_missing_steps":"","primary_source_parity":f"volume>=taker_buy_base {valid}/{n}","unit_parity":"Kaggle taker ratio equivalence NOT PROVEN"})
except Exception as e:errors.append({"dataset":"PRIMARY_BINANCE_FUTURES_5M","error":type(e).__name__+":"+str(e)[:220]})
def write(name,rs):
 if not rs:rs=[{"note":"NO_ROWS"}]
 keys=list(dict.fromkeys(k for r in rs for k in r))
 with (O/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rs)
write("quality_report.csv",reports);write("sample_rows.csv",samples);write("errors.csv",errors)
(O/"manifest.json").write_text(json.dumps({"version":"4.4","datasets":DATASETS,"checks":"real Kaggle CSV temporal integrity + independent Binance Futures August 2023 5m control","limitations":["No proof that Kaggle taker values match original Binance takerlongshortRatio endpoint","No OI primary historical series parity yet","No funding primary historical value-by-value parity yet","CSV schema and timestamps inspected, not full exchange value matching","No trade signals, no portfolio changes"],"status":"RESEARCH_ONLY"},indent=2))
print(json.dumps({"files_audited":len(reports),"errors":errors}),flush=True)
