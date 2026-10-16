#!/usr/bin/env python3
"""Opt-in GitHub Actions -> Telegram for NEW SHADOW candidates only.

No polling service, no exchange credentials, no current price or trade execution.
Telegram token/chat id must be configured as GitHub Actions Secrets.
Never echo credentials, request URLs, or full HTTP responses in logs.
Delivery is best-effort with persistent receipts; true exactly-once across
network timeouts is not possible with Telegram sendMessage.
"""
import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVENTS=ROOT/"detector-signal-events.json"
RECEIPTS=ROOT/"detector-alert-deliveries.json"
MAX_AFTER_DETECTION_MS=15*60*1000
MAX_SENDS_PER_RUN=8
VERSION="detector-alert-deliveries-1.0"

def parse_ms(value):
    try:
        ts=datetime.fromisoformat(value.replace("Z","+00:00"))
        return int(ts.timestamp()*1000) if ts.tzinfo else None
    except (TypeError,ValueError,OverflowError,AttributeError):
        return None

def empty_receipts():
    return {"schemaVersion":VERSION,"receipts":[],"researchOnly":True,"notTradeApproval":True}

def prepare_events(events,receipts,now_ms):
    if not isinstance(events,dict) or events.get("schemaVersion")!="detector-signal-events-1.0" or events.get("initialized") is not True:
        raise ValueError("INVALID_EVENT_LEDGER")
    if not isinstance(receipts,dict) or receipts.get("schemaVersion")!=VERSION:
        raise ValueError("INVALID_RECEIPT_LEDGER")
    history=receipts.get("receipts")
    if not isinstance(history,list):
        raise ValueError("RECEIPTS_MALFORMED")
    sent_ids={r["id"] for r in history if isinstance(r,dict) and isinstance(r.get("id"),str)}
    chosen=[]
    for row in events.get("events",[]):
        if not isinstance(row,dict) or row.get("alertEligible") is not True or row.get("notificationStatus")!="NEW_SHADOW_CANDIDATE":
            continue
        ident=row.get("id")
        if not isinstance(ident,str) or ident in sent_ids or len(ident)!=24:
            continue
        if (row.get("status")!="EARLY_CANDIDATE_SHADOW" or
            row.get("direction") not in ("LONG","SHORT") or
            row.get("notTradeApproval") is not True):
            continue
        detect=parse_ms(row.get("firstDetectedAtUtc"))
        close=parse_ms(row.get("barClosedAtUtc"))
        if (detect is None or close is None or
            detect<close or
            not 0<=now_ms-detect<=MAX_AFTER_DETECTION_MS):
            continue
        chosen.append(row)
    chosen.sort(key=lambda x:(x["firstDetectedAtUtc"],x["id"]))
    return chosen[:MAX_SENDS_PER_RUN]

def message_text(row,at_ms):
    detected=parse_ms(row["firstDetectedAtUtc"])
    close=parse_ms(row["barClosedAtUtc"])
    lag=round((detected-close)/60000,1)
    alert_lag=round((at_ms-detected)/1000,1)
    side="🟢 LONG" if row["direction"]=="LONG" else "🔴 SHORT"
    s=row["symbol"]
    return (
        "📡 Детектор — новый исследовательский кандидат\n"
        f"Актив: {s} | {side}\n"
        f"🕯 Свеча 15m закрыта: {row['barClosedAtMadrid']}\n"
        f"🔎 Обнаружено GitHub: {row['firstDetectedAtMadrid']}\n"
        f"⌛ От закрытия свечи до обнаружения: {lag} мин\n"
        f"📨 Задержка до отправки: ~{alert_lag} с\n"
        f"ID сигнала: {row['id']}\n"
        "Статус: EARLY_CANDIDATE_SHADOW\n"
        "Не торговый сигнал и не разрешение входа. "
        "Цена и актуальность сетапа требуют новой проверки в «Спекуляции»."
    )

def post_telegram(token,chat_id,text,*,timeout=10):
    # Do not expose auth to logs; never send through GET or echo endpoint.
    url="https://api.telegram.org/bot"+token+"/sendMessage"
    payload=urllib.parse.urlencode({
        "chat_id":chat_id,"text":text,"disable_web_page_preview":"true"
    }).encode("utf-8")
    req=urllib.request.Request(url,data=payload,method="POST",
                               headers={"Content-Type":"application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        raw=response.read(4096)
    packet=json.loads(raw)
    if not isinstance(packet,dict) or packet.get("ok") is not True:
        raise RuntimeError("TELEGRAM_API_NOT_OK")
    result=packet.get("result") or {}
    mid=result.get("message_id")
    timestamp=result.get("date")
    if not isinstance(mid,int) or not isinstance(timestamp,int):
        raise RuntimeError("TELEGRAM_UNVERIFIED_DELIVERY_RESPONSE")
    return {"telegramMessageId":mid,
            "telegramServerTimestampUtc":datetime.fromtimestamp(timestamp,timezone.utc).isoformat(),
            "telegramChatIdStored":False}

def perform(events,receipts,*,now_ms,send):
    """Pure-testable sender. Raises on remote failure, so failed events are retried."""
    pending=prepare_events(events,receipts,now_ms)
    existing=list(receipts["receipts"])
    published=[]
    for row in pending:
        message=message_text(row,now_ms)
        receipt=send(message)
        if not isinstance(receipt,dict) or not isinstance(receipt.get("telegramMessageId"),int):
            raise RuntimeError("SEND_WITHOUT_CONFIRMED_RECEIPT")
        existing.append({
            "id":row["id"],
            "symbol":row["symbol"],
            "direction":row["direction"],
            "barClosedAtUtc":row["barClosedAtUtc"],
            "firstDetectedAtUtc":row["firstDetectedAtUtc"],
            "notificationAttemptAtUtc":datetime.fromtimestamp(now_ms/1000,timezone.utc).isoformat(),
            **receipt
        })
        published.append(row["id"])
    return {"schemaVersion":VERSION,"receipts":existing,
            "researchOnly":True,"notTradeApproval":True},published

def main():
    token=os.environ.get("DETECTOR_TELEGRAM_BOT_TOKEN","").strip()
    chat=os.environ.get("DETECTOR_TELEGRAM_CHAT_ID","").strip()
    if not token or not chat:
        print("DETECTOR_TELEGRAM_NOT_CONFIGURED: no messages; no secrets printed")
        return
    events=json.loads(EVENTS.read_text(encoding="utf-8"))
    receipts=json.loads(RECEIPTS.read_text(encoding="utf-8")) if RECEIPTS.exists() else empty_receipts()
    now_ms=int(time.time()*1000)
    pending=prepare_events(events,receipts,now_ms)
    delivered=0
    for row in pending:
        try:
            receipt=post_telegram(token,chat,message_text(row,int(time.time()*1000)))
            if not isinstance(receipt,dict) or not isinstance(receipt.get("telegramMessageId"),int):
                raise RuntimeError("MISSING_VERIFIED_TELEGRAM_RECEIPT")
        except Exception as ex:
            # Do not print urllib errors: they may contain the bot token URL.
            print("DETECTOR_TELEGRAM_DELIVERY_ERROR:",type(ex).__name__,
                  "; previously acknowledged notifications remain on disk")
            raise SystemExit(2) from None
        current=list(receipts["receipts"])
        current.append({
            "id":row["id"],"symbol":row["symbol"],"direction":row["direction"],
            "barClosedAtUtc":row["barClosedAtUtc"],
            "firstDetectedAtUtc":row["firstDetectedAtUtc"],
            "notificationAttemptAtUtc":datetime.fromtimestamp(
                time.time(),timezone.utc).isoformat(),
            **receipt})
        receipts={"schemaVersion":VERSION,"receipts":current,
                  "researchOnly":True,"notTradeApproval":True}
        # Persist each successful receipt before the next network request.
        temp=RECEIPTS.with_suffix(".json.tmp")
        temp.write_text(json.dumps(receipts,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
        os.replace(temp,RECEIPTS)
        delivered+=1
    print("DETECTOR_TELEGRAM:",delivered,"confirmed messages;",
          "historical ledger alerts are suppressed; NO trading authority")
if __name__=="__main__":
    main()
