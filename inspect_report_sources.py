from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent

files = [
    "fact_ledger.csv",
    "fact_expense.csv",
    "dim_account.csv",
    "fact_invoice.csv",
    "fact_invoice_payment.csv",
    "dim_client.csv",
    "fact_anomaly.csv",
    "fact_forecast.csv",
    "fact_headcount_monthly.csv",
    "kpi_targets.csv",
]

for filename in files:
    path = ROOT / "clean" / filename
    print(f"\n{'=' * 70}\n{filename}")

    if not path.exists():
        print("NOT FOUND")
        continue

    df = pd.read_csv(path, nrows=2)
    print("Columns:", list(df.columns))
    print("Sample:")
    print(df.head(2).to_string(index=False))

path = ROOT / "outputs" / "task13_department_month.csv"
print(f"\n{'=' * 70}\ntask13_department_month.csv")

if path.exists():
    df = pd.read_csv(path, nrows=2)
    print("Columns:", list(df.columns))
    print(df.head(2).to_string(index=False))
else:
    print("NOT FOUND")
