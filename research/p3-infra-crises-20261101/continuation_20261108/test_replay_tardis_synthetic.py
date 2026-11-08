#!/usr/bin/env python3
"""Deterministic replay smoke test using original synthetic L2 rows; not historical validation."""
import csv,gzip,json,pathlib,subprocess,sys,tempfile
root=pathlib.Path(__file__).parent
with tempfile.TemporaryDirectory() as tmp:
 p=pathlib.Path(tmp)/"synthetic.csv.gz";out=pathlib.Path(tmp)/"receipt.json"
 rows=[
  ("1000","true","bid","100","2"),("1000","true","ask","101","3"),
  ("1001","false","bid","100","0"),("1002","false","bid","99","4"),
  ("1003","false","ask","101","0"),("1004","false","ask","102","1"),
 ]
 with gzip.open(p,"wt",newline="") as f:
  w=csv.writer(f);w.writerow(["local_timestamp","is_snapshot","side","price","amount"]);w.writerows(rows)
 run=subprocess.run([sys.executable,str(root/"replay_tardis_l2.py"),"--file",str(p),"--out",str(out)],capture_output=True,text=True)
 if run.returncode:raise AssertionError(run.stdout+"\n"+run.stderr)
 data=json.loads(out.read_text())
 assert data["status"]=="REPLAY_BASIC_CHECKS_PASSED_NOT_SEQUENCE_VERIFIED",data
 assert data["snapshots"]==1 and data["crossed_book_rows"]==0,data
 assert data["last_quote"]["best_bid"]=="99" and data["last_quote"]["best_ask"]=="102",data
 print("PASS synthetic replay smoke test; real market replay NOT verified")
