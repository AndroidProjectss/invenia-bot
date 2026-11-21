"""Совместный запуск админки, webhook и Telegram одним процессом."""

from __future__ import annotations

import os
import threading
import traceback
import time

from bot.admin_app import _load_dotenv, run_admin


def _run_telegram() -> None:
    from bot.telegram_bot import run_bot
    from bot.telegram_state import report

    while True:
        try:
            report("starting", "Подключение к Telegram")
            run_bot()
        except (Exception, SystemExit) as error:
            # Текст сетевого исключения может содержать URL с токеном.
            report("error", f"Приёмник остановился ({type(error).__name__}), повтор через 5 секунд")
            print(f"Telegram: {type(error).__name__}. Перезапуск через 5 секунд.", flush=True)
        else:
            report("restarting", "Приёмник завершился, перезапуск через 5 секунд")
        time.sleep(5)


def run_all() -> None:
    """Запускает web-приложение и настроенные фоновые каналы."""
    _load_dotenv()
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

    print("Запуск Invenia Support:")
    print("- админка и WhatsApp webhook: включены")
    if telegram_token:
        telegram = threading.Thread(
            target=_run_telegram,
            name="invenia-telegram",
            daemon=True,
        )
        telegram.start()
        print("- Telegram-бот: включён")
    else:
        from bot.telegram_state import report
        report("disabled", "TELEGRAM_BOT_TOKEN не заполнен, приёмник не запущен")
        print("- Telegram-бот: пропущен, TELEGRAM_BOT_TOKEN не заполнен")
    print("Остановка всех сервисов: Ctrl+C")

    # Web-сервер остаётся в главном потоке и управляет временем жизни процесса.
    run_admin()
