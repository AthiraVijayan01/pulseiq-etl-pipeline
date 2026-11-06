from pathlib import Path
import pandas as pd
from src.db import get_connection

ROOT = Path(__file__).resolve().parent
passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")
    if detail:
        print(f"      {detail}")


print("=" * 65)
print("TASK 15 - EXECUTIVE SCORECARD VERIFICATION")
print("=" * 65)

dashboard = ROOT / "dashboards" / "pages" / "10_Executive_Scorecard.py"
check("Dashboard file exists", dashboard.exists())

code = ""
if dashboard.exists():
    code = dashboard.read_text(encoding="utf-8")
    check("Dashboard file is not empty", bool(code.strip()))
    try:
        compile(code, str(dashboard), "exec")
        check("Dashboard Python syntax", True)
    except Exception as exc:
        check("Dashboard Python syntax", False, str(exc))

target_file = ROOT / "clean" / "kpi_targets.csv"
check("KPI targets CSV exists", target_file.exists())

if target_file.exists():
    try:
        targets = pd.read_csv(target_file)
        check("KPI targets contain records", not targets.empty)
        check("KPI target columns are unique", targets.columns.is_unique)
        print("      KPI target rows:", len(targets))
    except Exception as exc:
        check("KPI targets CSV readable", False, str(exc))

conn = None

try:
    conn = get_connection()
    check("PostgreSQL connection", True)

    views = pd.read_sql("""
        SELECT table_schema, table_name
        FROM information_schema.views
        WHERE table_schema IN ('phase2', 'phase3')
    """, conn)

    available = set(zip(views.table_schema, views.table_name))

    required = [
        ("phase2", "v_monthly_attrition_exits"),
        ("phase2", "v_monthly_attendance_rate"),
        ("phase2", "v_monthly_leave_days"),
        ("phase3", "v_pnl_monthly"),
    ]

    for schema, view in required:
        check(f"View {schema}.{view} exists", (schema, view) in available)

    sources = {
        "Headcount and attrition": "SELECT COUNT(*) AS n FROM phase2.v_monthly_attrition_exits",
        "Attendance": "SELECT COUNT(*) AS n FROM phase2.v_monthly_attendance_rate",
        "Approved leave": "SELECT COUNT(*) AS n FROM phase2.v_monthly_leave_days",
        "Profit and loss": "SELECT COUNT(*) AS n FROM phase3.v_pnl_monthly",
    }

    for name, query in sources.items():
        try:
            count = int(pd.read_sql(query, conn).iloc[0]["n"])
            check(f"{name} source contains data", count > 0, f"Rows: {count}")
        except Exception as exc:
            check(f"{name} source query", False, str(exc))

    months = pd.read_sql("""
        SELECT DISTINCT month_start
        FROM phase2.v_monthly_attendance_rate
        ORDER BY month_start
    """, conn)

    check("Reporting months are available", not months.empty,
          f"Available months: {len(months)}")

    if not months.empty:
        print("      First month:", months.iloc[0]["month_start"])
        print("      Latest month:", months.iloc[-1]["month_start"])

except Exception as exc:
    check("Database verification", False, str(exc))

finally:
    if conn is not None:
        conn.close()

elements = [
    "Employee Headcount",
    "Attendance Rate",
    "Monthly Attrition Rate",
    "Approved Leave Days",
    "Revenue",
    "Expenses",
    "Net Profit",
    "Profit Margin",
    "selectbox",
    "KPI Details",
    "Justification",
]

for element in elements:
    check(f"Dashboard includes {element}", element.lower() in code.lower())

print("\n" + "=" * 65)
print("TASK 15 VERIFICATION SUMMARY")
print("=" * 65)
print(f"PASS: {passed}")
print(f"FAIL: {failed}")
print(f"TOTAL: {passed + failed}")

if failed == 0:
    print("All automated checks passed.")
else:
    print("Some checks need investigation.")
