from datetime import datetime, timedelta, timezone

from src.db import get_connection
from run_official_dq_checks import CHECKS

SOURCE_TABLES = [
    "fact_payroll",
    "fact_ledger",
    "dim_employee",
    "fact_attendance_monthly",
    "fact_invoice",
    "fact_expense",
    "fact_task",
    "fact_leave",
    "fact_attrition_risk",
]

FIXTURES = {
    "DQ-C01": [
        ("fact_payroll",
         """INSERT INTO pg_temp.fact_payroll
            (payroll_item_id, run_id, period_end_date, employer_cost)
            VALUES ('TEST-P1','TEST-R1','2026-06-30','100')"""),
        ("fact_ledger",
         """INSERT INTO pg_temp.fact_ledger
            (line_id, entry_id, entry_date, account_code,
             signed_amount_debit_positive)
            VALUES ('TEST-L1','TEST-J1','2026-06-30','5001','90')"""),
    ],
    "DQ-C02": [
        ("fact_ledger",
         """INSERT INTO pg_temp.fact_ledger
            (line_id, entry_id, debit, credit)
            VALUES ('TEST-L2','TEST-J2','100','90')"""),
    ],
    "DQ-C03": [
        ("fact_payroll",
         """INSERT INTO pg_temp.fact_payroll
            (payroll_item_id, employee_id, run_id)
            VALUES ('TEST-P3A','TEST-E3','TEST-R3'),
                   ('TEST-P3B','TEST-E3','TEST-R3')"""),
    ],
    "DQ-C04": [
        ("fact_payroll",
         """INSERT INTO pg_temp.fact_payroll
            (payroll_item_id, employee_id, run_id)
            VALUES ('TEST-P4','TEST-MISSING','TEST-R4')"""),
    ],
    "DQ-C05": [
        ("dim_employee",
         """INSERT INTO pg_temp.dim_employee
            (employee_key, employee_id, exit_date, is_current)
            VALUES ('901','TEST-E5','2024-01-15','Y')"""),
        ("fact_attendance_monthly",
         """INSERT INTO pg_temp.fact_attendance_monthly
            (attendance_fact_id, employee_id, period_end_date)
            VALUES ('TEST-A5','TEST-E5','2024-02-29')"""),
    ],
    "DQ-C06": [
        ("fact_attendance_monthly",
         """INSERT INTO pg_temp.fact_attendance_monthly
            (attendance_fact_id, employee_id, period_end_date,
             unpaid_absence_days)
            VALUES ('TEST-A6','TEST-E6','2024-02-29','2')"""),
    ],
    "DQ-C07": [
        ("fact_invoice",
         """INSERT INTO pg_temp.fact_invoice
            (invoice_id, amount_paid, total_amount, balance_due)
            VALUES ('TEST-I7','110','100','0')"""),
    ],
    "DQ-C08": [
        ("fact_expense",
         """INSERT INTO pg_temp.fact_expense
            (expense_id, total_amount, amount_excl_gst, gst_amount)
            VALUES ('TEST-X8','110','100','5')"""),
    ],
    "DQ-C09": [
        ("fact_task",
         """INSERT INTO pg_temp.fact_task
            (task_id, status, started_date, completed_date)
            VALUES ('TEST-T9','Done','2024-02-02','2024-02-01')"""),
    ],
    "DQ-C10": [
        ("fact_leave",
         """INSERT INTO pg_temp.fact_leave
            (leave_request_id, start_date, end_date)
            VALUES ('TEST-V10','2024-03-05','2024-03-01')"""),
    ],
    "DQ-C11": [
        ("etl_run_log",
         """INSERT INTO pg_temp.etl_run_log
            (run_id, log_file, started_at, finished_at, status)
            VALUES (1, 'negative-test',
                    %s, %s, 'SUCCESS')"""),
        ("fact_attrition_risk",
         """INSERT INTO pg_temp.fact_attrition_risk
            (prediction_id, as_of_date)
            VALUES ('TEST-RISK11', %s)"""),
    ],
    "DQ-C12": [
        ("dim_employee",
         """INSERT INTO pg_temp.dim_employee
            (employee_key, employee_id, valid_from, valid_to)
            VALUES ('901','TEST-E12','2024-01-01','2024-06-01'),
                   ('902','TEST-E12','2024-05-01','2024-12-31')"""),
    ],
}


def main():
    conn = get_connection()
    results = []

    try:
        with conn.cursor() as cur:
            source_names = list(SOURCE_TABLES) + ["etl_run_log"]

            for table in source_names:
                if table == "etl_run_log":
                    source = "workforce_metrics.etl_run_log"
                else:
                    source = f"official_stage.{table}"

                cur.execute(
                    f"CREATE TEMP TABLE {table} "
                    f"(LIKE {source})"
                )

            queries = {
                check_id: query
                for check_id, _name, _severity, query in CHECKS
            }

            for check_id in [f"DQ-C{i:02}" for i in range(1, 13)]:
                name, query = next(
                    (name, queries[check_id])
                    for cid, name, _severity, _sql in CHECKS
                    if cid == check_id
                )

                test_query = (
                    query.replace(
                        "official_stage.", "pg_temp."
                    ).replace(
                        "workforce_metrics.etl_run_log",
                        "pg_temp.etl_run_log"
                    )
                )

                cur.execute(
                    "TRUNCATE " + ", ".join(
                        f"pg_temp.{table}" for table in source_names
                    )
                )

                cur.execute(test_query)
                baseline_count = len(cur.fetchall())

                if baseline_count != 0:
                    results.append((check_id, "BLOCKED", baseline_count))
                    print(
                        f"{check_id} | {name} | BLOCKED | "
                        f"baseline unexpectedly returned {baseline_count} rows"
                    )
                    continue

                params = []
                for table, statement in FIXTURES[check_id]:
                    if check_id == "DQ-C11" and table == "etl_run_log":
                        now = datetime.now(timezone.utc)
                        cur.execute(statement, (now, now))
                    elif check_id == "DQ-C11" and table == "fact_attrition_risk":
                        stale_date = (
                            datetime.now(timezone.utc).date()
                            - timedelta(days=30)
                        )
                        cur.execute(statement, (stale_date.isoformat(),))
                    else:
                        cur.execute(statement)

                cur.execute(test_query)
                detected_count = len(cur.fetchall())

                status = "PASS" if detected_count > 0 else "FAIL"
                results.append((check_id, status, detected_count))
                print(
                    f"{check_id} | {name} | {status} | "
                    f"detected rows: {detected_count}"
                )

            print("\n=== ISOLATED NEGATIVE TEST SUMMARY ===")
            for status in ("PASS", "FAIL", "BLOCKED"):
                print(
                    f"{status}: "
                    f"{sum(1 for _, result, _ in results if result == status)}"
                )
            print("No official DQ result rows were written.")

    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    main()
