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

required = {
    "fact_attendance_monthly.csv": {
        "period_end_date", "department_id", "scheduled_days",
        "present_days", "late_arrivals", "overtime_hours",
    },
    "fact_leave.csv": {
        "employee_id", "start_date", "days", "status",
        "leave_type_code",
    },
}

for filename, columns in required.items():
    df = attendance if filename == "fact_attendance_monthly.csv" else leave
    missing = columns - set(df.columns)
    if missing:
        st.error(f"{filename} is missing columns: {sorted(missing)}")
        st.stop()

attendance["period_end_date"] = pd.to_datetime(
    attendance["period_end_date"], errors="coerce"
)
attendance = attendance.dropna(subset=["period_end_date"]).copy()
attendance["month"] = (
    attendance["period_end_date"].dt.to_period("M").astype(str)
)

for col in [
    "scheduled_days", "present_days", "late_arrivals", "overtime_hours"
]:
    attendance[col] = pd.to_numeric(attendance[col], errors="coerce").fillna(0)

attendance["attendance_rate_calc"] = (
    attendance["present_days"]
    .div(attendance["scheduled_days"].where(attendance["scheduled_days"] > 0))
)

dept_name_col = next(
    (
        c for c in [
            "department_name", "department", "name", "department_label"
        ]
        if c in departments.columns
    ),
    None,
)

if "department_id" in departments.columns and dept_name_col:
    dept_map = departments[["department_id", dept_name_col]].drop_duplicates(
        "department_id"
    )
    attendance = attendance.merge(
        dept_map, on="department_id", how="left"
    )
    attendance["department"] = attendance[dept_name_col].fillna(
        attendance["department_id"]
    )
else:
    attendance["department"] = attendance["department_id"]

attendance["department"] = attendance["department"].astype(str)

calendar["date"] = pd.to_datetime(calendar["date"], errors="coerce")
calendar["month"] = calendar["date"].dt.to_period("M").astype(str)

calendar["is_holiday_flag"] = (
    calendar["is_holiday"].astype(str).str.upper().isin(["Y", "YES", "TRUE", "1"])
)
calendar["is_weekend_flag"] = (
    calendar["is_weekend"].astype(str).str.upper().isin(["Y", "YES", "TRUE", "1"])
)

holiday_summary = (
    calendar.groupby("month", as_index=False)
    .agg(
        holidays=("is_holiday_flag", "sum"),
        weekend_days=("is_weekend_flag", "sum"),
    )
)

monthly = (
    attendance.groupby(["month", "department"], as_index=False)
    .agg(
        scheduled_days=("scheduled_days", "sum"),
        present_days=("present_days", "sum"),
        late_arrivals=("late_arrivals", "sum"),
        overtime_hours=("overtime_hours", "sum"),
        attendance_records=("employee_id", "size"),
    )
)

monthly["attendance_rate"] = (
    monthly["present_days"]
    .div(monthly["scheduled_days"].where(monthly["scheduled_days"] > 0))
    .mul(100)
)

monthly = monthly.merge(holiday_summary, on="month", how="left")
monthly[["holidays", "weekend_days"]] = (
    monthly[["holidays", "weekend_days"]].fillna(0)
)

st.sidebar.header("Filters")

months = sorted(monthly["month"].dropna().unique())
if not months:
    st.warning("No monthly attendance data is available.")
    st.stop()

selected_months = st.sidebar.select_slider(
    "Month range",
    options=months,
    value=(months[0], months[-1]),
)

all_departments = sorted(monthly["department"].unique())
selected_departments = st.sidebar.multiselect(
    "Departments",
    options=all_departments,
    default=all_departments,
)

filtered = monthly[
    monthly["month"].between(*selected_months)
    & monthly["department"].isin(selected_departments)
].copy()

if filtered.empty:
    st.info("No records match the selected filters.")
    st.stop()

total_scheduled = filtered["scheduled_days"].sum()
total_present = filtered["present_days"].sum()
overall_rate = (
    total_present / total_scheduled * 100
    if total_scheduled > 0 else 0
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Attendance rate", f"{overall_rate:.2f}%")
c2.metric("Scheduled days", f"{total_scheduled:,.0f}")
c3.metric("Late arrivals", f"{filtered['late_arrivals'].sum():,.0f}")
c4.metric("Overtime hours", f"{filtered['overtime_hours'].sum():,.1f}")

st.subheader("Monthly attendance rate")
fig = px.line(
    filtered,
    x="month",
    y="attendance_rate",
    color="department",
    markers=True,
    labels={
        "month": "Month",
        "attendance_rate": "Attendance rate (%)",
        "department": "Department",
    },
)
fig.update_layout(yaxis_ticksuffix="%", legend_title_text="Department")
st.plotly_chart(fig, use_container_width=True)

left, right = st.columns(2)

with left:
    st.subheader("Late arrivals by month")
    late = filtered.groupby("month", as_index=False)["late_arrivals"].sum()
    st.plotly_chart(
        px.bar(late, x="month", y="late_arrivals"),
        use_container_width=True,
    )

with right:
    st.subheader("Overtime by department")
    overtime = (
        filtered.groupby("department", as_index=False)["overtime_hours"].sum()
    )
    st.plotly_chart(
        px.bar(
            overtime,
            x="department",
            y="overtime_hours",
            labels={"overtime_hours": "Overtime hours"},
        ),
        use_container_width=True,
    )

st.subheader("Holiday calendar")
holiday_display = holiday_summary[
    holiday_summary["month"].between(*selected_months)
].copy()
st.dataframe(holiday_display, hide_index=True, use_container_width=True)

st.subheader("Leave patterns")

leave["start_date"] = pd.to_datetime(leave["start_date"], errors="coerce")
leave["month"] = leave["start_date"].dt.to_period("M").astype(str)
leave["days"] = pd.to_numeric(leave["days"], errors="coerce").fillna(0)

approved = leave[
    leave["status"].astype(str).str.strip().str.lower().eq("approved")
].copy()

if "employee_id" in attendance.columns:
    employee_dept = (
        attendance[["employee_id", "department"]]
        .drop_duplicates("employee_id")
    )
    approved = approved.merge(employee_dept, on="employee_id", how="left")
    approved["department"] = approved["department"].fillna("Unknown")
else:
    approved["department"] = "Unknown"

approved = approved[
    approved["month"].between(*selected_months)
    & approved["department"].isin(selected_departments)
].copy()

if not approved.empty:
    leave_monthly = (
        approved.groupby(["month", "leave_type_code"], as_index=False)
        .agg(leave_days=("days", "sum"))
    )
    st.plotly_chart(
        px.bar(
            leave_monthly,
            x="month",
            y="leave_days",
            color="leave_type_code",
            barmode="stack",
            labels={
                "month": "Month",
                "leave_days": "Approved leave days",
                "leave_type_code": "Leave type",
            },
        ),
        use_container_width=True,
    )
else:
    st.info("No approved leave records match these filters.")

st.subheader("Monthly department metrics")
st.dataframe(
    filtered.sort_values(["month", "department"]),
    hide_index=True,
    use_container_width=True,
)

st.caption(
    "Attendance rate = total present days / total scheduled days. "
    "Leave counts include approved requests only. "
    "Calendar holiday counts are monthly totals, not department-specific."
)
