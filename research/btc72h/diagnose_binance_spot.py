#!/usr/bin/env python3
"""Read-only Binance Spot BTCUSDT 1h connectivity and continuity probe.
No trading, no event registration, no writes to canonical files.
"""
import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request

HOSTS = ["https://api.binance.com", "https://api1.binance.com", "https://data-api.binance.vision"]
def iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat()
def probe(host):
    now_ms = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    last_open_ms = (now_ms // 3600000 - 1) * 3600000
    start_ms = last_open_ms - 199 * 3600000
    end_ms = last_open_ms + 3599999
    params = urllib.parse.urlencode({"symbol":"BTCUSDT","interval":"1h","startTime":start_ms,"endTime":end_ms,"limit":250})
    url = host + "/api/v3/klines?" + params
    request = urllib.request.Request(url, headers={"User-Agent":"BTC72H-research-readonly-diagnostic/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            rows = json.load(response)
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], list):
            return {"host":host,"status":"INVALID_PAYLOAD","preview":str(rows)[:200]}
        opens = [int(row[0]) for row in rows]
        valid = all(len(row) >= 7 and int(row[6]) < now_ms and int(row[6]) == int(row[0])+3599999 and float(row[2])>=float(row[3]) and float(row[5])>=0 for row in rows)
        gaps = [iso(opens[i]) for i in range(1,len(opens)) if opens[i]-opens[i-1]!=3600000]
        return {"host":host,"status":"COMPLETE" if valid and not gaps and opens[0]==start_ms and opens[-1]==last_open_ms else "INCOMPLETE","count":len(rows),"first_open_utc":iso(opens[0]),"last_open_utc":iso(opens[-1]),"expected_first_open_utc":iso(start_ms),"expected_last_open_utc":iso(last_open_ms),"gaps":gaps[:10],"valid_closed_ohlcv":valid}
    except (urllib.error.URLError,TimeoutError,ValueError,TypeError) as e:
        return {"host":host,"status":"ERROR","error":str(e)[:300]}
if __name__ == "__main__":
    print(json.dumps({"checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"market":"Binance Spot BTCUSDT","interval":"1h","results":[probe(h) for h in HOSTS]},ensure_ascii=False,indent=2))
