#!/usr/bin/env python3
"""Conservative Tardis normalized L2 replay; reject incomplete or crossed books."""
import argparse,csv,gzip,hashlib,json,pathlib
from decimal import Decimal,InvalidOperation
p=argparse.ArgumentParser();p.add_argument("--file",required=True);p.add_argument("--out",required=True);p.add_argument("--max-rows",type=int,default=0);a=p.parse_args()
path=pathlib.Path(a.file);sha=hashlib.sha256()
with path.open("rb") as f:
 for b in iter(lambda:f.read(1024*1024),b""):sha.update(b)
bid={};ask={};snapshots=0;updates=0;crossed=0;pre_snapshot=0;valid_quotes=0;last_local=None;time_regressions=0;first_quote=None;last_quote=None;rows=0
with gzip.open(path,"rt",newline="") as f:
 rd=csv.DictReader(f);required={"local_timestamp","is_snapshot","side","price","amount"}
 if not required.issubset(rd.fieldnames or []):raise SystemExit("MISSING_REQUIRED_L2_COLUMNS")
 in_snapshot=False;ever_snapshot=False
 for row in rd:
  rows+=1
  if a.max_rows and rows>a.max_rows:break
  snapshot=row["is_snapshot"].lower()=="true"
  if snapshot and not in_snapshot:
   bid.clear();ask.clear();snapshots+=1;ever_snapshot=True
  in_snapshot=snapshot
  if not ever_snapshot:pre_snapshot+=1;continue
  try:
   price=Decimal(row["price"]);amount=Decimal(row["amount"]);local=int(row["local_timestamp"])
  except (InvalidOperation,ValueError,KeyError):raise SystemExit("INVALID_L2_VALUE")
  if price<=0 or amount<0:raise SystemExit("INVALID_PRICE_OR_AMOUNT")
  if last_local is not None and local<last_local:time_regressions+=1
  last_local=local
  side=bid if row["side"]=="bid" else ask if row["side"]=="ask" else None
  if side is None:raise SystemExit("INVALID_SIDE")
  if amount==0:side.pop(price,None)
  else:side[price]=amount
  updates+=1
  if not snapshot and bid and ask:
   best_bid=max(bid);best_ask=min(ask)
   if best_bid>=best_ask:crossed+=1
   else:
    valid_quotes+=1;quote={"local_timestamp":local,"best_bid":str(best_bid),"best_ask":str(best_ask),"spread":str(best_ask-best_bid),"spread_bps":str((best_ask-best_bid)/((best_ask+best_bid)/2)*10000)}
    if first_quote is None:first_quote=quote
    last_quote=quote
status="REPLAY_PARTIAL_NOT_ACCEPTED"
if not a.max_rows and snapshots>0 and valid_quotes>0 and crossed==0 and time_regressions==0:status="REPLAY_BASIC_CHECKS_PASSED_NOT_SEQUENCE_VERIFIED"
result={"schema":"P3_TARDIS_REPLAY_V1","status":status,"sha256":sha.hexdigest(),"rows":rows,"snapshots":snapshots,"updates":updates,"pre_snapshot_discarded":pre_snapshot,"crossed_book_rows":crossed,"time_regressions":time_regressions,"valid_quote_rows":valid_quotes,"first_quote":first_quote,"last_quote":last_quote,"limitations":"No exchange-native sequence IDs, disconnect events, full depth acceptance or independent quote cross-check. Crossing counted per row rather than atomic WebSocket message."}
pathlib.Path(a.out).write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result))
if status!="REPLAY_BASIC_CHECKS_PASSED_NOT_SEQUENCE_VERIFIED":raise SystemExit("REPLAY_NOT_VALIDATED")
