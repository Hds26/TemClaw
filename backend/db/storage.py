"""
storage.py
----------
Thin async SQLite wrapper (via aiosqlite) for persisting provider configs,
skill configuration, conversations and messages.

Schema
------
providers(...)
skills_config(name PK, enabled, is_builtin, filename, created_at)
conversations(id PK, title, created_at, updated_at)
messages(id PK, conversation_id FK, role, content, tool_calls_json, created_at)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

DB_PATH = Path(os.getenv("DB_PATH", "data/agent.db"))


def _get_db() -> aiosqlite.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return aiosqlite.connect(DB_PATH)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS providers (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT    NOT NULL,
                provider_type  TEXT    NOT NULL DEFAULT 'openai',
                api_key        TEXT    NOT NULL DEFAULT '',
                base_url       TEXT,
                default_model  TEXT    NOT NULL DEFAULT 'gpt-4o-mini',
                enabled        INTEGER NOT NULL DEFAULT 1
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS skills_config (
                name       TEXT    PRIMARY KEY,
                enabled    INTEGER NOT NULL DEFAULT 1,
                is_builtin INTEGER NOT NULL DEFAULT 1,
                filename   TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT    NOT NULL DEFAULT 'New Chat',
                created_at TEXT    NOT NULL,
                updated_at TEXT    NOT NULL
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role            TEXT    NOT NULL,
                content         TEXT    NOT NULL DEFAULT '',
                tool_calls_json TEXT,
                created_at      TEXT    NOT NULL
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id)"
        )

        await db.commit()

        # Auto-seed provider from env vars on first launch
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM providers")
        row = await cursor.fetchone()
        if row[0] == 0:
            name = os.getenv("DEFAULT_PROVIDER_NAME")
            api_key = os.getenv("DEFAULT_PROVIDER_API_KEY")
            if name and api_key:
                await db.execute(
                    "INSERT INTO providers (name, provider_type, api_key, base_url, default_model) VALUES (?,?,?,?,?)",
                    (
                        name,
                        os.getenv("DEFAULT_PROVIDER_TYPE", "openai"),
                        api_key,
                        os.getenv("DEFAULT_PROVIDER_BASE_URL") or None,
                        os.getenv("DEFAULT_PROVIDER_MODEL", "gpt-4o-mini"),
                    ),
                )
                await db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: aiosqlite.Row) -> dict:
    d = dict(row)
    for key in ("enabled", "is_builtin"):
        if key in d:
            d[key] = bool(d[key])
    return d


# ---------------------------------------------------------------------------
# Providers CRUD
# ---------------------------------------------------------------------------

async def list_providers() -> list[dict]:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM providers ORDER BY id")
        rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_provider(provider_id: int) -> dict | None:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM providers WHERE id = ?", (provider_id,))
        row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def create_provider(data: dict) -> dict:
    async with _get_db() as db:
        cursor = await db.execute(
            "INSERT INTO providers (name, provider_type, api_key, base_url, default_model, enabled) VALUES (:name,:provider_type,:api_key,:base_url,:default_model,:enabled)",
            {
                "name": data["name"],
                "provider_type": data.get("provider_type", "openai"),
                "api_key": data.get("api_key", ""),
                "base_url": data.get("base_url") or None,
                "default_model": data.get("default_model", "gpt-4o-mini"),
                "enabled": 1 if data.get("enabled", True) else 0,
            },
        )
        await db.commit()
        new_id = cursor.lastrowid
    return await get_provider(new_id)


async def update_provider(provider_id: int, data: dict) -> dict | None:
    existing = await get_provider(provider_id)
    if not existing:
        return None
    merged = {**existing, **data}
    async with _get_db() as db:
        await db.execute(
            "UPDATE providers SET name=:name, provider_type=:provider_type, api_key=:api_key, base_url=:base_url, default_model=:default_model, enabled=:enabled WHERE id=:id",
            {
                "id": provider_id,
                "name": merged["name"],
                "provider_type": merged["provider_type"],
                "api_key": merged["api_key"],
                "base_url": merged.get("base_url") or None,
                "default_model": merged["default_model"],
                "enabled": 1 if merged.get("enabled", True) else 0,
            },
        )
        await db.commit()
    return await get_provider(provider_id)


async def delete_provider(provider_id: int) -> bool:
    async with _get_db() as db:
        cursor = await db.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        await db.commit()
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Skills Config CRUD
# ---------------------------------------------------------------------------

async def list_skills_config() -> list[dict]:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM skills_config ORDER BY created_at")
        rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_skill_config(name: str) -> dict | None:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM skills_config WHERE name = ?", (name,))
        row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def upsert_skill_config(
    name: str, filename: str, is_builtin: bool = True, enabled: bool = True
) -> dict:
    now = _now_iso()
    async with _get_db() as db:
        await db.execute(
            """
            INSERT INTO skills_config (name, enabled, is_builtin, filename, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET filename=excluded.filename, is_builtin=excluded.is_builtin
            """,
            (name, 1 if enabled else 0, 1 if is_builtin else 0, filename, now),
        )
        await db.commit()
    return await get_skill_config(name)


async def set_skill_enabled(name: str, enabled: bool) -> dict | None:
    existing = await get_skill_config(name)
    if not existing:
        return None
    async with _get_db() as db:
        await db.execute(
            "UPDATE skills_config SET enabled = ? WHERE name = ?",
            (1 if enabled else 0, name),
        )
        await db.commit()
    return await get_skill_config(name)


async def delete_skill_config(name: str) -> bool:
    async with _get_db() as db:
        cursor = await db.execute("DELETE FROM skills_config WHERE name = ?", (name,))
        await db.commit()
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Conversations CRUD
# ---------------------------------------------------------------------------

async def list_conversations() -> list[dict]:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def create_conversation(title: str = "New Chat") -> dict:
    now = _now_iso()
    async with _get_db() as db:
        cursor = await db.execute(
            "INSERT INTO conversations (title, created_at, updated_at) VALUES (?, ?, ?)",
            (title, now, now),
        )
        await db.commit()
        cid = cursor.lastrowid
    return {"id": cid, "title": title, "created_at": now, "updated_at": now}


async def get_conversation(conversation_id: int) -> dict | None:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        conv = dict(row)

        cursor2 = await db.execute(
            "SELECT id, role, content, tool_calls_json, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        )
        msgs = await cursor2.fetchall()
        conv["messages"] = [dict(m) for m in msgs]
    return conv


async def rename_conversation(conversation_id: int, title: str) -> dict | None:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now_iso(), conversation_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            return None
    return (await get_conversation(conversation_id))


async def delete_conversation(conversation_id: int) -> bool:
    async with _get_db() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        await db.commit()
    return cursor.rowcount > 0


async def append_message(
    conversation_id: int, role: str, content: str, tool_calls_json: str | None = None
) -> dict:
    now = _now_iso()
    async with _get_db() as db:
        cursor = await db.execute(
            "INSERT INTO messages (conversation_id, role, content, tool_calls_json, created_at) VALUES (?,?,?,?,?)",
            (conversation_id, role, content, tool_calls_json, now),
        )
        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        await db.commit()
        mid = cursor.lastrowid
    return {"id": mid, "conversation_id": conversation_id, "role": role, "content": content, "tool_calls_json": tool_calls_json, "created_at": now}
