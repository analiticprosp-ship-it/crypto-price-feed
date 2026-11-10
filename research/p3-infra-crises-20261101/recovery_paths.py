"""Extend pre-existing P3 recovery diagnostic; offline, no trading actions."""
from pathlib import Path
import argparse,json
import pandas as pd
P=argparse.ArgumentParser();P.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);A=P.parse_args();R=A.root;O=Path(__file__).resolve().parent/'results';O.mkdir(exist_ok=True)
events=json.loads((R/'events.json').read_text());daily={a:pd.read_csv(R/f'raw/cm_{a}.csv').set_index('time')['PriceUSD'] for a in ['btc','eth']}
controls=pd.read_csv(R/'results/daily_control_candidates.csv');recover=pd.read_csv(R/'results/recovery.csv')
def point(a,t):
 try:v=float(daily[a].loc[t.strftime('%Y-%m-%d')]);return v if pd.notna(v) else None
 except KeyError:return None
def calc(a,d,h):
 b=point(a,d-pd.Timedelta(days=1));seq=[point(a,d+pd.Timedelta(days=i)) for i in range(h)]
 if b is None or any(x is None for x in seq):return None
 peak=b;dd=0
 for v in seq:peak=max(v,peak);dd=min(dd,100*(v/peak-1))
 return {'return_pct':100*(seq[-1]/b-1),'min_close_vs_base_pct':100*(min(seq)/b-1),'max_close_vs_base_pct':100*(max(seq)/b-1),'peak_to_trough_close_pct':dd}
rows=[];ref=[];follow=[]
for e in events:
 eid=e['parent_event_id'];d=pd.Timestamp(e['event_date'])
 for a in ['btc','eth']:
  for h in [7,30,90,180]:
   z=calc(a,d,h);rows.append({'event':eid,'asset':a,'calendar_days':h,**(z or {}),'status':'CALCULATED_REVISED_EOD_NOT_EVENT_HOURS' if z else 'SOURCE_NOT_COVERED'})
  q=recover[(recover.event==eid)&(recover.asset==a)].iloc[0];n=q['confirmation_days_from_baseline']
  if pd.notna(n):
   # confirmation close is EOD(d+n-1); first future day is d+n, no retrospective fill on run start.
   nd=d+pd.Timedelta(days=int(n));z=calc(a,nd,30)
   follow.append({'event':eid,'asset':a,'confirmation_close_utc':str(nd.tz_localize('UTC')),'days_to_confirmation':int(n),**(z or {}),'status':'POST_CONFIRMATION_DESCRIPTIVE' if z else 'CENSORED'})
for _,c in controls.iterrows():
 for h in [7,30,90,180]:
  z=calc(c.asset,pd.Timestamp(c.date),h)
  if z:ref.append({'event':c.event,'asset':c.asset,'control_date':c.date,'calendar_days':h,**z})
pd.DataFrame(rows).to_csv(O/'historical_path_risk.csv',index=False);pd.DataFrame(ref).to_csv(O/'historical_control_paths.csv',index=False);pd.DataFrame(follow).to_csv(O/'post_7close_confirmation.csv',index=False)
comp=[];rf=pd.DataFrame(ref)
for r in rows:
 if r['status'].startswith('SOURCE'):continue
 s=rf[(rf.event==r['event'])&(rf.asset==r['asset'])&(rf.calendar_days==r['calendar_days'])]
 comp.append({**r,'candidate_control_n':len(s),'candidate_median_return_pct':float(s.return_pct.median()) if len(s) else None,'candidate_median_min_close_pct':float(s.min_close_vs_base_pct.median()) if len(s) else None,'not_causal':True})
pd.DataFrame(comp).to_csv(O/'historical_reference_comparison.csv',index=False)
print(pd.DataFrame(rows).query('calendar_days==30').to_string(index=False));print(pd.DataFrame(follow).to_string(index=False))
