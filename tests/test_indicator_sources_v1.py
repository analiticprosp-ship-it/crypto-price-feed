import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('collector',Path(__file__).parents[1]/'scripts/collect_indicator_sources.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

class SourceGuards(unittest.TestCase):
    def flow(self):
        return {'code':'0','data':[[str(i*c.HOUR),'2','3'] for i in range(25)]}
    def test_excludes_current_hour(self):
        v=c.closed_flow(self.flow(),24*c.HOUR+1000)
        self.assertEqual(v['delta'],24)
        self.assertEqual(v['closed_hours'],24)
    def test_rejects_gap(self):
        d=self.flow();del d['data'][12]
        with self.assertRaises(ValueError):c.closed_flow(d,24*c.HOUR+1000)
    def test_rejects_duplicate(self):
        d=self.flow();d['data'].append(d['data'][0])
        with self.assertRaises(ValueError):c.closed_flow(d,24*c.HOUR+1000)
    def test_rejects_nonfinite(self):
        with self.assertRaises(ValueError):c.finite('NaN')
    def test_does_not_use_unclosed_candle(self):
        d={'code':'0','data':[['0','1','2','1','2','4','5','6','1'],[str(4*c.HOUR),'2','3','1','3','4','5','6','0']]}
        v=c.candles(d,5*c.HOUR,'4H')
        self.assertEqual(v['close'],2)
    def test_provider_error_not_empty_signal(self):
        with self.assertRaises(ValueError):c.okx({'code':'500','data':[]})
    def test_no_surface_extrapolation(self):
        self.assertIsNone(c.interpolate([(1,.4),(3,.6)],7))
    def test_coinbase_maker_side_inversion(self):
        self.assertEqual(c.coinbase_trade_delta({'size':'2','price':'100','side':'sell'}),(2,200))
        self.assertEqual(c.coinbase_trade_delta({'size':'2','price':'100','side':'buy'}),(-2,-200))
    def test_missing_year_month_is_not_previous_available_row(self):
        csv = 'observation_date,CPIAUCSL\n2025-09-01,100\n2025-10-01,\n2025-11-01,101\n2026-09-01,104\n2026-10-01,105\n'
        v=c.fred(csv,'CPIAUCSL')
        self.assertIsNone(v['year_over_year_pct'])
        self.assertEqual(v['yoy_base_status'],'MISSING_CALENDAR_MONTH')
        self.assertAlmostEqual(v['month_over_month_pct'],100*(105/104-1))
    def test_year_over_year_uses_calendar_month_even_with_short_sample(self):
        csv = 'observation_date,PCEPI\n2025-10-01,100\n2026-10-01,104\n'
        v=c.fred(csv,'PCEPI')
        self.assertAlmostEqual(v['year_over_year_pct'],4)
        self.assertIsNone(v['month_over_month_pct'])
    def test_month_gap_does_not_create_two_month_mom(self):
        csv = 'observation_date,PCEPI\n2026-08-01,100\n2026-09-01,.\n2026-10-01,104\n'
        self.assertIsNone(c.fred(csv,'PCEPI')['month_over_month_pct'])
    def test_flat_iv_surface_has_zero_skew(self):
        from datetime import datetime,timezone
        now=datetime(2026,10,31,8,tzinfo=timezone.utc).timestamp()*1000
        rows=[]
        for expiry in ('6NOV26','13NOV26','27NOV26','25DEC26'):
            for strike in (50,70,80,90,100,110,120,140,160):
                for side in ('C','P'):
                    rows.append({'instrument_name':f'BTC-{expiry}-{strike}-{side}',
                       'underlying_price':100,'mark_iv':40,'open_interest':1,'bid_price':.01,'ask_price':.02})
        v=c.option_surface(rows,now)
        for d in ('7d','30d'):
            self.assertAlmostEqual(v['tenors'][d]['atm_iv_percent'],40)
            self.assertAlmostEqual(v['tenors'][d]['put_minus_call_25d_pp'],0)

if __name__=='__main__':unittest.main()
