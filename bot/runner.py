"""Совместный запуск админки, webhook и Telegram одним процессом."""

from __future__ import annotations

import os
import threading
import traceback

from bot.admin_app import _load_dotenv, run_admin


def _run_telegram() -> None:
    try:
        from bot.telegram_bot import run_bot

        run_bot()
    except SystemExit as error:
        print(f"Telegram остановлен: {error}")
    except Exception:
        print("Telegram-бот завершился с ошибкой:")
        traceback.print_exc()


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
        print("- Telegram-бот: пропущен, TELEGRAM_BOT_TOKEN не заполнен")
    print("Остановка всех сервисов: Ctrl+C")

    # Web-сервер остаётся в главном потоке и управляет временем жизни процесса.
    run_admin()
