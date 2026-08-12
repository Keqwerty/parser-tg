from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ItemState:
    source_id: str
    item_key: str
    content_hash: str
    status: str
    filters: tuple[str, ...]
    delivery: str | None


class StateStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                source_id TEXT NOT NULL,
                item_key TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                filters_json TEXT NOT NULL,
                delivery TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (source_id, item_key)
            )
            """
        )
        self._connection.commit()

    def get(self, source_id: str, item_key: str) -> ItemState | None:
        row = self._connection.execute(
            """
            SELECT source_id, item_key, content_hash, status, filters_json, delivery
            FROM items WHERE source_id = ? AND item_key = ?
            """,
            (source_id, item_key),
        ).fetchone()
        if row is None:
            return None
        return ItemState(row[0], row[1], row[2], row[3], tuple(json.loads(row[4])), row[5])

    def put(
        self,
        source_id: str,
        item_key: str,
        content_hash: str,
        status: str,
        filters: tuple[str, ...] = (),
        delivery: str | None = None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO items (
                source_id, item_key, content_hash, status, filters_json, delivery, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, item_key) DO UPDATE SET
                content_hash = excluded.content_hash,
                status = excluded.status,
                filters_json = excluded.filters_json,
                delivery = excluded.delivery,
                updated_at = excluded.updated_at
            """,
            (
                source_id,
                item_key,
                content_hash,
                status,
                json.dumps(filters, ensure_ascii=False),
                delivery,
                datetime.now(UTC).isoformat(),
            ),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
