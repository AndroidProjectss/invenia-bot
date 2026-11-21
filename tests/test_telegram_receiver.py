import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.runner import _run_telegram
from bot.telegram_bot import run_bot
from bot.storage import ensure_chat, get_messages, update_chat
from bot.telegram_state import snapshot


class TelegramReceiverTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"BOT_DB_PATH": str(Path(folder.name)/"test.db"),
                                      "TELEGRAM_BOT_TOKEN": "test-token", "AI_UNDERSTANDING_ENABLED": "0"})
        env.start()
        self.addCleanup(env.stop)

    def test_polling_recovers_after_timeout_and_saves_paused_chat_message(self):
        chat=ensure_chat('telegram','42')
        update_chat(chat['id'],bot_enabled=0)
        replies = iter([
            {'ok':True,'result':{'username':'test_bot'}},
            {'ok':True,'result':{'url':''}},
            TimeoutError(),
            {'ok':True,'result':[{'update_id':1,'message':{
                'message_id':99,'chat':{'id':42},'text':'Входящее сообщение',
                'from':{'first_name':'Клиент'}}}]},
            KeyboardInterrupt(),
        ])
        def api(*args,**kwargs):
            reply=next(replies)
            if isinstance(reply,BaseException): raise reply
            return reply
        with patch('bot.telegram_bot._api',side_effect=api), patch('bot.telegram_bot.time.sleep'):
            run_bot()
        messages=get_messages(chat['id'])
        self.assertEqual(len(messages),1)
        self.assertEqual(messages[0]['text'],'Входящее сообщение')
        self.assertEqual(messages[0]['direction'],'inbound')

    def test_supervisor_restarts_after_startup_failure(self):
        with patch('bot.telegram_bot.run_bot',side_effect=[SystemExit('network'),KeyboardInterrupt()]) as run, patch('bot.runner.time.sleep'):
            with self.assertRaises(KeyboardInterrupt):
                _run_telegram()
        self.assertEqual(run.call_count,2)

    def test_existing_webhook_is_reported_without_deleting_it(self):
        with patch('bot.telegram_bot._api',side_effect=[
            {'ok':True,'result':{'username':'test_bot'}},
            {'ok':True,'result':{'url':'https://example.test/hook'}},
        ]) as api, patch('bot.telegram_bot.time.sleep'):
            run_bot()
        self.assertEqual(snapshot()['status'],'webhook')
        self.assertEqual(api.call_count,2)
