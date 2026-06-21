"""Smoke test: Alembic migration applies cleanly and matches the ORM models."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

import config as config_mod

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _cfg(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_upgrade_creates_expected_tables(tmp_path, monkeypatch):
    db = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{db}"
    monkeypatch.setattr(config_mod.settings, "database_url", url)

    cfg = _cfg(url)
    command.upgrade(cfg, "head")

    con = sqlite3.connect(db)
    try:
        tables = {r[0] for r in con.execute(
            "select name from sqlite_master where type='table'"
        )}
        bots_cols = {r[1] for r in con.execute("PRAGMA table_info(bots)")}
    finally:
        con.close()

    assert {"flows", "bots", "alembic_version"} <= tables
    assert {"id", "flow_id", "token", "channel", "webhook_secret"} <= bots_cols

    command.downgrade(cfg, "base")
    con = sqlite3.connect(db)
    try:
        tables_after = {r[0] for r in con.execute(
            "select name from sqlite_master where type='table'"
        )}
    finally:
        con.close()
    assert "flows" not in tables_after and "bots" not in tables_after
