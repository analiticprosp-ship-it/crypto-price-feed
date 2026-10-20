"""Offline timestamps, checksum semantics, and anti-lookahead for 3-metric forward OKX."""
import unittest
from research.detector_okx_3metric_forward_48h import parse_rows,reconcile,coverage_gate,SCHEMA
from research.detector_okx_3metric_forward_48h import SYMBOLS,METRICS

T=1800000000000
R=T+60000
def row(label,code="a"):
 return {"label_ms":label,"raw_sha256":code*64,"data":{}}
def record(metric,labels,received=R,inst=SYMBOLS[0]):
 return {"schema":SCHEMA,"metric":metric,"symbol":inst,
    "response_received_ms":received,"rows":[row(x) for x in labels]}

class ThreeMetricContract(unittest.TestCase):
 def test_price_close_confirmed(self):
  p={"code":"0","data":[[str(T),"100","120","90","110","5","5","550","1"]]}
  r=parse_rows("price",p,SYMBOLS[0],R)
  self.assertEqual(r[0]["data"]["confirm"],"1")
  self.assertEqual(r[0]["data"]["source_bar_nominal_end_ms"],T+300000)
 def test_price_unfinished_is_never_the_same_as_complete(self):
  p={"code":"0","data":[[str(T),"100","120","90","110","5","5","550","0"]]}
  self.assertEqual(parse_rows("price",p,SYMBOLS[0],R)[0]["data"]["confirm"],"0")
 def test_flow_sell_first_buy_second(self):
  p={"code":"0","data":[[str(T),"4.5","7.5"]]}
  x=parse_rows("flow",p,SYMBOLS[0],R)[0]["data"]
  self.assertEqual(x["sell_native"],"4.5")
  self.assertEqual(x["buy_native"],"7.5")
 def test_native_oi_never_converted_to_notional(self):
  x=parse_rows("oi",{"code":"0","data":[[str(T),"100","200"]]},SYMBOLS[0],R)[0]
  self.assertEqual(x["data"]["units"],"NATIVE_OI_INSTRUMENT_SIZE_UNVERIFIED")
 def test_negative_flow_fails_closed(self):
  with self.assertRaisesRegex(ValueError,"NONFINITE"):
   parse_rows("flow",{"code":"0","data":[[str(T),"-1","5"]]},SYMBOLS[0],R)
 def test_nan_oi_fails_closed(self):
  with self.assertRaisesRegex(ValueError,"NONFINITE"):
   parse_rows("oi",{"code":"0","data":[[str(T),"NaN"]]},SYMBOLS[0],R)
 def test_wrong_http_schema_rejected(self):
  with self.assertRaisesRegex(ValueError,"API_CODE"):
   parse_rows("price",{"code":"51000","data":[]},SYMBOLS[0],R)
 def test_duplicate_source_label_fails_closed(self):
  with self.assertRaisesRegex(ValueError,"DUPLICATE_OR_OFFGRID"):
   parse_rows("flow",{"code":"0","data":[[str(T),"1","2"],[str(T),"3","4"]]},SYMBOLS[0],R)
 def test_future_source_label_fails_closed(self):
  with self.assertRaisesRegex(ValueError,"DUPLICATE_OR_OFFGRID"):
   parse_rows("flow",{"code":"0","data":[[str(T+300000),"1","2"]]},SYMBOLS[0],R)
 def test_bootstrap_only_no_historical_first_release(self):
  f,r,b=reconcile(None,record("oi",[T]))
  self.assertTrue(b)
  self.assertEqual((f,r),([],[]))
 def test_sampled_appearance_bounds_only_if_previously_absent(self):
  a=record("oi",[T],T+360000)
  b=record("oi",[T,T+300000],T+660000)
  first,changes,boot=reconcile(a,b)
  self.assertEqual(len(first),1)
  self.assertEqual(first[0]["kind"],"SAMPLED_ABSENT_THEN_PRESENT")
  self.assertEqual(first[0]["last_observed_absent_ms"],T+360000)
  self.assertTrue(first[0]["never_original_exchange_publication"])
 def test_no_false_prior_absence_before_label(self):
  a=record("oi",[T],T+150000)
  b=record("oi",[T+300000],T+660000)
  first,_,_=reconcile(a,b)
  self.assertIsNone(first[0]["last_observed_absent_ms"])
 def test_revised_value_not_backdated(self):
  a=record("oi",[T],T+360000)
  b=record("oi",[T],T+660000)
  b["rows"][0]["raw_sha256"]="b"*64
  first,changes,_=reconcile(a,b)
  self.assertFalse(first)
  self.assertEqual(changes[0]["old_sha256"],"a"*64)
 def test_nonmonotonic_collector_clock_rejected(self):
  a=record("oi",[T],T+360000)
  b=record("oi",[T],T+120000)
  with self.assertRaisesRegex(ValueError,"CLOCK_INVALID"):
   reconcile(a,b)
 def test_three_source_label_overlap_does_not_authorize_pit(self):
  p={}
  for inst in SYMBOLS:
   for metric in METRICS:p[inst,metric]=record(metric,[T])
  result=coverage_gate(p)
  for inst in SYMBOLS:
   self.assertEqual(result[inst]["source_label_triples"],1)
   self.assertEqual(result[inst]["causal_5m_rows_authorized"],0)
   self.assertFalse(result[inst]["training_authorized"])
 def test_missing_metric_not_silently_filled(self):
  p={(SYMBOLS[0],"oi"):record("oi",[T]),(SYMBOLS[0],"price"):record("price",[T])}
  result=coverage_gate(p)
  self.assertEqual(result[SYMBOLS[0]]["source_label_triples"],0)
  self.assertIn("flow",result[SYMBOLS[0]]["missing_streams"])
if __name__=="__main__":unittest.main()
