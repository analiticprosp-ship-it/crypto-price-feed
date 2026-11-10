"""Recalculate registered P3 phases with primary Binance SPOT, quote USDT."""
from pathlib import Path
import hashlib,json,argparse
import pandas as pd,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parent
a=argparse.ArgumentParser();a.add_argument('--data-dir',type=Path,default=R/'primary');a.add_argument('--previous-root',type=Path,default=R.parent);args=a.parse_args()
D=args.data_dir;O=R/'results';O.mkdir(exist_ok=True)
m=json.loads((D/'manifest.json').read_text());verified=[]
for r in m['raw_records']:
 p=D/r['file'];raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=r['sha256'] and hashlib.sha256(raw[:-1]).hexdigest()==r['sha256']:p.write_bytes(raw[:-1]);raw=raw[:-1]
 assert hashlib.sha256(raw).hexdigest()==r['sha256'],r['file']
 verified.append({'file':r['file'],'sha256':r['sha256'],'match':True})
rows=[];paths=[];hourly=[]
for e in m['events']:
 assert not e['errors'];points=e['minute_points'];base=next(p['close'] for p in points if p['horizon_hours']==0);anchor=pd.Timestamp(e['anchor_utc'])
 for p in points:
  h=p['horizon_hours'];close=p.get('close');value=100*(base/close-1) if h<0 and close is not None else 100*(close/base-1) if close is not None else None
  if close is not None:assert p['actual_close_utc']==p['target_utc']
  rows.append({'event':e['parent_event_id'],'symbol':e['symbol'],'horizon_hours':h,'target_utc':p['target_utc'],'actual_close_utc':p.get('actual_close_utc'),'close_usdt':close,'return_pct':value,'status':p['status'],'source':'BINANCE_SPOT_PRIMARY_API','historical_first_available':None})
 if e['hourly_file']:
  d=json.loads((D/e['hourly_file']).read_text());assert all(int(d[i][0])-int(d[i-1][0])==3600000 for i in range(1,len(d)))
  for r in d:
   end=pd.Timestamp(int(r[6])+1,unit='ms',tz='UTC');close=float(r[4]);paths.append({'event':e['parent_event_id'],'symbol':e['symbol'],'close_utc':str(end),'hours_from_anchor':(end-anchor).total_seconds()/3600,'close_usdt':close,'return_vs_exact_minute_anchor_pct':100*(close/base-1)})
  hourly.append({'event':e['parent_event_id'],'symbol':e['symbol'],'rows':len(d),'first_open_utc':str(pd.Timestamp(int(d[0][0]),unit='ms',tz='UTC')),'last_close_utc':str(pd.Timestamp(int(d[-1][6])+1,unit='ms',tz='UTC'))})
df=pd.DataFrame(rows);df.to_csv(O/'primary_spot_response.csv',index=False);pd.DataFrame(paths).to_csv(O/'primary_spot_hourly_paths.csv',index=False);pd.DataFrame(hourly).to_csv(O/'primary_spot_coverage.csv',index=False)
(O/'primary_raw_validation.json').write_text(json.dumps(verified,indent=2))
# ETH/BTC ratio return separately; it is not an observed transfer of investor capital.
rat=[]
for eid in df.event.unique():
 z=df[df.event==eid];bp=z[(z.symbol=='BTCUSDT')&(z.horizon_hours==0)].iloc[0].close_usdt;ep=z[(z.symbol=='ETHUSDT')&(z.horizon_hours==0)].iloc[0].close_usdt
 for h in [4,24,72]:
  b=z[(z.symbol=='BTCUSDT')&(z.horizon_hours==h)].iloc[0].close_usdt;e=z[(z.symbol=='ETHUSDT')&(z.horizon_hours==h)].iloc[0].close_usdt
  rat.append({'event':eid,'horizon_hours':h,'ETH_BTC_ratio_return_pct':100*((e/b)/(ep/bp)-1) if pd.notna(b) and pd.notna(e) else None,'not_capital_flow':True})
pd.DataFrame(rat).to_csv(O/'ETH_BTC_relative_response.csv',index=False)
# Isolate endpoint resolution from venue/quote differences where prior mirror panels exist.
oldpath=args.previous_root/'results/hourly_comparison.csv'
old=pd.read_csv(oldpath) if oldpath.exists() else pd.DataFrame(columns=['event','asset','phase','horizon_hours','return_pct']);compare=[]
for _,r in df.iterrows():
 z=old[(old.event==r.event)&(old.asset==r.symbol[:3].lower())&(old.phase=='registered_anchor')&(old.horizon_hours==r.horizon_hours)]
 if len(z) and pd.notna(r.return_pct) and pd.notna(z.iloc[0].return_pct):compare.append({'event':r.event,'symbol':r.symbol,'horizon_hours':r.horizon_hours,'primary_minute_USDT_return_pct':r.return_pct,'old_mirror_hour_grid_USD_return_pct':z.iloc[0].return_pct,'difference_pp':r.return_pct-z.iloc[0].return_pct,'cause':'CONFOUNDED_VENUE_QUOTE_AND_RESOLUTION_NOT_PROVEN_SOURCE_ERROR'})
pd.DataFrame(compare).to_csv(O/'primary_vs_previous_panel.csv',index=False)
fig,axs=plt.subplots(5,1,figsize=(10,14))
ph=pd.DataFrame(paths)
for ax,eid in zip(axs,df.event.unique()):
 for sym,c in [('BTCUSDT','#c88818'),('ETHUSDT','#6964b8')]:
  z=ph[(ph.event==eid)&(ph.symbol==sym)];ax.plot(z.hours_from_anchor,z.return_vs_exact_minute_anchor_pct,label=sym,color=c,lw=1.5)
  p=df[(df.event==eid)&(df.symbol==sym)&df.horizon_hours.isin([0,4,24,72])].dropna(subset=['return_pct']);ax.scatter(p.horizon_hours,p.return_pct,color=c,s=22)
 ax.set_title(eid);ax.axhline(0,color='gray',lw=.6);ax.axvline(0,color='gray',ls=':');ax.set_ylabel('Return (%) in USDT');ax.grid(alpha=.15);ax.legend();ax.set_xticks([-72,-24,0,4,24,72])
axs[-1].set_xlabel('Hours relative to registered phase; markers = exact closed-minute endpoints')
fig.suptitle('P3 primary SPOT: Binance BTCUSDT / ETHUSDT, historical revised API\nNot USD, not original publication vintages, no causal attribution',fontsize=12)
fig.tight_layout(rect=[0,0,1,.96]);fig.savefig(O/'primary_spot_reactions.png',dpi=150);plt.close(fig)
summary={'run_id':m['run_id'],'raw_pages_verified':len(verified),'primary_minute_points':int(df.close_usdt.notna().sum()),'pending':int(df.close_usdt.isna().sum()),'hourly_rows':sum(x['rows'] for x in hourly),'independent_parent_episodes':5,'source':'BINANCE_SPOT_PRIMARY_API','quote':'USDT_NOT_USD','original_historical_availability':None,'status':'PRICE_COLLECTION_EXECUTED_NOT_FULL_H1_H2_H3_VALIDATION','trades_changed':False,'frozen_models_changed':False}
(O/'primary_summary.json').write_text(json.dumps(summary,indent=2))
print(df[df.horizon_hours.isin([4,24,72])].to_string(index=False));print(json.dumps(summary,indent=2))
