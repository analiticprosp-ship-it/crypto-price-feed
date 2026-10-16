#!/usr/bin/env python3
"""SHADOW only: conservative first-touch outcomes and delayed entries on OKX 5m candles."""
import argparse,csv,datetime as dt,json,time
from pathlib import Path
import requests
UTC=dt.timezone.utc
def ms(x):return int(dt.datetime.fromisoformat(x.replace("Z","+00:00")).timestamp()*1000)
def iso(x):return dt.datetime.fromtimestamp(x/1000,UTC).isoformat()
def getbars(s,sym,start,end):
    found={};cursor=end+1
    for _ in range(180):
        if cursor<=start:break
        for attempt in range(4):
            try:
                r=s.get("https://www.okx.com/api/v5/market/history-candles",params={"instId":sym+"-USDT-SWAP","bar":"5m","after":str(cursor),"limit":"100"},timeout=25)
                r.raise_for_status();j=r.json()
                if j.get("code")!="0":raise RuntimeError(str(j))
                data=j.get("data",[]);break
            except Exception:
                if attempt==3:raise
                time.sleep(2**attempt)
        if not data:break
        oldest=cursor
        for a in data:
            t=int(a[0]);oldest=min(oldest,t)
            if start-300000<=t<=end and a[8]=="1":
                found[t]=(t,float(a[1]),float(a[2]),float(a[3]),float(a[4]))
        if oldest>=cursor:break
        cursor=oldest-1;time.sleep(.10)
    return [found[t] for t in sorted(found)]
def trial(e,bars,delay,anchor,window,target,stop,cutoff):
    signal=ms(e["barClosedAtUtc"]);detected=ms(e["firstDetectedAtUtc"])
    planned=(detected if anchor=="detected" else signal)+delay*60000
    # No entry before actual discovery, even in hypothetical bar-close-delay scenario.
    if planned<detected:return {"status":"BEFORE_DETECTION"}
    # First open of 5m bar beginning at or after planned time. An open is not an executable quote.
    entry_bar=next((i for i,b in enumerate(bars) if b[0]>=planned and b[0]+300000<=cutoff),None)
    if entry_bar is None:return {"status":"ENTRY_NOT_OBSERVED"}
    entry=bars[entry_bar];price=entry[1];sgn=1 if e["direction"]=="LONG" else -1
    limit=entry[0]+window*60000
    future=[b for b in bars[entry_bar:] if b[0]+300000<=min(limit,cutoff)]
    if not future:return {"status":"NO_FULL_BARS"}
    result={"status":"OK" if cutoff>=limit else "RIGHT_CENSORED","entry_utc":iso(entry[0]),
       "entry_price":price,"entry_lag_from_close_min":round((entry[0]-signal)/60000,2),
       "entry_lag_from_detection_min":round((entry[0]-detected)/60000,2),
       "bars_evaluated":len(future)}
    outcome="NO_TOUCH";first=None
    for b in future:
        favorable=100*sgn*((b[2] if sgn==1 else b[3])/price-1)
        adverse=100*(-sgn)*((b[3] if sgn==1 else b[2])/price-1)
        hit=favorable>=target;bad=adverse>=stop
        if hit and bad:outcome="AMBIGUOUS_SAME_5M_BAR";first=b;break
        if bad:outcome="STOP_FIRST";first=b;break
        if hit:outcome="TARGET_FIRST";first=b;break
    result["outcome"]=outcome
    result["first_touch_bar_end_min"]=round((first[0]+300000-entry[0])/60000,2) if first else None
    result["max_favorable_pct"]=round(max(100*sgn*((b[2] if sgn==1 else b[3])/price-1) for b in future),4)
    result["max_adverse_pct"]=round(max(100*(-sgn)*((b[3] if sgn==1 else b[2])/price-1) for b in future),4)
    # Mark uncertain stop-vs-target ordering as ambiguous, never as a win.
    return result
def main():
    p=argparse.ArgumentParser();p.add_argument("--date",default="2026-10-16");p.add_argument("--out",default="detector_entry_window_results");a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    events=[e for e in json.loads(Path("detector-signal-events.json").read_text())["events"] if e.get("firstDetectedAtUtc","").startswith(a.date) and e.get("status")=="EARLY_CANDIDATE_SHADOW"]
    cutoff=int(dt.datetime.now(UTC).timestamp()*1000)
    start=min((ms(e["barClosedAtUtc"]) for e in events),default=cutoff)-600000
    s=requests.Session();s.headers["User-Agent"]="shadow-entry-window-audit/1.0"
    data={};errors={}
    for sym in sorted({e["symbol"] for e in events}):
        try:data[sym]=getbars(s,sym,start,cutoff);print(sym,len(data[sym]),flush=True)
        except Exception as exc:data[sym]=[];errors[sym]=str(exc)
    rows=[]
    for e in events:
        for anchor,delays in (("detected",(0,15,20,30,45,60)),("bar_close",(0,15,20,30,45,60))):
            for delay in delays:
                for window in (30,60,120,240):
                    for target in (1,2):
                        for stop in (.5,1):
                            base={"event_id":e["id"],"symbol":e["symbol"],"direction":e["direction"],
                                "bar_closed_utc":e["barClosedAtUtc"],"detected_utc":e["firstDetectedAtUtc"],
                                "anchor":anchor,"delay_minutes":delay,"window_minutes":window,
                                "target_pct":target,"stop_pct":stop}
                            base.update(trial(e,data[e["symbol"]],delay,anchor,window,target,stop,cutoff))
                            rows.append(base)
    keys=sorted({k for x in rows for k in x})
    with (out/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
    summary={}
    for row in rows:
        key=(row["anchor"],row["delay_minutes"],row["window_minutes"],row["target_pct"],row["stop_pct"])
        if key not in summary:summary[key]={"anchor":key[0],"delay_minutes":key[1],"window_minutes":key[2],"target_pct":key[3],"stop_pct":key[4],"events":0,"wins":0,"stops":0,"ambiguous":0,"censored":0,"unavailable":0,"no_touch":0}
        x=summary[key];x["events"]+=1
        if row["status"]=="RIGHT_CENSORED":x["censored"]+=1;continue
        if row["status"]!="OK":x["unavailable"]+=1;continue
        x[{"TARGET_FIRST":"wins","STOP_FIRST":"stops","AMBIGUOUS_SAME_5M_BAR":"ambiguous","NO_TOUCH":"no_touch"}[row["outcome"]]]+=1
    with (out/"summary.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(next(iter(summary.values())).keys()));w.writeheader();w.writerows(summary.values())
    manifest={"status":"SHADOW_RESEARCH_ONLY","date":a.date,"generated_utc":iso(cutoff),
      "events":len(events),"trials":len(rows),"errors":errors,
      "rules":["5m OHLC first touch, simultaneous target and stop is AMBIGUOUS not win",
       "Entry is next available 5m open at/after chosen delay; fills, fees, spread not modeled",
       "Bar-close anchored scenarios before first detection are impossible and excluded",
       "Right-censored windows excluded from full-window win rate",
       "Correlated repeat signals are not independent observations",
       "Alert delivery timestamp unavailable; modeled delay is hypothetical"],
      "source":"OKX public 5m history candles"}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))
if __name__=="__main__":main()
