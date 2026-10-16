
from src.db import database_connection

with database_connection() as conn:
    with conn.cursor() as cursor:
        queries = {
            "Department distribution": """
                SELECT d.department_name,
                       COUNT(DISTINCT e.employee_id) AS headcount
                FROM dim_employee e
                JOIN dim_department d
                    ON d.department_key = e.department_key
                WHERE e.joining_date <= DATE '2025-11-30'
                  AND (
                      e.leaving_date IS NULL
                      OR e.leaving_date > DATE '2025-11-30'
                  )
                GROUP BY d.department_name
                ORDER BY d.department_name;
            """,
            "Role distribution": """
                SELECT r.role_name,
                       COUNT(DISTINCT e.employee_id) AS headcount
                FROM dim_employee e
                JOIN dim_role r
                    ON r.role_key = e.role_key
                WHERE e.joining_date <= DATE '2025-11-30'
                  AND (
                      e.leaving_date IS NULL
                      OR e.leaving_date > DATE '2025-11-30'
                  )
                GROUP BY r.role_name
                ORDER BY r.role_name;
            """,
            "Monthly headcount snapshots": """
                SELECT dd.full_date,
                       d.department_name,
                       f.headcount
                FROM fact_monthly_headcount f
                JOIN dim_date dd
                    ON dd.date_key = f.month_key
                JOIN dim_department d
                    ON d.department_key = f.department_key
                ORDER BY dd.full_date, d.department_name;
            """
        }

        for title, query in queries.items():
            print(f"\n--- {title} ---")
            cursor.execute(query)
            for row in cursor.fetchall():
                print(row)
