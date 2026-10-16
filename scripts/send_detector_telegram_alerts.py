#!/usr/bin/env python3
"""Best-effort push of *newly journaled* Detector SHADOW events to Telegram.

Requires GitHub Action secrets DETECTOR_TELEGRAM_BOT_TOKEN and
DETECTOR_TELEGRAM_CHAT_ID. No secrets or endpoints stored in files.
Run AFTER successful journal publication. NEVER accept a trading command.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JOURNAL=ROOT/"detector-signal-events.json"
URL="https://github.com/analiticprosp-ship-it/crypto-price-feed/blob/main/detector-signal-events.json"
MAX_PER_RUN=25

def fresh_events(doc):
    if not isinstance(doc,dict) or doc.get("schemaVersion")!="detector-signal-events-1.0":
        raise ValueError("INVALID_SIGNAL_JOURNAL")
    if doc.get("researchOnly") is not True or doc.get("notTradeApproval") is not True:
        raise ValueError("SIGNAL_JOURNAL_GUARDS_MISSING")
    event_time=doc.get("generatedAtUtc")
    if not isinstance(event_time,str):
        raise ValueError("MISSING_JOURNAL_TIME")
    result=[]
    for e in doc.get("events",[]):
        if not isinstance(e,dict):continue
        if (e.get("journalFirstRecordedAtUtc")==event_time and
            e.get("notificationEligible") is True and
            e.get("initialSnapshotBaseline") is False and
            e.get("status")=="EARLY_CANDIDATE_SHADOW" and
            e.get("researchOnly") is True and
            e.get("notTradeApproval") is True and
            isinstance(e.get("firstDetectedAtMadrid"),str) and
            isinstance(e.get("signalCandleClosedAtMadrid"),str) and
            isinstance(e.get("detectionLagSeconds"),(int,float)) and
            e["detectionLagSeconds"]>=0):
            result.append(e)
    if len(result)>MAX_PER_RUN:
        # Never silently lose overflow. Caller fails safely rather than pretending alerted.
        raise ValueError("TOO_MANY_NEW_EVENTS_REQUIRES_MANUAL_REVIEW")
    return result

def format_message(e):
    direction=e["direction"]
    symbol=e["symbol"]
    if direction not in ("LONG","SHORT") or not isinstance(symbol,str) or not symbol.isalnum():
        raise ValueError("BAD_EVENT_IN_ALERT")
    lag=e["detectionLagSeconds"]/60
    return (
        "🔎 Детектор — ранний "+direction+" по "+symbol+"\n"
        "Сигнальная свеча закрылась: "+e["signalCandleClosedAtMadrid"]+" (Мадрид)\n"
        "Впервые обнаружено алгоритмом: "+e["firstDetectedAtMadrid"]+" (Мадрид)\n"
        "Задержка обнаружения: "+f"{lag:.1f}"+" мин\n"
        "Статус: EARLY_CANDIDATE_SHADOW — только исследование.\n"
        "Нет подтверждения прибыли, готовой цены входа или разрешения на сделку.\n"
        "Запись: "+URL+"\n"
    )

def deliver(token,chat_id,text):
    url="https://api.telegram.org/bot"+token+"/sendMessage"
    post=urllib.parse.urlencode({
        "chat_id":chat_id,"text":text,"disable_web_page_preview":"true"
    }).encode("utf-8")
    request=urllib.request.Request(url,data=post,method="POST",
                                   headers={"Content-Type":"application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request,timeout=12) as f:
            data=json.loads(f.read(4096))
            if data.get("ok") is not True:
                return False,"BOT_API_NOT_OK"
            return True,None
    except urllib.error.HTTPError as ex:
        return False,"TELEGRAM_HTTP_"+str(ex.code)
    except Exception as ex:
        return False,"TELEGRAM_"+type(ex).__name__

def main():
    doc=json.loads(JOURNAL.read_text(encoding="utf-8"))
    events=fresh_events(doc)
    if not events:
        print("TELEGRAM_NOTIFIER: NO_NEW_ELIGIBLE_SHADOW_SIGNALS")
        return 0
    token=os.environ.get("DETECTOR_TELEGRAM_BOT_TOKEN","")
    chat_id=os.environ.get("DETECTOR_TELEGRAM_CHAT_ID","")
    if not token or not chat_id:
        print("TELEGRAM_NOTIFIER: NOT_CONFIGURED; alerts are NOT being delivered; "+str(len(events))+" eligible events are in GitHub journal")
        return 0
    success=0
    for event in events:
        message=format_message(event)
        ok,reason=deliver(token,chat_id,message)
        if not ok:
            # Do not print URL containing bot token or request exception text.
            print("TELEGRAM_NOTIFIER: FAILED",reason,"eventId",event["eventId"])
            return 2
        success+=1
        time.sleep(0.1)
    print("TELEGRAM_NOTIFIER: DELIVERED",success,"SHADOW alerts")
    return 0

if __name__=="__main__":
    sys.exit(main())
