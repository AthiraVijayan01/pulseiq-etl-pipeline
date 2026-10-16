
import sys
from pathlib import Path
from datetime import date

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
def query_df(query, params=None):
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params or ())
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]
    return pd.DataFrame(rows, columns=columns)


def load_departments():
    return query_df(
        """
        SELECT department_name
        FROM dim_department
        ORDER BY department_name
        """
    )


def load_date_bounds():
    return query_df(
        """
        SELECT
            LEAST(
                (SELECT MIN(full_date) FROM dim_date),
                (SELECT MIN(joining_date) FROM dim_employee)
            ) AS min_date,
            GREATEST(
                (SELECT MAX(full_date) FROM dim_date),
                (SELECT MAX(leaving_date) FROM dim_employee)
            ) AS max_date
        """
    )

def load_headcount(as_of_date, departments):
    query = """
        SELECT COUNT(DISTINCT e.employee_id) AS headcount
        FROM dim_employee e
        JOIN dim_department d
          ON d.department_key = e.department_key
        WHERE e.joining_date <= %s
          AND (e.leaving_date IS NULL OR e.leaving_date > %s)
          AND e.effective_from <= %s
          AND e.effective_to >= %s
    """
    params = [as_of_date, as_of_date, as_of_date, as_of_date]

    if departments:
        query += " AND d.department_name = ANY(%s)"
        params.append(departments)
    else:
        query += " AND FALSE"

    result = query_df(query, params)
    return int(result.iloc[0]["headcount"] or 0)


def load_department_distribution(as_of_date, departments):
    query = """
        SELECT d.department_name,
               COUNT(DISTINCT e.employee_id) AS headcount
        FROM dim_employee e
        JOIN dim_department d
          ON d.department_key = e.department_key
        WHERE e.joining_date <= %s
          AND (e.leaving_date IS NULL OR e.leaving_date > %s)
          AND e.effective_from <= %s
          AND e.effective_to >= %s
    """
    params = [as_of_date, as_of_date, as_of_date, as_of_date]

    if departments:
        query += " AND d.department_name = ANY(%s)"
        params.append(departments)
    else:
        query += " AND FALSE"

    query += " GROUP BY d.department_name ORDER BY headcount DESC"
    return query_df(query, params)


def load_role_distribution(as_of_date, departments):
    query = """
        SELECT r.role_name,
               COUNT(DISTINCT e.employee_id) AS headcount
        FROM dim_employee e
        JOIN dim_department d
          ON d.department_key = e.department_key
        JOIN dim_role r
          ON r.role_key = e.role_key
        WHERE e.joining_date <= %s
          AND (e.leaving_date IS NULL OR e.leaving_date > %s)
          AND e.effective_from <= %s
          AND e.effective_to >= %s
    """
    params = [as_of_date, as_of_date, as_of_date, as_of_date]

    if departments:
        query += " AND d.department_name = ANY(%s)"
        params.append(departments)
    else:
        query += " AND FALSE"

    query += " GROUP BY r.role_name ORDER BY headcount DESC"
    return query_df(query, params)


def load_monthly_headcount(start_date, end_date, departments):
    query = """
        SELECT dd.full_date AS month,
               d.department_name,
               SUM(f.headcount) AS headcount
        FROM fact_monthly_headcount f
        JOIN dim_date dd
          ON dd.date_key = f.month_key
        JOIN dim_department d
          ON d.department_key = f.department_key
        WHERE dd.full_date BETWEEN %s AND %s
    """
    params = [start_date, end_date]

    if departments:
        query += " AND d.department_name = ANY(%s)"
        params.append(departments)
    else:
        query += " AND FALSE"

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
                   e.joining_date AS movement_date,
                   'Joiners' AS movement
            FROM dim_employee e
            JOIN dim_department d
              ON d.department_key = e.department_key
            WHERE e.joining_date BETWEEN %s AND %s

            UNION ALL

            SELECT e.employee_id,
                   e.leaving_date AS movement_date,
                   'Leavers' AS movement
            FROM dim_employee e
            JOIN dim_department d
              ON d.department_key = e.department_key
            WHERE e.leaving_date BETWEEN %s AND %s
        ) movements
        WHERE TRUE
    """
    params = [start_date, end_date, start_date, end_date]

    if departments:
        query += """
            AND EXISTS (
                SELECT 1
                FROM dim_employee e
                JOIN dim_department d
                  ON d.department_key = e.department_key
                WHERE e.employee_id = movements.employee_id
                  AND d.department_name = ANY(%s)
            )
        """
        params.append(departments)
    else:
        query += " AND FALSE"

    query += """
        GROUP BY movements.movement_date, movements.movement
        ORDER BY movements.movement_date, movements.movement
    """
    return query_df(query, params)



def load_tenure_data(as_of_date, departments):
    query = """
        SELECT
            e.employee_id,
            e.joining_date,
            d.department_name
        FROM dim_employee e
        JOIN dim_department d
          ON d.department_key = e.department_key
        WHERE e.joining_date IS NOT NULL
          AND e.joining_date <= %s
          AND (e.leaving_date IS NULL OR e.leaving_date > %s)
          AND e.effective_from <= %s
          AND e.effective_to >= %s
    """
    params = [as_of_date, as_of_date, as_of_date, as_of_date]

    if departments:
        query += " AND d.department_name = ANY(%s)"
        params.append(departments)
    else:
        query += " AND FALSE"

    query += " ORDER BY e.employee_id"
    data = query_df(query, params)

    if data.empty:
        data["tenure_years"] = pd.Series(dtype=float)
        data["tenure_band"] = pd.Series(dtype="object")
        return data

    data["joining_date"] = pd.to_datetime(data["joining_date"])
    days_employed = (pd.Timestamp(as_of_date) - data["joining_date"]).dt.days
    data["tenure_years"] = (days_employed / 365.25).clip(lower=0)

    data["tenure_band"] = pd.cut(
        data["tenure_years"],
        bins=[0, 1, 3, 5, float("inf")],
        labels=["Under 1 year", "1–3 years", "3–5 years", "5+ years"],
        right=False,
        include_lowest=True,
    )
    return data

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
            st.warning("No dates are available in dim_date.")
            st.stop()

        min_date = pd.to_datetime(
            bounds_df.iloc[0]["min_date"]
        ).date()
        max_date = pd.to_datetime(
            bounds_df.iloc[0]["max_date"]
        ).date()

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
    role_data = load_role_distribution(
        end_date, selected_departments
    )
    monthly_data = load_monthly_headcount(
        start_date, end_date, selected_departments
    )
    movement_data = load_employee_movements(
        start_date, end_date, selected_departments
    )

    tenure_data = load_tenure_data(end_date, selected_departments)

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
        nonzero_tenure = tenure_summary[tenure_summary["employees"] > 0]
        if not nonzero_tenure.empty:
            largest_band = nonzero_tenure.iloc[0]
            takeaways.append(
                f"Tenure band with the most employees: "
                f"{largest_band['tenure_band']} "
                f"({int(largest_band['employees'])} employees)."
            )

    if takeaways:
        for takeaway in takeaways:
            st.write(f"- {takeaway}")
    else:
        st.info("No takeaways are available for the selected filters.")

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
            st.plotly_chart(figure, use_container_width=True)

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
            st.plotly_chart(figure, use_container_width=True)

    st.subheader("Monthly Headcount Trend")

    if monthly_data.empty:
        st.info(
            "No monthly headcount snapshots found for this period. "
            "Check the warehouse loading step."
        )
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
        st.plotly_chart(figure, use_container_width=True)

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
        st.plotly_chart(figure, use_container_width=True)

    st.subheader("Employee Tenure Bands")

    if tenure_summary.empty or tenure_summary["employees"].sum() == 0:
        st.info("No tenure data is available for the selected filters.")
    else:
        figure = px.bar(
            tenure_summary,
            x="tenure_band",
            y="employees",
            text="employees",
            category_orders={
                "tenure_band": [
                    "Under 1 year",
                    "1–3 years",
                    "3–5 years",
                    "5+ years",
                ]
            },
            labels={
                "tenure_band": "Length of Service",
                "employees": "Employees",
            },
        )
        st.plotly_chart(figure, use_container_width=True)

    with st.expander("View tenure data"):
        st.dataframe(tenure_data, use_container_width=True)

    with st.expander("View department data"):
        st.dataframe(department_data, use_container_width=True)

    with st.expander("View role data"):
        st.dataframe(role_data, use_container_width=True)

    with st.expander("View monthly headcount data"):
        st.dataframe(monthly_data, use_container_width=True)

    with st.expander("View employee movement data"):
        st.dataframe(movement_data, use_container_width=True)

    st.subheader("Download Dashboard Data")
    download_col1, download_col2, download_col3 = st.columns(3)

    with download_col1:
        st.download_button(
            "Download department CSV",
            data=department_data.to_csv(index=False).encode("utf-8"),
            file_name="pulseiq_department_data.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download role CSV",
            data=role_data.to_csv(index=False).encode("utf-8"),
            file_name="pulseiq_role_data.csv",
            mime="text/csv",
        )

    with download_col2:
        st.download_button(
            "Download monthly headcount CSV",
            data=monthly_data.to_csv(index=False).encode("utf-8"),
            file_name="pulseiq_monthly_headcount.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download employee movements CSV",
            data=movement_data.to_csv(index=False).encode("utf-8"),
            file_name="pulseiq_employee_movements.csv",
            mime="text/csv",
        )

    with download_col3:
        st.download_button(
            "Download tenure CSV",
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
        "Check your PostgreSQL connection, database schema, "
        "warehouse data, and .env configuration."
    )
