"""Offline checksum/CRC/schema verification and interval-aware funding diagnostics."""
import argparse,base64,csv,hashlib,io,json,zipfile
from pathlib import Path
import pandas as pd
from collect_primary_spot import EVENTS
R=Path(__file__).resolve().parent
a=argparse.ArgumentParser();a.add_argument('--data-dir',type=Path,default=R/'funding');args=a.parse_args()
D=args.data_dir;O=R/'results';O.mkdir(exist_ok=True)
m=json.loads((D/'manifest.json').read_text());allrows=[];checks=[]
cutoff=pd.Timestamp(m['retrieved_at'])
for r in m['records']:
 if not r['status'].startswith('COLLECTED'):continue
 e=json.loads((D/r['normalized_file'].replace('.normalized.json','.evidence.json')).read_text())
 raw=base64.b64decode(e['zip_base64']);h=hashlib.sha256(raw).hexdigest()
 assert h==r['sha256']==e['zip_sha256']==e['checksum_text'].split()[0]
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  assert z.testzip() is None
  members=[n for n in z.namelist() if n.endswith('.csv')];assert len(members)==1
  text=z.read(members[0]).decode('utf-8-sig');assert text==e['csv']
 source=list(csv.DictReader(io.StringIO(text)));norm=json.loads((D/r['normalized_file']).read_text());assert len(source)==len(norm)
 for s,n in zip(source,norm):
  assert int(s['calc_time'])==n['settlement_ms'] and float(s['funding_interval_hours'])==n['period_hours'] and float(s['last_funding_rate'])==n['realized_rate_decimal']
  end=pd.Timestamp(n['settlement_utc']);start=end-pd.Timedelta(hours=n['period_hours'])
  assert end<=cutoff,'FUTURE_SETTLEMENT'
  allrows.append(dict(symbol=r['symbol'],start=start,end=end,hours=n['period_hours'],rate=n['realized_rate_decimal'],source_sha256=h))
 checks.append(dict(symbol=r['symbol'],month=r['month'],rows=len(norm),zip_checksum_verified=True,csv_recomputed=True))
df=pd.DataFrame(allrows).sort_values(['symbol','end']);assert not df.duplicated(['symbol','end']).any()
out=[];detail=[]
for eid,anchor in EVENTS:
 t=pd.Timestamp(anchor)
 for sym in ['BTCUSDT','ETHUSDT']:
  z=df[df.symbol==sym]
  for _,q in z[(z.end>t-pd.Timedelta(hours=72))&(z.start<t+pd.Timedelta(hours=72))].iterrows():
   detail.append(dict(event=eid,symbol=sym,interval_start_utc=str(q.start),settlement_utc=str(q.end),period_hours=q.hours,rate_percent=q.rate*100,linear_percent_per_hour=q.rate*100/q.hours,straddles_anchor=bool(q.start<t<q.end)))
  for h in [4,24,72]:
   for side,lo,hi in [('pre',t-pd.Timedelta(hours=h),t),('post',t,t+pd.Timedelta(hours=h))]:
    q=z[(z.start>=lo)&(z.end<=hi)];hours=float(q.hours.sum());rates=float(q.rate.sum()*100)
    out.append(dict(event=eid,symbol=sym,side=side,window_hours=h,full_intervals=len(q),covered_interval_hours=hours,window_coverage_fraction=hours/h,sum_realized_percent=rates if len(q) else None,linear_percent_per_hour=rates/hours if hours else None,prorated=False,status='WHOLE_INTERVALS_ONLY' if len(q) else 'NO_FULL_INTERVAL_NOT_ZERO'))
pd.DataFrame(out).to_csv(O/'primary_funding_windows.csv',index=False);pd.DataFrame(detail).to_csv(O/'primary_funding_intervals.csv',index=False)
(O/'primary_funding_validation.json').write_text(json.dumps(dict(archives=checks,total_rows=len(df),missing=[r for r in m['records'] if not r['status'].startswith('COLLECTED')],original_historical_availability=None),indent=2))
print(pd.DataFrame(out).query("side=='post' and window_hours==24").to_string(index=False));print('verified_archives',len(checks),'settlements',len(df))
