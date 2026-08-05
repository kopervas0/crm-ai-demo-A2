"""
Сквозная демонстрация AI-цепочки CRM (запускается без зависимостей и без ключей).

Сценарий на каждый входящий звонок:
    входящий звонок → транскрипт → AI-анализ (summary/intent/sentiment)
        → сохранение звонка в БД → авто-задача менеджеру (если нужна)

В конце печатаем получившуюся картину: лиды, звонки с разметкой и задачи,
отдельно помечая те, что создал AI.

Запуск (из папки ai-crm-backend):
    python scripts/demo.py

БД создаётся во временном файле, чтобы демо было воспроизводимым и ничего не засоряло.
"""
import sys
import tempfile
from pathlib import Path

# На Windows консоль по умолчанию cp1251 и падает на юникоде (стрелки, эмодзи).
# Принудительно переключаем вывод на UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Позволяем импортировать src/ без установки пакета.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import db  # noqa: E402
from ai import analyze_transcript, decide_followup  # noqa: E402


# Демо-звонки: (имя, телефон, канал, направление, текст транскрипта)
SAMPLE_CALLS = [
    ("Иван Петров", "79991234567", "call", "inbound",
     "Здравствуйте, мне интересно ваше предложение по фулфилменту. Сколько стоит хранение на складе?"),
    ("Ольга Смирнова", "79992221100", "call", "inbound",
     "Сейчас неудобно говорить, перезвоните мне, пожалуйста, позже во второй половине дня."),
    ("Сергей Ким", "79993334455", "call", "outbound",
     "Спасибо, нам это не интересно, у вас слишком дорого по сравнению с текущим подрядчиком."),
    ("Мария Волкова", "79995556677", "call", "inbound",
     "У меня вопрос: можно ли уточнить, как вы считаете тариф за приёмку товара на Wildberries?"),
]


def run():
    tmp_db = Path(tempfile.gettempdir()) / "crm_demo.db"
    if tmp_db.exists():
        tmp_db.unlink()
    conn = db.get_connection(str(tmp_db))

    print("=" * 70)
    print("AI CRM — демонстрация цепочки: звонок → транскрибация → аналитика → задача")
    print("=" * 70)

    for name, phone, source, direction, transcript in SAMPLE_CALLS:
        # 1) Находим или заводим лида (дедупликация по телефону — внутри db).
        lead_id = db.find_or_create_lead(conn, name=name, phone=phone, source=source)

        # 2) AI-аналитика транскрипта (реальный LLM или rule-based мок — прозрачно).
        analysis = analyze_transcript(transcript)

        # 3) Сохраняем звонок с разметкой.
        call_id = db.save_call(
            conn, lead_id=lead_id, phone=phone, direction=direction,
            transcript=transcript, summary=analysis["summary"],
            intent=analysis["intent"], sentiment=analysis["sentiment"],
        )

        # 4) AI решает, нужен ли follow-up, и сам ставит задачу.
        followup_title = decide_followup(analysis)
        auto_task = ""
        if followup_title:
            db.create_task(conn, lead_id=lead_id, call_id=call_id,
                           title=followup_title, created_by="ai")
            auto_task = f"  →  AI создал задачу: «{followup_title}»"

        print(f"\n📞 {name} ({phone}) — {direction}")
        print(f"   intent={analysis['intent']}  sentiment={analysis['sentiment']}")
        print(f"   summary: {analysis['summary']}")
        if auto_task:
            print(auto_task)

    # Итоговая картина из БД.
    print("\n" + "=" * 70)
    leads = db.fetch_all(conn, "leads")
    calls = db.fetch_all(conn, "calls")
    tasks = db.fetch_all(conn, "tasks")
    ai_tasks = [t for t in tasks if t["created_by"] == "ai"]

    print(f"Итого в базе: лидов={len(leads)}, звонков={len(calls)}, задач={len(tasks)} "
          f"(из них AI создал {len(ai_tasks)})")
    print("\nЗадачи, поставленные AI автоматически:")
    for t in ai_tasks:
        print(f"  • [{t['status']}] {t['title']}")

    conn.close()
    print("\nГотово. БД демо:", tmp_db)


if __name__ == "__main__":
    run()
