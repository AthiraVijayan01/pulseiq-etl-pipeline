
-- ============================================================
-- PULSEIQ PHASE 3 - TASK 11
-- FINANCIAL ANALYTICS SQL VIEWS
-- ============================================================

CREATE SCHEMA IF NOT EXISTS phase3;


-- ============================================================
-- VIEW 1: MONTHLY P&L ACCOUNT DETAIL
-- ============================================================

CREATE OR REPLACE VIEW phase3.v_pnl_account_monthly AS
SELECT
    l.posting_period,
    a.account_code,
    a.account_name,
    a.account_type,

    SUM(l.debit)::NUMERIC(20, 2) AS total_debit,
    SUM(l.credit)::NUMERIC(20, 2) AS total_credit,

    CASE
        WHEN a.account_type = 'INCOME'
            THEN SUM(l.credit - l.debit)

        WHEN a.account_type = 'EXPENSE'
            THEN SUM(l.debit - l.credit)
    END::NUMERIC(20, 2) AS account_amount

FROM phase3.fact_ledger l

INNER JOIN phase3.dim_account a
    ON l.account_code = a.account_code

WHERE
    a.statement = 'Profit & Loss'
    AND a.is_group = 'N'
    AND a.is_active = 'Y'
    AND a.account_type IN ('INCOME', 'EXPENSE')
    AND l.source_type <> 'OPENING'

GROUP BY
    l.posting_period,
    a.account_code,
    a.account_name,
    a.account_type;


-- ============================================================
-- VIEW 2: MONTHLY PROFIT AND LOSS
-- ============================================================

CREATE OR REPLACE VIEW phase3.v_pnl_monthly AS

WITH monthly AS (
    SELECT
        posting_period,

        SUM(
            CASE
                WHEN account_type = 'INCOME'
                    THEN account_amount
                ELSE 0
            END
        )::NUMERIC(20, 2) AS revenue,

        SUM(
            CASE
                WHEN account_type = 'EXPENSE'
                    THEN account_amount
                ELSE 0
            END
        )::NUMERIC(20, 2) AS expenses

    FROM phase3.v_pnl_account_monthly

    GROUP BY posting_period
)

SELECT
    posting_period,
    revenue,
    expenses,

    (revenue - expenses)::NUMERIC(20, 2) AS net_profit,

    ROUND(
        100.0 * (revenue - expenses)
        / NULLIF(revenue, 0),
        2
    ) AS profit_margin_pct

FROM monthly;


-- ============================================================
-- VIEW 3: EXPENSE CATEGORY ANALYSIS
-- Amounts are before GST.
-- ============================================================

CREATE OR REPLACE VIEW phase3.v_expense_category_monthly AS

SELECT
    TO_CHAR(e.expense_date, 'YYYY-MM') AS expense_month,

    a.account_code,
    a.account_name AS expense_category,

    COUNT(*) AS expense_count,

    SUM(e.amount_excl_gst)::NUMERIC(20, 2)
        AS amount_excl_gst,

    SUM(e.gst_amount)::NUMERIC(20, 2)
        AS gst_amount,

    SUM(e.total_amount)::NUMERIC(20, 2)
        AS total_amount

FROM phase3.fact_expense e

INNER JOIN phase3.dim_account a
    ON e.category_account = a.account_code

WHERE
    a.statement = 'Profit & Loss'
    AND a.account_type = 'EXPENSE'
    AND a.is_group = 'N'
    AND a.is_active = 'Y'

GROUP BY
    TO_CHAR(e.expense_date, 'YYYY-MM'),
    a.account_code,
    a.account_name;


-- ============================================================
-- VIEW 4: VENDOR SPENDING ANALYSIS
-- Amounts are before GST.
-- ============================================================

CREATE OR REPLACE VIEW phase3.v_vendor_spend_monthly AS

SELECT
    TO_CHAR(e.expense_date, 'YYYY-MM') AS expense_month,

    v.vendor_id,
    v.vendor_name,

    COUNT(*) AS expense_count,

    SUM(e.amount_excl_gst)::NUMERIC(20, 2)
        AS amount_excl_gst,

    SUM(e.gst_amount)::NUMERIC(20, 2)
        AS gst_amount,

    SUM(e.total_amount)::NUMERIC(20, 2)
        AS total_amount

FROM phase3.fact_expense e

INNER JOIN phase3.dim_vendor v
    ON e.vendor_id = v.vendor_id

INNER JOIN phase3.dim_account a
    ON e.category_account = a.account_code

WHERE
    a.statement = 'Profit & Loss'
    AND a.account_type = 'EXPENSE'
    AND a.is_group = 'N'
    AND a.is_active = 'Y'

GROUP BY
    TO_CHAR(e.expense_date, 'YYYY-MM'),
    v.vendor_id,
    v.vendor_name;


-- ============================================================
-- END OF TASK 11 FINANCIAL VIEWS
-- ============================================================
