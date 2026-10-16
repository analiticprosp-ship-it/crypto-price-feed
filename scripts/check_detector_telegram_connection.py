#!/usr/bin/env python3
"""Manual, read-only Telegram connection smoke test. No trading and no event creation.

Requires DETECTOR_TELEGRAM_BOT_TOKEN and DETECTOR_TELEGRAM_CHAT_ID as
GitHub Actions repository secrets. Does not print credentials, URLs or chat ID.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notify_detector_telegram import post_telegram

def main():
    token = os.environ.get("DETECTOR_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("DETECTOR_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("DETECTOR_TELEGRAM_TEST_NOT_CONFIGURED: both GitHub Actions secrets are required")
        return 2
    text = ("✅ Детектор: тест Telegram прошёл.\n"
            "Это проверка доставки, НЕ рыночный сигнал.\n"
            "Новые исследовательские LONG/SHORT будут отправляться отдельно, "
            "если они появятся и пройдут проверку свежести.")
    try:
        ack = post_telegram(token, chat_id, text)
    except Exception as exc:
        # Exceptions may embed the secret-bearing Bot API URL.
        print("DETECTOR_TELEGRAM_TEST_FAILED:", type(exc).__name__)
        return 3
    print("DETECTOR_TELEGRAM_TEST_DELIVERED: message confirmed by Telegram at",
          ack["telegramServerTimestampUtc"],
          "message ID", ack["telegramMessageId"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
