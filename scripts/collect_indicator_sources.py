#!/usr/bin/env python3
"""Sequential, isolated research collection. No trading or portfolio writes."""
import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
from html.parser import HTMLParser
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
    weekly = series in ('NFCI','ANFCI','WALCL','WTREGEN','WRESBAL')
    monthly = series in ('CPIAUCSL','CPILFESL','PCEPI','PCEPILFE','INDPRO','PAYEMS','UNRATE')
    return {'observed_at_date': rows[-1][0], 'value': rows[-1][1],
            'previous_observation': {'date': rows[-2][0], 'value': rows[-2][1]} if len(rows)>1 else None,
            'daily_five_observation_baseline': {'date': rows[-6][0], 'value': rows[-6][1]} if len(rows)>5 and not weekly and not monthly else None,
            'frequency': 'MONTHLY' if monthly else 'WEEKLY' if weekly else 'DAILY',
            'unit': 'INDEX_LEVEL_NOT_INFLATION_PERCENT' if series in ('CPIAUCSL','CPILFESL','PCEPI','PCEPILFE') else 'FRED_SERIES_NATIVE_UNIT',
            'month_over_month_pct': 100*(rows[-1][1]/rows[-2][1]-1) if monthly and len(rows)>1 and series not in ('UNRATE',) else None,
            'year_over_year_pct': 100*(rows[-1][1]/rows[-13][1]-1) if monthly and len(rows)>12 and series not in ('UNRATE',) else None,
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

def interpolate(points, target):
    points=sorted(points)
    for x,y in points:
        if abs(x-target)<1e-12:return y
    for (x,a),(z,b) in zip(points,points[1:]):
        if x<target<z:return a+(b-a)*(target-x)/(z-x)
    return None

def option_surface(rows, now_ms):
    groups={}
    for r in rows:
        try:
            parts=r['instrument_name'].split('-')
            expiry=datetime.strptime(parts[1],'%d%b%y').replace(hour=8,tzinfo=timezone.utc).timestamp()*1000
            days=(expiry-now_ms)/(24*HOUR); t=days/365
            k=finite(parts[2]); f=finite(r['underlying_price']); vol=finite(r['mark_iv'])/100
            if min(days,k,f,vol)<=0 or finite(r['open_interest'])<=0:continue
            bid=r.get('bid_price');ask=r.get('ask_price')
            if bid is None or ask is None or not 0<finite(bid)<=finite(ask):continue
            d1=(math.log(f/k)+.5*vol*vol*t)/(vol*math.sqrt(t))
            delta=.5*(1+math.erf(d1/math.sqrt(2)))
            side=parts[-1];absdelta=delta if side=='C' else 1-delta
            g=groups.setdefault(days,{'atm':[],'P':[],'C':[]})
            g['atm'].append((math.log(k/f),vol))
            g[side].append((absdelta,vol))
        except (KeyError,ValueError,TypeError,IndexError):continue
    expiries={}
    for days,g in groups.items():
        # Average call/put mark IV at duplicate moneyness before ATM interpolation.
        values={}
        for x,v in g['atm']:values.setdefault(x,[]).append(v)
        atm=interpolate([(x,sum(v)/len(v)) for x,v in values.items()],0)
        p=interpolate(g['P'],.25);c=interpolate(g['C'],.25)
        if None not in (atm,p,c):expiries[days]={'atm':atm,'put25':p,'call25':c}
    targets={}
    for target in (7,30):
        legs={}
        for leg in ('atm','put25','call25'):
            variance=interpolate([(d,v[leg]**2*d/365) for d,v in expiries.items()],target)
            legs[leg]=math.sqrt(variance/(target/365))*100 if variance is not None and variance>=0 else None
        targets[str(target)+'d']={'atm_iv_percent':legs['atm'],'put25_iv_percent':legs['put25'],
            'call25_iv_percent':legs['call25'],'put_minus_call_25d_pp':legs['put25']-legs['call25'] if None not in (legs['put25'],legs['call25']) else None}
    return {'method':'MODEL_BLACK76_UNDISCOUNTED_FORWARD_DELTA_MARK_IV; delta-linear legs; maturity-total-variance interpolation; no extrapolation',
            'quality':'MODEL_ESTIMATE_NOT_PROVIDER_QUOTED_SKEW','two_sided_positive_oi_filter':True,
            'valid_expiries':len(expiries),'tenors':targets}

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
            'iv_skew':option_surface(rows,now_ms),
            'skew_status':'MODEL_ESTIMATE_SEPARATE_FROM_PROVIDER_METRIC',
            'gamma_status':'DEALER_POSITION_SIGN_UNOBSERVABLE', 'not_dealer_gex':True}

def stable(d):
    rows = sorted(d,key=lambda r:int(r['date']))
    rows = [r for r in rows if datetime.fromtimestamp(int(r['date']),timezone.utc).date() < utc().date()]
    r = rows[-1]
    val = finite(r['totalCirculatingUSD']['peggedUSD'])
    return {'observed_at':iso(int(r['date'])*1000),'value_usd':val,
            'definition':'DefiLlama totalCirculatingUSD.peggedUSD; do not mix with nominal circulating',
            'day_completed':True}

class TableText(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.cells=None; self.text=None; self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag=='tr': self.cells=[]
        if tag in ('td','th') and self.cells is not None: self.text=[]
    def handle_data(self,data):
        if self.text is not None:self.text.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cells is not None and self.text is not None:
            self.cells.append(''.join(self.text).strip()); self.text=None
        if tag=='tr' and self.cells is not None:
            self.rows.append(self.cells);self.cells=None

def etf(text):
    p=TableText();p.feed(text);rows={};partial=[]
    for r in p.rows:
        if not r:continue
        try:date=datetime.strptime(r[0],'%d %b %Y').date()
        except ValueError:continue
        if date>=utc().date():continue
        try:
            vals=[]
            for v in r[1:]:
                v=v.replace(',','').replace('−','-').strip()
                if v in ('','-','–','—'):raise ValueError('unreported fund')
                vals.append(-finite(v[1:-1]) if v.startswith('(') and v.endswith(')') else finite(v))
            if len(vals)<3 or abs(sum(vals[:-1])-vals[-1])>max(.5,len(vals)*.06):
                raise ValueError('fund total mismatch')
            rows[date.isoformat()]=vals[-1]
        except ValueError:partial.append(date.isoformat())
    if not rows:raise ValueError('no verified ETF totals')
    dates=sorted(rows);latest=dates[-1]
    return {'observed_at_date':latest,'net_flow_million_usd':rows[latest],
            'last_five_reported_sessions':{d:rows[d] for d in dates[-5:]},
            'five_session_sum_million_usd':sum(rows[d] for d in dates[-5:]) if len(dates)>=5 else None,
            'newer_partial_dates':sorted(d for d in partial if d>latest),
            'revision_policy':'LATEST_REVISED_DESCRIPTIVE_NOT_PIT','available_at':None}

def rwa(text):
    m=re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',text,re.S)
    if not m:raise ValueError('missing RWA structured payload')
    p=json.loads(m[1])['props']['pageProps']
    dates=re.findall(r'as of (?:<!-- -->)?(\d{1,2}/\d{1,2}/\d{4})',text)
    if not dates:raise ValueError('RWA date not found')
    date=datetime.strptime(dates[0],'%m/%d/%Y').date().isoformat()
    agg={r['label']:{'value':finite(r['value']),'change':r.get('percentChange')} for r in p['aggregates']}
    if not {'Distributed Asset Value','Represented Asset Value'}<=set(agg):
        raise ValueError('RWA definitions changed')
    return {'observed_at_date':date,'aggregates':agg,'not_additive':True,
            'five_business_day_comparison':'ACCUMULATING_SAME_DEFINITION_SNAPSHOTS',
            'seven_day_netflows_ex_stablecoins':p.get('netFlows',{}).get('seven_days'),
            'snapshot_not_completed_day':date>=utc().date().isoformat()}

def bitview(d,dates):
    if d.get('index')!='day1' or dates.get('index')!='day1' or d.get('start')!=dates.get('start') or d.get('end')!=dates.get('end') or len(d['data'])!=len(dates['data']):
        raise ValueError('Bitview date alignment mismatch')
    rows=[(date,finite(v)) for date,v in zip(dates['data'],d['data']) if v is not None and date<utc().date().isoformat()]
    if not rows:raise ValueError('no closed onchain day')
    return {'observed_at_date':rows[-1][0],'value':rows[-1][1],'day_completed':True,
            'provider':'Bitview/BRK','not_entity_adjusted':True,'lth_cutoff_days':150,
            'provider_parity':'INDEPENDENT_NOT_GLASSNODE_OR_CRYPTOQUANT',
            'daily_history':dict(rows),'computation_version':d.get('version')}

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
        result.append(('FRED_'+series,'https://fred.stlouisfed.org/graph/fredgraph.csv?id='+series+'&cosd='+(utc()-timedelta(days=550)).date().isoformat(),'fred:'+series))
    for ticker in ('SPY','QQQ','IWM','SOXX','RSP','HYG','LQD','COIN','MSTR','HOOD','DX-Y.NYB','^VIX','CL=F'):
        result.append(('YAHOO_'+ticker,'https://query1.finance.yahoo.com/v8/finance/chart/'+quote(ticker,safe='')+'?range=1mo&interval=1d','yahoo'))
    result.append(('stablecoins','https://stablecoins.llama.fi/stablecoincharts/all','stable'))
    # Fetch primary pages too, but don't label unparsed HTML a verified indicator.
    for key,url in (('ETF_BTC','https://farside.co.uk/btc/'),('ETF_ETH','https://farside.co.uk/eth/'),('RWA','https://app.rwa.xyz/networks'),('ISM','https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/'),('APPARENT_DEMAND','https://cryptoquant.com/asset/btc/chart/network-indicator/apparent-demand')):
        result.append((key,url,'etf' if key.startswith('ETF_') else 'rwa' if key=='RWA' else 'page'))
    for series in ['date', 'lth_supply', 'sth_supply', 'circulating_supply', 'balance_1_to_10_btc_supply', 'balance_1_to_10_sats_supply', 'balance_100_to_1k_btc_supply', 'balance_10_to_100_btc_supply', 'balance_1k_to_10k_btc_supply', 'balance_over_100k_btc_supply', 'balance_100_to_1k_sats_supply', 'balance_10_to_100_sats_supply', 'balance_1k_to_10k_sats_supply', 'balance_1m_to_10m_sats_supply', 'balance_100k_to_1m_sats_supply', 'balance_10k_to_100k_btc_supply', 'balance_10k_to_100k_sats_supply', 'balance_10m_to_100m_sats_supply', 'age_1d_to_1w_supply', 'age_1h_to_1d_supply', 'age_1m_to_2m_supply', 'age_1w_to_1m_supply', 'age_2m_to_3m_supply', 'age_2y_to_3y_supply', 'age_3m_to_4m_supply', 'age_3y_to_4y_supply', 'age_4m_to_5m_supply', 'age_4y_to_5y_supply', 'age_5m_to_6m_supply', 'age_5y_to_6y_supply', 'age_6m_to_9m_supply', 'age_6y_to_7y_supply', 'age_7y_to_8y_supply', 'age_9m_to_1y_supply', 'age_over_15y_supply', 'age_under_1h_supply', 'age_18m_to_2y_supply', 'age_1y_to_18m_supply', 'age_8y_to_10y_supply', 'age_10y_to_12y_supply', 'age_12y_to_15y_supply', 'age_1d_to_1w_realized_cap', 'age_1h_to_1d_realized_cap', 'age_1m_to_2m_realized_cap', 'age_1w_to_1m_realized_cap', 'age_2m_to_3m_realized_cap', 'age_2y_to_3y_realized_cap', 'age_3m_to_4m_realized_cap', 'age_3y_to_4y_realized_cap', 'age_4m_to_5m_realized_cap', 'age_4y_to_5y_realized_cap', 'age_5m_to_6m_realized_cap', 'age_5y_to_6y_realized_cap', 'age_6m_to_9m_realized_cap', 'age_6y_to_7y_realized_cap', 'age_7y_to_8y_realized_cap', 'age_9m_to_1y_realized_cap', 'age_over_15y_realized_cap', 'age_under_1h_realized_cap', 'age_18m_to_2y_realized_cap', 'age_1y_to_18m_realized_cap', 'age_8y_to_10y_realized_cap', 'age_10y_to_12y_realized_cap', 'age_12y_to_15y_realized_cap']:
        result.append(('BRK_'+series,'https://bitview.space/api/series/'+series+'/day1?start='+(utc()-timedelta(days=14)).date().isoformat()+'&end='+utc().date().isoformat(),'bitview_dates' if series=='date' else 'bitview'))
    return result

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    started = utc(); rid = started.strftime('%Y%m%dT%H%M%S%fZ')
    run = OUT/'runs'/rid; run.mkdir(parents=True)
    results = []
    dates={}
    for key,url,kind in definitions():
        item = {'key':key,'url':url,'started_at':utc().isoformat(),'status':'FAILED','available_at':None}
        try:
            req = urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; IndicatorResearchCollector/1.0)','Accept':'application/json,text/csv,text/html'})
            with urllib.request.urlopen(req,timeout=12) as response:
                raw = response.read(8*1024*1024+1)
                item['http_status'] = response.status
            if kind=='oi':
                first=json.loads(raw); initial=okx(first)
                next_url=url+'&end='+str(min(int(r[0]) for r in initial))
                with urllib.request.urlopen(urllib.request.Request(next_url,headers={'User-Agent':'Mozilla/5.0'}),timeout=12) as response:
                    second_raw=response.read(1024*1024)
                second=okx(json.loads(second_raw))
                merged={int(r[0]):r for r in initial+second}
                first['data']=[merged[t] for t in sorted(merged,reverse=True)]
                raw=json.dumps(first).encode()
                item.update(pagination_urls=[url,next_url],stored_payload='MERGED_PROVIDER_PAGES')
            if len(raw)>8*1024*1024:
                raise ValueError('response size limit')
            name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in key)+'.raw'
            if len(raw)>1000000:
                name+='.gz';(run/name).write_bytes(gzip.compress(raw,mtime=0))
            else:(run/name).write_bytes(raw)
            item.update(raw_file=name,sha256=hashlib.sha256(raw).hexdigest(),retrieved_at=utc().isoformat())
            now_ms = int(time.time()*1000)
            txt = raw.decode('utf-8-sig')
            if re.search(r'captcha_form|verify you are human|checking your browser',txt,re.I):
                item.update(status='ACCESS_BLOCKED',reason='PROVIDER_HUMAN_VERIFICATION_REQUIRED')
                raise ValueError('provider access block; no bypass attempted')
            if kind=='page':
                item.update(status='FETCHED_UNPARSED',reason='HTML_NOT_A_VERIFIED_NUMERIC_INDICATOR')
            else:
                d = txt if kind.startswith('fred:') or kind in ('etf','rwa') else json.loads(txt)
                if kind=='spot': value = closed_flow(d,now_ms)
                elif kind=='oi': value = oi_history(d,now_ms)
                elif kind=='funding': value = funding(d,now_ms)
                elif kind=='options': value = options(d,now_ms)
                elif kind=='yahoo': value = yahoo(d)
                elif kind=='stable': value = stable(d)
                elif kind=='etf': value = etf(txt)
                elif kind=='rwa': value = rwa(txt)
                elif kind=='bitview_dates':
                    dates=d;value={'status':'DATE_ALIGNMENT_INDEX','start':d['start'],'end':d['end']}
                elif kind=='bitview':value=bitview(d,dates)
                elif kind.startswith('candles:'): value = candles(d,now_ms,kind.split(':')[1])
                elif kind.startswith('fred:'): value = fred(d,kind.split(':')[1])
                else: raise ValueError('unsupported parser')
                item.update(status='COLLECTED_VALIDATED',value=value)
        except Exception as e:
            item['reason'] = type(e).__name__+': '+str(e)[:200]
        item['finished_at'] = utc().isoformat()
        results.append(item)
        print(key,item['status'],flush=True)
    for key,reason in [('TV_MFI','BROWSER_CAPTURE_REQUIRED'),('TV_BIG_GUY_BURJ','BROWSER_CAPTURE_REQUIRED'),('TV_LUXALGO','BROWSER_CAPTURE_REQUIRED'),('ONCHAIN_ENTITY_FLOWS','PROVIDER_ACCESS_NOT_CONFIGURED'),('US_SPOT_CVD','CONTINUOUS_TRADE_COVERAGE_NOT_CONFIGURED'),('ACTUAL_STOCK_BREADTH','CONSTITUENT_SERIES_NOT_CONFIGURED')]:
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
