CREATE OR REPLACE VIEW phase2.v_monthly_attendance_rate AS
WITH nonworking_days AS (
    SELECT
        full_date,
        is_holiday,
        full_date - ROW_NUMBER() OVER (ORDER BY full_date)::integer AS run_id
    FROM phase2.dim_date
    WHERE NOT is_working_day
),
long_weekends AS (
    SELECT full_date
    FROM nonworking_days
    WHERE run_id IN (
        SELECT run_id
        FROM nonworking_days
        GROUP BY run_id
        HAVING COUNT(*) >= 3
           AND BOOL_OR(is_holiday)
    )
),
calendar_monthly AS (
    SELECT
        DATE_TRUNC('month', d.full_date)::date AS month_start,
        COUNT(*) FILTER (WHERE d.is_holiday) AS holiday_days,
        COUNT(lw.full_date) AS long_weekend_days
    FROM phase2.dim_date d
    LEFT JOIN long_weekends lw ON lw.full_date = d.full_date
    GROUP BY DATE_TRUNC('month', d.full_date)::date
)
SELECT
    DATE_TRUNC('month', a.period_end_date)::date AS month_start,
    TO_CHAR(a.period_end_date, 'YYYY-MM') AS year_month,
    a.department_id,
    d.department_name,
    COUNT(DISTINCT a.employee_id) AS employee_count,
    SUM(a.scheduled_days) AS scheduled_days,
    SUM(a.present_days) AS present_days,
    ROUND(
        100.0 * SUM(a.present_days) / NULLIF(SUM(a.scheduled_days), 0),
        2
    ) AS attendance_rate_pct,
    SUM(a.late_arrivals) AS late_arrivals,
    ROUND(SUM(a.overtime_hours), 2) AS overtime_hours,
    COALESCE(c.holiday_days, 0) AS holiday_days,
    COALESCE(c.long_weekend_days, 0) AS long_weekend_days
FROM phase2.fact_attendance_monthly a
JOIN phase2.dim_department d
    ON d.department_id = a.department_id
LEFT JOIN calendar_monthly c
    ON c.month_start = DATE_TRUNC('month', a.period_end_date)::date
GROUP BY
    DATE_TRUNC('month', a.period_end_date)::date,
    TO_CHAR(a.period_end_date, 'YYYY-MM'),
    a.department_id,
    d.department_name,
    c.holiday_days,
    c.long_weekend_days
HAVING COUNT(DISTINCT a.employee_id) >= 5;

CREATE OR REPLACE VIEW phase2.v_monthly_leave_days AS
SELECT
    DATE_TRUNC('month', l.start_date)::date AS month_start,
    TO_CHAR(l.start_date, 'YYYY-MM') AS year_month,
    e.department_id,
    d.department_name,
    l.leave_type_code,
    lt.leave_type_name,
    COUNT(DISTINCT l.employee_id) AS employee_count,
    COUNT(*) AS approved_leave_requests,
    ROUND(SUM(l.days), 2) AS approved_leave_days
FROM phase2.fact_leave l
JOIN phase2.dim_employee e ON e.employee_key = l.employee_key
JOIN phase2.dim_department d ON d.department_id = e.department_id
JOIN phase2.dim_leave_type lt ON lt.leave_type_code = l.leave_type_code
WHERE LOWER(TRIM(l.status)) = 'approved'
  AND l.start_date IS NOT NULL
  AND l.end_date >= l.start_date
  AND l.days > 0
GROUP BY
    DATE_TRUNC('month', l.start_date)::date,
    TO_CHAR(l.start_date, 'YYYY-MM'),
    e.department_id,
    d.department_name,
    l.leave_type_code,
    lt.leave_type_name
HAVING COUNT(DISTINCT l.employee_id) >= 5;
