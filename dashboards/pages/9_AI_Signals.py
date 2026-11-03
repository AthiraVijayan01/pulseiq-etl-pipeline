from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
MIN_GROUP_SIZE = 5
HUMAN_REVIEW_LABEL = "AI-generated, for human review"


st.set_page_config(
    page_title="AI Signals",
    page_icon="🤖",
    layout="wide",
)


@st.cache_data
def load_csv(filename):
    for folder in ("clean", "raw"):
        path = ROOT / folder / filename
        if path.exists():
            return pd.read_csv(path)

    raise FileNotFoundError(
        f"{filename} was not found in the clean/ or raw/ directory."
    )


def money(value):
    return f"₹{value:,.2f}"


def percent(value):
    return f"{value:.2f}%"


def add_ai_label():
    st.caption(HUMAN_REVIEW_LABEL)


def build_actual_values(headcount, metric, department):
    data = headcount.copy()
    data["month_start_date"] = pd.to_datetime(
        data["month_start_date"], errors="coerce"
    )

    if department != "ALL":
        data = data[data["department_id"] == department]

    if metric == "headcount_end":
        actuals = (
            data.groupby("month_start_date", as_index=False)
            ["headcount_end"]
            .sum()
            .rename(columns={"headcount_end": "actual_value"})
        )
        return actuals

    if metric == "attrition_rate_monthly_pct":
        actuals = (
            data.groupby("month_start_date", as_index=False)
            .agg(
                exits=("exits", "sum"),
                headcount_start=("headcount_start", "sum"),
            )
        )

        actuals["actual_value"] = (
            actuals["exits"]
            .div(actuals["headcount_start"].replace(0, pd.NA))
            .mul(100)
        )

        return actuals[["month_start_date", "actual_value"]]

    return pd.DataFrame(
        columns=["month_start_date", "actual_value"]
    )


def build_forecast_error_table(forecast, headcount):
    records = []

    for _, row in forecast.iterrows():
        metric = row["metric"]
        department = row["department_id"]

        actuals = build_actual_values(
            headcount,
            metric,
            department,
        )

        forecast_month = pd.to_datetime(
            row["forecast_month"], errors="coerce"
        )

        match = actuals[
            actuals["month_start_date"] == forecast_month
        ]

        actual_value = (
            float(match.iloc[0]["actual_value"])
            if not match.empty
            and pd.notna(match.iloc[0]["actual_value"])
            else None
        )

        forecast_value = float(row["forecast_value"])

        if actual_value is None:
            absolute_error = None
            percentage_error = None
            status = "Awaiting actual"
        else:
            absolute_error = abs(forecast_value - actual_value)

            percentage_error = (
                absolute_error / abs(actual_value) * 100
                if actual_value != 0
                else None
            )

            status = "Actual available"

        records.append({
            "forecast_id": row["forecast_id"],
            "metric": metric,
            "department_id": department,
            "forecast_month": forecast_month,
            "forecast_value": forecast_value,
            "actual_value": actual_value,
            "absolute_error": absolute_error,
            "absolute_percentage_error": percentage_error,
            "status": status,
        })

    return pd.DataFrame(records)


def build_forecast_chart(forecast, headcount, metric, department):
    selected = forecast[
        (forecast["metric"] == metric)
        & (forecast["department_id"] == department)
    ].copy()

    selected["forecast_month"] = pd.to_datetime(
        selected["forecast_month"], errors="coerce"
    )
    selected = selected.sort_values("forecast_month")

    actuals = build_actual_values(
        headcount,
        metric,
        department,
    )

    actuals = actuals.sort_values("month_start_date").tail(18)

    figure = go.Figure()

    if not actuals.empty:
        figure.add_trace(
            go.Scatter(
                x=actuals["month_start_date"],
                y=actuals["actual_value"],
                mode="lines+markers",
                name="Historical actual",
                line={"width": 2},
            )
        )

    figure.add_trace(
        go.Scatter(
            x=selected["forecast_month"],
            y=selected["lower_80"],
            mode="lines",
            line={"width": 0},
            name="Lower 80% bound",
            showlegend=False,
            hovertemplate=(
                "Month: %{x|%b %Y}<br>"
                "Lower bound: %{y:,.2f}<extra></extra>"
            ),
        )
    )

    figure.add_trace(
        go.Scatter(
            x=selected["forecast_month"],
            y=selected["upper_80"],
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor="rgba(99, 110, 250, 0.18)",
            name="80% confidence range",
            hovertemplate=(
                "Month: %{x|%b %Y}<br>"
                "Upper bound: %{y:,.2f}<extra></extra>"
            ),
        )
    )

    figure.add_trace(
        go.Scatter(
            x=selected["forecast_month"],
            y=selected["forecast_value"],
            mode="lines+markers",
            name="Forecast",
            line={"width": 3, "dash": "dash"},
            hovertemplate=(
                "Month: %{x|%b %Y}<br>"
                "Forecast: %{y:,.2f}<extra></extra>"
            ),
        )
    )

    figure.update_layout(
        xaxis_title="Month",
        yaxis_title=(
            "Employees"
            if metric == "headcount_end"
            else "Attrition rate (%)"
        ),
        hovermode="x unified",
        legend_title_text="Series",
        margin={"l": 10, "r": 10, "t": 35, "b": 10},
    )

    return figure, selected


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

st.title("AI Signals Dashboard")
st.caption(
    "Anomaly monitoring, workforce forecasts and attrition-risk signals."
)

try:
    anomaly = load_csv("fact_anomaly.csv")
    forecast = load_csv("fact_forecast.csv")
    risk = load_csv("fact_attrition_risk.csv")
    headcount = load_csv("fact_headcount_monthly.csv")

except Exception as exc:
    st.error(f"Unable to load Task 14 source data: {exc}")
    st.stop()


# --------------------------------------------------
# PREPARE DATA
# --------------------------------------------------

anomaly["anomaly_score"] = pd.to_numeric(
    anomaly["anomaly_score"], errors="coerce"
)
anomaly["money_at_risk"] = pd.to_numeric(
    anomaly["money_at_risk"], errors="coerce"
)
anomaly["period"] = pd.to_datetime(
    anomaly["period"], errors="coerce"
)

forecast["forecast_value"] = pd.to_numeric(
    forecast["forecast_value"], errors="coerce"
)
forecast["lower_80"] = pd.to_numeric(
    forecast["lower_80"], errors="coerce"
)
forecast["upper_80"] = pd.to_numeric(
    forecast["upper_80"], errors="coerce"
)

risk["risk_score_12m"] = pd.to_numeric(
    risk["risk_score_12m"], errors="coerce"
)
risk["as_of_date"] = pd.to_datetime(
    risk["as_of_date"], errors="coerce"
)

headcount["month_start_date"] = pd.to_datetime(
    headcount["month_start_date"], errors="coerce"
)

headcount["headcount_start"] = pd.to_numeric(
    headcount["headcount_start"], errors="coerce"
)
headcount["headcount_end"] = pd.to_numeric(
    headcount["headcount_end"], errors="coerce"
)
headcount["exits"] = pd.to_numeric(
    headcount["exits"], errors="coerce"
)

flagged = anomaly[
    anomaly["flagged"].astype(str).str.upper() == "Y"
].copy()

financial_anomalies = flagged[
    flagged["money_at_risk"].notna()
].copy()

nonfinancial_anomalies = flagged[
    flagged["money_at_risk"].isna()
].copy()

risk_latest_date = risk["as_of_date"].max()

latest_risk = risk[
    risk["as_of_date"] == risk_latest_date
].copy()

forecast_errors = build_forecast_error_table(
    forecast,
    headcount,
)


# --------------------------------------------------
# OVERVIEW
# --------------------------------------------------

st.subheader("Signal Overview")

total_exposure = financial_anomalies["money_at_risk"].sum()
unique_anomaly_types = flagged["reason_code"].nunique()
high_risk_count = (
    latest_risk["risk_band"].astype(str).str.lower() == "high"
).sum()
medium_risk_count = (
    latest_risk["risk_band"].astype(str).str.lower() == "medium"
).sum()

c1, c2, c3, c4 = st.columns(4)

c1.metric("Flagged Anomaly Records", f"{len(flagged):,}")
c2.metric("Recorded Money at Risk", money(total_exposure))
c3.metric("Latest High-Risk Signals", f"{high_risk_count:,}")
c4.metric("Forecast Records", f"{len(forecast):,}")

st.caption(
    f"{len(financial_anomalies):,} anomaly records contain a monetary "
    f"value; {len(nonfinancial_anomalies):,} do not. "
    "Money at risk is a model-associated exposure estimate, not a "
    "confirmed loss."
)


# --------------------------------------------------
# SECTION 1: ANOMALY SIGNALS
# --------------------------------------------------

st.divider()
st.header("1. Anomaly Signals")

st.write(
    "This section groups flagged payroll and attendance records by "
    "anomaly type. Financial exposure is ranked using the available "
    "money-at-risk values. Missing monetary values are not treated as zero."
)

add_ai_label()

anomaly_summary = (
    flagged.groupby("reason_code", dropna=False)
    .agg(
        flagged_records=("result_id", "count"),
        monetary_records=("money_at_risk", "count"),
        money_at_risk=("money_at_risk", "sum"),
        average_anomaly_score=("anomaly_score", "mean"),
    )
    .reset_index()
)

anomaly_summary["money_at_risk"] = (
    anomaly_summary["money_at_risk"].fillna(0)
)

financial_summary = (
    anomaly_summary[
        anomaly_summary["monetary_records"] > 0
    ]
    .sort_values("money_at_risk", ascending=False)
)

left, right = st.columns([1.6, 1])

with left:
    st.subheader("Anomaly Types Ranked by Money at Risk")
    add_ai_label()

    chart = px.bar(
        financial_summary.sort_values(
            "money_at_risk", ascending=True
        ),
        x="money_at_risk",
        y="reason_code",
        orientation="h",
        labels={
            "money_at_risk": "Money at risk (₹)",
            "reason_code": "Anomaly type",
        },
        hover_data={
            "flagged_records": True,
            "monetary_records": True,
            "average_anomaly_score": ":.3f",
            "money_at_risk": ":,.2f",
        },
    )

    chart.update_layout(
        yaxis={"categoryorder": "total ascending"},
        xaxis_title="Recorded exposure (₹)",
        yaxis_title="Anomaly type",
    )

    st.plotly_chart(chart, width="stretch")

    st.caption(
        "Plain-English explanation: longer bars represent anomaly "
        "categories with a larger sum of recorded monetary exposure. "
        "This is a prioritisation signal for investigation, not proof "
        "that the amount was lost."
    )

with right:
    st.subheader("Anomaly Summary")
    st.dataframe(
        anomaly_summary.sort_values(
            "flagged_records", ascending=False
        ).rename(columns={
            "reason_code": "Anomaly type",
            "flagged_records": "Records",
            "monetary_records": "Records with amount",
            "money_at_risk": "Money at risk (₹)",
            "average_anomaly_score": "Average score",
        }),
        hide_index=True,
        width="stretch",
    )

    st.caption(
        "Plain-English explanation: record counts show how often each "
        "signal occurred. The monetary-record count identifies which "
        "categories actually contain a financial exposure value."
    )

st.subheader("Financial and Non-Financial Signals")

m1, m2, m3 = st.columns(3)
m1.metric("Financial Records", f"{len(financial_anomalies):,}")
m2.metric("Without Monetary Value", f"{len(nonfinancial_anomalies):,}")
m3.metric("Anomaly Types", f"{unique_anomaly_types:,}")

st.caption(
    "Non-financial signals include attendance patterns such as "
    "no attendance, long unpaid absence and frequent late arrivals. "
    "They remain visible as operational signals even without a "
    "monetary estimate."
)


# --------------------------------------------------
# SECTION 2: FORECASTS
# --------------------------------------------------

st.divider()
st.header("2. Workforce Forecasts")

st.write(
    "The forecast dataset contains monthly headcount forecasts by "
    "department and an organisation-wide monthly attrition-rate forecast."
)

forecast_metric_labels = {
    "headcount_end": "Ending headcount",
    "attrition_rate_monthly_pct": "Monthly attrition rate",
}

available_metrics = [
    metric for metric in forecast_metric_labels
    if metric in forecast["metric"].unique()
]

selected_metric = st.selectbox(
    "Select forecast metric",
    options=available_metrics,
    format_func=lambda value: forecast_metric_labels[value],
)

metric_forecasts = forecast[
    forecast["metric"] == selected_metric
].copy()

departments = sorted(
    metric_forecasts["department_id"].dropna().unique().tolist()
)

selected_department = st.selectbox(
    "Select department",
    options=departments,
    index=departments.index("ALL") if "ALL" in departments else 0,
)

figure, selected_forecast = build_forecast_chart(
    forecast,
    headcount,
    selected_metric,
    selected_department,
)

st.subheader(
    f"{forecast_metric_labels[selected_metric]} — "
    f"{selected_department}"
)
add_ai_label()
st.plotly_chart(figure, width="stretch")

trained_through = (
    selected_forecast["trained_through"].iloc[0]
    if not selected_forecast.empty
    else "Not available"
)

method = (
    selected_forecast["method"].iloc[0]
    if not selected_forecast.empty
    else "Not available"
)

st.caption(
    f"Plain-English explanation: the solid historical line shows "
    f"recorded values, the dashed line shows the model forecast, and "
    f"the shaded area shows the model's 80% confidence range. "
    f"The model was trained through {trained_through}. "
    f"Method: {method}."
)

forecast_start = pd.to_datetime(
    selected_forecast["forecast_month"]
).min()
forecast_end = pd.to_datetime(
    selected_forecast["forecast_month"]
).max()

st.info(
    f"Forecast horizon: {forecast_start:%b %Y} to "
    f"{forecast_end:%b %Y}. The available actual data ends in "
    f"{headcount['month_start_date'].max():%b %Y}."
)


# --------------------------------------------------
# FORECAST ERROR TABLE
# --------------------------------------------------

st.subheader("Forecast vs Actual — Error Tracking")

st.write(
    "Forecast error is calculated only when an actual value exists "
    "for the same metric, department and month."
)

add_ai_label()

error_available = (
    forecast_errors["status"] == "Actual available"
).sum()
error_pending = (
    forecast_errors["status"] == "Awaiting actual"
).sum()

e1, e2, e3 = st.columns(3)
e1.metric("Forecast Rows", f"{len(forecast_errors):,}")
e2.metric("Actual Available", f"{error_available:,}")
e3.metric("Awaiting Actual", f"{error_pending:,}")

display_errors = forecast_errors.copy()

display_errors["forecast_month"] = (
    display_errors["forecast_month"].dt.strftime("%b %Y")
)

st.dataframe(
    display_errors.rename(columns={
        "forecast_id": "Forecast ID",
        "metric": "Metric",
        "department_id": "Department",
        "forecast_month": "Forecast month",
        "forecast_value": "Forecast value",
        "actual_value": "Actual value",
        "absolute_error": "Absolute error",
        "absolute_percentage_error": "Absolute error (%)",
        "status": "Status",
    }),
    hide_index=True,
    width="stretch",
)

st.download_button(
    label="Download Forecast Error Table (CSV)",
    data=forecast_errors.to_csv(index=False).encode("utf-8"),
    file_name="task14_forecast_error.csv",
    mime="text/csv",
)

if error_available == 0:
    st.warning(
        "No forecast months overlap with the available actual data. "
        "All forecast errors are therefore pending. The actual source "
        "data currently ends in September 2026, while forecasts begin "
        "in October 2026. Recalculate errors after actual results become "
        "available."
    )
else:
    st.caption(
        "Plain-English explanation: absolute error is the absolute "
        "difference between the forecast and actual value. Absolute "
        "percentage error expresses that difference relative to the "
        "actual value."
    )


# --------------------------------------------------
# SECTION 3: ATTRITION RISK
# --------------------------------------------------

st.divider()
st.header("3. Attrition Risk Signals")

st.write(
    "This section summarises the latest available attrition-risk "
    "snapshot. Risk bands are model-generated prioritisation signals "
    "for supportive HR review, not certain outcomes."
)

st.caption(
    f"Latest snapshot: {risk_latest_date:%d %B %Y} | "
    f"Employees in snapshot: {latest_risk['employee_id'].nunique():,}"
)

st.info(
    "The source contains more than one snapshot date. This dashboard "
    "uses only the latest date to avoid combining different prediction "
    "periods. Individual employee risk scores are not displayed."
)

add_ai_label()

risk_counts = (
    latest_risk["risk_band"]
    .value_counts()
    .reindex(["High", "Medium", "Low"], fill_value=0)
    .rename_axis("Risk band")
    .reset_index(name="Employees")
)

r1, r2 = st.columns(2)

with r1:
    st.subheader("Latest Risk Band Distribution")
    add_ai_label()

    risk_chart = px.bar(
        risk_counts,
        x="Risk band",
        y="Employees",
        text="Employees",
        labels={"Employees": "Employees"},
    )

    risk_chart.update_traces(textposition="outside")
    st.plotly_chart(risk_chart, width="stretch")

    st.caption(
        "Plain-English explanation: this chart shows how the latest "
        "prediction snapshot is distributed across the model's High, "
        "Medium and Low bands."
    )

with r2:
    st.subheader("Department-Level Risk Summary")
    add_ai_label()

    department_risk = (
        latest_risk.groupby("department_id")
        .agg(
            employees=("employee_id", "nunique"),
            average_risk=("risk_score_12m", "mean"),
            high_risk=("risk_band", lambda values:
                       (values == "High").sum()),
            medium_risk=("risk_band", lambda values:
                         (values == "Medium").sum()),
        )
        .reset_index()
    )

    department_risk = department_risk[
        department_risk["employees"] >= MIN_GROUP_SIZE
    ].sort_values("average_risk", ascending=False)

    risk_department_chart = px.bar(
        department_risk.sort_values(
            "average_risk", ascending=True
        ),
        x="average_risk",
        y="department_id",
        orientation="h",
        hover_data={
            "employees": True,
            "high_risk": True,
            "medium_risk": True,
            "average_risk": ":.3f",
        },
        labels={
            "average_risk": "Average model risk score",
            "department_id": "Department",
        },
    )

    st.plotly_chart(
        risk_department_chart,
        width="stretch",
    )

    st.caption(
        "Plain-English explanation: departments are ordered by their "
        "average model risk score. Counts are shown for context; this "
        "comparison does not establish that a department caused "
        "employee attrition."
    )

st.subheader("Department Risk Details")

department_display = department_risk.copy()
department_display["average_risk"] = (
    department_display["average_risk"] * 100
)

st.dataframe(
    department_display.rename(columns={
        "department_id": "Department",
        "employees": "Employees in snapshot",
        "average_risk": "Average risk score (%)",
        "high_risk": "High-risk signals",
        "medium_risk": "Medium-risk signals",
    }),
    hide_index=True,
    width="stretch",
)

st.subheader("Common Model-Reported Reasons")

reason_columns = [
    "top_reason_1",
    "top_reason_2",
    "top_reason_3",
]

reason_values = pd.concat(
    [latest_risk[column] for column in reason_columns],
    ignore_index=True,
).dropna()

reason_summary = (
    reason_values.value_counts()
    .head(15)
    .rename_axis("Model-reported reason")
    .reset_index(name="Occurrences")
)

add_ai_label()

reason_chart = px.bar(
    reason_summary.sort_values(
        "Occurrences", ascending=True
    ),
    x="Occurrences",
    y="Model-reported reason",
    orientation="h",
    labels={
        "Occurrences": "Occurrences across reason fields",
        "Model-reported reason": "Reason",
    },
)

st.plotly_chart(reason_chart, width="stretch")

st.caption(
    "Plain-English explanation: the chart counts the reason descriptions "
    "reported in the three explanation fields for the latest snapshot. "
    "A reason's frequency does not prove causation or identify an "
    "individual's intentions."
)


# --------------------------------------------------
# MODEL LIMITATIONS AND GOVERNANCE
# --------------------------------------------------

st.divider()
st.header("Model Limitations and Human Review")

st.markdown(
    """
    - All AI-generated signals are intended to support investigation,
      not replace human judgement.
    - Anomaly scores and money-at-risk values are model outputs and
      require source-record verification.
    - Missing money-at-risk values are treated as unavailable, not zero.
    - Forecast intervals represent the supplied 80% model confidence
      range; they are not guarantees.
    - Forecast accuracy cannot yet be evaluated because the forecast
      period starts after the available actual-data period.
    - Attrition risk bands are baseline model signals, not certain
      predictions about individual employees.
    - HR should use these summaries for supportive investigation and
      should not use model scores alone for employment decisions.
    - Department-level summaries suppress groups smaller than five.
    """
)

st.caption(
    "Source datasets: fact_anomaly.csv, fact_forecast.csv, "
    "fact_attrition_risk.csv and fact_headcount_monthly.csv."
)
