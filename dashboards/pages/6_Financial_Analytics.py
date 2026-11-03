
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]


st.set_page_config(
    page_title="Financial Analytics",
    page_icon="💰",
    layout="wide"
)


def load_csv(filename):
    path = ROOT / "clean" / filename

    if not path.exists():
        path = ROOT / "raw" / filename

    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {filename}")

    return pd.read_csv(path)


@st.cache_data
def load_data():
    ledger = load_csv("fact_ledger.csv")
    account = load_csv("dim_account.csv")
    expense = load_csv("fact_expense.csv")
    vendor = load_csv("dim_vendor.csv")

    for col in ["account_code", "debit", "credit"]:
        ledger[col] = pd.to_numeric(
            ledger[col], errors="coerce"
        )

    account["account_code"] = pd.to_numeric(
        account["account_code"], errors="coerce"
    )

    expense["category_account"] = pd.to_numeric(
        expense["category_account"], errors="coerce"
    )

    expense["amount_excl_gst"] = pd.to_numeric(
        expense["amount_excl_gst"], errors="coerce"
    )

    expense["expense_date"] = pd.to_datetime(
        expense["expense_date"], errors="coerce"
    )

    ledger["posting_period"] = (
        ledger["posting_period"].astype(str).str.strip()
    )

    return ledger, account, expense, vendor


def prepare_pnl(ledger, account):
    pnl_accounts = account[
        (account["statement"].astype(str).str.strip() == "Profit & Loss")
        & (account["is_group"].astype(str).str.upper() == "N")
        & (account["is_active"].astype(str).str.upper() == "Y")
    ][
        ["account_code", "account_name", "account_type"]
    ].copy()

    data = ledger.merge(
        pnl_accounts,
        on="account_code",
        how="inner"
    )

    data = data[
        data["source_type"].astype(str).str.upper() != "OPENING"
    ].copy()

    data["revenue"] = 0.0
    data["expenses"] = 0.0

    income_mask = (
        data["account_type"].astype(str).str.upper() == "INCOME"
    )

    expense_mask = (
        data["account_type"].astype(str).str.upper() == "EXPENSE"
    )

    data.loc[income_mask, "revenue"] = (
        data.loc[income_mask, "credit"]
        - data.loc[income_mask, "debit"]
    )

    data.loc[expense_mask, "expenses"] = (
        data.loc[expense_mask, "debit"]
        - data.loc[expense_mask, "credit"]
    )

    return data


def format_currency(value):
    return f"₹{value:,.2f}"


try:
    ledger, account, expense, vendor = load_data()

    pnl_data = prepare_pnl(ledger, account)

except Exception as error:
    st.error(f"Unable to load financial data: {error}")
    st.stop()


# ============================================================
# PAGE HEADER
# ============================================================

st.title("Financial Analytics")

st.caption(
    "Profitability, expense distribution, vendor spending "
    "and monthly financial performance."
)

st.divider()


# ============================================================
# MONTHLY PROFIT AND LOSS
# ============================================================

monthly = pnl_data.groupby("posting_period").agg(
    revenue=("revenue", "sum"),
    expenses=("expenses", "sum")
).reset_index()

monthly["net_profit"] = (
    monthly["revenue"] - monthly["expenses"]
)

monthly["profit_margin"] = (
    monthly["net_profit"] / monthly["revenue"] * 100
).where(monthly["revenue"] != 0, 0)

monthly = monthly.sort_values("posting_period")

if monthly.empty:
    st.warning("No monthly P&L records are available.")
    st.stop()


# ============================================================
# MONTH SELECTOR
# ============================================================

st.subheader("Monthly Profit & Loss")

available_months = monthly["posting_period"].tolist()

selected_month = st.selectbox(
    "Select Reporting Month",
    available_months,
    index=len(available_months) - 1
)

selected_data = monthly[
    monthly["posting_period"] == selected_month
]

revenue = float(selected_data["revenue"].iloc[0])
expenses = float(selected_data["expenses"].iloc[0])
profit = float(selected_data["net_profit"].iloc[0])
margin = float(selected_data["profit_margin"].iloc[0])


# ============================================================
# FINANCIAL KPI CARDS
# ============================================================

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Revenue",
    format_currency(revenue)
)

col2.metric(
    "Total Expenses",
    format_currency(expenses)
)

col3.metric(
    "Net Profit",
    format_currency(profit)
)

col4.metric(
    "Profit Margin",
    f"{margin:.2f}%"
)


# ============================================================
# DETAILED PROFIT AND LOSS TABLE
# ============================================================

st.divider()
st.subheader("Detailed Profit & Loss Statement")

selected_ledger = pnl_data[
    pnl_data["posting_period"] == selected_month
].copy()

account_summary = selected_ledger.groupby(
    ["account_code", "account_name", "account_type"]
).agg(
    debit=("debit", "sum"),
    credit=("credit", "sum")
).reset_index()

account_summary["amount"] = 0.0

income_mask = (
    account_summary["account_type"].astype(str).str.upper()
    == "INCOME"
)

expense_mask = (
    account_summary["account_type"].astype(str).str.upper()
    == "EXPENSE"
)

account_summary.loc[income_mask, "amount"] = (
    account_summary.loc[income_mask, "credit"]
    - account_summary.loc[income_mask, "debit"]
)

account_summary.loc[expense_mask, "amount"] = (
    account_summary.loc[expense_mask, "debit"]
    - account_summary.loc[expense_mask, "credit"]
)

income_table = account_summary[
    income_mask
][["account_code", "account_name", "amount"]].copy()

expense_table = account_summary[
    expense_mask
][["account_code", "account_name", "amount"]].copy()

st.markdown("**Revenue Accounts**")

if not income_table.empty:
    st.dataframe(
        income_table.rename(
            columns={
                "account_code": "Account Code",
                "account_name": "Account Name",
                "amount": "Revenue"
            }
        ),
        hide_index=True,
        use_container_width=True
    )
else:
    st.info("No revenue records for this month.")

st.markdown("**Expense Accounts**")

if not expense_table.empty:
    st.dataframe(
        expense_table.rename(
            columns={
                "account_code": "Account Code",
                "account_name": "Account Name",
                "amount": "Expense"
            }
        ),
        hide_index=True,
        use_container_width=True
    )
else:
    st.info("No expense records for this month.")

pnl_summary = pd.DataFrame({
    "Particulars": [
        "Total Revenue",
        "Total Expenses",
        "Net Profit"
    ],
    "Amount": [
        revenue,
        expenses,
        profit
    ]
})

st.markdown("**P&L Summary**")

st.dataframe(
    pnl_summary.style.format(
        {"Amount": "₹{:,.2f}"}
    ),
    hide_index=True,
    use_container_width=True
)


# ============================================================
# MONTHLY FINANCIAL TREND
# ============================================================

st.divider()
st.subheader("Monthly Financial Trend")

trend = monthly.melt(
    id_vars="posting_period",
    value_vars=["revenue", "expenses"],
    var_name="Financial Metric",
    value_name="Amount"
)

trend["Financial Metric"] = trend[
    "Financial Metric"
].map({
    "revenue": "Revenue",
    "expenses": "Expenses"
})

fig = px.line(
    trend,
    x="posting_period",
    y="Amount",
    color="Financial Metric",
    markers=True,
    title="Monthly Revenue vs Expenses"
)

fig.update_layout(
    xaxis_title="Reporting Month",
    yaxis_title="Amount (₹)",
    legend_title="Metric"
)

st.plotly_chart(
    fig,
    use_container_width=True
)


# ============================================================
# EXPENSE CATEGORY ANALYSIS
# ============================================================

st.divider()
st.subheader("Expense Analysis by Category")

category_data = expense.merge(
    account[["account_code", "account_name"]],
    left_on="category_account",
    right_on="account_code",
    how="left"
)

category_data = category_data[
    category_data["account_name"].notna()
].copy()

category_data = category_data[
    category_data["expense_date"].dt.strftime("%Y-%m")
    == selected_month
]

category_summary = category_data.groupby(
    ["category_account", "account_name"]
).agg(
    transactions=("expense_id", "count"),
    expense_amount=("amount_excl_gst", "sum")
).reset_index()

category_summary = category_summary.sort_values(
    "expense_amount",
    ascending=False
)

if not category_summary.empty:

    category_fig = px.bar(
        category_summary,
        x="account_name",
        y="expense_amount",
        title=f"Expense by Category — {selected_month}",
        text_auto=".2s"
    )

    category_fig.update_layout(
        xaxis_title="Expense Category",
        yaxis_title="Amount Excluding GST (₹)",
        xaxis_tickangle=-35
    )

    st.plotly_chart(
        category_fig,
        use_container_width=True
    )

    st.dataframe(
        category_summary.rename(
            columns={
                "category_account": "Account Code",
                "account_name": "Category",
                "transactions": "Transactions",
                "expense_amount": "Amount Excluding GST"
            }
        ).style.format(
            {"Amount Excluding GST": "₹{:,.2f}"}
        ),
        hide_index=True,
        use_container_width=True
    )

else:
    st.info("No expense category records for this month.")


# ============================================================
# TOP 10 VENDORS
# ============================================================

st.divider()
st.subheader("Top 10 Vendors")

vendor_data = expense.merge(
    vendor[["vendor_id", "vendor_name"]],
    on="vendor_id",
    how="left"
)

vendor_data = vendor_data[
    vendor_data["expense_date"].dt.strftime("%Y-%m")
    == selected_month
]

vendor_summary = vendor_data.groupby(
    ["vendor_id", "vendor_name"],
    dropna=False
).agg(
    transactions=("expense_id", "count"),
    total_spend=("amount_excl_gst", "sum")
).reset_index()

vendor_summary = vendor_summary.sort_values(
    "total_spend",
    ascending=False
).head(10)

if not vendor_summary.empty:

    vendor_fig = px.bar(
        vendor_summary.sort_values("total_spend"),
        x="total_spend",
        y="vendor_name",
        orientation="h",
        title=f"Top 10 Vendors — {selected_month}",
        text_auto=".2s"
    )

    vendor_fig.update_layout(
        xaxis_title="Amount Excluding GST (₹)",
        yaxis_title="Vendor"
    )

    st.plotly_chart(
        vendor_fig,
        use_container_width=True
    )

    st.dataframe(
        vendor_summary.rename(
            columns={
                "vendor_id": "Vendor ID",
                "vendor_name": "Vendor Name",
                "transactions": "Transactions",
                "total_spend": "Total Spend"
            }
        ).style.format(
            {"Total Spend": "₹{:,.2f}"}
        ),
        hide_index=True,
        use_container_width=True
    )

else:
    st.info("No vendor expense records for this month.")


# ============================================================
# FINANCIAL OBSERVATIONS
# ============================================================

st.divider()
st.subheader("Financial Observations")

st.markdown(
    f"""
    - Revenue for **{selected_month}** was **{format_currency(revenue)}**.
    - Expenses for **{selected_month}** were **{format_currency(expenses)}**.
    - Net profit was **{format_currency(profit)}**.
    - Profit margin was **{margin:.2f}%**.
    """
)

st.caption(
    "P&L figures are calculated from posted ledger entries using "
    "active detail-level Profit & Loss accounts. Opening journal "
    "entries are excluded, and group accounts are not included. "
    "Expense category and vendor figures use expense-register "
    "amounts before GST and are not added again to ledger-based "
    "P&L expenses."
)


# ============================================================
# DATA VALIDATION SUMMARY
# ============================================================

st.divider()
st.subheader("Financial Data Validation")

total_revenue = float(monthly["revenue"].sum())
total_expenses = float(monthly["expenses"].sum())
total_profit = float(monthly["net_profit"].sum())

validation = pd.DataFrame({
    "Metric": [
        "Overall Revenue",
        "Overall Expenses",
        "Overall Net Profit",
        "Number of Reporting Periods"
    ],
    "Verified Value": [
        format_currency(total_revenue),
        format_currency(total_expenses),
        format_currency(total_profit),
        len(monthly)
    ]
})

st.dataframe(
    validation,
    hide_index=True,
    use_container_width=True
)

st.caption(
    "Monthly financial totals are aggregated from detail-level "
    "ledger accounts. Expense-register amounts are presented "
    "separately to avoid double counting."
)
