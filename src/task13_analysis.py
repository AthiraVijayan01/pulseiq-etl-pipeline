from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "clean"
OUTPUT = ROOT / "outputs"

OUTPUT.mkdir(exist_ok=True)

START = pd.Timestamp("2025-04-01")
END = pd.Timestamp("2026-09-01")

def load(name):
    return pd.read_csv(CLEAN / name)

def month_start(series):
    return pd.to_datetime(series).dt.to_period("M").dt.to_timestamp()

# ---------------------------------------------------------
# 1. Load sources
# ---------------------------------------------------------

hc = load("fact_headcount_monthly.csv")
pay = load("fact_payroll.csv")
att = load("fact_attendance_monthly.csv")
leave = load("fact_leave.csv")
emp = load("dim_employee.csv")

# ---------------------------------------------------------
# 2. Normalize dates and numeric columns
# ---------------------------------------------------------

hc["month_start_date"] = pd.to_datetime(hc["month_start_date"])
pay["period_end_date"] = pd.to_datetime(pay["period_end_date"])
att["period_end_date"] = pd.to_datetime(att["period_end_date"])

hc["month"] = hc["month_start_date"]
pay["month"] = month_start(pay["period_end_date"])
att["month"] = month_start(att["period_end_date"])

pay_numeric = [
    "employer_cost", "overtime_pay", "overtime_hours_paid"
]
att_numeric = [
    "scheduled_days", "present_days", "paid_leave_days",
    "unpaid_absence_days", "late_arrivals", "overtime_hours"
]
hc_numeric = [
    "headcount_start", "headcount_end", "hires", "exits",
    "voluntary_exits", "transfers_in", "transfers_out"
]

for df, columns in [
    (pay, pay_numeric),
    (att, att_numeric),
    (hc, hc_numeric)
]:
    for column in columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

# ---------------------------------------------------------
# 3. Verify and remove exact payroll duplicates
#    Only the analytical copy is deduplicated.
# ---------------------------------------------------------

duplicate_mask = pay.duplicated(
    ["employee_id", "period_end_date"], keep=False
)
duplicate_rows = pay[duplicate_mask]

business_columns = [
    c for c in pay.columns if c != "payroll_item_id"
]

for key, group in duplicate_rows.groupby(
    ["employee_id", "period_end_date"]
):
    if group[business_columns].drop_duplicates().shape[0] != 1:
        raise ValueError(
            f"Conflicting payroll duplicate found: {key}"
        )

pay_before = len(pay)
pay = pay.drop_duplicates(
    subset=business_columns, keep="first"
).copy()
duplicates_removed = pay_before - len(pay)

print("Payroll rows before deduplication:", pay_before)
print("Exact duplicate rows removed:", duplicates_removed)
print("Payroll analytical rows:", len(pay))

# ---------------------------------------------------------
# 4. Create common reporting period
# ---------------------------------------------------------

hc = hc[hc["month"].between(START, END)].copy()
pay = pay[pay["month"].between(START, END)].copy()
att = att[att["month"].between(START, END)].copy()

if hc.duplicated(["department_id", "month"]).any():
    raise ValueError("Duplicate headcount department-month grain")

# ---------------------------------------------------------
# 5. Aggregate headcount
# ---------------------------------------------------------

headcount = hc.groupby(
    ["department_id", "month"], as_index=False
).agg(
    headcount_start=("headcount_start", "sum"),
    headcount_end=("headcount_end", "sum"),
    hires=("hires", "sum"),
    exits=("exits", "sum"),
    voluntary_exits=("voluntary_exits", "sum"),
    transfers_in=("transfers_in", "sum"),
    transfers_out=("transfers_out", "sum"),
    source_attrition_rate_pct=("attrition_rate_monthly_pct", "mean")
)

# ---------------------------------------------------------
# 6. Aggregate payroll
# ---------------------------------------------------------

payroll = pay.groupby(
    ["department_id", "month"], as_index=False
).agg(
    employer_cost=("employer_cost", "sum"),
    overtime_cost=("overtime_pay", "sum"),
    payroll_overtime_hours=("overtime_hours_paid", "sum"),
    payroll_employee_count=("employee_id", "nunique"),
    payroll_rows=("payroll_item_id", "count")
)

# ---------------------------------------------------------
# 7. Aggregate attendance
# ---------------------------------------------------------

attendance = att.groupby(
    ["department_id", "month"], as_index=False
).agg(
    scheduled_days=("scheduled_days", "sum"),
    present_days=("present_days", "sum"),
    attendance_paid_leave_days=("paid_leave_days", "sum"),
    unpaid_absence_days=("unpaid_absence_days", "sum"),
    late_arrivals=("late_arrivals", "sum"),
    attendance_overtime_hours=("overtime_hours", "sum"),
    attendance_employee_count=("employee_id", "nunique")
)

attendance["attendance_rate_pct"] = (
    attendance["present_days"]
    .div(attendance["scheduled_days"].replace(0, pd.NA))
    .mul(100)
)

# ---------------------------------------------------------
# 8. Map leave requests to department
# ---------------------------------------------------------

if emp["employee_key"].duplicated().any():
    raise ValueError("Employee dimension employee_key is not unique")

leave = leave.merge(
    emp[["employee_key", "department_id"]],
    on="employee_key",
    how="left",
    validate="many_to_one"
)

if leave["department_id"].isna().any():
    raise ValueError("Some leave requests have no department mapping")

leave["start_date"] = pd.to_datetime(leave["start_date"])
leave["end_date"] = pd.to_datetime(leave["end_date"])
leave["days"] = pd.to_numeric(
    leave["days"], errors="coerce"
).fillna(0)

approved = leave[
    leave["status"].astype(str).str.strip().str.lower() == "approved"
].copy()

# Allocate recorded request days proportionally by weekdays.
# Weekends are excluded; public holidays are not adjusted because
# no holiday calendar is supplied in the leave source.

allocations = []

for row in approved.itertuples(index=False):
    start = row.start_date
    end = row.end_date

    if pd.isna(start) or pd.isna(end) or end < start:
        continue

    segments = []
    current = start.to_period("M")
    last = end.to_period("M")

    while current <= last:
        segment_start = max(start, current.start_time)
        segment_end = min(end, current.end_time)

        weekday_weight = len(
            pd.bdate_range(segment_start, segment_end)
        )

        segments.append((current.to_timestamp(), weekday_weight))
        current += 1

    total_weight = sum(weight for _, weight in segments)

    if total_weight == 0:
        segments = [
            (month, (min(end, month + pd.offsets.MonthEnd(0))
                     - max(start, month)).days + 1)
            for month, _ in segments
        ]
        total_weight = sum(weight for _, weight in segments)

    for month, weight in segments:
        allocated_days = (
            float(row.days) * weight / total_weight
            if total_weight else 0
        )

        allocations.append({
            "department_id": row.department_id,
            "month": month,
            "approved_leave_days": allocated_days
        })

leave_monthly = pd.DataFrame(allocations)

if leave_monthly.empty:
    leave_monthly = pd.DataFrame(
        columns=["department_id", "month", "approved_leave_days"]
    )
else:
    leave_monthly = leave_monthly.groupby(
        ["department_id", "month"], as_index=False
    ).agg(
        approved_leave_days=("approved_leave_days", "sum")
    )

leave_monthly = leave_monthly[
    leave_monthly["month"].between(START, END)
].copy()

# ---------------------------------------------------------
# 9. Join only aggregated department-month tables
# ---------------------------------------------------------

result = headcount.merge(
    payroll,
    on=["department_id", "month"],
    how="left",
    validate="one_to_one"
)

result = result.merge(
    attendance,
    on=["department_id", "month"],
    how="left",
    validate="one_to_one"
)

result = result.merge(
    leave_monthly,
    on=["department_id", "month"],
    how="left",
    validate="one_to_one"
)

sum_columns = [
    "employer_cost", "overtime_cost", "payroll_overtime_hours",
    "payroll_employee_count", "payroll_rows",
    "scheduled_days", "present_days", "attendance_paid_leave_days",
    "unpaid_absence_days", "late_arrivals",
    "attendance_overtime_hours", "attendance_employee_count",
    "approved_leave_days"
]

for column in sum_columns:
    result[column] = result[column].fillna(0)

result["average_headcount"] = (
    result["headcount_start"] + result["headcount_end"]
) / 2

result["leave_days_per_head"] = (
    result["approved_leave_days"]
    .div(result["average_headcount"].replace(0, pd.NA))
)

result["exit_rate_recalculated_pct"] = (
    result["exits"]
    .div(result["headcount_start"].replace(0, pd.NA))
    .mul(100)
)

result["month"] = pd.to_datetime(result["month"])
result = result.sort_values(["month", "department_id"])

# ---------------------------------------------------------
# 10. Validation and output
# ---------------------------------------------------------

if result.duplicated(["department_id", "month"]).any():
    raise ValueError("Final dataset has duplicate department-month rows")

expected_rows = hc[["department_id", "month"]].drop_duplicates().shape[0]

if len(result) != expected_rows:
    raise ValueError("Final row count does not match headcount grain")

output_file = OUTPUT / "task13_department_month.csv"
result.to_csv(output_file, index=False)

print("\n" + "=" * 75)
print("TASK 13 AGGREGATION SUMMARY")
print("=" * 75)

print("Reporting period:", START.date(), "to", END.date())
print("Final rows:", len(result))
print("Departments:", result["department_id"].nunique())
print("Months:", result["month"].nunique())
print("Duplicate department-month rows:",
      result.duplicated(["department_id", "month"]).sum())

print("\nSOURCE TOTALS")
print("Deduplicated payroll employer cost:", round(pay["employer_cost"].sum(), 2))
print("Combined employer cost:", round(result["employer_cost"].sum(), 2))
print("Deduplicated payroll overtime cost:", round(pay["overtime_pay"].sum(), 2))
print("Combined overtime cost:", round(result["overtime_cost"].sum(), 2))
print("Attendance paid leave days:", round(att["paid_leave_days"].sum(), 2))
print("Approved leave days allocated in reporting period:",
      round(result["approved_leave_days"].sum(), 2))

print("\nMISSING SOURCE MONTHS")
print("Department-months without payroll:",
      int(result["payroll_rows"].eq(0).sum()))
print("Department-months without attendance:",
      int(result["attendance_employee_count"].eq(0).sum()))

print("\nOUTPUT:", output_file)
print("\nSAMPLE:")
print(result.head(10).to_string(index=False))

print("\nTASK 13 AGGREGATION COMPLETE")
