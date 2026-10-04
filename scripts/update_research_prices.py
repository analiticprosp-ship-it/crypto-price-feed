#!/usr/bin/env python3
"""Independent non-trading research quotes; never substitutes prices.json."""
import json
import math
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime,timezone
from pathlib import Path

BASE='https://crypto-price-gateway.vercel.app'

def one(symbol,market):
    url=BASE+'/batch?'+urllib.parse.urlencode({'symbols':symbol,'market':market})
    with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'crypto-price-feed/research-1'}),timeout=9) as r:
        payload=json.load(r)
    for q in payload.get('quotes',[]):
        p=q.get('systemPrice')
        if q.get('symbol')==symbol and q.get('ok') is True and isinstance(p,(float,int)) and not isinstance(p,bool) and math.isfinite(p) and p>0:
            return q
    raise RuntimeError('N/A: exact valid quote missing')

def main():
    now=datetime.now(timezone.utc)
    u=json.loads(Path('universe.json').read_text())
    # P0 belongs to the isolated primary file. Research P1/P2 are deliberately non-trading.
    groups=[]
    if now.minute<18:
        groups.append('P1')
        if now.hour%4==0: groups.append('P2')
    spot=list(dict.fromkeys(s for g in groups for s in u['priority'][g] if s not in u['spot_core'] and s not in u['groups']['stablecoins_metrics_only']))
    perp=list(dict.fromkeys(s for s in u['groups']['futures_extended'] if s not in u['perpetual_core']))
    jobs=[('spot',s) for s in spot]+[('perp',s) for s in perp]
    out={'generatedAt':None,'authority':'RESEARCH_ONLY_NO_SYSTEMPRICE_NO_TRADE',
         'source':BASE,'groupsRequested':groups,'spot':{'quotes':[]},'perpetual':{'quotes':[]},
         'availability':{'spot':{},'perpetual':{}},'notRequestedThisRun':'N/A_NOT_FRESH'}
    with ThreadPoolExecutor(max_workers=10) as executor:
        fs={executor.submit(one,s,m):(m,s) for m,s in jobs}
        for f in as_completed(fs):
            market,symbol=fs[f]; section='spot' if market=='spot' else 'perpetual'
            try: out[section]['quotes'].append(f.result())
            except Exception as exc: out['availability'][section][symbol]=str(exc)[:140]
    out['generatedAt']=datetime.now(timezone.utc).isoformat()
    Path('research-prices.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print('Research',out['generatedAt'],'success',len(out['spot']['quotes'])+len(out['perpetual']['quotes']))

if __name__=='__main__': main()
