from src.db import get_connection

conn = get_connection()

try:
    rows = conn.execute("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = 'phase2'
        ORDER BY table_name
    """).fetchall()

    for row in rows:
        print(f"{row[0]}.{row[1]}")

finally:
    conn.close()
