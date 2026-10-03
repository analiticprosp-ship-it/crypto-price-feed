#!/usr/bin/env python3
"""Independent research feed: OKX candles + current OI/funding, accumulated OI samples.
No trading signals; missing mappings/feeds are N/A. Uses stdlib only.
"""
import json, os, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
U=json.loads((ROOT/'universe.json').read_text())
OUT=ROOT/'market-structure.json'
now=datetime.now(timezone.utc)
# Limit request volume. P0 every run; P1 hourly; P2 every 4h.
priority=['P0'] + (['P1'] if now.minute < 15 else []) + (['P2'] if now.hour%4==0 and now.minute<15 else [])
selected=list(dict.fromkeys(x for pr in priority for x in U['priority'][pr] if x not in U['groups']['stablecoins_metrics_only']))
prior={}
try: prior=json.loads(OUT.read_text()).get('instruments',{})
except (FileNotFoundError,ValueError): pass
# Only exact direct OKX instrument names; if not listed, mark unavailable. Do not silently map aliases.
def api(path,params):
    url='https://www.okx.com'+path+'?'+urllib.parse.urlencode(params)
    rq=urllib.request.Request(url,headers={'User-Agent':'crypto-portfolio-structure/1.0','Accept':'application/json'})
    with urllib.request.urlopen(rq,timeout=12) as resp: obj=json.load(resp)
    if obj.get('code')!='0': raise RuntimeError(f'{path}: {obj.get("code")} {obj.get("msg")}')
    return obj.get('data',[])

def get_inst(inst_type):
    try: return {x['instId'] for x in api('/api/v5/public/instruments',{'instType':inst_type})}
    except Exception: return set()
spot_list=get_inst('SPOT'); swap_list=get_inst('SWAP')
res={}
for sym in selected:
    d={'roles':[k for k,v in U['groups'].items() if sym in v], 'source':'OKX','spot':{},'perpetual':{},'status':'N/A', 'updatedAt':now.isoformat()}
    old=prior.get(sym,{})
    # Preserve previous validated history on slow-tier runs where particular ticker is not requested.
    if sym in spot_list: pass # requires pair selection below; instrument list includes BTC-USDT etc.
    sp=f'{sym}-USDT'; sw=f'{sym}-USDT-SWAP'
    if sp in spot_list:
        for tf,bar in [('1D','1D'),('4H','4H'),('1H','1H')]:
            try:
                raw=api('/api/v5/market/history-candles',{'instId':sp,'bar':bar,'limit':'100'})
                # OKX [ts,o,h,l,c,vol,volCcy,volCcyQuote,confirm]; exclude unfinished candles
                cs=[{'t':int(x[0]),'o':x[1],'h':x[2],'l':x[3],'c':x[4],
                     'volumeBase':x[5],'volumeQuote':x[7] if len(x)>7 else None} for x in raw if len(x)>8 and x[8]=='1']
                d['spot'][tf]={'candles':sorted(cs,key=lambda x:x['t']),'ok':bool(cs)}
            except Exception as ex: d['spot'][tf]={'ok':False,'error':str(ex)[:160]}
            time.sleep(.10)
    else: d['spot']['availability']={'ok':False,'reason':'Exact '+sp+' not listed on OKX; no alias substitution'}
    if sw in swap_list and sym in set(U['perpetual_core']+U['groups']['futures_extended']):
        for tf,bar in [('1D','1D'),('4H','4H'),('1H','1H')]:
            try:
                raw=api('/api/v5/market/history-candles',{'instId':sw,'bar':bar,'limit':'100'})
                cs=[{'t':int(x[0]),'o':x[1],'h':x[2],'l':x[3],'c':x[4],
                     'volumeContracts':x[5],'volumeQuote':x[7] if len(x)>7 else None} for x in raw if len(x)>8 and x[8]=='1']
                d['perpetual'][tf]={'candles':sorted(cs,key=lambda x:x['t']),'ok':bool(cs)}
            except Exception as ex: d['perpetual'][tf]={'ok':False,'error':str(ex)[:160]}
            time.sleep(.10)
        try:
            x=api('/api/v5/public/open-interest',{'instType':'SWAP','instId':sw})[0]
            sample={'t':int(x.get('ts',0)),'oiContracts':x.get('oi'),'oiCcy':x.get('oiCcy'),'oiUsd':x.get('oiUsd')}
            hist=(old.get('perpetual') or {}).get('openInterestHistory',[])
            # Deduplicate and preserve 7d of samples; this is collection, NOT retroactive history.
            hist={str(x['t']):x for x in hist if x.get('t',0)>=int(now.timestamp()*1000)-7*86400*1000}
            if sample['t']>0:hist[str(sample['t'])]=sample
            d['perpetual']['openInterestCurrent']=sample
            d['perpetual']['openInterestHistory']=sorted(hist.values(),key=lambda a:a['t'])[-2016:]
        except Exception as ex:d['perpetual']['openInterestCurrent']={'ok':False,'error':str(ex)[:160]}
        try:
            x=api('/api/v5/public/funding-rate',{'instId':sw})[0]
            d['perpetual']['funding']={'fundingRate':x.get('fundingRate'),'fundingTime':x.get('fundingTime'),'nextFundingTime':x.get('nextFundingTime')}
        except Exception as ex:d['perpetual']['funding']={'ok':False,'error':str(ex)[:160]}
    else:d['perpetual']['availability']={'ok':False,'reason':'No validated exact swap or outside perp monitoring group'}
    d['status']='PARTIAL' if any(isinstance(v,dict) and v.get('ok') for v in d['spot'].values()) or any(isinstance(v,dict) and v.get('ok') for v in d['perpetual'].values()) else 'N/A'
    res[sym]=d
    time.sleep(.12)
# Preserve last P1/P2 samples on intermediate updates with explicit last check time and stale flag.
for sym,old in prior.items():
    if sym not in res:
        old['notUpdatedThisRun']=True
        res[sym]=old
payload={'schemaVersion':'1.0.0','generatedAt':now.isoformat(),'source':'OKX public API','priorityUpdated':priority,'semantics':{'candles':'CLOSED_ONLY chronological oldest-first','oi':'venue-specific; do not sum different units','history':'OI samples accumulated from installation date; no backfill invented','missing':'N/A is not zero','status':'data availability; never a trade approval'},'instruments':res}
OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n')
print(f'Wrote {OUT.name}: {len(selected)} requested / {len(res)} tracked')
