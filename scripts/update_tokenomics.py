#!/usr/bin/env python3
"""Date-harmonized tokenomics snapshot. Never manufactures unlocks or live system prices."""
import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ASSETS = Path('tokenomics-assets.json')
EVENTS = Path('tokenomics-events.json')
OUT = Path('tokenomics.json')
HISTORY = Path('tokenomics-history.json')
CG_BASE = 'https://api.coingecko.com/api/v3/coins/markets'
WINDOWS = (7, 30, 90, 365)

def utc(t):
    return datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(timezone.utc)

def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0: return None
    return value

def supply_rows(ids):
    query=urllib.parse.urlencode({'vs_currency':'usd','ids':','.join(ids.values()),'order':'market_cap_desc',
                                 'per_page':250,'page':1,'sparkline':'false','price_change_percentage':'24h'})
    req=urllib.request.Request(CG_BASE+'?'+query,headers={'Accept':'application/json','User-Agent':'crypto-price-feed/tokenomics-1'})
    key=os.getenv('COINGECKO_DEMO_API_KEY')
    if key: req.add_header('x-cg-demo-api-key',key)
    with urllib.request.urlopen(req,timeout=35) as response:
        if response.status!=200: raise RuntimeError('CoinGecko status '+str(response.status))
        result=json.load(response)
    if not isinstance(result,list): raise ValueError('CoinGecko response is not a list')
    return {str(row.get('id')):row for row in result if isinstance(row,dict)}

def classify_events(symbol, events, now):
    eligible=[]
    for e in events:
        if e.get('symbol')!=symbol: continue
        if e.get('verification') not in ('VERIFIED_PRIMARY','DOCUMENTARY_EVENT_NO_AMOUNT'): continue
        try: at=utc(e['eventAt'])
        except (KeyError,TypeError,ValueError): continue
        if at.date()>=now.date(): eligible.append((at,e))
    views=[]; windows={}
    for at,e in eligible:
        views.append({k:e.get(k) for k in ('id','eventAt','eventType','holderGroup','amountTokens','circulatingIncreaseConfirmed',
                'saleConfirmed','timePrecision','sourceKind','sourceUrl','sourcePublishedAt','verification','notes')})
    for days in WINDOWS:
        within=[e for at,e in eligible if at.date()<=(now+timedelta(days=days)).date()]
        # VERIFIED_PRIMARY + numerical amount + confirmed circulating-supply impact only;
        # this is still a known-event MINIMUM, never the complete total unlock forecast.
        numeric=[e['amountTokens'] for e in within if e.get('verification')=='VERIFIED_PRIMARY'
                 and e.get('circulatingIncreaseConfirmed') is True and number(e.get('amountTokens')) is not None]
        windows[str(days)+'d']={'totalExpectedTokens':None,'completeness':'UNVERIFIED_COVERAGE',
                              'knownVerifiedCirculatingIncreaseMinimum':sum(numeric) if numeric else None,
                              'relevantDocumentaryEvents':len(within)}
    return views,windows

def build(now, ids, events, data, provider_error=None):
    result={'schemaVersion':'1.0.0','generatedAt':now.isoformat(),'effectiveDateUTC':now.date().isoformat(),
            'authority':'RESEARCH_ONLY_NO_SYSTEM_PRICE_NO_TRADE','primaryPriceFile':'prices.json',
            'supplyProvider':'CoinGecko coins/markets (supply fields only)',
            'supplyProviderUrl':'https://www.coingecko.com/en/api',
            'unlockMethod':'Verified documentary events only; empty schedule is NOT evidence of zero unlocks',
            'providerError':provider_error,'assets':[]}
    for ticker,coinid in ids.items():
        row=data.get(coinid) if data else None
        # Do not use CoinGecko current_price, market_cap, FDV etc. No price authority here.
        corr = isinstance(row,dict) and str(row.get('symbol','')).upper()==ticker and row.get('id')==coinid
        cir=number(row.get('circulating_supply')) if corr else None
        total=number(row.get('total_supply')) if corr else None
        maxs=number(row.get('max_supply')) if corr else None
        reported_at=row.get('last_updated') if corr else None
        # Provider last_updated is NOT guaranteed to be a per-field supply-update timestamp.
        issues=[]
        if not corr: issues.append('SOURCE_MISSING_OR_TICKER_ID_MISMATCH')
        if cir is None: issues.append('CIRCULATING_NA')
        if total is None: issues.append('TOTAL_NA')
        if cir is not None and total is not None and cir>total*1.005: issues.append('CIRCULATING_GT_TOTAL_REVIEW')
        if reported_at:
            try:
                if abs((now-utc(reported_at)).total_seconds())>48*3600: issues.append('PROVIDER_LAST_UPDATED_OLDER_THAN_48H')
            except (ValueError,TypeError): issues.append('BAD_PROVIDER_TIMESTAMP')
        ev, windows=classify_events(ticker,events,now)
        result['assets'].append({'symbol':ticker,'coingeckoId':coinid,'supplyStatus':'AVAILABLE_WITH_CAVEATS' if corr and cir is not None and not issues else 'PARTIAL_OR_NA',
            'circulatingSupply':cir,'totalSupply':total,'maxSupply':maxs,
            'lockedSupply':None,'notCirculatingByProvider':round(total-cir,8) if total is not None and cir is not None and total>=cir else None,
            'netEmission':None,'dilutionForecastPct':None,'providerLastUpdatedAt':reported_at,
            'supplyRetrievedAt':now.isoformat() if corr else None,'supplySourceUrl':f'https://www.coingecko.com/en/coins/{coinid}',
            'supplyTimestampCaveat':'providerLastUpdatedAt is general coin market update, not a field-level supply update',
            'unlockEvents':ev,'unlockWindows':windows,'issues':issues})
    return result

def main():
    now=datetime.now(timezone.utc)
    ids=json.loads(ASSETS.read_text())['coingeckoIdMap']
    if len(ids)!=15 or len(set(ids.values()))!=15: raise RuntimeError('Asset ID map MUST have 15 unique entries')
    events=json.loads(EVENTS.read_text())['events']
    seen=set()
    for e in events:
        if e.get('id') in seen or e.get('symbol') not in ids or not e.get('sourceUrl','').startswith('https://'):
            raise ValueError('Invalid curated tokenomics event')
        seen.add(e['id'])
    source_error=None
    try: source=supply_rows(ids)
    except Exception as e:
        source={};source_error=str(e)[:250]
    output=build(now,ids,events,source,source_error)
    OUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    # Append-only history; same day can contain several explicitly timestamped samples.
    try: history=json.loads(HISTORY.read_text())
    except FileNotFoundError: history={'schemaVersion':'1.0.0','snapshots':[]}
    history['snapshots'].append({'generatedAt':output['generatedAt'],'providerError':source_error,
        'supplies':[{k:a[k] for k in ('symbol','circulatingSupply','totalSupply','maxSupply','supplyStatus')} for a in output['assets']]})
    HISTORY.write_text(json.dumps(history,ensure_ascii=False,indent=2)+'\n')
    print('Tokenomics',output['generatedAt'],'available circulating',sum(x['circulatingSupply'] is not None for x in output['assets']),'/15',source_error)

if __name__=='__main__': main()
