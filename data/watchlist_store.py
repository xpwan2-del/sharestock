from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


class WatchlistStore:
    def __init__(self, db_path: Optional[str] = None):
        root = Path(__file__).resolve().parent.parent
        self.db_path = Path(db_path) if db_path else root / "data_cache" / "watchlist.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT,
                    group_name TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, code)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    code TEXT,
                    name TEXT,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    signal_date TEXT,
                    fingerprint TEXT NOT NULL,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, fingerprint)
                )
            """)
            conn.commit()

    def list_watchlist(self, user_id: str = "default") -> pd.DataFrame:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT code, name, group_name, note, created_at, updated_at FROM watchlist WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows]) if rows else pd.DataFrame(columns=["code", "name", "group_name", "note", "created_at", "updated_at"])

    def add_stock(self, code: str, name: str = "", group_name: str = "默认", note: str = "", user_id: str = "default"):
        now = datetime.now().isoformat(timespec="seconds")
        code = str(code).strip().zfill(6)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO watchlist(user_id, code, name, group_name, note, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, code) DO UPDATE SET
                    name = excluded.name,
                    group_name = excluded.group_name,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (user_id, code, name.strip(), group_name.strip() or "默认", note.strip(), now, now),
            )
            conn.commit()

    def remove_stock(self, code: str, user_id: str = "default"):
        code = str(code).strip().zfill(6)
        with self._connect() as conn:
            conn.execute("DELETE FROM watchlist WHERE user_id = ? AND code = ?", (user_id, code))
            conn.commit()

    def create_alert(self, alert: Dict, user_id: str = "default"):
        now = datetime.now().isoformat(timespec="seconds")
        code = str(alert.get("code", "")).zfill(6) if alert.get("code") else ""
        fingerprint = alert.get("fingerprint") or f"{code}:{alert.get('alert_type')}:{alert.get('signal_date')}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO alerts(user_id, code, name, alert_type, severity, title, content, signal_date, fingerprint, is_read, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    user_id,
                    code,
                    alert.get("name", ""),
                    alert.get("alert_type", "signal"),
                    alert.get("severity", "medium"),
                    alert.get("title", "信号提醒"),
                    alert.get("content", ""),
                    str(alert.get("signal_date", "")),
                    fingerprint,
                    now,
                ),
            )
            conn.commit()

    def list_alerts(self, user_id: str = "default", limit: int = 100) -> pd.DataFrame:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, code, name, alert_type, severity, title, content, signal_date, is_read, created_at
                FROM alerts
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows]) if rows else pd.DataFrame(columns=["id", "code", "name", "alert_type", "severity", "title", "content", "signal_date", "is_read", "created_at"])

    def mark_read(self, alert_id: Optional[int] = None, user_id: str = "default"):
        with self._connect() as conn:
            if alert_id is None:
                conn.execute("UPDATE alerts SET is_read = 1 WHERE user_id = ?", (user_id,))
            else:
                conn.execute("UPDATE alerts SET is_read = 1 WHERE user_id = ? AND id = ?", (user_id, alert_id))
            conn.commit()

    def unread_count(self, user_id: str = "default") -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM alerts WHERE user_id = ? AND is_read = 0", (user_id,)).fetchone()
        return int(row["cnt"] if row else 0)

    def export_state(self, user_id: str = "default") -> str:
        return json.dumps({
            "watchlist": self.list_watchlist(user_id).to_dict("records"),
            "alerts": self.list_alerts(user_id).to_dict("records"),
        }, ensure_ascii=False, default=str)
