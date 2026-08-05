"""
Тесты слоя данных и AI-аналитики. Без внешних зависимостей — только стандартный
модуль unittest, поэтому запускаются как:

    python -m unittest discover -s tests        (из папки ai-crm-backend)

Используем БД в памень (:memory:), чтобы тесты были быстрыми и изолированными.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import db  # noqa: E402
import ai  # noqa: E402


class DbTests(unittest.TestCase):
    def setUp(self):
        # ":memory:" — свежая пустая БД на каждый тест.
        self.conn = db.get_connection(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_create_lead(self):
        lead_id = db.find_or_create_lead(self.conn, name="Тест", phone="79990000000", source="call")
        self.assertIsInstance(lead_id, int)
        leads = db.fetch_all(self.conn, "leads")
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["name"], "Тест")

    def test_dedup_by_phone(self):
        """Повторное обращение с тем же телефоном не должно плодить нового лида."""
        first = db.find_or_create_lead(self.conn, name="Иван", phone="79991112233", source="call")
        second = db.find_or_create_lead(self.conn, name="Иван (WA)", phone="79991112233",
                                        source="whatsapp")
        self.assertEqual(first, second)
        self.assertEqual(len(db.fetch_all(self.conn, "leads")), 1)

    def test_dedup_by_messenger(self):
        """Дедупликация также работает по паре messenger + messenger_id."""
        first = db.find_or_create_lead(self.conn, messenger="telegram",
                                       messenger_id="tg_42", source="telegram")
        second = db.find_or_create_lead(self.conn, messenger="telegram",
                                        messenger_id="tg_42", source="telegram")
        self.assertEqual(first, second)
        self.assertEqual(len(db.fetch_all(self.conn, "leads")), 1)

    def test_save_call_and_link(self):
        lead_id = db.find_or_create_lead(self.conn, phone="79990000001", source="call")
        call_id = db.save_call(self.conn, lead_id=lead_id, phone="79990000001",
                               direction="inbound", transcript="тест", intent="interested")
        calls = db.fetch_all(self.conn, "calls")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["lead_id"], lead_id)
        self.assertEqual(calls[0]["id"], call_id)

    def test_create_task_ai_flag(self):
        lead_id = db.find_or_create_lead(self.conn, phone="79990000002", source="call")
        db.create_task(self.conn, lead_id=lead_id, title="Перезвонить", created_by="ai")
        tasks = db.fetch_all(self.conn, "tasks")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["created_by"], "ai")
        self.assertEqual(tasks[0]["status"], "open")


class AiTests(unittest.TestCase):
    def test_intent_interested(self):
        result = ai.analyze_transcript("Мне интересно, сколько стоит ваш тариф?")
        self.assertEqual(result["intent"], "interested")
        self.assertIn(result["sentiment"], ai.SENTIMENTS)

    def test_intent_callback(self):
        result = ai.analyze_transcript("Сейчас неудобно, перезвоните позже пожалуйста.")
        self.assertEqual(result["intent"], "callback_requested")

    def test_intent_not_interested_negative(self):
        result = ai.analyze_transcript("Спасибо, нам не интересно, у вас дорого.")
        self.assertEqual(result["intent"], "not_interested")
        self.assertEqual(result["sentiment"], "negative")

    def test_analyze_always_valid_values(self):
        """Что бы ни пришло на вход — intent/sentiment всегда из допустимого набора."""
        result = ai.analyze_transcript("абракадабра без ключевых слов")
        self.assertIn(result["intent"], ai.INTENTS)
        self.assertIn(result["sentiment"], ai.SENTIMENTS)

    def test_followup_created_for_callback(self):
        analysis = {"intent": "callback_requested", "sentiment": "neutral", "summary": ""}
        self.assertIsNotNone(ai.decide_followup(analysis))

    def test_no_followup_for_not_interested(self):
        analysis = {"intent": "not_interested", "sentiment": "negative", "summary": ""}
        self.assertIsNone(ai.decide_followup(analysis))


if __name__ == "__main__":
    unittest.main()
