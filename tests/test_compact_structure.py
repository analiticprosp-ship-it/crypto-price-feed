import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_market_summary import valid,aligned_rs,build,TFS,SYMS
class TestCompact(unittest.TestCase):
 def test_unclosed_rejected(self):
  p=TFS['1H']; rows=[dict(t=i*p,o=100,h=110,l=90,c=101,v=10) for i in range(3)]
  self.assertEqual(len(valid(rows,'1H',2*p)),2)
 def test_rs_requires_matching_period(self):
  a=[dict(t=0,c=100),dict(t=TFS['4H'],c=105)]
  b=[dict(t=0,c=100),dict(t=TFS['4H'],c=101)]
  self.assertAlmostEqual(aligned_rs(a,b,'4H')['rsPctPoints'],4)
  self.assertIsNone(aligned_rs(a,b[:-1],'4H'))
 def test_detector_extended_common_universe(self):
  self.assertTrue({'AVAX','APT','NEAR','INJ'}<=set(SYMS))
  self.assertEqual(len(set(SYMS)),len(SYMS))
  self.assertIn('DOT',SYMS)
 def test_closed_15m_bar_is_present_in_compact(self):
  p=TFS['15m'];end=10*p
  # A valid closed 15m bar cannot be fabricated from a future/unclosed bar.
  def sample(primary,sym,tf,now):
   period=TFS[tf]
   return dict(venue='OKX-primary',candles=[
    dict(t=k*period,o=100,h=110,l=90,c=101,v=10)
    for k in range(9) if (k+1)*period<=now],attempts=[])
  d=build({},['SOL'],TFS['1D']*10,sample)
  bar=d['instruments']['SOL']['15m']['lastClosedBar']
  self.assertEqual(bar['endMs'],bar['t']+p)
  self.assertLessEqual(bar['endMs'],TFS['1D']*10)
 def test_no_fabricated_rs(self):
  def empty(primary,sym,tf,now):return dict(venue=None,candles=[],attempts=['no data'])
  d=build({},['SOL'],TFS['1D']*10,empty)
  self.assertIsNone(d['instruments']['SOL']['4H']['rsVsBTC'])
if __name__=='__main__':unittest.main()
