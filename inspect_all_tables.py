from src.db import get_connection

conn = get_connection()

try:
    query = """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema NOT IN (
            'information_schema',
            'pg_catalog'
        )
        ORDER BY table_schema, table_name
    """

    rows = conn.execute(query).fetchall()

    print("\nALL DATABASE TABLES AND VIEWS")
    print("=" * 50)

    for schema, table, kind in rows:
        print(f"{schema}.{table} ({kind})")

finally:
    conn.close()
