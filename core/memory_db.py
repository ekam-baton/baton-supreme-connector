"""
Baton Supreme Connector — SQLite Session Persistence
Replaces the in-memory session dict with a SQLite-backed store.
Sessions survive server crashes and reboots.
"""

import sqlite3
import time
import uuid
import json
import os
from typing import List, Optional, Dict
from pydantic import BaseModel
from threading import Lock


DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "sessions.db")


class MemoryEntry(BaseModel):
    role: str
    content: str
    timestamp: float
    tool_call: Optional[str] = None
    tool_result: Optional[str] = None


class SQLiteSessionMemory:
    """
    SQLite-backed session store. Drop-in replacement for the in-memory SessionMemory.
    All methods are thread-safe.
    """

    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self._lock = Lock()
        os.makedirs(DB_DIR, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    tool_call TEXT,
                    tool_result TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)")
            conn.commit()
            conn.close()

    def _conn(self):
        return sqlite3.connect(DB_PATH)

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        with self._lock:
            conn = self._conn()
            conn.execute("INSERT INTO sessions (session_id, created_at) VALUES (?, ?)",
                         (session_id, time.time()))
            conn.commit()
            conn.close()
        return session_id

    def add_message(self, session_id: str, role: str, content: str,
                    tool_call: Optional[str] = None, tool_result: Optional[str] = None):
        with self._lock:
            conn = self._conn()
            # Ensure session exists
            existing = conn.execute("SELECT 1 FROM sessions WHERE session_id = ?",
                                    (session_id,)).fetchone()
            if not existing:
                conn.execute("INSERT INTO sessions (session_id, created_at) VALUES (?, ?)",
                             (session_id, time.time()))

            conn.execute("""
                INSERT INTO messages (session_id, role, content, timestamp, tool_call, tool_result)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, role, content, time.time(), tool_call, tool_result))

            # Trim to max history
            count = conn.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?",
                                 (session_id,)).fetchone()[0]
            if count > self.max_history:
                excess = count - self.max_history
                conn.execute("""
                    DELETE FROM messages WHERE id IN (
                        SELECT id FROM messages WHERE session_id = ?
                        ORDER BY timestamp ASC LIMIT ?
                    )
                """, (session_id, excess))

            conn.commit()
            conn.close()

    def get_messages(self, session_id: str) -> List[dict]:
        with self._lock:
            conn = self._conn()
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,)
            ).fetchall()
            conn.close()
            return [{"role": r[0], "content": r[1]} for r in rows]

    def get_full_history(self, session_id: str) -> List[MemoryEntry]:
        with self._lock:
            conn = self._conn()
            rows = conn.execute(
                """SELECT role, content, timestamp, tool_call, tool_result
                   FROM messages WHERE session_id = ? ORDER BY timestamp ASC""",
                (session_id,)
            ).fetchall()
            conn.close()
            return [
                MemoryEntry(role=r[0], content=r[1], timestamp=r[2],
                            tool_call=r[3], tool_result=r[4])
                for r in rows
            ]

    def list_sessions(self) -> List[dict]:
        with self._lock:
            conn = self._conn()
            rows = conn.execute("""
                SELECT s.session_id, s.created_at,
                       COUNT(m.id) as message_count,
                       MAX(m.timestamp) as last_activity
                FROM sessions s
                LEFT JOIN messages m ON s.session_id = m.session_id
                GROUP BY s.session_id
                ORDER BY s.created_at DESC
                LIMIT 100
            """).fetchall()
            conn.close()
            return [
                {
                    "session_id": r[0],
                    "created_at": r[1],
                    "message_count": r[2],
                    "last_activity": r[3],
                }
                for r in rows
            ]

    def delete_session(self, session_id: str):
        with self._lock:
            conn = self._conn()
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            conn.close()

    # Compatibility shim for security health check
    @property
    def _sessions(self) -> dict:
        """Returns a dict-like view for backward compatibility with health check scanner."""
        sessions = {}
        conn = self._conn()
        session_ids = [r[0] for r in conn.execute("SELECT session_id FROM sessions").fetchall()]
        for sid in session_ids:
            rows = conn.execute(
                "SELECT role, content, timestamp, tool_call, tool_result FROM messages WHERE session_id = ?",
                (sid,)
            ).fetchall()
            sessions[sid] = [
                MemoryEntry(role=r[0], content=r[1], timestamp=r[2], tool_call=r[3], tool_result=r[4])
                for r in rows
            ]
        conn.close()
        return sessions
