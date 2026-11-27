"""Public-data-only prospective PAPER observer. Python standard library only.

Never submits orders, reads exchange accounts, or uses credentials.
Every fill uses a quote actually observed in this run, never a past bar open.
"""
import argparse
import base64
import concurrent.futures
import copy
import datetime as dt
import hashlib
import json
import math
import pathlib
import statistics
import urllib.parse
import urllib.request
import zlib

API='https://data-api.binance.vision/api/v3/'
H4=14400000
DAY=86400000
SYMBOLS=['BTCUSDT','ETHUSDT']

def utc(ms):return dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc).isoformat().replace('+00:00','Z')
def timestamp(text):return int(dt.datetime.fromisoformat(text.replace('Z','+00:00')).timestamp()*1000)
def now_ms():return int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(x):return hashlib.sha256(canonical(x).encode()).hexdigest()

def get(path,**params):
    url=API+path+('?' + urllib.parse.urlencode(params) if params else '')
    with urllib.request.urlopen(url,timeout=25) as response:obj=json.load(response)
    if isinstance(obj,dict) and 'code' in obj:raise ValueError('PUBLIC_API_ERROR '+str(obj.get('code')))
    return obj

def candles(rows,step,asof):
    out=[]
    for r in rows:
        start=int(r[0]);end=int(r[6])+1
        if end>asof:continue
        o,h,l,c,v=map(float,r[1:6])
        assert start%step==0 and end==start+step and 0<l<=min(o,c)<=max(o,c)<=h
        out.append({'t':start,'end':end,'o':o,'h':h,'l':l,'c':c,'v':v})
    out.sort(key=lambda x:x['t'])
    assert len({r['t'] for r in out})==len(out)
    assert all(b['t']-a['t']==step for a,b in zip(out,out[1:])), 'OHLCV_GAP'
    assert out[-1]['end']==asof//step*step,'STALE_CLOSED_CANDLE'
    return out

def ema(values,span):
    alpha=2/(span+1);result=[];v=float(values[0])
    for x in values:v=alpha*x+(1-alpha)*v;result.append(v)
    return result

def phase(daily,asof):
    d=[r for r in daily if r['end']<=asof]
    assert len(d)>=220,'DAILY_WARMUP'
    c=[r['c'] for r in d];ma=statistics.fmean(c[-200:]);old=statistics.fmean(c[-220:-20]);slope=ma/old-1;dist=c[-1]/ma-1
    if dist>.02 and slope>0:regime='UP'
    elif dist<-.02 and slope<0:regime='DOWN'
    elif abs(dist)<=.02 and abs(slope)<=.01:regime='RANGE'
    else:regime='TRANSITION'
    e=ema(c,20)
    return {'regime':regime,'daily_close_utc':utc(d[-1]['end']),'close':c[-1],'sma200':ma,'sma_slope20':slope,'ema20':e[-1],'ema20_lag5':e[-6],'constructive_transition':c[-1]>e[-1] and e[-1]>e[-6]}

def indicators(bars):
    assert len(bars)>=500,'NW_WARMUP'
    closes=[r['c'] for r in bars]
    tr=[]
    for i,r in enumerate(bars):
        prev=bars[i-1]['c'] if i else r['c']
        tr.append(max(r['h']-r['l'],abs(r['h']-prev),abs(r['l']-prev)))
    atr=statistics.fmean(tr[:14])
    for v in tr[14:]:atr=(atr*13+v)/14
    w=[math.exp(-i*i/(2*8*8)) for i in range(500)]
    center=math.fsum(closes[-1-i]*w[i] for i in range(500))/math.fsum(w)
    last=bars[-1];previous_high=max(r['h'] for r in bars[-21:-1])
    return {'atr14':atr,'nw_center':center,'breakout20_high':previous_high,'signal':last['c']>previous_high and last['c']>center,'structural_anchor':min(r['l'] for r in bars[-5:])-.25*atr,'signal_open_utc':utc(last['t']),'signal_close_utc':utc(last['end']),'close':last['c']}

def snapshot():
    server=get('time')['serverTime'];observed=now_ms()
    assert abs(server-observed)<120000,'CLOCK_SKEW'
    tasks={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for symbol in SYMBOLS:
            tasks[(symbol,'4H')]=pool.submit(get,'klines',symbol=symbol,interval='4h',limit=1000)
            tasks[(symbol,'1D')]=pool.submit(get,'klines',symbol=symbol,interval='1d',limit=500)
            tasks[(symbol,'quote')]=pool.submit(get,'ticker/bookTicker',symbol=symbol)
        raw={s:{} for s in SYMBOLS};parsed={}
        for symbol in SYMBOLS:
            raw[symbol]['4H']=tasks[(symbol,'4H')].result();raw[symbol]['1D']=tasks[(symbol,'1D')].result()
            q=tasks[(symbol,'quote')].result();received=now_ms()
            bid=float(q['bidPrice']);ask=float(q['askPrice']);assert 0<bid<=ask and (ask-bid)/((bid+ask)/2)<.007,'BAD_SPREAD'
            parsed[symbol]={'bars':candles(raw[symbol]['4H'],H4,server),'daily':candles(raw[symbol]['1D'],DAY,server),'quote':{'bid':bid,'ask':ask,'mid':(bid+ask)/2,'observed_utc':utc(received)}}
    raw_text=canonical(raw).encode()
    return {'server_utc':utc(server),'observed_utc':utc(now_ms()),'symbols':parsed,'audit_inputs':{'codec':'base64+zlib+json','sha256_uncompressed':hashlib.sha256(raw_text).hexdigest(),'payload':base64.b64encode(zlib.compress(raw_text,9)).decode()}}

def add_event(state,symbol,kind,at,**data):
    record={'kind':kind,'symbol':symbol,'first_detected_utc':at,**data}
    key={k:v for k,v in record.items() if k not in ['first_detected_utc','observed_price']}
    record['event_id']=sha(key)
    if any(e['event_id']==record['event_id'] for e in state['events']):return
    state['events'].append(record)

def apply(state,snap):
    state=copy.deepcopy(state);now=timestamp(snap['observed_utc']);start=timestamp(state['first_eligible_signal_close_utc']);end=timestamp(state['test_end_signal_close_utc']);fee=state['cost_per_side']
    before_count=len(state['events']);summary={};finishing=now>=end
    for symbol in SYMBOLS:
        account=state['buckets'][symbol];data=snap['symbols'][symbol];bars=data['bars'];daily=data['daily'];quote=data['quote'];p=quote['mid'];at=quote['observed_utc']
        last_seen=timestamp(account['last_processed_close_utc']) if account.get('last_processed_close_utc') else bars[-1]['end']
        new=[r for r in bars if last_seen<r['end']<=end]
        current=phase(daily,timestamp(snap['server_utc']));last_info=indicators(bars)
        exited=False;position=account['position'];exit_intent=None;partial_intent=None
        if position:
            for bar in new:
                if bar['end']<=timestamp(position['entry_observed_utc']):continue
                history=[r for r in bars if r['end']<=bar['end']];info=indicators(history)
                context=phase(daily,bar['t']) # matches frozen engine's context available at candle open
                reason=None
                if bar['c']<=position['invalidation']:reason='CLOSE_INVALIDATION'
                elif context['regime']=='DOWN':reason='REGIME_DOWN'
                elif bar['end']-timestamp(position['entry_observed_utc'])>=30*DAY:reason='TIME_30D'
                if reason:
                    exit_intent=(bar,reason);break
                unit_risk=position['initial_distance']+2*fee*position['entry_price']
                target=(position['entry_price']*(1+fee)+1.5*unit_risk)/(1-fee)
                if not position['half_done'] and bar['c']>=target and partial_intent is None:partial_intent=(bar,target)
                position['highest_close']=max(position['highest_close'],bar['c'])
                position['invalidation']=max(position['invalidation'],position['highest_close']-3*info['atr14'])
                if position['half_done']:position['invalidation']=max(position['invalidation'],position['entry_price']*(1+fee)/(1-fee))
            if exit_intent or partial_intent:
                if exit_intent:signal,reason=exit_intent;qty=position['quantity'];kind='PAPER_EXIT'
                else:signal,target=partial_intent;reason='CLOSE_TP1';qty=min(position['quantity'],position['initial_quantity']*.5);kind='PAPER_PARTIAL'
                proceeds=qty*p*(1-fee);account['cash']+=proceeds;position['proceeds']+=proceeds;position['quantity']-=qty
                add_event(state,symbol,kind,at,signal_close_utc=utc(signal['end']),observed_price=p,quantity=qty,reason=reason,delay_seconds=(timestamp(at)-signal['end'])/1000,paper_only=True)
                if position['quantity']<=position['initial_quantity']*1e-10:
                    pnl=position['proceeds']-position['entry_cost'];account['realized_pnl']+=pnl
                    account['closed_trades'].append({'entry_observed_utc':position['entry_observed_utc'],'exit_observed_utc':at,'phase':position['phase'],'net_pnl':pnl,'R_net':pnl/position['initial_risk'],'reason':reason})
                    account['position']=None;account['last_exit_observed_utc']=at;position=None;exited=True
                else:
                    position['half_done']=True
                    position['invalidation']=max(position['invalidation'],position['entry_price']*(1+fee)/(1-fee))
        if new and position is None and not exited and not finishing:
            signal=new[-1];seen=signal['end'];info=indicators([r for r in bars if r['end']<=seen])
            own=phase(daily,seen);btc=phase(snap['symbols']['BTCUSDT']['daily'],seen)
            eligible=own['regime']=='UP' or (own['regime']=='TRANSITION' and own['constructive_transition'])
            cooldown=account.get('last_exit_observed_utc') and now-timestamp(account['last_exit_observed_utc'])<8*3600000
            if start<=seen<end and info['signal']:
                reject=[]
                if not eligible:reject.append('REGIME_NOT_ELIGIBLE')
                if symbol=='ETHUSDT' and btc['regime']=='DOWN':reject.append('BTC_DOWN_VETO')
                if cooldown:reject.append('COOLDOWN')
                delay=(timestamp(at)-seen)/1000
                if delay>state['max_entry_detection_delay_seconds']:reject.append('LATE_DETECTION_NO_RETRO_FILL')
                if p>info['close']+.5*info['atr14']:reject.append('PRICE_CHASE')
                stop=min(info['structural_anchor'],p-info['atr14']);distance=p-stop
                if stop<=0 or distance>3*info['atr14']:reject.append('INVALID_STRUCTURAL_DISTANCE')
                if reject:add_event(state,symbol,'SIGNAL_REJECTED',at,signal_close_utc=utc(seen),reasons=reject,phase=own['regime'],delay_seconds=delay,paper_only=True)
                else:
                    risk=.005 if own['regime']=='UP' else .0025;cap=.25 if own['regime']=='UP' else .125;unit=distance+2*fee*p
                    qty=min(account['cash']*risk/unit,account['cash']*cap/(p*(1+fee)));debit=qty*p*(1+fee)
                    account['cash']-=debit
                    account['position']={'entry_observed_utc':at,'signal_close_utc':utc(seen),'phase':own['regime'],'entry_price':p,'entry_cost':debit,'quantity':qty,'initial_quantity':qty,'initial_distance':distance,'initial_risk':qty*unit,'invalidation':stop,'highest_close':p,'half_done':False,'proceeds':0.}
                    add_event(state,symbol,'PAPER_ENTRY',at,signal_close_utc=utc(seen),observed_price=p,quantity=qty,phase=own['regime'],initial_invalidation=stop,delay_seconds=delay,paper_only=True)
        for missed in new[:-1]:
            if start<=missed['end']<end and now-missed['end']>state['max_entry_detection_delay_seconds']*1000:
                add_event(state,symbol,'MISSED_OBSERVATION',snap['observed_utc'],signal_close_utc=utc(missed['end']),paper_only=True)
        if new:account['last_processed_close_utc']=utc(new[-1]['end'])
        elif not account.get('last_processed_close_utc'):account['last_processed_close_utc']=utc(bars[-1]['end'])
        pos=account['position'];mark=(next((r['c'] for r in reversed(bars) if r['end']<=end),bars[-1]['c']) if finishing else bars[-1]['c'])
        nav=account['cash']+(pos['quantity']*mark*(1-fee) if pos else 0)
        account['closed_mark_nav']=nav
        summary[symbol]={'regime':current['regime'],'constructive_transition':current['constructive_transition'],'last_closed_4H_utc':utc(bars[-1]['end']),'last_closed_1D_utc':utc(daily[-1]['end']),'breakout_signal_on_last_closed':last_info['signal'],'position':pos is not None,'cash':account['cash'],'closed_mark_nav':nav,'closed_trades':len(account['closed_trades']),'realized_pnl':account['realized_pnl']}
    total=sum(x['closed_mark_nav'] for x in state['buckets'].values());state['peak_nav']=max(state['peak_nav'],total);state['max_drawdown_pct']=min(state['max_drawdown_pct'],(total/state['peak_nav']-1)*100)
    state['status']='INITIAL_WINDOW_FINISHED' if finishing else 'RUNNING_PAPER_ONLY';state['last_observed_utc']=snap['observed_utc'];state['run_count']+=1
    state['latest_snapshot']={'server_utc':snap['server_utc'],'observed_utc':snap['observed_utc'],'symbols':summary,'quotes':{s:snap['symbols'][s]['quote'] for s in SYMBOLS},'audit_inputs':snap['audit_inputs']}
    state['history'].append({'observed_utc':snap['observed_utc'],'last_closed_4H_utc':summary['BTCUSDT']['last_closed_4H_utc'],'nav':total,'event_count':len(state['events']),'status':state['status']})
    state['latest_result']={'status':state['status'],'virtual_nav':total,'virtual_return_pct':(total/state['initial_virtual_capital']-1)*100,'new_events':state['events'][before_count:],'symbols':summary,'final_window':finishing}
    return state

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--state',required=True);parser.add_argument('--out',required=True);args=parser.parse_args()
    path=pathlib.Path(args.state);state=json.loads(path.read_text())
    assert state['kind']=='LONG_CANDIDATE_FORWARD_PAPER_V1'
    runner_hash=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
    assert state['runner_sha256']==runner_hash,'RUNNER_HASH_CHANGED'
    if state['status']=='INITIAL_WINDOW_FINISHED':
        print(canonical({'status':'ALREADY_FINISHED','message':'Do not extend or trade without a new instruction.'}));return
    result=apply(state,snapshot());pathlib.Path(args.out).write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
    print(canonical(result['latest_result']))

if __name__=='__main__':main()
