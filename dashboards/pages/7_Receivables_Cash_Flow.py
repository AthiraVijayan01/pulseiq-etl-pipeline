
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
OPEN_STATUSES = ["SENT", "OVERDUE", "PARTIALLY_PAID"]
CASH_ACCOUNT_CODES = [1001, 1002]


st.set_page_config(
    page_title="Receivables & Cash Flow",
    page_icon="💳",
    layout="wide",
)


def load_csv(filename):
    for folder in ("clean", "raw"):
        path = ROOT / folder / filename
        if path.exists():
            return pd.read_csv(path)

    raise FileNotFoundError(
        f"Could not find {filename} in clean or raw directory."
    )


@st.cache_data
def load_data():
    invoice = load_csv("fact_invoice.csv")
    payment = load_csv("fact_invoice_payment.csv")
    client = load_csv("dim_client.csv")
    ledger = load_csv("fact_ledger.csv")
    account = load_csv("dim_account.csv")

    for col in [
        "total_amount",
        "amount_paid",
        "balance_due",
        "days_past_due_at_cutoff",
        "days_to_pay",
    ]:
        invoice[col] = pd.to_numeric(invoice[col], errors="coerce")

    invoice["invoice_date"] = pd.to_datetime(
        invoice["invoice_date"], errors="coerce"
    )
    invoice["due_date"] = pd.to_datetime(
        invoice["due_date"], errors="coerce"
    )
    invoice["last_payment_date"] = pd.to_datetime(
        invoice["last_payment_date"], errors="coerce"
    )

    payment["payment_date"] = pd.to_datetime(
        payment["payment_date"], errors="coerce"
    )
    payment["amount"] = pd.to_numeric(
        payment["amount"], errors="coerce"
    )

    ledger["account_code"] = pd.to_numeric(
        ledger["account_code"], errors="coerce"
    )
    ledger["debit"] = pd.to_numeric(
        ledger["debit"], errors="coerce"
    )
    ledger["credit"] = pd.to_numeric(
        ledger["credit"], errors="coerce"
    )
    ledger["entry_date"] = pd.to_datetime(
        ledger["entry_date"], errors="coerce"
    )

    client["payment_terms_days"] = pd.to_numeric(
        client["payment_terms_days"], errors="coerce"
    )

    return invoice, payment, client, ledger, account


def money(value):
    return f"₹{value:,.2f}"


def prepare_receivables(invoice, client):
    result = invoice.merge(
        client[
            [
                "client_id",
                "client_name",
                "payment_terms_days",
                "payment_behaviour",
            ]
        ],
        on="client_id",
        how="left",
    )

    result["status"] = (
        result["status"].astype(str).str.strip().str.upper()
    )

    result["is_open"] = result["status"].isin(OPEN_STATUSES)

    result["days_past_due_at_cutoff"] = (
        result["days_past_due_at_cutoff"].fillna(0)
    )

    result["ageing_bucket"] = "Not yet due"

    overdue = result["days_past_due_at_cutoff"] > 0

    result.loc[
        overdue & (result["days_past_due_at_cutoff"] <= 30),
        "ageing_bucket",
    ] = "0-30 days"

    result.loc[
        (result["days_past_due_at_cutoff"] > 30)
        & (result["days_past_due_at_cutoff"] <= 60),
        "ageing_bucket",
    ] = "31-60 days"

    result.loc[
        (result["days_past_due_at_cutoff"] > 60)
        & (result["days_past_due_at_cutoff"] <= 90),
        "ageing_bucket",
    ] = "61-90 days"

    result.loc[
        result["days_past_due_at_cutoff"] > 90,
        "ageing_bucket",
    ] = "90+ days"

    return result


def prepare_cash_flow(ledger):
    cash = ledger[
        ledger["account_code"].isin(CASH_ACCOUNT_CODES)
    ].copy()

    cash = cash[
        cash["source_type"].astype(str).str.upper() != "OPENING"
    ].copy()

    cash["cash_in"] = cash["debit"].fillna(0)
    cash["cash_out"] = cash["credit"].fillna(0)

    cash["posting_period"] = cash["entry_date"].dt.to_period(
        "M"
    ).astype(str)

    cash["source_type"] = (
        cash["source_type"].fillna("OTHER").astype(str)
    )

    monthly = (
        cash.groupby("posting_period", as_index=False)
        .agg(
            cash_in=("cash_in", "sum"),
            cash_out=("cash_out", "sum"),
        )
    )

    monthly["net_cash_flow"] = (
        monthly["cash_in"] - monthly["cash_out"]
    )

    return cash, monthly


def prepare_client_payment(invoice, client):
    paid = invoice[
        (invoice["status"] == "PAID")
        & invoice["days_to_pay"].notna()
    ].copy()

    performance = (
        paid.groupby("client_id", as_index=False)
        .agg(
            invoice_count=("invoice_id", "count"),
            average_days_to_pay=("days_to_pay", "mean"),
            median_days_to_pay=("days_to_pay", "median"),
        )
    )

    performance = performance.merge(
        client[
            [
                "client_id",
                "client_name",
                "payment_terms_days",
                "payment_behaviour",
            ]
        ],
        on="client_id",
        how="left",
    )

    performance["days_beyond_terms"] = (
        performance["average_days_to_pay"]
        - performance["payment_terms_days"]
    )

    return performance.sort_values(
        "average_days_to_pay", ascending=False
    )


try:
    invoice, payment, client, ledger, account = load_data()
except Exception as exc:
    st.error(f"Unable to load financial data: {exc}")
    st.stop()


receivables = prepare_receivables(invoice, client)

open_invoices = receivables[
    receivables["is_open"]
].copy()

overdue_invoices = open_invoices[
    open_invoices["days_past_due_at_cutoff"] > 0
].copy()

cash, monthly_cash = prepare_cash_flow(ledger)

client_performance = prepare_client_payment(invoice, client)


st.title("Invoices, Receivables & Cash Flow")

st.caption(
    "Receivables ageing, client payment behaviour, "
    "overdue balances and monthly cash movements."
)

st.info(
    "Open invoice statuses: SENT, OVERDUE and PARTIALLY_PAID. "
    "PAID, CANCELLED and DRAFT invoices are excluded from "
    "open receivables."
)


# ---------------------------------------------------------
# 1. RECEIVABLES OVERVIEW
# ---------------------------------------------------------

st.header("Receivables Overview")

total_open = open_invoices["balance_due"].sum()

overdue_balance = overdue_invoices["balance_due"].sum()

not_due_balance = open_invoices.loc[
    open_invoices["days_past_due_at_cutoff"] <= 0,
    "balance_due",
].sum()

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Open Invoices",
    f"{len(open_invoices):,}",
)

col2.metric(
    "Total Open Receivables",
    money(total_open),
)

col3.metric(
    "Overdue Receivables",
    money(overdue_balance),
)

col4.metric(
    "Not Yet Due",
    money(not_due_balance),
)


status_summary = (
    open_invoices.groupby("status", as_index=False)
    .agg(
        invoice_count=("invoice_id", "count"),
        outstanding_amount=("balance_due", "sum"),
    )
)

st.subheader("Open Invoice Status")

col1, col2 = st.columns([1, 1])

with col1:
    st.dataframe(
        status_summary,
        use_container_width=True,
        hide_index=True,
    )

with col2:
    if not status_summary.empty:
        fig = px.pie(
            status_summary,
            names="status",
            values="outstanding_amount",
            title="Outstanding Amount by Status",
            hole=0.45,
        )
        st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------
# 2. RECEIVABLES AGEING
# ---------------------------------------------------------

st.divider()
st.header("Receivables Ageing")

ageing_order = [
    "Not yet due",
    "0-30 days",
    "31-60 days",
    "61-90 days",
    "90+ days",
]

ageing = (
    open_invoices.groupby("ageing_bucket", as_index=False)
    .agg(
        invoice_count=("invoice_id", "count"),
        outstanding_amount=("balance_due", "sum"),
    )
)

ageing["ageing_bucket"] = pd.Categorical(
    ageing["ageing_bucket"],
    categories=ageing_order,
    ordered=True,
)

ageing = ageing.sort_values("ageing_bucket")

ageing_total = ageing["outstanding_amount"].sum()
ageing_difference = total_open - ageing_total

col1, col2 = st.columns(2)

with col1:
    st.dataframe(
        ageing,
        use_container_width=True,
        hide_index=True,
    )

with col2:
    fig = px.bar(
        ageing,
        x="ageing_bucket",
        y="outstanding_amount",
        color="ageing_bucket",
        text_auto=",.2s",
        title="Outstanding Receivables by Age",
        labels={
            "ageing_bucket": "Ageing Bucket",
            "outstanding_amount": "Outstanding Amount (₹)",
        },
    )
    st.plotly_chart(fig, width="stretch")

st.subheader("Ageing Reconciliation")

r1, r2, r3 = st.columns(3)

r1.metric("Total Open Receivables", money(total_open))
r2.metric("Ageing Bucket Total", money(ageing_total))
r3.metric("Difference", money(ageing_difference))

if abs(ageing_difference) <= 0.01:
    st.success(
        "PASS: Ageing buckets reconcile with total open receivables."
    )
else:
    st.error(
        "FAIL: Ageing bucket totals do not match open receivables."
    )


# ---------------------------------------------------------
# 3. CLIENT PAYMENT PERFORMANCE
# ---------------------------------------------------------

st.divider()
st.header("Client Payment Performance")

st.caption(
    "Average days to pay is calculated from paid invoices "
    "with a recorded days_to_pay value. It is compared "
    "with each client's agreed payment terms."
)

if not client_performance.empty:
    display_performance = client_performance.copy()

    for col in [
        "average_days_to_pay",
        "median_days_to_pay",
        "days_beyond_terms",
    ]:
        display_performance[col] = display_performance[col].round(2)

    st.dataframe(
        display_performance[
            [
                "client_name",
                "invoice_count",
                "average_days_to_pay",
                "median_days_to_pay",
                "payment_terms_days",
                "days_beyond_terms",
                "payment_behaviour",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    top_slow = client_performance.head(10)

    fig = px.bar(
        top_slow,
        x="average_days_to_pay",
        y="client_name",
        orientation="h",
        color="days_beyond_terms",
        title="Top 10 Slow-Paying Clients",
        labels={
            "average_days_to_pay": "Average Days to Pay",
            "client_name": "Client",
            "days_beyond_terms": "Days Beyond Terms",
        },
    )

    fig.update_layout(yaxis={"categoryorder": "total ascending"})

    st.plotly_chart(fig, width="stretch")
else:
    st.info("No paid invoices with payment-duration data were found.")


# ---------------------------------------------------------
# 4. CLIENTS WITH THE MOST OVERDUE MONEY
# ---------------------------------------------------------

st.divider()
st.header("Clients with the Highest Overdue Balances")

if not overdue_invoices.empty:
    overdue_clients = (
        overdue_invoices.groupby(
            ["client_id", "client_name"], as_index=False
        )
        .agg(
            overdue_invoice_count=("invoice_id", "count"),
            overdue_amount=("balance_due", "sum"),
            maximum_days_overdue=(
                "days_past_due_at_cutoff",
                "max",
            ),
        )
        .sort_values("overdue_amount", ascending=False)
        .head(10)
    )

    st.dataframe(
        overdue_clients,
        use_container_width=True,
        hide_index=True,
    )

    fig = px.bar(
        overdue_clients,
        x="overdue_amount",
        y="client_name",
        orientation="h",
        color="maximum_days_overdue",
        title="Top 10 Clients by Overdue Balance",
        labels={
            "overdue_amount": "Overdue Amount (₹)",
            "client_name": "Client",
            "maximum_days_overdue": "Maximum Days Overdue",
        },
    )

    fig.update_layout(yaxis={"categoryorder": "total ascending"})

    st.plotly_chart(fig, width="stretch")
else:
    st.info("No overdue balances were found.")


# ---------------------------------------------------------
# 5. MONTHLY CASH FLOW
# ---------------------------------------------------------

st.divider()
st.header("Monthly Cash In versus Cash Out")

st.caption(
    "Cash in is based on debit entries in bank and cash accounts. "
    "Cash out is based on credit entries. Opening balances are excluded."
)

if not monthly_cash.empty:
    monthly_cash = monthly_cash.sort_values("posting_period")

    fig = px.bar(
        monthly_cash,
        x="posting_period",
        y=["cash_in", "cash_out"],
        barmode="group",
        title="Monthly Cash In and Cash Out",
        labels={
            "posting_period": "Month",
            "value": "Amount (₹)",
            "variable": "Cash Movement",
        },
        color_discrete_map={
            "cash_in": "#2E8B57",
            "cash_out": "#D95F59",
        },
    )

    st.plotly_chart(fig, width="stretch")

    monthly_display = monthly_cash.copy()

    for col in ["cash_in", "cash_out", "net_cash_flow"]:
        monthly_display[col] = monthly_display[col].round(2)

    st.subheader("Monthly Cash Flow Table")

    st.dataframe(
        monthly_display,
        use_container_width=True,
        hide_index=True,
    )

    total_cash_in = cash["cash_in"].sum()
    total_cash_out = cash["cash_out"].sum()

    c1, c2, c3 = st.columns(3)

    c1.metric("Total Cash In", money(total_cash_in))
    c2.metric("Total Cash Out", money(total_cash_out))
    c3.metric(
        "Net Cash Movement",
        money(total_cash_in - total_cash_out),
    )
else:
    st.warning("No bank or cash transactions were found.")


# ---------------------------------------------------------
# 6. PAYMENT REGISTER RECONCILIATION
# ---------------------------------------------------------

st.divider()
st.header("Invoice Payment Reconciliation")

payment_by_invoice = (
    payment.groupby("invoice_id", as_index=False)
    .agg(payment_register_total=("amount", "sum"))
)

payment_check = invoice[
    [
        "invoice_id",
        "invoice_number",
        "amount_paid",
        "balance_due",
        "status",
    ]
].merge(
    payment_by_invoice,
    on="invoice_id",
    how="left",
)

payment_check["payment_register_total"] = (
    payment_check["payment_register_total"].fillna(0)
)

payment_check["difference"] = (
    payment_check["amount_paid"]
    - payment_check["payment_register_total"]
)

exceptions = payment_check[
    payment_check["difference"].abs() > 0.01
].copy()

invoice_paid_total = invoice["amount_paid"].sum()
payment_register_total = payment["amount"].sum()

p1, p2, p3 = st.columns(3)

p1.metric("Invoice Amount Paid", money(invoice_paid_total))
p2.metric("Payment Register Total", money(payment_register_total))
p3.metric(
    "Reconciliation Difference",
    money(invoice_paid_total - payment_register_total),
)

if exceptions.empty:
    st.success("PASS: All invoice payments reconcile.")
else:
    st.warning(
        f"{len(exceptions)} invoice payment reconciliation "
        "exception(s) require investigation."
    )

    st.dataframe(
        exceptions,
        use_container_width=True,
        hide_index=True,
    )


# ---------------------------------------------------------
# 7. DATA DEFINITIONS AND FINDINGS
# ---------------------------------------------------------

st.divider()
st.header("Definitions and Business Observations")

with st.expander("Calculation definitions"):
    st.markdown(
        """
        - **Open invoices:** SENT, OVERDUE and PARTIALLY_PAID.
        - **Closed invoices:** PAID and CANCELLED.
        - **Draft invoices:** Excluded from open receivables.
        - **Ageing:** Based on days past due at the supplied reporting cutoff.
        - **Not yet due:** Invoices with zero or negative days past due.
        - **Average days to pay:** Mean recorded days_to_pay for paid invoices.
        - **Cash in:** Debit movements in bank and cash accounts.
        - **Cash out:** Credit movements in bank and cash accounts.
        - **Opening balances:** Excluded from monthly cash movements.
        """
    )

if not overdue_invoices.empty:
    highest_client = (
        overdue_invoices.groupby("client_name")["balance_due"]
        .sum()
        .sort_values(ascending=False)
    )

    st.markdown(
        f"""
        1. Open receivables total **{money(total_open)}** across
           **{len(open_invoices)} invoices**.

        2. Overdue balances total **{money(overdue_balance)}**.
           The largest overdue client is
           **{highest_client.index[0]}**.

        3. The ageing buckets reconcile to the open receivables
           balance with a difference of **{money(ageing_difference)}**.
        """
    )

st.caption(
    "Financial figures are based on the supplied invoice, payment "
    "and bank/cash ledger records. Reconciliation exceptions are "
    "shown rather than silently adjusted."
)
