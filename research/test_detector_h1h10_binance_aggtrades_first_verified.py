"""Offline source- and clock-proof tests for bounded Binance raw Spot/USDM aggTrades."""
import datetime as dt
import io
import unittest
import zipfile

from research.detector_h1h10_binance_aggtrades_first_verified import (
    DAY, SYMBOLS, MARKETS, MAX_FILES,
    MAX_ZIP_BYTES, MAX_TOTAL_ZIP_BYTES,
    parse_day_zip, flow_csv_bytes, select_sources,
)


def source_zip(market="spot", symbol="SOLUSDT", missing=0,
               header=True, bad_time=False, duplicate=False,
               unknown_header=False, maker_override=None):
    start=int(dt.datetime.fromisoformat(DAY+"T00:00:00+00:00").timestamp()*1000)
    scale=1000 if market=="spot" else 1
    lines=[]
    if header:
        lines.append("unexpected,fields,absolutely,not,official" if unknown_header else
                     "agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker")
    for i in range(288-missing):
        aid=i if not duplicate or i!=2 else 1
        time=(start+i*300000+15000)*scale
        if bad_time and i==5:
            time=start-1
        maker=maker_override or ("true" if i%2 else "false")
        lines.append(f"{aid},100,2,{i*2},{i*2+1},{time},{maker}")
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{symbol}-aggTrades-{DAY}.csv","\n".join(lines)+"\n")
    return bio.getvalue()


class BoundedRealTradeAudit(unittest.TestCase):
    def test_spot_microsecond_event_trade_and_288_slots(self):
        source, rows=parse_day_zip(source_zip(),"spot","SOLUSDT",DAY)
        self.assertEqual(source["trade_clock_unit"],"microseconds")
        self.assertEqual(source["trades"],288)
        self.assertEqual(source["five_minute_slots_with_trades"],288)
        self.assertEqual(source["missing_five_minute_slots"],0)
        self.assertEqual(source["causal_rows_authorized"],0)
        self.assertEqual(source["source_event_time"],"VERIFIED_SOURCE_LABEL_ONLY")
        self.assertEqual(source["historical_original_publication_time"],"UNVERIFIED")
        self.assertEqual(rows[0]["taker_buy_quote_usdt"],200)
        self.assertEqual(rows[1]["taker_sell_quote_usdt"],200)

    def test_usdm_millisecond_event_clock(self):
        source,rows=parse_day_zip(source_zip(market="um"),"um","SOLUSDT",DAY)
        self.assertEqual(source["trade_clock_unit"],"milliseconds")
        self.assertEqual(len(rows),288)

    def test_spot_millisecond_cannot_pass_microsecond(self):
        with self.assertRaisesRegex(ValueError,"AGGTRADE_DAY_OR_TIME_UNIT_MISMATCH"):
            parse_day_zip(source_zip(market="um"),"spot","SOLUSDT",DAY)

    def test_missed_slot_is_reported_never_imputed(self):
        source,rows=parse_day_zip(source_zip(missing=2),"spot","SOLUSDT",DAY)
        self.assertEqual(source["missing_five_minute_slots"],2)
        self.assertEqual(len(rows),286)
        self.assertEqual(len(flow_csv_bytes(rows).splitlines()),287)

    def test_unknown_header_cannot_be_silently_skipped(self):
        with self.assertRaisesRegex(ValueError,"AGGTRADE_CSV_COLUMNS_INVALID"):
            parse_day_zip(source_zip(unknown_header=True),"spot","SOLUSDT",DAY)

    def test_invalid_trade_timestamp_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"AGGTRADE_DAY_OR_TIME_UNIT_MISMATCH"):
            parse_day_zip(source_zip(bad_time=True),"spot","SOLUSDT",DAY)

    def test_duplicate_aggtrade_ids_rejected(self):
        with self.assertRaisesRegex(ValueError,"AGGTRADE_DUPLICATE_OR_NONMONOTONIC_ID"):
            parse_day_zip(source_zip(duplicate=True),"spot","SOLUSDT",DAY)

    def test_invalid_buyer_maker_rejected(self):
        with self.assertRaisesRegex(ValueError,"AGGTRADE_TRADE_SEMANTICS_INVALID"):
            parse_day_zip(source_zip(maker_override="unknown"),"spot","SOLUSDT",DAY)

    def test_wrong_source_identity_fails(self):
        with self.assertRaisesRegex(ValueError,"AGGTRADE_ZIP_MEMBER_IDENTITY_MISMATCH"):
            parse_day_zip(source_zip(),"spot","BTCUSDT",DAY)

    def test_selection_bounded_with_explicit_exclusions(self):
        sources={(m,s):{"http":200,"bytes": 2_000_000 if s=="SOLUSDT" else
                          (10_000_000 if s=="ETHUSDT" else MAX_ZIP_BYTES+1)}
                  for m in MARKETS for s in SYMBOLS}
        chosen, skipped=select_sources(sources)
        self.assertEqual(len(chosen),4)
        self.assertEqual({m for m,s,n in chosen},set(MARKETS))
        self.assertLessEqual(sum(n for m,s,n in chosen),MAX_TOTAL_ZIP_BYTES)
        self.assertEqual(len(skipped),2)
        self.assertTrue(all(x["reason"]=="HTTP_OR_SOURCE_SIZE_NOT_ELIGIBLE"
                            for x in skipped))

    def test_source_missing_in_selection_fails(self):
        with self.assertRaisesRegex(ValueError,"SOURCE_AVAILABILITY_INCOMPLETE"):
            select_sources({})

    def test_all_oversized_no_fabricated_success(self):
        sources={(m,s):{"http":200,"bytes":MAX_ZIP_BYTES+1}
                 for m in MARKETS for s in SYMBOLS}
        chosen, skipped=select_sources(sources)
        self.assertEqual(chosen,[])
        self.assertEqual(len(skipped),6)


if __name__=="__main__":
    unittest.main()
