
import pandas as pd
import plotly.express as px
import streamlit as st

from src.db import get_connection


MIN_GROUP_SIZE = 5

st.set_page_config(
    page_title="Attrition Analytics | PulseIQ",
    page_icon="📉",
    layout="wide",
)

st.title("Attrition Analytics")
st.caption(
    "Employee exits, tenure patterns, department trends, and predicted "
    "attrition risk."
)


@st.cache_data(ttl=300)
def load_query(query):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]

    return pd.DataFrame(rows, columns=columns)


def parse_dates(df, columns):
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_datetime(
                df[column],
                errors="coerce",
            )
    return df


def normalize_id(series):
    return series.astype("string").str.strip()


def safe_count(value):
    if pd.isna(value):
        return "Unavailable"

    value = int(value)

    if 0 < value < MIN_GROUP_SIZE:
        return "Suppressed (<5)"

    return f"{value:,}"


def has_safe_group_size(value):
    return pd.notna(value) and value >= MIN_GROUP_SIZE


def prepare_current_employees(employees):
    employees = employees.copy()

    flags = (
        employees["is_current"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    current_rows = employees[
        flags.isin(["Y", "YES", "TRUE", "T", "1"])
    ].copy()

    current_rows = current_rows.sort_values(
        "valid_from",
        na_position="first",
    )

    current_rows = current_rows.drop_duplicates(
        "employee_id",
        keep="last",
    )

    employees = employees.sort_values(
        "valid_from",
        na_position="first",
    )

    latest_rows = employees.drop_duplicates(
        "employee_id",
        keep="last",
    )

    current_ids = set(
        current_rows["employee_id"].dropna().tolist()
    )

    missing_current = latest_rows[
        ~latest_rows["employee_id"].isin(current_ids)
    ].copy()

    result = pd.concat(
        [current_rows, missing_current],
        ignore_index=True,
    )

    return result.drop_duplicates(
        "employee_id",
        keep="last",
    ).copy()


def calculate_tenure_years(data):
    valid = data[
        data["hire_date"].notna()
        & data["exit_date"].notna()
    ].copy()

    valid["tenure_years"] = (
        valid["exit_date"] - valid["hire_date"]
    ).dt.days / 365.25

    return valid[
        valid["tenure_years"].notna()
        & (valid["tenure_years"] >= 0)
    ].copy()


def prepare_risk_bands(series):
    normalized = (
        series.fillna("Unknown")
        .astype(str)
        .str.strip()
        .str.title()
    )

    valid_bands = {"Low", "Medium", "High"}

    return normalized.where(
        normalized.isin(valid_bands),
        "Unknown",
    )


try:
    employees = load_query(
        """
        SELECT
            employee_id,
            hire_date,
            exit_date,
            employment_status,
            department_id,
            valid_from,
            is_current
        FROM phase2.dim_employee
        """
    )

    departments = load_query(
        """
        SELECT
            department_id,
            department_name
        FROM phase2.dim_department
        """
    )

    risk = load_query(
        """
        SELECT
            employee_id,
            as_of_date,
            risk_score_12m,
            risk_band,
            department_id,
            model_version,
            top_reason_1,
            top_reason_2,
            top_reason_3
        FROM phase2.fact_attrition_risk
        """
    )

except Exception as exc:
    st.error(
        "Unable to load attrition data from PostgreSQL. "
        "Check the database connection and Phase 2 tables."
    )
    st.exception(exc)
    st.stop()


required_employee_columns = {
    "employee_id",
    "hire_date",
    "exit_date",
    "employment_status",
    "department_id",
    "valid_from",
    "is_current",
}

required_risk_columns = {
    "employee_id",
    "as_of_date",
    "risk_score_12m",
    "risk_band",
    "department_id",
}

required_department_columns = {
    "department_id",
    "department_name",
}

if not required_employee_columns.issubset(employees.columns):
    st.error(
        "The PostgreSQL employee table is missing required columns."
    )
    st.stop()

if not required_risk_columns.issubset(risk.columns):
    st.error(
        "The PostgreSQL attrition-risk table is missing required columns."
    )
    st.stop()

if not required_department_columns.issubset(departments.columns):
    st.error(
        "The PostgreSQL department table is missing required columns."
    )
    st.stop()


employees = parse_dates(
    employees,
    ["hire_date", "exit_date", "valid_from"],
)

risk = parse_dates(
    risk,
    ["as_of_date"],
)

employees["employee_id"] = normalize_id(
    employees["employee_id"]
)

risk["employee_id"] = normalize_id(
    risk["employee_id"]
)

employees["department_id"] = normalize_id(
    employees["department_id"]
)

risk["department_id"] = normalize_id(
    risk["department_id"]
)

departments["department_id"] = normalize_id(
    departments["department_id"]
)

employees = employees.dropna(
    subset=["employee_id"]
).copy()

risk = risk.dropna(
    subset=["employee_id", "as_of_date"]
).copy()

department_lookup = (
    departments.dropna(subset=["department_id"])
    .drop_duplicates("department_id")
    .set_index("department_id")["department_name"]
    .to_dict()
)

employees["department"] = employees["department_id"].map(
    department_lookup
)

risk["department"] = risk["department_id"].map(
    department_lookup
)

employees["department"] = (
    employees["department"]
    .fillna("Unassigned")
    .astype(str)
)

risk["department"] = (
    risk["department"]
    .fillna("Unassigned")
    .astype(str)
)

employees["employment_status"] = (
    employees["employment_status"]
    .fillna("Unknown")
    .astype(str)
    .str.strip()
)

risk["risk_score_12m"] = pd.to_numeric(
    risk["risk_score_12m"],
    errors="coerce",
)

invalid_risk_scores = (
    risk["risk_score_12m"].notna()
    & ~risk["risk_score_12m"].between(0, 1)
)

if invalid_risk_scores.any():
    risk.loc[
        invalid_risk_scores,
        "risk_score_12m",
    ] = float("nan")

risk["risk_band"] = prepare_risk_bands(
    risk["risk_band"]
)

current_employees = prepare_current_employees(
    employees
)

exits = current_employees[
    current_employees["exit_date"].notna()
].copy()

exits = exits[
    exits["hire_date"].isna()
    | (exits["exit_date"] >= exits["hire_date"])
].copy()

if exits.empty:
    st.info("No valid employee exit records were found.")


st.sidebar.header("Attrition filters")

date_source = exits["exit_date"].dropna()

if not date_source.empty:
    min_date = date_source.min().date()
    max_date = date_source.max().date()

    selected_dates = st.sidebar.date_input(
        "Exit date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    if (
        isinstance(selected_dates, (tuple, list))
        and len(selected_dates) == 2
    ):
        start_date, end_date = selected_dates
    else:
        start_date, end_date = min_date, max_date

    filtered_exits = exits[
        exits["exit_date"].dt.date.between(
            start_date,
            end_date,
        )
    ].copy()

else:
    filtered_exits = exits.copy()


department_options = sorted(
    current_employees["department"]
    .dropna()
    .unique()
    .tolist()
)

selected_departments = st.sidebar.multiselect(
    "Departments",
    options=department_options,
    default=department_options,
)

filtered_exits = filtered_exits[
    filtered_exits["department"].isin(selected_departments)
].copy()


st.subheader("Employee exits")

if filtered_exits.empty:
    st.info("No employee exits match the selected filters.")

else:
    total_exits = filtered_exits["employee_id"].nunique()

    tenure_data = calculate_tenure_years(
        filtered_exits
    )

    median_tenure_years = (
        tenure_data["tenure_years"].median()
        if not tenure_data.empty
        else None
    )

    if total_exits < MIN_GROUP_SIZE:
        st.info(
            "Exit results are hidden because fewer than five distinct "
            "employees match the selected filters."
        )

    else:
        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Unique employee exits",
            safe_count(total_exits),
        )

        c2.metric(
            "Median tenure at exit",
            (
                f"{median_tenure_years:.1f} years"
                if median_tenure_years is not None
                else "Unavailable"
            ),
        )

        c3.metric(
            "Departments represented",
            f"{filtered_exits['department'].nunique():,}",
        )

        st.caption(
            "Exit totals count distinct employees in the selected period. "
            "They are not an attrition rate because the average workforce "
            "denominator is not calculated on this page."
        )

        monthly = (
            filtered_exits.assign(
                exit_month=(
                    filtered_exits["exit_date"]
                    .dt.to_period("M")
                    .dt.to_timestamp()
                )
            )
            .groupby("exit_month")["employee_id"]
            .nunique()
            .reset_index(name="Employee exits")
            .sort_values("exit_month")
        )

        st.subheader("Monthly exit trend")

        monthly_chart = monthly[
            monthly["Employee exits"] >= MIN_GROUP_SIZE
        ].copy()

        if monthly_chart.empty:
            st.info(
                "Monthly exit chart is hidden because no month reaches "
                "the minimum group size of five."
            )
        else:
            fig = px.line(
                monthly_chart,
                x="exit_month",
                y="Employee exits",
                markers=True,
                labels={
                    "exit_month": "Exit month",
                    "Employee exits": "Distinct employee exits",
                },
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )

        with st.expander("Monthly exit counts"):
            visible_monthly = monthly[
                monthly["Employee exits"] >= MIN_GROUP_SIZE
            ].copy()

            suppressed_months = len(monthly) - len(
                visible_monthly
            )

            if suppressed_months:
                st.info(
                    f"{suppressed_months} month(s) are hidden because "
                    "their exit counts are below five."
                )

            if visible_monthly.empty:
                st.info("No monthly counts meet the privacy threshold.")
            else:
                visible_monthly["Employee exits"] = (
                    visible_monthly["Employee exits"].apply(
                        safe_count
                    )
                )

                st.dataframe(
                    visible_monthly.rename(
                        columns={"exit_month": "Month"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

        st.subheader("Exits by department")

        department_exits = (
            filtered_exits.groupby("department")["employee_id"]
            .nunique()
            .reset_index(name="Employee exits")
        )

        visible_department_exits = department_exits[
            department_exits["Employee exits"] >= MIN_GROUP_SIZE
        ].sort_values(
            "Employee exits",
            ascending=False,
        )

        suppressed_departments = (
            len(department_exits)
            - len(visible_department_exits)
        )

        if suppressed_departments:
            st.info(
                f"{suppressed_departments} department group(s) are "
                "hidden because they contain fewer than five exits."
            )

        if visible_department_exits.empty:
            st.info(
                "Department exit counts are hidden because no department "
                "reaches the minimum group size of five."
            )
        else:
            fig = px.bar(
                visible_department_exits,
                x="department",
                y="Employee exits",
                labels={
                    "department": "Department",
                    "Employee exits": "Distinct employee exits",
                },
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )

        st.subheader("Tenure at exit")

        if len(tenure_data) < MIN_GROUP_SIZE:
            st.info(
                "Tenure distribution is hidden because fewer than five "
                "valid employee records are available."
            )
        else:
            tenure_data = tenure_data.copy()

            tenure_data["Tenure band"] = pd.cut(
                tenure_data["tenure_years"],
                bins=[
                    float("-inf"),
                    1,
                    3,
                    5,
                    10,
                    float("inf"),
                ],
                labels=[
                    "Less than 1 year",
                    "1–3 years",
                    "3–5 years",
                    "5–10 years",
                    "10+ years",
                ],
                right=False,
            )

            tenure_counts = (
                tenure_data.groupby(
                    "Tenure band",
                    observed=False,
                )
                .size()
                .reset_index(name="Employees")
            )

            tenure_counts = tenure_counts[
                tenure_counts["Employees"] > 0
            ]

            if (
                tenure_counts["Employees"] < MIN_GROUP_SIZE
            ).any():
                st.info(
                    "The tenure distribution is hidden because at least "
                    "one tenure band contains fewer than five employees."
                )
            else:
                fig = px.bar(
                    tenure_counts,
                    x="Tenure band",
                    y="Employees",
                    labels={
                        "Tenure band": "Completed tenure at exit",
                        "Employees": "Employees",
                    },
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True,
                )

        st.subheader("Exit status categories")

        status_counts = (
            filtered_exits.groupby("employment_status")[
                "employee_id"
            ]
            .nunique()
            .reset_index(name="Employees")
        )

        visible_status_counts = status_counts[
            status_counts["Employees"] >= MIN_GROUP_SIZE
        ]

        if len(visible_status_counts) != len(status_counts):
            st.info(
                "Some exit status categories are hidden because they "
                "contain fewer than five employees."
            )

        if visible_status_counts.empty:
            st.info(
                "Exit status breakdown is hidden for privacy."
            )
        else:
            st.dataframe(
                visible_status_counts,
                use_container_width=True,
                hide_index=True,
            )

        st.info(
            "Employment status values are presented as recorded. "
            "They are not treated as verified voluntary-exit reasons."
        )

        st.subheader("Three numerical findings")

        visible_months = monthly[
            monthly["Employee exits"] >= MIN_GROUP_SIZE
        ]

        if not visible_months.empty:
            highest_month = visible_months.loc[
                visible_months["Employee exits"].idxmax()
            ]

            st.write(
                f"1. The highest visible monthly exit count was "
                f"{int(highest_month['Employee exits'])} in "
                f"{highest_month['exit_month']:%B %Y}."
            )
        else:
            st.write(
                "1. No monthly exit count is reported because all "
                "monthly groups fall below the privacy threshold."
            )

        if not visible_department_exits.empty:
            top_department = visible_department_exits.iloc[0]

            st.write(
                f"2. {top_department['department']} had the highest "
                f"visible department exit count: "
                f"{int(top_department['Employee exits'])}."
            )
        else:
            st.write(
                "2. No department exit count is reported because the "
                "department groups fall below the privacy threshold."
            )

        if median_tenure_years is not None:
            st.write(
                f"3. Median tenure among valid exit records was "
                f"{median_tenure_years:.1f} years."
            )
        else:
            st.write(
                "3. Median tenure could not be calculated from valid dates."
            )


st.divider()

st.subheader("Predicted, not certain")

st.warning(
    "Risk scores are model predictions, not confirmed future exits. "
    "They must not be used alone to make employment decisions. Use them "
    "only as a signal for supportive, human-led review."
)


if risk.empty:
    st.info("No attrition prediction records are available.")

else:
    available_snapshots = sorted(
        risk["as_of_date"].dropna().unique()
    )

    if not available_snapshots:
        st.info("No prediction snapshot dates are available.")

    else:
        snapshot_labels = [
            pd.Timestamp(value).strftime("%Y-%m-%d")
            for value in available_snapshots
        ]

        selected_snapshot_label = st.selectbox(
            "Prediction snapshot date",
            snapshot_labels,
            index=len(snapshot_labels) - 1,
        )

        selected_snapshot = pd.Timestamp(
            selected_snapshot_label
        )

        snapshot = risk[
            risk["as_of_date"] == selected_snapshot
        ].copy()

        snapshot = snapshot[
            snapshot["department"].isin(selected_departments)
        ].copy()

        snapshot = snapshot.sort_values(
            ["as_of_date", "model_version"],
            na_position="first",
        )

        snapshot = snapshot.drop_duplicates(
            "employee_id",
            keep="last",
        )

        employee_count = snapshot["employee_id"].nunique()

        if employee_count < MIN_GROUP_SIZE:
            st.info(
                "Prediction summaries are hidden because fewer than five "
                "distinct employees are included in this snapshot and filter."
            )

        else:
            model_versions = sorted(
                snapshot["model_version"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

            st.caption(
                f"Snapshot: {selected_snapshot_label} | "
                f"Employees scored: {employee_count:,} | "
                f"Model: {', '.join(model_versions) if model_versions else 'Not specified'}"
            )

            band_counts = (
                snapshot["risk_band"]
                .value_counts()
                .reindex(
                    ["Low", "Medium", "High", "Unknown"],
                    fill_value=0,
                )
            )

            nonzero_bands = band_counts[
                band_counts > 0
            ]

            unsafe_bands = nonzero_bands[
                nonzero_bands < MIN_GROUP_SIZE
            ]

            if not unsafe_bands.empty:
                st.info(
                    "The risk-band breakdown is hidden because at least "
                    "one non-zero band contains fewer than five employees."
                )
            else:
                c1, c2, c3 = st.columns(3)

                c1.metric(
                    "Employees scored",
                    f"{employee_count:,}",
                )

                c2.metric(
                    "High risk band",
                    safe_count(band_counts["High"]),
                )

                c3.metric(
                    "Medium risk band",
                    safe_count(band_counts["Medium"]),
                )

                visible_band_counts = (
                    band_counts[band_counts > 0]
                    .rename_axis("Risk band")
                    .reset_index(name="Predicted employees")
                )

                fig = px.bar(
                    visible_band_counts,
                    x="Risk band",
                    y="Predicted employees",
                    category_orders={
                        "Risk band": [
                            "Low",
                            "Medium",
                            "High",
                            "Unknown",
                        ]
                    },
                    labels={
                        "Predicted employees": "Employees"
                    },
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True,
                )

            risk_department = (
                snapshot.groupby("department", as_index=False)
                .agg(
                    employee_count=("employee_id", "nunique"),
                    mean_risk_score=("risk_score_12m", "mean"),
                    high_risk_count=(
                        "risk_band",
                        lambda values: int(
                            (values == "High").sum()
                        ),
                    ),
                    medium_risk_count=(
                        "risk_band",
                        lambda values: int(
                            (values == "Medium").sum()
                        ),
                    ),
                )
            )

            risk_department = risk_department[
                risk_department["employee_count"] >= MIN_GROUP_SIZE
            ].copy()

            if risk_department.empty:
                st.info(
                    "Department risk summaries are hidden because no "
                    "department meets the minimum group size of five."
                )

            else:
                risk_department["mean_risk_score_pct"] = (
                    risk_department["mean_risk_score"] * 100
                ).round(2)

                risk_department["High-band count"] = (
                    risk_department["high_risk_count"].apply(
                        safe_count
                    )
                )

                risk_department["Medium-band count"] = (
                    risk_department["medium_risk_count"].apply(
                        safe_count
                    )
                )

                st.subheader("Department risk summary")

                chart_data = risk_department[
                    risk_department["mean_risk_score_pct"].notna()
                ].sort_values(
                    "mean_risk_score_pct",
                    ascending=False,
                )

                if chart_data.empty:
                    st.info(
                        "No valid department risk scores are available."
                    )
                else:
                    fig = px.bar(
                        chart_data,
                        x="department",
                        y="mean_risk_score_pct",
                        labels={
                            "department": "Department",
                            "mean_risk_score_pct": (
                                "Average predicted risk score (%)"
                            ),
                        },
                    )

                    st.plotly_chart(
                        fig,
                        use_container_width=True,
                    )

                st.dataframe(
                    risk_department[
                        [
                            "department",
                            "employee_count",
                            "mean_risk_score_pct",
                            "High-band count",
                            "Medium-band count",
                        ]
                    ].rename(
                        columns={
                            "department": "Department",
                            "employee_count": "Employees in group",
                            "mean_risk_score_pct": (
                                "Mean predicted risk (%)"
                            ),
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            reason_columns = [
                column
                for column in [
                    "top_reason_1",
                    "top_reason_2",
                    "top_reason_3",
                ]
                if column in snapshot.columns
            ]

            if reason_columns:
                reasons = snapshot[
                    ["employee_id"] + reason_columns
                ].melt(
                    id_vars="employee_id",
                    value_vars=reason_columns,
                    value_name="reason",
                )

                reasons["reason"] = (
                    reasons["reason"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                )

                reasons = reasons[
                    reasons["reason"] != ""
                ]

                reasons = reasons.drop_duplicates(
                    ["employee_id", "reason"]
                )

                reason_counts = (
                    reasons.groupby("reason")["employee_id"]
                    .nunique()
                    .sort_values(ascending=False)
                    .rename("Distinct employees")
                    .reset_index()
                )

                reason_counts = reason_counts[
                    reason_counts["Distinct employees"]
                    >= MIN_GROUP_SIZE
                ].head(10)

                if reason_counts.empty:
                    st.info(
                        "Reason themes are hidden because no theme is "
                        "associated with at least five distinct employees."
                    )
                else:
                    st.subheader("Common model reason themes")

                    st.caption(
                        "Themes are model outputs, not proof of causation. "
                        "Only themes associated with at least five distinct "
                        "employees are displayed."
                    )

                    st.dataframe(
                        reason_counts.rename(
                            columns={
                                "reason": "Model reason theme",
                                "Distinct employees": "Employees",
                            }
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
