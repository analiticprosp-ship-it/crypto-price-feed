#!/usr/bin/env python3
"""Critical prices.json: only this file authorizes live system prices."""
import json
import math
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = 'https://crypto-price-gateway.vercel.app'
OUT = Path('prices.json')

def batch(symbols, market, timeout=18):
    url = BASE + '/batch?' + urllib.parse.urlencode({'symbols': ','.join(symbols), 'market': market})
    req = urllib.request.Request(url, headers={'Accept':'application/json', 'User-Agent':'crypto-price-feed/core-3'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f'Gateway HTTP {response.status}')
        return json.load(response)

def valid_quote(q, symbol, now):
    if q.get('symbol') != symbol or q.get('ok') is not True:
        return False
    price = q.get('systemPrice')
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
        return False
    try:
        requested = datetime.fromisoformat(q['requestedAt'].replace('Z', '+00:00'))
    except (KeyError, ValueError, TypeError):
        return False
    return -60 <= (now - requested).total_seconds() <= 120

def mandatory_ok(obj, symbols):
    now = datetime.now(timezone.utc)
    qs = {q.get('symbol'): q for q in obj.get('quotes', [])}
    return obj.get('ok') is True and all(valid_quote(qs.get(s, {}), s, now) for s in symbols)

def main():
    u = json.loads(Path('universe.json').read_text())
    main_spot = u['spot_core']
    main_perp = ['BTC','ETH','SOL','XRP','HYPE']  # the original failure-isolated mandatory set
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(batch, main_spot, 'spot')
        b = pool.submit(batch, main_perp, 'perp')
        spot, perp = a.result(), b.result()
    if not mandatory_ok(spot, main_spot) or not mandatory_ok(perp, main_perp):
        raise RuntimeError('MANDATORY_QUOTES_NOT_VALID: keep previous prices.json; do not timestamp stale prices')
    # Preserve previously available P0 Spot and Futures focus, without letting any failure block core.
    extra_spot = [s for s in u['priority']['P0'] if s not in main_spot and s not in u['groups']['stablecoins_metrics_only']]
    extra_perp = [s for s in u['perpetual_core'] if s not in main_perp]
    optional = [('spot', s) for s in extra_spot] + [('perp', s) for s in extra_perp]
    failures = {'spot':{}, 'perpetual':{}}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(batch, [s], market, 8):(market,s) for market,s in optional}
        for f in as_completed(futures):
            market,s = futures[f]
            try:
                data = f.result()
                good = [q for q in data.get('quotes',[]) if valid_quote(q, s, datetime.now(timezone.utc))]
                if not good: raise ValueError('N/A: exact fresh quote unavailable')
                (spot if market == 'spot' else perp)['quotes'].extend(good)
            except Exception as e:
                failures['spot' if market == 'spot' else 'perpetual'][s] = str(e)[:140]
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        'generatedAt':now, 'source':BASE,
        'protocol':{'venues':['MEXC','OKX','Bybit'],'price':'mid=(bid+ask)/2',
          'rule':'3 fresh -> mean_3; 2 fresh -> mean_2; <2 -> validated OKX; spread >0.7% -> OKX',
          'freshnessSeconds':15,'fileMaxAgeMinutes':15,'spreadLimitPct':0.7,
          'universe':'universe.json','researchFeedIndependent':'research-prices.json',
          'optionalFailuresAreNotZero':True},
        'spot':spot,'perpetual':perp,'optionalAvailability':failures}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    print('Published core',now,'spot',len(spot['quotes']),'perp',len(perp['quotes']),'optional failures',failures)

if __name__ == '__main__': main()
