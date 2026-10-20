"""Offline immutable R2-source contract and 1750-day 3-coin gap mask tests."""
import copy
import unittest
from research import detector_joint_source_oi_2022_2026_v1 as a

def synthetic_early():
    excluded={"2022-03-07","2022-03-08","2022-03-15","2022-09-03",
       "2023-06-06","2023-08-09","2023-09-12","2023-11-11",
       "2023-11-20","2023-11-23","2023-11-26","2023-12-08","2023-12-12"}
    rows=[]
    for day in a.dates(a.START,a.BRIDGE-a.dt.timedelta(days=1)):
        rejected=["SOLUSDT"] if day in excluded else []
        m={sym:{"full_288_labels_and_numeric":sym not in rejected} for sym in a.SYMBOLS}
        rows.append({"day":day,"per_symbol":m,"excluded_symbols":rejected,
                     "three_coin_full_source_day":day not in excluded})
    return {"schema":a.SOURCES["2022_2023"]["schema"],"research_only":True,
        "edge_status":"EDGE_UNVALIDATED","calendar_days":730,
        "source_complete_asset_days":2159,"partial_asset_days":31,
        "three_coin_joint_full_days":717,"daily_source_quality_mask":rows}

def synthetic_late():
    anomalies=[{"date_utc":"2024-02-16","missing":125},
               {"date_utc":"2024-10-28","missing":2},
               {"date_utc":"2025-08-29","missing":3}]
    by_sym={s:{"calendar_days":1020,"complete_5m_days":1017,
        "missing_5m_slots":130,"duplicate_label_rows":0,
        "anomalous_days":copy.deepcopy(anomalies)} for s in a.SYMBOLS}
    return {"schema":a.SOURCES["2024_2026"]["schema"],"edge_status":"EDGE_UNVALIDATED",
       "research_only":True,"status":"OI_SOURCE_LABEL_GAP_LEDGER_COMPLETE",
       "window_start":"2024-01-01","window_end":"2026-10-16",
       "all_symbols_same_gap_ledger":True,"symbols":by_sym}

class JointSource(unittest.TestCase):
 def test_exact_1750_dates(self):
    self.assertEqual(len(a.dates(a.START,a.END)),1750)
    self.assertEqual(a.dates(a.START,a.END)[-1],"2026-10-16")
 def test_two_immutable_sources(self):
    self.assertEqual(set(a.SOURCES),{"2022_2023","2024_2026"})
    for value in a.SOURCES.values():self.assertEqual(len(value["sha256"]),64)
 def test_early_717_preserved(self):
    s=a.early_2022_2023(synthetic_early())
    self.assertEqual((len(s),sum(v["all_three_5m_source_clean"] for v in s.values())),(730,717))
 def test_late_1017_preserved(self):
    s=a.late_2024_2026(synthetic_late())
    self.assertEqual((len(s),sum(v["all_three_5m_source_clean"] for v in s.values())),(1020,1017))
 def test_joint_1734_and_16_exclusions(self):
    both=a.combine(a.early_2022_2023(synthetic_early()),a.late_2024_2026(synthetic_late()))
    self.assertEqual((both["total_calendar_days"],both["joint_full_days"],both["joint_excluded_days"]),(1750,1734,16))
    self.assertEqual(len(both["rejected_day_details"]),16)
 def test_joint_end_has_no_future_dates(self):
    c=a.combine(a.early_2022_2023(synthetic_early()),a.late_2024_2026(synthetic_late()))
    self.assertEqual(c["source_daily_mask"][-1]["date_utc"],"2026-10-16")
 def test_source_provenance_levels_preserved(self):
    c=a.combine(a.early_2022_2023(synthetic_early()),a.late_2024_2026(synthetic_late()))
    self.assertNotEqual(c["source_daily_mask"][0]["provenance_level"],c["source_daily_mask"][-1]["provenance_level"])
 def test_missing_5m_source_not_imputed(self):
    c=a.combine(a.early_2022_2023(synthetic_early()),a.late_2024_2026(synthetic_late()))
    rejected={x["date_utc"]:x for x in c["rejected_day_details"]}
    self.assertEqual(rejected["2024-02-16"]["native_quality_by_asset"]["BTCUSDT"]["missing_5m_source_labels"],125)
    self.assertEqual(rejected["2025-08-29"]["rejected_assets"],list(a.SYMBOLS))
 def test_reject_incomplete_2022_provenance(self):
    r=synthetic_early()
    r["daily_source_quality_mask"].pop()
    with self.assertRaises(ValueError):a.early_2022_2023(r)
 def test_reject_early_asset_quality_contradiction(self):
    r=synthetic_early()
    r["daily_source_quality_mask"][0]["excluded_symbols"]=["BTCUSDT"]
    with self.assertRaises(ValueError):a.early_2022_2023(r)
 def test_late_wrong_source_gap_counts_fail(self):
    x=synthetic_late()
    x["symbols"]["SOLUSDT"]["missing_5m_slots"]=129
    with self.assertRaises(ValueError):a.late_2024_2026(x)
 def test_late_different_symbol_gap_calendar_fails(self):
    x=synthetic_late()
    x["symbols"]["ETHUSDT"]["anomalous_days"][0]["missing"]=124
    with self.assertRaises(ValueError):a.late_2024_2026(x)
 def test_unverified_parent_cannot_be_used(self):
    x=synthetic_late();x["edge_status"]="EDGE_VALIDATED"
    with self.assertRaises(ValueError):a.late_2024_2026(x)
 def test_overlapping_source_periods_fail(self):
    early=a.early_2022_2023(synthetic_early())
    late={"2023-12-31":list(early.values())[-1]}
    with self.assertRaises(ValueError):a.combine(early,late)
 def test_longest_run_covers_post_2025_gap(self):
    c=a.combine(a.early_2022_2023(synthetic_early()),a.late_2024_2026(synthetic_late()))
    self.assertEqual(c["clean_streaks_longest_first"][0],
                     {"start":"2025-08-30","end":"2026-10-16","calendar_days":413})

if __name__=="__main__":unittest.main()
