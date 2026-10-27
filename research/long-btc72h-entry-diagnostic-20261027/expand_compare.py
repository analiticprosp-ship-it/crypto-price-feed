"""Frozen expanded diagnostic. Uses cached public data, writes separate outputs only."""
import bisect, csv, datetime as dt, hashlib, json, math, pathlib, statistics
import runner as L
ROOT=pathlib.Path(__file__).parent;H=3600000
INVALID=[]
def read(symbol,interval):return json.loads((ROOT/'history'/f'{symbol}_{interval}.json').read_text())
def bars(rows,step):
    out=[]
    for r in rows:
        t=int(r[0]);end=int(r[6])+1;o,h,l,c,v=map(float,r[1:6])
        if not(t%step==0 and end==t+step and 0<l<=min(o,c)<=max(o,c)<=h):
            INVALID.append(dict(open_ms=t,step_ms=step,source_close_ms=r[6],reason='NONSTANDARD_BAR_TIME_OR_OHLC'));continue
        out.append(dict(t=t,end=end,o=o,h=h,l=l,c=c,v=v))
    return out
def index_indicators(a):
    result={};tr=[];atr=None;weights=[math.exp(-i*i/128) for i in range(500)];ws=math.fsum(weights)
    for i,b in enumerate(a):
        prev=a[i-1]['c'] if i else b['c'];tr.append(max(b['h']-b['l'],abs(b['h']-prev),abs(b['l']-prev)))
        if i==13:atr=statistics.fmean(tr)
        elif i>13:atr=(atr*13+tr[-1])/14
        if i<499:continue
        # Missing 4h bars invalidate the complete indicator history, not zero inputs.
        continuous=all(a[k]['t']-a[k-1]['t']==L.H4 for k in range(i-498,i+1))
        if not continuous:continue
        center=math.fsum(a[i-j]['c']*weights[j] for j in range(500))/ws
        hi=max(x['h'] for x in a[i-20:i]);result[b['end']]=dict(signal=b['c']>hi and b['c']>center,close=b['c'],atr14=atr,structural_anchor=min(x['l'] for x in a[i-4:i+1])-.25*atr)
    return result
def execute():
    assert hashlib.sha256((ROOT/'runner.py').read_bytes()).hexdigest()=='a6721cd5cbe9b2316dde43ba4d9f3dcaf139b2e9a77e1a77b7c7c5e06695bc75'
    design=json.loads((ROOT/'expanded_design.json').read_text())
    hs=read('BTCUSDT','1h');valid_hours={b['t'] for b in bars(hs['rows'],H)};hourly=[r for r in hs['rows'] if r[0] in valid_hours];events=[];gap_windows=0
    for i in range(66,len(hourly)):
        if any(hourly[k][0]-hourly[k-1][0]!=H for k in range(i-65,i+1)):gap_windows+=1;continue
        j=min(range(i-18,i-2),key=lambda k:float(hourly[k][3]));low=float(hourly[j][3]);high=max(float(hourly[k][2]) for k in range(j-48,j));close=float(hourly[i][4])
        if high<=0 or (high-low)/high<.05 or (close-low)/low<.02 or (close-low)/(high-low)>=.8:continue
        if any(float(hourly[k][3])<low for k in range(j+1,i+1)):continue
        if sum(float(hourly[k][4])>float(hourly[k][1]) for k in range(j+1,i+1))<2:continue
        if events and hourly[i][0]-events[-1]['signal_open_ms']<168*H:continue
        cp_rows=hourly[j+1:j+73];complete=len(cp_rows)==72 and all(r[0]==hourly[j][0]+(n+1)*H for n,r in enumerate(cp_rows))
        survivor=min(float(r[3]) for r in cp_rows)>=low if complete else None
        events.append(dict(id='btc72h-'+str(hourly[i][0]),signal_open_ms=hourly[i][0],known_ms=hourly[i][0]+H,low_ms=hourly[j][0],checkpoint_ms=hourly[j][0]+73*H,survivor=survivor,low=low,drop=(high-low)/high))
    cluster=-1;anchor=None
    for e in events:
        if anchor is None or e['low_ms']>=anchor+30*L.DAY:cluster+=1;anchor=e['low_ms']
        e['cluster']=cluster
    market={};phase_cache={};phase_calls=0
    for symbol in L.SYMBOLS:
        a=bars(read(symbol,'4h')['rows'],L.H4);daily=bars(read(symbol,'1d')['rows'],L.DAY)
        market[symbol]=dict(bars=a,bytime={b['t']:b for b in a},daily=daily,indicators=index_indicators(a))
    def phase(symbol,t):
        day=t//L.DAY*L.DAY;key=(symbol,day)
        if key not in phase_cache:
            d=[b for b in market[symbol]['daily'] if b['end']<=day]
            if len(d)<220 or d[-1]['end']!=day or any(b['t']-a['t']!=L.DAY for a,b in zip(d[-220:],d[-219:])):phase_cache[key]=None
            else:phase_cache[key]=L.phase(d,day)
        return phase_cache[key]
    def allowed(symbol,t):
        p=phase(symbol,t);btc=phase('BTCUSDT',t)
        if p is None or btc is None:return None
        return (p['regime']=='UP' or (p['regime']=='TRANSITION' and p['constructive_transition'])) and (symbol=='BTCUSDT' or btc['regime']!='DOWN')
    rows=[];excluded=[]
    for e in events:
        start=math.ceil(e['known_ms']/L.H4)*L.H4;checkpoint=math.ceil(e['checkpoint_ms']/L.H4)*L.H4
        # Common point-in-time cohort, independent of later Survivor or signals.
        if any(start not in market[s]['bytime'] or start not in market[s]['indicators'] or phase(s,start) is None for s in L.SYMBOLS):
            excluded.append(dict(event_id=e['id'],reason='COMMON_WARMUP_OR_DATA'));continue
        year=dt.datetime.fromtimestamp(start/1000,dt.timezone.utc).year;block='2017-2019' if year<2020 else ('2020-2022' if year<2023 else '2023-2026')
        for symbol,data in market.items():
            bt=data['bytime'];a=data['bars'];regime=phase(symbol,start)['regime']
            for days in (7,14):
                end=start+days*L.DAY;mature=end in bt
                for arm in ('EARLY','LONG_CONFIRM','SURVIVOR72'):
                    fill=None;reason='NO_SIGNAL';unknown=False
                    times=[start] if arm=='EARLY' else ([checkpoint] if arm=='SURVIVOR72' else range(start,end,L.H4))
                    if arm=='SURVIVOR72' and e['survivor'] is not True:reason='NOT_SURVIVOR' if e['survivor'] is False else 'CHECKPOINT_UNAVAILABLE';unknown=e['survivor'] is None;times=[]
                    for t in times:
                        if t>=end:reason='LATE';break
                        if t not in bt or allowed(symbol,t) is None:reason='DATA_UNAVAILABLE';unknown=True;break
                        if not allowed(symbol,t):reason='REGIME_REJECTED';continue
                        if arm=='LONG_CONFIRM':
                            info=data['indicators'].get(t)
                            if info is None:reason='INDICATOR_UNAVAILABLE';unknown=True;break
                            if not info['signal']:continue
                            p=bt[t]['o'];stop=min(info['structural_anchor'],p-info['atr14'])
                            if p>info['close']+.5*info['atr14'] or stop<=0 or p-stop>3*info['atr14']:reason='LONG_PRICE_DISTANCE_REJECTED';continue
                        fill=t;reason='FILLED';break
                    result=dict(event_id=e['id'],cluster=e['cluster'],block=block,regime_at_candidate=regime,early_regime_eligible=allowed(symbol,start),symbol=symbol,horizon_days=days,arm=arm,survivor=e['survivor'],signal_known_utc=L.utc(e['known_ms']),checkpoint_utc=L.utc(e['checkpoint_ms']),entry_utc=L.utc(fill) if fill is not None else None,exit_utc=L.utc(end),status=reason,mature=mature,net_return_pct=None,stress_return_pct=None,mae_pct=None,mfe_pct=None)
                    if mature and not unknown:
                        if fill is None:result['net_return_pct']=result['stress_return_pct']=0.
                        else:
                            segment=[bt[t] for t in range(fill,end,L.H4) if t in bt]
                            if len(segment)!=(end-fill)//L.H4:result['status']='OUTCOME_DATA_GAP'
                            else:
                                p=bt[fill]['o'];exitp=bt[end]['o'];result.update(net_return_pct=(exitp*.9985/(p*1.0015)-1)*100,stress_return_pct=(exitp*.997/(p*1.003)-1)*100,mae_pct=(min(b['l'] for b in segment)/p-1)*100,mfe_pct=(max(b['h'] for b in segment)/p-1)*100)
                    rows.append(result)
    summaries=[]
    for symbol in L.SYMBOLS:
        for days in (7,14):
            for arm in ('EARLY','LONG_CONFIRM','SURVIVOR72'):
                for group,value in [('all','all')]+[('block',v) for v in ['2017-2019','2020-2022','2023-2026']]+[('regime_at_candidate',v) for v in ['UP','TRANSITION','RANGE','DOWN']]+[('survivor',v) for v in [True,False]]+[('early_regime_eligible',True)]:
                    subset=[r for r in rows if r['symbol']==symbol and r['horizon_days']==days and r['arm']==arm and (group=='all' or r[group]==value) and r['net_return_pct'] is not None];filled=[r for r in subset if r['status']=='FILLED']
                    clusters={c:statistics.fmean(r['net_return_pct'] for r in subset if r['cluster']==c) for c in set(r['cluster'] for r in subset)}
                    summaries.append(dict(symbol=symbol,days=days,arm=arm,group=group,value=value,events=len(subset),fills=len(filled),clusters=len(clusters),mean_all_pct=statistics.fmean(r['net_return_pct'] for r in subset) if subset else None,mean_filled_pct=statistics.fmean(r['net_return_pct'] for r in filled) if filled else None,cluster_mean_pct=statistics.fmean(clusters.values()) if clusters else None,stress_mean_pct=statistics.fmean(r['stress_return_pct'] for r in subset) if subset else None,mean_mae_pct=statistics.fmean(r['mae_pct'] for r in filled) if filled else None))
    paired=[]
    for symbol in L.SYMBOLS:
        for days in (7,14):
            base={r['event_id']:r for r in rows if r['symbol']==symbol and r['horizon_days']==days and r['arm']=='EARLY' and r['net_return_pct'] is not None}
            for arm in ('LONG_CONFIRM','SURVIVOR72'):
                pairs=[(r['cluster'],r['net_return_pct']-base[r['event_id']]['net_return_pct']) for r in rows if r['symbol']==symbol and r['horizon_days']==days and r['arm']==arm and r['net_return_pct'] is not None and r['event_id'] in base]
                means=[statistics.fmean(v for c,v in pairs if c==cluster) for cluster in sorted(set(c for c,v in pairs))]
                paired.append(dict(symbol=symbol,days=days,arm_minus_early=arm,events=len(pairs),clusters=len(means),paired_mean_pp=statistics.fmean(v for c,v in pairs) if pairs else None,paired_cluster_mean_pp=statistics.fmean(means) if means else None))
    result=dict(status='EXPLORATORY_NOT_OOS',design_sha256=hashlib.sha256((ROOT/'expanded_design.json').read_bytes()).hexdigest(),candidates=len(events),non_survivors=sum(e['survivor'] is False for e in events),survivors=sum(e['survivor'] is True for e in events),checkpoint_unknown=sum(e['survivor'] is None for e in events),clusters=cluster+1,excluded_common_cohort=excluded,invalid_source_rows=INVALID,skipped_hourly_windows_due_to_gap=gap_windows,summary=summaries,paired=paired,events=events)
    (ROOT/'expanded_results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    with (ROOT/'expanded_ledger.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    delay_diagnostic=[]
    for symbol in L.SYMBOLS:
        early={r['event_id']:r for r in rows if r['symbol']==symbol and r['horizon_days']==7 and r['arm']=='EARLY' and r['status']=='FILLED' and r['net_return_pct'] is not None}
        pairs=[(early[r['event_id']],r) for r in rows if r['symbol']==symbol and r['horizon_days']==7 and r['arm']=='SURVIVOR72' and r['status']=='FILLED' and r['net_return_pct'] is not None and r['event_id'] in early]
        premiums=[(market[symbol]['bytime'][L.timestamp(b['entry_utc'])]['o']/market[symbol]['bytime'][L.timestamp(a['entry_utc'])]['o']-1)*100 for a,b in pairs]
        delay_diagnostic.append(dict(symbol=symbol,both_filled=len(pairs),mean_entry_premium_pct=statistics.fmean(premiums),median_entry_premium_pct=statistics.median(premiums),mean_mae_early=statistics.fmean(a['mae_pct'] for a,b in pairs),mean_mae_72=statistics.fmean(b['mae_pct'] for a,b in pairs),status='POSTHOC_MECHANISM_DIAGNOSTIC_NOT_SELECTION_RULE'))
    (ROOT/'entry_delay_diagnostic.json').write_text(json.dumps(delay_diagnostic,indent=2)+'\n')
    sources=[]
    for symbol,interval in [('BTCUSDT','1h'),('BTCUSDT','4h'),('ETHUSDT','4h'),('BTCUSDT','1d'),('ETHUSDT','1d')]:
        obj=read(symbol,interval);sources.append(dict(symbol=symbol,interval=interval,rows=len(obj['rows']),canonical_rows_sha256=L.sha(obj['rows']),receipts=obj['receipts']))
    (ROOT/'source_receipts.json').write_text(json.dumps(sources,indent=2)+'\n')
    # Invariants that matter for causal comparison and missing outcomes.
    for r in rows:
        if r['entry_utc']:
            assert r['entry_utc']>=r['signal_known_utc']
            if r['arm']=='SURVIVOR72':assert r['survivor'] is True and r['entry_utc']>=r['checkpoint_utc']
        if not r['mature']:assert r['net_return_pct'] is None
        if r['status']=='NOT_SURVIVOR' and r['mature']:assert r['net_return_pct']==0
    # Match optimized calculations to frozen engine at widely spaced valid points.
    for symbol,data in market.items():
        valid=list(data['indicators'])
        for t in valid[::max(1,len(valid)//10)]:
            a=[b for b in data['bars'] if b['end']<=t];expected=L.indicators(a);actual=data['indicators'][t]
            for key in ('atr14','structural_anchor'):assert math.isclose(expected[key],actual[key],rel_tol=1e-12)
            assert expected['signal']==actual['signal']
    print(json.dumps({k:result[k] for k in ['candidates','non_survivors','survivors','checkpoint_unknown','clusters','paired']},indent=2))
    print('PASS causal fills, null immature outcomes, rejected Survivor retention, frozen indicator equivalence')
if __name__=='__main__':execute()
