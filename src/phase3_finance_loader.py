
from pathlib import Path

import pandas as pd

from src.db import database_connection


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"

TABLES = {
    "dim_account": {
        "file": "dim_account.csv",
        "columns": [
            "account_code",
            "account_name",
            "account_type",
            "normal_balance",
            "parent_code",
            "is_group",
            "statement",
            "is_active",
        ],
        "dates": [],
        "integers": ["account_code", "parent_code"],
    },
    "dim_vendor": {
        "file": "dim_vendor.csv",
        "columns": [
            "vendor_id",
            "vendor_name",
            "primary_expense_account",
            "payment_terms_days",
            "city",
            "gst_registration",
            "is_active",
        ],
        "dates": [],
        "integers": ["primary_expense_account", "payment_terms_days"],
    },
    "fact_ledger": {
        "file": "fact_ledger.csv",
        "columns": [
            "line_id",
            "entry_id",
            "date_key",
            "entry_date",
            "posting_period",
            "financial_year",
            "account_code",
            "debit",
            "credit",
            "signed_amount_debit_positive",
            "cost_center_department_id",
            "source_type",
            "source_id",
        ],
        "dates": ["entry_date"],
        "integers": ["date_key", "account_code"],
    },
    "fact_expense": {
        "file": "fact_expense.csv",
        "columns": [
            "expense_id",
            "expense_date",
            "expense_date_key",
            "category_account",
            "vendor_id",
            "bill_reference",
            "description",
            "department_id",
            "amount_excl_gst",
            "gst_rate_percent",
            "gst_amount",
            "total_amount",
            "due_date",
            "paid_date",
            "status",
            "payment_mode",
            "submitted_by",
            "approved_by",
            "ledger_entry_id",
            "payment_ledger_entry_id",
        ],
        "dates": ["expense_date", "due_date", "paid_date"],
        "integers": [
            "expense_date_key",
            "category_account",
            "amount_excl_gst",
            "gst_rate_percent",
        ],
    },
}


DDL = """
CREATE SCHEMA IF NOT EXISTS phase3;

CREATE TABLE IF NOT EXISTS phase3.dim_account (
    account_code INTEGER PRIMARY KEY,
    account_name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    normal_balance TEXT NOT NULL,
    parent_code INTEGER,
    is_group CHAR(1) NOT NULL,
    statement TEXT NOT NULL,
    is_active CHAR(1) NOT NULL
);

CREATE TABLE IF NOT EXISTS phase3.dim_vendor (
    vendor_id TEXT PRIMARY KEY,
    vendor_name TEXT NOT NULL,
    primary_expense_account INTEGER NOT NULL
        REFERENCES phase3.dim_account(account_code),
    payment_terms_days INTEGER,
    city TEXT,
    gst_registration TEXT,
    is_active CHAR(1) NOT NULL
);

CREATE TABLE IF NOT EXISTS phase3.fact_ledger (
    line_id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL,
    date_key INTEGER NOT NULL,
    entry_date DATE NOT NULL,
    posting_period TEXT NOT NULL,
    financial_year TEXT NOT NULL,
    account_code INTEGER NOT NULL
        REFERENCES phase3.dim_account(account_code),
    debit NUMERIC(20, 2) NOT NULL,
    credit NUMERIC(20, 2) NOT NULL,
    signed_amount_debit_positive NUMERIC(20, 2) NOT NULL,
    cost_center_department_id TEXT,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phase3.fact_expense (
    expense_id TEXT PRIMARY KEY,
    expense_date DATE NOT NULL,
    expense_date_key INTEGER NOT NULL,
    category_account INTEGER NOT NULL
        REFERENCES phase3.dim_account(account_code),
    vendor_id TEXT NOT NULL
        REFERENCES phase3.dim_vendor(vendor_id),
    bill_reference TEXT NOT NULL,
    description TEXT,
    department_id TEXT,
    amount_excl_gst NUMERIC(20, 2) NOT NULL,
    gst_rate_percent NUMERIC(8, 2),
    gst_amount NUMERIC(20, 2) NOT NULL,
    total_amount NUMERIC(20, 2) NOT NULL,
    due_date DATE,
    paid_date DATE,
    status TEXT NOT NULL,
    payment_mode TEXT,
    submitted_by TEXT,
    approved_by TEXT,
    ledger_entry_id TEXT NOT NULL,
    payment_ledger_entry_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_phase3_ledger_period
    ON phase3.fact_ledger(posting_period);

CREATE INDEX IF NOT EXISTS idx_phase3_ledger_account
    ON phase3.fact_ledger(account_code);

CREATE INDEX IF NOT EXISTS idx_phase3_expense_date
    ON phase3.fact_expense(expense_date);

CREATE INDEX IF NOT EXISTS idx_phase3_expense_vendor
    ON phase3.fact_expense(vendor_id);
"""


def load_dataframe(table_name, config):
    path = RAW / config["file"]

    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")

    df = pd.read_csv(path)

    expected = config["columns"]
    missing = sorted(set(expected) - set(df.columns))

    if missing:
        raise ValueError(
            f"{table_name}: missing columns: {missing}"
        )

    df = df[expected].copy()

    for column in config["dates"]:
        df[column] = pd.to_datetime(
            df[column], errors="raise"
        ).dt.date

    for column in config["integers"]:
        df[column] = pd.to_numeric(
            df[column], errors="raise"
        ).astype("Int64")

    df = df.astype(object).where(pd.notna(df), None)

    return df


def main():
    dataframes = {}

    print("\nPHASE 3 FINANCE SOURCE CHECK")
    print("=" * 65)

    for table_name, config in TABLES.items():
        df = load_dataframe(table_name, config)
        dataframes[table_name] = df

        print(
            f"{table_name}: {len(df):,} rows, "
            f"{len(df.columns)} columns"
        )

    print("\nLOADING PHASE 3 TABLES")
    print("=" * 65)

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(DDL)

            # Reload only these four Phase 3 tables.
            cursor.execute("""
                TRUNCATE TABLE
                    phase3.fact_expense,
                    phase3.fact_ledger,
                    phase3.dim_vendor,
                    phase3.dim_account
            """)

            load_order = [
                "dim_account",
                "dim_vendor",
                "fact_ledger",
                "fact_expense",
            ]

            for table_name in load_order:
                df = dataframes[table_name]
                columns = TABLES[table_name]["columns"]

                column_sql = ", ".join(
                    f'"{column}"' for column in columns
                )

                copy_sql = (
                    f"COPY phase3.{table_name} "
                    f"({column_sql}) FROM STDIN"
                )

                with cursor.copy(copy_sql) as copy:
                    for row in df.itertuples(
                        index=False, name=None
                    ):
                        copy.write_row(row)

                print(
                    f"LOADED {table_name}: {len(df):,} rows"
                )

            cursor.execute("""
                ANALYZE phase3.dim_account;
                ANALYZE phase3.dim_vendor;
                ANALYZE phase3.fact_ledger;
                ANALYZE phase3.fact_expense;
            """)

        connection.commit()

    print("\nPHASE 3 FINANCE LOAD COMPLETED")


if __name__ == "__main__":
    main()
