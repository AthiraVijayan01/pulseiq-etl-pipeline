from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="KPI Explorer | PulseIQ",
    page_icon="📊",
    layout="wide"
)

PROJECT_DIR = Path(__file__).resolve().parents[2]
DEPARTMENT_FILE = PROJECT_DIR / "outputs" / "task13_department_month.csv"
TEAM_FILE = PROJECT_DIR / "clean" / "dim_team.csv"
DEPARTMENT_DIM_FILE = PROJECT_DIR / "clean" / "dim_department.csv"

MIN_GROUP_SIZE = 5

ROLE_METRICS = {
    "ADMIN": [
        "Headcount",
        "Hires",
        "Exits",
        "Exit Rate",
        "Employer Cost",
        "Overtime Cost",
        "Attendance Rate",
        "Approved Leave Days"
    ],
    "HR": [
        "Headcount",
        "Hires",
        "Exits",
        "Exit Rate",
        "Attendance Rate",
        "Approved Leave Days"
    ],
    "MANAGER": [
        "Headcount",
        "Attendance Rate",
        "Approved Leave Days"
    ],
    "EXECUTIVE": [
        "Headcount",
        "Exit Rate",
        "Employer Cost",
        "Overtime Cost",
        "Attendance Rate"
    ]
}

METRIC_DEFINITIONS = {
    "Headcount": "Sum of month-end department headcount.",
    "Hires": "Total hires recorded during the selected month.",
    "Exits": "Total employee exits recorded during the selected month.",
    "Exit Rate": "Exit rate recalculated using exits divided by average headcount.",
    "Employer Cost": "Total employer payroll cost for the selected month.",
    "Overtime Cost": "Total overtime cost for the selected month.",
    "Attendance Rate": "Total present days divided by total scheduled days.",
    "Approved Leave Days": "Total approved leave days allocated to departments."
}


@st.cache_data
def load_data():
    departments = pd.read_csv(DEPARTMENT_FILE)
    teams = pd.read_csv(TEAM_FILE)

    department_dimension = (
        pd.read_csv(DEPARTMENT_DIM_FILE)
        if DEPARTMENT_DIM_FILE.exists()
        else pd.DataFrame()
    )

    departments["month"] = pd.to_datetime(
        departments["month"], errors="coerce"
    )

    for column in [
        "department_id",
        "headcount_end",
        "hires",
        "exits",
        "employer_cost",
        "overtime_cost",
        "present_days",
        "scheduled_days",
        "approved_leave_days",
        "average_headcount"
    ]:
        if column not in departments.columns:
            raise ValueError(f"Required column missing: {column}")

    for column in ["team_id", "department_id", "active_members"]:
        if column not in teams.columns:
            raise ValueError(f"Required team column missing: {column}")

    teams["active_members"] = pd.to_numeric(
        teams["active_members"], errors="coerce"
    ).fillna(0)

    return departments, teams, department_dimension


def calculate_metric(data, metric):
    if data.empty:
        return None

    if metric == "Headcount":
        return data["headcount_end"].sum()

    if metric == "Hires":
        return data["hires"].sum()

    if metric == "Exits":
        return data["exits"].sum()

    if metric == "Employer Cost":
        return data["employer_cost"].sum()

    if metric == "Overtime Cost":
        return data["overtime_cost"].sum()

    if metric == "Approved Leave Days":
        return data["approved_leave_days"].sum()

    if metric == "Attendance Rate":
        scheduled = data["scheduled_days"].sum()
        if scheduled <= 0:
            return None
        return data["present_days"].sum() / scheduled * 100

    if metric == "Exit Rate":
        average_headcount = data["average_headcount"].sum()
        if average_headcount <= 0:
            return None
        return data["exits"].sum() / average_headcount * 100

    return None


def display_metric(value, metric):
    if value is None or pd.isna(value):
        return "Unavailable"

    if metric in ["Employer Cost", "Overtime Cost"]:
        return f"₹{value:,.2f}"

    if metric in ["Attendance Rate", "Exit Rate"]:
        return f"{value:.2f}%"

    if metric == "Headcount":
        return f"{value:,.0f}"

    return f"{value:,.2f}"


st.title("📊 PulseIQ – Self-Service KPI Explorer")

st.caption(
    "Explore workforce, attendance and cost metrics "
    "with minimum-group privacy protection."
)

st.info(
    "Demonstration role selector only. This is not production "
    "authentication or authorization."
)

try:
    departments, teams, department_dimension = load_data()
except Exception as error:
    st.error(f"Unable to load KPI Explorer data: {error}")
    st.stop()


# Role selection
role = st.selectbox(
    "Select demonstration role",
    ["ADMIN", "HR", "MANAGER", "EXECUTIVE"]
)

st.caption(f"Current demonstration role: {role}")

# Month selection
available_months = sorted(
    departments["month"].dropna().unique(),
    reverse=True
)

if not available_months:
    st.error("No valid reporting months are available.")
    st.stop()

selected_month = st.selectbox(
    "Reporting month",
    available_months,
    format_func=lambda value: pd.Timestamp(value).strftime("%B %Y")
)

monthly_data = departments[
    departments["month"] == selected_month
].copy()

# Optional department names
if (
    not department_dimension.empty
    and {"department_id", "department_name"}.issubset(
        department_dimension.columns
    )
):
    department_names = dict(
        zip(
            department_dimension["department_id"],
            department_dimension["department_name"]
        )
    )
else:
    department_names = {}


# Exploration level
level = st.radio(
    "Explore by",
    ["Company", "Department", "Team"],
    horizontal=True
)

if level == "Team":
    metric = "Active Team Members"
else:
    metric = st.selectbox(
        "Choose KPI",
        ROLE_METRICS[role]
    )


st.divider()

if level == "Company":

    company_size = monthly_data["headcount_end"].sum()

    if company_size < MIN_GROUP_SIZE:
        st.warning(
            "Company results are hidden because the group "
            "does not meet the minimum group size."
        )
        st.stop()

    value = calculate_metric(monthly_data, metric)

    st.subheader("Company-level result")
    st.metric(metric, display_metric(value, metric))
    st.caption(
        f"Reporting month: {pd.Timestamp(selected_month):%B %Y}"
    )
    st.caption(METRIC_DEFINITIONS[metric])

elif level == "Department":

    department_sizes = (
        monthly_data.groupby("department_id")["headcount_end"]
        .sum()
    )

    safe_departments = department_sizes[
        department_sizes >= MIN_GROUP_SIZE
    ].index.tolist()

    suppressed_count = len(department_sizes) - len(safe_departments)

    if suppressed_count:
        st.warning(
            f"{suppressed_count} department group(s) are hidden "
            f"because they have fewer than {MIN_GROUP_SIZE} people."
        )

    if not safe_departments:
        st.warning("No departments meet the privacy threshold.")
        st.stop()

    selected_department = st.selectbox(
        "Select department",
        safe_departments,
        format_func=lambda value: (
            f"{department_names.get(value, value)} ({value})"
        )
    )

    selected_data = monthly_data[
        monthly_data["department_id"] == selected_department
    ]

    group_size = selected_data["headcount_end"].sum()

    if group_size < MIN_GROUP_SIZE:
        st.warning("This department is suppressed for privacy.")
        st.stop()

    value = calculate_metric(selected_data, metric)

    st.subheader("Department-level result")
    st.metric(metric, display_metric(value, metric))
    st.caption(
        f"Department: {department_names.get(selected_department, selected_department)}"
    )
    st.caption(METRIC_DEFINITIONS[metric])


elif level == "Team":

    st.caption(
        "Team-level exploration currently exposes active membership "
        "counts only. Department-level financial and HR metrics are "
        "not allocated to teams in the available dataset."
    )

    team_sizes = teams[
        teams["active_members"] >= MIN_GROUP_SIZE
    ].copy()

    suppressed_teams = len(teams) - len(team_sizes)

    if suppressed_teams:
        st.warning(
            f"{suppressed_teams} team(s) hidden because they do not "
            f"meet the minimum group size of {MIN_GROUP_SIZE}."
        )

    if team_sizes.empty:
        st.warning("No teams meet the privacy threshold.")
        st.stop()

    safe_departments = sorted(
        team_sizes["department_id"].dropna().unique()
    )

    selected_department = st.selectbox(
        "Select department",
        safe_departments,
        format_func=lambda value: (
            f"{department_names.get(value, value)} ({value})"
        )
    )

    department_teams = team_sizes[
        team_sizes["department_id"] == selected_department
    ]

    if department_teams.empty:
        st.warning("No eligible teams are available.")
        st.stop()

    selected_team = st.selectbox(
        "Select team",
        department_teams["team_id"].tolist(),
        format_func=lambda value: (
            department_teams.loc[
                department_teams["team_id"] == value,
                "team_name"
            ].iloc[0]
        )
    )

    team_row = department_teams[
        department_teams["team_id"] == selected_team
    ].iloc[0]

    active_members = int(team_row["active_members"])

    if active_members < MIN_GROUP_SIZE:
        st.warning("This team is suppressed for privacy.")
        st.stop()

    st.subheader("Team-level result")
    st.metric("Active Team Members", active_members)
    st.caption(f"Team: {team_row['team_name']}")
    st.caption(
        f"Department: {department_names.get(selected_department, selected_department)}"
    )


st.divider()

st.subheader("Privacy protection")

st.write(
    f"Minimum group size: **{MIN_GROUP_SIZE} people**"
)

st.success(
    "Groups below the minimum threshold are excluded from "
    "the available department and team selections."
)

st.caption(
    "This demonstration uses aggregated department and team data. "
    "It does not expose employee-level records. A production system "
    "must enforce role permissions on the server using authenticated "
    "user identities."
)
