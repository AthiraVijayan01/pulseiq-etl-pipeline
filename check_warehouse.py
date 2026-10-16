
from src.db import database_connection

with database_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT
                e.employee_id,
                e.first_name,
                e.last_name,
                d.department_name,
                r.role_name
            FROM dim_employee e
            JOIN dim_department d
                ON e.department_key = d.department_key
            JOIN dim_role r
                ON e.role_key = r.role_key
            ORDER BY e.employee_id;
        """)

        print("Employee roles in PostgreSQL:")
        for row in cursor.fetchall():
            print(row)
