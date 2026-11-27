#!/usr/bin/env python3
"""Isolated P3 public SPOT history collection. Never reads/writes BTC72H state."""
import datetime as dt,hashlib,json,math,os,time,urllib.parse,urllib.request
from pathlib import Path
# Recollection registered 2026-11-02 after +72H maturity; retain original anchors.
HOST='https://data-api.binance.vision';H=3600000;M=60000
EVENTS=[('BINANCE_SECURITY_20261029','2026-10-29T20:05:00+00:00'),('BYBIT_20250221','2025-02-21T14:13:00+00:00'),('FTX_NOV2022','2022-11-02T14:44:00+00:00'),('TERRA_UST_202205','2022-05-07T21:44:00+00:00'),('USDC_SVB_202303','2023-03-10T16:15:00+00:00')]
HORIZONS=[-72,-24,-4,0,4,24,72]
ROOT=Path(__file__).resolve().parent
def iso(ms):return dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc).isoformat()
def sha(b):return hashlib.sha256(b).hexdigest()
def validate(rows,interval):
 for r in rows:
  assert int(r[0])%interval==0 and int(r[6])==int(r[0])+interval-1,'CANDLE_TIME'
  o,h,l,c,v=map(float,r[1:6]);assert all(map(math.isfinite,[o,h,l,c,v])) and h>=max(o,c,l) and l<=min(o,c,h) and v>=0,'OHLCV'
 assert len({int(r[0]) for r in rows})==len(rows),'DUPLICATES'
 assert all(int(rows[i][0])-int(rows[i-1][0])==interval for i in range(1,len(rows))),'GAP'
def selftest():
 validate([[0,'1','2','0.5','1.2','2',M-1]],M)
 for bad in [[[0,'1','0.9','0.5','1.2','2',M-1]],[[0,'1','2','0.5','1.2','2',M-2]]]:
  try:validate(bad,M)
  except AssertionError:pass
  else:raise AssertionError('INVALID_ACCEPTED')
 return True
def get(symbol,interval,start,end,out,key,records):
 step=H if interval=='1h' else M;rows=[];cursor=start;page=0
 while cursor<=end:
  params={'symbol':symbol,'interval':interval,'startTime':cursor,'endTime':end+step-1,'limit':1000}
  url=HOST+'/api/v3/klines?'+urllib.parse.urlencode(params)
  before=dt.datetime.now(dt.timezone.utc).isoformat();raw=None
  for attempt in range(3):
   try:
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'P3-infrastructure-shadow/1.0'}),timeout=25) as r:raw=r.read()
    break
   except Exception:
    if attempt==2:raise
    time.sleep(1+attempt)
  after=dt.datetime.now(dt.timezone.utc).isoformat();data=json.loads(raw)
  assert isinstance(data,list) and data,'EMPTY_OR_ERROR_RESPONSE';validate(data,step)
  assert int(data[0][0])==cursor and int(data[-1][0])<=end,'UNEXPECTED_RANGE'
  assert all(int(x[6])<int(dt.datetime.now(dt.timezone.utc).timestamp()*1000) for x in data),'UNCLOSED'
  name=f'{key}_{page}.raw.json';(out/name).write_bytes(raw)
  records.append({'file':name,'url':url,'sha256':sha(raw),'request_started_at':before,'retrieved_at':after,'first_available_historically':None,'source':'BINANCE_SPOT_PRIMARY_API_REVISED_HISTORY','rows':len(data)})
  rows.extend(data);cursor=int(data[-1][0])+step;page+=1
  time.sleep(.15)
 validate(rows,step);assert len(rows)==(end-start)//step+1,'INCOMPLETE_WINDOW'
 return rows
def main():
 selftest();now=dt.datetime.now(dt.timezone.utc);nowms=int(now.timestamp()*1000)
 run=now.strftime('%Y%m%dT%H%M%SZ')+'_'+os.environ.get('GITHUB_RUN_ID','local')
 out=ROOT/'spot_runs'/run;out.mkdir(parents=True,exist_ok=False)
 manifest={'run_id':run,'created_at':now.isoformat(),'mode':'SHADOW_RESEARCH_ONLY','market':'SPOT','host':HOST,'code_commit':os.environ.get('GITHUB_SHA'),'events':[],'raw_records':[],'no_trade_changes':True,'btc72h_unchanged':True,'historical_pit':False}
 for eid,t in EVENTS:
  anchor=int(dt.datetime.fromisoformat(t).timestamp()*1000)
  for symbol in ['BTCUSDT','ETHUSDT']:
   item={'parent_event_id':eid,'symbol':symbol,'anchor_utc':t,'anchor_role':'TECHNICAL_OR_REGISTERED_PHASE_NOT_ALWAYS_FIRST_PUBLIC_NEWS','minute_points':[],'hourly_file':None,'errors':[]}
   try:
    start=(anchor-72*H)//H*H;end=min((anchor+72*H)//H*H- H,(nowms//H-1)*H)
    rows=get(symbol,'1h',start,end,out,eid+'_'+symbol+'_1h',manifest['raw_records'])
    n=eid+'_'+symbol+'_1h.json';(out/n).write_text(json.dumps(rows,separators=(',',':')));item['hourly_file']=n
   except Exception as e:item['errors'].append({'part':'hourly','type':type(e).__name__,'error':str(e)[:250]})
   for h in HORIZONS:
    target=anchor+h*H
    if target>nowms:item['minute_points'].append({'horizon_hours':h,'target_utc':iso(target),'status':'HORIZON_PENDING'});continue
    try:
     # Exact minute-grid close immediately before target; preserve legacy phase precision.
     start=target//M*M-M;rows=get(symbol,'1m',start,start,out,eid+'_'+symbol+'_m'+str(h).replace('-','neg'),manifest['raw_records']);r=rows[0]
     item['minute_points'].append({'horizon_hours':h,'target_utc':iso(target),'actual_close_utc':iso(int(r[6])+1),'close':float(r[4]),'status':'PRIMARY_SPOT_CLOSED_MINUTE_GRID','quote':'USDT','first_available_historically':None})
    except Exception as e:item['minute_points'].append({'horizon_hours':h,'target_utc':iso(target),'status':'FAILED_NOT_ZERO','error_type':type(e).__name__,'error':str(e)[:200]})
   manifest['events'].append(item)
   print(json.dumps({'event':eid,'symbol':symbol,'hourly':item['hourly_file'] is not None,'minute_ok':sum(x['status']=='PRIMARY_SPOT_CLOSED_MINUTE_GRID' for x in item['minute_points']),'errors':len(item['errors'])}),flush=True)
 manifest['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat();manifest['status']='COLLECTED_WITH_EXPLICIT_COVERAGE';(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({'run':run,'raw_pages':len(manifest['raw_records']),'manifest':str(out/'manifest.json')}))
if __name__=='__main__':main()
