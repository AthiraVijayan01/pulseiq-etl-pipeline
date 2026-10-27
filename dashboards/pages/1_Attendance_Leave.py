from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]


def load_csv(name):
    for folder in ["clean", "raw"]:
        path = ROOT / folder / name
        if path.exists():
            return pd.read_csv(path)
    raise FileNotFoundError(f"Missing {name} in clean and raw folders.")


def flag(series):
    return series.astype(str).str.strip().str.upper().isin(
        ["Y", "YES", "TRUE", "1"]
    )


def month_text(value):
    return pd.Period(value, freq="M").strftime("%b %Y")


st.set_page_config(
    page_title="Attendance & Leave | PulseIQ",
    page_icon="📅",
    layout="wide",
)

st.title("Attendance & Leave Analytics")
st.caption("PulseIQ | Phase 2 — Task 6")

try:
    attendance = load_csv("fact_attendance_monthly.csv")
    leave = load_csv("fact_leave.csv")
    calendar = load_csv("dim_date.csv")
    departments = load_csv("dim_department.csv")
except Exception as exc:
    st.error(f"Unable to load source data: {exc}")
    st.stop()


required_attendance = {
    "employee_id", "period_end_date", "department_id",
    "scheduled_days", "present_days", "late_arrivals",
    "overtime_hours",
}
required_leave = {
    "employee_id", "start_date", "end_date", "days",
    "status", "leave_type_code",
}
required_calendar = {
    "date", "is_working_day", "is_holiday", "is_weekend",
}

for name, df, required in [
    ("attendance", attendance, required_attendance),
    ("leave", leave, required_leave),
    ("calendar", calendar, required_calendar),
]:
    missing = required - set(df.columns)
    if missing:
        st.error(f"{name} is missing columns: {sorted(missing)}")
        st.stop()


attendance["period_end_date"] = pd.to_datetime(
    attendance["period_end_date"], errors="coerce"
)
attendance = attendance.dropna(subset=["period_end_date"]).copy()

for col in [
    "scheduled_days", "present_days", "late_arrivals", "overtime_hours"
]:
    attendance[col] = pd.to_numeric(attendance[col], errors="coerce")

attendance = attendance.dropna(
    subset=[
        "scheduled_days", "present_days",
        "late_arrivals", "overtime_hours",
    ]
).copy()

attendance = attendance[
    (attendance["scheduled_days"] > 0)
    & (attendance["present_days"] >= 0)
    & (attendance["present_days"] <= attendance["scheduled_days"])
    & (attendance["late_arrivals"] >= 0)
    & (attendance["overtime_hours"] >= 0)
].copy()

attendance["month"] = (
    attendance["period_end_date"].dt.to_period("M").astype(str)
)

dept_name_col = next(
    (
        col for col in [
            "department_name", "department", "name", "department_label"
        ]
        if col in departments.columns
    ),
    None,
)

if dept_name_col and "department_id" in departments.columns:
    dept_map = departments[
        ["department_id", dept_name_col]
    ].drop_duplicates("department_id")

    attendance = attendance.merge(
        dept_map, on="department_id", how="left"
    )
    attendance["department"] = attendance[dept_name_col].fillna(
        attendance["department_id"].astype(str)
    )
else:
    attendance["department"] = attendance["department_id"].astype(str)

attendance["department"] = attendance["department"].astype(str)

attendance_monthly = (
    attendance.groupby(["month", "department"], as_index=False)
    .agg(
        scheduled_days=("scheduled_days", "sum"),
        present_days=("present_days", "sum"),
        late_arrivals=("late_arrivals", "sum"),
        overtime_hours=("overtime_hours", "sum"),
        attendance_records=("employee_id", "size"),
    )
)

attendance_monthly["attendance_rate_pct"] = (
    100 * attendance_monthly["present_days"]
    / attendance_monthly["scheduled_days"]
)

calendar["date"] = pd.to_datetime(calendar["date"], errors="coerce")
calendar = calendar.dropna(subset=["date"]).copy()
calendar = calendar.sort_values("date").drop_duplicates("date")

calendar["is_working_day_flag"] = flag(calendar["is_working_day"])
calendar["is_holiday_flag"] = flag(calendar["is_holiday"])
calendar["is_weekend_flag"] = flag(calendar["is_weekend"])
calendar["month"] = calendar["date"].dt.to_period("M").astype(str)

# A long weekend is a consecutive run of at least three days where
# every date is a weekend or holiday.
calendar["non_working_flag"] = (
    calendar["is_weekend_flag"] | calendar["is_holiday_flag"]
)

run_id = (
    (~calendar["non_working_flag"])
    | calendar["date"].diff().dt.days.ne(1)
).cumsum()

calendar["non_working_run"] = run_id
run_lengths = calendar.groupby("non_working_run")["date"].transform("size")

calendar["long_weekend_flag"] = (
    calendar["non_working_flag"] & (run_lengths >= 3)
)

calendar["long_weekend_days"] = calendar["long_weekend_flag"].astype(int)

calendar_summary = (
    calendar.groupby("month", as_index=False)
    .agg(
        calendar_working_days=("is_working_day_flag", "sum"),
        holidays=("is_holiday_flag", "sum"),
        weekend_days=("is_weekend_flag", "sum"),
        long_weekend_days=("long_weekend_days", "sum"),
    )
)

holiday_dates = calendar.loc[
    calendar["is_holiday_flag"],
    ["date", "month", "long_weekend_flag"],
].copy()

holiday_dates["date"] = holiday_dates["date"].dt.strftime("%Y-%m-%d")
holiday_dates["long_weekend_flag"] = holiday_dates[
    "long_weekend_flag"
].map({True: "Yes", False: "No"})

monthly = attendance_monthly.merge(
    calendar_summary, on="month", how="left"
)

for col in [
    "calendar_working_days", "holidays",
    "weekend_days", "long_weekend_days",
]:
    monthly[col] = monthly[col].fillna(0).astype(int)

st.sidebar.header("Filters")

months = sorted(monthly["month"].unique())
departments_available = sorted(monthly["department"].unique())

if not months or not departments_available:
    st.warning("No valid attendance records are available.")
    st.stop()

selected_months = st.sidebar.select_slider(
    "Month range",
    options=months,
    value=(months[0], months[-1]),
    format_func=month_text,
)

selected_departments = st.sidebar.multiselect(
    "Departments",
    options=departments_available,
    default=departments_available,
)

filtered = monthly[
    monthly["month"].between(*selected_months)
    & monthly["department"].isin(selected_departments)
].copy()

if filtered.empty:
    st.info("No records match the selected filters.")
    st.stop()

scheduled_total = filtered["scheduled_days"].sum()
present_total = filtered["present_days"].sum()
overall_rate = (
    100 * present_total / scheduled_total
    if scheduled_total else 0
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Attendance rate", f"{overall_rate:.2f}%")
c2.metric("Scheduled working days", f"{scheduled_total:,.0f}")
c3.metric("Late arrivals", f"{filtered['late_arrivals'].sum():,.0f}")
c4.metric("Overtime hours", f"{filtered['overtime_hours'].sum():,.1f}")

st.caption(
    "Attendance rate = total present days ÷ total scheduled days × 100. "
    "The denominator is the sum of scheduled days in the attendance facts; "
    "calendar working-day counts are shown separately for context."
)

st.subheader("Monthly attendance rate by department")
fig = px.line(
    filtered.sort_values("month"),
    x="month",
    y="attendance_rate_pct",
    color="department",
    markers=True,
    labels={
        "month": "Month",
        "attendance_rate_pct": "Attendance rate (%)",
        "department": "Department",
    },
    hover_data=["scheduled_days", "present_days"],
)
fig.update_layout(yaxis_ticksuffix="%", legend_title_text="Department")
st.plotly_chart(fig, use_container_width=True)

left, right = st.columns(2)

with left:
    st.subheader("Late arrivals by month")
    late_monthly = (
        filtered.groupby("month", as_index=False)["late_arrivals"].sum()
    )
    st.plotly_chart(
        px.bar(
            late_monthly,
            x="month",
            y="late_arrivals",
            labels={"late_arrivals": "Late arrivals"},
        ),
        use_container_width=True,
    )

with right:
    st.subheader("Overtime hours by department")
    overtime_department = (
        filtered.groupby("department", as_index=False)["overtime_hours"].sum()
    )
    st.plotly_chart(
        px.bar(
            overtime_department,
            x="department",
            y="overtime_hours",
            labels={"overtime_hours": "Overtime hours"},
        ),
        use_container_width=True,
    )

st.subheader("Attendance heatmap")
heatmap_data = filtered.pivot(
    index="department",
    columns="month",
    values="attendance_rate_pct",
)
st.plotly_chart(
    px.imshow(
        heatmap_data,
        aspect="auto",
        color_continuous_scale="RdYlGn",
        labels={
            "x": "Month",
            "y": "Department",
            "color": "Attendance rate (%)",
        },
        text_auto=".1f",
    ),
    use_container_width=True,
)

st.subheader("Holiday and long-weekend calendar")
calendar_display = calendar_summary[
    calendar_summary["month"].between(*selected_months)
].copy()
calendar_display["month"] = calendar_display["month"].map(month_text)
st.dataframe(calendar_display, hide_index=True, use_container_width=True)

visible_holidays = holiday_dates[
    holiday_dates["month"].between(*selected_months)
].drop(columns="month")

st.write("Holiday dates and whether each falls within a detected long weekend:")
st.dataframe(visible_holidays, hide_index=True, use_container_width=True)

st.subheader("Approved leave patterns")

leave["start_date"] = pd.to_datetime(leave["start_date"], errors="coerce")
leave["end_date"] = pd.to_datetime(leave["end_date"], errors="coerce")
leave["days"] = pd.to_numeric(leave["days"], errors="coerce")

approved = leave[
    leave["status"].astype(str).str.strip().str.lower().eq("approved")
    & leave["start_date"].notna()
    & leave["end_date"].notna()
    & leave["days"].notna()
    & (leave["days"] > 0)
    & (leave["end_date"] >= leave["start_date"])
].copy()

# Assign each leave request to the employee's nearest attendance-period
# department, rather than choosing an arbitrary department for that employee.
dept_lookup = {}
attendance_by_employee = {
    employee_id: group.sort_values("period_end_date")
    for employee_id, group in attendance.groupby("employee_id")
}

for _, request in approved.iterrows():
    employee_id = request["employee_id"]
    if employee_id not in dept_lookup:
        dept_lookup[employee_id] = None

    group = attendance_by_employee.get(employee_id)
    if group is not None and not group.empty:
        distances = (
            group["period_end_date"] - request["start_date"]
        ).abs()
        nearest_idx = distances.idxmin()
        dept_lookup[employee_id] = group.loc[nearest_idx, "department"]

approved["department"] = approved["employee_id"].map(dept_lookup)
approved["department"] = approved["department"].fillna("Unknown")

# Allocate the request's recorded leave days across months in proportion
# to working dates within each month's portion of the request.
calendar_working = calendar[
    calendar["is_working_day_flag"]
].copy()
calendar_working["month_period"] = (
    calendar_working["date"].dt.to_period("M").astype(str)
)

allocations = []

for _, request in approved.iterrows():
    start = request["start_date"].normalize()
    end = request["end_date"].normalize()

    days_in_range = calendar_working[
        calendar_working["date"].between(start, end)
    ]

    month_counts = days_in_range.groupby("month_period").size()

    if month_counts.empty:
        month_counts = pd.Series({
            str(start.to_period("M")): 1
        })

    denominator = month_counts.sum()

    for month, working_days in month_counts.items():
        allocations.append({
            "month": month,
            "department": request["department"],
            "leave_type_code": request["leave_type_code"],
            "leave_days": (
                float(request["days"]) * working_days / denominator
            ),
        })

leave_monthly = pd.DataFrame(allocations)

if not leave_monthly.empty:
    leave_monthly = leave_monthly[
        leave_monthly["month"].between(*selected_months)
        & leave_monthly["department"].isin(selected_departments)
    ]

if not leave_monthly.empty:
    left, right = st.columns(2)

    with left:
        st.plotly_chart(
            px.bar(
                leave_monthly.groupby(
                    ["month", "leave_type_code"], as_index=False
                )["leave_days"].sum(),
                x="month",
                y="leave_days",
                color="leave_type_code",
                barmode="stack",
                labels={
                    "month": "Month",
                    "leave_days": "Allocated approved leave days",
                    "leave_type_code": "Leave type",
                },
            ),
            use_container_width=True,
        )

    with right:
        st.plotly_chart(
            px.bar(
                leave_monthly.groupby(
                    ["department", "leave_type_code"], as_index=False
                )["leave_days"].sum(),
                x="department",
                y="leave_days",
                color="leave_type_code",
                barmode="stack",
                labels={
                    "department": "Department",
                    "leave_days": "Allocated approved leave days",
                    "leave_type_code": "Leave type",
                },
            ),
            use_container_width=True,
        )
else:
    st.info("No approved leave records match the selected filters.")

st.subheader("Three numerical observations")

month_totals = (
    filtered.groupby("month", as_index=False)
    .agg(
        scheduled_days=("scheduled_days", "sum"),
        present_days=("present_days", "sum"),
        late_arrivals=("late_arrivals", "sum"),
        overtime_hours=("overtime_hours", "sum"),
    )
)

month_totals["attendance_rate_pct"] = (
    100 * month_totals["present_days"] / month_totals["scheduled_days"]
)

if not month_totals.empty:
    lowest = month_totals.loc[month_totals["attendance_rate_pct"].idxmin()]
    highest = month_totals.loc[month_totals["attendance_rate_pct"].idxmax()]

    st.write(
        f"1. Lowest attendance in the selected period: "
        f"{month_text(lowest['month'])} at "
        f"{lowest['attendance_rate_pct']:.2f}%."
    )
    st.write(
        f"2. Highest attendance in the selected period: "
        f"{month_text(highest['month'])} at "
        f"{highest['attendance_rate_pct']:.2f}%."
    )

department_totals = (
    filtered.groupby("department", as_index=False)
    .agg(
        scheduled_days=("scheduled_days", "sum"),
        present_days=("present_days", "sum"),
        late_arrivals=("late_arrivals", "sum"),
        overtime_hours=("overtime_hours", "sum"),
    )
)

department_totals["attendance_rate_pct"] = (
    100 * department_totals["present_days"]
    / department_totals["scheduled_days"]
)

if not department_totals.empty:
    lowest_dept = department_totals.loc[
        department_totals["attendance_rate_pct"].idxmin()
    ]
    st.write(
        f"3. Lowest department attendance in the selected period: "
        f"{lowest_dept['department']} at "
        f"{lowest_dept['attendance_rate_pct']:.2f}% "
        f"({lowest_dept['scheduled_days']:,.0f} scheduled days)."
    )

st.subheader("Monthly department metrics")
display = filtered.sort_values(["month", "department"]).copy()
display["month"] = display["month"].map(month_text)
st.dataframe(display, hide_index=True, use_container_width=True)

st.caption(
    "Long weekend = a consecutive run of at least three calendar dates "
    "each marked as a weekend or holiday in dim_date. This identifies "
    "calendar patterns; it does not prove the cause of attendance changes. "
    "Leave is allocated across covered months by working-day share. "
    "Department assignment for leave uses the nearest available attendance "
    "period and may be approximate when an employee changes department."
)
