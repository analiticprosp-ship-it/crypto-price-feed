#!/usr/bin/env python3
"""09L v0.8.8 — first observed BTC liquidation per frozen 6h bucket.
Exploratory price-behavior proxies only, NOT evidence of mechanism or future cluster first-hit.
"""
import argparse,csv,datetime as dt,gzip,hashlib,io,json,math,pathlib,sys,urllib.request
ROOT=pathlib.Path(__file__).resolve().parent
OUT=ROOT/"derived"/"liquidation_event_proxies"
STUDIES={f"{'bybit' if v=='bybit' else 'okx'}_{m}":(v,"BTCUSDT" if v=="bybit" else "BTC-USDT-SWAP",f"2026-{n:02d}-01")
 for v in ("bybit","okex-swap") for m,n in (("feb",2),("mar",3),("apr",4),("may",5))}
BUCKETS=((6,12),(12,18),(18,24))
MAX_BYTES=160_000_000
def shaurl(venue,kind,day,symbol):
 return f"https://datasets.tardis.dev/v1/{venue}/{kind}/{day:%Y/%m/%d}/"+("PERPETUALS" if kind=="liquidations" else symbol)+".csv.gz"
class Tapped:
 def __init__(self,f):
  self.file=f;self.digest=hashlib.sha256();self.n=0
 def read(self,n=-1):
  b=self.file.read(n);self.n+=len(b);self.digest.update(b)
  if self.n>MAX_BYTES:raise ValueError("COMPRESSED_LIMIT")
  return b
def reader(url):
 req=urllib.request.Request(url,headers={"User-Agent":"09L-v088-shadow-asof-capture"})
 f=urllib.request.urlopen(req,timeout=90)
 assert f.status==200
 obj=Tapped(f)
 lines=csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=obj),encoding="utf8",newline=""))
 return obj,lines
def us0(day):
 return int(dt.datetime(day.year,day.month,day.day,tzinfo=dt.timezone.utc).timestamp()*1e6)
def number(s):
 x=float(s)
 if not math.isfinite(x):raise ValueError("NOT_FINITE")
 return x
def first_events(venue,symbol,day):
 url=shaurl(venue,"liquidations",day,symbol)
 info={"url":url,"kind":"observed_liquidation_messages"}
 anchors=[{"session_utc":f"{a:02d}:00-{b:02d}:00","session_start_hour":a,"event":None} for a,b in BUCKETS]
 zero=us0(day);counts=0;invalid=0;allrows=0;last=None;backwards=0
 tap=None
 try:
  tap,rows=reader(url)
  if not {"symbol","local_timestamp","side","price","amount"}.issubset(rows.fieldnames or []):
   raise ValueError("LIQUIDATION_COLUMNS_MISSING")
  for r in rows:
   allrows+=1
   if r["symbol"]!=symbol:continue
   try:
    ts=int(r["local_timestamp"]);side=r["side"].lower()
    price=number(r["price"]);amount=number(r["amount"])
    if side not in ("buy","sell") or price<=0 or amount<0 or not zero<=ts<zero+86400_000_000:raise ValueError()
   except (ValueError,TypeError,OverflowError):
    invalid+=1;continue
   counts+=1
   if last is not None and ts<last:backwards+=1
   last=ts
   for a in anchors:
    lo=zero+a["session_start_hour"]*3600_000_000
    hi=lo+6*3600_000_000
    if lo<ts<hi and a["event"] is None:
     a["event"]={"local_timestamp_us":ts,"side":side,"reported_liquidation_price":price,
                 "reported_liquidation_amount_native":amount}
  info.update(status="OK" if invalid==backwards==0 and counts>0 else "DATA_INCOMPLETE",
              rows_all_symbols=allrows,btc_liquidation_messages=counts,invalid=invalid,
              nonmonotonic_capture=backwards,
              gzip_sha256=tap.digest.hexdigest(),gzip_bytes=tap.n)
 except Exception as e:
  info.update(status="SOURCE_UNAVAILABLE",error_type=type(e).__name__)
 return anchors,info
def asof(pairs,target,staleness_us=2_000_000):
 x=pairs.get(target)
 if x is None:return None
 ts,p=x
 if ts>target or target-ts>staleness_us:return None
 return {"timestamp_us":ts,"age_ms":round((target-ts)/1000,4),"price":p}
def classify(continuation,peak):
 if continuation is None or peak is None:return "MISSING_ASOF"
 if continuation>=15 and peak>=20:return "CONTINUATION_PROXY"
 if continuation<=-10:return "OPPOSITE_REVERSAL_PROXY"
 if -10<continuation<=5 and peak<10:return "LIMITED_CONTINUATION_PROXY"
 return "MIXED_OR_UNCLASSIFIED"
def trades_evaluate(venue,symbol,day,anchors):
 url=shaurl(venue,"trades",day,symbol)
 info={"url":url,"kind":"individual_aggressive_trades"}
 events=[a for a in anchors if a["event"] is not None]
 for a in events:
  evt=a["event"]
  evt["past"]=[]
  evt["asof"]={}
  evt["max_signed_excursion_bps"]=None
  evt["observed_post_ticks"]=0
 allrows=0;selected=0;invalid=0;reversed=0;last=None;tap=None
 try:
  tap,rows=reader(url)
  if not {"symbol","local_timestamp","side","price","amount"}.issubset(rows.fieldnames or []):
   raise ValueError("TRADE_COLUMNS_MISSING")
  zero=us0(day)
  for r in rows:
   allrows+=1
   if r["symbol"]!=symbol:continue
   try:
    ts=int(r["local_timestamp"]);price=number(r["price"]);amount=number(r["amount"])
    side=r["side"].lower()
    if not zero<=ts<zero+86400_000_000 or price<=0 or amount<=0 or side not in ("buy","sell"):raise ValueError()
   except (ValueError,TypeError,OverflowError):invalid+=1;continue
   selected+=1
   if last is not None and ts<last:reversed+=1
   last=ts
   for a in events:
    evt=a["event"];t0=evt["local_timestamp_us"]
    if t0-30_000_000<=ts<t0:evt["past"].append((ts,price,amount,side))
    for delta_s in (-30,0,30,60,300):
     target=t0+delta_s*1_000_000
     if ts<=target and (target-ts)<=2_000_000:
      evt["asof"][target]=(ts,price)
    if t0<ts<=t0+300_000_000:
     evt["observed_post_ticks"]+=1
     ref=evt["asof"].get(t0)
     if ref is not None:
      direction=1 if evt["side"]=="buy" else -1
      move=10000*direction*(price/ref[1]-1)
      if evt["max_signed_excursion_bps"] is None or move>evt["max_signed_excursion_bps"]:
       evt["max_signed_excursion_bps"]=move
  info.update(status="OK" if selected>0 and invalid==0 and reversed==0 else "DATA_INCOMPLETE",
              rows_all_symbols=allrows,btc_trades=selected,invalid=invalid,
              nonmonotonic_capture=reversed,gzip_sha256=tap.digest.hexdigest(),gzip_bytes=tap.n)
 except Exception as e:
  info.update(status="SOURCE_UNAVAILABLE",error_type=type(e).__name__)
 return info
def study(which):
 venue,symbol,datestr=STUDIES[which];day=dt.date.fromisoformat(datestr)
 dest=OUT/venue/(datestr+"_first_message_behaviour.json")
 if dest.exists():return {"study":which,"status":"ALREADY_ARCHIVED"}
 anchors,liq=first_events(venue,symbol,day)
 trades=trades_evaluate(venue,symbol,day,anchors) if liq["status"]=="OK" else {"status":"SKIPPED_LIQUIDATION_SOURCE_NOT_OK"}
 for a in anchors:
  evt=a.get("event")
  if evt is None:
   a["status"]="NO_OBSERVED_LIQUIDATION_IN_BUCKET";continue
  t0=evt["local_timestamp_us"]
  ref=asof(evt["asof"],t0)
  mom=asof(evt["asof"],t0-30_000_000)
  past=evt.pop("past");pairs=evt.pop("asof")
  side_buy=sum(t[2] for t in past if t[3]=="buy")
  side_sell=sum(t[2] for t in past if t[3]=="sell")
  feats={"trades_pre_30s":len(past),"buy_amount_native_pre_30s":round(side_buy,8),
         "sell_amount_native_pre_30s":round(side_sell,8),
         "flow_imbalance_pre_30s":round((side_buy-side_sell)/(side_buy+side_sell),6) if side_buy+side_sell else None,
         "momentum_pre_30s_bps":round(10000*(past[-1][1]/mom["price"]-1),6) if past and mom else None,
         "range_pre_30s_bps":round(10000*(max(t[1] for t in past)-min(t[1] for t in past))/past[-1][1],6) if past else None}
  sign=1 if evt["side"]=="buy" else -1
  future={}
  for seconds in (30,60,300):
   p=asof(pairs,t0+seconds*1_000_000)
   future[str(seconds)]={"asof_age_ms":p["age_ms"] if p else None,
       "signed_return_bps":round(10000*sign*(p["price"]/ref["price"]-1),6) if p and ref else None}
  out300=future["300"]["signed_return_bps"]
  peak=evt.pop("max_signed_excursion_bps",None)
  status=classify(out300,peak) if evt["observed_post_ticks"]>0 else "MISSING_ASOF"
  a["status"]="EVALUATED_BEHAVIOUR_PROXY" if status!="MISSING_ASOF" else "MISSING_ASOF"
  a["pre_liquidation_features_only"]=feats
  a["reference_trade_asof"]=ref
  a["forward_outcomes_not_features"]=future
  a["maximum_same_direction_excursion_bps"]=round(peak,6) if peak is not None else None
  a["price_behaviour_label"]=status
 result={"study":"09L v0.8.8 retrospective FIRST OBSERVED liquidation message event behaviour",
       "source_day_utc":datestr,"venue":venue,"symbol":symbol,"trade_sources":trades,"liquidation_source":liq,
       "frozen_selection":"FIRST_BTC_LIQ_MSG_AFTER_06_12_18_UTC_SESSION_START",
       "selected_session_events":anchors,"event_count":sum(a["event"] is not None for a in anchors),
       "valid_behaviour_labels":sum(a.get("status")=="EVALUATED_BEHAVIOUR_PROXY" for a in anchors),
       "status":"EVENT_PROXIES_EXPLORATORY" if liq["status"]=="OK" and trades["status"]=="OK" else "DATA_INCOMPLETE",
       "scientific_restrictions":["Observed liquidation messages are NOT predicted pre-event clusters or CoinGlass Model2 heatmaps.",
       "No direct evidence of maker absorption, cancellation, or market-maker gamma.",
       "Signs are based on vendor reported liquidation side; BUY shorts / SELL longs.",
       "This is a first-message time-bucket sample, not a severity or representative event sample.",
       "No calibrated cascade probability or cluster first-hit probability; no trading authorization."],
       "coinglass_model2_pit":"MISSING","trading_canon_unchanged":True}
 dest.parent.mkdir(parents=True,exist_ok=True)
 with dest.open("x",encoding="utf8") as f:json.dump(result,f,ensure_ascii=False,indent=2,sort_keys=True);f.write("\n")
 cnt={}
 for a in anchors:
  label=a.get("price_behaviour_label",a["status"]);cnt[label]=cnt.get(label,0)+1
 return {"study":which,"status":result["status"],"events":result["event_count"],
         "valid_labels":result["valid_behaviour_labels"],"classes":cnt,
         "source_checks":[liq.get("status"),trades.get("status")],"path":str(dest.relative_to(ROOT))}
def main():
 p=argparse.ArgumentParser();p.add_argument("--study",choices=sorted(STUDIES))
 p.add_argument("--selftest",action="store_true")
 a=p.parse_args()
 if a.selftest:
  assert len(STUDIES)==8
  assert classify(18,23)=="CONTINUATION_PROXY"
  assert classify(-14,30)=="OPPOSITE_REVERSAL_PROXY"
  assert classify(3,8)=="LIMITED_CONTINUATION_PROXY"
  assert classify(9,8)=="MIXED_OR_UNCLASSIFIED"
  assert classify(None,8)=="MISSING_ASOF"
  print(json.dumps({"status":"SELFTEST_PASS"}));return
 if not a.study:p.error("requires --study")
 print(json.dumps(study(a.study)))
if __name__=="__main__":main()
