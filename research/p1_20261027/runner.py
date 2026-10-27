#!/usr/bin/env python3
"""P1 operational forward v1: original BTCI v8.16 signals, NO TRADES.
All cloud writes confined to research/p1/v1/, immutable conditional puts.
Official-source bytes are archived; delayed runs never backdate forecasts.
"""
import datetime as dt,hashlib,importlib.util,json,math,os,re,sys,urllib.parse,urllib.request
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
PREFIX='research/p1/v1/'
P86=('research/btci/v8.6/runs/39130315439-1/extended_history.json','9af82767fa8139685e784c131c075cec553298c4718ed4a40ac41412144248ca')
P89=('research/btci/v8.9/runs/39138844921-1/multiscale.json','4b8822e929aff5569fa9cd105404c02b110927a970aed33db68910925c111b73')
EXP='STRUCTURAL_EXPANSION_PRICE_PROXY';CON='STRUCTURAL_CONTRACTION_PRICE_PROXY';MID='TRANSITION_OR_REBOUND_PRICE_PROXY'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def date(s):return dt.date.fromisoformat(s)
def rawjson(obj):return (json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def utcnow():return dt.datetime.now(dt.timezone.utc)
def geturl(url,maxbytes=2500000):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'P1 prospective research v1','Accept':'application/json,text/html,text/plain'}),timeout=30) as r:raw=r.read(maxbytes+1)
 if len(raw)>maxbytes:raise ValueError('SOURCE_TOO_LARGE')
 return raw
def last_sunday(now):
 day=now.date();ans=day-dt.timedelta(days=(day.weekday()+1)%7)
 if day==ans:ans-=dt.timedelta(days=7)
 return ans
def eligible_window(now,sunday,first):
 decision=dt.datetime.combine(sunday+dt.timedelta(days=1),dt.time(10),dt.timezone.utc)
 return sunday>=first and decision<=now<=decision+dt.timedelta(hours=4)
def trend(values):
 if len(values)<34:raise ValueError('LESS_THAN_34_WEEKS')
 q=list(reversed(values[-34:]));ma=sum(q[:30])/30;old=sum(q[4:34])/30
 rising=max(q[:4])>max(q[4:8]) and min(q[:4])>min(q[4:8])
 return {'up':q[0]>ma and ma>old and rising,'ma30':ma,'ma30_previous4':old,'close_structure_rising':rising}
def structural(rows):
 out=[];prev=None;streak=0;confirmed=None
 v=[r['btcFixingPriceUSD'] for r in rows]
 for i,r in enumerate(rows):
  if i<64:continue
  ma=sum(v[i-51:i+1])/52;old=sum(v[i-64:i-12])/52;r26=v[i]/v[i-26]-1
  raw=EXP if v[i]>ma and ma>old and r26>0 else CON if v[i]<ma and ma<old and r26<0 else MID
  streak=streak+1 if prev==raw else 1;prev=raw
  if streak>=4 and confirmed!=raw:confirmed=raw
  out.append({'date':r['date'],'raw':raw,'confirmed':confirmed,'rawConsecutiveWeeks':streak})
 return out
def acceptance(parent,context):
 rows=parent['weeklyRows'];assert len(rows)==814 and len({r['date'] for r in rows})==814
 assert all((date(b['date'])-date(a['date'])).days==7 for a,b in zip(rows,rows[1:]))
 values=[r['btcFixingPriceUSD'] for r in rows];n=0
 for i in range(33,len(rows)):
  got=trend(values[:i+1]);assert got['up']==rows[i]['weeklyTrendConfirmed'];assert abs(got['ma30']-rows[i]['sma30w'])<2e-6;n+=1
 computed=structural(rows);old=context['pastOnlyWeeklyContext'];assert len(computed)==len(old)==750
 for a,b in zip(computed,old):assert all(a[k]==b[k] for k in ('date','raw','confirmed','rawConsecutiveWeeks'))
 return {'BTC_fast_flags_verified':n,'structural_states_verified':len(old),'status':'EXACT_FLAG_PARITY_PASS','rounding_tolerance_ma_usd':2e-6}
def cloud():
 import boto3
 return boto3.client('s3',endpoint_url='https://'+os.environ['R2_ACCOUNT_ID']+'.r2.cloudflarestorage.com',aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],region_name='auto')
def getparent(s,b,key,digest):
 raw=s.get_object(Bucket=b,Key=key)['Body'].read()
 if sha(raw)!=digest:raise ValueError('PARENT_HASH_MISMATCH')
 return json.loads(raw)
def existing(s,b,key):
 if not key.startswith(PREFIX):raise ValueError('OUT_OF_SCOPE_READ')
 try:
  raw=s.get_object(Bucket=b,Key=key)['Body'].read();return raw
 except Exception as e:
  code=getattr(e,'response',{}).get('Error',{}).get('Code')
  if code in ('NoSuchKey','404','NotFound'):return None
  raise
def immutable(s,b,key,raw,kind='application/json'):
 if not key.startswith(PREFIX):raise ValueError('OUT_OF_SCOPE_WRITE')
 prev=existing(s,b,key)
 if prev is not None:
  if prev!=raw:raise ValueError('IMMUTABLE_RECORD_CONFLICT')
  return {'key':key,'sha256':sha(raw),'status':'EXISTING_IDENTICAL_VERIFIED'}
 try:s.put_object(Bucket=b,Key=key,Body=raw,ContentType=kind,IfNoneMatch='*',Metadata={'sha256':sha(raw),'research-only':'true'})
 except Exception as e:
  if getattr(e,'response',{}).get('Error',{}).get('Code') not in ('PreconditionFailed','412','ConditionalRequestConflict'):raise
 if existing(s,b,key)!=raw:raise ValueError('IMMUTABLE_READBACK_FAILED')
 return {'key':key,'sha256':sha(raw),'status':'CREATED_READBACK_VERIFIED'}
def listkeys(s,b,prefix):
 if not prefix.startswith(PREFIX):raise ValueError('OUT_OF_SCOPE_LIST')
 token=None
 while True:
  args={'Bucket':b,'Prefix':prefix}
  if token:args['ContinuationToken']=token
  out=s.list_objects_v2(**args)
  for item in out.get('Contents',[]):yield item['Key']
  if not out.get('IsTruncated'):break
  token=out['NextContinuationToken']
def import_pinned(rel,expected):
 path=REPO/rel
 if sha(path.read_bytes())!=expected:raise ValueError('DEPENDENCY_CODE_HASH_MISMATCH')
 spec=importlib.util.spec_from_file_location('p1_'+path.stem,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def prices(sunday,start):
 params={'assets':'btc','metrics':'PriceUSD','frequency':'1d','start_time':start.isoformat(),'end_time':sunday.isoformat(),'page_size':10000}
 url='https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?'+urllib.parse.urlencode(params)
 raw=geturl(url);obj=json.loads(raw)
 if obj.get('next_page_url'):raise ValueError('PRICE_PAGINATION_NOT_COMPLETE')
 result={}
 for item in obj.get('data',[]):
  d=date(item['time'][:10]);v=float(item['PriceUSD'])
  if d> sunday or not math.isfinite(v) or v<=0 or d in result:raise ValueError('PRICE_BAD_OR_FUTURE')
  result[d]=v
 if any(start+dt.timedelta(days=i) not in result for i in range((sunday-start).days+1)):raise ValueError('PRICE_DAILY_GAP')
 return result,raw,url
def fed_features(sunday,parser,archive):
 url='https://alfred.stlouisfed.org/release/downloaddates?ff=txt&rid=20';raw=geturl(url)
 archive('H41_release_calendar.txt',raw,url,'text/plain')
 dates=sorted({date(x) for x in re.findall(r'(?<!\d)((?:19|20)\d{2}-[01]\d-[0-3]\d)(?!\d)',raw.decode('utf-8','replace')) if date(x)<=sunday})
 last=dates[-5:]
 if len(last)!=5 or (sunday-last[-1]).days>10 or any(not 1<=(b-a).days<=10 for a,b in zip(last,last[1:])):raise ValueError('H41_RELEASE_WINDOW_GAP')
 rows=[]
 for d in last:
  u='https://www.federalreserve.gov/releases/h41/'+d.strftime('%Y%m%d')+'/'
  body=geturl(u);row=parser.parse(body,d.isoformat());archive('H41_'+d.isoformat()+'.html',body,u,'text/html');rows.append(row)
 delta=rows[-1]['simplifiedFedMinusTGAMinusRRP_MillionUSD']-rows[0]['simplifiedFedMinusTGAMinusRRP_MillionUSD']
 return {'up':delta>0,'delta4_million_usd':delta,'releases':rows,'source_limitation':'Dated release pages captured now may include corrections; exact original intraday publication bytes not independently proven.'}
def append_new_sundays(parentrows,daily,asof):
 rows=[{'date':r['date'],'btcFixingPriceUSD':r['btcFixingPriceUSD']} for r in parentrows]
 last=date(rows[-1]['date']);day=last+dt.timedelta(days=7)
 while day<=asof:
  if day not in daily:raise ValueError('NEW_WEEKLY_PRICE_GAP')
  rows.append({'date':day.isoformat(),'btcFixingPriceUSD':daily[day]});day+=dt.timedelta(days=7)
 return rows
def evaluate_record(record,daily):
 asof=date(record['asof_sunday']);end=asof+dt.timedelta(weeks=13)
 needed=[asof+dt.timedelta(days=i) for i in range(1,92)]
 if any(d not in daily for d in needed):return None
 rows=record['structural_weekly_prefix'][:];day=asof+dt.timedelta(days=7)
 while day<=end:rows.append({'date':day.isoformat(),'btcFixingPriceUSD':daily[day]});day+=dt.timedelta(days=7)
 states=[z for z in structural(rows) if asof<date(z['date'])<=end]
 if len(states)!=13:raise ValueError('OUTCOME_NOT_13_FULL_WEEKS')
 start=record['features']['BTC']['reference_close_usd'];ret=100*(daily[end]/start-1);worst=100*(min(daily[d] for d in needed)/start-1)
 return {'return13w_pct':ret,'positive13w':ret>0,'worst_daily_close_pct':worst,'adverse20_daily_close':worst<=-20,'confirmed_expansion_any_next13w':any(z['confirmed']==EXP for z in states),'initial_structural_state':record['structural_state_at_asof'],'future_week_count':13,'target_caveat':'Price-defined structural label, not independent true bull market; terminal return and path risk separate.'}
def main():
 now=utcnow();registration_raw=(HERE/'registration.json').read_bytes();reg=json.loads(registration_raw)
 if sha(Path(__file__).read_bytes())!=reg['runner_sha256']:raise ValueError('RUNNER_HASH_MISMATCH')
 specpath=REPO/reg['parent_protocol_path']
 if sha(specpath.read_bytes())!=reg['parent_protocol_sha256']:raise ValueError('FROZEN_V816_CHANGED')
 if reg['mode']!='RESEARCH_ONLY_NO_TRADES' or reg['first_sunday']!='2026-11-01':raise ValueError('REGISTRATION_INVALID')
 parser=import_pinned(reg['dependencies']['h41']['path'],reg['dependencies']['h41']['sha256'])
 fred=import_pinned(reg['dependencies']['fred']['path'],reg['dependencies']['fred']['sha256'])
 s=cloud();bucket=os.environ['R2_BUCKET'];parent=getparent(s,bucket,*P86);context=getparent(s,bucket,*P89)
 parity=acceptance(parent,context)
 register=immutable(s,bucket,PREFIX+'registrations/operational_v1.json',registration_raw)
 # Strict conditional-write test uses only this research namespace.
 test=rawjson({'kind':'IMMUTABILITY_ACCEPTANCE','registration_sha256':sha(registration_raw)})
 testkey=PREFIX+'acceptance/immutable_v1.json';immutable(s,bucket,testkey,test);again=immutable(s,bucket,testkey,test)
 try:immutable(s,bucket,testkey,b'changed')
 except ValueError as e:
  if str(e)!='IMMUTABLE_RECORD_CONFLICT':raise
 else:raise ValueError('OVERWRITE_WAS_NOT_REJECTED')
 run=PREFIX+'runs/'+os.getenv('GITHUB_RUN_ID','local')+'-'+os.getenv('GITHUB_RUN_ATTEMPT','1')+'/'+now.strftime('%Y%m%dT%H%M%S%fZ')+'/'
 audit={'kind':'P1_FORWARD_RUN','observed_at_utc':now.isoformat(),'registration_sha256':sha(registration_raw),'parity':parity,'immutable_acceptance':'CREATE_READBACK_IDENTICAL_AND_CONFLICT_REJECTION_PASS','registration_storage':register,'first_sunday':reg['first_sunday'],'new_forecasts':[],'new_outcomes':[],'source_errors':[],'raw_sources':[],'trade_authority':False,'main_changed':False}
 def archive(name,raw,url,kind='application/json'):
  receipt=immutable(s,bucket,run+'sources/'+name,raw,kind);audit['raw_sources'].append({**receipt,'source_url':url,'retrieved_at_utc':utcnow().isoformat()});return receipt
 sunday=last_sunday(now)
 try:
  start=min(date(parent['weeklyRows'][-1]['date'])+dt.timedelta(days=1),sunday-dt.timedelta(days=250))
  daily,raw,url=prices(sunday,start);archive('BTC_PriceUSD.json',raw,url)
  vals=[daily[sunday-dt.timedelta(days=7*i)] for i in range(33,-1,-1)]
  btc=trend(vals);btc['reference_close_usd']=daily[sunday];btc['asof_sunday']=sunday.isoformat()
  h41=fed_features(sunday,parser,archive)
  ff={}
  for symbol in ('NFCI','ANFCI'):
   value,raw=fred.fetch_asof(symbol,sunday.isoformat(),os.environ.get('FRED_API_KEY',''))
   if value.get('status')!='PIT_ASOF_DATE_VERIFIED' or raw is None:raise ValueError('FRED_'+symbol+'_SOURCE_PENDING')
   archive(symbol+'_asof.json',raw,'https://api.stlouisfed.org/fred/series/observations?series_id='+symbol+'&realtime_start='+sunday.isoformat()+'&realtime_end='+sunday.isoformat())
   ff[symbol]=value
  weekly=append_new_sundays(parent['weeklyRows'],daily,sunday);state=structural(weekly)[-1]['confirmed']
  signals={'BTC_WEEKLY_UP':btc['up'],'FED_EASING':h41['up'],'NFCI_EASING':ff['NFCI']['deltaFourWeeks']<0,'ANFCI_EASING':ff['ANFCI']['deltaFourWeeks']<0}
  signals['CHICAGO_FAMILY']=signals['NFCI_EASING'] and signals['ANFCI_EASING'];signals['PRIMARY_EARLY']=signals['FED_EASING'] and signals['CHICAGO_FAMILY'];signals['PRIMARY_CONFIRMATION']=signals['BTC_WEEKLY_UP'] and signals['PRIMARY_EARLY']
  audit['source_validation']='ALL_FOUR_INPUTS_PASS';audit['audit_sunday']=sunday.isoformat();audit['source_check_only_signals']=signals
  if eligible_window(now,sunday,date(reg['first_sunday'])):
   forecastkey=PREFIX+'forecasts/'+sunday.isoformat()+'.json';prior=existing(s,bucket,forecastkey)
   if prior is None:
    record={'kind':'P1_V816_PROSPECTIVE_OBSERVATION','asof_sunday':sunday.isoformat(),'registered_at_utc':utcnow().isoformat(),'decision_clock_utc':dt.datetime.combine(sunday+dt.timedelta(days=1),dt.time(10),dt.timezone.utc).isoformat(),'operational_max_delay_hours':4,'registration_sha256':sha(registration_raw),'mode':'RESEARCH_ONLY_NO_TRADES','signals':signals,'features':{'BTC':btc,'FED':h41,**ff},'structural_state_at_asof':state,'cohort':'NON_EXPANSION_PRIMARY' if state!=EXP else 'ALREADY_EXPANSION_DIAGNOSTIC','structural_weekly_prefix':weekly,'source_receipts':audit['raw_sources'][:],'outcome_status':'PENDING_13_COMPLETE_FUTURE_WEEKS','horizon_end_sunday':(sunday+dt.timedelta(weeks=13)).isoformat(),'trading_applicability':'NOT_ESTABLISHED','limitations':reg['limitations']}
    audit['new_forecasts'].append(immutable(s,bucket,forecastkey,rawjson(record)))
   else:audit['forecast_status']='ALREADY_REGISTERED_UNCHANGED'
  else:audit['forecast_status']='NOT_DUE_BEFORE_FIRST_SUNDAY' if sunday<date(reg['first_sunday']) else 'MISSED_DECISION_WINDOW_NO_BACKFILL'
 except Exception as exc:
  audit['source_validation']='SOURCE_PENDING';audit['source_errors'].append({'type':type(exc).__name__,'reason':str(exc)[:120] if isinstance(exc,ValueError) else 'SOURCE_FETCH_OR_VALIDATION_FAILED','http_status':getattr(exc,'code',None)})
 # Each horizon is evaluated only after all13 future Sundays have closed.
 try:
  for key in listkeys(s,bucket,PREFIX+'forecasts/'):
   saved=existing(s,bucket,key);record=json.loads(saved);asof=date(record['asof_sunday']);end=asof+dt.timedelta(weeks=13)
   if now<dt.datetime.combine(end+dt.timedelta(days=1),dt.time(10),dt.timezone.utc):continue
   outkey=PREFIX+'outcomes/'+asof.isoformat()+'/13w.json'
   if existing(s,bucket,outkey) is not None:continue
   values,raw,url=prices(end,asof);archive('outcome_'+asof.isoformat()+'.json',raw,url)
   result=evaluate_record(record,values)
   if result is None:continue
   outcome={'kind':'P1_IMMUTABLE_13W_OUTCOME','forecast_key':key,'forecast_sha256':sha(saved),'asof_sunday':asof.isoformat(),'horizon_end_sunday':end.isoformat(),'verified_at_utc':utcnow().isoformat(),'source_sha256':sha(raw),'outcomes':result,'no_trading_authority':True}
   audit['new_outcomes'].append(immutable(s,bucket,outkey,rawjson(outcome)))
 except Exception as exc:audit['outcome_error']={'type':type(exc).__name__,'reason':'OUTCOME_SOURCE_PENDING_NO_INVENTED_RESULT'}
 audit['stored_forecasts_n']=sum(1 for _ in listkeys(s,bucket,PREFIX+'forecasts/'))
 audit['stored_outcomes_n']=sum(1 for _ in listkeys(s,bucket,PREFIX+'outcomes/'))
 receipt=immutable(s,bucket,run+'run.json',rawjson(audit))
 out=Path('p1_forward_artifact');out.mkdir(exist_ok=True);(out/'run.json').write_bytes(rawjson(audit));(out/'receipt.json').write_bytes(rawjson(receipt))
 brief={k:audit.get(k) for k in ('observed_at_utc','parity','immutable_acceptance','source_validation','audit_sunday','forecast_status','new_forecasts','new_outcomes','source_errors','stored_forecasts_n','stored_outcomes_n')};brief['run_receipt']=receipt;brief['status']='SOURCE_PENDING' if audit['source_errors'] else 'RUN_WRITE_READBACK_VERIFIED'
 print('P1_FORWARD_RESULT '+json.dumps(brief,ensure_ascii=False),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as exc:
  print('P1_FORWARD_FATAL '+json.dumps({'type':type(exc).__name__,'reason':str(exc)[:160] if isinstance(exc,(ValueError,AssertionError)) else 'FAIL_CLOSED_NO_FORECAST_NO_PRODUCTION_WRITES'}),flush=True);raise SystemExit(1)
