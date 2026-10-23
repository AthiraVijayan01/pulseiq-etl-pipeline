from src.db import get_connection
from run_data_quality_checks import CHECKS


TABLES = [
    "fact_monthly_headcount",
    "fact_salary",
    "fact_payroll",
    "fact_leave",
    "fact_attendance",
    "dim_employee",
    "dim_department",
    "dim_role",
    "dim_date",
    "dim_leave_type",
]

TEMP_TABLES = [
    """CREATE TEMP TABLE dim_employee (
        employee_key INTEGER,
        employee_id TEXT,
        is_current BOOLEAN,
        effective_from DATE,
        effective_to DATE,
        department_key INTEGER,
        role_key INTEGER
    )""",
    "CREATE TEMP TABLE dim_department (department_key INTEGER)",
    "CREATE TEMP TABLE dim_role (role_key INTEGER)",
    "CREATE TEMP TABLE dim_date (date_key INTEGER, full_date DATE)",
    "CREATE TEMP TABLE dim_leave_type (leave_type_key INTEGER)",
    """CREATE TEMP TABLE fact_attendance (
        employee_key INTEGER, date_key INTEGER, hours_worked NUMERIC
    )""",
    """CREATE TEMP TABLE fact_leave (
        employee_key INTEGER, leave_type_key INTEGER,
        leave_start_key INTEGER, leave_end_key INTEGER, days NUMERIC
    )""",
    """CREATE TEMP TABLE fact_payroll (
        employee_key INTEGER, pay_period TEXT,
        gross_pay NUMERIC, deductions NUMERIC, net_pay NUMERIC
    )""",
    """CREATE TEMP TABLE fact_salary (
        employee_key INTEGER, effective_date DATE, salary_amount NUMERIC
    )""",
    """CREATE TEMP TABLE fact_monthly_headcount (
        headcount INTEGER, month_key INTEGER, department_key INTEGER
    )""",
]

TEST_DATA = {
    "DQ01_current_employee_version": [
        """INSERT INTO dim_employee (employee_id, is_current)
           VALUES ('TEST01', FALSE), ('TEST01', FALSE)"""
    ],
    "DQ02_employee_effective_dates": [
        """INSERT INTO dim_employee
           (employee_id, effective_from, effective_to)
           VALUES ('TEST02', DATE '2026-12-31', DATE '2026-01-01')"""
    ],
    "DQ03_employee_department_reference": [
        """INSERT INTO dim_employee (employee_id, department_key)
           VALUES ('TEST03', 999)"""
    ],
    "DQ04_employee_role_reference": [
        """INSERT INTO dim_employee (employee_id, role_key)
           VALUES ('TEST04', 999)"""
    ],
    "DQ05_duplicate_attendance_employee_date": [
        """INSERT INTO fact_attendance (employee_key, date_key)
           VALUES (1, 1), (1, 1)"""
    ],
    "DQ06_attendance_references": [
        """INSERT INTO fact_attendance (employee_key, date_key)
           VALUES (999, 999)"""
    ],
    "DQ07_attendance_hours_range": [
        """INSERT INTO fact_attendance (employee_key, date_key, hours_worked)
           VALUES (1, 1, 25)"""
    ],
    "DQ08_leave_references": [
        """INSERT INTO fact_leave
           (employee_key, leave_type_key, leave_start_key, leave_end_key, days)
           VALUES (999, 999, 999, 999, 1)"""
    ],
    "DQ09_leave_days_and_date_order": [
        """INSERT INTO dim_date (date_key, full_date)
           VALUES (1, DATE '2026-12-31'), (2, DATE '2026-01-01')""",
        """INSERT INTO fact_leave
           (employee_key, leave_type_key, leave_start_key, leave_end_key, days)
           VALUES (1, 1, 1, 2, 1)"""
    ],
    "DQ10_payroll_employee_reference": [
        """INSERT INTO fact_payroll (employee_key, pay_period)
           VALUES (999, '2026-01')"""
    ],
    "DQ11_payroll_amounts_and_reconciliation": [
        """INSERT INTO fact_payroll
           (employee_key, pay_period, gross_pay, deductions, net_pay)
           VALUES (1, '2026-01', 100, 10, 95)"""
    ],
    "DQ12_duplicate_payroll_period": [
        """INSERT INTO fact_payroll (employee_key, pay_period)
           VALUES (1, '2026-01'), (1, '2026-01')"""
    ],
    "DQ13_salary_amount_and_duplicate_effective_date": [
        """INSERT INTO fact_salary (employee_key, effective_date, salary_amount)
           VALUES (1, DATE '2026-01-01', -100)"""
    ],
    "DQ14_monthly_headcount_integrity": [
        """INSERT INTO fact_monthly_headcount
           (headcount, month_key, department_key)
           VALUES (-1, 1, 1)"""
    ],
}


def main():
    checks = {item[0]: item for item in CHECKS}
    conn = get_connection()
    passed = 0
    failed = []

    try:
        with conn.cursor() as cur:
            for statement in TEMP_TABLES:
                cur.execute(statement)
            conn.commit()

            print("Testing DQ checks using temporary tables only.")
            print("Permanent warehouse tables are not modified.\n")

            for name, statements in TEST_DATA.items():
                _, severity, query, _ = checks[name]

                try:
                    cur.execute(
                        "TRUNCATE TABLE " + ", ".join(TABLES)
                    )

                    for statement in statements:
                        cur.execute(statement)

                    cur.execute(query)
                    detected = int(cur.fetchone()[0])

                    if detected > 0:
                        print(f"PASS | {name} | detected={detected}")
                        passed += 1
                    else:
                        print(f"FAIL | {name} | detected=0")
                        failed.append(name)

                except Exception as exc:
                    print(f"ERROR | {name} | {exc}")
                    failed.append(name)

                finally:
                    conn.rollback()

        print("\n" + "-" * 60)
        print(f"Negative tests passed: {passed}/{len(TEST_DATA)}")
        print(f"Failed or errored: {len(failed)}")

        if failed:
            print("Review these checks:")
            for name in failed:
                print(f" - {name}")

        return 1 if failed else 0

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
