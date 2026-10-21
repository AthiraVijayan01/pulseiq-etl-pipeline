
import sys
from uuid import uuid4

from src.db import get_connection


CHECKS = [
    (
        "DQ01_current_employee_version",
        "CRITICAL",
        """
        SELECT COUNT(*)
        FROM (
            SELECT employee_id
            FROM dim_employee
            GROUP BY employee_id
            HAVING COUNT(*) FILTER (WHERE is_current) <> 1
        ) bad
        """,
        "Each employee must have exactly one current SCD2 version.",
    ),
    (
        "DQ02_employee_effective_dates",
        "CRITICAL",
        """
        SELECT COUNT(*)
        FROM dim_employee
        WHERE effective_from > effective_to
        """,
        "Employee effective_from must not be later than effective_to.",
    ),
    (
        "DQ03_employee_department_reference",
        "CRITICAL",
        """
        SELECT COUNT(*)
        FROM dim_employee e
        WHERE e.department_key IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM dim_department d
              WHERE d.department_key = e.department_key
          )
        """,
        "Employee department references must resolve.",
    ),
    (
        "DQ04_employee_role_reference",
        "CRITICAL",
        """
        SELECT COUNT(*)
        FROM dim_employee e
        WHERE e.role_key IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM dim_role r
              WHERE r.role_key = e.role_key
          )
        """,
        "Employee role references must resolve.",
    ),
    (
        "DQ05_duplicate_attendance_employee_date",
        "CRITICAL",
        """
        SELECT COUNT(*)
        FROM (
            SELECT employee_key, date_key
            FROM fact_attendance
            GROUP BY employee_key, date_key
            HAVING COUNT(*) > 1
        ) bad
        """,
        "An employee should have at most one attendance record per date.",
    ),
    (
        "DQ06_attendance_references",
        "CRITICAL",
        """
        SELECT COUNT(*)
        FROM fact_attendance a
        WHERE NOT EXISTS (
            SELECT 1 FROM dim_employee e
            WHERE e.employee_key = a.employee_key
        )
        OR NOT EXISTS (
            SELECT 1 FROM dim_date d
            WHERE d.date_key = a.date_key
        )
        """,
        "Attendance employee and date references must resolve.",
    ),
    (
        "DQ07_attendance_hours_range",
        "WARNING",
        """
        SELECT COUNT(*)
        FROM fact_attendance
        WHERE hours_worked < 0 OR hours_worked > 24
        """,
        "Recorded attendance hours must be between 0 and 24.",
    ),
    (
        "DQ08_leave_references",
        "CRITICAL",
        """
        SELECT COUNT(*)
        FROM fact_leave l
        WHERE NOT EXISTS (
            SELECT 1 FROM dim_employee e
            WHERE e.employee_key = l.employee_key
        )
        OR NOT EXISTS (
            SELECT 1 FROM dim_leave_type t
            WHERE t.leave_type_key = l.leave_type_key
        )
        OR NOT EXISTS (
            SELECT 1 FROM dim_date d
            WHERE d.date_key = l.leave_start_key
        )
        OR NOT EXISTS (
            SELECT 1 FROM dim_date d
            WHERE d.date_key = l.leave_end_key
        )
        """,
        "Leave employee, type, and date references must resolve.",
    ),
    (
        "DQ09_leave_days_and_date_order",
        "CRITICAL",
        """
        SELECT COUNT(*)
        FROM fact_leave l
        JOIN dim_date s ON s.date_key = l.leave_start_key
        JOIN dim_date e ON e.date_key = l.leave_end_key
        WHERE l.days <= 0 OR s.full_date > e.full_date
        """,
        "Leave days must be positive and the start date cannot follow the end date.",
    ),
    (
        "DQ10_payroll_employee_reference",
        "CRITICAL",
        """
        SELECT COUNT(*)
        FROM fact_payroll p
        WHERE NOT EXISTS (
            SELECT 1 FROM dim_employee e
            WHERE e.employee_key = p.employee_key
        )
        """,
        "Every payroll row must reference an employee version.",
    ),
    (
        "DQ11_payroll_amounts_and_reconciliation",
        "CRITICAL",
        """
        SELECT COUNT(*)
        FROM fact_payroll
        WHERE gross_pay < 0
           OR deductions < 0
           OR net_pay < 0
           OR ABS(gross_pay - deductions - net_pay) > 0.01
        """,
        "Payroll amounts must be nonnegative and gross minus deductions must equal net pay.",
    ),
    (
        "DQ12_duplicate_payroll_period",
        "WARNING",
        """
        SELECT COUNT(*)
        FROM (
            SELECT employee_key, pay_period
            FROM fact_payroll
            GROUP BY employee_key, pay_period
            HAVING COUNT(*) > 1
        ) bad
        """,
        "Check for more than one payroll row per employee and pay period.",
    ),
    (
        "DQ13_salary_amount_and_duplicate_effective_date",
        "CRITICAL",
        """
        SELECT
            (SELECT COUNT(*)
             FROM fact_salary
             WHERE salary_amount < 0)
            +
            (SELECT COUNT(*)
             FROM (
                 SELECT employee_key, effective_date
                 FROM fact_salary
                 GROUP BY employee_key, effective_date
                 HAVING COUNT(*) > 1
             ) duplicates)
        """,
        "Salary must be nonnegative, with one row per employee and effective date.",
    ),
    (
        "DQ14_monthly_headcount_integrity",
        "CRITICAL",
        """
        SELECT
            (SELECT COUNT(*)
             FROM fact_monthly_headcount
             WHERE headcount < 0)
            +
            (SELECT COUNT(*)
             FROM fact_monthly_headcount h
             WHERE NOT EXISTS (
                 SELECT 1 FROM dim_date d
                 WHERE d.date_key = h.month_key
             )
             OR NOT EXISTS (
                 SELECT 1 FROM dim_department dep
                 WHERE dep.department_key = h.department_key
             ))
            +
            (SELECT COUNT(*)
             FROM (
                 SELECT month_key, department_key
                 FROM fact_monthly_headcount
                 GROUP BY month_key, department_key
                 HAVING COUNT(*) > 1
             ) duplicates)
        """,
        "Monthly headcount must be nonnegative, have valid references, and be unique per month and department.",
    ),
]


def should_fail_run(results):
    critical_failures = sum(
        r[1] == "CRITICAL" and r[3] in ("FAIL", "ERROR")
        for r in results
    )
    errors = sum(r[3] == "ERROR" for r in results)
    return critical_failures > 0 or errors > 0


def main():
    run_id = str(uuid4())
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS dq_results (
                    run_id UUID NOT NULL,
                    check_name TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    failed_rows BIGINT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT NOT NULL,
                    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (run_id, check_name)
                )
            """)
            conn.commit()

            results = []

            for name, severity, query, details in CHECKS:
                try:
                    cur.execute(query)
                    failed_rows = int(cur.fetchone()[0])
                    status = "PASS" if failed_rows == 0 else "FAIL"
                except Exception as exc:
                    conn.rollback()
                    failed_rows = -1
                    status = "ERROR"
                    details = f"{details} SQL error: {exc}"

                cur.execute(
                    """
                    INSERT INTO dq_results
                        (run_id, check_name, severity, failed_rows, status, details)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (run_id, name, severity, failed_rows, status, details),
                )
                conn.commit()
                results.append((name, severity, failed_rows, status))

        print(f"\nData Quality Run ID: {run_id}")
        print("-" * 82)
        print(f"{'CHECK':44} {'SEVERITY':10} {'BAD ROWS':10} STATUS")
        print("-" * 82)

        for name, severity, failed_rows, status in results:
            print(f"{name:44} {severity:10} {failed_rows:10} {status}")

        passed = sum(r[3] == "PASS" for r in results)
        failed = sum(r[3] == "FAIL" for r in results)
        errors = sum(r[3] == "ERROR" for r in results)

        print("-" * 82)
        print(
            f"Total: {len(results)} | Passed: {passed} | "
            f"Failed: {failed} | Errors: {errors}"
        )
        print("Results saved in PostgreSQL table: dq_results")

        if should_fail_run(results):
            sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
