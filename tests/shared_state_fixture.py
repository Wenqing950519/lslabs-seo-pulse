"""A real cross-process transactional fixture; never available as a hosted backend."""
import json
import sqlite3

from seo_pulse_mcp.admission import SharedAdmissionStore


class SQLiteBackend:
    def __init__(self, filename):
        self.filename = str(filename)
        with sqlite3.connect(self.filename, timeout=20) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, body TEXT NOT NULL)")

    def run(self, operation):
        with sqlite3.connect(self.filename, timeout=20) as connection:
            connection.execute("BEGIN IMMEDIATE")

            class Transaction:
                def read(self, key):
                    row = connection.execute("SELECT body FROM documents WHERE id=?", (key,)).fetchone()
                    return json.loads(row[0]) if row else {}

                def write(self, key, data):
                    connection.execute("INSERT OR REPLACE INTO documents VALUES (?, ?)",
                                       (key, json.dumps(data, default=lambda value: value.isoformat())))

            return operation(Transaction())


def sqlite_store(filename, clock=None):
    options = {"clock": clock} if clock else {}
    return SharedAdmissionStore(SQLiteBackend(filename), namespace="test", hmac_key="test-key-" * 8, **options)
