"""Cached query runners — the only place SQL is executed.

Every page calls `run_sql()` and nothing else. Connections are routed through
`db.connection` so the app obeys the repo's single-access-point rule.
"""

import sys
from pathlib import Path

import pandas as pd
import psycopg
import streamlit as st

# Streamlit puts the *script's* directory on sys.path, not the repo root, so the
# `db` package is not importable without this.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.connection import get_connection  # noqa: E402

QUERIES = ROOT / "queries"


@st.cache_resource(show_spinner=False)
def _conn() -> psycopg.Connection:
    """One connection per server process.

    autocommit keeps the session out of an idle-in-transaction state between
    reads — the app never writes.
    """
    conn = get_connection()
    conn.autocommit = True
    return conn


def _frame(cur: psycopg.Cursor) -> pd.DataFrame:
    cols = [d.name for d in cur.description or []]
    return pd.DataFrame(cur.fetchall(), columns=cols)


@st.cache_data(ttl=600, show_spinner=False)
def run_sql(name: str, **params) -> pd.DataFrame:
    """Run `queries/<name>` and return a DataFrame.

    Cache key is the file name plus params, so a season-wide query is computed
    once and shared by every page.
    """
    sql = (QUERIES / name).read_text()
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute(sql, params or None)
            return _frame(cur)
    except (psycopg.OperationalError, psycopg.InterfaceError):
        # The pooled connection went away (server restart, idle timeout).
        # Drop it and rebuild once.
        _conn.clear()
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute(sql, params or None)
            return _frame(cur)


@st.cache_data(ttl=600, show_spinner=False)
def leagues() -> pd.DataFrame:
    return run_sql("league_list.sql")


@st.cache_data(ttl=600, show_spinner=False)
def seasons(league_id: int | None = None) -> pd.DataFrame:
    return run_sql("season_list.sql", league_id=league_id)


@st.cache_data(ttl=600, show_spinner=False)
def sessions(season_id: int | None = None) -> pd.DataFrame:
    """One row per race — powers the season rail, selectbox and metric strip."""
    return run_sql("session_list.sql", season_id=season_id)


def refresh() -> None:
    """Clear every cached frame. The whole story after an ingest."""
    st.cache_data.clear()