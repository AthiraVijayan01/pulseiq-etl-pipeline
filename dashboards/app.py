
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from src.db import database_connection


st.set_page_config(
    page_title="PulseIQ HR Analytics",
    page_icon="📊",
    layout="wide",
)


@st.cache_data(ttl=60)
def query_df(query):
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]
    return pd.DataFrame(rows, columns=columns)


@st.cache_data(ttl=60)
def load_metric_layer():
    return {
        "catalog": query_df("""
            SELECT
                metric_name,
                metric_description,
                unit,
                source_view,
                owner
            FROM metric_catalog
            ORDER BY metric_name
        """),
        "headcount": query_df("""
            SELECT * FROM v_monthly_headcount
        """),
        "attendance": query_df("""
            SELECT * FROM v_monthly_attendance_rate
        """),
        "leave": query_df("""
            SELECT * FROM v_monthly_leave_days
        """),
        "payroll": query_df("""
            SELECT * FROM v_monthly_net_payroll
        """),
    }


def has_column(data, column):
    return column in data.columns


def filter_view(data, start_date=None, end_date=None, departments=None):
    result = data.copy()

    if "month_start" in result.columns and start_date is not None:
        dates = pd.to_datetime(result["month_start"], errors="coerce")
        result = result[
            dates.notna()
            & (dates.dt.date >= start_date)
            & (dates.dt.date <= end_date)
        ]

    if departments and "department_name" in result.columns:
        result = result[
            result["department_name"].isin(departments)
        ]

    return result


def show_insight(message):
    st.caption(f"Insight: {message}")


def show_metric_chart(
    data,
    title,
    x_column,
    y_column,
    chart_type="bar",
    color_column=None,
    x_label=None,
    y_label=None,
):
    st.subheader(title)

    required = [x_column, y_column]
    if color_column:
        required.append(color_column)

    if data.empty:
        st.info(
            "No rows are available from the approved metric view. "
            "The minimum-five-employee privacy rule may suppress "
            "these results."
        )
        show_insight(
            "No conclusion can be drawn until approved data is available."
        )
        return

    if any(column not in data.columns for column in required):
        st.warning(
            "This chart cannot be rendered because the metric view "
            "does not contain the expected columns."
        )
        st.caption(f"Available columns: {', '.join(data.columns)}")
        return

    labels = {}
    if x_label:
        labels[x_column] = x_label
    if y_label:
        labels[y_column] = y_label

    if chart_type == "line":
        figure = px.line(
            data,
            x=x_column,
            y=y_column,
            color=color_column,
            markers=True,
            labels=labels,
        )
    elif chart_type == "pie":
        figure = px.pie(
            data,
            names=x_column,
            values=y_column,
            hole=0.4,
            labels=labels,
        )
    else:
        figure = px.bar(
            data,
            x=x_column,
            y=y_column,
            color=color_column,
            labels=labels,
        )

    st.plotly_chart(figure, width="stretch")

    if chart_type == "line":
        show_insight(
            "Compare the visible monthly values to identify changes "
            "over the selected reporting period."
        )
    elif chart_type == "pie":
        show_insight(
            "The chart compares the relative contribution of the "
            "visible categories."
        )
    else:
        show_insight(
            "Compare the visible categories to identify differences "
            "in the selected metric."
        )


st.title("PulseIQ HR Analytics Dashboard")
st.caption(
    "HR analytics powered by approved PostgreSQL metric views. "
    "Groups suppressed by the privacy threshold are not displayed."
)

try:
    metrics = load_metric_layer()

    catalog = metrics["catalog"]
    headcount_data = metrics["headcount"]
    attendance_data = metrics["attendance"]
    leave_data = metrics["leave"]
    payroll_data = metrics["payroll"]

    st.header("Official Metric Catalog")

    if catalog.empty:
        st.warning("No metric definitions were found in metric_catalog.")
    else:
        st.dataframe(catalog, width="stretch")

    st.divider()
    st.header("Dashboard Filters")

    all_views = [
        headcount_data,
        attendance_data,
        leave_data,
        payroll_data,
    ]

    available_departments = sorted({
        str(value)
        for data in all_views
        if "department_name" in data.columns
        for value in data["department_name"].dropna().tolist()
    })

    available_months = []
    for data in all_views:
        if "month_start" in data.columns:
            parsed = pd.to_datetime(data["month_start"], errors="coerce")
            available_months.extend(parsed.dropna().tolist())

    selected_departments = available_departments
    start_date = None
    end_date = None

    if available_departments:
        selected_departments = st.multiselect(
            "Departments",
            options=available_departments,
            default=available_departments,
        )
    else:
        st.info(
            "Department filtering will become available when the "
            "approved metric views contain visible rows."
        )

    if available_months:
        min_date = min(available_months).date()
        max_date = max(available_months).date()

        selected_range = st.date_input(
            "Reporting date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        if isinstance(selected_range, (tuple, list)):
            if len(selected_range) == 2:
                start_date, end_date = selected_range
            elif len(selected_range) == 1:
                start_date = end_date = selected_range[0]
        else:
            start_date = end_date = selected_range
    else:
        st.info(
            "No reporting dates are available in the approved views. "
            "The date filter will appear when visible metric rows exist."
        )

    if start_date is not None and end_date is not None:
        if start_date > end_date:
            st.error("The start date must not be after the end date.")
            st.stop()

    headcount = filter_view(
        headcount_data, start_date, end_date, selected_departments
    )
    attendance = filter_view(
        attendance_data, start_date, end_date, selected_departments
    )
    leave = filter_view(
        leave_data, start_date, end_date, selected_departments
    )
    payroll = filter_view(
        payroll_data, start_date, end_date, selected_departments
    )

    st.divider()
    st.header("Key Metrics")

    col1, col2, col3, col4 = st.columns(4)

    if not headcount.empty and "headcount" in headcount.columns:
        if "month_start" in headcount.columns:
            latest_month = pd.to_datetime(
                headcount["month_start"], errors="coerce"
            ).max()
            latest_rows = headcount[
                pd.to_datetime(
                    headcount["month_start"], errors="coerce"
                ) == latest_month
            ]
        else:
            latest_rows = headcount

        headcount_value = pd.to_numeric(
            latest_rows["headcount"], errors="coerce"
        ).sum()
        col1.metric("Headcount", f"{headcount_value:,.0f}")
    else:
        col1.metric("Headcount", "—")

    if (
        not attendance.empty
        and "attendance_rate_percent" in attendance.columns
    ):
        attendance_values = pd.to_numeric(
            attendance["attendance_rate_percent"], errors="coerce"
        ).dropna()
        attendance_value = (
            attendance_values.mean()
            if not attendance_values.empty
            else None
        )
        col2.metric(
            "Average Attendance Rate",
            f"{attendance_value:.1f}%"
            if attendance_value is not None else "—",
        )
    else:
        col2.metric("Average Attendance Rate", "—")

    if not leave.empty and "total_leave_days" in leave.columns:
        leave_value = pd.to_numeric(
            leave["total_leave_days"], errors="coerce"
        ).sum()
        col3.metric("Total Leave Days", f"{leave_value:,.0f}")
    else:
        col3.metric("Total Leave Days", "—")

    if not payroll.empty and "total_net_payroll" in payroll.columns:
        payroll_value = pd.to_numeric(
            payroll["total_net_payroll"], errors="coerce"
        ).sum()
        col4.metric("Net Payroll", f"{payroll_value:,.2f}")
    else:
        col4.metric("Net Payroll", "—")

    if all(data.empty for data in all_views):
        st.warning(
            "The approved metric views currently return no rows. "
            "Your privacy rule requires at least five distinct employees "
            "in each applicable group, while the current sample dataset "
            "contains only four employees. Results remain suppressed; "
            "the privacy threshold has not been weakened."
        )

    st.divider()
    st.header("Approved Metric Visualizations")

    show_metric_chart(
        headcount,
        "Monthly Headcount Trend",
        "month_start",
        "headcount",
        chart_type="line",
        color_column=(
            "department_name"
            if "department_name" in headcount.columns else None
        ),
        x_label="Month",
        y_label="Employees",
    )

    show_metric_chart(
        headcount,
        "Headcount by Department",
        "department_name",
        "headcount",
        x_label="Department",
        y_label="Employees",
    )

    show_metric_chart(
        attendance,
        "Monthly Attendance Rate",
        "month_start",
        "attendance_rate_percent",
        chart_type="line",
        color_column=(
            "department_name"
            if "department_name" in attendance.columns else None
        ),
        x_label="Month",
        y_label="Attendance Rate (%)",
    )

    show_metric_chart(
        leave,
        "Monthly Leave Days",
        "month_start",
        "total_leave_days",
        chart_type="bar",
        color_column=(
            "leave_type_name"
            if "leave_type_name" in leave.columns else None
        ),
        x_label="Month",
        y_label="Leave Days",
    )

    show_metric_chart(
        payroll,
        "Monthly Net Payroll",
        "month_start",
        "total_net_payroll",
        chart_type="line",
        color_column=(
            "department_name"
            if "department_name" in payroll.columns else None
        ),
        x_label="Month",
        y_label="Net Payroll",
    )

    st.divider()
    st.header("Metric View Data")

    with st.expander("View headcount metric data"):
        st.dataframe(headcount, width="stretch")

    with st.expander("View attendance metric data"):
        st.dataframe(attendance, width="stretch")

    with st.expander("View leave metric data"):
        st.dataframe(leave, width="stretch")

    with st.expander("View payroll metric data"):
        st.dataframe(payroll, width="stretch")

    st.caption(
        "All displayed metrics are sourced from the approved metric "
        "views. Values depend on the data available after privacy "
        "suppression."
    )

except Exception as error:
    st.error("The dashboard could not load its data.")
    st.code(str(error))
    st.info(
        "Check the PostgreSQL connection, metric view definitions, "
        "metric catalog, and environment configuration."
    )

