#!/usr/bin/env python3
"""Detector v4.5 — historical primary-source parity probes, research-only.
Never silently promote Kaggle values; record failures and missing overlap explicitly.
"""
import urllib.request,urllib.error,zipfile,io,csv,json,collections,datetime as dt,hashlib,time
from pathlib import Path
O=Path("detector_kaggle_primary_v45_results");O.mkdir(exist_ok=True)
def get(url,limit=30_000_000):
 req=urllib.request.Request(url,headers={"User-Agent":"DetectorResearch-v45","Accept":"application/json"})
 with urllib.request.urlopen(req,timeout=35) as r:
  b=r.read(limit+1)
  if len(b)>limit:raise ValueError("SIZE_CAP")
  return b
def parse(s):
 s=str(s).strip()
 try:
  x=float(s)
  if x>1e15:x/=1e6
  elif x>1e12:x/=1e3
  elif x<1e9:return None
  return int(x)
 except:pass
 try:return int(dt.datetime.fromisoformat(s.replace("Z","+00:00")).replace(tzinfo=dt.timezone.utc).timestamp()) if ("Z" not in s and "+" not in s) else int(dt.datetime.fromisoformat(s.replace("Z","+00:00")).timestamp())
 except:return None
def kaggle(ref):
 owner,slug=ref.split("/")
 b=get(f"https://www.kaggle.com/api/v1/datasets/download/{owner}/{slug}")
 with zipfile.ZipFile(io.BytesIO(b)) as z:
  for fn in z.namelist():
   if fn.lower().endswith(".csv"):
    with z.open(fn) as f:
     r=csv.DictReader(io.TextIOWrapper(f,encoding="utf-8-sig",errors="replace"))
     return fn,list(r)
 raise ValueError("NO_CSV")
reports=[];examples=[]
for kind,ref in [("funding","jesusgraterol/bitcoin-funding-rate-binance-futures"),("oi","jesusgraterol/bitcoin-open-interest-binance-futures"),("taker","jesusgraterol/bitcoin-taker-buy-sell-volume-binance-futures")]:
 rec={"dataset":kind,"source":"Kaggle "+ref,"status":"NOT_VERIFIED","primary_parity":"NOT_PROVEN"}
 try:
  fn,rows=kaggle(ref);rec.update(file=fn,rows=len(rows),columns="|".join(rows[0]) if rows else "")
  cols=list(rows[0]) if rows else []
  tc=next((c for c in cols if any(t in c.lower() for t in ("timestamp","time","date"))),None)
  times=[parse(r.get(tc,"")) for r in rows] if tc else []
  valid=[t for t in times if t is not None]
  rec.update(time_column=tc or "",first_utc=dt.datetime.fromtimestamp(min(valid),dt.timezone.utc).isoformat() if valid else "",last_utc=dt.datetime.fromtimestamp(max(valid),dt.timezone.utc).isoformat() if valid else "")
  if kind=="funding":
   # Official Binance USD-M premiumIndexKlines archive is not funding history.
   # REST historical funding endpoint may be region blocked; explicitly report outcome.
   start=1690848000000;end=1690934400000
   url=f"https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&startTime={start}&endTime={end}&limit=1000"
   try:
    data=json.loads(get(url,1_000_000))
    rec["primary_status"]="BINANCE_FUNDING_REST_ACCESSIBLE" if isinstance(data,list) else "UNEXPECTED_PRIMARY_RESPONSE"
    rec["primary_rows"]=len(data) if isinstance(data,list) else 0
    # Compare only after explicitly resolving Kaggle rate column and matching exact fundingTime.
    if isinstance(data,list) and data:
     primary={int(x["fundingTime"])//1000:float(x["fundingRate"]) for x in data}
     candidate=[c for c in cols if "funding" in c.lower() and "rate" in c.lower()]
     match=0;different=0
     if candidate:
      for r,t in zip(rows,times):
       if t in primary:
        try:
         v=float(r[candidate[0]])
         if abs(v-primary[t])<=1e-10:match+=1
         else:different+=1
        except:pass
      rec.update(primary_overlap=match+different,exact_matches=match,mismatches=different,primary_parity="PARTIAL_MATCH" if match and not different else "NOT_PROVEN")
   except Exception as e:rec["primary_status"]="UNAVAILABLE_"+type(e).__name__;rec["primary_error"]=str(e)[:160]
  elif kind=="oi":
   url="https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=5m&limit=30"
   try:
    data=json.loads(get(url,1_000_000));rec["primary_status"]="RECENT_ONLY_NOT_HISTORICAL_2023";rec["primary_rows"]=len(data) if isinstance(data,list) else 0
   except Exception as e:rec["primary_status"]="UNAVAILABLE_"+type(e).__name__;rec["primary_error"]=str(e)[:160]
  else:
   # Public monthly kline archive has taker_buy_base, not independently same as REST takerlongshortRatio.
   rec["primary_status"]="BINANCE_KLINE_TAKER_BASE_AVAILABLE_V40_V44; ORIGINAL_RATIO_PARITY_NOT_PROVEN"
  rec["status"]="KAGGLE_CSV_READABLE"
 except Exception as e:rec.update(status="KAGGLE_DOWNLOAD_OR_PARSE_FAILED",error=type(e).__name__+":"+str(e)[:160])
 reports.append(rec)
def write(name,rs):
 keys=list(dict.fromkeys(k for r in rs for k in r))
 with (O/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rs)
write("primary_source_parity.csv",reports)
(O/"manifest.json").write_text(json.dumps({"version":"4.5","purpose":"Kaggle vs primary Binance historical parity; actual overlap required","limitations":["HTTP 451/403 is not a data mismatch","Binance openInterestHist public REST is limited history, not 2023 audit substitute","No Kaggle data approved without timestamp/value parity","Taker from Binance kline is not original takerlongshortRatio without independent confirmation","No live Detector, Futures, P&L or trading limit changes"],"status":"RESEARCH_ONLY"},indent=2))
print(json.dumps(reports,ensure_ascii=False),flush=True)
