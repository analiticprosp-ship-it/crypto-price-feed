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

if __name__=='__main__':unittest.main()
