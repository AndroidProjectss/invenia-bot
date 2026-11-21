import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from bot.admin_app import create_app
from bot.analytics import build_analytics
from bot.storage import ensure_chat, add_message, record_delivery, save_answer_details, _connect


class AnalyticsTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {'BOT_DB_PATH':str(Path(folder.name)/'analytics.db')})
        env.start()
        self.addCleanup(env.stop)
        self.chat = ensure_chat('telegram','123')['id']

    def message(self, text, mode=None, sender='bot', chat=None):
        chat = chat or self.chat
        incoming=add_message(chat,'inbound','customer',text)
        outgoing=add_message(chat,'outbound',sender,'Ответ',mode=mode) if mode else None
        return incoming,outgoing

    def test_outcomes_grouping_commands_and_delivery(self):
        self.message('/start','command')
        self.message('Привет','greeting')
        _, answer=self.message('Как проверить баланс?','direct')
        save_answer_details(answer['id'],{'faq_id':1})
        self.message('как проверить баланс!','refuse')
        self.message('Нет интернета','buttons')
        self.message('Помогите','manual',sender='operator')
        self.message('Ещё вопрос')
        _, failed=self.message('Роуминг','direct')
        record_delivery(failed['id'],'failed',error='test')
        add_message(self.chat,'inbound','customer','Выбор кнопки',mode='selection')
        stats=build_analytics(days=0)
        self.assertEqual(stats['total'],6)
        self.assertEqual(stats['answered'],1)
        self.assertEqual(stats['outcomes']['unanswered'],1)
        self.assertEqual(stats['outcomes']['uncertain'],1)
        self.assertEqual(stats['outcomes']['pending'],1)
        self.assertEqual(stats['outcomes']['failed'],1)
        self.assertEqual(stats['outcomes']['operator'],1)
        self.assertEqual(stats['questions'][0]['count'],2)
        self.assertIn('Как проверить баланс?', [topic['title'] for topic in stats['topics']])

    def test_channel_filter_and_period_in_bishkek(self):
        incoming,outgoing=self.message('Вопрос ночью','direct')
        with _connect() as db:
            db.execute("UPDATE messages SET created_at=?",('2026-11-20T19:00:00+00:00',))
        stats=build_analytics(days=1,now=datetime(2026,11,21,1,tzinfo=timezone.utc))
        self.assertEqual(stats['total'],1)
        self.assertEqual(stats['timeline'][0]['total'],1)
        whatsapp=ensure_chat('whatsapp','456')['id']
        self.message('Вопрос WhatsApp','direct',chat=whatsapp)
        self.assertEqual(build_analytics(days=0,channel='whatsapp')['total'],1)

    def test_statistics_are_protected_and_rendered(self):
        self.message('Нет ответа, +996 555 123456, test@example.com','refuse')
        app=create_app({'TESTING':True,'SECRET_KEY':'test','ADMIN_PASSWORD':'test'})
        client=app.test_client()
        self.assertEqual(client.get('/analytics').status_code,302)
        client.post('/login',data={'password':'test'})
        with client.get('/analytics?period=all') as response:
            self.assertEqual(response.status_code,200)
            self.assertIn('Частые вопросы'.encode(),response.data)
            self.assertIn('Где нужна помощь'.encode(),response.data)
            self.assertNotIn(b'test@example.com',response.data)
            self.assertNotIn(b'555 123456',response.data)
        for asset in ('analytics.css','analytics.js'):
            with client.get('/static/'+asset) as response:
                self.assertEqual(response.status_code,200)

    def test_empty_analytics_has_no_division_error(self):
        stats=build_analytics(days=7)
        self.assertEqual(stats['rate'],0)
        self.assertEqual(len(stats['timeline']),7)
