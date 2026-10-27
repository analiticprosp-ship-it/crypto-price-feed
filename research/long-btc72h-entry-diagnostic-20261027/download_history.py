"""Download pinned closed market-data-only klines, cache each response and receipt."""
import concurrent.futures, datetime as dt, hashlib, json, pathlib, time, urllib.parse, urllib.request
ROOT=pathlib.Path(__file__).parent/'history';ROOT.mkdir(exist_ok=True)
START=1502928000000;END=1793102400000
INTERVALS=[('BTCUSDT','1h',3600000),('BTCUSDT','4h',14400000),('ETHUSDT','4h',14400000),('BTCUSDT','1d',86400000),('ETHUSDT','1d',86400000)]
def get(task):
    symbol,interval,step,start=task;p=ROOT/f'{symbol}_{interval}_{start}.json'
    if p.exists():return json.loads(p.read_text())
    url='https://data-api.binance.vision/api/v3/klines?'+urllib.parse.urlencode(dict(symbol=symbol,interval=interval,startTime=start,endTime=min(start+1000*step,END)-1,limit=1000))
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url,timeout=35) as response:b=response.read();rows=json.loads(b)
            assert isinstance(rows,list) and rows
            rows=[r for r in rows if int(r[6])<END]
            assert all(start<=r[0]<min(start+1000*step,END) for r in rows)
            rec=dict(source=url,retrieved_utc=dt.datetime.now(dt.timezone.utc).isoformat(),sha256_response=hashlib.sha256(b).hexdigest(),rows=rows)
            p.write_text(json.dumps(rec,separators=(',',':')));return rec
        except Exception:
            if attempt==3:raise
            time.sleep(1+attempt)
tasks=[(s,i,step,t) for s,i,step in INTERVALS for t in range(START,END,1000*step)]
completed=0
with concurrent.futures.ThreadPoolExecutor(6) as pool:
    for result in pool.map(get,tasks):
        completed+=1
        if completed%20==0:print(f'downloaded {completed}/{len(tasks)}',flush=True)
summary=[]
for symbol,interval,step in INTERVALS:
    receipts=[json.loads(p.read_text()) for p in sorted(ROOT.glob(f'{symbol}_{interval}_*.json'))]
    rows=sorted([r for receipt in receipts for r in receipt['rows']],key=lambda r:r[0])
    assert len({r[0] for r in rows})==len(rows)
    gaps=[dict(after=a[0],before=b[0],missing=(b[0]-a[0])//step-1) for a,b in zip(rows,rows[1:]) if b[0]-a[0]!=step]
    obj=dict(source='https://data-api.binance.vision',symbol=symbol,interval=interval,cutoff_utc='2026-10-27T12:00:00Z',rows=rows,gaps=gaps,receipts=[{k:v for k,v in x.items() if k!='rows'} for x in receipts])
    (ROOT/f'{symbol}_{interval}.json').write_text(json.dumps(obj,separators=(',',':')))
    summary.append(dict(symbol=symbol,interval=interval,count=len(rows),first=rows[0][0],last=rows[-1][0],gap_count=len(gaps),gaps=gaps[:10]))
(ROOT/'coverage.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
