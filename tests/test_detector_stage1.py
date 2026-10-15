"""Stage-1 Detector feature guards: closed bars, no fabricated flow, no future OI."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_market_summary import detector_features, detector_derivatives, TFS

class TestDetectorStage1(unittest.TestCase):
    def candles(self):
        p=TFS['15m']
        bars=[dict(t=i*p,o=101.,h=104.,l=98.,c=101.,v=100.) for i in range(14)]
        return bars

    def test_sweep_reclaim_is_pattern_not_taker_proof(self):
        bars=self.candles()
        bars[-1].update(o=99.0,h=103.0,l=97.0,c=101.0)
        feat=detector_features(bars,'15m')
        self.assertEqual(feat['status'],'OHLCV_PROXY_ONLY')
        self.assertTrue(feat['localStructure']['sweptLowReclaimed'])
        self.assertFalse(feat['localStructure']['sweptHighRejected'])
        self.assertEqual(feat['pressureProxy']['interpretation'],'PRICE_VOLUME_PROXY_NOT_TAKER_FLOW')

    def test_sweep_high_rejected(self):
        bars=self.candles()
        bars[-1].update(o=105.0,h=107.0,l=100.0,c=103.0)
        feat=detector_features(bars,'15m')
        self.assertTrue(feat['localStructure']['sweptHighRejected'])
        self.assertFalse(feat['localStructure']['sweptLowReclaimed'])

    def test_invalid_bars_and_gaps_block_features(self):
        bars=self.candles()
        self.assertEqual(detector_features(bars[:-1],'15m')['status'],'INSUFFICIENT_CLOSED_BARS')
        bars[8]['t']+=1000
        feat=detector_features(bars,'15m')
        self.assertEqual(feat['status'],'GAPPED_HISTORY')
        self.assertNotIn('localStructure',feat)

    def test_no_quote_of_no_order_flow(self):
        feat=detector_features(self.candles(),'15m')
        self.assertNotIn('takerFlow',feat)
        self.assertNotIn('absorptionConfirmed',feat)
        self.assertEqual(feat['localStructure']['prior12High'],104.0)
        self.assertEqual(feat['localStructure']['prior12Low'],98.0)

    def test_oi_changes_are_same_venue_same_units(self):
        now=1800000000000
        samples=[
            {'t':now-3600000,'oiContracts':'100','oiUsd':'200'},
            {'t':now-900000,'oiContracts':'110','oiUsd':'240'},
            {'t':now,'oiContracts':'120','oiUsd':'260'}]
        primary={'instruments':{'SOL':{'perpetual':{
            'openInterestHistory':samples,
            'funding':{'fundingRate':'0.0001','observedAtMs':now-30000,
                       'fundingTime':'1800003600000','nextFundingTime':'1800032400000'}}}}}
        out=detector_derivatives(primary,'SOL',now)
        self.assertEqual(out['status'],'PARTIAL')
        self.assertEqual(out['openInterest']['deltaContractsPct1h'],20.0)
        self.assertAlmostEqual(out['openInterest']['deltaContractsPct15m'],9.0909,places=4)
        self.assertEqual(out['openInterest']['deltaUsdPct1h'],30.0)
        self.assertAlmostEqual(out['funding']['rate'],0.0001)

    def test_stale_and_future_data_is_not_validated(self):
        now=1800000000000
        primary={'instruments':{'SOL':{'perpetual':{
            'openInterestHistory':[{'t':now-3600000,'oiContracts':'100'},
                                   {'t':now+1000,'oiContracts':'999'}],
            'funding':{'observedAtMs':now-7200000,'fundingRate':'0.002'}}}}}
        out=detector_derivatives(primary,'SOL',now)
        self.assertEqual(out['status'],'N/A')
        self.assertIsNone(out['funding'])
        self.assertIsNone(out['openInterest'])
        self.assertIsNone(out['liquidations'])
        self.assertIsNone(out['takerFlow'])

    def test_no_oi_history_does_not_imply_zero_change(self):
        out=detector_derivatives({},'AAVE',1800000000000)
        self.assertEqual(out['status'],'N/A')
        self.assertIsNone(out['openInterest'])

if __name__=='__main__':
    unittest.main()
