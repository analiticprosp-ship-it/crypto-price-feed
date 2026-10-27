#!/usr/bin/env python3
"""Read-only Binance Spot 1H collector; no forecasts or trading actions."""
import datetime as dt
import hashlib
import json
import pathlib
import urllib.parse
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parent
DEST=ROOT/"data"/"btc_spot_1h.json"
HOST="https://data-api.binance.vision"
HOUR=3600000

def fetch(start,end):
    out=[]
    while start<=end:
        args=urllib.parse.urlencode({"symbol":"BTCUSDT","interval":"1h","startTime":start,"endTime":end+HOUR-1,"limit":1000})
        req=urllib.request.Request(HOST+"/api/v3/klines?"+args,headers={"User-Agent":"BTC72H-shadow-research/1.0"})
        with urllib.request.urlopen(req,timeout=25) as response:
            rows=json.load(response)
        if not rows: raise RuntimeError("EMPTY_WINDOW")
        for r in rows:
            t=int(r[0])
            if t<start or t>end: raise RuntimeError("OUT_OF_RANGE")
            if int(r[6])!=t+HOUR-1 or t%HOUR: raise RuntimeError("INVALID_UTC_CANDLE")
            o,h,l,c,v=map(float,(r[1],r[2],r[3],r[4],r[5]))
            if not (h>=max(o,c,l) and l<=min(o,c,h) and v>=0): raise RuntimeError("INVALID_OHLCV")
            out.append([t,str(r[1]),str(r[2]),str(r[3]),str(r[4]),str(r[5]),int(r[6])])
        start=int(rows[-1][0])+HOUR
    return out

def main():
    now=dt.datetime.now(dt.timezone.utc)
    last=(int(now.timestamp()*1000)//HOUR-1)*HOUR
    if DEST.exists():
        old=json.loads(DEST.read_text())
        assert old["source"]==HOST and old["symbol"]=="BTCUSDT"
        rows=old["candles"]
        start=rows[-1][0]+HOUR
    else:
        rows=[]
        start=last-999*HOUR
    if start<=last: rows+=fetch(start,last)
    if not rows: raise RuntimeError("NO_DATA")
    if rows[-1][0]!=last: raise RuntimeError("STALE_DATA")
    if any(rows[i][0]-rows[i-1][0]!=HOUR for i in range(1,len(rows))): raise RuntimeError("GAP")
    raw=json.dumps(rows,ensure_ascii=False,separators=(",",":")).encode()
    result={"source":HOST,"symbol":"BTCUSDT","interval":"1h","checked_at_utc":now.isoformat(),"first_open_utc":dt.datetime.fromtimestamp(rows[0][0]/1000,dt.timezone.utc).isoformat(),"last_open_utc":dt.datetime.fromtimestamp(rows[-1][0]/1000,dt.timezone.utc).isoformat(),"count":len(rows),"sha256_candles":hashlib.sha256(raw).hexdigest(),"candles":rows}
    DEST.parent.mkdir(parents=True,exist_ok=True)
    DEST.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="candles"},indent=2))
if __name__=="__main__": main()
