
#!/usr/bin/env python3
"""Compact, read-only analytical derivative of market-structure.json.
Falls back to public, CLOSED-only perpetual OHLCV; never grants trade authority.
stdlib only. Source file is not overwritten.
"""
import json, math, os, time, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
TFS={'15m':900000,'1H':3600000,'4H':14400000,'1D':86400000}
BARS={'15m':'15m','1H':'1H','4H':'4H','1D':'1Dutc'}
SYMS=['BTC','ETH','SOL','HYPE','AAVE','LINK','LDO','SUI','XRP','BNB','ENA','DOT',
      'AVAX','APT','NEAR','INJ']
def get_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'crypto-portfolio-fallback/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=12) as r:return json.load(r)
def valid(rows,tf,now_ms):
    period=TFS[tf]; out={}
    for x in rows:
        try:
            t=int(x['t']); o,h,l,c,v=(float(x[k]) for k in ('o','h','l','c','v'))
            if t%period or t+period>now_ms or not (0<l<=min(o,c)<=max(o,c)<=h) or min(v,o,h,l,c)<0:continue
            out[t]={'t':t,'o':o,'h':h,'l':l,'c':c,'v':v}
        except (ValueError,TypeError,KeyError):continue
    return [out[t] for t in sorted(out)]
def okx(sym,tf,now_ms):
    q=urllib.parse.urlencode({'instId':f'{sym}-USDT-SWAP','bar':BARS[tf],'limit':'100'})
    d=get_json('https://www.okx.com/api/v5/market/history-candles?'+q)
    if d.get('code')!='0':raise ValueError('OKX '+str(d.get('msg')))
    rows=[dict(t=x[0],o=x[1],h=x[2],l=x[3],c=x[4],v=x[5]) for x in d.get('data',[]) if len(x)>8 and x[8]=='1']
    return valid(rows,tf,now_ms)
def binance(sym,tf,now_ms):
    bar={'1D':'1d','4H':'4h','1H':'1h','15m':'15m'}[tf]
    q=urllib.parse.urlencode({'symbol':sym+'USDT','interval':bar,'limit':100})
    d=get_json('https://fapi.binance.com/fapi/v1/klines?'+q)
    rows=[dict(t=x[0],o=x[1],h=x[2],l=x[3],c=x[4],v=x[5]) for x in d]
    return valid(rows,tf,now_ms)
def mexc(sym,tf,now_ms):
    interval={'1D':'Day1','4H':'Hour4','1H':'Hour1','15m':'Min15'}[tf]
    d=get_json(f'https://contract.mexc.com/api/v1/contract/kline/{sym}_USDT?'+urllib.parse.urlencode({'interval':interval}))
    if not d.get('success'):raise ValueError('MEXC unavailable')
    v=d['data']; rows=[dict(t=int(t)*1000,o=o,h=h,l=l,c=c,v=vol) for t,o,h,l,c,vol in zip(v['time'],v['open'],v['high'],v['low'],v['close'],v['vol'])]
    return valid(rows,tf,now_ms)
def extract(primary,sym,tf,now_ms):
    block=primary.get('instruments',{}).get(sym,{}).get('perpetual',{}).get(tf,{})
    raw=[dict(t=x['t'],o=x['o'],h=x['h'],l=x['l'],c=x['c'],v=x.get('volumeContracts',0)) for x in block.get('candles',[])]
    candles=valid(raw,tf,now_ms)
    if len(candles)>=26 and now_ms-candles[-1]['t']<=3*TFS[tf]:
        return {'venue':'OKX-primary','candles':candles,'attempts':[]}
    attempts=['primary: insufficient or stale']
    for venue,fn in [('OKX',okx),('Binance Futures',binance),('MEXC Futures',mexc)]:
        try:
            cs=fn(sym,tf,now_ms)
            if len(cs)>=26 and now_ms-cs[-1]['t']<=3*TFS[tf]:
                return {'venue':venue,'candles':cs,'attempts':attempts}
            attempts.append(venue+': insufficient or stale')
        except Exception as e:attempts.append(venue+': '+str(e)[:120])
    return {'venue':None,'candles':[],'attempts':attempts}
def aligned_rs(asset,btc,tf):
    a={x['t']:x['c'] for x in asset}; b={x['t']:x['c'] for x in btc}
    common=sorted(set(a)&set(b))
    if len(common)<2:return None
    end=common[-1]; start=end-TFS[tf]
    if end!=max(a) or end!=max(b):return None
    if start not in a or start not in b:return None
    ra=100*(a[end]/a[start]-1);rb=100*(b[end]/b[start]-1)
    return {'start':start,'end':end,'assetReturnPct':round(ra,5),'btcReturnPct':round(rb,5),'rsPctPoints':round(ra-rb,5)}

def detector_features(candles, tf):
    """OHLCV-only *candidate* patterns, never proof of taker absorption."""
    period=TFS[tf]
    if len(candles)<14:
        return {'status':'INSUFFICIENT_CLOSED_BARS','requiredBars':14,'availableBars':len(candles)}
    recent=candles[-14:]
    gaps=sum(recent[i]['t']-recent[i-1]['t']!=period for i in range(1,len(recent)))
    last=recent[-1]
    result={'status':'OHLCV_PROXY_ONLY','sourceBarClosedAt':last['t']+period,
            'closedBars':len(candles),'gapsInLast14':gaps, 'lookbackBars':12}
    if gaps:
        result['status']='GAPPED_HISTORY'
        return result
    prev=recent[-13:-1]
    upper=max(x['h'] for x in prev);lower=min(x['l'] for x in prev)
    width=last['h']-last['l']
    last3=recent[-3:]
    widths=[x['h']-x['l'] for x in last3]
    result['pressureProxy']={
        'lastCloseLocation':round((last['c']-last['l'])/width,5) if width>0 else None,
        'lastBodyToRange':round((last['c']-last['o'])/width,5) if width>0 else None,
        'last3RangesContracting':widths[0]>widths[1]>widths[2],
        'lastVolumeVsPrior4':round(last['v']/(sum(x['v'] for x in recent[-5:-1])/4),5)
            if sum(x['v'] for x in recent[-5:-1])>0 else None,
        'interpretation':'PRICE_VOLUME_PROXY_NOT_TAKER_FLOW'
    }
    result['localStructure']={
        'prior12High':upper,'prior12Low':lower,
        'sweptLowReclaimed':last['l']<lower and last['c']>lower,
        'sweptHighRejected':last['h']>upper and last['c']<upper,
        'closedAbovePrior12High':last['c']>upper,
        'closedBelowPrior12Low':last['c']<lower,
        'interpretation':'PRICE_PATTERN_CANDIDATE_NOT_VERIFIED_ORDER_FLOW'
    }
    return result

def detector_derivatives(primary, sym, now_ms):
    """Observed OKX-only derivatives with age and unit guards. No missing -> zero."""
    src=primary.get('instruments',{}).get(sym,{})
    pp=src.get('perpetual') or {}
    out={'venue':'OKX','status':'N/A', 'openInterest':None,'funding':None,
         'liquidations':None,'takerFlow':None,'orderBook':None,
         'historyIsObservedOnly':True}
    samples=[x for x in pp.get('openInterestHistory',[])
             if isinstance(x,dict) and isinstance(x.get('t'),int) and 0<=now_ms-x['t']<=7*86400000]
    samples.sort(key=lambda x:x['t'])
    def num(x):
        try:
            v=float(x)
            return v if math.isfinite(v) else None
        except (TypeError,ValueError):return None
    if samples and now_ms-samples[-1]['t']<=30*60000:
        cur=samples[-1]
        oi={'timestamp':cur['t'],'ageMs':now_ms-cur['t'],
            'oiContracts':num(cur.get('oiContracts')), 'oiUsd':num(cur.get('oiUsd')),
            'oiCcy':num(cur.get('oiCcy')), 'deltaContractsPct1h':None,
            'deltaUsdPct1h':None,'deltaContractsPct15m':None,
            'unitRule':'DO_NOT_AGGREGATE_VENUES; USD-NOT-NEW-CONTRACTS'}
        for label,window_ms in [('1h',3600000),('15m',900000)]:
            target=cur['t']-window_ms
            prior=min(samples[:-1],key=lambda x:abs(x['t']-target),default=None)
            if prior and abs(prior['t']-target)<=window_ms*.25:
                p=num(prior.get('oiContracts')); c=oi['oiContracts']
                if p and p>0 and c is not None:
                    oi['deltaContractsPct'+label]=round(100*(c/p-1),4)
                if label=='1h':
                    pu=num(prior.get('oiUsd'));cu=oi['oiUsd']
                    if pu and pu>0 and cu is not None:
                        oi['deltaUsdPct1h']=round(100*(cu/pu-1),4)
        out['openInterest']=oi
    funding=pp.get('funding') or {}
    observed=funding.get('observedAtMs')
    if isinstance(observed,int) and 0<=now_ms-observed<=60*60000:
        out['funding']={'rate':num(funding.get('fundingRate')),
                        'observedAtMs':observed,
                        'fundingTime':funding.get('fundingTime'),
                        'nextFundingTime':funding.get('nextFundingTime')}
    out['status']='PARTIAL' if out['openInterest'] or out['funding'] else 'N/A'
    return out

def build(primary,syms=SYMS,now_ms=None,fetch=extract):
    now_ms=now_ms or int(time.time()*1000); records={}
    for sym in dict.fromkeys(['BTC']+list(syms)):
        records[sym]={}
        for tf in TFS:
            d=fetch(primary,sym,tf,now_ms); cs=d['candles']
            records[sym][tf]={'source':d['venue'],'lastClosedOpen':cs[-1]['t'] if cs else None,'count':len(cs),
                              'attempts':d['attempts'],'rsVsBTC':None,'candles':cs,
                              'detectorFeatures':detector_features(cs,tf) if tf in ('15m','1H','4H') else None,
                              'lastClosedBar':dict(cs[-1],endMs=cs[-1]['t']+TFS[tf])
                                   if cs and tf=='15m' else None}
    for sym,tfs in records.items():
        for tf,x in tfs.items():
            if sym!='BTC' and x['source'] == records['BTC'][tf]['source'] and x['source'] is not None:x['rsVsBTC']=aligned_rs(x['candles'],records['BTC'][tf]['candles'],tf)
    for s,tfs in records.items():
        tfs['derivatives']=detector_derivatives(primary,s,now_ms)
        for tf in TFS:
            tfs[tf].pop('candles')
    return {'schemaVersion':'1.0','generatedAt':datetime.fromtimestamp(now_ms/1000,timezone.utc).isoformat(),
            'researchOnly':True,'notTradeApproval':True,'rsMethod':'same-venue within each row; synchronized exact closed periods; do not compare mixed venues',
            'detectorFeatureContract':'CLOSED_OHLCV_ONLY; proxy, NOT taker-flow/absorption proof; NO_TRADE_APPROVAL',
            'instruments':records}
def main():
    p=ROOT/'market-structure.json'
    try: primary=json.loads(p.read_text())
    except (OSError,ValueError):primary={}
    result=build(primary)
    out=ROOT/'market-summary.json';out.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    leaders=[]
    for s,d in result['instruments'].items():
        if s=='BTC':continue
        rs=d['4H']['rsVsBTC']
        if rs and d['4H']['source']==result['instruments']['BTC']['4H']['source']:
            leaders.append({'symbol':s,'rs4HPctPoints':rs['rsPctPoints'],'rs1H':d['1H']['rsVsBTC'],
                            'source':d['4H']['source'],'lastClosedOpen':d['4H']['lastClosedOpen']})
    leaders.sort(key=lambda x:x['rs4HPctPoints'],reverse=True)
    (ROOT/'market-leaders.json').write_text(json.dumps({'generatedAt':result['generatedAt'],'researchOnly':True,'leaders':leaders},ensure_ascii=False,separators=(',',':'))+'\n')
    print('Compact structure: '+str(len(result['instruments']))+' instruments, leaders='+str(len(leaders)))
if __name__=='__main__':main()
