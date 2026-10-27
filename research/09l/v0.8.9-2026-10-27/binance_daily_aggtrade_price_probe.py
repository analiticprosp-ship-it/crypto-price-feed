#!/usr/bin/env python3
"""09L v089B non-first-of-month Binance USD-M aggTrades public ZIP receipt audit.
Frozen eight clocks, price-only directional labels, no liquidation or CoinGlass inference.
Do not conflate aggTrades with individual fills, receipt timestamps, or true PIT OI.
"""
import argparse,csv,datetime as dt,hashlib,io,json,math,pathlib,re,urllib.request,zipfile
ROOT=pathlib.Path(__file__).resolve().parent
OUT=ROOT/"derived"/"daily_binance"
DATES=tuple(f"2026-10-{n:02d}" for n in range(19,27))
FORWARD_START=dt.date(2026,10,27)
def valid_day(day):
 try:d=dt.date.fromisoformat(day)
 except ValueError:return False
 return day in DATES or (FORWARD_START<=d<dt.datetime.now(dt.timezone.utc).date())
def recent_days():
 today=dt.datetime.now(dt.timezone.utc).date()
 return [str(d) for j in range(7,0,-1) if (d:=today-dt.timedelta(days=j))>=FORWARD_START]
CLOCKS=("07:24:30","08:32:30","13:49:30","14:19:30","15:10:30","15:49:30","17:28:30","18:38:30")
BASE="https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/"
MAX_ZIP=140_000_000
def day_ms(day):
 return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp()*1000)
def validate_num(z):
 a=float(z)
 if not math.isfinite(a) or a<=0:raise ValueError("INVALID_PRICE_OR_QTY")
 return a
def fetch(url,max_bytes):
 req=urllib.request.Request(url,headers={"User-Agent":"09L-v089B-research-only","Accept":"application/octet-stream"})
 with urllib.request.urlopen(req,timeout=90) as f:
  if f.status!=200:raise ValueError("NON_200_SOURCE_RESPONSE")
  raw=f.read(max_bytes+1)
 if len(raw)>max_bytes:raise ValueError("SOURCE_TOO_LARGE")
 return raw
def parse(day):
 if not valid_day(day):raise ValueError("DATE_NOT_PRE_REGISTERED_OR_NOT_COMPLETED")
 archived=OUT/(day+".json")
 if archived.exists():
  meta=json.loads(archived.read_text(encoding="utf8"))
  if meta.get("status")=="DAILY_PRICE_ONLY_EXPLORATORY":
   return {"date":day,"status":"ALREADY_ARCHIVED","path":str(archived.relative_to(ROOT))}
 filename=f"BTCUSDT-aggTrades-{day}.zip"
 url=BASE+filename
 observed_at=dt.datetime.now(dt.timezone.utc).isoformat()
 source={"venue":"binance-usdm","instrument":"BTCUSDT","data_type":"aggregated_trades_not_individual_fills",
         "source_date_utc":day,"source_url":url,"publisher_checksum_url":url+".CHECKSUM",
         "received_at_utc":observed_at,"status":"UNAVAILABLE"}
 result={"study":"09L v089B distinct non-month-start days price/flow comparator",
   "source":source,"date":day,"scope":"RESEARCH_SHADOW_ONLY",
   "coinglass_model2_pit":"MISSING_NOT_COLLECTED",
   "actual_liquidation_prints":"NOT_COLLECTED_NO_CASCADE_LABELS",
   "venue":"binance-usdm","symbol":"BTCUSDT","trading_canon_unchanged":True}
 try:
  checked=fetch(url+".CHECKSUM",2048).decode("utf8").strip().splitlines()
  checksum=[line for line in checked if filename in line]
  if len(checksum)!=1:raise ValueError("CHECKSUM_AMBIGUOUS_OR_MISSING")
  match=re.match(r"^([a-fA-F0-9]{64})\s+\*?(.+)$",checksum[0].strip())
  if not match or match.group(2)!=filename:raise ValueError("WRONG_PUBLISHER_CHECKSUM")
  expected=match.group(1).lower()
  raw=fetch(url,MAX_ZIP);sha=hashlib.sha256(raw).hexdigest()
  if sha!=expected:raise ValueError("PUBLISHER_SHA256_MISMATCH")
  start=day_ms(day);end=start+86_400_000
  events=[]
  for clock in CLOCKS:
   h,m,s=map(int,clock.split(":"))
   anchor=start+(h*3600+m*60+s)*1000
   events.append({"clock_utc":clock,"t0_ms":anchor,"past":[],"asof":{}})
  low=events[0]["t0_ms"]-32_000;high=events[-1]["t0_ms"]+302_000
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   infos=[i for i in z.infolist() if i.filename.endswith(".csv")]
   if len(infos)!=1 or len(z.infolist())!=1:raise ValueError("UNEXPECTED_ZIP_CONTENTS")
   if infos[0].file_size>650_000_000:raise ValueError("UNCOMPRESSED_TOO_LARGE")
   with z.open(infos[0]) as f:
    rows=csv.reader(io.TextIOWrapper(f,encoding="utf8",newline=""))
    n=0;invalid=0;backwards=0;last_ts=None;last_id=None;header_skipped=False
    for row in rows:
     if n==0 and row and (row[0].lower() in ("aggtradeid","agg_trade_id")):
      header_skipped=True;continue
     n+=1
     try:
      if len(row)!=7:raise ValueError("SCHEMA_NOT_SEVEN_COLUMNS")
      agg=int(row[0]);p=validate_num(row[1]);qty=validate_num(row[2]);f_id=int(row[3]);l_id=int(row[4])
      ts=int(row[5]);maker=row[6].lower()
      if maker not in ("true","false") or f_id>l_id or agg<0 or not(start<=ts<end):
       raise ValueError("INVALID_SCHEMA_OR_TIMESTAMP")
     except (ValueError,TypeError,OverflowError) as e:
      invalid+=1
      if invalid<=2:source["first_invalid_type"]=type(e).__name__
      continue
     if last_ts is not None and ts<last_ts:backwards+=1
     last_ts=ts
     if last_id is not None and agg<=last_id:source["nonincreasing_agg_id"]=source.get("nonincreasing_agg_id",0)+1
     last_id=agg
     if ts<low or ts>high:continue
     side="sell" if maker=="true" else "buy"
     for ev in events:
      t0=ev["t0_ms"]
      if t0-30_000<=ts<t0:ev["past"].append((ts,p,qty,side))
      for offset in (-30,0,30,60,300):
       target=t0+offset*1000
       if 0<=target-ts<=2000:ev["asof"][offset]=(ts,p)
    # Closing the zip member validates CRC32 against ZIP metadata.
  source.update(status="OK" if n>0 and invalid==backwards==0 and source.get("nonincreasing_agg_id",0)==0 else "DATA_INVALID",
       publisher_sha256=expected,downloaded_zip_sha256=sha,zip_bytes=len(raw),
       uncompressed_csv_bytes=infos[0].file_size,zip_crc32_verified=True,
       total_aggtrade_rows=n,invalid_rows=invalid,backwards_timestamp_rows=backwards,
       header_skipped=header_skipped,timestamp_unit="milliseconds_exchange_recorded_not_original_receipt")
  output=[]
  for ev in events:
   old=ev["asof"].get(-30);ref=ev["asof"].get(0);past=ev["past"]
   buy=sum(x[2] for x in past if x[3]=="buy");sell=sum(x[2] for x in past if x[3]=="sell")
   momentum=(10000*(past[-1][1]/old[1]-1) if old and past else None)
   flow=(buy-sell)/(buy+sell) if buy+sell else None
   forward={}
   for h in (30,60,300):
    future=ev["asof"].get(h)
    forward[str(h)]={"asof_age_ms":ev["t0_ms"]+h*1000-future[0] if future else None,
         "return_bps":round(10000*(future[1]/ref[1]-1),6) if ref and future else None}
   output.append({"clock_utc":ev["clock_utc"],"asof_ref_age_ms":ev["t0_ms"]-ref[0] if ref else None,
      "n_aggtrades_past30s":len(past),
      "past_only":{"momentum_bps":round(momentum,6) if momentum is not None else None,
                   "buy_agg_amount_native":round(buy,8),"sell_agg_amount_native":round(sell,8),
                   "raw_agg_flow_imbalance":round(flow,6) if flow is not None else None},
      "forward_outcomes_not_features":forward,
      "status":"LABEL_READY" if ref and forward["300"]["return_bps"] is not None and momentum is not None and flow is not None else "MISSING_ASOF_OR_PRIOR_FEATURE"})
  result.update(status="DAILY_PRICE_ONLY_EXPLORATORY" if source["status"]=="OK" else "SOURCE_DATA_INVALID",
    eight_fixed_utc_windows=output,
    horizons_seconds=[30,60,300],
    exclusions="asof_max_2s_no_imputation",
    scientifically_not_comparable_to_raw_Tardis_trade_message_counts=True,
    not_prospective_sealed_holdout=True,
    no_liquidation_first_touch_established=True)
 except Exception as e:
  source.update(status="UNAVAILABLE_OR_INVALID",error_type=type(e).__name__,
                error_category=str(e)[:90] if isinstance(e,ValueError) else type(e).__name__)
  result.update(status="SOURCE_UNAVAILABLE_OR_INVALID",eight_fixed_utc_windows=[])
 dest=OUT/(day+".json")
 if result["status"]!="DAILY_PRICE_ONLY_EXPLORATORY":
  dest=OUT/"attempts"/day/(dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+".json")
 dest.parent.mkdir(parents=True,exist_ok=True)
 with dest.open("x",encoding="utf8") as f:json.dump(result,f,indent=2,ensure_ascii=False,sort_keys=True);f.write("\n")
 return {"date":day,"status":result["status"],"source_status":source["status"],
   "rows":source.get("total_aggtrade_rows"),"input_sha256":source.get("downloaded_zip_sha256"),
   "labels_ready":sum(x["status"]=="LABEL_READY" for x in result["eight_fixed_utc_windows"]),
   "error_category":source.get("error_category"),"path":str(dest.relative_to(ROOT))}
def main():
 p=argparse.ArgumentParser();p.add_argument("--date")
 p.add_argument("--recent",action="store_true")
 p.add_argument("--selftest",action="store_true")
 a=p.parse_args()
 if a.selftest:
  assert len(DATES)==8 and len(CLOCKS)==8
  assert day_ms("2026-10-24")%86400000==0
  assert valid_day("2026-10-25") and not valid_day("2026-10-28") if dt.datetime.now(dt.timezone.utc).date()==dt.date(2026,10,27) else True
  print(json.dumps({"status":"SELFTEST_PASS","dates":len(DATES),"future_start":FORWARD_START.isoformat()}));return
 if a.recent:
  ds=recent_days()
  if not ds:print(json.dumps({"status":"NO_CLOSED_FORWARD_DAILY_DATES_YET"}));return
  for day in ds:print(json.dumps(parse(day),ensure_ascii=False),flush=True)
  return
 if not a.date:p.error("requires --date or --recent")
 print(json.dumps(parse(a.date),ensure_ascii=False))
if __name__=="__main__":main()
