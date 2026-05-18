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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS custom_strategies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    signal_type TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    conditions_json TEXT NOT NULL,
                    risk_rule_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, strategy_id)
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

    def list_custom_strategies(self, user_id: str = "default", enabled_only: bool = False) -> pd.DataFrame:
        query = """
            SELECT id, strategy_id, name, description, signal_type, enabled, conditions_json, risk_rule_json, created_at, updated_at
            FROM custom_strategies
            WHERE user_id = ?
        """
        params = [user_id]
        if enabled_only:
            query += " AND enabled = 1"
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        columns = ["id", "strategy_id", "name", "description", "signal_type", "enabled", "conditions_json", "risk_rule_json", "created_at", "updated_at"]
        return pd.DataFrame([dict(row) for row in rows]) if rows else pd.DataFrame(columns=columns)

    def save_custom_strategy(
        self,
        name: str,
        conditions: List[Dict],
        signal_type: str = "BUY",
        description: str = "",
        risk_rule: Optional[Dict] = None,
        strategy_id: Optional[str] = None,
        enabled: bool = True,
        user_id: str = "default",
    ):
        now = datetime.now().isoformat(timespec="seconds")
        strategy_id = strategy_id or f"custom_{int(datetime.now().timestamp())}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO custom_strategies(user_id, strategy_id, name, description, signal_type, enabled, conditions_json, risk_rule_json, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, strategy_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    signal_type = excluded.signal_type,
                    enabled = excluded.enabled,
                    conditions_json = excluded.conditions_json,
                    risk_rule_json = excluded.risk_rule_json,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    strategy_id,
                    name.strip() or "人工策略",
                    description.strip(),
                    signal_type.strip() or "BUY",
                    1 if enabled else 0,
                    json.dumps(conditions, ensure_ascii=False),
                    json.dumps(risk_rule or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()

    def delete_custom_strategy(self, strategy_id: str, user_id: str = "default"):
        with self._connect() as conn:
            conn.execute("DELETE FROM custom_strategies WHERE user_id = ? AND strategy_id = ?", (user_id, strategy_id))
            conn.commit()

    def set_custom_strategy_enabled(self, strategy_id: str, enabled: bool, user_id: str = "default"):
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "UPDATE custom_strategies SET enabled = ?, updated_at = ? WHERE user_id = ? AND strategy_id = ?",
                (1 if enabled else 0, now, user_id, strategy_id),
            )
            conn.commit()

    def unread_count(self, user_id: str = "default") -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM alerts WHERE user_id = ? AND is_read = 0", (user_id,)).fetchone()
        return int(row["cnt"] if row else 0)

    def export_state(self, user_id: str = "default") -> str:
        return json.dumps({
            "watchlist": self.list_watchlist(user_id).to_dict("records"),
            "alerts": self.list_alerts(user_id).to_dict("records"),
            "custom_strategies": self.list_custom_strategies(user_id).to_dict("records"),
        }, ensure_ascii=False, default=str)
