
from src.db import database_connection

report_date = "2025-11-30"

with database_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                e.employee_id,
                e.first_name,
                e.last_name,
                d.department_name,
                e.joining_date,
                e.leaving_date,
                e.effective_from,
                e.effective_to
            FROM dim_employee e
            JOIN dim_department d
                ON d.department_key = e.department_key
            WHERE e.joining_date <= %s
              AND (
                  e.leaving_date IS NULL
                  OR e.leaving_date > %s
              )
              AND e.effective_from <= %s
              AND e.effective_to >= %s
            ORDER BY e.employee_id;
            """,
            (report_date, report_date, report_date, report_date),
        )

        rows = cursor.fetchall()

        print(f"Active employees on {report_date}: {len(rows)}")

        for row in rows:
            print(row)
