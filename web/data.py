"""Query runner for the web spike — no Streamlit, same queries/ directory.

Deliberately thin: this exists to prove the SQL layer is frontend-independent.
A real port would add caching; 21 races answer fast enough without it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.connection import get_connection  # noqa: E402

QUERIES = ROOT / "queries"
_conn = None


def _connection():
    global _conn
    if _conn is None or _conn.closed:
        _conn = get_connection()
        _conn.autocommit = True
    return _conn


def rows(name: str, **params) -> list[dict]:
    """Run queries/<name> and return a list of dicts."""
    sql = (QUERIES / name).read_text()
    with _connection().cursor() as cur:
        cur.execute(sql, params or None)
        cols = [d.name for d in cur.description or []]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def one(name: str, **params) -> dict | None:
    found = rows(name, **params)
    return found[0] if found else None
