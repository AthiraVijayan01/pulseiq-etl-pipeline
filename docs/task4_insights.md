# PulseIQ HR Analytics — Insights Report

## Objective
Analyze employee attendance, leave usage, and payroll consistency using the PulseIQ PostgreSQL warehouse.

## 1. Attendance
- January 2025 contains 8 attendance records.
- 6 records are marked present.
- Average recorded working hours are 6.81.
- Thursday has 4 records with average hours of 5.88.
- Friday has 4 records with average hours of 7.75.
- A three-month rolling average is implemented, but the current result contains only one month.

## 2. Leave Analysis
- The warehouse contains 4 leave events in the current results.
- Annual leave: 2 days in February and 3 days in March.
- Sick leave: 1 day in February.
- Personal leave: 1 day in April.
- These results describe the available sample records, not a full-year workforce trend.

## 3. Payroll Quality
- No payroll rows triggered the tested anomaly rules.
- The checks cover negative pay values, deductions exceeding gross pay, and net-pay calculation mismatches.
- Further reconciliation against source payroll records is recommended.

## 4. Recommendations
- Collect more attendance records across several months before drawing trend conclusions.
- Review attendance hours and weekday differences with the relevant HR team.
- Monitor annual, sick, and personal leave usage over time.
- Continue validating payroll totals against source records.
- Verify dashboard filters and charts before publishing results.

## Limitations
The current warehouse contains a small sample dataset. Late-arrival analysis is unavailable because the attendance fact table has no arrival-time field. Findings should not be generalized to the entire workforce without more data.

## Conclusion
The analytics queries executed successfully against the current PulseIQ warehouse. The results provide an initial view of attendance, leave, and payroll data quality. Broader data coverage and dashboard verification are needed before operational conclusions can be made.
