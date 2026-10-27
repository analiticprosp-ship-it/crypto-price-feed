"""Offline exploratory entry timing study; no orders or PAPER state writes.
Usage: python compare.py --inputs DIR --out FILE
Requires runner.py, long_state.json, btc_spot_1h.json, detector_state.json.
Not a replay of forward operational mid fills or full managed LONG exits.
"""
import argparse, base64, hashlib, json, math, pathlib, zlib
import runner as L

def run(root):
    state=json.loads((root/'long_state.json').read_text())
    assert hashlib.sha256((root/'runner.py').read_bytes()).hexdigest()==state['runner_sha256']
    packed=state['latest_snapshot']['audit_inputs']
    raw_bytes=zlib.decompress(base64.b64decode(packed['payload']))
    assert hashlib.sha256(raw_bytes).hexdigest()==packed['sha256_uncompressed']
    raw=json.loads(raw_bytes); asof=L.timestamp(state['last_observed_utc'])
    market={s:{t:L.candles(rows, L.H4 if t=='4H' else L.DAY,asof) for t,rows in d.items()} for s,d in raw.items()}
    hourly=json.loads((root/'btc_spot_1h.json').read_text())
    hrows=hourly['candles']; H=3600000
    assert all(b[0]-a[0]==H for a,b in zip(hrows,hrows[1:]))
    assert L.sha(hrows)==hourly['sha256_candles']
    accepted=[]
    # Exact candidate selection from pinned detector, before Survivor selection.
    for i in range(66,len(hrows)):
        j=min(range(i-18,i-2),key=lambda k:float(hrows[k][3]))
        low=float(hrows[j][3]);high=max(float(hrows[k][2]) for k in range(j-48,j));close=float(hrows[i][4])
        if high<=0 or (high-low)/high<.05 or (close-low)/low<.02 or (close-low)/(high-low)>=.8:continue
        if any(float(hrows[k][3])<low for k in range(j+1,i+1)):continue
        if sum(float(hrows[k][4])>float(hrows[k][1]) for k in range(j+1,i+1))<2:continue
        if accepted and hrows[i][0]-accepted[-1]['signal_open_ms']<168*H:continue
        cp=hrows[j][0]+73*H
        survival=None if j+72>=len(hrows) else min(float(r[3]) for r in hrows[j+1:j+73])>=low
        accepted.append(dict(id='btc72h-'+str(hrows[i][0]),signal_open_ms=hrows[i][0],known_ms=hrows[i][0]+H,checkpoint_ms=cp,survivor=survival,low=low))
    reference=json.loads((root/'detector_state.json').read_text())
    assert [e['id'] for e in accepted]==[e['id'] for e in reference['accepted']]
    rows=[]
    for event in accepted:
        start=math.ceil(event['known_ms']/L.H4)*L.H4
        checkpoint=math.ceil(event['checkpoint_ms']/L.H4)*L.H4
        for symbol,data in market.items():
            bars=data['4H']; bytime={b['t']:b for b in bars}
            def allowed(t):
                p=L.phase(data['1D'],t)
                own=p['regime']=='UP' or (p['regime']=='TRANSITION' and p['constructive_transition'])
                return own and (symbol=='BTCUSDT' or L.phase(market['BTCUSDT']['1D'],t)['regime']!='DOWN')
            for days in (7,14):
                end=start+days*L.DAY
                for arm in ('EARLY','LONG_CONFIRM','SURVIVOR72'):
                    fill=None;reason='NO_SIGNAL'
                    times=[start] if arm=='EARLY' else ([checkpoint] if arm=='SURVIVOR72' else range(start,end,L.H4))
                    if arm=='SURVIVOR72' and event['survivor'] is not True:reason='NOT_SURVIVOR' if event['survivor'] is False else 'CHECKPOINT_PENDING';times=[]
                    for t in times:
                        if t>=end:reason='LATE';break
                        if t not in bytime:reason='DATA_UNAVAILABLE';break
                        if not allowed(t):reason='REGIME_REJECTED';continue
                        if arm=='LONG_CONFIRM':
                            hist=[b for b in bars if b['end']<=t]
                            if len(hist)<500:reason='WARMUP_UNAVAILABLE';continue
                            info=L.indicators(hist)
                            if not info['signal']:continue
                            p=bytime[t]['o'];stop=min(info['structural_anchor'],p-info['atr14'])
                            if p>info['close']+.5*info['atr14'] or stop<=0 or p-stop>3*info['atr14']:reason='LONG_PRICE_DISTANCE_REJECTED';continue
                        fill=t;reason='FILLED';break
                    mature=end in bytime
                    result=dict(event_id=event['id'],symbol=symbol,horizon_days=days,arm=arm,survivor=event['survivor'],signal_known_utc=L.utc(event['known_ms']),checkpoint_utc=L.utc(event['checkpoint_ms']),entry_utc=L.utc(fill) if fill is not None else None,exit_utc=L.utc(end),status=reason,mature=mature,net_return_pct=None,stress_return_pct=None,mae_pct=None,mfe_pct=None)
                    if mature:
                        if fill is None and reason not in ('DATA_UNAVAILABLE','WARMUP_UNAVAILABLE','CHECKPOINT_PENDING'):
                            result['net_return_pct']=result['stress_return_pct']=0.
                        elif fill is not None:
                            p=bytime[fill]['o'];exitp=bytime[end]['o'];segment=[b for b in bars if fill<=b['t']<end]
                            result.update(net_return_pct=(exitp*(1-.0015)/(p*(1+.0015))-1)*100,stress_return_pct=(exitp*(1-.003)/(p*(1+.003))-1)*100,mae_pct=(min(b['l'] for b in segment)/p-1)*100,mfe_pct=(max(b['h'] for b in segment)/p-1)*100)
                    rows.append(result)
    summary=[]
    for symbol in market:
        for days in (7,14):
            for arm in ('EARLY','LONG_CONFIRM','SURVIVOR72'):
                a=[r for r in rows if r['symbol']==symbol and r['horizon_days']==days and r['arm']==arm and r['mature'] and r['net_return_pct'] is not None]
                f=[r for r in a if r['status']=='FILLED']
                summary.append(dict(symbol=symbol,days=days,arm=arm,mature_events=len(a),fills=len(f),mean_all_events_pct=sum(r['net_return_pct'] for r in a)/len(a) if a else None,mean_filled_pct=sum(r['net_return_pct'] for r in f)/len(f) if f else None))
    return dict(status='EXPLORATORY_NOT_OOS',asof_utc=state['last_observed_utc'],candidate_count=len(accepted),non_survivors=sum(e['survivor'] is False for e in accepted),independence='All three lows within one 30-day cluster; effective independent clusters <=1',scope='Equal notional entry timing with common calendar exit; no stops, partials, sizing, portfolio compounding or operational quote fills. ETH uses BTC event timing, not BTC probabilities.',events=accepted,rows=rows,summary=summary,source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'runner.py',root/'long_state.json',root/'btc_spot_1h.json',root/'detector_state.json']})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args()
    result=run(a.inputs);a.out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(result['summary'],indent=2))
