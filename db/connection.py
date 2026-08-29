import os
from collections.abc import Generator
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv

load_dotenv()

def _get_dsn() -> str:
    # Build psycopg connection from environment vars
    host = os.environ["PGHOST"]
    port = os.environ.get("PGPORT", "5432")
    dbname = os.environ["PGDATABASE"]
    user = os.environ["PGUSER"]
    password = os.environ["PGPASSWORD"]

    return (
        f"host={host} port={port} dbname={dbname} user={user} password={password}"
    )

def get_connection() -> psycopg.Connection:
    return psycopg.connect(_get_dsn())

@contextmanager
def connection() -> Generator[psycopg.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()