#!/usr/bin/env python3
"""Sequential, isolated research collection. No trading or portfolio writes."""
import csv
import hashlib
import io
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/indicator_sources_v1'
HOUR = 3600000

def utc():
    return datetime.now(timezone.utc)

def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()

def finite(v):
    n = float(v)
    if not math.isfinite(n):
        raise ValueError('nonfinite')
    return n

def okx(d):
    if d.get('code') != '0' or not d.get('data'):
        raise ValueError('OKX nonzero code or empty data')
    return d['data']

def closed_flow(d, now_ms):
    # OKX Rubik timestamp is the bucket start. Exclude unfinished hour.
    rows = {}
    for r in okx(d):
        t = int(r[0]); sell, buy = finite(r[1]), finite(r[2])
        if t % HOUR or min(sell, buy) < 0:
            raise ValueError('bad hourly spot bucket')
        if t + HOUR <= now_ms:
            if t in rows:
                raise ValueError('duplicate bucket')
            rows[t] = (sell, buy)
    if not rows:
        raise ValueError('no completed spot hours')
    end = max(rows) + HOUR
    start = end - 24 * HOUR
    if any(t not in rows for t in range(start, end, HOUR)):
        raise ValueError('gapped 24h spot flow')
    buy = sum(rows[t][1] for t in range(start, end, HOUR))
    sell = sum(rows[t][0] for t in range(start, end, HOUR))
    if now_ms - end > 2 * HOUR:
        raise ValueError('stale spot history')
    return {'observed_at': iso(end), 'window_start': iso(start), 'window_end': iso(end),
            'market': 'SPOT', 'venue': 'OKX', 'unit': 'base_asset',
            'buy': buy, 'sell': sell, 'delta': buy - sell,
            'cvd_definition': 'sum(buy-sell), reset at window_start', 'closed_hours': 24,
            'not_global_flow': True}

def oi_history(d, now_ms):
    rows = sorted((int(r[0]), [finite(v) for v in r[1:4]]) for r in okx(d))
    rows = [r for r in rows if r[0] <= now_ms]
    t, vals = rows[-1]
    if now_ms - t > 2 * HOUR:
        raise ValueError('stale OI')
    hist = dict(rows)
    base_t = t - 120 * HOUR
    baseline = hist.get(base_t)
    return {'observed_at': iso(t), 'venue': 'OKX', 'market': 'PERPETUAL',
            'contracts': vals[0], 'coins': vals[1], 'usd': vals[2],
            'baseline_120h': {'observed_at': iso(base_t), 'contracts': baseline[0],
                'delta_contracts_pct': 100*(vals[0]/baseline[0]-1),
                'delta_usd_pct': 100*(vals[2]/baseline[2]-1)} if baseline else None,
            'baseline_status': 'EXACT' if baseline else 'MISSING_EXACT_POINT',
            'not_directional_long_short': True}

def funding(d, now_ms):
    rows = [r for r in okx(d) if int(r['fundingTime']) <= now_ms]
    r = max(rows, key=lambda r: int(r['fundingTime']))
    t = int(r['fundingTime'])
    if now_ms-t > 10*HOUR:
        raise ValueError('stale funding')
    return {'observed_at': iso(t), 'realized_percent_per_period': finite(r['fundingRate'])*100,
            'venue': 'OKX', 'instId': r['instId']}

def candles(d, now_ms, tf):
    span = {'4H': 4*HOUR, '1Dutc': 24*HOUR}[tf]
    rows = sorted((int(r[0]), [finite(v) for v in r[1:6]]) for r in okx(d)
                  if r[-1] == '1' and int(r[0])+span <= now_ms)
    t, v = rows[-1]
    if now_ms-(t+span) > span+20*60000:
        raise ValueError('stale candle')
    return {'observed_at': iso(t+span), 'bar_open': iso(t), 'bar_close': iso(t+span),
            'closed': True, 'open': v[0], 'high': v[1], 'low': v[2], 'close': v[3],
            'volume_contracts': v[4], 'market': 'PERPETUAL', 'venue': 'OKX',
            'not_indicator_signal': True}

def fred(text, series):
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for r in reader:
        val = r.get(series)
        date = r.get('observation_date') or r.get('DATE')
        if date and val not in (None, '.', ''):
            rows.append((date, finite(val)))
    if not rows:
        raise ValueError('no FRED numeric observations')
    rows.sort()
    # Latest revised descriptive series, not a point-in-time historical vintage.
    return {'observed_at_date': rows[-1][0], 'value': rows[-1][1],
            'previous_observation': {'date': rows[-2][0], 'value': rows[-2][1]} if len(rows)>1 else None,
            'daily_five_observation_baseline': {'date': rows[-6][0], 'value': rows[-6][1]} if len(rows)>5 else None,
            'series': series, 'revision_policy': 'LATEST_REVISED_DESCRIPTIVE_NOT_PIT',
            'available_at': None, 'publication_time_verified': False,
            'freshness': 'LAST_PUBLISHED_OBSERVATION_AGE_EXPLICIT',
            'age_calendar_days': (utc().date()-datetime.fromisoformat(rows[-1][0]).date()).days}

def yahoo(d):
    x = d['chart']['result'][0]
    q = x['indicators']['quote'][0]
    meta = x['meta']
    rows = [(int(t), finite(v)) for t,v in zip(x['timestamp'],q['close']) if v is not None]
    # Daily current-session candle is not declared a final close.
    tz = timezone(timedelta(seconds=int(meta.get('gmtoffset', 0))))
    today = utc().astimezone(tz).date()
    rows = [r for r in rows if datetime.fromtimestamp(r[0],tz).date() < today]
    if len(rows)<6:
        raise ValueError('fewer than six completed sessions')
    return {'observed_at': iso(rows[-1][0]*1000), 'session_date': datetime.fromtimestamp(rows[-1][0],tz).date().isoformat(),
            'close': rows[-1][1], 'baseline_session_date': datetime.fromtimestamp(rows[-6][0],tz).date().isoformat(),
            'baseline_close': rows[-6][1], 'return_5_sessions_pct': 100*(rows[-1][1]/rows[-6][1]-1),
            'exchange_timezone': meta.get('exchangeTimezoneName'), 'timestamp_is_session_open': True,
            'freshness': 'LAST_COMPLETED_SESSION', 'breadth_not_proven': True}

def options(d, now_ms):
    rows = d.get('result')
    if not isinstance(rows,list) or not rows:
        raise ValueError('no Deribit option chain')
    call = put = 0.0
    by_expiry = {}
    timestamps = []
    for r in rows:
        name = r['instrument_name']; parts = name.split('-')
        exp = datetime.strptime(parts[1], '%d%b%y').replace(hour=8,tzinfo=timezone.utc)
        if exp.timestamp()*1000 <= now_ms:
            continue
        oi = finite(r['open_interest'])
        if oi < 0:
            raise ValueError('negative option OI')
        call += oi if parts[-1]=='C' else 0
        put += oi if parts[-1]=='P' else 0
        by_expiry[exp.isoformat()] = by_expiry.get(exp.isoformat(),0)+oi
        timestamps.append(int(r['creation_timestamp']))
    if not timestamps or now_ms-max(timestamps)>20*60000:
        raise ValueError('stale option snapshot')
    return {'observed_at': iso(max(timestamps)), 'venue':'Deribit', 'instruments':len(rows),
            'put_oi':put,'call_oi':call,'put_call_oi_ratio':put/call if call else None,
            'expiry_oi':by_expiry, 'mark_iv_chain_saved':True,
            'skew_status':'RAW_CHAIN_COLLECTED_MODEL_NOT_VALIDATED',
            'gamma_status':'DEALER_POSITION_SIGN_UNOBSERVABLE', 'not_dealer_gex':True}

def stable(d):
    rows = sorted(d,key=lambda r:int(r['date']))
    rows = [r for r in rows if datetime.fromtimestamp(int(r['date']),timezone.utc).date() < utc().date()]
    r = rows[-1]
    val = finite(r['totalCirculatingUSD']['peggedUSD'])
    return {'observed_at':iso(int(r['date'])*1000),'value_usd':val,
            'definition':'DefiLlama totalCirculatingUSD.peggedUSD; do not mix with nominal circulating',
            'day_completed':True}

def definitions():
    result = []
    for asset in ('BTC','ETH'):
        inst = asset+'-USDT-SWAP'
        base = 'https://www.okx.com/api/v5/'
        result += [
            (asset+'_funding',base+'public/funding-rate-history?instId='+inst+'&limit=100','funding'),
            (asset+'_oi',base+'rubik/stat/contracts/open-interest-history?instId='+inst+'&period=1H','oi'),
            (asset+'_spot_cvd',base+'rubik/stat/taker-volume?ccy='+asset+'&instType=SPOT&period=1H','spot'),
            (asset+'_options','https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency='+asset+'&kind=option','options')]
        for tf in ('4H','1Dutc'):
            result.append((asset+'_'+tf,base+'market/candles?instId='+inst+'&bar='+tf+'&limit=100','candles:'+tf))
    for series in ('DGS2','DGS10','DFII10','DTWEXBGS','BAMLH0A0HYM2','NFCI','ANFCI','WALCL','WTREGEN','RRPONTSYD','WRESBAL','CPIAUCSL','CPILFESL','PCEPI','PCEPILFE','INDPRO','PAYEMS','UNRATE','DCOILWTICO'):
        result.append(('FRED_'+series,'https://fred.stlouisfed.org/graph/fredgraph.csv?id='+series+'&cosd='+(utc()-timedelta(days=150)).date().isoformat(),'fred:'+series))
    for ticker in ('SPY','QQQ','IWM','SOXX','RSP','HYG','LQD','COIN','MSTR','HOOD','DX-Y.NYB','^VIX','CL=F'):
        result.append(('YAHOO_'+ticker,'https://query1.finance.yahoo.com/v8/finance/chart/'+quote(ticker,safe='')+'?range=1mo&interval=1d','yahoo'))
    result.append(('stablecoins','https://stablecoins.llama.fi/stablecoincharts/all','stable'))
    # Fetch primary pages too, but don't label unparsed HTML a verified indicator.
    for key,url in (('ETF_BTC','https://farside.co.uk/btc/'),('ETF_ETH','https://farside.co.uk/eth/'),('RWA','https://app.rwa.xyz/networks'),('ISM','https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/'),('APPARENT_DEMAND','https://cryptoquant.com/asset/btc/chart/network-indicator/apparent-demand')):
        result.append((key,url,'page'))
    return result

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    started = utc(); rid = started.strftime('%Y%m%dT%H%M%S%fZ')
    run = OUT/'runs'/rid; run.mkdir(parents=True)
    results = []
    for key,url,kind in definitions():
        item = {'key':key,'url':url,'started_at':utc().isoformat(),'status':'FAILED','available_at':None}
        try:
            req = urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; IndicatorResearchCollector/1.0)','Accept':'application/json,text/csv,text/html'})
            with urllib.request.urlopen(req,timeout=12) as response:
                raw = response.read(8*1024*1024+1)
                item['http_status'] = response.status
            if len(raw)>8*1024*1024:
                raise ValueError('response size limit')
            name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in key)+'.raw'
            (run/name).write_bytes(raw)
            item.update(raw_file=name,sha256=hashlib.sha256(raw).hexdigest(),retrieved_at=utc().isoformat())
            now_ms = int(time.time()*1000)
            txt = raw.decode('utf-8-sig')
            if kind=='page':
                item.update(status='FETCHED_UNPARSED',reason='HTML_NOT_A_VERIFIED_NUMERIC_INDICATOR')
            else:
                d = json.loads(txt) if not kind.startswith('fred:') else txt
                if kind=='spot': value = closed_flow(d,now_ms)
                elif kind=='oi': value = oi_history(d,now_ms)
                elif kind=='funding': value = funding(d,now_ms)
                elif kind=='options': value = options(d,now_ms)
                elif kind=='yahoo': value = yahoo(d)
                elif kind=='stable': value = stable(d)
                elif kind.startswith('candles:'): value = candles(d,now_ms,kind.split(':')[1])
                elif kind.startswith('fred:'): value = fred(d,kind.split(':')[1])
                else: raise ValueError('unsupported parser')
                item.update(status='COLLECTED_VALIDATED',value=value)
        except Exception as e:
            item['reason'] = type(e).__name__+': '+str(e)[:200]
        item['finished_at'] = utc().isoformat()
        results.append(item)
        print(key,item['status'],flush=True)
    for key,reason in [('TV_MFI','BROWSER_CAPTURE_REQUIRED'),('TV_BIG_GUY_BURJ','BROWSER_CAPTURE_REQUIRED'),('TV_LUXALGO','BROWSER_CAPTURE_REQUIRED'),('ONCHAIN_ENTITY_FLOWS','PROVIDER_ACCESS_NOT_CONFIGURED'),('ONCHAIN_COHORTS','ADAPTER_PENDING'),('US_SPOT_CVD','CONTINUOUS_TRADE_COVERAGE_NOT_CONFIGURED'),('ACTUAL_STOCK_BREADTH','CONSTITUENT_SERIES_NOT_CONFIGURED')]:
        results.append({'key':key,'status':'NOT_CONNECTED','reason':reason})
    packet = {'schema':'indicator-sources-v1','run_id':rid,'started_at':started.isoformat(),
              'finished_at':utc().isoformat(),'sequential':True,'research_only':True,
              'last_good_is_not_current':True,'all_sources_connected':False,'sources':results}
    payload = json.dumps(packet,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    (run/'receipt.json').write_text(payload)
    tmp = OUT/'latest.tmp'; tmp.write_text(payload); tmp.replace(OUT/'latest.json')
    # Byte readback verifies our output; HTTP success alone never passes a source.
    assert json.loads((OUT/'latest.json').read_text())['run_id']==rid
    print('COLLECTION_WRITE_READBACK_VERIFIED',rid,flush=True)

if __name__=='__main__':
    main()
