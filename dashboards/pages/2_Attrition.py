
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLEAN_DIR = PROJECT_ROOT / "clean"
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


@st.cache_data
def load_csv(filename):
    path = CLEAN_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"Required data file not found: {path}")

    return pd.read_csv(path, low_memory=False)


def parse_dates(df, columns):
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
    return df


def safe_count(value):
    value = int(value)

    if 0 < value < MIN_GROUP_SIZE:
        return "Suppressed (<5)"

    return f"{value:,}"


try:
    employees = load_csv("dim_employee.csv")
    departments = load_csv("dim_department.csv")
    risk = load_csv("fact_attrition_risk.csv")

except (FileNotFoundError, pd.errors.ParserError) as exc:
    st.error(f"Unable to load attrition data: {exc}")
    st.stop()


required_employee_columns = {
    "employee_id",
    "hire_date",
    "exit_date",
    "employment_status",
    "department_id",
}

required_risk_columns = {
    "employee_id",
    "as_of_date",
    "risk_score_12m",
    "risk_band",
    "department_id",
}

if not required_employee_columns.issubset(employees.columns):
    st.error("The employee CSV is missing required columns.")
    st.stop()

if not required_risk_columns.issubset(risk.columns):
    st.error("The attrition-risk CSV is missing required columns.")
    st.stop()

if not {"department_id", "department_name"}.issubset(departments.columns):
    st.error("The department CSV is missing required columns.")
    st.stop()


employees = parse_dates(employees, ["hire_date", "exit_date", "valid_from"])
risk = parse_dates(risk, ["as_of_date"])

employees["employee_id"] = employees["employee_id"].astype("string").str.strip()
risk["employee_id"] = risk["employee_id"].astype("string").str.strip()

employees = employees.dropna(subset=["employee_id"]).copy()
risk = risk.dropna(subset=["employee_id", "as_of_date"]).copy()

department_lookup = (
    departments.dropna(subset=["department_id"])
    .drop_duplicates("department_id")
    .set_index("department_id")["department_name"]
    .to_dict()
)

employees["department"] = employees["department_id"].map(department_lookup)
risk["department"] = risk["department_id"].map(department_lookup)

employees["employment_status"] = (
    employees["employment_status"].fillna("Unknown").astype(str).str.strip()
)

risk["risk_score_12m"] = pd.to_numeric(
    risk["risk_score_12m"], errors="coerce"
)

if risk["risk_score_12m"].dropna().empty:
    st.warning("No numeric risk scores are available.")

# Use one employee record, preferring the current version.
if "is_current" in employees.columns:
    current_flags = (
        employees["is_current"]
        .astype(str)
        .str.strip()
        .str.upper()
    )
    current_employees = employees[current_flags.isin(["Y", "TRUE", "1"])].copy()
else:
    current_employees = employees.iloc[0:0].copy()

if current_employees["employee_id"].duplicated().any():
    current_employees = current_employees.sort_values(
        "valid_from", na_position="first"
    ).drop_duplicates("employee_id", keep="last")

if current_employees.empty:
    current_employees = (
        employees.sort_values("valid_from", na_position="first")
        .drop_duplicates("employee_id", keep="last")
        .copy()
    )

# Exit records require a valid exit date. Deduplication prevents SCD versions
# from counting the same person multiple times.
exits = current_employees[
    current_employees["exit_date"].notna()
].copy()

exits = exits.drop_duplicates("employee_id", keep="last")
exits = exits[exits["hire_date"].isna() | (exits["exit_date"] >= exits["hire_date"])]

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

    if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
    else:
        start_date, end_date = min_date, max_date

    filtered_exits = exits[
        exits["exit_date"].dt.date.between(start_date, end_date)
    ].copy()
else:
    filtered_exits = exits.copy()

department_options = sorted(
    current_employees["department"].dropna().unique().tolist()
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

    tenure_days = (
        filtered_exits["exit_date"] - filtered_exits["hire_date"]
    ).dt.days

    valid_tenure = tenure_days[tenure_days >= 0]
    median_tenure_years = (
        valid_tenure.median() / 365.25 if not valid_tenure.empty else None
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Unique employee exits", f"{total_exits:,}")
    c2.metric(
        "Median tenure at exit",
        f"{median_tenure_years:.1f} years"
        if median_tenure_years is not None
        else "Unavailable",
    )
    c3.metric(
        "Departments represented",
        f"{filtered_exits['department'].nunique():,}",
    )

    st.caption(
        "Exit totals count distinct employees in the selected period. "
        "They are not an attrition rate because the average workforce "
        "denominator has not been calculated here."
    )

    monthly = (
        filtered_exits.assign(
            exit_month=filtered_exits["exit_date"].dt.to_period("M").dt.to_timestamp()
        )
        .groupby("exit_month")["employee_id"]
        .nunique()
        .reset_index(name="Employee exits")
        .sort_values("exit_month")
    )

    # Suppress monthly counts below five.
    monthly["Display exits"] = monthly["Employee exits"].apply(safe_count)

    st.subheader("Monthly exit trend")
    monthly_chart = monthly[
        monthly["Employee exits"] >= MIN_GROUP_SIZE
    ].copy()

    if monthly_chart.empty:
        st.info(
            "Monthly exit chart is hidden because no month reaches the "
            "minimum group size of five."
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
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("Monthly exit counts"):
        st.dataframe(
            monthly[["exit_month", "Display exits"]].rename(
                columns={
                    "exit_month": "Month",
                    "Display exits": "Employee exits",
                }
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

    department_exits = department_exits[
        department_exits["Employee exits"] >= MIN_GROUP_SIZE
    ].sort_values("Employee exits", ascending=False)

    if department_exits.empty:
        st.info(
            "Department exit counts are hidden because no department "
            "reaches the minimum group size of five."
        )
    else:
        fig = px.bar(
            department_exits,
            x="department",
            y="Employee exits",
            labels={
                "department": "Department",
                "Employee exits": "Distinct employee exits",
            },
        )
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Tenure at exit")

    tenure_data = filtered_exits.copy()
    tenure_data["Tenure (years)"] = (
        tenure_data["exit_date"] - tenure_data["hire_date"]
    ).dt.days / 365.25

    tenure_data = tenure_data[
        tenure_data["Tenure (years)"].notna()
        & (tenure_data["Tenure (years)"] >= 0)
    ]

    if len(tenure_data) >= MIN_GROUP_SIZE:
        fig = px.histogram(
            tenure_data,
            x="Tenure (years)",
            nbins=12,
            labels={"Tenure (years)": "Completed tenure at exit (years)"},
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(
            "Tenure distribution is hidden because fewer than five "
            "valid employee records are available."
        )

    st.subheader("Exit status categories")

    status_counts = (
        filtered_exits.groupby("employment_status")["employee_id"]
        .nunique()
        .reset_index(name="Employees")
    )

    status_counts = status_counts[
        status_counts["Employees"] >= MIN_GROUP_SIZE
    ]

    if status_counts.empty:
        st.info("Exit status breakdown is hidden for privacy.")
    else:
        st.dataframe(status_counts, use_container_width=True, hide_index=True)

    st.info(
        "The dataset contains employment status values such as Resigned, "
        "Terminated, and Contract Ended. These are presented as recorded; "
        "the available change_reason field is not treated as a verified "
        "voluntary-exit reason."
    )

    st.subheader("Three numerical findings")

    if not monthly.empty:
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
                "1. No monthly exit count is reported because all monthly "
                "groups fall below the privacy threshold."
            )

    if not department_exits.empty:
        top_department = department_exits.iloc[0]
        st.write(
            f"2. {top_department['department']} had the highest visible "
            f"department exit count: {int(top_department['Employee exits'])}."
        )
    else:
        st.write(
            "2. No department exit count is reported because the department "
            "groups fall below the privacy threshold."
        )

    if median_tenure_years is not None:
        st.write(
            f"3. Median tenure among valid exit records was "
            f"{median_tenure_years:.1f} years."
        )
    else:
        st.write("3. Median tenure could not be calculated from valid dates.")

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
    available_snapshots = sorted(risk["as_of_date"].dropna().unique())

    if not available_snapshots:
        st.info("No prediction snapshot dates are available.")
    else:
        snapshot_labels = {
            pd.Timestamp(value).strftime("%Y-%m-%d"): pd.Timestamp(value)
            for value in available_snapshots
        }

        selected_snapshot_label = st.selectbox(
            "Prediction snapshot date",
            list(snapshot_labels.keys()),
            index=len(snapshot_labels) - 1,
        )

        selected_snapshot = snapshot_labels[selected_snapshot_label]

        snapshot = risk[risk["as_of_date"] == selected_snapshot].copy()
        snapshot = snapshot[
            snapshot["department"].isin(selected_departments)
        ].copy()

        snapshot = (
            snapshot.sort_values("as_of_date")
            .drop_duplicates("employee_id", keep="last")
        )

        employee_count = snapshot["employee_id"].nunique()

        if employee_count < MIN_GROUP_SIZE:
            st.info(
                "Prediction summaries are hidden because fewer than five "
                "distinct employees are included in this snapshot and filter."
            )
        else:
            model_versions = (
                sorted(snapshot["model_version"].dropna().astype(str).unique())
                if "model_version" in snapshot.columns
                else []
            )

            st.caption(
                f"Snapshot: {selected_snapshot_label} | "
                f"Employees scored: {employee_count:,} | "
                f"Model: {', '.join(model_versions) if model_versions else 'Not specified'}"
            )

            band_order = ["Low", "Medium", "High"]
            band_counts = (
                snapshot["risk_band"].fillna("Unknown")
                .value_counts()
                .reindex(band_order, fill_value=0)
            )

            small_nonzero_band = (
                (band_counts > 0) & (band_counts < MIN_GROUP_SIZE)
            ).any()

            if small_nonzero_band:
                st.info(
                    "The risk-band breakdown is hidden because at least one "
                    "non-zero band contains fewer than five employees."
                )
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("Employees scored", f"{employee_count:,}")
                c2.metric("High risk band", f"{int(band_counts['High']):,}")
                c3.metric("Medium risk band", f"{int(band_counts['Medium']):,}")

                band_chart = (
                    band_counts.rename_axis("Risk band")
                    .reset_index(name="Predicted employees")
                )

                fig = px.bar(
                    band_chart,
                    x="Risk band",
                    y="Predicted employees",
                    category_orders={"Risk band": band_order},
                    labels={"Predicted employees": "Employees"},
                )
                st.plotly_chart(fig, use_container_width=True)

            risk_department = (
                snapshot.groupby("department", as_index=False)
                .agg(
                    employee_count=("employee_id", "nunique"),
                    mean_risk_score=("risk_score_12m", "mean"),
                    high_risk_count=(
                        "risk_band",
                        lambda values: int((values == "High").sum()),
                    ),
                    medium_risk_count=(
                        "risk_band",
                        lambda values: int((values == "Medium").sum()),
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
                    risk_department["high_risk_count"].apply(safe_count)
                )
                risk_department["Medium-band count"] = (
                    risk_department["medium_risk_count"].apply(safe_count)
                )

                st.subheader("Department risk summary")
                fig = px.bar(
                    risk_department.sort_values(
                        "mean_risk_score_pct", ascending=False
                    ),
                    x="department",
                    y="mean_risk_score_pct",
                    labels={
                        "department": "Department",
                        "mean_risk_score_pct": "Average predicted risk score (%)",
                    },
                )
                st.plotly_chart(fig, use_container_width=True)

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
                            "mean_risk_score_pct": "Mean predicted risk (%)",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            reason_columns = [
                column
                for column in ["top_reason_1", "top_reason_2", "top_reason_3"]
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
                    reasons["reason"].fillna("").astype(str).str.strip()
                )
                reasons = reasons[reasons["reason"] != ""]
                reasons = reasons.drop_duplicates(["employee_id", "reason"])

                reason_counts = (
                    reasons.groupby("reason")["employee_id"]
                    .nunique()
                    .sort_values(ascending=False)
                    .rename("Distinct employees")
                    .reset_index()
                )

                reason_counts = reason_counts[
                    reason_counts["Distinct employees"] >= MIN_GROUP_SIZE
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

            if "model_note" in snapshot.columns:
                model_notes = snapshot["model_note"].dropna().unique()
                if len(model_notes):
                    st.info(str(model_notes[0]))
