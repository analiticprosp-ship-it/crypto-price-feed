#!/usr/bin/env python3
"""SHADOW ONLY: measure post-detection 15m OHLC moves, never trading signals."""
import argparse,csv,json,time,datetime as dt
from pathlib import Path
import requests

UTC=dt.timezone.utc
def iso(ms):return dt.datetime.fromtimestamp(ms/1000,UTC).isoformat()
def ms(s):return int(dt.datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()*1000)
def candles(session,symbol,start,end):
    url="https://www.okx.com/api/v5/market/history-candles"
    out={}
    cursor=end+1
    for _ in range(80):
        if cursor<=start:break
        data=None
        for retry in range(4):
            try:
                r=session.get(url,params={"instId":symbol+"-USDT-SWAP","bar":"15m","after":str(cursor),"limit":"100"},timeout=25)
                r.raise_for_status();obj=r.json()
                if obj.get("code")!="0":raise RuntimeError(str(obj))
                data=obj.get("data",[]);break
            except Exception:
                if retry==3:raise
                time.sleep(2**retry)
        if not data:break
        oldest=cursor
        for x in data:
            t=int(x[0]);oldest=min(oldest,t)
            if start-900000<=t<=end and x[8]=="1":
                out[t]={"t":t,"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4])}
        if oldest>=cursor:break
        cursor=oldest-1
        time.sleep(.12)
    return sorted(out.values(),key=lambda x:x["t"])

def measure(event,bars,cutoff):
    detect=ms(event["firstDetectedAtUtc"])
    # Exclude any candle already underway at detection: avoids lookahead within bar.
    eligible=[b for b in bars if b["t"]>=((detect+899999)//900000)*900000 and b["t"]+900000<=cutoff]
    result={"event_id":event["id"],"symbol":event["symbol"],"direction":event["direction"],
            "detected_utc":event["firstDetectedAtUtc"],"signal_bar_closed_utc":event["barClosedAtUtc"],
            "observation_policy":"FIRST_FULL_15M_BAR_AFTER_DETECTION",
            "observation_start_utc":iso(eligible[0]["t"]) if eligible else None,
            "bars":len(eligible),"status":"OK" if eligible else "NO_COMPLETE_POST_DETECTION_BARS"}
    if not eligible:return result
    # Price known without lookahead: close of the last completed 15m candle at detection.
    previous=[b for b in bars if b["t"]+900000<=detect]
    if not previous:
        result["status"]="NO_PRE_DETECTION_REFERENCE";return result
    base=previous[-1]["c"];sign=1 if event["direction"]=="LONG" else -1
    favorable=[100*sign*((b["h"] if sign==1 else b["l"])/base-1) for b in eligible]
    adverse=[100*(-sign)*((b["l"] if sign==1 else b["h"])/base-1) for b in eligible]
    peak=max(range(len(eligible)),key=lambda i:favorable[i])
    result.update(reference_price=base,reference_at_utc=iso(previous[-1]["t"]+900000),
                  max_favorable_pct=round(favorable[peak],5),peak_bar_start_utc=iso(eligible[peak]["t"]),
                  minutes_to_peak_bar_end=round((eligible[peak]["t"]+900000-detect)/60000,2),
                  max_adverse_pct=round(max(adverse),5),
                  final_close_signed_pct=round(100*sign*(eligible[-1]["c"]/base-1),5))
    for threshold in (.5,1,2,3,5):
        ix=next((i for i,x in enumerate(favorable) if x>=threshold),None)
        key="threshold_"+str(threshold).replace(".","_")
        result[key+"_first_minutes"]=round((eligible[ix]["t"]+900000-detect)/60000,2) if ix is not None else None
        # High/low proves a touch, not how long price remained beyond the level.
        # Close-based consecutive full bars after first qualifying close is a conservative proxy.
        closes=[100*sign*(b["c"]/base-1)>=threshold for b in eligible]
        runs=[];n=0
        for good in closes:
            if good:n+=1
            elif n:runs.append(n);n=0
        if n:runs.append(n)
        result[key+"_longest_close_run_minutes"]=15*max(runs,default=0)
        result[key+"_total_closes_minutes"]=15*sum(closes)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument("--date",default="2026-10-16");p.add_argument("--out",default="detector_event_followthrough_results");a=p.parse_args()
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    data=json.loads(Path("detector-signal-events.json").read_text())
    events=[e for e in data["events"] if e.get("firstDetectedAtUtc","").startswith(a.date) and e.get("status")=="EARLY_CANDIDATE_SHADOW"]
    cutoff=int(dt.datetime.now(UTC).timestamp()*1000)
    start=min((ms(e["firstDetectedAtUtc"]) for e in events),default=cutoff)-3600000
    s=requests.Session();s.headers.update({"User-Agent":"shadow-detector-followthrough/1.0"})
    rows=[];errors={}
    for sym in sorted({e["symbol"] for e in events}):
        try:
            bars=candles(s,sym,start,cutoff)
            subset=[e for e in events if e["symbol"]==sym]
            for e in subset:rows.append(measure(e,bars,cutoff))
            print(sym,len(bars),"bars",len(subset),"events",flush=True)
        except Exception as exc:
            errors[sym]=str(exc)
            for e in events:
                if e["symbol"]==sym:rows.append({"event_id":e["id"],"symbol":sym,"direction":e["direction"],"status":"FETCH_FAILED"})
    columns=sorted({k for r in rows for k in r})
    with (dest/"events.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)
    manifest={"status":"SHADOW_RESEARCH_ONLY","date":a.date,"generated_at_utc":iso(cutoff),
      "event_count":len(events),"rows":len(rows),"errors":errors,
      "reference":"LAST_COMPLETED_15M_CLOSE_AT_DETECTION","evaluation":"FIRST_FULL_15M_BAR_AFTER_DETECTION",
      "limitations":["15m OHLC cannot resolve intrabar order or exact peak minute","Close-run duration is a 15m sampled proxy, not continuous holding time","No live execution, fees, spreads or alert delivery timestamps"]}
    (dest/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps(manifest,indent=2))
if __name__=="__main__":main()
