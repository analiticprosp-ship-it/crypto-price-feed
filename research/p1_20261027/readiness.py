#!/usr/bin/env python3
"""Read-only source readiness for original BTCI v8.16. NOT a forecast.
No R2/canonical/portfolio writes. API key sent only to official FRED endpoint.
"""
import datetime as dt,hashlib,json,math,os,re,urllib.parse,urllib.request
from pathlib import Path

OUT=Path('p1_readiness_artifact');OUT.mkdir(exist_ok=True)
NOW=dt.datetime.now(dt.timezone.utc)
day=NOW.date();sunday=day-dt.timedelta(days=(day.weekday()+1)%7)
if day==sunday:sunday-=dt.timedelta(days=7)
ASOF=sunday.isoformat()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def fetch_fred(symbol):
 key=os.environ.get('FRED_API_KEY','')
 if not re.fullmatch(r'[a-z0-9]{32}',key):return {'status':'SOURCE_PENDING','reason':'NAMED_FRED_API_KEY_NOT_CONFIGURED'}
 params={'series_id':symbol,'api_key':key,'file_type':'json','realtime_start':ASOF,'realtime_end':ASOF,'observation_start':(sunday-dt.timedelta(weeks=16)).isoformat(),'observation_end':ASOF,'limit':'1000'}
 url='https://api.stlouisfed.org/fred/series/observations?'+urllib.parse.urlencode(params)
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'P1 source readiness'}),timeout=25) as response:raw=response.read(500001)
  assert len(raw)<=500000
  data=json.loads(raw)
  assert data['realtime_start']==data['realtime_end']==ASOF
  vals=[]
  for z in data.get('observations',[]):
   if z.get('value') in (None,'.',''):continue
   assert z['date']<=ASOF and z['realtime_start']<=ASOF<=z['realtime_end']
   value=float(z['value']);assert math.isfinite(value);vals.append((z['date'],value))
  vals.sort();assert len(vals)>=5 and len({d for d,v in vals})==len(vals)
  last=vals[-1];prior=vals[-5]
  age=(sunday-dt.date.fromisoformat(last[0])).days;gap=(dt.date.fromisoformat(last[0])-dt.date.fromisoformat(prior[0])).days
  assert 6<=age<=18 and 27<=gap<=35
  assert all((dt.date.fromisoformat(b[0])-dt.date.fromisoformat(a[0])).days==7 for a,b in zip(vals[-5:],vals[-4:]))
  (OUT/(symbol+'_asof_raw.json')).write_bytes(raw)
  return {'status':'READINESS_DATE_VINTAGE_VERIFIED','series':symbol,'audit_asof_sunday':ASOF,'last_observation':last[0],'last_value':last[1],'delta4weeks':last[1]-prior[1],'age_days':age,'raw_sha256':sha(raw),'retrieved_at_utc':NOW.isoformat(),'original_intraday_release_time_verified':False,'forecast_registered':False}
 except Exception as exc:
  return {'status':'SOURCE_PENDING','reason':type(exc).__name__,'http_status':getattr(exc,'code',None)}
def public_probe(name,url):
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'P1 read-only readiness'}),timeout=25) as response:raw=response.read(1500001)
  assert len(raw)<=1500000
  if name=='coinmetrics':
   obj=json.loads(raw);assert obj.get('data') and all(z.get('PriceUSD') for z in obj['data'])
  if name=='fed':assert b'H.4.1' in raw or b'Factors Affecting Reserve Balances' in raw
  (OUT/(name+'_probe.raw')).write_bytes(raw)
  return {'status':'HTTP_AND_CONTENT_OK','raw_sha256':sha(raw),'bytes':len(raw),'source_url':url,'forecast_registered':False}
 except Exception as exc:return {'status':'SOURCE_PENDING','reason':type(exc).__name__,'http_status':getattr(exc,'code',None)}
features={s:fetch_fred(s) for s in ('NFCI','ANFCI')}
q=urllib.parse.urlencode({'assets':'btc','metrics':'PriceUSD','frequency':'1d','start_time':(sunday-dt.timedelta(days=250)).isoformat(),'end_time':ASOF,'page_size':1000})
features['coinmetrics']=public_probe('coinmetrics','https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?'+q)
# Prior Thursday is a known dated release candidate, not a reconstructed forecast.
thursday=sunday-dt.timedelta(days=3)
features['fed']=public_probe('fed','https://www.federalreserve.gov/releases/h41/'+thursday.strftime('%Y%m%d')+'/')
result={'id':'P1_V816_READINESS_20261027','kind':'SOURCE_READINESS_AUDIT_NOT_FORECAST','observed_at_utc':NOW.isoformat(),'audit_sunday':ASOF,'first_intended_new_sunday':'2026-11-01','not_backdated':True,'features':features,'sources_reachable':all(v['status'] in ('READINESS_DATE_VINTAGE_VERIFIED','HTTP_AND_CONTENT_OK') for v in features.values()),'remaining':['Exact frozen BTC trend acceptance against v8.6','Full five-release H41 parsing and gap validation','Append-only immutable prospective runner and write/readback acceptance','Weekly activation and first prospective observation after registration'],'forecasts':[],'trade_authority':False,'production_mutations':False}
(OUT/'readiness.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('P1_READINESS_RESULT '+json.dumps(result,ensure_ascii=False))
