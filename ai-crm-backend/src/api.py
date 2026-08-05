"""
REST API + статический сервер для CRM (чистый stdlib, без зависимостей).

Один процесс делает две вещи:
  1) отдаёт фронтенд (index.html, css, js) как статику;
  2) обслуживает REST-эндпоинты /api/deals и /api/clients поверх SQLite.

Поскольку фронтенд и API живут на одном origin, CORS не нужен.

Хранилище — обобщённое: на каждую коллекцию таблица (id TEXT, data TEXT-JSON).
Это позволяет хранить произвольные поля (в т.ч. пользовательские customValues и
теги-массивы) без миграций схемы — как раз то, что нужно конструктору полей.

Запуск (из корня crm-test-project или откуда угодно — пути берутся от __file__):
    python ai-crm-backend/src/api.py
затем открыть http://localhost:8080
"""
import json
import os
import sqlite3
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BACKEND_ROOT = Path(__file__).resolve().parent.parent      # ai-crm-backend/
FRONTEND_DIR = BACKEND_ROOT.parent                          # crm-test-project/ (тут index.html)
DB_PATH = BACKEND_ROOT / "data" / "crm_api.db"
PORT = int(os.getenv("PORT", "8080"))

# Коллекции, которые обслуживает API, и файлы для первичного посева данных.
# seed=None — коллекция стартует пустой (например, пользовательские поля).
COLLECTIONS = {
    "deals": {"prefix": "d", "seed": FRONTEND_DIR / "data" / "deals.json"},
    "clients": {"prefix": "c", "seed": FRONTEND_DIR / "data" / "clients.json"},
    "fields": {"prefix": "cf", "seed": None},
}


# ---------------- Слой данных ----------------

def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    for name in COLLECTIONS:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {name} (id TEXT PRIMARY KEY, data TEXT NOT NULL)"
        )
    return conn


def seed_if_empty():
    """При первом запуске наполняем таблицы из data/*.json, чтобы демо было не пустым."""
    conn = get_conn()
    for name, cfg in COLLECTIONS.items():
        count = conn.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()["c"]
        if count:
            continue
        seed_file = cfg["seed"]
        if seed_file is None or not seed_file.exists():
            continue
        records = json.loads(seed_file.read_text(encoding="utf-8"))
        for rec in records:
            conn.execute(
                f"INSERT OR REPLACE INTO {name} (id, data) VALUES (?, ?)",
                (rec["id"], json.dumps(rec, ensure_ascii=False)),
            )
        print(f"seeded {name}: {len(records)} записей")
    conn.commit()
    conn.close()


def list_items(name):
    conn = get_conn()
    rows = conn.execute(f"SELECT data FROM {name} ORDER BY rowid").fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


def create_item(name, obj):
    obj = dict(obj)
    obj["id"] = COLLECTIONS[name]["prefix"] + str(int(time.time() * 1000))
    conn = get_conn()
    conn.execute(
        f"INSERT INTO {name} (id, data) VALUES (?, ?)",
        (obj["id"], json.dumps(obj, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    return obj


def update_item(name, item_id, obj):
    obj = dict(obj)
    obj["id"] = item_id  # id из URL — источник истины, тело не может его переписать
    conn = get_conn()
    cur = conn.execute(
        f"UPDATE {name} SET data = ? WHERE id = ?",
        (json.dumps(obj, ensure_ascii=False), item_id),
    )
    conn.commit()
    found = cur.rowcount > 0
    conn.close()
    return obj if found else None


def delete_item(name, item_id):
    conn = get_conn()
    cur = conn.execute(f"DELETE FROM {name} WHERE id = ?", (item_id,))
    conn.commit()
    found = cur.rowcount > 0
    conn.close()
    return found


# ---------------- HTTP-обработчик ----------------

class Handler(SimpleHTTPRequestHandler):
    """Наследуемся от статического сервера и перехватываем только /api/*."""

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _parse_api(self):
        """Разбираем /api/<collection>[/<id>]. Возвращает (collection, id) или None."""
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return None
        parts = [p for p in path[len("/api/"):].split("/") if p]
        if not parts or parts[0] not in COLLECTIONS:
            return ("__unknown__", None)
        collection = parts[0]
        item_id = parts[1] if len(parts) > 1 else None
        return (collection, item_id)

    # -- GET: либо API-список, либо статика --
    def do_GET(self):
        api = self._parse_api()
        if api is None:
            return super().do_GET()  # обычный файл (index.html, css, js)
        collection, _ = api
        if collection == "__unknown__":
            return self._send_json({"error": "unknown collection"}, 404)
        return self._send_json(list_items(collection))

    def do_POST(self):
        api = self._parse_api()
        if api is None or api[0] == "__unknown__":
            return self._send_json({"error": "not found"}, 404)
        collection, _ = api
        try:
            obj = self._read_json_body()
        except json.JSONDecodeError:
            return self._send_json({"error": "invalid json"}, 400)
        return self._send_json(create_item(collection, obj), 201)

    def do_PUT(self):
        api = self._parse_api()
        if api is None or api[0] == "__unknown__":
            return self._send_json({"error": "not found"}, 404)
        collection, item_id = api
        if not item_id:
            return self._send_json({"error": "id required"}, 400)
        try:
            obj = self._read_json_body()
        except json.JSONDecodeError:
            return self._send_json({"error": "invalid json"}, 400)
        updated = update_item(collection, item_id, obj)
        if updated is None:
            return self._send_json({"error": "not found"}, 404)
        return self._send_json(updated)

    def do_DELETE(self):
        api = self._parse_api()
        if api is None or api[0] == "__unknown__":
            return self._send_json({"error": "not found"}, 404)
        collection, item_id = api
        if not item_id:
            return self._send_json({"error": "id required"}, 400)
        if not delete_item(collection, item_id):
            return self._send_json({"error": "not found"}, 404)
        return self._send_json({"ok": True})


def main():
    seed_if_empty()
    handler = partial(Handler, directory=str(FRONTEND_DIR))
    server = ThreadingHTTPServer(("0.0.0.0", PORT), handler)
    print(f"CRM API + фронтенд на http://localhost:{PORT}")
    print(f"  статика: {FRONTEND_DIR}")
    print(f"  база:    {DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлено")
        server.shutdown()


if __name__ == "__main__":
    main()
