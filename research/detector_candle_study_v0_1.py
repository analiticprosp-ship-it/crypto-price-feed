#!/usr/bin/env python3
"""Detector Candle Continuation Study v0.1. Research only; no trade authority."""
import argparse, json, time, math
from pathlib import Path
import requests
import numpy as np
import pandas as pd

API="https://www.okx.com/api/v5/market/history-candles"
TFS={"5m":"5min","15m":"15min","30m":"30min","1H":"1h","4H":"4h"}
HORIZONS=[1,4,12,24,72]
DEFAULT_SYMBOLS=["BTC","ETH","SOL","XRP","HYPE","LINK","LDO","SUI","AAVE"]

def fetch(symbol,days,pause):
    inst=f"{symbol}-USDT-SWAP"
    cutoff=int((pd.Timestamp.now(tz="UTC")-pd.Timedelta(days=days)).timestamp()*1000)
    after=None; rows={}; errors=[]; session=requests.Session()
    max_pages=math.ceil(days*288/100)+5
    for _ in range(max_pages):
        params={"instId":inst,"bar":"5m","limit":"100"}
        if after is not None:params["after"]=str(after)
        try:
            resp=session.get(API,params=params,timeout=25)
            resp.raise_for_status(); data=resp.json()
            if data.get("code")!="0":raise ValueError(str(data)[:300])
            batch=data.get("data",[])
            if not batch:break
            for bar in batch:
                stamp=int(bar[0])
                if stamp>=cutoff and str(bar[8])=="1":
                    rows[stamp]=tuple(float(v) for v in bar[1:6])
            oldest=min(int(b[0]) for b in batch)
            if oldest<=cutoff or (after is not None and oldest>=after):break
            after=oldest
            time.sleep(pause)
        except Exception as exc:
            errors.append(str(exc)[:400]);break
    df=pd.DataFrame([(k,*v) for k,v in rows.items()],columns=["ms","open","high","low","close","volume"])
    gaps=None
    if not df.empty:
        df["time"]=pd.to_datetime(df.ms,unit="ms",utc=True)
        df=df.drop_duplicates("time").set_index("time").sort_index().drop(columns="ms")
        expected=pd.date_range(df.index.min(),df.index.max(),freq="5min",tz="UTC")
        gaps=len(expected.difference(df.index))
    return df,{"symbol":symbol,"instrument":inst,"bars":len(df),"gaps":gaps,"errors":errors}

def aggregate(df,rule):
    if df.empty:return df
    x=df.resample(rule,origin="epoch",label="left",closed="left").agg(
        {"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
    n=df.close.resample(rule,origin="epoch",label="left",closed="left").count()
    return x[n==int(pd.Timedelta(rule)/pd.Timedelta(minutes=5))].dropna()

def evaluate(symbol,df):
    events=[]
    for tf,rule in TFS.items():
        x=aggregate(df,rule)
        if len(x)<20:continue
        span=(x.high-x.low).replace(0,np.nan)
        loc=(x.close-x.low)/span
        hi=x.high.shift(1).rolling(12).max()
        lo=x.low.shift(1).rolling(12).min()
        patterns={"top20_LONG":loc>=.8,"bottom20_SHORT":loc<=.2,
                  "break12_LONG":x.close>hi,"break12_SHORT":x.close<lo,
                  "reject_high_SHORT":(x.high>hi)&(x.close<hi),
                  "reclaim_low_LONG":(x.low<lo)&(x.close>lo)}
        for horizon in HORIZONS:
            steps=int(np.ceil(pd.Timedelta(hours=horizon)/pd.Timedelta(rule)))
            future=x.close.shift(-steps)
            actual_time=pd.Series(x.index,index=x.index).shift(-steps)
            continuous=(actual_time-pd.Series(x.index,index=x.index))==pd.Timedelta(rule)*steps
            change=(future/x.close-1)*100
            for name,mask in patterns.items():
                direction=1 if name.endswith("LONG") else -1
                valid=mask.fillna(False)&continuous&change.notna()
                for t in x.index[valid]:
                    signed=float(direction*change.loc[t])
                    events.append({"symbol":symbol,"signal_bar_open_utc":t.isoformat(),
                        "tf":tf,"pattern":name,"direction":"LONG" if direction==1 else "SHORT",
                        "horizon_h":horizon,"signed_return_pct":signed,"positive":signed>0})
    return events

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--days",type=int,default=10)
    parser.add_argument("--symbols",nargs="+",default=DEFAULT_SYMBOLS)
    parser.add_argument("--pause",type=float,default=.2)
    parser.add_argument("--out",default="detector_study_results")
    a=parser.parse_args()
    output=Path(a.out);output.mkdir(parents=True,exist_ok=True)
    quality=[];events=[]
    for symbol in a.symbols:
        df,q=fetch(symbol,a.days,a.pause);quality.append(q)
        if not df.empty:
            df.to_csv(output/f"{symbol}_5m.csv")
            events.extend(evaluate(symbol,df))
        print(symbol,q,flush=True)
    frame=pd.DataFrame(events)
    if not frame.empty:
        frame.to_csv(output/"events.csv",index=False)
        summary=frame.groupby(["tf","pattern","horizon_h"]).agg(
            n=("positive","size"),positive=("positive","sum"),
            hit_rate=("positive","mean"),mean_signed_return_pct=("signed_return_pct","mean"),
            median_signed_return_pct=("signed_return_pct","median")).reset_index()
        summary["independent_sample_verified"]=False
        summary["trade_edge_validated"]=False
        summary.to_csv(output/"summary_DESCRIPTIVE_ONLY.csv",index=False)
    report={"status":"RESEARCH_ONLY","not_trade_approval":True,
        "generated_utc":pd.Timestamp.now(tz="UTC").isoformat(),
        "source":API,"days_requested":a.days,"quality":quality,"event_rows":len(events),
        "limitations":["Descriptive only; no OOS","Overlapping outcomes and correlated assets",
          "No fees, slippage, latency, MFE or MAE","OHLCV only; no aligned OI/taker confirmation",
          "Bar close is not actual detector discovery time",
          "No proof of historical point-in-time data availability"]}
    (output/"manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    if not events:raise SystemExit("NO_EVENTS_OR_DATA: inspect manifest.json")
if __name__=="__main__":main()
