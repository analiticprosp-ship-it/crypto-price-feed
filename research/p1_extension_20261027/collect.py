"""Historical extension only. Read pinned parents; no cloud writes, no forecasts."""
import os,json,hashlib,datetime as dt,bisect,urllib.request,urllib.parse,time,math
from pathlib import Path
import boto3
OUT=Path('p1-extension-data');OUT.mkdir(exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
s=boto3.client('s3',endpoint_url='https://'+os.environ['R2_ACCOUNT_ID']+'.r2.cloudflarestorage.com',aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],region_name='auto')
def parent(key,h,name):
 b=s.get_object(Bucket=os.environ['R2_BUCKET'],Key=key)['Body'].read();assert sha(b)==h
 (OUT/name).write_bytes(b);return json.loads(b)
f=parent('research/btci/v8.10.1/runs/39141047403-1/macro_study.json','230f5c2eebdba583dbadf4a44d50123fb85f93c39b318f5d4fcbb7cb7480fb81','fed.json')
w=parent('research/btci/v8.6/runs/39130315439-1/extended_history.json','9af82767fa8139685e784c131c075cec553298c4718ed4a40ac41412144248ca','btc.json')
p=parent('research/btci/v8.17.1/runs/39212878778-1/full_historical_rise_fall.json','539bcc1817a2120287497c2814d0344aae5d62714b4f35a36f30c2425e5d3091','macro_parent.json')
existing={r['date']:r for r in p['weeklyPanel']};records=[]
for row in w['weeklyRows']:
 day=row['date']
 if day<'2012-06-03' or day in existing:continue
 for symbol in ['NFCI','ANFCI']:
  args={'series_id':symbol,'api_key':os.environ['FRED_API_KEY'],'file_type':'json','realtime_start':day,'realtime_end':day,'observation_start':(dt.date.fromisoformat(day)-dt.timedelta(weeks=16)).isoformat(),'observation_end':day,'limit':1000}
  url='https://api.stlouisfed.org/fred/series/observations?'+urllib.parse.urlencode(args)
  status='UNAVAILABLE';raw=None
  for retry in range(3):
   try:
    raw=urllib.request.urlopen(url,timeout=30).read();x=json.loads(raw)
    assert x['realtime_start']==x['realtime_end']==day
    vals=[]
    for v in x['observations']:
     if v['value']=='.':continue
     assert v['date']<=day and v['realtime_start']<=day<=v['realtime_end']
     n=float(v['value']);assert math.isfinite(n);vals.append((v['date'],n))
    vals.sort();assert len(vals)>=5 and len(set(z[0] for z in vals))==len(vals)
    age=(dt.date.fromisoformat(day)-dt.date.fromisoformat(vals[-1][0])).days
    span=(dt.date.fromisoformat(vals[-1][0])-dt.date.fromisoformat(vals[-5][0])).days
    assert 6<=age<=18 and 27<=span<=35
    status='AVAILABLE_ASOF_DATE';break
   except Exception as e:
    status='UNAVAILABLE_'+type(e).__name__;time.sleep(retry+1)
  entry={'date':day,'series':symbol,'status':status}
  if status=='AVAILABLE_ASOF_DATE':entry.update(value=vals[-1][1],fourWeekDelta=round(vals[-1][1]-vals[-5][1],6),latestObs=vals[-1][0],rawSha256=sha(raw));(OUT/(symbol+'_'+day+'.json')).write_bytes(raw)
  records.append(entry);time.sleep(1.05)
 print('HISTORY_FETCH',day,records[-2]['status'],records[-1]['status'],flush=True)
(OUT/'new_vintages.json').write_text(json.dumps(records,indent=2))
receipt={'status':'HISTORY_COLLECTION_FINISHED','new_series_dates':len(records),'unavailable':sum(z['status']!='AVAILABLE_ASOF_DATE' for z in records),'run_id':os.environ['GITHUB_RUN_ID'],'no_cloud_writes':True,'no_model_changes':True,'files':{p.name:sha(p.read_bytes()) for p in OUT.iterdir() if p.is_file()}}
(OUT/'receipt.json').write_text(json.dumps(receipt,indent=2));print('P1_HISTORY_RESULT '+json.dumps(receipt,sort_keys=True))
