import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_market_summary import valid,aligned_rs,build,TFS
class TestCompact(unittest.TestCase):
 def test_unclosed_rejected(self):
  p=TFS['1H']; rows=[dict(t=i*p,o=100,h=110,l=90,c=101,v=10) for i in range(3)]
  self.assertEqual(len(valid(rows,'1H',2*p)),2)
 def test_rs_requires_matching_period(self):
  a=[dict(t=0,c=100),dict(t=TFS['4H'],c=105)]
  b=[dict(t=0,c=100),dict(t=TFS['4H'],c=101)]
  self.assertAlmostEqual(aligned_rs(a,b,'4H')['rsPctPoints'],4)
  self.assertIsNone(aligned_rs(a,b[:-1],'4H'))
 def test_no_fabricated_rs(self):
  def empty(primary,sym,tf,now):return dict(venue=None,candles=[],attempts=['no data'])
  d=build({},['SOL'],TFS['1D']*10,empty)
  self.assertIsNone(d['instruments']['SOL']['4H']['rsVsBTC'])
if __name__=='__main__':unittest.main()
