from src.db import get_connection

conn = get_connection()

try:
    query = """
        SELECT
            table_name,
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_schema = 'phase3'
        ORDER BY table_name, ordinal_position
    """

    rows = conn.execute(query).fetchall()

    current_table = None

    print("\nPHASE3 TABLE STRUCTURE")
    print("=" * 55)

    for table, column, dtype in rows:
        if table != current_table:
            current_table = table
            print(f"\n{table}")

        print(f"  {column} ({dtype})")

finally:
    conn.close()
