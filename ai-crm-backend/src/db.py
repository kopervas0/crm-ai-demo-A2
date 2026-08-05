"""
Модель данных AI CRM Assistant.

Три таблицы:
  leads — клиенты/лиды (кто обратился: по звонку, из Telegram, из WhatsApp и т.д.)
  calls — звонки, привязаны к лиду. Хранят: аудио-ссылку (в реальной системе),
          транскрипт (текст звонка), краткое саммари и определённое "намерение" (intent)
  tasks — задачи для менеджера, могут быть созданы вручную или автоматически
          (например, AI решил, что после звонка нужен follow-up)

Никаких внешних библиотек — только sqlite3 из стандартной библиотеки Python,
поэтому проект запускается где угодно без pip install.
"""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    phone TEXT,
    messenger TEXT,           -- 'telegram' | 'whatsapp' | NULL
    messenger_id TEXT,        -- id пользователя в мессенджере, если пришёл оттуда
    source TEXT NOT NULL,     -- 'call' | 'telegram' | 'whatsapp' | 'manual'
    status TEXT NOT NULL DEFAULT 'new',  -- 'new' | 'in_progress' | 'closed'
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER REFERENCES leads(id),
    phone TEXT NOT NULL,
    direction TEXT NOT NULL,   -- 'inbound' | 'outbound'
    audio_ref TEXT,            -- путь/URL к записи звонка (в реальной системе — из телефонии)
    transcript TEXT,           -- результат AI-транскрибации
    summary TEXT,              -- краткое саммари от LLM-аналитики
    intent TEXT,               -- 'interested' | 'not_interested' | 'callback_requested' | 'question' | 'other'
    sentiment TEXT,            -- 'positive' | 'neutral' | 'negative'
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER REFERENCES leads(id),
    call_id INTEGER REFERENCES calls(id),
    title TEXT NOT NULL,
    due_at TEXT,
    status TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'done'
    created_by TEXT NOT NULL DEFAULT 'manual',  -- 'manual' | 'ai'
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection(db_path="data/crm.db"):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def find_or_create_lead(conn, *, name=None, phone=None, messenger=None,
                         messenger_id=None, source="manual"):
    """Ищем существующего лида по телефону или messenger_id, иначе создаём нового.
    Это типичная логика CRM: один и тот же клиент может написать в Telegram,
    потом позвонить — важно не плодить дубликаты карточек."""
    cur = conn.cursor()
    if phone:
        cur.execute("SELECT * FROM leads WHERE phone = ?", (phone,))
        row = cur.fetchone()
        if row:
            return row["id"]
    if messenger and messenger_id:
        cur.execute(
            "SELECT * FROM leads WHERE messenger = ? AND messenger_id = ?",
            (messenger, messenger_id),
        )
        row = cur.fetchone()
        if row:
            return row["id"]

    cur.execute(
        """INSERT INTO leads (name, phone, messenger, messenger_id, source)
           VALUES (?, ?, ?, ?, ?)""",
        (name, phone, messenger, messenger_id, source),
    )
    conn.commit()
    return cur.lastrowid


def create_task(conn, *, lead_id, title, call_id=None, due_at=None, created_by="manual"):
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO tasks (lead_id, call_id, title, due_at, created_by)
           VALUES (?, ?, ?, ?, ?)""",
        (lead_id, call_id, title, due_at, created_by),
    )
    conn.commit()
    return cur.lastrowid


def save_call(conn, *, lead_id, phone, direction, audio_ref=None,
              transcript=None, summary=None, intent=None, sentiment=None):
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO calls (lead_id, phone, direction, audio_ref, transcript, summary, intent, sentiment)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (lead_id, phone, direction, audio_ref, transcript, summary, intent, sentiment),
    )
    conn.commit()
    return cur.lastrowid


def fetch_all(conn, table):
    cur = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC")
    return [dict(row) for row in cur.fetchall()]
