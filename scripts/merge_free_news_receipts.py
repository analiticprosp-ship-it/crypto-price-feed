"""Research-only merge of retained collection receipts; no inferred historical timestamps."""
import argparse
import json
from pathlib import Path

def merge(paths):
    ledger = {}
    observations = 0
    for path in paths:
        for line in Path(path).read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = row["dedupe_key"]
            observed = row["first_seen_at_utc"]
            observations += 1
            if key not in ledger:
                ledger[key] = {"dedupe_key": key, "source": row["source"],
                               "first_seen_at_utc": observed, "observations": []}
            entry = ledger[key]
            entry["first_seen_at_utc"] = min(entry["first_seen_at_utc"], observed)
            entry["observations"].append(row)
    for entry in ledger.values():
        entry["observations"].sort(key=lambda r: r["first_seen_at_utc"])
    return {"observations": observations, "unique_source_items": len(ledger),
            "repeat_observations": observations - len(ledger),
            "items": sorted(ledger.values(), key=lambda r: r["dedupe_key"])}

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("inputs", nargs="+")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    result = merge(a.inputs)
    out = Path(a.output)
    if out.exists():
        raise FileExistsError(out)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k != "items"}))
