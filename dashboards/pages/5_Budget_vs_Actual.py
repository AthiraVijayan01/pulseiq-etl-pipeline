
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parents[2]
CLEAN_DIR = PROJECT_DIR / "clean"
RAW_DIR = PROJECT_DIR / "raw"

MIN_GROUP_SIZE = 5


st.set_page_config(
    page_title="Budget vs Actual | PulseIQ",
    page_icon="💰",
    layout="wide",
)


def load_csv(filename):
    clean_path = CLEAN_DIR / filename
    raw_path = RAW_DIR / filename

    if clean_path.exists():
        path = clean_path
    elif raw_path.exists():
        path = raw_path
    else:
        return pd.DataFrame()

    try:
        return pd.read_csv(path, low_memory=False)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        st.warning(f"Could not read {filename}: {exc}")
        return pd.DataFrame()


def require_columns(df, columns, filename):
    missing = [column for column in columns if column not in df.columns]

    if missing:
        st.error(
            f"{filename} is missing required columns: "
            + ", ".join(missing)
        )
        st.stop()


def month_start(series):
    dates = pd.to_datetime(series, errors="coerce")
    return dates.dt.to_period("M").dt.to_timestamp()


def sum_min_count(series):
    return series.sum(min_count=1)


def numeric_column(df, column):
    if column not in df.columns:
        return pd.Series(float("nan"), index=df.index)

    return pd.to_numeric(df[column], errors="coerce")


def show_empty(message):
    st.info(message)


def format_currency(value):
    if pd.isna(value):
        return "N/A"

    return f"₹{value:,.2f}"


def format_number(value, decimals=2):
    if pd.isna(value):
        return "N/A"

    return f"{value:,.{decimals}f}"


def normalize_department_id(df):
    if "department_id" in df.columns:
        df["department_id"] = (
            df["department_id"]
            .astype("string")
            .str.strip()
        )

    return df


def get_department_names():
    departments = load_csv("dim_department.csv")

    if (
        not departments.empty
        and {"department_id", "department_name"}.issubset(
            departments.columns
        )
    ):
        departments = departments[
            ["department_id", "department_name"]
        ].drop_duplicates("department_id")

        return departments

    return pd.DataFrame(
        columns=["department_id", "department_name"]
    )


def get_month_column(df):
    for column in [
        "month",
        "month_start_date",
        "period_end_date",
        "date",
    ]:
        if column in df.columns:
            return column

    return None


def prepare_monthly_data(df, filename):
    if df.empty:
        return df

    month_column = get_month_column(df)

    if month_column is None:
        st.warning(
            f"{filename} does not contain a recognized month/date column."
        )
        return pd.DataFrame()

    df = df.copy()
    df["month"] = month_start(df[month_column])
    df = df.dropna(subset=["month"])

    return df


def prepare_budget_data():
    budget = load_csv("budget_payroll_cost.csv")

    if budget.empty:
        return pd.DataFrame()

    require_columns(
        budget,
        ["department_id", "month", "budget_payroll_cost"],
        "budget_payroll_cost.csv",
    )

    budget = budget.copy()
    budget = normalize_department_id(budget)
    budget["month"] = month_start(budget["month"])
    budget["budget_payroll_cost"] = numeric_column(
        budget, "budget_payroll_cost"
    )

    budget = budget.dropna(
        subset=["department_id", "month"]
    )

    budget = (
        budget.groupby(
            ["department_id", "month"],
            as_index=False,
        )
        .agg(
            budget_amount=(
                "budget_payroll_cost",
                sum_min_count,
            )
        )
    )

    return budget


def prepare_payroll_data():
    payroll = load_csv("fact_payroll.csv")

    if payroll.empty:
        return pd.DataFrame()

    require_columns(
        payroll,
        ["department_id", "period_end_date", "employee_id"],
        "fact_payroll.csv",
    )

    payroll = payroll.copy()
    payroll = normalize_department_id(payroll)
    payroll["month"] = month_start(payroll["period_end_date"])

    if "employer_cost" in payroll.columns:
        payroll["employer_cost"] = numeric_column(
            payroll, "employer_cost"
        )
    else:
        payroll["employer_cost"] = float("nan")

    payroll = payroll.dropna(
        subset=["department_id", "month"]
    )

    payroll["employee_id"] = (
        payroll["employee_id"].astype("string").str.strip()
    )

    payroll = (
        payroll.groupby(
            ["department_id", "month"],
            as_index=False,
        )
        .agg(
            actual_amount=("employer_cost", sum_min_count),
            employee_count=("employee_id", "nunique"),
        )
    )

    return payroll


def build_budget_reconciliation():
    budget = prepare_budget_data()
    payroll = prepare_payroll_data()

    if budget.empty and payroll.empty:
        return pd.DataFrame()

    reconciliation = pd.merge(
        budget,
        payroll,
        on=["department_id", "month"],
        how="outer",
        validate="one_to_one",
    )

    reconciliation["employee_count"] = (
        reconciliation["employee_count"].fillna(0).astype(int)
    )

    reconciliation["privacy_suppressed"] = (
        reconciliation["employee_count"] > 0
    ) & (
        reconciliation["employee_count"] < MIN_GROUP_SIZE
    )

    reconciliation["budget_amount"] = reconciliation[
        "budget_amount"
    ].mask(reconciliation["privacy_suppressed"])

    reconciliation["actual_amount"] = reconciliation[
        "actual_amount"
    ].mask(reconciliation["privacy_suppressed"])

    reconciliation["variance"] = (
        reconciliation["actual_amount"]
        - reconciliation["budget_amount"]
    )

    reconciliation["variance_pct"] = (
        reconciliation["variance"]
        .div(reconciliation["budget_amount"].where(
            reconciliation["budget_amount"] != 0
        ))
        * 100
    )

    reconciliation["variance_status"] = "Unavailable"

    valid = (
        reconciliation["budget_amount"].notna()
        & reconciliation["actual_amount"].notna()
        & ~reconciliation["privacy_suppressed"]
    )

    reconciliation.loc[valid, "variance_status"] = (
        "Within budget"
    )

    reconciliation.loc[
        valid & (reconciliation["variance"] > 0),
        "variance_status",
    ] = "Over budget"

    reconciliation.loc[
        valid & (reconciliation["variance"] < 0),
        "variance_status",
    ] = "Under budget"

    reconciliation.loc[
        reconciliation["privacy_suppressed"],
        "variance_status",
    ] = "Suppressed"

    department_names = get_department_names()

    if not department_names.empty:
        reconciliation = reconciliation.merge(
            department_names,
            on="department_id",
            how="left",
            validate="many_to_one",
        )
    else:
        reconciliation["department_name"] = pd.NA

    reconciliation["department_name"] = (
        reconciliation["department_name"]
        .fillna(reconciliation["department_id"])
    )

    return reconciliation.sort_values(
        ["month", "department_name"]
    )


def build_attendance_actuals():
    attendance = load_csv("fact_attendance_monthly.csv")

    if attendance.empty:
        return pd.DataFrame()

    required = [
        "department_id",
        "employee_id",
        "scheduled_days",
        "present_days",
    ]

    require_columns(
        attendance,
        required,
        "fact_attendance_monthly.csv",
    )

    attendance = normalize_department_id(attendance)
    attendance = prepare_monthly_data(
        attendance,
        "fact_attendance_monthly.csv",
    )

    if attendance.empty:
        return pd.DataFrame()

    attendance["scheduled_days"] = numeric_column(
        attendance, "scheduled_days"
    )
    attendance["present_days"] = numeric_column(
        attendance, "present_days"
    )

    if "overtime_hours" in attendance.columns:
        attendance["overtime_hours"] = numeric_column(
            attendance, "overtime_hours"
        )
    else:
        attendance["overtime_hours"] = float("nan")

    attendance["employee_id"] = (
        attendance["employee_id"].astype("string").str.strip()
    )

    grouped = (
        attendance.groupby(
            ["department_id", "month"],
            as_index=False,
        )
        .agg(
            scheduled_days=("scheduled_days", sum_min_count),
            present_days=("present_days", sum_min_count),
            overtime_hours=("overtime_hours", sum_min_count),
            employee_count=("employee_id", "nunique"),
        )
    )

    grouped["attendance_rate"] = (
        grouped["present_days"]
        .div(grouped["scheduled_days"].where(
            grouped["scheduled_days"] > 0
        ))
        * 100
    )

    grouped["overtime_hours_actual"] = grouped[
        "overtime_hours"
    ]

    return grouped


def build_attrition_actuals():
    headcount = load_csv("fact_headcount_monthly.csv")

    if headcount.empty:
        return pd.DataFrame()

    require_columns(
        headcount,
        ["department_id", "headcount_end"],
        "fact_headcount_monthly.csv",
    )

    headcount = normalize_department_id(headcount)
    headcount = prepare_monthly_data(
        headcount,
        "fact_headcount_monthly.csv",
    )

    if headcount.empty:
        return pd.DataFrame()

    headcount["headcount_end"] = numeric_column(
        headcount, "headcount_end"
    )

    if "attrition_rate_monthly_pct" in headcount.columns:
        headcount["attrition_actual"] = numeric_column(
            headcount, "attrition_rate_monthly_pct"
        )
    else:
        headcount["attrition_actual"] = float("nan")

    grouped = (
        headcount.groupby(
            ["department_id", "month"],
            as_index=False,
        )
        .agg(
            employee_count=("headcount_end", "max"),
            attrition_actual=("attrition_actual", "mean"),
        )
    )

    return grouped


def build_task_actuals():
    tasks = load_csv("fact_task.csv")
    teams = load_csv("dim_team.csv")

    if tasks.empty or teams.empty:
        return pd.DataFrame()

    require_columns(
        tasks,
        ["team_id", "task_id"],
        "fact_task.csv",
    )

    require_columns(
        teams,
        ["team_id", "department_id"],
        "dim_team.csv",
    )

    teams = teams[["team_id", "department_id"]].drop_duplicates(
        "team_id"
    )

    tasks = tasks.copy()

    tasks = tasks.merge(
        teams,
        on="team_id",
        how="left",
        validate="many_to_one",
    )

    if "completed_date" in tasks.columns:
        tasks["month"] = month_start(tasks["completed_date"])
    elif "created_date" in tasks.columns:
        tasks["month"] = month_start(tasks["created_date"])
    else:
        st.warning(
            "fact_task.csv has no completed_date or created_date column."
        )
        return pd.DataFrame()

    tasks["status_normalized"] = (
        tasks["status"].astype("string").str.strip().str.lower()
        if "status" in tasks.columns
        else pd.Series("", index=tasks.index)
    )

    if "completed_date" in tasks.columns:
        has_completed_date = pd.to_datetime(
            tasks["completed_date"], errors="coerce"
        ).notna()
    else:
        has_completed_date = pd.Series(
            False, index=tasks.index
        )

    completed_statuses = {
        "completed",
        "complete",
        "done",
        "closed",
        "resolved",
    }

    tasks["is_completed"] = (
        has_completed_date
        | tasks["status_normalized"].isin(completed_statuses)
    )

    tasks["assignee_employee_id"] = (
        tasks["assignee_employee_id"].astype("string").str.strip()
        if "assignee_employee_id" in tasks.columns
        else pd.Series(pd.NA, index=tasks.index, dtype="string")
    )

    tasks = tasks.dropna(
        subset=["department_id", "month"]
    )

    grouped = (
        tasks.groupby(
            ["department_id", "month"],
            as_index=False,
        )
        .agg(
            task_count=("task_id", "nunique"),
            completed_tasks=("is_completed", "sum"),
            employee_count=("assignee_employee_id", "nunique"),
        )
    )

    grouped["task_completion_actual"] = (
        grouped["completed_tasks"]
        .div(grouped["task_count"].where(
            grouped["task_count"] > 0
        ))
        * 100
    )

    return grouped


def build_kpi_actuals():
    attendance = build_attendance_actuals()
    attrition = build_attrition_actuals()
    tasks = build_task_actuals()

    pieces = []

    if not attendance.empty:
        pieces.append(
            attendance[
                [
                    "department_id",
                    "month",
                    "attendance_rate",
                    "overtime_hours_actual",
                    "employee_count",
                ]
            ].rename(
                columns={
                    "attendance_rate": "attendance_actual",
                }
            )
        )

    if not attrition.empty:
        attrition_part = attrition[
            [
                "department_id",
                "month",
                "attrition_actual",
                "employee_count",
            ]
        ].copy()

        if not attendance.empty:
            attrition_part = attrition_part.rename(
                columns={
                    "employee_count": "attrition_employee_count"
                }
            )

        pieces.append(attrition_part)

    if not tasks.empty:
        task_part = tasks[
            [
                "department_id",
                "month",
                "task_completion_actual",
                "employee_count",
            ]
        ].copy()

        if not attendance.empty or not attrition.empty:
            task_part = task_part.rename(
                columns={
                    "employee_count": "task_employee_count"
                }
            )

        pieces.append(task_part)

    if not pieces:
        return pd.DataFrame()

    actuals = pieces[0]

    for part in pieces[1:]:
        actuals = actuals.merge(
            part,
            on=["department_id", "month"],
            how="outer",
            validate="one_to_one",
        )

    count_columns = [
        column
        for column in actuals.columns
        if column.endswith("employee_count")
    ]

    if count_columns:
        actuals["employee_count"] = actuals[
            count_columns
        ].max(axis=1, skipna=True)
    else:
        actuals["employee_count"] = float("nan")

    return actuals


def build_kpi_targets():
    targets = load_csv("kpi_targets.csv")

    if targets.empty:
        return pd.DataFrame()

    require_columns(
        targets,
        ["department_id"],
        "kpi_targets.csv",
    )

    targets = normalize_department_id(targets)
    targets = prepare_monthly_data(
        targets,
        "kpi_targets.csv",
    )

    if targets.empty:
        return pd.DataFrame()

    target_columns = [
        column
        for column in targets.columns
        if column.endswith("_target")
    ]

    if not target_columns:
        st.warning(
            "kpi_targets.csv contains no columns ending in '_target'."
        )
        return pd.DataFrame()

    targets = targets[
        ["department_id", "month"] + target_columns
    ].copy()

    for column in target_columns:
        targets[column] = numeric_column(targets, column)

    targets = targets.drop_duplicates(
        ["department_id", "month"],
        keep="last",
    )

    long_targets = targets.melt(
        id_vars=["department_id", "month"],
        value_vars=target_columns,
        var_name="target_column",
        value_name="target",
    )

    target_mapping = {
        "attendance_rate_target": (
            "Attendance rate",
            "attendance_actual",
            "Higher is better",
        ),
        "overtime_hours_target": (
            "Overtime hours",
            "overtime_hours_actual",
            "Lower is better",
        ),
        "attrition_rate_target": (
            "Attrition rate",
            "attrition_actual",
            "Lower is better",
        ),
        "attrition_target": (
            "Attrition rate",
            "attrition_actual",
            "Lower is better",
        ),
        "task_completion_rate_target": (
            "Task completion rate",
            "task_completion_actual",
            "Higher is better",
        ),
        "task_completion_target": (
            "Task completion rate",
            "task_completion_actual",
            "Higher is better",
        ),
    }

    long_targets["mapping"] = long_targets[
        "target_column"
    ].map(target_mapping)

    long_targets = long_targets.dropna(subset=["mapping"])

    if long_targets.empty:
        st.warning(
            "The KPI target columns could not be mapped to supported metrics."
        )
        return pd.DataFrame()

    long_targets[
        ["metric", "actual_column", "direction"]
    ] = pd.DataFrame(
        long_targets["mapping"].tolist(),
        index=long_targets.index,
    )

    long_targets = long_targets.drop(columns=["mapping"])

    attendance_mask = (
        long_targets["target_column"] == "attendance_rate_target"
    )

    attendance_targets = long_targets.loc[
        attendance_mask, "target"
    ]

    if (
        not attendance_targets.dropna().empty
        and attendance_targets.dropna().between(0, 1).all()
    ):
        long_targets.loc[attendance_mask, "target"] = (
            long_targets.loc[attendance_mask, "target"] * 100
        )

    percent_target_metrics = {
        "attrition_rate_target",
        "attrition_target",
        "task_completion_rate_target",
        "task_completion_target",
    }

    for target_column in percent_target_metrics:
        mask = long_targets["target_column"] == target_column
        values = long_targets.loc[mask, "target"]

        if (
            not values.dropna().empty
            and values.dropna().between(0, 1).all()
        ):
            long_targets.loc[mask, "target"] = values * 100

    return long_targets


def build_kpi_report():
    actuals = build_kpi_actuals()
    targets = build_kpi_targets()

    if actuals.empty or targets.empty:
        return pd.DataFrame()

    actual_long = actuals.melt(
        id_vars=[
            "department_id",
            "month",
            "employee_count",
        ],
        value_vars=[
            column
            for column in [
                "attendance_actual",
                "overtime_hours_actual",
                "attrition_actual",
                "task_completion_actual",
            ]
            if column in actuals.columns
        ],
        var_name="actual_column",
        value_name="actual",
    )

    actual_mapping = {
        "attendance_actual": "Attendance rate",
        "overtime_hours_actual": "Overtime hours",
        "attrition_actual": "Attrition rate",
        "task_completion_actual": "Task completion rate",
    }

    actual_long["metric"] = actual_long[
        "actual_column"
    ].map(actual_mapping)

    report = targets.merge(
        actual_long[
            [
                "department_id",
                "month",
                "metric",
                "actual",
                "employee_count",
            ]
        ],
        on=["department_id", "month", "metric"],
        how="left",
        validate="one_to_one",
    )

    report["employee_count"] = pd.to_numeric(
        report["employee_count"], errors="coerce"
    )

    report["privacy_suppressed"] = (
        report["employee_count"].notna()
        & (report["employee_count"] > 0)
        & (report["employee_count"] < MIN_GROUP_SIZE)
    )

    report.loc[
        report["privacy_suppressed"], "actual"
    ] = float("nan")

    report["performance"] = "Actual unavailable"

    target_missing = report["target"].isna()

    report.loc[
        target_missing, "performance"
    ] = "Target not configured"

    comparable = (
        report["actual"].notna()
        & report["target"].notna()
        & ~report["privacy_suppressed"]
    )

    higher_is_better = (
        report["direction"] == "Higher is better"
    )

    report.loc[
        comparable & higher_is_better
        & (report["actual"] >= report["target"]),
        "performance",
    ] = "Target met"

    report.loc[
        comparable & higher_is_better
        & (report["actual"] < report["target"]),
        "performance",
    ] = "Below target"

    report.loc[
        comparable & ~higher_is_better
        & (report["actual"] <= report["target"]),
        "performance",
    ] = "Target met"

    report.loc[
        comparable & ~higher_is_better
        & (report["actual"] > report["target"]),
        "performance",
    ] = "Above target"

    report.loc[
        report["privacy_suppressed"], "performance"
    ] = "Suppressed"

    departments = get_department_names()

    if not departments.empty:
        report = report.merge(
            departments,
            on="department_id",
            how="left",
            validate="many_to_one",
        )
    else:
        report["department_name"] = pd.NA

    report["department_name"] = (
        report["department_name"]
        .fillna(report["department_id"])
    )

    return report.sort_values(
        ["month", "department_name", "metric"]
    )


st.title("Budget vs Actual")
st.caption(
    "Department-level payroll reporting, budget reconciliation, "
    "workforce KPI targets, and small-group privacy controls."
)

st.info(
    f"Privacy rule: groups with fewer than {MIN_GROUP_SIZE} "
    "employees have actual values suppressed."
)

reconciliation = build_budget_reconciliation()

if reconciliation.empty:
    show_empty(
        "No budget or payroll data is available. "
        "Check budget_payroll_cost.csv and fact_payroll.csv."
    )
else:
    available_months = sorted(
        reconciliation["month"].dropna().unique()
    )

    if not available_months:
        show_empty("No valid months were found in the budget data.")
    else:
        st.subheader("Filters")

        filter_col1, filter_col2 = st.columns(2)

        with filter_col1:
            selected_months = st.select_slider(
                "Month range",
                options=available_months,
                value=(
                    available_months[0],
                    available_months[-1],
                ),
                format_func=lambda value: pd.Timestamp(
                    value
                ).strftime("%b %Y"),
            )

        with filter_col2:
            department_options = sorted(
                reconciliation["department_name"]
                .dropna()
                .unique()
                .tolist()
            )

            selected_departments = st.multiselect(
                "Departments",
                options=department_options,
                default=department_options,
            )

        start_month, end_month = selected_months

        filtered = reconciliation[
            reconciliation["month"].between(
                start_month, end_month
            )
            & reconciliation["department_name"].isin(
                selected_departments
            )
        ].copy()

        visible = filtered[
            ~filtered["privacy_suppressed"]
        ].copy()

        total_budget = visible["budget_amount"].sum(
            min_count=1
        )
        total_actual = visible["actual_amount"].sum(
            min_count=1
        )

        variance_total = (
            total_actual - total_budget
            if pd.notna(total_actual) and pd.notna(total_budget)
            else float("nan")
        )

        suppressed_groups = int(
            filtered["privacy_suppressed"].sum()
        )

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)

        kpi1.metric(
            "Budget",
            format_currency(total_budget),
        )

        kpi2.metric(
            "Actual employer cost",
            format_currency(total_actual),
        )

        kpi3.metric(
            "Variance",
            format_currency(variance_total),
        )

        kpi4.metric(
            "Suppressed groups",
            f"{suppressed_groups:,}",
        )

        st.divider()

        st.subheader("Monthly Budget vs Actual")

        monthly = (
            visible.groupby("month", as_index=False)
            .agg(
                budget=("budget_amount", sum_min_count),
                actual=("actual_amount", sum_min_count),
            )
            .sort_values("month")
        )

        chart_data = monthly.melt(
            id_vars="month",
            value_vars=["budget", "actual"],
            var_name="category",
            value_name="amount",
        )

        chart_data["category"] = chart_data[
            "category"
        ].map(
            {
                "budget": "Budget",
                "actual": "Actual",
            }
        )

        if chart_data["amount"].notna().any():
            fig = px.line(
                chart_data,
                x="month",
                y="amount",
                color="category",
                markers=True,
                title="Monthly payroll budget and actual cost",
                labels={
                    "month": "Month",
                    "amount": "Amount (₹)",
                    "category": "Category",
                },
            )

            fig.update_layout(
                hovermode="x unified",
                legend_title_text="",
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )
        else:
            show_empty(
                "There are no visible budget and actual values "
                "for the selected filters."
            )

        st.subheader("Department Variance")

        department_variance = (
            visible.groupby(
                "department_name",
                as_index=False,
            )
            .agg(
                budget=("budget_amount", sum_min_count),
                actual=("actual_amount", sum_min_count),
            )
        )

        department_variance["variance"] = (
            department_variance["actual"]
            - department_variance["budget"]
        )

        department_variance = department_variance.dropna(
            subset=["variance"]
        )

        if not department_variance.empty:
            variance_fig = px.bar(
                department_variance.sort_values("variance"),
                x="variance",
                y="department_name",
                orientation="h",
                title="Actual cost minus budget by department",
                labels={
                    "variance": "Variance (₹)",
                    "department_name": "Department",
                },
            )

            st.plotly_chart(
                variance_fig,
                use_container_width=True,
            )
        else:
            show_empty(
                "Department variance is unavailable for these filters."
            )

        st.subheader("Payroll Reconciliation Details")

        display_columns = [
            "month",
            "department_name",
            "employee_count",
            "budget_amount",
            "actual_amount",
            "variance",
            "variance_pct",
            "variance_status",
        ]

        table = filtered[display_columns].copy()
        table.insert(
            0,
            "S.No",
            range(1, len(table) + 1),
        )

        table["month"] = pd.to_datetime(
            table["month"]
        ).dt.strftime("%Y-%m")

        table = table.rename(
            columns={
                "month": "Month",
                "department_name": "Department",
                "employee_count": "Employee Count",
                "budget_amount": "Budget (₹)",
                "actual_amount": "Actual (₹)",
                "variance": "Variance (₹)",
                "variance_pct": "Variance (%)",
                "variance_status": "Status",
            }
        )

        st.dataframe(
            table,
            hide_index=True,
            use_container_width=True,
        )

        csv_data = table.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download Payroll Reconciliation CSV",
            data=csv_data,
            file_name="pulseiq_budget_vs_actual.csv",
            mime="text/csv",
        )


st.divider()

st.title("Workforce KPI Target Tracking")
st.caption(
    "Compare attendance, overtime, attrition, and task completion "
    "against the targets configured in kpi_targets.csv."
)

kpi_report = build_kpi_report()

if kpi_report.empty:
    show_empty(
        "KPI tracking could not be built. Check kpi_targets.csv, "
        "fact_attendance_monthly.csv, fact_headcount_monthly.csv, "
        "fact_task.csv, and dim_team.csv."
    )
else:
    kpi_months = sorted(
        kpi_report["month"].dropna().unique()
    )

    kpi_filter1, kpi_filter2, kpi_filter3 = st.columns(3)

    with kpi_filter1:
        selected_metrics = st.multiselect(
            "KPI metrics",
            options=sorted(kpi_report["metric"].dropna().unique()),
            default=sorted(kpi_report["metric"].dropna().unique()),
        )

    with kpi_filter2:
        kpi_departments = sorted(
            kpi_report["department_name"].dropna().unique().tolist()
        )

        selected_kpi_departments = st.multiselect(
            "KPI departments",
            options=kpi_departments,
            default=kpi_departments,
        )

    with kpi_filter3:
        if kpi_months:
            selected_kpi_months = st.select_slider(
                "KPI month range",
                options=kpi_months,
                value=(kpi_months[0], kpi_months[-1]),
                format_func=lambda value: pd.Timestamp(
                    value
                ).strftime("%b %Y"),
                key="kpi_month_range",
            )
        else:
            selected_kpi_months = None

    kpi_filtered = kpi_report[
        kpi_report["metric"].isin(selected_metrics)
        & kpi_report["department_name"].isin(
            selected_kpi_departments
        )
    ].copy()

    if selected_kpi_months is not None:
        kpi_filtered = kpi_filtered[
            kpi_filtered["month"].between(
                selected_kpi_months[0],
                selected_kpi_months[1],
            )
        ]

    total_kpis = len(kpi_filtered)
    met_count = int(
        (kpi_filtered["performance"] == "Target met").sum()
    )
    suppressed_kpi_count = int(
        (kpi_filtered["performance"] == "Suppressed").sum()
    )
    unavailable_count = int(
        kpi_filtered["performance"].isin(
            [
                "Actual unavailable",
                "Target not configured",
            ]
        ).sum()
    )

    kc1, kc2, kc3, kc4 = st.columns(4)

    kc1.metric("KPI Records", f"{total_kpis:,}")
    kc2.metric("Targets Met", f"{met_count:,}")
    kc3.metric("Suppressed", f"{suppressed_kpi_count:,}")
    kc4.metric("Unavailable / No Target", f"{unavailable_count:,}")

    st.subheader("Actual vs Target")

    chart_kpis = kpi_filtered[
        ~kpi_filtered["privacy_suppressed"]
    ].copy()

    chart_kpis = chart_kpis.dropna(
        subset=["actual", "target"]
    )

    if not chart_kpis.empty:
        chart_kpis["month_label"] = pd.to_datetime(
            chart_kpis["month"]
        ).dt.strftime("%Y-%m")

        selected_metric_for_chart = st.selectbox(
            "Metric to chart",
            options=sorted(chart_kpis["metric"].unique()),
        )

        metric_chart_data = chart_kpis[
            chart_kpis["metric"] == selected_metric_for_chart
        ].copy()

        metric_chart_data = (
            metric_chart_data.groupby(
                ["month", "month_label"],
                as_index=False,
            )
            .agg(
                actual=("actual", "mean"),
                target=("target", "mean"),
            )
            .sort_values("month")
        )

        metric_chart_long = metric_chart_data.melt(
            id_vars=["month", "month_label"],
            value_vars=["actual", "target"],
            var_name="category",
            value_name="value",
        )

        metric_chart_long["category"] = (
            metric_chart_long["category"].map(
                {
                    "actual": "Actual",
                    "target": "Target",
                }
            )
        )

        kpi_fig = px.line(
            metric_chart_long,
            x="month_label",
            y="value",
            color="category",
            markers=True,
            title=f"{selected_metric_for_chart}: actual vs target",
            labels={
                "month_label": "Month",
                "value": "Value",
                "category": "",
            },
        )

        kpi_fig.update_layout(
            hovermode="x unified",
            legend_title_text="",
        )

        st.plotly_chart(
            kpi_fig,
            use_container_width=True,
        )
    else:
        show_empty(
            "No KPI actuals and targets are available together "
            "for charting under the selected filters."
        )

    st.subheader("KPI Details")

    kpi_display = kpi_filtered[
        [
            "month",
            "department_name",
            "metric",
            "employee_count",
            "actual",
            "target",
            "direction",
            "performance",
        ]
    ].copy()

    kpi_display.insert(
        0,
        "S.No",
        range(1, len(kpi_display) + 1),
    )

    kpi_display["month"] = pd.to_datetime(
        kpi_display["month"]
    ).dt.strftime("%Y-%m")

    kpi_display = kpi_display.rename(
        columns={
            "month": "Month",
            "department_name": "Department",
            "metric": "KPI",
            "employee_count": "Employee Count",
            "actual": "Actual",
            "target": "Target",
            "direction": "Desired Direction",
            "performance": "Status",
        }
    )

    st.dataframe(
        kpi_display,
        hide_index=True,
        use_container_width=True,
    )

    kpi_csv = kpi_display.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download Workforce KPI CSV",
        data=kpi_csv,
        file_name="pulseiq_workforce_kpi_tracking.csv",
        mime="text/csv",
    )

st.caption(
    "PulseIQ | Budget reconciliation and workforce KPI analytics"
)
