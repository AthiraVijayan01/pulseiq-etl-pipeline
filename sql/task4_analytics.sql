
WITH monthly_attendance AS (
    SELECT
        DATE_TRUNC('month', dt.full_date)::date AS attendance_month,
        COUNT(*) AS attendance_records,
        COUNT(*) FILTER (
            WHERE LOWER(a.attendance_status) = 'present'
        ) AS present_records,
        ROUND(AVG(a.hours_worked), 2) AS average_hours
    FROM fact_attendance a
    JOIN dim_date dt ON dt.date_key = a.date_key
    GROUP BY DATE_TRUNC('month', dt.full_date)::date
)
SELECT
    attendance_month,
    attendance_records,
    present_records,
    average_hours,
    ROUND(
        AVG(average_hours) OVER (
            ORDER BY attendance_month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS rolling_3_month_average_hours
FROM monthly_attendance
ORDER BY attendance_month;


SELECT
    dt.weekday_name,
    dt.weekday_number,
    COUNT(*) AS attendance_records,
    COUNT(*) FILTER (
        WHERE LOWER(a.attendance_status) = 'present'
    ) AS present_records,
    ROUND(AVG(a.hours_worked), 2) AS average_hours
FROM fact_attendance a
JOIN dim_date dt ON dt.date_key = a.date_key
GROUP BY dt.weekday_name, dt.weekday_number
ORDER BY dt.weekday_number;


SELECT
    DATE_TRUNC('month', dt.full_date)::date AS leave_month,
    lt.leave_type_name,
    COUNT(*) AS leave_events,
    SUM(l.days) AS total_leave_days
FROM fact_leave l
JOIN dim_date dt ON dt.date_key = l.leave_start_key
JOIN dim_leave_type lt ON lt.leave_type_key = l.leave_type_key
GROUP BY
    DATE_TRUNC('month', dt.full_date)::date,
    lt.leave_type_name
ORDER BY leave_month, lt.leave_type_name;


SELECT
    p.payroll_key,
    e.employee_id,
    p.pay_period,
    p.gross_pay,
    p.deductions,
    p.net_pay,
    CASE
        WHEN p.gross_pay < 0 THEN 'Negative gross pay'
        WHEN p.deductions < 0 THEN 'Negative deductions'
        WHEN p.net_pay < 0 THEN 'Negative net pay'
        WHEN p.deductions > p.gross_pay THEN 'Deductions exceed gross pay'
        WHEN ABS(p.net_pay - (p.gross_pay - p.deductions)) > 0.01
            THEN 'Net pay calculation mismatch'
    END AS anomaly
FROM fact_payroll p
JOIN dim_employee e ON e.employee_key = p.employee_key
WHERE
    p.gross_pay < 0
    OR p.deductions < 0
    OR p.net_pay < 0
    OR p.deductions > p.gross_pay
    OR ABS(p.net_pay - (p.gross_pay - p.deductions)) > 0.01
ORDER BY p.pay_period, e.employee_id;
