"""Read-only schema introspection.

Prints every table in the `public` schema with its columns (type, nullability,
default), primary keys, foreign keys, and indexes. Issues only SELECTs against
the system catalogs. Run with: uv run python -m db.introspect
"""
from db.connection import connection


def main() -> None:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        tables = [r[0] for r in cur.fetchall()]
        if not tables:
            print("(no base tables found in schema 'public')")
            return

        for table in tables:
            print(f"\n=== {table} ===")

            cur.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table,),
            )
            print("columns:")
            for name, dtype, nullable, default in cur.fetchall():
                null = "NULL" if nullable == "YES" else "NOT NULL"
                dflt = f" default={default}" if default else ""
                print(f"  {name}: {dtype} {null}{dflt}")

            cur.execute(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = %s
                  AND tc.constraint_type = 'PRIMARY KEY'
                ORDER BY kcu.ordinal_position
                """,
                (table,),
            )
            pks = [r[0] for r in cur.fetchall()]
            if pks:
                print(f"primary key: ({', '.join(pks)})")

            cur.execute(
                """
                SELECT kcu.column_name,
                       ccu.table_name AS ref_table,
                       ccu.column_name AS ref_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                 AND tc.table_schema = ccu.table_schema
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = %s
                  AND tc.constraint_type = 'FOREIGN KEY'
                """,
                (table,),
            )
            fks = cur.fetchall()
            if fks:
                print("foreign keys:")
                for col, ref_table, ref_col in fks:
                    print(f"  {col} -> {ref_table}.{ref_col}")

            cur.execute(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = %s ORDER BY indexname",
                (table,),
            )
            idxs = cur.fetchall()
            if idxs:
                print("indexes:")
                for idxname, idxdef in idxs:
                    print(f"  {idxname}: {idxdef}")


if __name__ == "__main__":
    main()