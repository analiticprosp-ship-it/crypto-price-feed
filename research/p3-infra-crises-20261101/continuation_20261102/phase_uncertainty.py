from pathlib import Path
import json
import pandas as pd
R=Path(__file__).resolve().parent;O=R/'results';O.mkdir(exist_ok=True)
c=json.loads((R/'phase_uncertainty_contract.json').read_text());rows=[]
for a in ['BTC','ETH']:
 d=pd.read_csv(R.parent/f'raw/mirror_bitstamp_{a}.csv',header=None,names=['unix','date','symbol','open','high','low','close','v1','v2'])
 d['end']=pd.to_datetime(d.unix,unit='s',utc=True)+pd.Timedelta(hours=1);d=d.set_index('end').sort_index();assert not d.index.duplicated().any()
 for t in pd.date_range('2022-11-08',periods=24,freq='h',tz='UTC'):
  b=float(d.loc[t,'close'])
  for h in c['horizons_hours']:
   p=float(d.loc[t+pd.Timedelta(hours=h),'close']);rows.append(dict(event=c['parent_event_id'],asset=a,anchor_utc=str(t),horizon_hours=h,return_pct=100*(p/b-1),quality='SECONDARY_MIRROR_USD_DATE_ONLY_GRID_SENSITIVITY_NOT_EVENT_TIME'))
x=pd.DataFrame(rows);x.to_csv(O/'ftx_date_only_all_anchors.csv',index=False)
s=x.groupby(['asset','horizon_hours']).return_pct.agg(['count','min','median','max']);assert (s['count']==24).all();s.to_csv(O/'ftx_date_only_range.csv');print(s.to_string())
# Vintage overlap comparison: same primary minute endpoints, not the previous venue panel.
old=pd.read_csv(R.parent/'continuation_20261101_spot/results/primary_spot_response.csv');new=pd.read_csv(O/'primary_spot_response.csv')
z=old.merge(new,on=['event','symbol','horizon_hours'],suffixes=('_old','_new'))
z=z[z.close_usdt_old.notna()&z.close_usdt_new.notna()].copy();z['price_delta_usdt']=z.close_usdt_new-z.close_usdt_old;z['return_delta_pp']=z.return_pct_new-z.return_pct_old
z[['event','symbol','horizon_hours','price_delta_usdt','return_delta_pp']].to_csv(O/'primary_vintage_overlap.csv',index=False)
(O/'primary_vintage_overlap_summary.json').write_text(json.dumps(dict(overlapping_points=len(z),changed_prices=int((z.price_delta_usdt!=0).sum()),max_abs_price_delta=float(z.price_delta_usdt.abs().max()),original_PIT=False),indent=2))
