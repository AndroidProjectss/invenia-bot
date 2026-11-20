import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.admin_app import create_app
from bot.storage import get_messages, list_chats


class WhatsAppDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {
            "BOT_DB_PATH": str(Path(self.temp.name) / "test.db"),
            "WHATSAPP_APP_SECRET": "", "AI_UNDERSTANDING_ENABLED": "0",
        })
        env.start()
        self.addCleanup(env.stop)
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test", "ADMIN_PASSWORD": "test"})
        self.client = self.app.test_client()

    def post(self, value):
        return self.client.post('/webhooks/whatsapp', json={
            "entry": [{"changes": [{"field": "messages", "value": value}]}]
        })

    def incoming(self):
        return {"messages": [{"id": "in.1", "from": "996555000000", "type": "text",
                              "text": {"body": "Как проверить баланс?"}}]}

    def test_api_acceptance_is_not_delivery_and_receipt_updates_message(self):
        with patch('bot.admin_app.send_whatsapp', return_value={"messages": [{"id": "out.1"}]}):
            self.assertEqual(self.post(self.incoming()).status_code, 200)
        chat = list_chats()[0]
        self.assertEqual(get_messages(chat['id'])[-1]['delivery_status'], 'accepted')
        self.post({"statuses": [{"id": "out.1", "status": "delivered"}]})
        self.assertEqual(get_messages(chat['id'])[-1]['delivery_status'], 'delivered')
        self.client.post('/login', data={"password": "test"})
        page = self.client.get('/')
        self.assertIn('Доставлено'.encode(), page.data)
        with self.client.get('/static/live.js') as script:
            self.assertEqual(script.status_code, 200)

    def test_api_error_is_visible_and_does_not_crash_webhook(self):
        with patch('bot.admin_app.send_whatsapp', side_effect=RuntimeError('API 190: token expired')):
            self.assertEqual(self.post(self.incoming()).status_code, 200)
        chat = list_chats()[0]
        outgoing = get_messages(chat['id'])[-1]
        self.assertEqual(outgoing['delivery_status'], 'failed')
        self.assertIn('190', outgoing['delivery_error'])
        self.assertEqual(chat['status'], 'needs_human')

    def test_provider_failed_receipt_preserves_error(self):
        with patch('bot.admin_app.send_whatsapp', return_value={"messages": [{"id": "out.1"}]}):
            self.post(self.incoming())
        self.post({"statuses": [{"id": "out.1", "status": "failed",
                    "errors": [{"code": 131047, "title": "Re-engagement message"}]}]})
        outgoing = get_messages(list_chats()[0]['id'])[-1]
        self.assertEqual(outgoing['delivery_status'], 'failed')
        self.assertIn('131047', outgoing['delivery_error'])

    def test_configuration_is_protected_and_contains_no_tokens(self):
        self.assertEqual(self.client.get('/api/channels/whatsapp').status_code, 302)
        self.client.post('/login', data={"password": "test"})
        response = self.client.get('/api/channels/whatsapp')
        self.assertEqual(response.status_code, 200)
        self.assertIn('missing', response.json)
