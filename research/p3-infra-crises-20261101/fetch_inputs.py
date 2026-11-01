"""Recreate acquired inputs from pinned public GitHub refs; read-only downloads."""
from pathlib import Path
import hashlib,json,urllib.request
R=Path(__file__).resolve().parent
for x in json.loads((R/'source_map.json').read_text()):
 p=R/x['local'];expected=x['expected_sha256']
 if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==expected:continue
 url='https://raw.githubusercontent.com/analiticprosp-ship-it/crypto-price-feed/'+x['ref']+'/'+x['repo_path']
 with urllib.request.urlopen(url,timeout=60) as response:raw=response.read()
 assert hashlib.sha256(raw).hexdigest()==expected,x['local']
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
print('Pinned input hashes verified')
