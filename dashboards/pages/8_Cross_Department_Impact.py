from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = ROOT / "outputs" / "task13_department_month.csv"


st.set_page_config(
    page_title="Cross-Department Impact",
    page_icon="🏢",
    layout="wide"
)


@st.cache_data
def load_data():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            "Task 13 dataset not found. Run src/task13_analysis.py first."
        )

    df = pd.read_csv(DATA_FILE)
    df["month"] = pd.to_datetime(df["month"])

    numeric_columns = [
        "employer_cost",
        "overtime_cost",
        "headcount_start",
        "headcount_end",
        "exits",
        "hires",
        "source_attrition_rate_pct",
        "attendance_rate_pct",
        "approved_leave_days",
        "attendance_paid_leave_days",
        "leave_days_per_head",
        "payroll_overtime_hours",
        "attendance_overtime_hours",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    return df


def money(value):
    return f"₹{value:,.2f}"


st.title("Cross-Department Impact")
st.caption(
    "Department-level comparison of workforce cost, overtime, "
    "attendance, leave and attrition."
)

try:
    data = load_data()
except Exception as exc:
    st.error(str(exc))
    st.stop()


# ---------------------------------------------------------
# Reporting period filter
# ---------------------------------------------------------

months = sorted(data["month"].dropna().unique())

month_labels = {
    pd.Timestamp(month).strftime("%b %Y"): pd.Timestamp(month)
    for month in months
}

period_options = ["All months"] + list(month_labels.keys())

selected_period = st.selectbox(
    "Reporting period",
    period_options,
    index=0
)

if selected_period == "All months":
    filtered = data.copy()
    period_description = (
        f"{data['month'].min():%b %Y} – {data['month'].max():%b %Y}"
    )
else:
    selected_month = month_labels[selected_period]
    filtered = data[data["month"] == selected_month].copy()
    period_description = selected_period


if filtered.empty:
    st.warning("No records are available for this reporting period.")
    st.stop()


# ---------------------------------------------------------
# Department-level comparison
# ---------------------------------------------------------

latest_month = filtered["month"].max()

latest_headcount = (
    filtered[filtered["month"] == latest_month]
    [["department_id", "headcount_end"]]
    .drop_duplicates("department_id")
    .rename(columns={"headcount_end": "latest_headcount"})
)

comparison = filtered.groupby(
    "department_id", as_index=False
).agg(
    employer_cost=("employer_cost", "sum"),
    overtime_cost=("overtime_cost", "sum"),
    exits=("exits", "sum"),
    hires=("hires", "sum"),
    average_monthly_attrition_pct=(
        "source_attrition_rate_pct", "mean"
    ),
    scheduled_days=("scheduled_days", "sum"),
    present_days=("present_days", "sum"),
    approved_leave_days=("approved_leave_days", "sum"),
    attendance_paid_leave_days=(
        "attendance_paid_leave_days", "sum"
    ),
    payroll_overtime_hours=("payroll_overtime_hours", "sum"),
)

comparison = comparison.merge(
    latest_headcount,
    on="department_id",
    how="left",
    validate="one_to_one"
)

comparison["attendance_rate_pct"] = (
    comparison["present_days"]
    .div(comparison["scheduled_days"].replace(0, pd.NA))
    .mul(100)
)

comparison["average_monthly_attrition_pct"] = (
    comparison["average_monthly_attrition_pct"].round(2)
)


# ---------------------------------------------------------
# KPI cards
# ---------------------------------------------------------

total_cost = filtered["employer_cost"].sum()
total_overtime = filtered["overtime_cost"].sum()
total_exits = filtered["exits"].sum()
average_attrition = filtered["source_attrition_rate_pct"].mean()
approved_leave = filtered["approved_leave_days"].sum()
attendance_leave = filtered["attendance_paid_leave_days"].sum()

st.subheader("Workforce and Cost Overview")
st.caption(f"Reporting period: {period_description}")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Employer Cost", money(total_cost))
col2.metric("Overtime Cost", money(total_overtime))
col3.metric("Employee Exits", f"{total_exits:,.0f}")
col4.metric(
    "Average Monthly Attrition",
    f"{average_attrition:.2f}%"
    if pd.notna(average_attrition) else "N/A"
)

col5, col6, col7, col8 = st.columns(4)

col5.metric(
    "Latest Headcount",
    f"{comparison['latest_headcount'].sum():,.0f}"
)
col6.metric(
    "Approved Leave Days (Allocated)",
    f"{approved_leave:,.2f}"
)
col7.metric(
    "Attendance Paid Leave Days",
    f"{attendance_leave:,.0f}"
)
col8.metric(
    "Attendance Rate",
    f"{(
        filtered['present_days'].sum()
        / filtered['scheduled_days'].sum() * 100
    ):.2f}%"
    if filtered["scheduled_days"].sum() else "N/A"
)


st.divider()


# ---------------------------------------------------------
# Combined department comparison chart
# ---------------------------------------------------------

st.subheader("Department Comparison: Cost, Overtime and Attrition")

st.caption(
    "Each point represents a department. Horizontal position shows "
    "employer cost, vertical position shows overtime cost, colour "
    "shows average monthly attrition, and bubble size shows latest "
    "headcount in the selected period."
)

chart = px.scatter(
    comparison,
    x="employer_cost",
    y="overtime_cost",
    color="average_monthly_attrition_pct",
    size="latest_headcount",
    size_max=48,
    hover_name="department_id",
    hover_data={
        "employer_cost": ":,.2f",
        "overtime_cost": ":,.2f",
        "average_monthly_attrition_pct": ":.2f",
        "latest_headcount": True,
        "exits": True,
    },
    labels={
        "employer_cost": "Employer Cost (₹)",
        "overtime_cost": "Overtime Cost (₹)",
        "average_monthly_attrition_pct": "Avg. Monthly Attrition (%)",
        "latest_headcount": "Latest Headcount",
    },
    color_continuous_scale="RdYlGn_r",
)

chart.update_layout(
    height=550,
    xaxis_title="Employer Cost (₹)",
    yaxis_title="Overtime Cost (₹)",
    coloraxis_colorbar_title="Attrition (%)",
)

st.plotly_chart(chart, width="stretch")


# ---------------------------------------------------------
# Department cost and attrition tables
# ---------------------------------------------------------

st.subheader("Department Performance")

display = comparison[
    [
        "department_id",
        "latest_headcount",
        "employer_cost",
        "overtime_cost",
        "payroll_overtime_hours",
        "exits",
        "hires",
        "average_monthly_attrition_pct",
        "attendance_rate_pct",
        "approved_leave_days",
        "attendance_paid_leave_days",
    ]
].copy()

display = display.rename(columns={
    "department_id": "Department",
    "latest_headcount": "Latest Headcount",
    "employer_cost": "Employer Cost (₹)",
    "overtime_cost": "Overtime Cost (₹)",
    "payroll_overtime_hours": "Payroll Overtime Hours",
    "exits": "Exits",
    "hires": "Hires",
    "average_monthly_attrition_pct": "Avg. Monthly Attrition (%)",
    "attendance_rate_pct": "Attendance Rate (%)",
    "approved_leave_days": "Approved Leave Days (Allocated)",
    "attendance_paid_leave_days": "Attendance Paid Leave Days",
})

st.dataframe(
    display,
    hide_index=True,
    width="stretch",
    column_config={
        "Employer Cost (₹)": st.column_config.NumberColumn(
            format="₹%.2f"
        ),
        "Overtime Cost (₹)": st.column_config.NumberColumn(
            format="₹%.2f"
        ),
        "Avg. Monthly Attrition (%)": st.column_config.NumberColumn(
            format="%.2f%%"
        ),
        "Attendance Rate (%)": st.column_config.NumberColumn(
            format="%.2f%%"
        ),
        "Approved Leave Days (Allocated)": st.column_config.NumberColumn(
            format="%.2f"
        ),
    },
)


st.divider()


# ---------------------------------------------------------
# Monthly trends for selected department
# ---------------------------------------------------------

st.subheader("Department Monthly Trends")

departments = sorted(data["department_id"].dropna().unique())

selected_department = st.selectbox(
    "Select department",
    departments,
    index=0
)

department_data = data[
    data["department_id"] == selected_department
].sort_values("month")

trend_col1, trend_col2 = st.columns(2)

with trend_col1:
    cost_chart = px.line(
        department_data,
        x="month",
        y="employer_cost",
        markers=True,
        title="Monthly Employer Cost",
        labels={
            "month": "Month",
            "employer_cost": "Employer Cost (₹)",
        },
    )
    cost_chart.update_layout(height=380)
    st.plotly_chart(cost_chart, width="stretch")

with trend_col2:
    overtime_chart = px.bar(
        department_data,
        x="month",
        y="overtime_cost",
        title="Monthly Overtime Cost",
        labels={
            "month": "Month",
            "overtime_cost": "Overtime Cost (₹)",
        },
    )
    overtime_chart.update_layout(height=380)
    st.plotly_chart(overtime_chart, width="stretch")


attrition_chart = px.line(
    department_data,
    x="month",
    y="source_attrition_rate_pct",
    markers=True,
    title="Monthly Attrition Rate",
    labels={
        "month": "Month",
        "source_attrition_rate_pct": "Attrition Rate (%)",
    },
)
attrition_chart.update_layout(height=380)

st.plotly_chart(attrition_chart, width="stretch")


# ---------------------------------------------------------
# Leave reconciliation and limitations
# ---------------------------------------------------------

st.subheader("Leave Reconciliation")

leave_col1, leave_col2, leave_col3 = st.columns(3)

leave_col1.metric(
    "Approved Leave Days (Allocated)",
    f"{approved_leave:,.2f}"
)

leave_col2.metric(
    "Attendance Paid Leave Days",
    f"{attendance_leave:,.0f}"
)

leave_col3.metric(
    "Difference",
    f"{approved_leave - attendance_leave:,.2f}"
)

st.info(
    "Approved leave days are allocated across months using weekday "
    "weights because the leave-request source does not contain a "
    "daily leave schedule or a holiday calendar. These allocated "
    "values are estimates. Attendance paid-leave days are shown "
    "separately and are not forced to reconcile with the request total."
)

st.caption(
    "Payroll analytical data excludes two exact duplicate business "
    "records identified by employee and payroll period. The original "
    "source CSV files were not modified."
)

st.caption(
    "Attrition is based on the monthly headcount source. It represents "
    "historical reported attrition, not an attrition-risk prediction."
)
