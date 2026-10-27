
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
MIN_GROUP_SIZE = 5


def load_csv(name):
    for folder in ("clean", "raw"):
        path = ROOT / folder / name
        if path.exists():
            return pd.read_csv(path)
    raise FileNotFoundError(f"Missing {name} in clean and raw folders.")


def flag(series):
    return (
        series.astype(str)
        .str.strip()
        .str.upper()
        .isin(["Y", "YES", "TRUE", "1"])
    )


def month_text(value):
    return pd.Period(value, freq="M").strftime("%b %Y")


def safe_number(series):
    return pd.to_numeric(series, errors="coerce")


def add_department_name(frame, departments):
    if "department_id" not in frame.columns:
        frame["department"] = "Unknown"
        return frame

    name_column = next(
        (
            col
            for col in (
                "department_name",
                "department",
                "name",
                "department_label",
            )
            if col in departments.columns
        ),
        None,
    )

    if name_column is None:
        frame["department"] = frame["department_id"].astype(str)
        return frame

    department_map = departments[
        ["department_id", name_column]
    ].drop_duplicates("department_id")

    frame = frame.merge(
        department_map,
        on="department_id",
        how="left",
        validate="many_to_one",
    )
    frame["department"] = (
        frame[name_column]
        .fillna(frame["department_id"].astype(str))
        .astype(str)
    )
    return frame.drop(columns=[name_column], errors="ignore")


def privacy_filter(frame, group_columns, employee_column="employee_id"):
    if frame.empty:
        return frame.copy()

    counts = (
        frame.groupby(group_columns, dropna=False)[employee_column]
        .nunique()
        .rename("_distinct_employees")
        .reset_index()
    )
    result = frame.merge(counts, on=group_columns, how="left")
    return result.loc[
        result["_distinct_employees"] >= MIN_GROUP_SIZE
    ].drop(columns="_distinct_employees")


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
    employees = load_csv("dim_employee.csv")
except Exception as exc:
    st.error(f"Unable to load source data: {exc}")
    st.stop()


# Support both the source dimension's full_date and a generic date column.
if "date" not in calendar.columns and "full_date" in calendar.columns:
    calendar = calendar.rename(columns={"full_date": "date"})

required_attendance = {
    "employee_id",
    "period_end_date",
    "department_id",
    "scheduled_days",
    "present_days",
    "late_arrivals",
    "overtime_hours",
}
required_leave = {
    "employee_id",
    "start_date",
    "end_date",
    "days",
    "status",
    "leave_type_code",
}
required_calendar = {
    "date",
    "is_working_day",
    "is_holiday",
    "is_weekend",
}
required_department = {"department_id"}
required_employee = {"employee_key", "employee_id"}

for name, frame, required in (
    ("attendance", attendance, required_attendance),
    ("leave", leave, required_leave),
    ("calendar", calendar, required_calendar),
    ("departments", departments, required_department),
    ("employees", employees, required_employee),
):
    missing = required - set(frame.columns)
    if missing:
        st.error(f"{name} is missing columns: {sorted(missing)}")
        st.stop()


# -------------------- Attendance cleaning --------------------

attendance["period_end_date"] = pd.to_datetime(
    attendance["period_end_date"], errors="coerce"
)

for col in (
    "scheduled_days",
    "present_days",
    "late_arrivals",
    "overtime_hours",
):
    attendance[col] = safe_number(attendance[col])

attendance = attendance.dropna(
    subset=[
        "employee_id",
        "period_end_date",
        "department_id",
        "scheduled_days",
        "present_days",
        "late_arrivals",
        "overtime_hours",
    ]
).copy()

attendance = attendance.loc[
    (attendance["scheduled_days"] > 0)
    & (attendance["present_days"] >= 0)
    & (attendance["present_days"] <= attendance["scheduled_days"])
    & (attendance["late_arrivals"] >= 0)
    & (attendance["overtime_hours"] >= 0)
].copy()

if attendance.empty:
    st.warning("No valid attendance records are available.")
    st.stop()

attendance["month"] = (
    attendance["period_end_date"].dt.to_period("M").astype(str)
)

attendance = add_department_name(attendance, departments)

# Count distinct people in each department-month before showing its metrics.
attendance_monthly = (
    attendance.groupby(
        ["month", "department", "department_id"], as_index=False
    )
    .agg(
        scheduled_days=("scheduled_days", "sum"),
        present_days=("present_days", "sum"),
        late_arrivals=("late_arrivals", "sum"),
        overtime_hours=("overtime_hours", "sum"),
        employee_count=("employee_id", "nunique"),
    )
)

attendance_monthly = attendance_monthly.loc[
    attendance_monthly["employee_count"] >= MIN_GROUP_SIZE
].copy()

if attendance_monthly.empty:
    st.warning(
        "No department-month attendance groups meet the minimum "
        f"group size of {MIN_GROUP_SIZE}."
    )
    st.stop()

attendance_monthly["attendance_rate_pct"] = (
    100
    * attendance_monthly["present_days"]
    / attendance_monthly["scheduled_days"]
)


# -------------------- Calendar and long weekends --------------------

calendar["date"] = pd.to_datetime(calendar["date"], errors="coerce")
calendar = (
    calendar.dropna(subset=["date"])
    .sort_values("date")
    .drop_duplicates("date")
    .copy()
)

calendar["is_working_day_flag"] = flag(calendar["is_working_day"])
calendar["is_holiday_flag"] = flag(calendar["is_holiday"])
calendar["is_weekend_flag"] = flag(calendar["is_weekend"])
calendar["month"] = calendar["date"].dt.to_period("M").astype(str)

# Use the calendar's working-day indicator as the authoritative
# non-working-day classification.
calendar["non_working_flag"] = ~calendar["is_working_day_flag"]

new_run = (
    calendar["non_working_flag"]
    & (
        ~calendar["non_working_flag"].shift(fill_value=False)
        | calendar["date"].diff().dt.days.ne(1)
    )
)
calendar["non_working_run"] = new_run.cumsum()

non_working = calendar.loc[calendar["non_working_flag"]].copy()

if not non_working.empty:
    run_length = non_working.groupby(
        "non_working_run"
    )["date"].transform("size")
    run_has_holiday = non_working.groupby(
        "non_working_run"
    )["is_holiday_flag"].transform("any")

    non_working["long_weekend_flag"] = (
        (run_length >= 3) & run_has_holiday
    )

    calendar["long_weekend_flag"] = False
    calendar.loc[
        non_working.index, "long_weekend_flag"
    ] = non_working["long_weekend_flag"].to_numpy()
else:
    calendar["long_weekend_flag"] = False

calendar["long_weekend_days"] = (
    calendar["long_weekend_flag"].astype(int)
)

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

for col in (
    "calendar_working_days",
    "holidays",
    "weekend_days",
    "long_weekend_days",
):
    monthly[col] = monthly[col].fillna(0).astype(int)


# -------------------- Filters --------------------

st.sidebar.header("Filters")

months = sorted(monthly["month"].unique().tolist())
departments_available = sorted(monthly["department"].unique().tolist())

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

filtered = monthly.loc[
    monthly["month"].between(*selected_months)
    & monthly["department"].isin(selected_departments)
].copy()

if filtered.empty:
    st.info("No records match the selected filters.")
    st.stop()


# -------------------- KPI cards --------------------

scheduled_total = filtered["scheduled_days"].sum()
present_total = filtered["present_days"].sum()
overall_rate = (
    100 * present_total / scheduled_total if scheduled_total else 0
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Attendance rate", f"{overall_rate:.2f}%")
c2.metric("Scheduled days", f"{scheduled_total:,.0f}")
c3.metric("Late arrivals", f"{filtered['late_arrivals'].sum():,.0f}")
c4.metric("Overtime hours", f"{filtered['overtime_hours'].sum():,.1f}")

st.caption(
    "Attendance rate = sum of present days ÷ sum of scheduled days × 100. "
    "Scheduled days are the denominator; calendar working days are shown "
    "separately for context. Department-level metrics are hidden when fewer "
    f"than {MIN_GROUP_SIZE} distinct employees contribute to a group."
)


# -------------------- Attendance trend --------------------

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
    hover_data=["scheduled_days", "present_days", "employee_count"],
)
fig.update_layout(
    yaxis_ticksuffix="%",
    legend_title_text="Department",
)
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
            labels={"month": "Month", "late_arrivals": "Late arrivals"},
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
            labels={
                "department": "Department",
                "overtime_hours": "Overtime hours",
            },
        ),
        use_container_width=True,
    )


# -------------------- Heatmap --------------------

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


# -------------------- Holiday calendar --------------------

st.subheader("Holiday and long-weekend calendar")

calendar_display = calendar_summary.loc[
    calendar_summary["month"].between(*selected_months)
].copy()
calendar_display["month"] = calendar_display["month"].map(month_text)

st.dataframe(
    calendar_display,
    hide_index=True,
    use_container_width=True,
)

visible_holidays = holiday_dates.loc[
    holiday_dates["month"].between(*selected_months)
].drop(columns="month")

st.write(
    "Holiday dates and whether each belongs to a detected long weekend:"
)
st.dataframe(
    visible_holidays,
    hide_index=True,
    use_container_width=True,
)


# -------------------- Approved leave analysis --------------------

st.subheader("Approved leave patterns")

leave["start_date"] = pd.to_datetime(
    leave["start_date"], errors="coerce"
)
leave["end_date"] = pd.to_datetime(
    leave["end_date"], errors="coerce"
)
leave["days"] = safe_number(leave["days"])

approved = leave.loc[
    leave["status"].astype(str).str.strip().str.lower().eq("approved")
    & leave["start_date"].notna()
    & leave["end_date"].notna()
    & leave["days"].notna()
    & (leave["days"] > 0)
    & (leave["end_date"] >= leave["start_date"])
].copy()

# Prefer the exact SCD employee_key-to-department mapping.
# If employee_key is unavailable in the leave file, use the employee ID
# only when it maps to exactly one department in the employee dimension.
employee_department = employees[
    ["employee_key", "employee_id", "department_id"]
].dropna(subset=["employee_id", "department_id"]).copy()

employee_department["employee_id"] = (
    employee_department["employee_id"].astype(str)
)

if "employee_key" in approved.columns:
    approved["employee_key"] = safe_number(
        approved["employee_key"]
    )
    employee_department["employee_key"] = safe_number(
        employee_department["employee_key"]
    )

    approved = approved.merge(
        employee_department[
            ["employee_key", "department_id"]
        ].drop_duplicates("employee_key"),
        on="employee_key",
        how="left",
        validate="many_to_one",
    )
else:
    unique_employee_departments = (
        employee_department.groupby("employee_id")["department_id"]
        .agg(["nunique", "first"])
        .reset_index()
    )
    unique_employee_departments.loc[
        unique_employee_departments["nunique"] != 1, "first"
    ] = pd.NA

    approved["employee_id"] = approved["employee_id"].astype(str)
    approved = approved.merge(
        unique_employee_departments[
            ["employee_id", "first"]
        ].rename(columns={"first": "department_id"}),
        on="employee_id",
        how="left",
        validate="many_to_one",
    )

approved = add_department_name(approved, departments)

# Do not split a multi-month request into invented monthly day allocations.
# The request is attributed to its start month and its recorded day count.
approved["month"] = (
    approved["start_date"].dt.to_period("M").astype(str)
)

approved_visible = approved.loc[
    approved["month"].between(*selected_months)
    & approved["department"].isin(selected_departments)
    & approved["department"].ne("Unknown")
].copy()

if not approved_visible.empty:
    leave_monthly = (
        approved_visible.groupby(
            ["month", "department", "leave_type_code"], as_index=False
        )
        .agg(
            leave_days=("days", "sum"),
            employee_count=("employee_id", "nunique"),
            requests=("employee_id", "size"),
        )
    )

    # Apply minimum group size at month-department-leave-type grain.
    leave_monthly = leave_monthly.loc[
        leave_monthly["employee_count"] >= MIN_GROUP_SIZE
    ].copy()

    if not leave_monthly.empty:
        left, right = st.columns(2)

        with left:
            st.subheader("Approved leave days by month and type")
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
                        "month": "Request start month",
                        "leave_days": "Recorded approved leave days",
                        "leave_type_code": "Leave type",
                    },
                ),
                use_container_width=True,
            )

        with right:
            st.subheader("Approved leave days by department and type")
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
                        "leave_days": "Recorded approved leave days",
                        "leave_type_code": "Leave type",
                    },
                ),
                use_container_width=True,
            )

        st.caption(
            "Leave is grouped by the request start month; the full recorded "
            "duration is not split across months. Department mapping uses "
            "employee-version keys when available. Groups with fewer than "
            f"{MIN_GROUP_SIZE} distinct employees are hidden."
        )
    else:
        st.info(
            "No leave-type groups meet the minimum group size for the "
            "selected filters."
        )
else:
    st.info("No valid approved leave records match the selected filters.")


# -------------------- Numerical observations --------------------

st.subheader("Three numerical insights")

month_totals = (
    filtered.groupby("month", as_index=False)
    .agg(
        scheduled_days=("scheduled_days", "sum"),
        present_days=("present_days", "sum"),
        late_arrivals=("late_arrivals", "sum"),
        overtime_hours=("overtime_hours", "sum"),
        holidays=("holidays", "sum"),
        long_weekend_days=("long_weekend_days", "sum"),
    )
)

month_totals = month_totals.loc[
    month_totals["scheduled_days"] > 0
].copy()

month_totals["attendance_rate_pct"] = (
    100 * month_totals["present_days"] / month_totals["scheduled_days"]
)

if not month_totals.empty:
    lowest = month_totals.loc[
        month_totals["attendance_rate_pct"].idxmin()
    ]
    highest = month_totals.loc[
        month_totals["attendance_rate_pct"].idxmax()
    ]

    st.write(
        f"1. Lowest monthly attendance was {month_text(lowest['month'])}: "
        f"{lowest['attendance_rate_pct']:.2f}% "
        f"({lowest['present_days']:,.0f} present out of "
        f"{lowest['scheduled_days']:,.0f} scheduled employee-days)."
    )

    st.write(
        f"2. Highest monthly attendance was {month_text(highest['month'])}: "
        f"{highest['attendance_rate_pct']:.2f}% "
        f"({highest['present_days']:,.0f} present out of "
        f"{highest['scheduled_days']:,.0f} scheduled employee-days)."
    )

if not department_totals.empty if "department_totals" in locals() else False:
    pass

if not month_totals.empty:
    st.write(
        f"3. Across the selected period, there were "
        f"{month_totals['late_arrivals'].sum():,.0f} recorded late arrivals "
        f"and {month_totals['overtime_hours'].sum():,.1f} overtime hours."
    )

    st.subheader("Three unusual months: attendance and calendar context")

    unusual_months = month_totals.nsmallest(
        min(3, len(month_totals)), "attendance_rate_pct"
    )

    for _, row in unusual_months.iterrows():
        holiday_count = int(row["holidays"])
        long_weekend_count = int(row["long_weekend_days"])

        if holiday_count > 0 or long_weekend_count > 0:
            context = (
                f"The calendar records {holiday_count} holidays and "
                f"{long_weekend_count} long-weekend days in the aggregated "
                "department data. These are contextual indicators, not proof "
                "that holidays caused lower attendance."
            )
        else:
            context = (
                "The aggregated calendar metrics show no holiday or "
                "long-weekend days for this month. The attendance result "
                "alone does not establish its cause."
            )

        st.markdown(
            f"**{month_text(row['month'])} ? "
            f"{row['attendance_rate_pct']:.2f}% attendance**"
        )
        st.write(
            f"Recorded {row['late_arrivals']:,.0f} late arrivals and "
            f"{row['overtime_hours']:,.1f} overtime hours. {context}"
        )

    st.caption(
        "Unusual months are selected as the three lowest attendance-rate "
        "months in the current filtered period. Holiday and long-weekend "
        "figures are aggregated across visible department groups and should "
        "not be interpreted as causal evidence."
    )
else:
    st.info("No monthly attendance data is available for the selected filters.")

st.subheader("Monthly department metrics")

display = filtered.sort_values(["month", "department"]).copy()
display["month"] = display["month"].map(month_text)

st.dataframe(
    display,
    hide_index=True,
    use_container_width=True,
)

st.caption(
    "Long weekend means a run of at least three consecutive non-working "
    "calendar dates containing at least one holiday. Calendar patterns "
    "do not establish the cause of attendance changes. Leave is grouped "
    "by request start month and is not prorated across months."
)
