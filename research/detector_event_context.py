#!/usr/bin/env python3
"""SHADOW only. Point-in-time RS versus BTC and OKX OI/funding context."""
import argparse,csv,datetime as dt,json,time
from pathlib import Path
import requests
from detector_event_followthrough import candles,ms,iso
UTC=dt.timezone.utc
def get(s,path,params):
    for retry in range(4):
        try:
            r=s.get("https://www.okx.com"+path,params=params,timeout=25);r.raise_for_status()
            j=r.json()
            if j.get("code")!="0":raise RuntimeError(str(j))
            return j.get("data",[])
        except Exception:
            if retry==3:raise
            time.sleep(2**retry)
def historical(s,path,inst,start,end,limit=100):
    found={};cursor=end+1
    for _ in range(60):
        if cursor<=start:break
        arr=get(s,path,{"instId":inst,"after":str(cursor),"limit":str(limit)})
        if not arr:break
        oldest=cursor
        for x in arr:
            t=int(x.get("ts",0));oldest=min(oldest,t)
            if start<=t<=end:found[t]=x
        if oldest>=cursor:break
        cursor=oldest-1;time.sleep(.12)
    return [found[t] for t in sorted(found)]
def prior_close(bars,t):
    a=[b for b in bars if b["t"]+900000<=t]
    return a[-1]["c"] if a else None
def main():
    p=argparse.ArgumentParser();p.add_argument("--date",default="2026-10-16");p.add_argument("--out",default="detector_context_results");a=p.parse_args()
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    events=[e for e in json.loads(Path("detector-signal-events.json").read_text())["events"] if e.get("firstDetectedAtUtc","").startswith(a.date) and e.get("status")=="EARLY_CANDIDATE_SHADOW"]
    cutoff=int(dt.datetime.now(UTC).timestamp()*1000)
    begin=min([ms(e["firstDetectedAtUtc"]) for e in events],default=cutoff)-26*3600000
    s=requests.Session();s.headers["User-Agent"]="shadow-point-in-time-context/1.0"
    prices={};oi={};funding={};errors={}
    for sym in sorted({e["symbol"] for e in events}|{"BTC"}):
        inst=sym+"-USDT-SWAP"
        try:prices[sym]=candles(s,sym,begin,cutoff)
        except Exception as exc:errors[sym+"_price"]=str(exc);prices[sym]=[]
        if sym=="BTC":continue
        try:oi[sym]=historical(s,"/api/v5/rubik/stat/contracts/open-interest-history",inst,begin,cutoff)
        except Exception as exc:errors[sym+"_oi"]=str(exc);oi[sym]=[]
        try:funding[sym]=historical(s,"/api/v5/public/funding-rate-history",inst,begin-3*86400000,cutoff)
        except Exception as exc:errors[sym+"_funding"]=str(exc);funding[sym]=[]
    rows=[]
    for e in events:
        t=ms(e["firstDetectedAtUtc"]);sym=e["symbol"];pb=prices.get(sym,[]);bb=prices.get("BTC",[])
        row={"event_id":e["id"],"symbol":sym,"direction":e["direction"],"detected_utc":e["firstDetectedAtUtc"],
             "status":"SHADOW_CONTEXT","rs_1h_pct_points":None,"rs_4h_pct_points":None,
             "oi_status":"UNAVAILABLE","funding_status":"UNAVAILABLE","oi_delta_1h_pct":None,
             "funding_rate_pct":None,"funding_effective_utc":None}
        for hours in (1,4):
            now=prior_close(pb,t);old=prior_close(pb,t-hours*3600000)
            btcnow=prior_close(bb,t);btcold=prior_close(bb,t-hours*3600000)
            if None not in (now,old,btcnow,btcold) and old>0 and btcold>0:
                row["rs_"+str(hours)+"h_pct_points"]=round(100*((now/old-1)-(btcnow/btcold-1)),5)
        # OI source can differ by endpoint schema; accept only explicit timestamped values.
        obs=[]
        for x in oi.get(sym,[]):
            try:
                ts=int(x["ts"])
                value=float(x.get("oi",x.get("openInterest")))
                if ts<=t:obs.append((ts,value))
            except (ValueError,TypeError,KeyError):continue
        if obs:
            obs.sort();recent=obs[-1];old=[x for x in obs if x[0]<=recent[0]-3600000]
            row["oi_asof_utc"]=iso(recent[0]);row["oi_status"]="ASOF_ONLY_NO_1H_PAIR"
            if old and old[-1][1]>0:
                row["oi_delta_1h_pct"]=round(100*(recent[1]/old[-1][1]-1),5)
                row["oi_status"]="HISTORICAL_ALIGNED"
        fr=[]
        for x in funding.get(sym,[]):
            try:
                effective=int(x["fundingTime"]);rate=float(x["fundingRate"])
                if effective<=t:fr.append((effective,rate))
            except (ValueError,TypeError,KeyError):continue
        if fr:
            effective,rate=max(fr)
            row["funding_status"]="LAST_SETTLED_ASOF"
            row["funding_rate_pct"]=round(rate*100,7)
            row["funding_effective_utc"]=iso(effective)
        rows.append(row)
    keys=sorted({k for row in rows for k in row})
    with (dest/"context.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
    manifest={"status":"SHADOW_RESEARCH_ONLY","date":a.date,"event_count":len(events),"rows":len(rows),
      "generated_at_utc":iso(cutoff),"errors":errors,"oi_status_counts":{x:sum(r["oi_status"]==x for r in rows) for x in set(r["oi_status"] for r in rows)},
      "limitations":["OI history endpoint may not expose timestamped contract OI; unavailable is not confirmation",
      "OI and funding are correlated with price and each other; not independent votes",
      "Only funding settlements with fundingTime <= detection are used; no future funding leakage",
      "RS uses last completed 15m closes for asset and BTC at detection and lookback",
      "Research only; no live detector modification"]}
    (dest/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps(manifest,indent=2))
if __name__=="__main__":main()
