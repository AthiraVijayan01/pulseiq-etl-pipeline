
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
    page_icon="ðŸ“Š",
    layout="wide",
)


@st.cache_data(ttl=60)
def query_df(query, params=None):
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params or ())
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]
    return pd.DataFrame(rows, columns=columns)


def load_departments():
    return query_df("""
        SELECT department_name
        FROM dim_department
        ORDER BY department_name
    """)


def load_date_bounds():
    return query_df("""
        SELECT
            LEAST(
                (SELECT MIN(full_date) FROM dim_date),
                (SELECT MIN(joining_date) FROM dim_employee)
            ) AS min_date,
            GREATEST(
                (SELECT MAX(full_date) FROM dim_date),
                (SELECT MAX(leaving_date) FROM dim_employee)
            ) AS max_date
    """)


def department_filter(query, params, departments, alias="d"):
    if departments:
        query += f" AND {alias}.department_name = ANY(%s)"
        params.append(departments)
    else:
        query += " AND FALSE"
    return query, params


def load_headcount(as_of_date, departments):
    query = """
        SELECT COUNT(DISTINCT e.employee_id) AS headcount
        FROM dim_employee e
        JOIN dim_department d ON d.department_key = e.department_key
        WHERE e.joining_date <= %s
          AND (e.leaving_date IS NULL OR e.leaving_date > %s)
          AND e.effective_from <= %s
          AND e.effective_to >= %s
    """
    params = [as_of_date, as_of_date, as_of_date, as_of_date]
    query, params = department_filter(query, params, departments)
    result = query_df(query, params)
    return int(result.iloc[0]["headcount"] or 0)


def load_department_distribution(as_of_date, departments):
    query = """
        SELECT d.department_name,
               COUNT(DISTINCT e.employee_id) AS headcount
        FROM dim_employee e
        JOIN dim_department d ON d.department_key = e.department_key
        WHERE e.joining_date <= %s
          AND (e.leaving_date IS NULL OR e.leaving_date > %s)
          AND e.effective_from <= %s
          AND e.effective_to >= %s
    """
    params = [as_of_date, as_of_date, as_of_date, as_of_date]
    query, params = department_filter(query, params, departments)
    query += """
        GROUP BY d.department_name
        ORDER BY headcount DESC
    """
    return query_df(query, params)


def load_role_distribution(as_of_date, departments):
    query = """
        SELECT r.role_name,
               COUNT(DISTINCT e.employee_id) AS headcount
        FROM dim_employee e
        JOIN dim_department d ON d.department_key = e.department_key
        JOIN dim_role r ON r.role_key = e.role_key
        WHERE e.joining_date <= %s
          AND (e.leaving_date IS NULL OR e.leaving_date > %s)
          AND e.effective_from <= %s
          AND e.effective_to >= %s
    """
    params = [as_of_date, as_of_date, as_of_date, as_of_date]
    query, params = department_filter(query, params, departments)
    query += """
        GROUP BY r.role_name
        ORDER BY headcount DESC
    """
    return query_df(query, params)


def load_monthly_headcount(start_date, end_date, departments):
    query = """
        SELECT dd.full_date AS month,
               d.department_name,
               SUM(f.headcount) AS headcount
        FROM fact_monthly_headcount f
        JOIN dim_date dd ON dd.date_key = f.month_key
        JOIN dim_department d ON d.department_key = f.department_key
        WHERE dd.full_date BETWEEN %s AND %s
    """
    params = [start_date, end_date]
    query, params = department_filter(query, params, departments)
    query += """
        GROUP BY dd.full_date, d.department_name
        ORDER BY dd.full_date, d.department_name
    """
    return query_df(query, params)


def load_employee_movements(start_date, end_date, departments):
    query = """
        SELECT movements.movement_date,
               movements.movement,
               COUNT(*) AS employees
        FROM (
            SELECT e.employee_id,
                   e.department_key,
                   e.joining_date AS movement_date,
                   'Joiners' AS movement
            FROM dim_employee e
            WHERE e.joining_date BETWEEN %s AND %s

            UNION ALL

            SELECT e.employee_id,
                   e.department_key,
                   e.leaving_date AS movement_date,
                   'Leavers' AS movement
            FROM dim_employee e
            WHERE e.leaving_date BETWEEN %s AND %s
        ) movements
        JOIN dim_department d
          ON d.department_key = movements.department_key
        WHERE TRUE
    """
    params = [start_date, end_date, start_date, end_date]
    query, params = department_filter(query, params, departments)
    query += """
        GROUP BY movements.movement_date, movements.movement
        ORDER BY movements.movement_date, movements.movement
    """
    return query_df(query, params)


def load_tenure_data(as_of_date, departments):
    query = """
        SELECT e.employee_id,
               e.joining_date,
               d.department_name
        FROM dim_employee e
        JOIN dim_department d ON d.department_key = e.department_key
        WHERE e.joining_date IS NOT NULL
          AND e.joining_date <= %s
          AND (e.leaving_date IS NULL OR e.leaving_date > %s)
          AND e.effective_from <= %s
          AND e.effective_to >= %s
    """
    params = [as_of_date, as_of_date, as_of_date, as_of_date]
    query, params = department_filter(query, params, departments)
    query += " ORDER BY e.employee_id"

    data = query_df(query, params)

    if data.empty:
        data["tenure_years"] = pd.Series(dtype=float)
        data["tenure_band"] = pd.Series(dtype="object")
        return data

    data["joining_date"] = pd.to_datetime(data["joining_date"])
    days_employed = (
        pd.Timestamp(as_of_date) - data["joining_date"]
    ).dt.days

    data["tenure_years"] = (days_employed / 365.25).clip(lower=0)
    data["tenure_band"] = pd.cut(
        data["tenure_years"],
        bins=[0, 1, 3, 5, float("inf")],
        labels=["Under 1 year", "1-3 years", "3-5 years", "5+ years"],
        right=False,
        include_lowest=True,
    )
    return data


def load_attendance_daily(start_date, end_date, departments):
    query = """
        SELECT
            dt.full_date,
            COUNT(*) AS total_records,
            COUNT(*) FILTER (
                WHERE LOWER(TRIM(a.attendance_status)) = 'present'
            ) AS present_records,
            COUNT(*) FILTER (
                WHERE LOWER(TRIM(a.attendance_status)) = 'absent'
            ) AS absent_records,
            COUNT(*) FILTER (
                WHERE LOWER(TRIM(a.attendance_status)) = 'late'
            ) AS late_records,
            ROUND(AVG(a.hours_worked)::numeric, 2)
                AS average_hours_worked
        FROM fact_attendance a
        JOIN dim_date dt ON dt.date_key = a.date_key
        JOIN dim_employee e ON e.employee_key = a.employee_key
        JOIN dim_department d ON d.department_key = e.department_key
        WHERE dt.full_date BETWEEN %s AND %s
    """
    params = [start_date, end_date]
    query, params = department_filter(query, params, departments)
    query += """
        GROUP BY dt.full_date
        ORDER BY dt.full_date
    """
    return query_df(query, params)


def load_attendance_by_department(start_date, end_date, departments):
    query = """
        SELECT
            d.department_name,
            COUNT(*) AS total_records,
            COUNT(*) FILTER (
                WHERE LOWER(TRIM(a.attendance_status)) = 'present'
            ) AS present_records,
            COUNT(*) FILTER (
                WHERE LOWER(TRIM(a.attendance_status)) = 'absent'
            ) AS absent_records,
            COUNT(*) FILTER (
                WHERE LOWER(TRIM(a.attendance_status)) = 'late'
            ) AS late_records,
            ROUND(AVG(a.hours_worked)::numeric, 2)
                AS average_hours_worked
        FROM fact_attendance a
        JOIN dim_date dt ON dt.date_key = a.date_key
        JOIN dim_employee e ON e.employee_key = a.employee_key
        JOIN dim_department d ON d.department_key = e.department_key
        WHERE dt.full_date BETWEEN %s AND %s
    """
    params = [start_date, end_date]
    query, params = department_filter(query, params, departments)
    query += """
        GROUP BY d.department_name
        ORDER BY d.department_name
    """
    return query_df(query, params)


def load_attendance_anomalies(start_date, end_date, departments):
    query = """
        SELECT
            e.employee_id,
            dt.full_date,
            d.department_name,
            a.attendance_status,
            a.hours_worked,
            CASE
                WHEN a.attendance_status IS NULL
                     OR TRIM(a.attendance_status) = ''
                    THEN 'Missing attendance status'
                WHEN a.hours_worked IS NULL
                    THEN 'Missing working hours'
                WHEN a.hours_worked < 0
                    THEN 'Negative working hours'
                WHEN a.hours_worked > 12
                    THEN 'Working hours exceed 12'
                WHEN LOWER(TRIM(a.attendance_status))
                     IN ('present', 'late')
                     AND a.hours_worked <= 0
                    THEN 'Present or late status with zero hours'
                WHEN LOWER(TRIM(a.attendance_status))
                     NOT IN (
                         'present', 'absent', 'late', 'on leave', 'leave'
                     )
                    THEN 'Unrecognized attendance status'
            END AS anomaly_reason
        FROM fact_attendance a
        JOIN dim_date dt ON dt.date_key = a.date_key
        JOIN dim_employee e ON e.employee_key = a.employee_key
        JOIN dim_department d ON d.department_key = e.department_key
        WHERE dt.full_date BETWEEN %s AND %s
          AND (
              a.attendance_status IS NULL
              OR TRIM(a.attendance_status) = ''
              OR a.hours_worked IS NULL
              OR a.hours_worked < 0
              OR a.hours_worked > 12
              OR (
                  LOWER(TRIM(a.attendance_status)) IN ('present', 'late')
                  AND a.hours_worked <= 0
              )
              OR LOWER(TRIM(a.attendance_status))
                 NOT IN (
                     'present', 'absent', 'late', 'on leave', 'leave'
                 )
          )
    """
    params = [start_date, end_date]
    query, params = department_filter(query, params, departments)
    query += " ORDER BY dt.full_date, e.employee_id"
    return query_df(query, params)


def load_leave_summary(start_date, end_date, departments):
    query = """
        SELECT
            DATE_TRUNC('month', start_dt.full_date)::date AS leave_month,
            lt.leave_type_name,
            COUNT(*) AS leave_events,
            SUM(l.days) AS total_leave_days
        FROM fact_leave l
        JOIN dim_date start_dt ON start_dt.date_key = l.leave_start_key
        JOIN dim_employee e ON e.employee_key = l.employee_key
        JOIN dim_department d ON d.department_key = e.department_key
        JOIN dim_leave_type lt ON lt.leave_type_key = l.leave_type_key
        WHERE start_dt.full_date BETWEEN %s AND %s
    """
    params = [start_date, end_date]
    query, params = department_filter(query, params, departments)
    query += """
        GROUP BY DATE_TRUNC('month', start_dt.full_date)::date,
                 lt.leave_type_name
        ORDER BY leave_month, lt.leave_type_name
    """
    return query_df(query, params)


st.title("PulseIQ HR Analytics Dashboard")
st.caption(
    "Human resources metrics powered by the PostgreSQL data warehouse."
)

try:
    departments_df = load_departments()
    bounds_df = load_date_bounds()

    if departments_df.empty:
        st.warning("No departments found. Load the warehouse data first.")
        st.stop()

    department_options = departments_df["department_name"].tolist()

    with st.sidebar:
        st.header("Dashboard Filters")

        selected_departments = st.multiselect(
            "Departments",
            options=department_options,
            default=department_options,
        )

        if bounds_df.empty or pd.isna(bounds_df.iloc[0]["min_date"]):
            st.warning("No dates are available in the warehouse.")
            st.stop()

        min_date = pd.to_datetime(bounds_df.iloc[0]["min_date"]).date()
        max_date = pd.to_datetime(bounds_df.iloc[0]["max_date"]).date()

        date_range = st.date_input(
            "Reporting date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        start_date, end_date = date_range
    elif isinstance(date_range, (tuple, list)) and len(date_range) == 1:
        start_date = end_date = date_range[0]
    else:
        start_date = end_date = date_range

    if start_date > end_date:
        st.error("The start date must be before the end date.")
        st.stop()

    headcount = load_headcount(end_date, selected_departments)
    department_data = load_department_distribution(
        end_date, selected_departments
    )
    role_data = load_role_distribution(end_date, selected_departments)
    monthly_data = load_monthly_headcount(
        start_date, end_date, selected_departments
    )
    movement_data = load_employee_movements(
        start_date, end_date, selected_departments
    )
    tenure_data = load_tenure_data(end_date, selected_departments)

    attendance_daily = load_attendance_daily(
        start_date, end_date, selected_departments
    )
    attendance_department = load_attendance_by_department(
        start_date, end_date, selected_departments
    )
    attendance_anomalies = load_attendance_anomalies(
        start_date, end_date, selected_departments
    )
    leave_summary = load_leave_summary(
        start_date, end_date, selected_departments
    )

    if tenure_data.empty:
        tenure_summary = pd.DataFrame(
            {"tenure_band": [], "employees": []}
        )
    else:
        tenure_summary = (
            tenure_data.groupby("tenure_band", observed=False)
            .size()
            .reset_index(name="employees")
        )

    joiners = 0
    leavers = 0

    if not movement_data.empty:
        joiners = int(
            movement_data.loc[
                movement_data["movement"] == "Joiners", "employees"
            ].sum()
        )
        leavers = int(
            movement_data.loc[
                movement_data["movement"] == "Leavers", "employees"
            ].sum()
        )

    first, second, third, fourth = st.columns(4)
    first.metric("Headcount", f"{headcount:,}")
    second.metric("Departments", f"{len(department_data):,}")
    third.metric("Joiners in period", f"{joiners:,}")
    fourth.metric("Leavers in period", f"{leavers:,}")

    st.subheader("Key Takeaways")
    takeaways = []

    if not department_data.empty:
        largest_department = department_data.iloc[0]
        takeaways.append(
            f"Largest department: {largest_department['department_name']} "
            f"({int(largest_department['headcount'])} employees)."
        )

    if not role_data.empty:
        largest_role = role_data.iloc[0]
        takeaways.append(
            f"Most common role: {largest_role['role_name']} "
            f"({int(largest_role['headcount'])} employees)."
        )

    if joiners > leavers:
        takeaways.append(
            f"There were {joiners - leavers} more joiners than leavers "
            "during the selected period."
        )
    elif leavers > joiners:
        takeaways.append(
            f"There were {leavers - joiners} more leavers than joiners "
            "during the selected period."
        )
    else:
        takeaways.append(
            "Joiners and leavers were equal during the selected period."
        )

    if not tenure_summary.empty:
        nonzero_tenure = tenure_summary[
            tenure_summary["employees"] > 0
        ]
        if not nonzero_tenure.empty:
            largest_band = nonzero_tenure.iloc[0]
            takeaways.append(
                f"Tenure band with the most employees: "
                f"{largest_band['tenure_band']} "
                f"({int(largest_band['employees'])} employees)."
            )

    for takeaway in takeaways:
        st.write(f"- {takeaway}")

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("Headcount by Department")
        if department_data.empty:
            st.info("No department data for these filters.")
        else:
            figure = px.bar(
                department_data,
                x="department_name",
                y="headcount",
                text="headcount",
                labels={
                    "department_name": "Department",
                    "headcount": "Employees",
                },
            )
            figure.update_layout(xaxis_tickangle=-30)
            st.plotly_chart(figure, width="stretch")

    with right:
        st.subheader("Employee Role Distribution")
        if role_data.empty:
            st.info("No role data for these filters.")
        else:
            figure = px.pie(
                role_data,
                names="role_name",
                values="headcount",
                hole=0.45,
            )
            st.plotly_chart(figure, width="stretch")

    st.subheader("Monthly Headcount Trend")
    if monthly_data.empty:
        st.info("No monthly headcount snapshots found for this period.")
    else:
        figure = px.line(
            monthly_data,
            x="month",
            y="headcount",
            color="department_name",
            markers=True,
            labels={
                "month": "Month",
                "headcount": "Headcount",
                "department_name": "Department",
            },
        )
        st.plotly_chart(figure, width="stretch")

    st.subheader("Employee Movements")
    if movement_data.empty:
        st.info("No joiners or leavers were found for this period.")
    else:
        figure = px.bar(
            movement_data,
            x="movement_date",
            y="employees",
            color="movement",
            barmode="group",
            labels={
                "movement_date": "Date",
                "employees": "Employees",
                "movement": "Movement",
            },
        )
        st.plotly_chart(figure, width="stretch")

    st.subheader("Employee Tenure Bands")
    if tenure_summary.empty or tenure_summary["employees"].sum() == 0:
        st.info("No tenure data is available for these filters.")
    else:
        figure = px.bar(
            tenure_summary,
            x="tenure_band",
            y="employees",
            text="employees",
            category_orders={
                "tenure_band": [
                    "Under 1 year", "1-3 years", "3-5 years", "5+ years"
                ]
            },
            labels={
                "tenure_band": "Length of Service",
                "employees": "Employees",
            },
        )
        st.plotly_chart(figure, width="stretch")

    st.divider()
    st.header("Attendance Analytics")
    st.caption(
        "Attendance summaries are based on recorded attendance rows. "
        "The current dataset is small, so interpret trends cautiously."
    )

    if attendance_daily.empty:
        st.info("No attendance records were found for these filters.")
    else:
        total_records = int(attendance_daily["total_records"].sum())
        total_present = int(attendance_daily["present_records"].sum())
        total_absent = int(attendance_daily["absent_records"].sum())
        total_late = int(attendance_daily["late_records"].sum())

        present_share = (
            total_present / total_records * 100 if total_records else 0
        )

        metric1, metric2, metric3, metric4 = st.columns(4)
        metric1.metric("Attendance Records", total_records)
        metric2.metric("Present", total_present)
        metric3.metric("Absent", total_absent)
        metric4.metric("Late", total_late)

        st.metric(
            "Present Share of Recorded Rows",
            f"{present_share:.1f}%"
        )

        left, right = st.columns(2)

        with left:
            st.subheader("Daily Attendance Status")
            status_data = attendance_daily.melt(
                id_vars=["full_date"],
                value_vars=[
                    "present_records",
                    "absent_records",
                    "late_records",
                ],
                var_name="attendance_status",
                value_name="records",
            )
            status_data["attendance_status"] = (
                status_data["attendance_status"]
                .str.replace("_records", "", regex=False)
                .str.title()
            )

            figure = px.bar(
                status_data,
                x="full_date",
                y="records",
                color="attendance_status",
                barmode="group",
                labels={
                    "full_date": "Date",
                    "records": "Records",
                    "attendance_status": "Status",
                },
            )
            st.plotly_chart(figure, width="stretch")

        with right:
            st.subheader("Average Hours Worked by Date")
            figure = px.line(
                attendance_daily,
                x="full_date",
                y="average_hours_worked",
                markers=True,
                labels={
                    "full_date": "Date",
                    "average_hours_worked": "Average Hours",
                },
            )
            st.plotly_chart(figure, width="stretch")

        st.subheader("Attendance by Department")
        if attendance_department.empty:
            st.info("No department attendance data is available.")
        else:
            chart_data = attendance_department.melt(
                id_vars=["department_name"],
                value_vars=[
                    "present_records",
                    "absent_records",
                    "late_records",
                ],
                var_name="attendance_status",
                value_name="records",
            )
            chart_data["attendance_status"] = (
                chart_data["attendance_status"]
                .str.replace("_records", "", regex=False)
                .str.title()
            )
            figure = px.bar(
                chart_data,
                x="department_name",
                y="records",
                color="attendance_status",
                barmode="group",
                labels={
                    "department_name": "Department",
                    "records": "Records",
                    "attendance_status": "Status",
                },
            )
            st.plotly_chart(figure, width="stretch")
            st.dataframe(attendance_department, width="stretch")

        st.subheader("Attendance Anomaly Review")
        if attendance_anomalies.empty:
            st.success(
                "No records matched the configured anomaly checks. "
                "This does not guarantee that all records are correct."
            )
        else:
            st.warning(
                f"{len(attendance_anomalies)} record(s) matched "
                "the configured anomaly checks and should be reviewed."
            )
            st.dataframe(attendance_anomalies, width="stretch")

        st.download_button(
            "Download Daily Attendance CSV",
            data=attendance_daily.to_csv(index=False).encode("utf-8"),
            file_name="pulseiq_daily_attendance.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download Attendance Anomalies CSV",
            data=attendance_anomalies.to_csv(index=False).encode("utf-8"),
            file_name="pulseiq_attendance_anomalies.csv",
            mime="text/csv",
        )

    st.subheader("Leave Analysis")
    if leave_summary.empty:
        st.info("No leave records were found for these filters.")
    else:
        figure = px.bar(
            leave_summary,
            x="leave_month",
            y="total_leave_days",
            color="leave_type_name",
            barmode="group",
            labels={
                "leave_month": "Month",
                "total_leave_days": "Leave Days",
                "leave_type_name": "Leave Type",
            },
        )
        st.plotly_chart(figure, width="stretch")
        st.dataframe(leave_summary, width="stretch")

        st.download_button(
            "Download Leave Summary CSV",
            data=leave_summary.to_csv(index=False).encode("utf-8"),
            file_name="pulseiq_leave_summary.csv",
            mime="text/csv",
        )

    with st.expander("View tenure data"):
        st.dataframe(tenure_data, width="stretch")

    with st.expander("View department data"):
        st.dataframe(department_data, width="stretch")

    with st.expander("View role data"):
        st.dataframe(role_data, width="stretch")

    with st.expander("View monthly headcount data"):
        st.dataframe(monthly_data, width="stretch")

    with st.expander("View employee movement data"):
        st.dataframe(movement_data, width="stretch")

    st.subheader("Download Dashboard Data")
    download_col1, download_col2, download_col3 = st.columns(3)

    with download_col1:
        st.download_button(
            "Download Department CSV",
            data=department_data.to_csv(index=False).encode("utf-8"),
            file_name="pulseiq_department_data.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download Role CSV",
            data=role_data.to_csv(index=False).encode("utf-8"),
            file_name="pulseiq_role_data.csv",
            mime="text/csv",
        )

    with download_col2:
        st.download_button(
            "Download Monthly Headcount CSV",
            data=monthly_data.to_csv(index=False).encode("utf-8"),
            file_name="pulseiq_monthly_headcount.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download Employee Movements CSV",
            data=movement_data.to_csv(index=False).encode("utf-8"),
            file_name="pulseiq_employee_movements.csv",
            mime="text/csv",
        )

    with download_col3:
        st.download_button(
            "Download Tenure CSV",
            data=tenure_data.to_csv(index=False).encode("utf-8"),
            file_name="pulseiq_employee_tenure.csv",
            mime="text/csv",
        )

    st.caption(
        f"Reporting period: {start_date} to {end_date}. "
        "Metrics depend on the data currently loaded into the warehouse."
    )

except Exception as error:
    st.error("The dashboard could not load its data.")
    st.code(str(error))
    st.info(
        "Check the PostgreSQL connection, database schema, "
        "warehouse data, and environment configuration."
    )



