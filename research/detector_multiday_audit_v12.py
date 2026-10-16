#!/usr/bin/env python3
"""Audit available real detector event dates from git revisions. SHADOW only."""
import csv,datetime as dt,json,subprocess
from collections import defaultdict
from pathlib import Path
out=Path("detector_multiday_audit_results");out.mkdir(exist_ok=True)
def git(*args):
    return subprocess.run(["git",*args],capture_output=True,text=True,check=True).stdout
revs=git("log","--format=%H","--","detector-signal-events.json").splitlines()
events={};failures=[]
for sha in revs:
    try:
        raw=git("show",sha+":detector-signal-events.json")
        doc=json.loads(raw)
        for e in doc.get("events",[]):
            if e.get("status")!="EARLY_CANDIDATE_SHADOW" or e.get("direction") not in ("LONG","SHORT"):continue
            ident=e.get("id")
            if not ident or not e.get("firstDetectedAtUtc"):continue
            # Prefer original event identity and timestamp, never reconstruct detection.
            if ident in events and events[ident].get("firstDetectedAtUtc")!=e["firstDetectedAtUtc"]:
                failures.append({"commit":sha,"event_id":ident,"reason":"CONFLICTING_FIRST_DETECTION"})
                continue
            events.setdefault(ident,e)
    except Exception as exc:failures.append({"commit":sha,"reason":str(exc)[:250]})
days=defaultdict(list)
for e in events.values():days[e["firstDetectedAtUtc"][:10]].append(e)
with (out/"available_days.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["date_utc","events","symbols","long","short","first_detected_utc","last_detected_utc"])
    w.writeheader()
    for day,ee in sorted(days.items()):
        times=sorted(x["firstDetectedAtUtc"] for x in ee)
        w.writerow({"date_utc":day,"events":len(ee),"symbols":len({x["symbol"] for x in ee}),
                    "long":sum(x["direction"]=="LONG" for x in ee),"short":sum(x["direction"]=="SHORT" for x in ee),
                    "first_detected_utc":times[0],"last_detected_utc":times[-1]})
with (out/"historical_real_events.json").open("w") as f:
    json.dump({"schemaVersion":"detector-real-event-history-audit-1.0","events":sorted(events.values(),key=lambda x:x["firstDetectedAtUtc"])},f,indent=2)
manifest={"mode":"SHADOW_RESEARCH_ONLY","commits_inspected":len(revs),"unique_real_events":len(events),
          "distinct_utc_days":len(days),"dates":sorted(days),"errors":failures,
          "next_step":"Require at least two distinct event dates before any out-of-day validation claim",
          "limitations":["Only events actually retained in Git revisions are observable",
            "No synthetic firstDetectedAtUtc or reconstructed Swing joins",
            "Commit history may omit older events due to squash, force-push or retention",
            "No trading actions or limit changes"]}
(out/"manifest.json").write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
