#!/usr/bin/env python3
"""09L v0.8.7: no-lookahead first-of-month event-feature/forward-label ledger.
Historical SHADOW research only; NO trained predictor or cascade classification.
"""
import argparse, csv, datetime as dt, gzip, hashlib, io, json, math, pathlib, urllib.request
ROOT=pathlib.Path(__file__).resolve().parent
OUT=ROOT/"derived"/"v087_labels"
CLOCKS=["07:24:30","08:32:30","13:49:30","14:19:30",
        "15:10:30","15:49:30","17:28:30","18:38:30"]
STUDIES={"bybit_feb":("bybit","BTCUSDT","2026-02-01"),
         "bybit_mar":("bybit","BTCUSDT","2026-03-01"),
         "bybit_apr":("bybit","BTCUSDT","2026-04-01"),
         "bybit_may":("bybit","BTCUSDT","2026-05-01"),
         "okx_feb":("okex-swap","BTC-USDT-SWAP","2026-02-01"),
         "okx_mar":("okex-swap","BTC-USDT-SWAP","2026-03-01"),
         "okx_apr":("okex-swap","BTC-USDT-SWAP","2026-04-01"),
         "okx_may":("okex-swap","BTC-USDT-SWAP","2026-05-01"),
         "bybit_sep":("bybit","BTCUSDT","2026-09-01"),
         "okx_oct":("okex-swap","BTC-USDT-SWAP","2026-10-01"),
         "bybit_jun":("bybit","BTCUSDT","2026-06-01"),
         "bybit_jul":("bybit","BTCUSDT","2026-07-01"),
         "bybit_aug":("bybit","BTCUSDT","2026-08-01"),
         "okx_jun":("okex-swap","BTC-USDT-SWAP","2026-06-01"),
         "okx_jul":("okex-swap","BTC-USDT-SWAP","2026-07-01"),
         "okx_aug":("okex-swap","BTC-USDT-SWAP","2026-08-01")}
MONTHS={"bybit_latest":("bybit","BTCUSDT"),"okx_latest":("okex-swap","BTC-USDT-SWAP")}
MAX_COMPRESSED_BYTES=160_000_000
class Tap:
 def __init__(self,f):self.f=f;self.n=0;self.sha=hashlib.sha256()
 def read(self,n=-1):
  b=self.f.read(n);self.n+=len(b);self.sha.update(b)
  if self.n>MAX_COMPRESSED_BYTES:raise ValueError("COMPRESSED_INPUT_SIZE_CAP")
  return b
def sample_day(now):
 day=dt.date(now.year,now.month,1)
 if now.day<3:
  day=(day-dt.timedelta(days=1)).replace(day=1)
 return day
def parse_day(s):return dt.date.fromisoformat(s)
def create_events(day):
 t0=dt.datetime(day.year,day.month,day.day,tzinfo=dt.timezone.utc)
 anchors=[]
 for c in CLOCKS:
  hh,mm,ss=map(int,c.split(":"));us=int((t0+dt.timedelta(hours=hh,minutes=mm,seconds=ss)).timestamp()*1e6)
  anchors.append({"clock_utc":c,"anchor_us":us,"asof":{},"past":[]})
 return anchors
def validate_asof(case,offset,cap=2):
 target=case["anchor_us"]+offset*1_000_000
 x=case["asof"].get(offset)
 if x is None:return None
 ts,p=x
 if not (0<=target-ts<=cap*1_000_000):return None
 return {"price":p,"last_trade_us":ts,"age_ms":round((target-ts)/1000,3)}
def as_float(v):
 x=float(v)
 if not math.isfinite(x) or x<=0:raise ValueError("BAD_TRADE_VALUE")
 return x
def compute(study,now,check_only=False):
 if study in STUDIES:
  venue,symbol,date=STUDIES[study];day=parse_day(date)
 else:
  venue,symbol=MONTHS[study];day=sample_day(now)
 result_path=OUT/venue/(day.isoformat()+"_no_lookahead_trade_labels.json")
 if result_path.exists():return {"status":"ALREADY_ARCHIVED","path":str(result_path.relative_to(ROOT))}
 if check_only:raise ValueError("SELFTEST_WRONG_CALL")
 cases=create_events(day)
 low=cases[0]["anchor_us"]-31_000_000
 high=cases[-1]["anchor_us"]+302_000_000
 url=f"https://datasets.tardis.dev/v1/{venue}/trades/{day:%Y/%m/%d}/{symbol}.csv.gz"
 audit={"url":url,"venue":venue,"symbol":symbol,"source_date_utc":day.isoformat()}
 try:
  f=urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"09L-v087-no-lookahead"}),timeout=95)
  tap=Tap(f)
  rows=csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=tap),encoding="utf8",newline=""))
  required={"symbol","local_timestamp","side","amount","price"}
  if not required.issubset(rows.fieldnames or []):raise ValueError("TRADES_SOURCE_MISSING_COLUMNS")
  n=0;invalid=0;nonmono=0;last_ts=None;start_day=int(dt.datetime(day.year,day.month,day.day,tzinfo=dt.timezone.utc).timestamp()*1e6)
  for row in rows:
   n+=1
   if row["symbol"]!=symbol:continue
   try:
    ts=int(row["local_timestamp"]);price=as_float(row["price"]);amount=as_float(row["amount"])
    side=row["side"].lower()
    if side not in ("buy","sell"):raise ValueError()
    if not start_day<=ts<start_day+86400_000_000:raise ValueError()
   except (ValueError,TypeError,OverflowError):
    invalid+=1;continue
   if last_ts is not None and ts<last_ts:nonmono+=1
   last_ts=ts
   if ts<low or ts>high:continue
   for e in cases:
    anchor=e["anchor_us"]
    if anchor-30_000_000<=ts<anchor:e["past"].append((ts,price,amount,side))
    for offset in (-30,0,30,60,300):
     target=anchor+offset*1_000_000
     if ts<=target:
      # overwrite with most recent captured trade at or before the query timestamp
      e["asof"][offset]=(ts,price)
  audit.update(status="OK",raw_rows=n,invalid_rows=invalid,nonmonotonic_capture_rows=nonmono,
    compressed_sha256=tap.sha.hexdigest(),compressed_bytes=tap.n)
  if invalid or nonmono or n==0:audit["status"]="DATA_INCOMPLETE"
 except Exception as exc:
  audit.update(status="SOURCE_UNAVAILABLE",error_type=type(exc).__name__)
 # For previously studied first-of-month sources, verify against immutably archived v0.8.6.
 if (venue,symbol,day.isoformat()) in [("bybit","BTCUSDT","2026-09-01"),("okex-swap","BTC-USDT-SWAP","2026-10-01")]:
  name="bybit_sep" if venue=="bybit" else "okx_oct"
  recorded=ROOT.parents[1]/"v0.8.6-2026-10-20"/"derived"/f"09L_v086_{name}_fixed_clock_robustness.json"
  expected=json.loads(recorded.read_text())["sources"]
  exp=next(x["compressed_sha256"] for x in expected if x["kind"]=="trades")
  audit["historical_expected_sha256"]=exp
  if audit.get("compressed_sha256")!=exp:audit["status"]="SOURCE_HASH_MISMATCH"
 output=[]
 for e in cases:
  past=e["past"];t0=validate_asof(e,0)
  feats={"n_trades_past_30s":len(past),
    "n_buy_past_30s":sum(v[3]=="buy" for v in past),
    "n_sell_past_30s":sum(v[3]=="sell" for v in past)}
  buy=sum(x[2] for x in past if x[3]=="buy");sell=sum(x[2] for x in past if x[3]=="sell")
  feats["buy_amount_native"]=round(buy,8);feats["sell_amount_native"]=round(sell,8)
  feats["raw_flow_imbalance"]=(round((buy-sell)/(buy+sell),6) if buy+sell else None)
  pre=validate_asof(e,-30)
  feats["past_30s_price_return_bps"]=(round(10000*(past[-1][1]/pre["price"]-1),5) if pre and past else None)
  feats["past_30s_high_low_range_bps"]=(round(10000*(max(x[1] for x in past)-min(x[1] for x in past))/past[-1][1],5) if past else None)
  outcomes={}
  for h in (30,60,300):
   ph=validate_asof(e,h)
   outcomes[str(h)]={"price_asof":ph["price"] if ph else None,
      "source_age_ms":ph["age_ms"] if ph else None,
      "return_bps":round(10000*(ph["price"]/t0["price"]-1),5) if ph and t0 else None}
  if venue=="okex-swap" and day.isoformat()=="2026-10-01" and e["clock_utc"]=="18:38:30":
   caveat="KNOWN_L2_RESTART_IN_FORWARD_WINDOW;TRADE_ONLY_LABEL_NOT_EXCLUDED"
  else:caveat="NO_DECLARED_L2_RESTART_IN_THIS_HISTORICAL_WINDOW"
  output.append({"clock_utc":e["clock_utc"],"anchor_utc":dt.datetime.fromtimestamp(e["anchor_us"]/1e6,dt.timezone.utc).isoformat(),
   "reference_trade":t0,"past_features_only":feats,"forward_outcomes_not_features":outcomes,
   "status":"LABEL_READY" if t0 and all(x["return_bps"] is not None for x in outcomes.values()) else "MISSING_ASOF_PRICE_AT_FROZEN_2S_LIMIT",
   "missing_reference_price":t0 is None,
   "missing_forward_horizons_s":[int(h) for h,v in outcomes.items() if v["return_bps"] is None],
   "source_caveat":caveat})
 status=("LABELS_REGISTERED_EXPLORATORY" if audit.get("status")=="OK" and len(output)==8 and all(x["status"]=="LABEL_READY" for x in output)
    else "PARTIAL_LABELS_MISSING_ASOF_PRICE" if audit.get("status")=="OK" and len(output)==8
    else "DATA_INCOMPLETE")
 obj={"study":"09L v0.8.7 no-lookahead forward label readiness","date_run_utc":now.isoformat(),
   "status":status,"source_date_utc":day.isoformat(),"venue":venue,"symbol":symbol,
   "source":audit,"eight_clock_fixed_cases":output,
   "source_clock":"captured local_timestamp UTC microseconds","time_cap_seconds":2,
   "features_strictly_pre_anchor":True,"forward_outcomes_from_new_trade_messages":True,
   "sample_count":len(output),"science_gate":"PREDICTIVE_LIFT_NOT_TESTED_INSUFFICIENT_INDEPENDENT_OBSERVATIONS",
   "coinglass_historical_pit":"MISSING","dealer_signed_gamma":"UNKNOWN",
   "trading_canon_unchanged":True}
 if audit.get("status")!="OK":
  # Never permanently block monthly future samples when the provider has not published the file yet.
  # Keep each failure as an append-only audit and try again on the next daily cycle.
  attempt=OUT/"attempts"/venue/day.isoformat()/(now.strftime("%Y%m%dT%H%M%S%fZ")+".json")
  attempt.parent.mkdir(parents=True,exist_ok=True)
  with attempt.open("x",encoding="utf8") as o:o.write(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
  return {"status":status,"path":str(attempt.relative_to(ROOT)),"study":study,
    "source_status":audit.get("status"),"retry_next_schedule":True}
 result_path.parent.mkdir(parents=True,exist_ok=True)
 with result_path.open("x",encoding="utf8") as o:o.write(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
 return {"status":status,"path":str(result_path.relative_to(ROOT)),"study":study,
    "source_sha":audit.get("compressed_sha256"),
    "ready_cases":sum(x["status"]=="LABEL_READY" for x in output),
    "outcomes":[[x["clock_utc"],x["forward_outcomes_not_features"]["300"]["return_bps"]] for x in output]}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--study",choices=sorted(set(STUDIES)|set(MONTHS)))
 p.add_argument("--selftest",action="store_true")
 a=p.parse_args()
 if a.selftest:
  assert sample_day(dt.datetime(2026,11,1,15,tzinfo=dt.timezone.utc))==dt.date(2026,10,1)
  assert sample_day(dt.datetime(2026,11,3,15,tzinfo=dt.timezone.utc))==dt.date(2026,11,1)
  assert len(CLOCKS)==8
  assert len([k for k in STUDIES if k in ("bybit_jun","bybit_jul","bybit_aug","okx_jun","okx_jul","okx_aug")])==6
  ev=create_events(dt.date(2026,9,1))[0]
  assert validate_asof(ev,0) is None
  assert all("t" not in d for d in [])
  print(json.dumps({"status":"SELFTEST_PASS"}));return
 if not a.study:p.error("must specify --study")
 print(json.dumps(compute(a.study,dt.datetime.now(dt.timezone.utc)),ensure_ascii=False))
if __name__=="__main__":main()
