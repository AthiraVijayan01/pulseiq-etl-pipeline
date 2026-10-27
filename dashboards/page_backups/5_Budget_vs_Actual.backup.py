
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parents[2]
CLEAN_DIR = PROJECT_DIR / "clean"
RAW_DIR = PROJECT_DIR / "raw"
MIN_GROUP_SIZE = 5

st.set_page_config(
    page_title="Budget vs Actual",
    page_icon="💰",
    layout="wide",
)

st.title("Budget vs Actual")
st.caption(
    "Compare payroll costs and workforce KPIs against department targets."
)


@st.cache_data
def load_csv(filename):
    for folder in (CLEAN_DIR, RAW_DIR):
        path = folder / filename
        if path.exists():
            return pd.read_csv(path)
    return pd.DataFrame()


def require_columns(frame, columns, filename):
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        st.error(
            f"{filename} is missing required columns: "
            f"{', '.join(missing)}"
        )
        st.stop()


def month_start(series):
    return (
        pd.to_datetime(series, errors="coerce")
        .dt.to_period("M")
        .dt.to_timestamp()
    )


def show_empty(message):
    st.info(message)
    st.stop()


def sum_min_count(series):
    return series.sum(min_count=1)


# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------

budget = load_csv("budget_payroll_cost.csv")
targets = load_csv("kpi_targets.csv")
payroll = load_csv("fact_payroll.csv")
attendance = load_csv("fact_attendance_monthly.csv")
headcount = load_csv("fact_headcount_monthly.csv")
tasks = load_csv("fact_task.csv")
teams = load_csv("dim_team.csv")
departments = load_csv("dim_department.csv")

if budget.empty:
    show_empty(
        "Could not find budget_payroll_cost.csv in the clean or raw folder."
    )

require_columns(
    budget,
    ["department_id", "month", "budget_payroll_cost"],
    "budget_payroll_cost.csv",
)

budget["month"] = month_start(budget["month"])
budget["budget_payroll_cost"] = pd.to_numeric(
    budget["budget_payroll_cost"], errors="coerce"
)
budget["department_id"] = budget["department_id"].astype("string")
budget = budget.dropna(
    subset=["month", "department_id", "budget_payroll_cost"]
)

if (
    not departments.empty
    and {"department_id", "department_name"}.issubset(departments.columns)
):
    departments = departments[
        ["department_id", "department_name"]
    ].drop_duplicates("department_id")
    departments["department_id"] = departments["department_id"].astype(
        "string"
    )
else:
    departments = pd.DataFrame(
        columns=["department_id", "department_name"]
    )


# ---------------------------------------------------------
# PREPARE PAYROLL AND APPLY MINIMUM GROUP SIZE
# ---------------------------------------------------------

if not payroll.empty:
    require_columns(
        payroll,
        [
            "department_id",
            "period_end_date",
            "employer_cost",
            "employee_id",
        ],
        "fact_payroll.csv",
    )

    payroll["month"] = month_start(payroll["period_end_date"])
    payroll["employer_cost"] = pd.to_numeric(
        payroll["employer_cost"], errors="coerce"
    )
    payroll["department_id"] = payroll["department_id"].astype("string")
    payroll["employee_id"] = payroll["employee_id"].replace(
        r"^\s*$", pd.NA, regex=True
    )

    payroll = payroll.dropna(
        subset=["month", "department_id", "employer_cost"]
    )

    payroll_actual = payroll.groupby(
        ["department_id", "month"],
        as_index=False,
        dropna=False,
    ).agg(
        actual_payroll_cost=("employer_cost", "sum"),
        payroll_employee_count=("employee_id", "nunique"),
    )
else:
    payroll_actual = pd.DataFrame(
        columns=[
            "department_id",
            "month",
            "actual_payroll_cost",
            "payroll_employee_count",
        ]
    )


# ---------------------------------------------------------
# BUDGET VS ACTUAL RECONCILIATION
# ---------------------------------------------------------

budget_actual = budget.groupby(
    ["department_id", "month"],
    as_index=False,
).agg(
    budget_payroll_cost=("budget_payroll_cost", "sum")
)

budget_actual = budget_actual.merge(
    payroll_actual,
    on=["department_id", "month"],
    how="left",
)

budget_actual["privacy_suppressed"] = (
    budget_actual["payroll_employee_count"].notna()
    & (
        budget_actual["payroll_employee_count"]
        < MIN_GROUP_SIZE
    )
)

# Hide budget and actual amounts for small payroll groups.
budget_actual.loc[
    budget_actual["privacy_suppressed"],
    ["budget_payroll_cost", "actual_payroll_cost"],
] = pd.NA

budget_actual["variance"] = (
    budget_actual["actual_payroll_cost"]
    - budget_actual["budget_payroll_cost"]
)

budget_actual["variance_pct"] = (
    budget_actual["variance"]
    / budget_actual["budget_payroll_cost"].where(
        budget_actual["budget_payroll_cost"] != 0
    )
    * 100
)

budget_actual["variance_status"] = "Actual unavailable"

budget_actual.loc[
    budget_actual["privacy_suppressed"],
    "variance_status",
] = "Privacy suppressed"

has_variance = (
    ~budget_actual["privacy_suppressed"]
    & budget_actual["variance"].notna()
)

budget_actual.loc[
    has_variance & (budget_actual["variance"] > 0),
    "variance_status",
] = "Over budget"

budget_actual.loc[
    has_variance & (budget_actual["variance"] < 0),
    "variance_status",
] = "Under budget"

budget_actual.loc[
    has_variance & (budget_actual["variance"] == 0),
    "variance_status",
] = "On budget"

budget_actual = budget_actual.merge(
    departments,
    on="department_id",
    how="left",
)

budget_actual["department_name"] = (
    budget_actual["department_name"]
    .fillna(budget_actual["department_id"])
)

available_months = sorted(
    budget_actual["month"].dropna().unique()
)

if not available_months:
    show_empty("No valid month values were found in the budget data.")

month_labels = {
    pd.Timestamp(month).strftime("%Y-%m"): pd.Timestamp(month)
    for month in available_months
}

month_options = list(month_labels.keys())
default_start = max(0, len(month_options) - min(12, len(month_options)))

# ---------------------------------------------------------
# FILTERS
# ---------------------------------------------------------

with st.sidebar:
    st.header("Filters")

    if len(month_options) > 1:
        selected_period = st.select_slider(
            "Month range",
            options=month_options,
            value=(
                month_options[default_start],
                month_options[-1],
            ),
        )
        start_month = month_labels[selected_period[0]]
        end_month = month_labels[selected_period[1]]
    else:
        selected_period = st.selectbox("Month", month_options)
        start_month = month_labels[selected_period]
        end_month = start_month

    department_options = sorted(
        budget_actual["department_name"].dropna().unique().tolist()
    )

    selected_departments = st.multiselect(
        "Departments",
        options=department_options,
        default=department_options,
    )

filtered = budget_actual[
    budget_actual["month"].between(start_month, end_month)
    & budget_actual["department_name"].isin(selected_departments)
].copy()

if filtered.empty:
    show_empty("No budget records match the selected filters.")

# ---------------------------------------------------------
# SUMMARY CARDS
# Totals include only department-month groups whose actual
# payroll is available and whose employee group meets the
# minimum group size.
# ---------------------------------------------------------

eligible_comparison = filtered[
    ~filtered["privacy_suppressed"]
    & filtered["actual_payroll_cost"].notna()
].copy()

if eligible_comparison.empty:
    st.info(
        "Payroll totals are unavailable for display because no eligible "
        "department-month groups meet the minimum group-size and "
        "data-availability requirements."
    )
else:
    budget_total = eligible_comparison["budget_payroll_cost"].sum(
        min_count=1
    )
    actual_total = eligible_comparison["actual_payroll_cost"].sum(
        min_count=1
    )

    if pd.notna(budget_total) and pd.notna(actual_total):
        variance_total = actual_total - budget_total
        variance_percent = (
            variance_total / budget_total * 100
            if budget_total != 0
            else None
        )
    else:
        variance_total = None
        variance_percent = None

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Budgeted Payroll Cost",
        f"₹{budget_total:,.0f}"
        if pd.notna(budget_total)
        else "Unavailable",
    )

    c2.metric(
        "Actual Employer Cost",
        f"₹{actual_total:,.0f}"
        if pd.notna(actual_total)
        else "Unavailable",
    )

    c3.metric(
        "Variance",
        f"₹{variance_total:,.0f}"
        if variance_total is not None
        else "Unavailable",
        delta=(
            f"{variance_percent:.2f}%"
            if variance_percent is not None
            else None
        ),
        delta_color="inverse",
    )

    c4.metric(
        "Months in Selection",
        eligible_comparison["month"].nunique(),
    )

missing_actual_count = filtered["actual_payroll_cost"].isna().sum()

if missing_actual_count:
    st.warning(
        f"Actual payroll data is unavailable or suppressed for "
        f"{missing_actual_count} department-month row(s). "
        "Missing actuals are not treated as zero."
    )


# ---------------------------------------------------------
# MONTHLY BUDGET VS ACTUAL
# ---------------------------------------------------------

st.subheader("Monthly Budget vs Actual")

monthly = eligible_comparison.groupby(
    "month",
    as_index=False,
).agg(
    budget_payroll_cost=("budget_payroll_cost", sum_min_count),
    actual_payroll_cost=("actual_payroll_cost", sum_min_count),
).sort_values("month")

if monthly.empty:
    st.info(
        "Monthly budget and actual trends are unavailable for the "
        "selected filters because no eligible payroll groups remain."
    )
else:
    monthly_long = monthly.melt(
        id_vars="month",
        value_vars=[
            "budget_payroll_cost",
            "actual_payroll_cost",
        ],
        var_name="cost_type",
        value_name="cost",
    )

    monthly_long["cost_type"] = monthly_long["cost_type"].map({
        "budget_payroll_cost": "Budget",
        "actual_payroll_cost": "Actual employer cost",
    })

    fig = px.line(
        monthly_long,
        x="month",
        y="cost",
        color="cost_type",
        markers=True,
        labels={
            "month": "Month",
            "cost": "Cost (₹)",
            "cost_type": "Series",
        },
    )

    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------
# DEPARTMENT BUDGET VARIANCE
# ---------------------------------------------------------

st.subheader("Department Budget Variance")

dept_variance = eligible_comparison.groupby(
    "department_name",
    as_index=False,
).agg(
    budget_payroll_cost=("budget_payroll_cost", sum_min_count),
    actual_payroll_cost=("actual_payroll_cost", sum_min_count),
)

dept_variance["variance"] = (
    dept_variance["actual_payroll_cost"]
    - dept_variance["budget_payroll_cost"]
)

dept_variance = dept_variance.dropna(
    subset=["actual_payroll_cost", "budget_payroll_cost"]
).sort_values("variance", ascending=False)

if dept_variance.empty:
    st.info(
        "No eligible actual payroll records are available for the "
        "selected period."
    )
else:
    variance_fig = px.bar(
        dept_variance,
        x="department_name",
        y="variance",
        color="variance",
        labels={
            "department_name": "Department",
            "variance": "Actual minus budget (₹)",
        },
    )

    variance_fig.add_hline(y=0, line_dash="dash")
    st.plotly_chart(variance_fig, use_container_width=True)


# ---------------------------------------------------------
# BUDGET RECONCILIATION TABLE
# ---------------------------------------------------------

display_table = filtered[
    [
        "month",
        "department_name",
        "budget_payroll_cost",
        "actual_payroll_cost",
        "variance",
        "variance_pct",
        "variance_status",
        "payroll_employee_count",
    ]
].copy()

# Avoid displaying small-group employee counts.
display_table.loc[
    filtered["privacy_suppressed"].to_numpy(),
    "payroll_employee_count",
] = pd.NA

display_table = display_table.rename(columns={
    "month": "Month",
    "department_name": "Department",
    "budget_payroll_cost": "Budget (₹)",
    "actual_payroll_cost": "Actual Employer Cost (₹)",
    "variance": "Variance (₹)",
    "variance_pct": "Variance (%)",
    "variance_status": "Status",
    "payroll_employee_count": "Payroll Employees",
})

display_table["Month"] = pd.to_datetime(
    display_table["Month"]
).dt.strftime("%Y-%m")

st.subheader("Budget Reconciliation Table")

st.dataframe(
    display_table,
    use_container_width=True,
    hide_index=True,
)

st.download_button(
    "Download budget variance CSV",
    data=display_table.to_csv(index=False).encode("utf-8"),
    file_name="budget_vs_actual_variance.csv",
    mime="text/csv",
)


# ---------------------------------------------------------
# WORKFORCE KPI TARGET TRACKING
# ---------------------------------------------------------

st.divider()
st.header("Workforce KPI Target Tracking")

if targets.empty:
    st.info(
        "kpi_targets.csv is unavailable. Budget analysis is available, "
        "but KPI tracking cannot be shown."
    )
    st.stop()

require_columns(
    targets,
    [
        "month",
        "department_id",
        "attendance_rate_target",
        "overtime_share_target_pct",
        "attrition_monthly_target_pct",
        "task_completion_target_pct",
    ],
    "kpi_targets.csv",
)

targets["month"] = month_start(targets["month"])
targets["department_id"] = targets["department_id"].astype("string")
targets = targets.dropna(subset=["month", "department_id"])

selected_department_ids = filtered["department_id"].unique()

targets = targets[
    targets["month"].between(start_month, end_month)
    & targets["department_id"].isin(selected_department_ids)
].copy()

kpi_rows = []


# ---------------------------------------------------------
# ATTENDANCE RATE AND OVERTIME SHARE
# ---------------------------------------------------------

if not attendance.empty:
    require_columns(
        attendance,
        [
            "department_id",
            "period_end_date",
            "scheduled_days",
            "present_days",
            "employee_id",
        ],
        "fact_attendance_monthly.csv",
    )

    attendance["month"] = month_start(
        attendance["period_end_date"]
    )
    attendance["department_id"] = attendance[
        "department_id"
    ].astype("string")

    attendance["employee_id"] = attendance["employee_id"].replace(
        r"^\s*$", pd.NA, regex=True
    )

    attendance["scheduled_days"] = pd.to_numeric(
        attendance["scheduled_days"], errors="coerce"
    )
    attendance["present_days"] = pd.to_numeric(
        attendance["present_days"], errors="coerce"
    )

    if "overtime_hours" in attendance.columns:
        attendance["overtime_hours"] = pd.to_numeric(
            attendance["overtime_hours"], errors="coerce"
        )
    else:
        attendance["overtime_hours"] = pd.NA

    attendance = attendance[
        attendance["month"].between(start_month, end_month)
        & attendance["department_id"].isin(selected_department_ids)
    ].copy()

    attendance_monthly = attendance.groupby(
        ["department_id", "month"],
        as_index=False,
    ).agg(
        scheduled_days=("scheduled_days", "sum"),
        present_days=("present_days", "sum"),
        employee_count=("employee_id", "nunique"),
    )

    attendance_monthly["actual"] = (
        attendance_monthly["present_days"]
        / attendance_monthly["scheduled_days"].where(
            attendance_monthly["scheduled_days"] > 0
        )
        * 100
    )

    attendance_monthly["kpi"] = "Attendance rate"
    attendance_monthly["target_column"] = "attendance_rate_target"

    kpi_rows.append(
        attendance_monthly[
            [
                "department_id",
                "month",
                "employee_count",
                "actual",
                "kpi",
                "target_column",
            ]
        ]
    )

    overtime_monthly = attendance.groupby(
        ["department_id", "month"],
        as_index=False,
    ).agg(
        overtime_hours=("overtime_hours", "sum"),
        scheduled_days=("scheduled_days", "sum"),
        employee_count=("employee_id", "nunique"),
    )

    overtime_monthly["actual"] = (
        overtime_monthly["overtime_hours"]
        / (
            overtime_monthly["scheduled_days"] * 8
        ).where(overtime_monthly["scheduled_days"] > 0)
        * 100
    )

    overtime_monthly["kpi"] = "Overtime share"
    overtime_monthly["target_column"] = "overtime_share_target_pct"

    kpi_rows.append(
        overtime_monthly[
            [
                "department_id",
                "month",
                "employee_count",
                "actual",
                "kpi",
                "target_column",
            ]
        ]
    )


# ---------------------------------------------------------
# MONTHLY ATTRITION
# ---------------------------------------------------------

if not headcount.empty:
    require_columns(
        headcount,
        [
            "department_id",
            "month_start_date",
            "attrition_rate_monthly_pct",
            "headcount_end",
        ],
        "fact_headcount_monthly.csv",
    )

    headcount["month"] = month_start(
        headcount["month_start_date"]
    )
    headcount["department_id"] = headcount[
        "department_id"
    ].astype("string")

    headcount["attrition_rate_monthly_pct"] = pd.to_numeric(
        headcount["attrition_rate_monthly_pct"],
        errors="coerce",
    )
    headcount["headcount_end"] = pd.to_numeric(
        headcount["headcount_end"],
        errors="coerce",
    )

    headcount = headcount[
        headcount["month"].between(start_month, end_month)
        & headcount["department_id"].isin(selected_department_ids)
    ].copy()

    attrition = headcount.groupby(
        ["department_id", "month"],
        as_index=False,
    ).agg(
        actual=("attrition_rate_monthly_pct", "mean"),
        employee_count=("headcount_end", "max"),
    )

    attrition["kpi"] = "Monthly attrition"
    attrition["target_column"] = "attrition_monthly_target_pct"

    kpi_rows.append(
        attrition[
            [
                "department_id",
                "month",
                "employee_count",
                "actual",
                "kpi",
                "target_column",
            ]
        ]
    )


# ---------------------------------------------------------
# TASK COMPLETION
# ---------------------------------------------------------

if not tasks.empty and not teams.empty:
    require_columns(
        tasks,
        [
            "team_id",
            "created_date",
            "status",
            "assignee_employee_id",
        ],
        "fact_task.csv",
    )
    require_columns(
        teams,
        ["team_id", "department_id"],
        "dim_team.csv",
    )

    tasks["month"] = month_start(tasks["created_date"])
    tasks["status"] = (
        tasks["status"].astype("string").str.strip().str.lower()
    )
    tasks["assignee_employee_id"] = tasks[
        "assignee_employee_id"
    ].replace(r"^\s*$", pd.NA, regex=True)

    tasks = tasks[
        tasks["month"].between(start_month, end_month)
        & (tasks["status"] != "cancelled")
    ].copy()

    tasks = tasks.merge(
        teams[["team_id", "department_id"]].drop_duplicates(
            "team_id"
        ),
        on="team_id",
        how="left",
    )

    tasks["department_id"] = tasks["department_id"].astype("string")

    tasks = tasks[
        tasks["department_id"].isin(selected_department_ids)
    ].copy()

    task_monthly = tasks.groupby(
        ["department_id", "month"],
        as_index=False,
    ).agg(
        task_count=("status", "size"),
        completed_count=(
            "status",
            lambda values: (values == "done").sum(),
        ),
        employee_count=("assignee_employee_id", "nunique"),
    )

    task_monthly["actual"] = (
        task_monthly["completed_count"]
        / task_monthly["task_count"].where(
            task_monthly["task_count"] > 0
        )
        * 100
    )

    task_monthly["kpi"] = "Task completion"
    task_monthly["target_column"] = "task_completion_target_pct"

    kpi_rows.append(
        task_monthly[
            [
                "department_id",
                "month",
                "employee_count",
                "actual",
                "kpi",
                "target_column",
            ]
        ]
    )


# ---------------------------------------------------------
# COMBINE ACTUALS WITH TARGETS
# ---------------------------------------------------------

if not kpi_rows:
    st.info(
        "No attendance, headcount, or task data is available "
        "to calculate KPIs."
    )
    st.stop()

kpis = pd.concat(kpi_rows, ignore_index=True)

target_long = targets.melt(
    id_vars=["department_id", "month"],
    value_vars=[
        "attendance_rate_target",
        "overtime_share_target_pct",
        "attrition_monthly_target_pct",
        "task_completion_target_pct",
    ],
    var_name="target_column",
    value_name="target",
)

target_long["target"] = pd.to_numeric(
    target_long["target"], errors="coerce"
)

target_long.loc[
    target_long["target_column"] == "attendance_rate_target",
    "target",
] *= 100

kpis = kpis.merge(
    target_long,
    on=["department_id", "month", "target_column"],
    how="left",
)

kpis["actual"] = pd.to_numeric(
    kpis["actual"], errors="coerce"
)
kpis["target"] = pd.to_numeric(
    kpis["target"], errors="coerce"
)
kpis["employee_count"] = pd.to_numeric(
    kpis["employee_count"], errors="coerce"
)

kpis = kpis.merge(
    departments,
    on="department_id",
    how="left",
)

kpis["department_name"] = kpis["department_name"].fillna(
    kpis["department_id"]
)

kpis = kpis[
    kpis["department_name"].isin(selected_departments)
].copy()

st.caption(
    "Department-level KPI values are suppressed when fewer than "
    f"{MIN_GROUP_SIZE} employees are represented. Missing employee "
    "counts are treated as unavailable and are not considered safe."
)

kpis["privacy_suppressed"] = (
    kpis["employee_count"].isna()
    | (kpis["employee_count"] < MIN_GROUP_SIZE)
)

kpis.loc[
    kpis["privacy_suppressed"],
    ["actual", "target"],
] = pd.NA

kpis["performance"] = "Unavailable"

kpis.loc[
    kpis["privacy_suppressed"],
    "performance",
] = "Privacy suppressed"

kpis.loc[
    ~kpis["privacy_suppressed"]
    & kpis["target"].isna(),
    "performance",
] = "Target not configured"

has_values = (
    kpis["actual"].notna()
    & kpis["target"].notna()
)

higher_is_better = kpis["kpi"].isin(
    ["Attendance rate", "Task completion"]
)
lower_is_better = kpis["kpi"].isin(
    ["Overtime share", "Monthly attrition"]
)

kpis.loc[
    has_values
    & higher_is_better
    & (kpis["actual"] >= kpis["target"]),
    "performance",
] = "Met target"

kpis.loc[
    has_values
    & higher_is_better
    & (kpis["actual"] < kpis["target"]),
    "performance",
] = "Below target"

kpis.loc[
    has_values
    & lower_is_better
    & (kpis["actual"] <= kpis["target"]),
    "performance",
] = "Met target"

kpis.loc[
    has_values
    & lower_is_better
    & (kpis["actual"] > kpis["target"]),
    "performance",
] = "Above target"


# ---------------------------------------------------------
# KPI VISUALIZATION AND TABLE
# ---------------------------------------------------------

selected_kpi = st.selectbox(
    "Choose KPI",
    sorted(kpis["kpi"].unique().tolist()),
)

kpi_view = kpis[kpis["kpi"] == selected_kpi].copy()

if kpi_view.empty:
    st.info("No results for this KPI in the selected period.")
else:
    chart_data = kpi_view.dropna(subset=["actual"])

    if not chart_data.empty:
        chart = px.line(
            chart_data.sort_values("month"),
            x="month",
            y="actual",
            color="department_name",
            markers=True,
            labels={
                "month": "Month",
                "actual": f"{selected_kpi} (%)",
                "department_name": "Department",
            },
        )

        target_data = chart_data.dropna(subset=["target"])

        if not target_data.empty:
            average_target = target_data.groupby(
                "month",
                as_index=False,
            )["target"].mean()

            chart.add_scatter(
                x=average_target["month"],
                y=average_target["target"],
                mode="lines",
                name="Average target",
                line={"dash": "dash"},
            )

        st.plotly_chart(
            chart,
            use_container_width=True,
        )
    else:
        st.info(
            "KPI values are unavailable or suppressed by the "
            "minimum group-size rule."
        )

    kpi_table = kpi_view[
        [
            "month",
            "department_name",
            "kpi",
            "actual",
            "target",
            "employee_count",
            "performance",
            "privacy_suppressed",
        ]
    ].copy()

    kpi_table = kpi_table.rename(columns={
        "month": "Month",
        "department_name": "Department",
        "kpi": "KPI",
        "actual": "Actual (%)",
        "target": "Target (%)",
        "employee_count": "Employees",
        "performance": "Target status",
        "privacy_suppressed": "Privacy suppressed",
    })

    kpi_table["Month"] = pd.to_datetime(
        kpi_table["Month"]
    ).dt.strftime("%Y-%m")

    # Do not expose exact counts for groups below the threshold.
    kpi_table.loc[
        kpi_table["Privacy suppressed"],
        "Employees",
    ] = pd.NA

    st.dataframe(
        kpi_table,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download KPI tracking CSV",
        data=kpi_table.to_csv(index=False).encode("utf-8"),
        file_name="workforce_kpi_tracking.csv",
        mime="text/csv",
    )

st.caption(
    "Positive payroll variance means actual employer cost exceeded "
    "budget. Confirm KPI formulas against the official metric "
    "dictionary before submission."
)
