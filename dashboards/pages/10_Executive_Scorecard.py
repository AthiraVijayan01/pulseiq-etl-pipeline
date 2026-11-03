
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.db import get_connection


st.set_page_config(
    page_title="Executive Company-Health Scorecard",
    page_icon="📊",
    layout="wide",
)

st.markdown(
    """
    <style>
    @page {
        size: A4 portrait;
        margin: 12mm;
    }

    @media print {
        [data-testid="stSidebar"],
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stStatusWidget"],
        .no-print {
            display: none !important;
        }

        .block-container {
            padding: 0 !important;
            max-width: 100% !important;
        }

        [data-testid="stMetric"] {
            break-inside: avoid;
        }
    }

    .scorecard-subtitle {
        color: #64748b;
        font-size: 0.9rem;
        margin-bottom: 1rem;
    }

    .kpi-status {
        display: inline-block;
        padding: 3px 9px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-top: 4px;
    }

    .status-good {
        background: #dcfce7;
        color: #166534;
    }

    .status-warning {
        background: #fef3c7;
        color: #92400e;
    }

    .status-info {
        background: #e2e8f0;
        color: #334155;
    }

    .kpi-card {
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px;
        min-height: 145px;
        margin-bottom: 12px;
    }

    .kpi-label {
        color: #64748b;
        font-size: 0.85rem;
        font-weight: 600;
    }

    .kpi-value {
        font-size: 1.55rem;
        font-weight: 700;
        margin: 8px 0;
        color: #0f172a;
    }

    .kpi-detail {
        font-size: 0.8rem;
        color: #64748b;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def fetch_dataframe(query):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]

    return pd.DataFrame(rows, columns=columns)


@st.cache_data(ttl=300)
def load_scorecard_data():
    headcount = fetch_dataframe(
        """
        SELECT
            year_month,
            SUM(headcount_end) AS headcount
        FROM phase2.v_monthly_attrition_exits
        GROUP BY year_month
        ORDER BY year_month
        """
    )

    attrition = fetch_dataframe(
        """
        SELECT
            year_month,
            SUM(headcount_start) AS headcount_start,
            SUM(exits) AS exits
        FROM phase2.v_monthly_attrition_exits
        GROUP BY year_month
        ORDER BY year_month
        """
    )

    attendance = fetch_dataframe(
        """
        SELECT
            year_month,
            SUM(scheduled_days) AS scheduled_days,
            SUM(present_days) AS present_days
        FROM phase2.v_monthly_attendance_rate
        GROUP BY year_month
        ORDER BY year_month
        """
    )

    leave = fetch_dataframe(
        """
        SELECT
            year_month,
            SUM(approved_leave_days) AS approved_leave_days
        FROM phase2.v_monthly_leave_days
        GROUP BY year_month
        ORDER BY year_month
        """
    )

    finance = fetch_dataframe(
        """
        SELECT
            posting_period AS year_month,
            revenue,
            expenses,
            net_profit,
            profit_margin_pct
        FROM phase3.v_pnl_monthly
        ORDER BY posting_period
        """
    )

    targets = pd.read_csv(ROOT / "clean" / "kpi_targets.csv")

    targets["month"] = pd.to_datetime(
        targets["month"], errors="coerce"
    )

    targets["year_month"] = targets["month"].dt.strftime("%Y-%m")

    for column in [
        "attendance_rate_target",
        "attrition_monthly_target_pct",
    ]:
        targets[column] = pd.to_numeric(
            targets[column], errors="coerce"
        )

    target_monthly = (
        targets.groupby("year_month", as_index=False)
        .agg(
            attendance_target=(
                "attendance_rate_target", "mean"
            ),
            attrition_target=(
                "attrition_monthly_target_pct", "mean"
            ),
        )
    )

    data = headcount.merge(
        attrition,
        on="year_month",
        how="outer",
    )

    data = data.merge(
        attendance,
        on="year_month",
        how="outer",
    )

    data = data.merge(
        leave,
        on="year_month",
        how="outer",
    )

    data = data.merge(
        finance,
        on="year_month",
        how="outer",
    )

    data = data.merge(
        target_monthly,
        on="year_month",
        how="left",
    )

    numeric_columns = [
        "headcount",
        "headcount_start",
        "exits",
        "scheduled_days",
        "present_days",
        "approved_leave_days",
        "revenue",
        "expenses",
        "net_profit",
        "profit_margin_pct",
        "attendance_target",
        "attrition_target",
    ]

    for column in numeric_columns:
        if column in data.columns:
            data[column] = pd.to_numeric(
                data[column], errors="coerce"
            )

    data["attendance_rate"] = (
        data["present_days"]
        .div(data["scheduled_days"])
        .mul(100)
    )

    data["attrition_rate"] = (
        data["exits"]
        .div(data["headcount_start"])
        .mul(100)
    )

    data["attendance_target"] = (
        data["attendance_target"] * 100
    )

    data = data.sort_values("year_month").reset_index(drop=True)

    return data


def format_value(value, metric_type):
    if pd.isna(value):
        return "N/A"

    if metric_type == "currency":
        return f"₹{value:,.2f}"

    if metric_type == "percentage":
        return f"{value:.2f}%"

    if metric_type == "days":
        return f"{value:,.0f} days"

    return f"{value:,.0f}"


def get_trend(current, previous, metric_type):
    if pd.isna(current) or pd.isna(previous):
        return "Previous month unavailable"

    difference = current - previous

    if metric_type == "percentage":
        return f"{difference:+.2f} percentage points"

    if previous != 0:
        percentage_change = difference / abs(previous) * 100
        return f"{difference:+,.2f} ({percentage_change:+.2f}%)"

    return f"{difference:+,.2f} versus previous month"


def get_status(actual, target, higher_is_better):
    if pd.isna(actual) or pd.isna(target):
        return "Informational", "status-info"

    if higher_is_better:
        if actual >= target:
            return "On Target", "status-good"
        return "Below Target", "status-warning"

    if actual <= target:
        return "On Target", "status-good"

    return "Above Target", "status-warning"


def render_kpi_card(
    label,
    value,
    target,
    trend,
    status,
    status_class,
):
    target_text = (
        format_value(target, "percentage")
        if pd.notna(target)
        else "Not defined"
    )

    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-detail">Target: {target_text}</div>
            <div class="kpi-detail">Trend: {trend}</div>
            <span class="kpi-status {status_class}">
                {status}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.title("Executive Company-Health Scorecard")

st.markdown(
    """
    <div class="scorecard-subtitle">
        Organisation-level workforce, attendance and financial
        performance summary. Select a reporting month to review
        company health.
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    data = load_scorecard_data()

except Exception as error:
    st.error(f"Unable to load scorecard data: {error}")
    st.stop()


if data.empty:
    st.warning("No monthly metric data is available.")
    st.stop()


months = data["year_month"].dropna().sort_values().unique().tolist()

if not months:
    st.warning("No valid reporting months were found.")
    st.stop()


st.markdown('<div class="no-print">', unsafe_allow_html=True)

selected_month = st.selectbox(
    "Select reporting month",
    options=months,
    index=len(months) - 1,
)

st.markdown("</div>", unsafe_allow_html=True)


selected_rows = data[
    data["year_month"] == selected_month
]

previous_rows = data[
    data["year_month"] < selected_month
]

if selected_rows.empty:
    st.warning("No data found for the selected month.")
    st.stop()

current = selected_rows.iloc[0]

previous = (
    previous_rows.iloc[-1]
    if not previous_rows.empty
    else None
)


def previous_value(column):
    if previous is None:
        return float("nan")
    return previous.get(column, float("nan"))


st.caption(
    f"Reporting month: {selected_month} | "
    "Actual values sourced from verified Phase 2 and Phase 3 "
    "metric views."
)


# KPI definitions:
# (label, source column, format, target column, higher is better)

kpis = [
    (
        "Employee Headcount",
        "headcount",
        "count",
        None,
        None,
    ),
    (
        "Attendance Rate",
        "attendance_rate",
        "percentage",
        "attendance_target",
        True,
    ),
    (
        "Monthly Attrition Rate",
        "attrition_rate",
        "percentage",
        "attrition_target",
        False,
    ),
    (
        "Approved Leave Days",
        "approved_leave_days",
        "days",
        None,
        None,
    ),
    (
        "Revenue",
        "revenue",
        "currency",
        None,
        None,
    ),
    (
        "Expenses",
        "expenses",
        "currency",
        None,
        None,
    ),
    (
        "Net Profit",
        "net_profit",
        "currency",
        None,
        None,
    ),
    (
        "Profit Margin",
        "profit_margin_pct",
        "percentage",
        None,
        None,
    ),
]


st.subheader("Company Health — Eight Headline KPIs")

for start in range(0, len(kpis), 2):
    columns = st.columns(2)

    for column, kpi in zip(columns, kpis[start:start + 2]):
        label, source, metric_type, target_column, higher_is_better = kpi

        actual = current.get(source, float("nan"))
        prior = previous_value(source)

        target = (
            current.get(target_column, float("nan"))
            if target_column
            else float("nan")
        )

        trend = get_trend(actual, prior, metric_type)

        if target_column:
            status, status_class = get_status(
                actual,
                target,
                higher_is_better,
            )
        else:
            status = "Informational"
            status_class = "status-info"

        with column:
            render_kpi_card(
                label=label,
                value=format_value(actual, metric_type),
                target=target,
                trend=trend,
                status=status,
                status_class=status_class,
            )


st.divider()

st.subheader("KPI Details and Justification")

justifications = [
    (
        "Employee Headcount",
        "Shows the size of the active workforce at the end of the selected month."
    ),
    (
        "Attendance Rate",
        "Measures employee attendance against scheduled working days and is compared with the official 94% target."
    ),
    (
        "Monthly Attrition Rate",
        "Measures exits relative to opening headcount and is compared with the official 1% target."
    ),
    (
        "Approved Leave Days",
        "Shows the volume of approved employee leave recorded for the selected month."
    ),
    (
        "Revenue",
        "Measures income generated during the reporting month."
    ),
    (
        "Expenses",
        "Tracks monthly operating and other expenses recorded in the Profit and Loss metric view."
    ),
    (
        "Net Profit",
        "Shows the financial result after subtracting expenses from revenue."
    ),
    (
        "Profit Margin",
        "Shows the percentage of revenue retained as net profit and helps assess profitability."
    ),
]

for label, explanation in justifications:
    st.markdown(f"**{label}:** {explanation}")


st.divider()

st.subheader("Detailed Dashboard Navigation")

navigation = [
    (
        "Attendance and Leave",
        "pages/1_Attendance_Leave.py",
    ),
    (
        "Attrition Analytics",
        "pages/2_Attrition.py",
    ),
    (
        "Financial Analytics",
        "pages/6_Financial_Analytics.py",
    ),
    (
        "Receivables and Cash Flow",
        "pages/7_Receivables_Cash_Flow.py",
    ),
]

nav_columns = st.columns(2)

for index, (label, page) in enumerate(navigation):
    with nav_columns[index % 2]:
        st.page_link(
            page,
            label=f"Open {label}",
            icon="↗",
        )


st.divider()

st.caption(
    "Governance: Actual KPI values are sourced from the populated "
    "phase2 and phase3 metric views. Official attendance and attrition "
    "targets are sourced from kpi_targets.csv. Metrics without an "
    "official target are shown as informational. Company-level "
    "aggregation is used; individual employee risk scores are not shown."
)

st.caption(
    "Trend compares the selected month with the immediately preceding "
    "available reporting month. Positive or negative movement is not "
    "automatically interpreted as good or bad."
)
