
from pathlib import Path
from datetime import datetime
import argparse
import calendar

import pandas as pd

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "clean"
OUTPUT = ROOT / "reports" / "monthly"

MIN_GROUP_SIZE = 5

FONT_DIR = Path("C:/Windows/Fonts")
REGULAR_FONT = FONT_DIR / "arial.ttf"
BOLD_FONT = FONT_DIR / "arialbd.ttf"


def register_pdf_fonts():
    if not REGULAR_FONT.exists():
        raise FileNotFoundError(
            f"Arial regular font not found: {REGULAR_FONT}"
        )

    if not BOLD_FONT.exists():
        raise FileNotFoundError(
            f"Arial bold font not found: {BOLD_FONT}"
        )

    if "Arial" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(
            TTFont("Arial", str(REGULAR_FONT))
        )

    if "Arial-Bold" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(
            TTFont("Arial-Bold", str(BOLD_FONT))
        )


def configure_styles():
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName="Arial-Bold",
            alignment=TA_CENTER,
            textColor=colors.HexColor("#23395B"),
            fontSize=22,
            leading=28,
            spaceAfter=10,
        )
    )

    for style_name in [
        "Normal",
        "Heading1",
        "Heading2",
        "Heading3",
        "Title",
    ]:
        styles[style_name].fontName = "Arial"

    for style_name in [
        "Heading1",
        "Heading2",
        "Heading3",
        "Title",
    ]:
        styles[style_name].fontName = "Arial-Bold"

    return styles


def load_csv(filename, required=True):
    path = CLEAN / filename

    if not path.exists():
        if required:
            raise FileNotFoundError(
                f"Required data file not found: {path}"
            )
        return pd.DataFrame()

    return pd.read_csv(path)


def normalize_code(series):
    return (
        series.astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )


def month_filter(data, column, month):
    if data.empty or column not in data.columns:
        return data.copy()

    result = data.copy()
    dates = pd.to_datetime(
        result[column],
        errors="coerce"
    )

    return result[
        dates.dt.strftime("%Y-%m") == month
    ].copy()


def money(value):
    try:
        if pd.isna(value):
            return "₹0.00"

        return f"₹{float(value):,.2f}"

    except (ValueError, TypeError):
        return "₹0.00"


def number(value):
    try:
        if pd.isna(value):
            return "0"

        return f"{float(value):,.2f}"

    except (ValueError, TypeError):
        return "0"


def safe_sum(data, column):
    if data.empty or column not in data.columns:
        return 0.0

    return pd.to_numeric(
        data[column],
        errors="coerce"
    ).fillna(0).sum()


def latest_date(data, column):
    if data.empty or column not in data.columns:
        return "Not available"

    dates = pd.to_datetime(
        data[column],
        errors="coerce"
    ).dropna()

    if dates.empty:
        return "Not available"

    return dates.max().strftime("%Y-%m-%d")


def calculate_profit_loss(month):
    ledger = load_csv("fact_ledger.csv")
    accounts = load_csv("dim_account.csv")

    required_ledger = {
        "account_code",
        "posting_period",
        "signed_amount_debit_positive",
    }

    required_accounts = {
        "account_code",
        "account_name",
        "account_type",
        "statement",
        "is_group",
    }

    if not required_ledger.issubset(ledger.columns):
        raise ValueError(
            "fact_ledger.csv is missing required columns."
        )

    if not required_accounts.issubset(accounts.columns):
        raise ValueError(
            "dim_account.csv is missing required columns."
        )

    ledger["account_code"] = normalize_code(
        ledger["account_code"]
    )

    accounts["account_code"] = normalize_code(
        accounts["account_code"]
    )

    ledger = month_filter(
        ledger,
        "posting_period",
        month
    )

    if "source_type" in ledger.columns:
        ledger = ledger[
            ledger["source_type"]
            .astype(str)
            .str.upper()
            .str.strip() != "OPENING"
        ].copy()

    merged = ledger.merge(
        accounts[
            [
                "account_code",
                "account_name",
                "account_type",
                "statement",
                "is_group",
            ]
        ],
        on="account_code",
        how="left",
    )

    merged = merged[
        merged["statement"]
        .astype(str)
        .str.strip() == "Profit & Loss"
    ].copy()

    group_values = (
        merged["is_group"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    merged = merged[
        ~group_values.isin(["Y", "YES", "TRUE", "1"])
    ].copy()

    merged["signed_amount_debit_positive"] = pd.to_numeric(
        merged["signed_amount_debit_positive"],
        errors="coerce"
    ).fillna(0)

    account_types = (
        merged["account_type"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    income = merged[account_types == "INCOME"]
    expenses = merged[account_types == "EXPENSE"]

    revenue = -safe_sum(
        income,
        "signed_amount_debit_positive"
    )

    expense_total = safe_sum(
        expenses,
        "signed_amount_debit_positive"
    )

    net_profit = revenue - expense_total

    margin = (
        net_profit / revenue * 100
        if revenue else 0
    )

    account_summary = (
        merged.groupby(
            [
                "account_code",
                "account_name",
                "account_type",
            ],
            dropna=False
        )["signed_amount_debit_positive"]
        .sum()
        .reset_index()
    )

    account_summary["amount"] = account_summary.apply(
        lambda row: (
            -row["signed_amount_debit_positive"]
            if str(row["account_type"]).strip().upper()
            == "INCOME"
            else row["signed_amount_debit_positive"]
        ),
        axis=1
    )

    account_summary = account_summary[
        [
            "account_code",
            "account_name",
            "account_type",
            "amount",
        ]
    ]

    return {
        "revenue": revenue,
        "expenses": expense_total,
        "profit": net_profit,
        "margin": margin,
        "accounts": account_summary,
        "ledger_rows": len(ledger),
    }


def calculate_expenses(month):
    data = load_csv("fact_expense.csv")

    required = {
        "expense_date",
        "expense_id",
        "category_account",
        "amount_excl_gst",
        "total_amount",
    }

    if not required.issubset(data.columns):
        raise ValueError(
            "fact_expense.csv is missing required columns."
        )

    data = month_filter(
        data,
        "expense_date",
        month
    )

    if data.empty:
        return data

    data["category_account"] = normalize_code(
        data["category_account"]
    )

    data["amount_excl_gst"] = pd.to_numeric(
        data["amount_excl_gst"],
        errors="coerce"
    ).fillna(0)

    data["total_amount"] = pd.to_numeric(
        data["total_amount"],
        errors="coerce"
    ).fillna(0)

    summary = (
        data.groupby(
            "category_account",
            dropna=False
        )
        .agg(
            expense_count=("expense_id", "count"),
            amount_excl_gst=("amount_excl_gst", "sum"),
            total_amount=("total_amount", "sum"),
        )
        .reset_index()
        .sort_values(
            "total_amount",
            ascending=False
        )
    )

    return summary


def calculate_receivables_and_cash(month):
    invoices = load_csv("fact_invoice.csv")
    payments = load_csv("fact_invoice_payment.csv")

    required_invoice_columns = {
        "balance_due",
        "invoice_date",
    }

    if not required_invoice_columns.issubset(invoices.columns):
        raise ValueError(
            "fact_invoice.csv is missing required columns."
        )

    if not {"payment_date", "amount"}.issubset(payments.columns):
        raise ValueError(
            "fact_invoice_payment.csv is missing required columns."
        )

    invoices["balance_due"] = pd.to_numeric(
        invoices["balance_due"],
        errors="coerce"
    ).fillna(0)

    open_invoices = invoices[
        invoices["balance_due"] > 0
    ].copy()

    payments_month = month_filter(
        payments,
        "payment_date",
        month
    )

    collected = safe_sum(
        payments_month,
        "amount"
    )

    receivables = safe_sum(
        open_invoices,
        "balance_due"
    )

    overdue = pd.DataFrame()

    if "days_past_due_at_cutoff" in open_invoices.columns:
        open_invoices["days_past_due_at_cutoff"] = pd.to_numeric(
            open_invoices["days_past_due_at_cutoff"],
            errors="coerce"
        ).fillna(0)

        overdue = open_invoices[
            open_invoices["days_past_due_at_cutoff"] > 0
        ].copy()

    overdue_amount = safe_sum(
        overdue,
        "balance_due"
    )

    return {
        "receivables": receivables,
        "open_invoice_count": len(open_invoices),
        "overdue_amount": overdue_amount,
        "monthly_collections": collected,
        "payments": payments_month,
        "snapshot_invoices": invoices,
        "latest_invoice_date": latest_date(
            invoices,
            "invoice_date"
        ),
        "latest_payment_date": latest_date(
            payments_month,
            "payment_date"
        ),
    }


def calculate_departments(month):
    path = (
        ROOT / "outputs" / "task13_department_month.csv"
    )

    if not path.exists():
        return pd.DataFrame()

    data = pd.read_csv(path)

    required = {
        "month",
        "department_id",
        "headcount_end",
        "employer_cost",
    }

    if not required.issubset(data.columns):
        raise ValueError(
            "Task 13 department output is missing required columns."
        )

    data = month_filter(
        data,
        "month",
        month
    )

    if data.empty:
        return data

    data["department_id"] = (
        data["department_id"]
        .astype(str)
        .str.strip()
    )

    data["headcount_end"] = pd.to_numeric(
        data["headcount_end"],
        errors="coerce"
    )

    data = data[
        data["headcount_end"] >= MIN_GROUP_SIZE
    ].copy()

    if data.empty:
        return data

    numeric_columns = [
        "employer_cost",
        "overtime_cost",
        "attendance_rate_pct",
        "approved_leave_days",
        "exits",
    ]

    for column in numeric_columns:
        if column in data.columns:
            data[column] = pd.to_numeric(
                data[column],
                errors="coerce"
            ).fillna(0)

    return data.sort_values(
        "employer_cost",
        ascending=False
    )


def calculate_ai_signals(month, departments):
    anomalies = load_csv(
        "fact_anomaly.csv",
        required=False
    )

    forecasts = load_csv(
        "fact_forecast.csv",
        required=False
    )

    if not anomalies.empty:
        if "period" not in anomalies.columns:
            anomalies = pd.DataFrame()
        else:
            anomalies = month_filter(
                anomalies,
                "period",
                month
            )

    if not forecasts.empty:
        if not {
            "forecast_month",
            "department_id",
        }.issubset(forecasts.columns):
            forecasts = pd.DataFrame()
        else:
            forecast_dates = pd.to_datetime(
                forecasts["forecast_month"],
                errors="coerce"
            )

            selected = pd.Period(
                month,
                freq="M"
            )

            forecasts = forecasts[
                forecast_dates.dt.to_period("M") > selected
            ].copy()

            forecasts["department_id"] = (
                forecasts["department_id"]
                .astype(str)
                .str.strip()
            )

            if not departments.empty:
                eligible_ids = set(
                    departments["department_id"]
                    .astype(str)
                    .str.strip()
                )
            else:
                eligible_ids = set()

            forecasts = forecasts[
                (
                    forecasts["department_id"] == "ALL"
                )
                | (
                    forecasts["department_id"].isin(
                        eligible_ids
                    )
                )
            ].copy()

    flagged = 0
    money_at_risk = 0.0

    if not anomalies.empty:
        if "department_id" in anomalies.columns:
            anomalies["department_id"] = (
                anomalies["department_id"]
                .astype(str)
                .str.strip()
            )

            if not departments.empty:
                eligible_ids = set(
                    departments["department_id"]
                    .astype(str)
                    .str.strip()
                )
            else:
                eligible_ids = set()

            anomalies = anomalies[
                (
                    anomalies["department_id"] == "ALL"
                )
                | (
                    anomalies["department_id"].isin(
                        eligible_ids
                    )
                )
            ].copy()
        else:
            anomalies = pd.DataFrame()

    if not anomalies.empty:
        if "flagged" in anomalies.columns:
            flagged = int(
                anomalies["flagged"]
                .astype(str)
                .str.upper()
                .isin(["Y", "YES", "TRUE", "1"])
                .sum()
            )

        money_at_risk = safe_sum(
            anomalies,
            "money_at_risk"
        )

    return {
        "anomalies": anomalies,
        "forecasts": forecasts,
        "flagged": flagged,
        "money_at_risk": money_at_risk,
    }


def make_table(rows, widths=None, font_size=8):
    table = Table(
        rows,
        colWidths=widths,
        repeatRows=1,
        hAlign="LEFT"
    )

    table.setStyle(TableStyle([
        (
            "BACKGROUND",
            (0, 0),
            (-1, 0),
            colors.HexColor("#23395B")
        ),
        (
            "TEXTCOLOR",
            (0, 0),
            (-1, 0),
            colors.white
        ),
        (
            "FONTNAME",
            (0, 0),
            (-1, 0),
            "Arial-Bold"
        ),
        (
            "FONTNAME",
            (0, 1),
            (-1, -1),
            "Arial"
        ),
        (
            "FONTSIZE",
            (0, 0),
            (-1, -1),
            font_size
        ),
        (
            "GRID",
            (0, 0),
            (-1, -1),
            0.35,
            colors.HexColor("#D5DCE5")
        ),
        (
            "ROWBACKGROUNDS",
            (0, 1),
            (-1, -1),
            [
                colors.white,
                colors.HexColor("#F1F4F8")
            ]
        ),
        (
            "VALIGN",
            (0, 0),
            (-1, -1),
            "MIDDLE"
        ),
        (
            "LEFTPADDING",
            (0, 0),
            (-1, -1),
            6
        ),
        (
            "RIGHTPADDING",
            (0, 0),
            (-1, -1),
            6
        ),
        (
            "TOPPADDING",
            (0, 0),
            (-1, -1),
            5
        ),
        (
            "BOTTOMPADDING",
            (0, 0),
            (-1, -1),
            5
        ),
    ]))

    return table


def add_section(story, styles, heading, description=None):
    story.append(
        Paragraph(heading, styles["Heading2"])
    )

    if description:
        story.append(
            Paragraph(
                description,
                styles["Normal"]
            )
        )

    story.append(Spacer(1, 5 * mm))


def build_pdf(month):
    try:
        period = pd.Period(month, freq="M")

        if str(period) != month:
            raise ValueError()

    except Exception as exc:
        raise ValueError(
            "Month must use YYYY-MM format, for example 2026-09."
        ) from exc

    register_pdf_fonts()
    styles = configure_styles()

    month_start = period.start_time.date()
    month_end = period.end_time.date()
    month_label = calendar.month_name[period.month]

    print(f"Building PulseIQ report for {month}...")

    pnl = calculate_profit_loss(month)
    expenses = calculate_expenses(month)
    cash = calculate_receivables_and_cash(month)
    departments = calculate_departments(month)

    ai = calculate_ai_signals(
        month,
        departments
    )

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path = (
        OUTPUT / f"PulseIQ_Report_{month}.pdf"
    )

    page_size = landscape(A4)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=page_size,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"PulseIQ Monthly Report - {month}",
        author="PulseIQ Analytics",
    )

    story = []

    story.append(Spacer(1, 15 * mm))

    story.append(
        Paragraph(
            "PULSEIQ MONTHLY MANAGEMENT REPORT",
            styles["ReportTitle"]
        )
    )

    story.append(
        Paragraph(
            f"{month_label} {period.year}",
            styles["Heading1"]
        )
    )

    story.append(Spacer(1, 8 * mm))

    metadata = [
        ["Reporting period", f"{month_start} to {month_end}"],
        ["Data cut-off", f"Period-based metrics: {month_end}"],
        ["Latest invoice date in source", cash["latest_invoice_date"]],
        ["Latest payment date in selected month", cash["latest_payment_date"]],
        ["Report generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        [
            "Receivables basis",
            "Invoice balances supplied in fact_invoice.csv; "
            "source snapshot date not independently available"
        ],
        [
            "Department privacy",
            f"Departments with headcount below {MIN_GROUP_SIZE} suppressed"
        ],
    ]

    story.append(
        make_table(
            [["Report information", "Value"]] + metadata,
            widths=[65 * mm, 180 * mm]
        )
    )

    story.append(Spacer(1, 12 * mm))

    story.append(
        Paragraph(
            "This report is generated from the available "
            "PulseIQ clean datasets and monthly department "
            "analysis output. Reporting-period metrics, "
            "invoice balances and payment collections are "
            "presented with their respective source-date "
            "limitations.",
            styles["Normal"]
        )
    )

    story.append(PageBreak())

    add_section(
        story,
        styles,
        "1. Monthly Profit and Loss",
        "Ledger-based figures for the selected posting "
        "period. Opening entries and group accounts are excluded."
    )

    pnl_rows = [
        ["Metric", "Amount"],
        ["Revenue", money(pnl["revenue"])],
        ["Expenses", money(pnl["expenses"])],
        ["Net profit", money(pnl["profit"])],
        ["Net profit margin", f'{pnl["margin"]:.2f}%'],
        ["Ledger rows in period", str(pnl["ledger_rows"])],
    ]

    story.append(
        make_table(
            pnl_rows,
            widths=[100 * mm, 70 * mm]
        )
    )

    if not pnl["accounts"].empty:
        story.append(Spacer(1, 8 * mm))

        story.append(
            Paragraph(
                "Account-level breakdown",
                styles["Heading3"]
            )
        )

        rows = [[
            "Account",
            "Account name",
            "Type",
            "Amount"
        ]]

        for _, row in pnl["accounts"].iterrows():
            rows.append([
                str(row["account_code"]),
                str(row["account_name"]),
                str(row["account_type"]),
                money(row["amount"]),
            ])

        story.append(make_table(rows))

    story.append(PageBreak())

    add_section(
        story,
        styles,
        "2. Expense Analysis",
        "Expense register totals for the selected month. "
        "Amounts are grouped by category account."
    )

    if expenses.empty:
        story.append(
            Paragraph(
                "No expense records were found for this month.",
                styles["Normal"]
            )
        )
    else:
        rows = [[
            "Category account",
            "Expense count",
            "Amount excluding GST",
            "Total including GST"
        ]]

        for _, row in expenses.iterrows():
            rows.append([
                str(row["category_account"]),
                str(int(row["expense_count"])),
                money(row["amount_excl_gst"]),
                money(row["total_amount"]),
            ])

        story.append(
            make_table(
                rows,
                widths=[
                    45 * mm,
                    35 * mm,
                    65 * mm,
                    65 * mm
                ]
            )
        )

    story.append(PageBreak())

    add_section(
        story,
        styles,
        "3. Receivables and Cash Collection",
        "Collections are payments recorded during the "
        "selected month. Outstanding and overdue balances "
        "use the invoice balances supplied in the source dataset."
    )

    cash_rows = [
        ["Metric", "Value"],
        ["Outstanding receivables", money(cash["receivables"])],
        ["Open invoice count", str(cash["open_invoice_count"])],
        ["Overdue receivables", money(cash["overdue_amount"])],
        [
            "Payments collected during selected month",
            money(cash["monthly_collections"])
        ],
        ["Latest invoice date in source", cash["latest_invoice_date"]],
        ["Latest payment date in selected month", cash["latest_payment_date"]],
    ]

    story.append(
        make_table(
            cash_rows,
            widths=[110 * mm, 90 * mm]
        )
    )

    story.append(PageBreak())

    add_section(
        story,
        styles,
        "4. Department Workforce and Cost",
        f"Departments with fewer than {MIN_GROUP_SIZE} "
        "employees are suppressed. Only eligible aggregate "
        "department-level figures are displayed."
    )

    if departments.empty:
        story.append(
            Paragraph(
                "No eligible department records were found for this month.",
                styles["Normal"]
            )
        )
    else:
        columns = [
            "department_id",
            "headcount_end",
            "employer_cost",
            "overtime_cost",
            "attendance_rate_pct",
            "approved_leave_days",
            "exits",
        ]

        available = [
            column
            for column in columns
            if column in departments.columns
        ]

        labels = {
            "department_id": "Department",
            "headcount_end": "Headcount",
            "employer_cost": "Employer cost",
            "overtime_cost": "Overtime cost",
            "attendance_rate_pct": "Attendance %",
            "approved_leave_days": "Leave days",
            "exits": "Exits",
        }

        rows = [[
            labels[column]
            for column in available
        ]]

        for _, row in departments.iterrows():
            values = []

            for column in available:
                value = row[column]

                if column == "department_id":
                    values.append(str(value))

                elif column in ["employer_cost", "overtime_cost"]:
                    values.append(money(value))

                elif column == "attendance_rate_pct":
                    values.append(f"{float(value):.2f}%")

                elif column in ["headcount_end", "exits"]:
                    values.append(str(int(value)))

                else:
                    values.append(number(value))

            rows.append(values)

        department_widths = [
            25 * mm,
            22 * mm,
            42 * mm,
            38 * mm,
            32 * mm,
            30 * mm,
            20 * mm,
        ]

        story.append(
            make_table(
                rows,
                widths=department_widths[:len(available)],
                font_size=7
            )
        )

        story.append(Spacer(1, 6 * mm))

        story.append(
            Paragraph(
                f"Eligible departments displayed: {len(departments)}",
                styles["Normal"]
            )
        )

    story.append(PageBreak())

    add_section(
        story,
        styles,
        "5. AI Signals and Workforce Forecast",
        "AI-generated signals are indicators for human review, "
        "not confirmed findings or automatic decisions. "
        "Department forecasts for groups below the minimum "
        "group size are suppressed."
    )

    ai_rows = [
        ["Metric", "Value"],
        ["Flagged anomaly records", str(ai["flagged"])],
        ["Recorded money at risk", money(ai["money_at_risk"])],
        ["Eligible future forecast records", str(len(ai["forecasts"]))],
    ]

    story.append(
        make_table(
            ai_rows,
            widths=[100 * mm, 70 * mm]
        )
    )

    if not ai["forecasts"].empty:
        story.append(Spacer(1, 8 * mm))

        story.append(
            Paragraph(
                "Available future forecasts",
                styles["Heading3"]
            )
        )

        forecast_columns = [
            "metric",
            "department_id",
            "forecast_month",
            "forecast_value",
            "lower_80",
            "upper_80",
        ]

        available = [
            column
            for column in forecast_columns
            if column in ai["forecasts"].columns
        ]

        rows = [[
            column.replace("_", " ").title()
            for column in available
        ]]

        for _, row in ai["forecasts"].head(20).iterrows():
            rows.append([
                str(row[column])
                for column in available
            ])

        story.append(
            make_table(
                rows,
                font_size=7
            )
        )

        if len(ai["forecasts"]) > 20:
            story.append(Spacer(1, 4 * mm))

            story.append(
                Paragraph(
                    f"Showing 20 of {len(ai['forecasts'])} "
                    "eligible forecast records.",
                    styles["Normal"]
                )
            )

    else:
        story.append(Spacer(1, 5 * mm))

        story.append(
            Paragraph(
                "No eligible future forecast records were found.",
                styles["Normal"]
            )
        )

    story.append(Spacer(1, 8 * mm))

    story.append(
        Paragraph(
            "Interpretation: anomaly flags and forecasts should "
            "be reviewed alongside source records, business "
            "context and data quality checks before management action.",
            styles["Normal"]
        )
    )

    def add_footer(canvas, document):
        canvas.saveState()

        canvas.setFont("Arial", 8)
        canvas.setFillColor(
            colors.HexColor("#667085")
        )

        canvas.drawString(
            15 * mm,
            8 * mm,
            "PulseIQ | Confidential management report"
        )

        canvas.drawRightString(
            page_size[0] - 15 * mm,
            8 * mm,
            f"Page {document.page}"
        )

        canvas.restoreState()

    doc.build(
        story,
        onFirstPage=add_footer,
        onLaterPages=add_footer
    )

    print("\nReport generated successfully:")
    print(output_path)
    print(f"Reporting period: {month_start} to {month_end}")
    print(f"Eligible departments: {len(departments)}")
    print(f"Eligible forecasts: {len(ai['forecasts'])}")
    print(f"PDF size: {output_path.stat().st_size:,} bytes")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate a PulseIQ monthly management PDF."
    )

    parser.add_argument(
        "--month",
        required=True,
        help="Reporting month in YYYY-MM format, e.g. 2026-09"
    )

    args = parser.parse_args()

    build_pdf(args.month)


if __name__ == "__main__":
    main()
