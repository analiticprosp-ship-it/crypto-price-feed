"""P3 continuation: pinned existing GitHub evidence, no production writes."""
from pathlib import Path
import json,hashlib,datetime as dt
import pandas as pd,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parent;D=R/'raw';O=R/'results';O.mkdir(exist_ok=True)
T=pd.Timestamp('2026-10-29T20:05:00Z')
L=json.loads((R/'evidence/latest.json').read_text())
G=json.loads((R/'evidence/github_audit.json').read_text())
def pct(v,b):return 100*(v/b-1)
def dump(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False))
integrity=[]
for s in L['sources']:
 p=D/s.get('raw_file','NOT_ACQUIRED')
 if p.is_file():
  good=hashlib.sha256(p.read_bytes()).hexdigest()==s['sha256'];integrity.append({'key':s['key'],'sha256_match':good});assert good,s['key']
dump('raw_hash_validation.json',integrity)
prices=[];ois=[];fund=[];coverage=[];norms={}
for a in ['BTC','ETH']:
 j=json.loads((D/f'{a}_4H.raw').read_text())
 d=pd.DataFrame(j['data'],columns=['ts','open','high','low','close','vol_contracts','vol_coin','vol_quote','confirm'])
 d['start']=pd.to_datetime(d.ts.astype('int64'),unit='ms',utc=True);d['end']=d.start+pd.Timedelta(hours=4)
 d=d[d.confirm=='1'].sort_values('end');d['close']=d.close.astype(float)
 assert not d.end.duplicated().any();assert (d.end.diff().dropna()==pd.Timedelta(hours=4)).all()
 def point(t):
  v=d[d.end<=t]
  if len(v)==0:return None
  z=v.iloc[-1]
  return z if (t-z.end).total_seconds()<14400 else None
 b=point(T)
 for h in [-72,-24,-4,0,4,24,72]:
  t=T+pd.Timedelta(hours=h);z=point(t)
  prices.append({'asset':a,'market':'OKX_USDT_PERPETUAL','horizon_hours':h,'requested_utc':str(t),'actual_close_utc':str(z.end) if z is not None else None,'lag_minutes':(t-z.end).total_seconds()/60 if z is not None else None,'close_usdt':float(z.close) if z is not None else None,'return_pct':pct(b.close,z.close) if h<0 and z is not None else pct(z.close,b.close) if z is not None else None,'status':'CLOSED_4H_GRID_NOT_SPOT' if z is not None else 'SOURCE_NOT_COVERED_OR_HORIZON_PENDING'})
 pd.DataFrame([{'asset':a,'close_utc':str(z.end),'close_usdt':float(z.close),'return_vs_baseline_pct':pct(z.close,b.close)} for _,z in d.iterrows() if T-pd.Timedelta(hours=72)<=z.end<=T+pd.Timedelta(hours=72)]).to_csv(O/f'{a}_perp_path.csv',index=False)
 j=json.loads((D/f'{a}_oi.raw').read_text());q=pd.DataFrame(j['data'],columns=['ts','contracts','coins','usd']);q[['contracts','coins','usd']]=q[['contracts','coins','usd']].astype(float)
 q['provider_time']=pd.to_datetime(q.ts.astype('int64'),unit='ms',utc=True);q=q.sort_values('provider_time')
 # Conservative collector policy: treat period timestamp as bucket start. Official docs verify units, not bucket-edge semantics.
 q['conservative_usable_at']=q.provider_time+pd.Timedelta(hours=1)
 assert not q.provider_time.duplicated().any();assert (q.provider_time.diff().dropna()==pd.Timedelta(hours=1)).all()
 ratio=q.coins/q.contracts;assert np.allclose(ratio,ratio.iloc[0],rtol=1e-7);norms[a]={'coins_per_contract_observed':float(ratio.iloc[0]),'status':'UNIT_COLUMNS_VERIFIED_OFFICIAL_DOCS_BUCKET_EDGE_NOT_INDEPENDENTLY_ATTESTED'}
 def oi(t):
  v=q[q.conservative_usable_at<=t]
  if len(v)==0:return None
  z=v.iloc[-1];return z if (t-z.conservative_usable_at).total_seconds()<3600 else None
 ob=oi(T)
 for h in [-72,-24,-4,0,4,24,72]:
  t=T+pd.Timedelta(hours=h);z=oi(t)
  ois.append({'asset':a,'horizon_hours':h,'requested_utc':str(t),'provider_timestamp':str(z.provider_time) if z is not None else None,'conservative_usable_at':str(z.conservative_usable_at) if z is not None else None,'contracts':float(z.contracts) if z is not None else None,'coins':float(z.coins) if z is not None else None,'usd_notional':float(z.usd) if z is not None else None,'contracts_change_vs_anchor_pct':pct(z.contracts,ob.contracts) if z is not None else None,'notional_change_vs_anchor_pct':pct(z.usd,ob.usd) if z is not None else None,'status':'HISTORICAL_CONSERVATIVE_BUCKET_POLICY_NOT_LONG_SHORT' if z is not None else 'NOT_COVERED'})
 j=json.loads((D/f'{a}_funding.raw').read_text());f=pd.DataFrame(j['data']);f['end']=pd.to_datetime(f.fundingTime.astype('int64'),unit='ms',utc=True);f=f.sort_values('end');f['start']=f.end.shift(1);f['period_hours']=(f.end-f.start).dt.total_seconds()/3600
 assert (f.period_hours.dropna()==8).all()
 for _,z in f.iterrows():
  if T-pd.Timedelta(hours=80)<=z.end<=T+pd.Timedelta(hours=72) and pd.notna(z.period_hours):
   rate=float(z.realizedRate)
   fund.append({'asset':a,'period_start_utc':str(z.start),'period_end_utc':str(z.end),'period_hours':float(z.period_hours),'realized_percent_per_period':rate*100,'linear_percent_per_hour':rate*100/z.period_hours,'crosses_incident':bool(z.start<T<z.end),'fully_post_incident':bool(z.start>=T),'fully_pre_incident':bool(z.end<=T),'not_annualized':True})
 coverage.append({'asset':a,'closed_perp_bars':len(d),'perp_start':str(d.start.min()),'perp_end':str(d.end.max()),'oi_rows':len(q),'oi_start':str(q.provider_time.min()),'oi_end':str(q.provider_time.max()),'funding_rows':len(f),'funding_period_hours':[8],'first_available_historical_utc':None})
pd.DataFrame(prices).to_csv(O/'binance_event_perp_response.csv',index=False)
pd.DataFrame(ois).to_csv(O/'binance_event_OI.csv',index=False)
pd.DataFrame(fund).to_csv(O/'funding_normalized.csv',index=False);dump('coverage.json',coverage);dump('oi_units.json',norms)
# Existing BTC72H SPOT archive is read-only. It stops before +24H, do not repair or change frozen module.
s=json.loads((R/'evidence/btc_spot_1h.json').read_text());a=pd.DataFrame(s['candles'],columns=['open_ms','open','high','low','close','volume','close_ms']);a['end']=pd.to_datetime(a.close_ms,unit='ms',utc=True)+pd.Timedelta(milliseconds=1);a['close']=a.close.astype(float);a=a.sort_values('end');assert not a.end.duplicated().any()
def spot(t):
 v=a[a.end<=t]
 if len(v)==0:return None
 z=v.iloc[-1];return z if (t-z.end).total_seconds()<3600 else None
b=spot(T);sr=[]
for h in [-72,-24,-4,0,4,24,72]:
 z=spot(T+pd.Timedelta(hours=h));sr.append({'asset':'BTC','market':'BINANCE_BTCUSDT_SPOT','horizon_hours':h,'actual_close_utc':str(z.end) if z is not None else None,'close_usdt':float(z.close) if z is not None else None,'return_pct':pct(b.close,z.close) if h<0 and z is not None else pct(z.close,b.close) if z is not None else None,'status':'EXISTING_ARCHIVED_SPOT_GRID' if z is not None else 'COMMITTED_ARCHIVE_NOT_COVERED'})
pd.DataFrame(sr).to_csv(O/'binance_event_BTC_spot.csv',index=False)
# Sparse books: never rename top25 native as ±1% or combine swap contract units with spot coin units.
br=[];bad=[];samples=[]
for p in sorted((R/'books').glob('*.json')):
 j=json.loads(p.read_text());samples.append(pd.Timestamp(j['capture_begin_utc']))
 for s in j['snapshots']:
  if s['status']!='SOURCE_SNAPSHOT_VALID':bad.append({'file':p.name,'venue':s['venue'],'market':s['instrument_kind'],'status':s['status']});continue
  calc=(s['ask1_price']-s['bid1_price'])/s['mid_price']*10000;assert abs(calc-s['spread_bps'])<.00001
  br.append({'file':p.name,'captured_at':s['captured_at_utc'],'venue':s['venue'],'market':s['instrument_kind'],'mid':s['mid_price'],'spread_bps':s['spread_bps'],'top25_bid_native':s['bid_depth_top25_native'],'top25_ask_native':s['ask_depth_top25_native'],'top25_total_native':s['bid_depth_top25_native']+s['ask_depth_top25_native'],'hours_from_incident':(pd.Timestamp(s['captured_at_utc'])-T).total_seconds()/3600,'not_depth_1pct':True})
books=pd.DataFrame(br);books.to_csv(O/'sparse_books.csv',index=False);pd.DataFrame(bad).to_csv(O/'books_access_gaps.csv',index=False)
groups=[]
for m in ['spot','swap']:
 for name,lo,hi in [('pre24h',-24,0),('post24h',0,24),('post24to72h',24,72)]:
  z=books[(books.market==m)&books.hours_from_incident.between(lo,hi,inclusive='left')]
  groups.append({'market':m,'window':name,'samples':len(z),'median_spread_bps':float(z.spread_bps.median()) if len(z) else None,'median_top25_native':float(z.top25_total_native.median()) if len(z) else None,'not_1pct_depth':True})
pd.DataFrame(groups).to_csv(O/'sparse_books_summary.csv',index=False)
dump('book_cadence.json',{'samples':len(samples),'valid_records':len(br),'access_gap_records':len(bad),'median_capture_gap_hours':float(pd.Series(samples).sort_values().diff().dt.total_seconds().dropna().median()/3600),'max_capture_gap_hours':float(pd.Series(samples).sort_values().diff().dt.total_seconds().dropna().max()/3600),'intended_schedule':'hourly at17','actual':'sparse, no fill, no 6 consecutive hourly normalization test'})
# Independent daily market context. Yahoo timestamps denote session start, not when close was available.
equity=[]
for p in sorted(D.glob('YAHOO_*.raw')):
 j=json.loads(p.read_text())['chart']['result'][0];sym=j['meta']['symbol'];cl=j['indicators']['quote'][0]['close'];rows=[]
 for ts,v in zip(j['timestamp'],cl):
  if v is not None:rows.append({'date':pd.Timestamp(ts,unit='s',tz='UTC').tz_convert('America/New_York').strftime('%Y-%m-%d'),'close':float(v)})
 z=pd.DataFrame(rows).set_index('date').sort_index()
 for da in ['2026-10-28','2026-10-29','2026-10-30']:
  prev=z.loc[:da].iloc[:-1]
  if da in z.index and len(prev):equity.append({'symbol':sym,'date':da,'close':float(z.loc[da,'close']),'prior_session_close':float(prev.iloc[-1]['close']),'session_return_pct':pct(z.loc[da,'close'],prev.iloc[-1]['close']),'quality':'YAHOO_VENDOR_DAILY_REVISED_NOT_INTRADAY_NOT_PIT'})
pd.DataFrame(equity).to_csv(O/'macro_market_sessions.csv',index=False)
macro=[]
for p in sorted(D.glob('FRED_*.raw')):
 d=pd.read_csv(p);series=d.columns[1];d[series]=pd.to_numeric(d[series],errors='coerce')
 for _,z in d[d.iloc[:,0].astype(str)>='2026-10-20'].iterrows():
  macro.append({'series':series,'observation_date':z.iloc[0],'value':float(z.iloc[1]) if pd.notna(z.iloc[1]) else None,'publication_time_utc':None,'quality':'REVISED_HISTORY_NOT_KNOWN_AT_EVENT'})
pd.DataFrame(macro).to_csv(O/'macro_latest_observations.csv',index=False)
flows=[]
def number(x):
 s=str(x).strip().replace(',','')
 if s in ['-','—','nan','']:return None
 try:return -float(s[1:-1]) if s.startswith('(') and s.endswith(')') else float(s)
 except ValueError:return None
for a in ['BTC','ETH']:
 tab=pd.read_html(str(D/f'ETF_{a}.raw'))[0]
 for _,z in tab.iterrows():
  try:da=pd.to_datetime(str(z.iloc[0]),format='%d %b %Y').strftime('%Y-%m-%d')
  except ValueError:continue
  vals=[number(x) for x in z.iloc[1:-1]];total=number(z.iloc[-1]);complete=all(v is not None for v in vals) and total is not None
  diff=sum(vals)-total if complete else None
  if complete:assert abs(diff)<.15,(a,da,diff)
  flows.append({'asset':a,'session_date':da,'total_million_usd':total,'component_sum_difference':diff,'complete':complete,'publication_time_utc':None,'source':'Farside publisher table archived in GitHub; not issuer-by-issuer independent replay','quality':'LATEST_REVISED_NOT_PIT_NOT_INTRADAY_FLOW'})
pd.DataFrame(flows).to_csv(O/'etf_flows_recomputed.csv',index=False)
summary={'status':'P3_CONTINUATION_CALCULATED_NOT_HYPOTHESES_VALIDATED','pinned_main_sha':G['main_sha'],'pinned_books_sha':G['books_sha'],'indicator_receipt':L['run_id'],'statuses':pd.Series([s['status'] for s in L['sources']]).value_counts().to_dict(),'raw_files_sha_matched':len(integrity),'new_data':['BTC spot pre/post4H','BTC_ETH perpetual price4H24H','BTC_ETH OI contracts_coins_notional','realized funding8H','sparse BTC books','daily macro market sessions','ETF component sums'],'not_closed':['5-crisis synchronized L1L2 panel','depth1pct','continuous liquidations','original publication vintages','causal macro decomposition','H2 sustained recovery','H3 source-to-destination capital transfer'],'trade_changes':False,'btc72h_frozen_changes':False,'P1_receiver_acceptance':'NOT_AUTOMATICALLY_GRANTED','72h_event_outcome':'PENDING_AT_DATA_CUTOFF'}
dump('summary.json',summary)
fig,axs=plt.subplots(2,2,figsize=(12,8))
for a,c in [('BTC','#d38b16'),('ETH','#596db5')]:
 d=pd.read_csv(O/f'{a}_perp_path.csv');times=pd.to_datetime(d.close_utc,utc=True);hrs=(times-T).dt.total_seconds()/3600
 axs[0,0].plot(hrs,d.return_vs_baseline_pct,label=a,color=c)
 q=pd.DataFrame(ois);z=q[(q.asset==a)&(q.horizon_hours>=0)];axs[0,1].plot(z.horizon_hours,z.contracts_change_vs_anchor_pct,label=a,color=c,marker='o')
for m,c in [('spot','#26866e'),('swap','#9b5d9d')]:
 z=books[books.market==m].sort_values('hours_from_incident');axs[1,0].scatter(z.hours_from_incident,z.spread_bps,label=m,color=c,s=18)
eq=pd.DataFrame(equity);z=eq[(eq.date=='2026-10-30')&eq.symbol.isin(['SPY','QQQ','SOXX','IWM','RSP'])];axs[1,1].bar(z.symbol,z.session_return_pct,color='#5b729c')
for ax in axs.flat:ax.axhline(0,color='gray',lw=.5);ax.grid(alpha=.15)
axs[0,0].set(title='OKX perpetual prices / closed 4H grid',ylabel='Return vs pre-event grid (%)',xlabel='Hours from incident');axs[0,0].legend()
axs[0,1].set(title='OKX OI contracts / conservative bucket policy',ylabel='Change vs anchor (%)',xlabel='Hours from incident');axs[0,1].legend()
axs[1,0].set(title='Sparse OKX BTC quoted spreads / no continuity',ylabel='Basis points',xlabel='Actual hours from incident');axs[1,0].legend()
axs[1,1].set(title='30 Oct US session / vendor daily closes',ylabel='Close-to-close return (%)')
fig.tight_layout();fig.savefig(O/'P3_continuation.png',dpi=150);plt.close(fig)
print(pd.DataFrame(prices).to_string(index=False));print(pd.DataFrame(ois)[['asset','horizon_hours','contracts_change_vs_anchor_pct','notional_change_vs_anchor_pct']].to_string(index=False));print(pd.DataFrame(groups).to_string(index=False));print(pd.DataFrame(equity).query("date=='2026-10-30'")[['symbol','session_return_pct']].to_string(index=False));print(json.dumps(summary,indent=2))
