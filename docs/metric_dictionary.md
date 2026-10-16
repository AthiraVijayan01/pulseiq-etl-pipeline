# PulseIQ Metric Dictionary

This document defines the business metrics used by the PulseIQ HR Analytics ETL pipeline.

## 1. Headcount

- **Definition:** Number of employees active on a specified reporting date.
- **Source:** `employee.csv`
- **Calculation:** Count distinct employees whose joining_date is on or before the reporting date and whose leaving_date is blank or later than the reporting date.
- **Unit:** Employees
- **Assumption:** Employees who leave after the reporting date are counted as active on that date. Employees who have not yet joined are excluded.

## 2. Average Salary

- **Definition:** Average of valid recorded employee salary amounts.
- **Source:** `salary.csv`
- **Calculation:** Sum of valid salary values divided by the number of valid salary records.
- **Unit:** Currency units per salary record
- **Assumption:** Multiple salary records for one employee are counted separately. Confirm the currency and reporting period before business reporting.

## 3. Attendance Rate

- **Definition:** Percentage of valid attendance records marked present.
- **Source:** `attendance.csv`
- **Calculation:** Number of valid records marked present divided by the total number of valid attendance records, multiplied by 100.
- **Unit:** Percentage
- **Assumption:** Only recognized attendance statuses are included. Confirm how holidays, weekends, and other attendance statuses should be treated.

## 4. Total Leave Days

- **Definition:** Total number of recorded leave days.
- **Source:** `leave.csv`
- **Calculation:** Sum of validated days values for the selected reporting period.
- **Unit:** Days
- **Assumption:** The days column represents the duration of each leave record. Specify the reporting period.

## 5. Total Net Payroll

- **Definition:** Total net payroll amount for the selected reporting period.
- **Source:** `payroll.csv`
- **Calculation:** Sum of valid net_pay values for the selected reporting period.
- **Unit:** Currency units
- **Assumption:** Confirm the currency and reporting period before reporting.

## Data Quality and Validation Rules

- Invalid records are stored separately in the `rejected/` directory.
- Rejected records must not be silently discarded.
- Metrics must use validated, cleaned data from the `clean/` directory or the corresponding validated warehouse tables.
- Employee IDs must be present and unique in the employee dataset.
- Salary, attendance, leave, and payroll records must reference valid employees.
- Numeric values must satisfy applicable nonnegative-value rules.
- Attendance hours must not exceed 24 hours per record.
- Payroll records must satisfy the applicable gross pay, deductions, and net pay consistency checks.
- Employee records with a joining_date later than their leaving_date must be rejected with a clear reason in `rejected/employee_rejected.csv`.
- Rejected records must not contribute to business metrics.

## Reporting Considerations

- Specify the reporting date for headcount.
- Specify the reporting period for salary, attendance, leave, and payroll metrics.
- Confirm currency before comparing monetary metrics.
- Document assumptions about missing values, attendance statuses, and duplicate records.
- Ensure dashboard calculations agree with the definitions in this document.