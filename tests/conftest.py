"""Fixtures: build a fully seeded library database in a temp dir."""
import json
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from db import connect, init_db  # noqa: E402
from seed import SEED_DIR, load_seed_file  # noqa: E402


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lib")
    db = tmp / "library.db"
    conn = init_db(db)
    for path in sorted(SEED_DIR.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        load_seed_file(conn, doc, path.name)
    conn.execute("INSERT INTO library_builds (built_at, note) VALUES (datetime('now'), 'test seed')")
    conn.commit()
    conn.close()
    return db


@pytest.fixture()
def engine(db_path):
    from engine import RuleEngine
    eng = RuleEngine(db_path)
    yield eng
    eng.conn.close()
