from pathlib import Path
import pandas as pd

ROOT = Path(r"D:\pulseiq-etl\raw")

payroll = pd.read_csv(ROOT / "fact_payroll.csv", dtype=str)
ledger = pd.read_csv(ROOT / "fact_ledger.csv", dtype=str)

payroll["month"] = payroll["period_end_date"].str[:7]

for col in ["earned_fixed_pay", "pf_employer"]:
    payroll[col] = pd.to_numeric(
        payroll[col], errors="coerce"
    ).fillna(0)

ledger["month"] = ledger["posting_period"].str[:7]
ledger["account_code"] = ledger["account_code"].str.strip()
ledger["source_type"] = ledger["source_type"].str.strip()
ledger["debit_num"] = pd.to_numeric(
    ledger["debit"], errors="coerce"
).fillna(0)
ledger["credit_num"] = pd.to_numeric(
    ledger["credit"], errors="coerce"
).fillna(0)
ledger["net_amount"] = ledger["debit_num"] - ledger["credit_num"]

cases = [
    ("2025-05", "D08", "5001"),
    ("2025-05", "D08", "5004"),
    ("2025-12", "D09", "5001"),
    ("2025-12", "D09", "5004"),
    ("2026-02", "D02", "5001"),
    ("2026-02", "D02", "5004"),
    ("2026-04", "D01", "5001"),
    ("2026-06", "D01", "5001"),
]

for month, dept, account in cases:
    p = payroll[
        (payroll["month"] == month)
        & (payroll["department_id"] == dept)
    ]

    l = ledger[
        (ledger["month"] == month)
        & (ledger["cost_center_department_id"] == dept)
        & (ledger["account_code"] == account)
        & (ledger["source_type"] == "PAYROLL_RUN")
    ]

    field = "earned_fixed_pay" if account == "5001" else "pf_employer"
    expected = round(p[field].sum(), 2)
    actual = round(l["net_amount"].sum(), 2)

    print(f"\n{'=' * 60}")
    print(f"Month: {month} | Department: {dept} | Account: {account}")
    print(f"Payroll expected: Rs. {expected:,.2f}")
    print(f"Ledger recorded:  Rs. {actual:,.2f}")
    print(f"Difference:       Rs. {expected - actual:,.2f}")
    print(f"Payroll rows: {len(p)} | Ledger lines: {len(l)}")

    columns = [
        "line_id", "entry_id", "entry_date", "account_code",
        "debit", "credit", "cost_center_department_id",
        "source_type", "source_id"
    ]

    if l.empty:
        print("No matching ledger lines found.")
    else:
        print("\nLedger source lines:")
        print(l[columns].to_string(index=False))

print("\nInspection complete. No source files or database rows were modified.")
