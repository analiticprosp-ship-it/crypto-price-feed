#!/usr/bin/env python3
"""Optional continuous Bybit public market-data collector; research only.

Not part of GitHub Actions schedules or prices.json. No account credentials,
trading API, private topics, signals, risk budgets, or orders.
Requires an always-on host and optional websocket-client dependency.
"""
import argparse
import hashlib
import json
import logging
import math
import os
import re
import signal
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger("detector-stream")
MINUTE = 60_000
SYMBOL = re.compile(r"^[A-Z0-9]{2,15}USDT$")
WS_URLS = {
    "linear": "wss://stream.bybit.com/v5/public/linear",
    "spot": "wss://stream.bybit.com/v5/public/spot",
}

def as_positive_float(value):
    try:
        out = float(value)
        return out if math.isfinite(out) and out > 0 else None
    except (TypeError, ValueError):
        return None

def parse_events(message, *, market, allowed, received_ms):
    """Strict public Bybit V5 payload normalizer. No synthetic order flow."""
    if market not in WS_URLS or not isinstance(message, dict):
        return []
    topic = message.get("topic", "")
    if not isinstance(topic, str) or "." not in topic:
        return []
    prefix, symbol = topic.split(".", 1)
    if symbol not in allowed or not SYMBOL.fullmatch(symbol):
        return []
    if prefix == "publicTrade":
        kind = "taker_trade"
    elif prefix == "allLiquidation" and market == "linear":
        kind = "liquidation"
    else:
        return []
    raw = message.get("data")
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    result = []
    for row in raw:
        if not isinstance(row, dict) or row.get("s") != symbol:
            continue
        side = row.get("S")
        if side not in ("Buy", "Sell"):
            continue
        try:
            event_ms = int(row.get("T"))
        except (TypeError, ValueError):
            continue
        # Reject bad clocks and replays: do not backfill disconnected history.
        if event_ms <= 0 or not -5000 <= received_ms - event_ms <= 120_000:
            continue
        qty, price = as_positive_float(row.get("v")), as_positive_float(row.get("p"))
        if qty is None or price is None:
            continue
        raw_id = row.get("i") if kind == "taker_trade" else None
        if kind == "taker_trade" and (not isinstance(raw_id, str) or not raw_id):
            continue
        if kind == "liquidation":
            # Bybit allLiquidation S = position side; Buy = liquidated LONG.
            # Lack of stable event ID means this fingerprint may collide.
            raw_id = hashlib.sha256(
                f"{event_ms}|{symbol}|{side}|{row['v']}|{row['p']}".encode()
            ).hexdigest()
        result.append((market, kind, symbol, str(raw_id), event_ms, side,
                       qty, qty * price))
    return result

class EventStore:
    """SQLite-backed rolling pilot with explicit per-connection coverage."""
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=30000")
        self.db.execute("""CREATE TABLE IF NOT EXISTS events (
          market TEXT NOT NULL, kind TEXT NOT NULL, symbol TEXT NOT NULL,
          event_id TEXT NOT NULL, ts INTEGER NOT NULL, side TEXT NOT NULL,
          qty REAL NOT NULL, notional REAL NOT NULL,
          PRIMARY KEY(market, kind, symbol, event_id))""")
        self.db.execute("CREATE INDEX IF NOT EXISTS events_time ON events(market,kind,symbol,ts)")
        self.db.execute("""CREATE TABLE IF NOT EXISTS sessions (
          market TEXT NOT NULL, start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL)""")
        self.db.commit()
        self.lock = threading.RLock()
        self.active = {}

    def subscribe_confirmed(self, market, at):
        with self.lock:
            if market not in self.active:
                self.active[market] = at

    def disconnected(self, market, at):
        with self.lock:
            start = self.active.pop(market, None)
            if start is not None and at > start:
                self.db.execute("INSERT INTO sessions VALUES (?,?,?)", (market, start, at))
                self.db.commit()

    def ingest(self, events):
        if not events:
            return 0
        with self.lock:
            before = self.db.total_changes
            self.db.executemany("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?)", events)
            self.db.commit()
            return self.db.total_changes - before

    def coverage(self, market, start_ms, end_ms, now_ms):
        with self.lock:
            intervals = [(max(start_ms, a), min(end_ms, b))
                         for a,b in self.db.execute(
                             "SELECT start_ms,end_ms FROM sessions WHERE market=? "
                             "AND end_ms>? AND start_ms<?", (market,start_ms,end_ms))]
            active_start = self.active.get(market)
            if active_start is not None:
                intervals.append((max(start_ms, active_start), min(end_ms, now_ms)))
        intervals = sorted((a,b) for a,b in intervals if b>a)
        if not intervals:
            return 0.0
        covered=0
        left,right=intervals[0]
        for a,b in intervals[1:]:
            if a<=right:
                right=max(right,b)
            else:
                covered+=right-left
                left,right=a,b
        covered+=right-left
        return min(1.0,covered/(end_ms-start_ms))

    def stats(self, market, kind, symbol, start_ms, end_ms):
        with self.lock:
            data=list(self.db.execute(
                "SELECT side,COUNT(*),SUM(qty),SUM(notional) FROM events "
                "WHERE market=? AND kind=? AND symbol=? AND ts>=? AND ts<? "
                "GROUP BY side", (market,kind,symbol,start_ms,end_ms)))
        sides={side:{"count":count,"quantity":qty,"notionalUsdEstimate":notional}
               for side,count,qty,notional in data}
        buy=sides.get("Buy",{"count":0,"quantity":0.0,"notionalUsdEstimate":0.0})
        sell=sides.get("Sell",{"count":0,"quantity":0.0,"notionalUsdEstimate":0.0})
        return {
            "buy":buy,"sell":sell,"count":buy["count"]+sell["count"],
            "deltaNotional":round(buy["notionalUsdEstimate"]-sell["notionalUsdEstimate"],4)
                if kind=="taker_trade" else None,
            "sideMeaning":"TAKER_SIDE" if kind=="taker_trade"
                 else "POSITION_SIDE_BUY_IS_LIQUIDATED_LONG",
            "notionalQuality":"TRADE_PRICE_X_QUANTITY" if kind=="taker_trade"
                 else "BANKRUPTCY_PRICE_X_QUANTITY_ESTIMATE_NOT_FILL_PRICE"
        }

    def snapshot(self, symbols, at=None):
        at=int(time.time()*1000) if at is None else int(at)
        end=(at//MINUTE)*MINUTE  # only fully closed minute windows
        blocks={}
        for market,kinds in [("spot",("taker_trade",)),
                             ("linear",("taker_trade","liquidation"))]:
            group={}
            for symbol in symbols:
                entries={}
                for kind in kinds:
                    windows={}
                    for minutes in (1,5,15):
                        start=end-minutes*MINUTE
                        ratio=self.coverage(market,start,end,at)
                        if ratio < 0.99:
                            windows[f"{minutes}m"]={"status":"NO_DATA_GAPPED_OR_WARMUP",
                                                     "coverageRatio":round(ratio,5),
                                                     "data":None}
                        else:
                            data=self.stats(market,kind,symbol,start,end)
                            # A healthy socket does not prove that this specific
                            # trade topic is producing. Do not fake zero trade flow.
                            if kind=="taker_trade" and data["count"]==0:
                                windows[f"{minutes}m"]={"status":"NO_TRADE_EVENTS_UNVERIFIED",
                                                         "coverageRatio":round(ratio,5),
                                                         "data":None}
                            else:
                                windows[f"{minutes}m"]={"status":"OBSERVED",
                                                         "coverageRatio":round(ratio,5),
                                                         "data":data}
                    entries[kind]=windows
                group[symbol]=entries
            blocks[market]=group
        return {
            "schemaVersion":"detector-microflow-pilot-0.1",
            "generatedAt":datetime.fromtimestamp(at/1000,timezone.utc).isoformat(),
            "lastCompleteMinuteEndMs":end,
            "source":"Bybit public WebSocket V5",
            "researchOnly":True,"notTradeApproval":True,
            "notSystemPrice":True,"notForPricingOrNAV":True,
            "noHistoricalBackfill":True,
            "coverageRule":"Whole closed window >=99% connected time; missing is NULL",
            "scope":"ONE_VENUE_ONLY; venue flows are not all-market flows",
            "streams":blocks,
        }

    def prune(self, at):
        cutoff=at-90*MINUTE
        with self.lock:
            self.db.execute("DELETE FROM events WHERE ts<?", (cutoff,))
            self.db.execute("DELETE FROM sessions WHERE end_ms<?", (cutoff,))
            self.db.commit()

def write_snapshot(store, symbols, path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    now=int(time.time()*1000)
    blob=json.dumps(store.snapshot(symbols,now),ensure_ascii=False,separators=(",",":"))
    temp=path.with_name(path.name+".tmp")
    temp.write_text(blob+"\n",encoding="utf-8")
    os.replace(temp,path)
    store.prune(now)

def run_stream(market, symbols, store, stop):
    import websocket  # optional: pip install websocket-client; not needed by tests
    url=WS_URLS[market]
    topics=[f"publicTrade.{s}" for s in symbols]
    if market=="linear":
        topics += [f"allLiquidation.{s}" for s in symbols]
    attempt=0
    while not stop.is_set():
        acknowledged=threading.Event()
        def on_open(ws):
            ws.send(json.dumps({"op":"subscribe","args":topics}))
        def on_message(ws, raw):
            try: obj=json.loads(raw)
            except (ValueError,TypeError): return
            if obj.get("op")=="subscribe":
                if obj.get("success") is True:
                    store.subscribe_confirmed(market,int(time.time()*1000))
                    acknowledged.set()
                else:
                    LOG.warning("%s subscribe rejected %s", market, str(obj)[:180])
                    ws.close()
                return
            if not acknowledged.is_set():
                return
            ev=parse_events(obj,market=market,allowed=set(symbols),received_ms=int(time.time()*1000))
            store.ingest(ev)
        def on_error(ws, error):
            LOG.warning("%s websocket failure: %s",market,error)
        def on_close(ws, code, msg):
            store.disconnected(market,int(time.time()*1000))
            LOG.warning("%s websocket closed code=%s %s",market,code,msg)
        app=websocket.WebSocketApp(url,on_open=on_open,on_message=on_message,
                                   on_error=on_error,on_close=on_close)
        session_done=threading.Event()
        def heartbeat():
            while not stop.is_set() and not session_done.wait(20):
                if app.sock and app.sock.connected:
                    try: app.send(json.dumps({"op":"ping"}))
                    except Exception: break
        ping_thread=threading.Thread(target=heartbeat,daemon=True)
        ping_thread.start()
        try:
            # Library ping also detects dead TCP connections.
            app.run_forever(ping_interval=30,ping_timeout=10)
        except Exception as ex:
            LOG.warning("%s stream exception: %s",market,ex)
        finally:
            session_done.set()
            store.disconnected(market,int(time.time()*1000))
        attempt+=1
        if stop.wait(min(60,2**min(attempt,6))):
            break

def main():
    p=argparse.ArgumentParser(description="Research-only Bybit microflow pilot")
    p.add_argument("--symbols",default="SOLUSDT,SUIUSDT")
    p.add_argument("--db",default="detector-stream.sqlite")
    p.add_argument("--out",default="detector-microflow.json")
    args=p.parse_args()
    symbols=list(dict.fromkeys(s.strip().upper() for s in args.symbols.split(",") if s.strip()))
    if not 1<=len(symbols)<=4 or any(not SYMBOL.fullmatch(s) for s in symbols):
        p.error("Pilot accepts 1-4 exact USDT symbols (e.g. SOLUSDT,SUIUSDT)")
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    store=EventStore(args.db)
    stop=threading.Event()
    def terminate(*unused):
        stop.set()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,terminate)
    for market in WS_URLS:
        threading.Thread(target=run_stream,args=(market,symbols,store,stop),
                         daemon=True,name=f"bybit-{market}").start()
    LOG.info("Pilot started %s; %s; research only, no trading",symbols,args.out)
    while not stop.wait(20):
        write_snapshot(store,symbols,args.out)
    for market in WS_URLS:
        store.disconnected(market,int(time.time()*1000))
    write_snapshot(store,symbols,args.out)

if __name__=="__main__":
    main()
