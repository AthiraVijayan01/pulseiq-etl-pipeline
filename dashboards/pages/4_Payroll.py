import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CLEAN_DIR = PROJECT_ROOT / "clean"
RAW_DIR = PROJECT_ROOT / "raw"
MIN_GROUP_SIZE = 5

st.set_page_config(page_title="Payroll Analytics", page_icon="💰", layout="wide")
st.title("Payroll Analytics")
st.caption("Department-level payroll reporting with reconciliation and small-group privacy controls.")


def load_csv(filename):
    for folder in (CLEAN_DIR, RAW_DIR):
        path = folder / filename
        if path.exists():
            try:
                return pd.read_csv(path)
            except Exception as exc:
                st.error(f"Could not read {path.name}: {exc}")
                return pd.DataFrame()
    return pd.DataFrame()


payroll = load_csv("fact_payroll.csv")
departments = load_csv("dim_department.csv")

if payroll.empty:
    st.error("Payroll data was not found or contains no rows.")
    st.stop()

required = {
    "period_end_date",
    "department_id",
    "employee_id",
    "gross_pay",
    "total_deductions",
    "net_pay",
    "employer_cost",
}

missing = required - set(payroll.columns)
if missing:
    st.error(f"Payroll dataset is missing required columns: {', '.join(sorted(missing))}")
    st.stop()

payroll["period_end_date"] = pd.to_datetime(
    payroll["period_end_date"], errors="coerce"
)
payroll["department_id"] = payroll["department_id"].astype("string")

numeric_columns = [
    "gross_pay",
    "total_deductions",
    "net_pay",
    "employer_cost",
    "earned_fixed_pay",
    "overtime_pay",
    "variable_pay",
    "pf_employer",
    "esi_employer",
    "overtime_hours_paid",
    "payable_days",
    "lop_days",
]

for column in numeric_columns:
    if column in payroll.columns:
        payroll[column] = pd.to_numeric(payroll[column], errors="coerce")

payroll = payroll.dropna(
    subset=["period_end_date", "department_id", "employee_id"]
).copy()

if departments.empty or not {"department_id", "department_name"}.issubset(
    departments.columns
):
    if not departments.empty and {
        "department_id",
        "department_name",
    }.issubset(departments.columns):
        pass
    else:
        departments = pd.DataFrame(
            columns=["department_id", "department_name"]
        )

if not departments.empty:
    payroll = payroll.merge(
        departments[["department_id", "department_name"]].drop_duplicates(
            "department_id"
        ),
        on="department_id",
        how="left",
    )

if "department_name" not in payroll.columns:
    payroll["department_name"] = payroll["department_id"]

payroll["department_name"] = payroll["department_name"].fillna(
    payroll["department_id"]
)
payroll["month"] = payroll["period_end_date"].dt.to_period("M").dt.to_timestamp()

st.sidebar.header("Filters")

min_date = payroll["period_end_date"].min().date()
max_date = payroll["period_end_date"].max().date()

date_range = st.sidebar.date_input(
    "Payroll period",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)

if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

department_options = sorted(payroll["department_name"].dropna().unique().tolist())
selected_departments = st.sidebar.multiselect(
    "Departments",
    department_options,
    default=department_options,
)

filtered = payroll[
    payroll["period_end_date"].dt.date.between(start_date, end_date)
    & payroll["department_name"].isin(selected_departments)
].copy()

if filtered.empty:
    st.warning("No payroll records match the selected filters.")
    st.stop()

gross_total = filtered["gross_pay"].sum()
deductions_total = filtered["total_deductions"].sum()
net_total = filtered["net_pay"].sum()
employer_total = filtered["employer_cost"].sum()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Gross payroll", f"₹{gross_total:,.0f}")
c2.metric("Net payroll", f"₹{net_total:,.0f}")
c3.metric("Total deductions", f"₹{deductions_total:,.0f}")
c4.metric("Employer cost", f"₹{employer_total:,.0f}")

st.subheader("Payroll trends")

monthly = (
    filtered.groupby("month", as_index=False)
    .agg(
        gross_pay=("gross_pay", "sum"),
        net_pay=("net_pay", "sum"),
        employer_cost=("employer_cost", "sum"),
    )
    .sort_values("month")
)

left, right = st.columns(2)

with left:
    trend = monthly.melt(
        id_vars="month",
        value_vars=["gross_pay", "net_pay"],
        var_name="pay_type",
        value_name="amount",
    )
    fig = px.line(
        trend,
        x="month",
        y="amount",
        color="pay_type",
        markers=True,
        title="Monthly gross and net payroll",
        labels={
            "month": "Month",
            "amount": "Amount (₹)",
            "pay_type": "Payroll measure",
        },
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    dept_totals = (
        filtered.groupby("department_name", as_index=False)
        .agg(
            gross_pay=("gross_pay", "sum"),
            net_pay=("net_pay", "sum"),
            employee_count=("employee_id", "nunique"),
        )
    )
    dept_totals = dept_totals[
        dept_totals["employee_count"] >= MIN_GROUP_SIZE
    ]
    if dept_totals.empty:
        st.info("Department comparison is hidden because groups are below the privacy threshold.")
    else:
        fig = px.bar(
            dept_totals.sort_values("gross_pay", ascending=False),
            x="department_name",
            y="gross_pay",
            title="Gross payroll by department",
            labels={
                "department_name": "Department",
                "gross_pay": "Gross payroll (₹)",
            },
        )
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)

st.subheader("Payroll reconciliation")

recon = filtered.copy()
recon["net_pay_expected"] = recon["gross_pay"] - recon["total_deductions"]
recon["net_pay_difference"] = recon["net_pay"] - recon["net_pay_expected"]

if {"earned_fixed_pay", "overtime_pay", "variable_pay"}.issubset(recon.columns):
    recon["gross_pay_expected"] = (
        recon["earned_fixed_pay"].fillna(0)
        + recon["overtime_pay"].fillna(0)
        + recon["variable_pay"].fillna(0)
    )
    recon["gross_pay_difference"] = (
        recon["gross_pay"] - recon["gross_pay_expected"]
    )
else:
    recon["gross_pay_difference"] = pd.NA

recon["net_check_pass"] = recon["net_pay_difference"].abs() <= 0.02
recon["gross_check_pass"] = recon["gross_pay_difference"].abs() <= 0.02

total_rows = len(recon)
net_failures = int((~recon["net_check_pass"]).sum())
gross_checked = int(recon["gross_check_pass"].notna().sum())
gross_failures = int((~recon["gross_check_pass"].fillna(True)).sum())

r1, r2, r3 = st.columns(3)
r1.metric("Payroll rows checked", f"{total_rows:,}")
r2.metric("Net pay mismatches", f"{net_failures:,}")
r3.metric("Gross pay mismatches", f"{gross_failures:,}" if gross_checked else "Not checked")

st.caption(
    "Checks use a tolerance of ₹0.02. These checks are preliminary and do not replace the assignment's required payroll validation instruction."
)

st.subheader("Department-month summary")

summary = (
    filtered.groupby(
        ["month", "department_id", "department_name"], as_index=False
    )
    .agg(
        employee_count=("employee_id", "nunique"),
        gross_pay=("gross_pay", "sum"),
        net_pay=("net_pay", "sum"),
        total_deductions=("total_deductions", "sum"),
        employer_cost=("employer_cost", "sum"),
    )
)

summary = summary[summary["employee_count"] >= MIN_GROUP_SIZE].copy()
summary["employer_cost_per_employee"] = (
    summary["employer_cost"] / summary["employee_count"]
)

if summary.empty:
    st.info("Department-month summary is hidden because all groups are below the privacy threshold.")
else:
    display = summary.rename(
        columns={
            "month": "Month",
            "department_id": "Department ID",
            "department_name": "Department",
            "employee_count": "Employees",
            "gross_pay": "Gross payroll (₹)",
            "net_pay": "Net payroll (₹)",
            "total_deductions": "Deductions (₹)",
            "employer_cost": "Employer cost (₹)",
            "employer_cost_per_employee": "Employer cost per employee (₹)",
        }
    )
    st.dataframe(
        display.sort_values(["Month", "Department"]),
        hide_index=True,
        use_container_width=True,
    )

with st.expander("Data-quality notes"):
    st.write(f"Records included after date and department filters: {len(filtered):,}")
    st.write(f"Distinct employees in filtered records: {filtered['employee_id'].nunique():,}")
    st.write(f"Missing variable-pay type values: {int(filtered['variable_pay_type'].isna().sum()) if 'variable_pay_type' in filtered.columns else 'Column not available'}")
    st.write("Individual employee salary records are not displayed.")
    st.write("Department summaries suppress groups with fewer than five distinct employees.")
