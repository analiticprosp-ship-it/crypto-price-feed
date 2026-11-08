#!/usr/bin/env python3
"""Independent SHA256 and file-format verification of P3 sample downloads."""
import argparse, hashlib, json, pathlib, struct, datetime as dt

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--directory",required=True)
 a=p.parse_args(); root=pathlib.Path(a.directory)
 manifest=json.loads((root/"probe_manifest.json").read_text())
 checks=[]
 for row in manifest["rows"]:
  if row["status"]!="DOWNLOADED_UNVALIDATED_L2":
   checks.append({"path_candidate":row["path_candidate"],"status":"NOT_DOWNLOADED","source_status":row["status"]})
   continue
  f=root/pathlib.Path(row["local_file"]).name
  item={"path_candidate":row["path_candidate"],"filename":f.name,"status":"NOT_VERIFIED"}
  try:
   h=hashlib.sha256(); n=0
   with f.open("rb") as inp:
    head=inp.read(4);inp.seek(0)
    for chunk in iter(lambda:inp.read(1024*1024),b""):
     n+=len(chunk);h.update(chunk)
   item.update(actual_bytes=n,actual_sha256=h.hexdigest(),first4_hex=head.hex())
   if n!=row["bytes"] or h.hexdigest()!=row["sha256"]:
    item["status"]="HASH_OR_SIZE_MISMATCH"
   elif head==b"PAR1":
    item["status"]="HASH_OK_PARQUET_MAGIC"
   elif head==bytes.fromhex("28b52ffd"):
    item["status"]="HASH_OK_ZSTD_MAGIC_SCHEMA_UNVERIFIED"
   else:
    item["status"]="HASH_OK_UNKNOWN_FORMAT"
  except Exception as e:
   item["status"]="FILE_MISSING_OR_READ_ERROR";item["error"]=str(e)
  checks.append(item)
 out={"schema":"P3_L2_INDEPENDENT_HASH_AUDIT_V1","generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"disclaimer":"Magic bytes and SHA do not prove L2 event schema, sequence continuity or book depth","checks":checks}
 (root/"verification.json").write_text(json.dumps(out,indent=2)+"\n")
 summary={s:sum(x["status"]==s for x in checks) for s in sorted(set(x["status"] for x in checks))}
 print(json.dumps(summary))
 if any(x["status"] in ("HASH_OR_SIZE_MISMATCH","FILE_MISSING_OR_READ_ERROR","HASH_OK_UNKNOWN_FORMAT") for x in checks):
  raise SystemExit("L2 file integrity verification failed")
if __name__=="__main__":main()
