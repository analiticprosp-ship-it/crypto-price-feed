#!/usr/bin/env python3
"""P3 historical funding archives: public publisher ZIP+CHECKSUM, no trading."""
import base64,csv,datetime as dt,hashlib,io,json,math,os,urllib.request,zipfile
from pathlib import Path
from collect_primary_spot import EVENTS
ROOT=Path(__file__).resolve().parent
def fetch(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'P3-funding-shadow/1.0'}),timeout=25) as r:return r.read()
def main():
 now=dt.datetime.now(dt.timezone.utc);run=now.strftime('%Y%m%dT%H%M%SZ')+'_'+os.environ.get('GITHUB_RUN_ID','local');out=ROOT/'funding_runs'/run;out.mkdir(parents=True,exist_ok=False)
 wanted={}
 for eid,t in EVENTS:
  d=dt.datetime.fromisoformat(t)
  for off in [-3,0,3]:
   month=(d+dt.timedelta(days=off)).strftime('%Y-%m')
   for symbol in ['BTCUSDT','ETHUSDT']:wanted.setdefault((symbol,month),set()).add(eid)
 manifest={'run_id':run,'retrieved_at':now.isoformat(),'market':'BINANCE_USDM_PERPETUAL','not_spot':True,'status':'ATTEMPTED_WITH_EXPLICIT_GAPS','records':[],'no_trade_changes':True,'frozen_btc72h_unchanged':True}
 for (symbol,month),events in sorted(wanted.items()):
  name=f'{symbol}-fundingRate-{month}.zip';url=f'https://data.binance.vision/data/futures/um/monthly/fundingRate/{symbol}/{name}';rec={'symbol':symbol,'month':month,'events':sorted(events),'url':url,'first_available_historically':None}
  try:
   raw=fetch(url);assert len(raw)<2_000_000,'OVERSIZED';checksum=fetch(url+'.CHECKSUM');expected=checksum.decode().split()[0];actual=hashlib.sha256(raw).hexdigest();assert actual==expected,'CHECKSUM_MISMATCH'
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    assert z.testzip() is None,'ZIP_CRC';members=[n for n in z.namelist() if n.endswith('.csv')];assert len(members)==1,'ZIP_SCHEMA';content=z.read(members[0]).decode('utf-8-sig')
   rows=list(csv.DictReader(io.StringIO(content)));required={'calc_time','funding_interval_hours','last_funding_rate'};assert rows and required.issubset(rows[0]),'UNATTESTED_COLUMNS'
   vals=[]
   for r in rows:
    ts=int(r['calc_time']);hours=float(r['funding_interval_hours']);rate=float(r['last_funding_rate']);assert 0<hours<=24 and math.isfinite(rate);assert 10**11<ts<10**14,'EPOCH_UNITS'
    vals.append({'settlement_ms':ts,'settlement_utc':dt.datetime.fromtimestamp(ts/1000,dt.timezone.utc).isoformat(),'period_hours':hours,'realized_rate_decimal':rate,'percent_per_period':rate*100,'linear_percent_per_hour':rate*100/hours})
   (out/(name+'.evidence.json')).write_text(json.dumps({'zip_base64':base64.b64encode(raw).decode(),'zip_sha256':actual,'checksum_text':checksum.decode(),'csv':content,'source_url':url,'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat()},indent=2))
   normalized=name+'.normalized.json';(out/normalized).write_text(json.dumps(vals,indent=2));rec.update(status='COLLECTED_PUBLISHER_CHECKSUM_AND_CRC_VERIFIED',rows=len(vals),sha256=actual,normalized_file=normalized)
  except Exception as e:rec.update(status='UNAVAILABLE_NOT_ZERO',error_type=type(e).__name__,error=str(e)[:200])
  manifest['records'].append(rec);print(json.dumps(rec),flush=True)
 # Short public API supplement for the unavailable November monthly funding archive.
 supplement=[]
 for symbol in ['BTCUSDT','ETHUSDT']:
  url='https://fapi.binance.com/fapi/v1/fundingRate?symbol='+symbol+'&startTime=1793045100000&endTime=1793563500000&limit=1000'
  rec={'symbol':symbol,'url':url,'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'ATTEMPTED','funding_interval_hours':None,'note':'API does not attest historical interval duration; no interval inferred automatically'}
  try:
   raw=fetch(url);data=json.loads(raw);assert isinstance(data,list) and data,'EMPTY_OR_ERROR';name=symbol+'_api_supplement.raw.json';(out/name).write_bytes(raw);rec.update(status='COLLECTED_RAW_NOT_INTERVAL_NORMALIZED',file=name,sha256=hashlib.sha256(raw).hexdigest(),rows=len(data))
  except Exception as e:rec.update(status='UNAVAILABLE_NOT_ZERO',error_type=type(e).__name__,error=str(e)[:200])
  supplement.append(rec)
 manifest['api_supplement']=supplement
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({'run':run,'ok':sum(r['status'].startswith('COLLECTED') for r in manifest['records']),'attempted':len(manifest['records'])}))
if __name__=='__main__':main()
