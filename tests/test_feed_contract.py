import sys,unittest,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import update_core_prices as core
import update_tokenomics as tok

class ContractTests(unittest.TestCase):
    def test_core_age_gate(self):
        now=datetime.now(timezone.utc)
        quote={'symbol':'BTC','ok':True,'systemPrice':85000,'requestedAt':now.isoformat()}
        self.assertTrue(core.valid_quote(quote,'BTC',now))
        quote['requestedAt']=(now-timedelta(minutes=5)).isoformat()
        self.assertFalse(core.valid_quote(quote,'BTC',now))
        quote['requestedAt']=now.isoformat();quote['ok']=False
        self.assertFalse(core.valid_quote(quote,'BTC',now))
        quote['ok']=True;quote['systemPrice']=0
        self.assertFalse(core.valid_quote(quote,'BTC',now))
    def test_tokenomics_count_and_missing_values(self):
        ids=json.loads((ROOT/'tokenomics-assets.json').read_text())['coingeckoIdMap']
        events=json.loads((ROOT/'tokenomics-events.json').read_text())['events']
        self.assertEqual(len(ids),15)
        self.assertEqual(len(set(ids.values())),15)
        now=datetime(2026,10,4,4,0,tzinfo=timezone.utc)
        result=tok.build(now,ids,events,{},'mock HTTP429')
        self.assertEqual(len(result['assets']),15)
        self.assertEqual(result['providerError'],'mock HTTP429')
        for a in result['assets']:
            self.assertIsNone(a['circulatingSupply'])
            self.assertIsNone(a['unlockWindows']['7d']['totalExpectedTokens'])
            self.assertIsNone(a['unlockWindows']['30d']['knownVerifiedCirculatingIncreaseMinimum'])
            self.assertIsNone(a['netEmission'])
            self.assertIsNone(a['lockedSupply'])
        ena=next(x for x in result['assets'] if x['symbol']=='ENA')
        self.assertEqual(len(ena['unlockEvents']),2)
        self.assertEqual(ena['unlockWindows']['7d']['relevantDocumentaryEvents'],2)
        _,same_day=tok.classify_events('ENA',events,datetime(2026,10,5,12,0,tzinfo=timezone.utc))
        self.assertEqual(same_day['7d']['relevantDocumentaryEvents'],2)
        self.assertTrue(all(e['amountTokens'] is None for e in ena['unlockEvents']))
    def test_supply_is_not_price_and_never_infers_locked_supply(self):
        ids=json.loads((ROOT/'tokenomics-assets.json').read_text())['coingeckoIdMap']
        now=datetime(2026,10,4,4,0,tzinfo=timezone.utc)
        result=tok.build(now,ids,[],{'bitcoin':{
          'id':'bitcoin','symbol':'btc','circulating_supply':19800000,
          'total_supply':19900000,'max_supply':21000000,'current_price':123456,
          'last_updated':now.isoformat()}},None)
        btc=result['assets'][0]
        self.assertEqual(btc['circulatingSupply'],19800000)
        self.assertEqual(btc['notCirculatingByProvider'],100000)
        self.assertIsNone(btc['lockedSupply'])
        self.assertNotIn('currentPrice',btc)
        self.assertNotIn('systemPrice',btc)
    def test_event_unknown_amount_does_not_become_zero(self):
        now=datetime(2026,10,4,tzinfo=timezone.utc)
        source=json.loads((ROOT/'tokenomics-events.json').read_text())['events']
        _,win=tok.classify_events('ENA',source,now)
        self.assertIsNone(win['30d']['knownVerifiedCirculatingIncreaseMinimum'])
        self.assertIsNone(win['30d']['totalExpectedTokens'])

if __name__=='__main__':unittest.main()
