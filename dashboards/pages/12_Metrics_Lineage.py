
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

from src.db import database_connection

st.set_page_config(
    page_title="Metrics & Lineage | PulseIQ",
    page_icon="📊",
    layout="wide"
)

st.title("PulseIQ – Metrics & Data Lineage")
st.caption("Task 19 | Metric Monitoring and Data Lineage")

METRICS = {
    "Headcount": {
        "query": """
            SELECT month_start, department_name,
                   headcount AS metric_value
            FROM public.v_monthly_headcount
            ORDER BY month_start
        """,
        "unit": "Employees",
        "description": "Monthly employee headcount.",
        "source": "public.v_monthly_headcount",
        "owner": "HR Analytics"
    },
    "Attendance Rate": {
        "query": """
            SELECT month_start, department_name,
                   attendance_rate_percent AS metric_value
            FROM public.v_monthly_attendance_rate
            ORDER BY month_start
        """,
        "unit": "Percent",
        "description": "Present attendance records divided by total attendance records.",
        "source": "public.v_monthly_attendance_rate",
        "owner": "HR Analytics"
    },
    "Leave Days": {
        "query": """
            SELECT month_start, department_name,
                   total_leave_days AS metric_value
            FROM public.v_monthly_leave_days
            ORDER BY month_start
        """,
        "unit": "Days",
        "description": "Total recorded leave days.",
        "source": "public.v_monthly_leave_days",
        "owner": "HR Analytics"
    },
    "Net Payroll": {
        "query": """
            SELECT month_start, department_name,
                   total_net_payroll AS metric_value
            FROM public.v_monthly_net_payroll
            ORDER BY month_start
        """,
        "unit": "Currency units",
        "description": "Total net payroll by month and department.",
        "source": "public.v_monthly_net_payroll",
        "owner": "Finance"
    }
}


@st.cache_data(ttl=300)
def load_metric(query):
    with database_connection() as connection:
        return pd.read_sql_query(query, connection)


@st.cache_data(ttl=300)
def load_database_status():
    query = """
        SELECT
            CURRENT_TIMESTAMP AS checked_at,
            CURRENT_DATABASE() AS database_name,
            CURRENT_SCHEMA() AS current_schema
    """
    with database_connection() as connection:
        return pd.read_sql_query(query, connection)


if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()

st.sidebar.header("Metric Explorer")

selected_metric = st.sidebar.selectbox(
    "Select metric",
    list(METRICS.keys())
)

config = METRICS[selected_metric]

st.subheader(selected_metric)
st.write(config["description"])

col1, col2, col3 = st.columns(3)

col1.metric("Unit", config["unit"])
col2.metric("Owner", config["owner"])
col3.metric("Privacy Threshold", "5 Employees")

st.caption(f"Source: `{config['source']}`")

try:
    data = load_metric(config["query"])

    if data.empty:
        st.warning("No metric records are available.")
        st.stop()

    data["month_start"] = pd.to_datetime(
        data["month_start"],
        errors="coerce"
    )

    data["metric_value"] = pd.to_numeric(
        data["metric_value"],
        errors="coerce"
    )

    data = data.dropna(
        subset=["month_start", "metric_value"]
    )

    if data.empty:
        st.warning("No valid metric values are available.")
        st.stop()

    departments = sorted(
        data["department_name"].dropna().unique()
    )

    selected_departments = st.sidebar.multiselect(
        "Departments",
        departments,
        default=departments
    )

    filtered = data[
        data["department_name"].isin(selected_departments)
    ].copy()

    if filtered.empty:
        st.warning("No records match the selected departments.")
        st.stop()

    latest_month = filtered["month_start"].max()

    latest_data = filtered[
        filtered["month_start"] == latest_month
    ]

    st.divider()
    st.subheader("Metric Overview")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Latest Reporting Month",
        latest_month.strftime("%B %Y")
    )

    col2.metric(
        "Departments",
        latest_data["department_name"].nunique()
    )

    col3.metric(
        "Average Metric Value",
        f"{latest_data['metric_value'].mean():,.2f}"
    )

    st.divider()
    st.subheader("Monthly Trends")

    chart_data = filtered.pivot_table(
        index="month_start",
        columns="department_name",
        values="metric_value",
        aggfunc="mean"
    )

    st.line_chart(chart_data)

    st.subheader("Metric Details")

    st.dataframe(
        filtered.sort_values(
            "month_start",
            ascending=False
        ),
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        "Download Metric Data",
        data=filtered.to_csv(index=False),
        file_name="pulseiq_metric_data.csv",
        mime="text/csv"
    )

except Exception as error:
    st.error(f"Unable to load metric data: {error}")


st.divider()
st.header("Metric Catalog")

catalog = pd.DataFrame([
    {
        "Metric": name,
        "Definition": config["description"],
        "Unit": config["unit"],
        "Source": config["source"],
        "Owner": config["owner"]
    }
    for name, config in METRICS.items()
])

st.dataframe(
    catalog,
    use_container_width=True,
    hide_index=True
)


st.divider()
st.header("Data Lineage")

st.graphviz_chart("""
digraph PulseIQ {
    rankdir=LR;
    node [shape=box, style="rounded,filled", fillcolor="#E8F0FE"];

    A [label="Raw CSV Files"];
    B [label="Python ETL"];
    C [label="Clean Data"];
    D [label="PostgreSQL Warehouse"];
    E [label="Privacy Metric Views"];
    F [label="Streamlit Dashboard"];

    A -> B;
    B -> C;
    C -> D;
    D -> E;
    E -> F;
}
""")

st.caption(
    "Lineage represents the intended data flow. "
    "Individual source-to-metric mappings must be verified."
)


st.divider()
st.header("Database Status")

try:
    status = load_database_status()

    st.success("PostgreSQL connection successful.")

    st.dataframe(
        status,
        use_container_width=True,
        hide_index=True
    )

    st.caption(
        "Checked-at time indicates when the database was queried, "
        "not the last ETL refresh time."
    )

except Exception as error:
    st.error(f"Database connection failed: {error}")


st.divider()

st.info(
    "Privacy protection: The selected warehouse metric views "
    "apply a minimum group-size threshold of five employees."
)
