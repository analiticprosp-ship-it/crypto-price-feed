#!/usr/bin/env python3
"""SHADOW only: full 5m path, counter-signal excursion and conditional pullback entries."""
import argparse,csv,json,datetime as dt,time
from pathlib import Path
import requests
from detector_entry_window_v01 import getbars,ms,iso
UTC=dt.timezone.utc
def write(path,rows):
    if not rows:return
    keys=sorted({k for r in rows for k in r})
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def evaluate_path(event,bars,cutoff):
    detect=ms(event["firstDetectedAtUtc"]);sgn=1 if event["direction"]=="LONG" else -1
    start=next((i for i,b in enumerate(bars) if b[0]>=detect and b[0]+300000<=cutoff),None)
    if start is None:return [],[],[]
    price=bars[start][1];origin=bars[start][0]
    path=[];entry=[];summary=[]
    for window in (30,60,120,240):
        subset=[b for b in bars[start:] if b[0]+300000<=min(origin+window*60000,cutoff)]
        if not subset:continue
        favorable=[100*sgn*((b[2] if sgn==1 else b[3])/price-1) for b in subset]
        adverse=[100*(-sgn)*((b[3] if sgn==1 else b[2])/price-1) for b in subset]
        r={"event_id":event["id"],"symbol":event["symbol"],"direction":event["direction"],"window_min":window,
           "complete":cutoff>=origin+window*60000,"max_favorable_pct":round(max(favorable),5),
           "max_adverse_pct":round(max(adverse),5),"entry_utc":iso(origin)}
        for x in (.25,.5,1,1.5,2):
            ix=next((i for i,v in enumerate(adverse) if v>=x),None)
            r["adverse_"+str(x).replace(".","_")+"_touched"]=ix is not None
            r["adverse_"+str(x).replace(".","_")+"_first_bar_end_min"]=5*(ix+1) if ix is not None else None
        summary.append(r)
    for b in bars[start:]:
        if b[0]+300000>min(origin+240*60000,cutoff):break
        path.append({"event_id":event["id"],"symbol":event["symbol"],"direction":event["direction"],
          "minute":int((b[0]-origin)/60000),"utc":iso(b[0]),"open_pct":round(100*sgn*(b[1]/price-1),5),
          "high_favorable_pct":round(100*sgn*((b[2] if sgn==1 else b[3])/price-1),5),
          "low_adverse_pct":round(100*sgn*((b[3] if sgn==1 else b[2])/price-1),5),
          "close_pct":round(100*sgn*(b[4]/price-1),5)})
    # Trigger is known only after a completed candle CLOSE below adverse threshold.
    # Entry at next 5m OPEN, preventing same-candle lookahead and fictional low fills.
    for threshold in (.25,.5,.75,1,1.5):
        for max_wait in (30,60,120):
            trigger=None
            for i,b in enumerate(bars[start:],start):
                if b[0]+300000>min(origin+max_wait*60000,cutoff):break
                signed_close=100*sgn*(b[4]/price-1)
                if signed_close<=-threshold:
                    trigger=i;break
            for window in (60,120):
                for target in (1,2):
                    for stop in (.5,1):
                        base={"event_id":event["id"],"symbol":event["symbol"],"direction":event["direction"],
                          "pullback_threshold_pct":threshold,"trigger_wait_min":max_wait,
                          "post_entry_window_min":window,"target_pct":target,"stop_pct":stop}
                        if trigger is None:base["status"]="NO_TRIGGER";entry.append(base);continue
                        idx=trigger+1
                        if idx>=len(bars) or bars[idx][0]!=bars[trigger][0]+300000 or bars[idx][0]+300000>cutoff:
                            base["status"]="NO_NEXT_BAR";entry.append(base);continue
                        ep=bars[idx][1];end=bars[idx][0]+window*60000
                        future=[b for b in bars[idx:] if b[0]+300000<=min(end,cutoff)]
                        if not future:base["status"]="NO_FOLLOWUP";entry.append(base);continue
                        result="NO_TOUCH";first=None
                        for b in future:
                            fav=100*sgn*((b[2] if sgn==1 else b[3])/ep-1)
                            adv=100*(-sgn)*((b[3] if sgn==1 else b[2])/ep-1)
                            if fav>=target and adv>=stop:result="AMBIGUOUS_SAME_5M_BAR";first=b;break
                            if adv>=stop:result="STOP_FIRST";first=b;break
                            if fav>=target:result="TARGET_FIRST";first=b;break
                        base.update(status="COMPLETE" if cutoff>=end else "RIGHT_CENSORED",
                          outcome=result,trigger_bar_end_utc=iso(bars[trigger][0]+300000),
                          entry_utc=iso(bars[idx][0]),entry_price=ep,
                          entry_delay_from_detection_min=round((bars[idx][0]-detect)/60000,2),
                          first_touch_minutes=round((first[0]+300000-bars[idx][0])/60000,2) if first else None)
                        entry.append(base)
    return path,summary,entry
def main():
    p=argparse.ArgumentParser();p.add_argument("--date",default="2026-10-16");p.add_argument("--out",default="detector_path_pullback_results");a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    events=[e for e in json.loads(Path("detector-signal-events.json").read_text())["events"] if e.get("firstDetectedAtUtc","").startswith(a.date) and e.get("status")=="EARLY_CANDIDATE_SHADOW"]
    cutoff=int(dt.datetime.now(UTC).timestamp()*1000)
    start=min([ms(e["firstDetectedAtUtc"]) for e in events],default=cutoff)-600000
    s=requests.Session();s.headers["User-Agent"]="shadow-full-path-pullback/1.0"
    bars={};errors={}
    for sym in sorted({e["symbol"] for e in events}):
        try:bars[sym]=getbars(s,sym,start,cutoff);print(sym,len(bars[sym]),flush=True)
        except Exception as ex:bars[sym]=[];errors[sym]=str(ex)
    paths=[];summaries=[];entries=[]
    for e in events:
        p,sm,en=evaluate_path(e,bars[e["symbol"]],cutoff)
        paths+=p;summaries+=sm;entries+=en
    write(out/"paths_5m.csv",paths);write(out/"adverse_frequency.csv",summaries);write(out/"pullback_entries.csv",entries)
    manifest={"mode":"SHADOW_RESEARCH_ONLY","events":len(events),"path_rows":len(paths),
      "adverse_rows":len(summaries),"entry_scenarios":len(entries),"errors":errors,
      "generated_utc":iso(cutoff),"rules":["Adverse touch is measured on every event, including failed signals",
       "Pullback trigger requires completed 5m candle close, entry is next 5m open",
       "A low/high wick alone never grants a fill at that price",
       "Both target and stop within same 5m bar => AMBIGUOUS, not win",
       "RIGHT_CENSORED excluded from full-window win-rate denominators",
       "Repeated correlated alerts are not independent trades",
       "5m OHLC cannot establish intrabar ordering; execution friction not modeled",
       "No guaranteed profits or live trading changes"]}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))
if __name__=="__main__":main()
