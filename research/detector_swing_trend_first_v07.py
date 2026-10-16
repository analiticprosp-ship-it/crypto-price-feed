#!/usr/bin/env python3
"""SHADOW-only 1W+1D trend-first swing study; no trade authorization."""
import argparse,json,math,time
from pathlib import Path
import requests,pandas as pd,numpy as np
API="https://www.okx.com/api/v5/market/history-candles"
p=argparse.ArgumentParser()
p.add_argument("--days",type=int,default=730)
p.add_argument("--out",default="detector_swing_v07_results")
a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
quality=[];events=[]
for symbol in "BTC ETH SOL XRP HYPE LINK LDO SUI AAVE".split():
    cutoff=int((pd.Timestamp.now(tz="UTC")-pd.Timedelta(days=a.days)).timestamp()*1000)
    rows={};after=None;errors=[]
    for page in range(math.ceil(a.days*24/100)+10):
        params={"instId":symbol+"-USDT-SWAP","bar":"1H","limit":"100"}
        if after is not None:params["after"]=str(after)
        try:
            r=requests.get(API,params=params,timeout=30);r.raise_for_status();j=r.json()
            if j.get("code")!="0":raise ValueError(str(j)[:200])
            batch=j.get("data",[])
            if not batch:break
            for b in batch:
                if int(b[0])>=cutoff and b[8]=="1":rows[int(b[0])]=list(map(float,b[1:6]))
            oldest=min(int(b[0]) for b in batch)
            if oldest<=cutoff or (after is not None and oldest>=after):break
            after=oldest;time.sleep(.12)
        except Exception as e:
            errors.append(str(e));break
    h=pd.DataFrame([(t,*v) for t,v in rows.items()],columns=["ms","open","high","low","close","volume"])
    q={"symbol":symbol,"bars":len(h),"errors":errors}
    if h.empty:quality.append(q);continue
    h["time"]=pd.to_datetime(h.ms,unit="ms",utc=True)
    h=h.set_index("time").sort_index().drop(columns="ms")
    q.update(first=str(h.index.min()),last=str(h.index.max()),gaps=len(pd.date_range(h.index.min(),h.index.max(),freq="1h").difference(h.index)))
    quality.append(q);print(q,flush=True)
    def agg(rule,n):
        x=h.resample(rule,origin="epoch",label="left").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
        cnt=h.close.resample(rule,origin="epoch",label="left").count()
        return x[cnt==n].dropna()
    f=agg("4h",4);d=agg("1D",24);w=agg("7D",168)
    if len(f)<100 or len(d)<35 or len(w)<12:continue
    hi=f.high.shift(1).rolling(12).max();lo=f.low.shift(1).rolling(12).min()
    wma=w.close.rolling(8).mean()
    dma=d.close.rolling(20).mean();dprev=d.close.shift(5)
    for i in range(25,len(f)-1):
        b=f.iloc[i];prev=f.iloc[i-1];t=f.index[i]+pd.Timedelta(hours=4)
        avail=d[d.index+pd.Timedelta(days=1)<=t]
        if len(avail)<21:continue
        wa=w[w.index+pd.Timedelta(days=7)<=t]
        if len(wa)<9:continue
        wi=w.index.get_loc(wa.index[-1]);wc=w.close.iloc[wi]
        weekly_trend=1 if wc>wma.iloc[wi] and wc>w.close.iloc[wi-4] else (-1 if wc<wma.iloc[wi] and wc<w.close.iloc[wi-4] else 0)
        ix=d.index.get_loc(avail.index[-1]);dc=d.close.iloc[ix]
        trend=1 if dc>dma.iloc[ix] and dc>dprev.iloc[ix] else (-1 if dc<dma.iloc[ix] and dc<dprev.iloc[ix] else 0)
        vol=(f.high.iloc[i-14:i]-f.low.iloc[i-14:i]).mean()/b.close*100
        regime=("up" if trend==1 else "down" if trend==-1 else "range")+("_highvol" if vol>=2.5 else "_lowvol")
        for direction in (1,-1):
            if trend!=direction or weekly_trend!=direction:continue
            if direction==1:
                pats={"false_break_reclaim":prev.low<lo.iloc[i-1] and prev.close>lo.iloc[i-1] and b.close>prev.high,
                      "breakout_hold":prev.close>hi.iloc[i-1] and b.low>=hi.iloc[i-1] and b.close>hi.iloc[i-1],
                      "trend_pullback":trend==1 and prev.close<prev.open and b.close>prev.high}
            else:
                pats={"false_break_reclaim":prev.high>hi.iloc[i-1] and prev.close<hi.iloc[i-1] and b.close<prev.low,
                      "breakout_hold":prev.close<lo.iloc[i-1] and b.high<=lo.iloc[i-1] and b.close<lo.iloc[i-1],
                      "trend_pullback":trend==-1 and prev.close>prev.open and b.close<prev.low}
            for name,valid in pats.items():
                if not valid:continue
                for days in (3,7):
                    future=h[(h.index>=t)&(h.index<t+pd.Timedelta(days=days))]
                    if len(future)!=days*24:continue
                    for target in (2,3,5):
                        for risk in (1.5,2):
                            tp=b.close*(1+direction*target/100);sl=b.close*(1-direction*risk/100)
                            outcome="none"
                            for _,c in future.iterrows():
                                hit=c.high>=tp if direction==1 else c.low<=tp
                                stop=c.low<=sl if direction==1 else c.high>=sl
                                if hit or stop:
                                    outcome="ambiguous" if hit and stop else ("win" if hit else "loss")
                                    break
                            events.append(dict(symbol=symbol,signal_close_utc=t.isoformat(),direction="LONG" if direction==1 else "SHORT",pattern=name,regime=regime,weekly_trend=weekly_trend,daily_trend=trend,horizon_days=days,target_pct=target,risk_pct=risk,outcome=outcome))
e=pd.DataFrame(events)
if len(e):
    e["signal_close_utc"]=pd.to_datetime(e.signal_close_utc,utc=True)
    cutoff=e.signal_close_utc.min()+.7*(e.signal_close_utc.max()-e.signal_close_utc.min())
    e["split"]=np.where(e.signal_close_utc<cutoff,"discovery","holdout")
    e.to_csv(out/"events.csv",index=False)
    clean=e[e.outcome!="ambiguous"].copy();clean["win"]=clean.outcome=="win"
    clean.groupby(["split","pattern","direction","regime","horizon_days","target_pct","risk_pct"]).agg(n=("win","size"),wins=("win","sum"),win_rate=("win","mean")).reset_index().to_csv(out/"summary_DESCRIPTIVE_ONLY.csv",index=False)
(out/"manifest.json").write_text(json.dumps(dict(status="SHADOW_RESEARCH_ONLY",days_requested=a.days,quality=quality,event_rows=len(e),limitations=["Weekly bars anchored to UTC epoch, only complete 168-hour bars","No fees/slippage/latency","Correlated assets and overlapping events","Same-hour first touch ambiguous","No OI confirmation","Selection requires forward independent validation","Daily regime uses only completed daily bars"]),indent=2))
if not len(e):raise SystemExit("NO_EVENTS_OR_DATA")
