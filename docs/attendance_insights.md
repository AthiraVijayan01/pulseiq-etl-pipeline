# PulseIQ Attendance Insights Report

## 1. Objective

Analyze attendance records in the PulseIQ PostgreSQL warehouse to identify attendance patterns across departments and weekdays.

## 2. Key Findings

### Overall Attendance

The dataset contains 8 attendance records for January 2025. Six records are marked present, one is absent, and one is late. The present-only attendance rate is 75%.

### Department Comparison

- Engineering: 4 of 4 records are present (100%).
- Finance: 1 of 2 records is present (50%).
- HR: 1 of 2 records is present (50%).

These department comparisons are based on a small sample and should be reviewed with additional data before drawing conclusions.

### Weekday Comparison

- Thursday: 3 of 4 records are present (75%).
- Friday: 3 of 4 records are present (75%).

Both weekdays have the same recorded present-only attendance rate.

### Monthly Trend

January 2025 has a present-only attendance rate of 75%. The rolling three-month average is also 75%, but only one month is available. More months of data are needed to evaluate a meaningful trend.

## 3. Recommended Actions

1. Review additional attendance records for Finance and HR before deciding whether follow-up is necessary.
2. Monitor absences and late arrivals separately.
3. Collect several months of consistent attendance data.
4. Consider approved leave and employee work schedules when reviewing patterns.
5. Refresh the dashboard as new validated records become available.

## 4. Limitations

- The analysis contains only 8 attendance records.
- The available attendance dates are limited to January 2025.
- Department and weekday comparisons are based on very small samples.
- The present-only attendance rate counts records marked present; late records are not counted as present.
- These findings are descriptive and do not establish causes or long-term employee behavior.

## 5. SQL and Data Source

Source query: `sql/warehouse/attendance_trends.sql`

Source tables: `fact_attendance`, `dim_date`, `dim_employee`, and `dim_department`.

## 6. Conclusion

The warehouse queries produce monthly, department-level, and weekday attendance summaries. The results demonstrate the attendance analytics workflow, but a larger dataset is required for reliable operational conclusions.