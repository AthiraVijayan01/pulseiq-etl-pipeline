# C01 Payroll-to-Ledger Reconciliation Investigation

## Investigation
- Payroll run: PR-2026-06
- Journal entry: JE-002094
- Affected account: 5001 — Salaries & Wages
- Affected department: D01

## Results
- Payroll employer cost: INR 54,664,233.35
- Ledger salary-related expense: INR 54,682,683.35
- Ledger exceeds payroll by: INR 18,450.00
- Journal debits: INR 54,682,683.35
- Journal credits: INR 54,682,683.35
- Journal balance difference: INR 0.00
- D01 payroll earned fixed pay: INR 19,873,074.18
- D01 ledger salaries: INR 19,891,524.18

## Conclusion
The journal is balanced, but the payroll-to-ledger reconciliation fails.
The INR 18,450.00 variance is isolated to account 5001 in department D01.
The underlying cause has not been confirmed.

## Action
Keep DQ-C01 as FAIL until the variance is explained by the data owner.
Do not modify official staging data or create an unsupported adjustment.
