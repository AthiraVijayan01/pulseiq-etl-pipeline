WITH monthly_attendance AS (
    SELECT
        DATE_TRUNC('month', dt.full_date)::date AS attendance_month,
        COUNT(*) AS total_records,
        COUNT(*) FILTER (
            WHERE LOWER(a.attendance_status) = 'present'
        ) AS present_records,
        ROUND(
            100.0 * COUNT(*) FILTER (
                WHERE LOWER(a.attendance_status) = 'present'
            ) / NULLIF(COUNT(*), 0),
            2
        ) AS attendance_rate
    FROM fact_attendance a
    JOIN dim_date dt ON dt.date_key = a.date_key
    GROUP BY DATE_TRUNC('month', dt.full_date)::date
)
SELECT
    attendance_month,
    total_records,
    present_records,
    attendance_rate,
    ROUND(
        AVG(attendance_rate) OVER (
            ORDER BY attendance_month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS rolling_3_month_average
FROM monthly_attendance
ORDER BY attendance_month;


SELECT
    d.department_name,
    COUNT(*) AS total_records,
    COUNT(*) FILTER (
        WHERE LOWER(a.attendance_status) = 'present'
    ) AS present_records,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE LOWER(a.attendance_status) = 'present'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS attendance_rate
FROM fact_attendance a
JOIN dim_employee e ON e.employee_key = a.employee_key
JOIN dim_department d ON d.department_key = e.department_key
GROUP BY d.department_name
ORDER BY attendance_rate DESC, d.department_name;


SELECT
    EXTRACT(ISODOW FROM dt.full_date)::integer AS weekday_number,
    TRIM(TO_CHAR(dt.full_date, 'Day')) AS weekday,
    COUNT(*) AS total_records,
    COUNT(*) FILTER (
        WHERE LOWER(a.attendance_status) = 'present'
    ) AS present_records,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE LOWER(a.attendance_status) = 'present'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS attendance_rate
FROM fact_attendance a
JOIN dim_date dt ON dt.date_key = a.date_key
GROUP BY
    EXTRACT(ISODOW FROM dt.full_date),
    TRIM(TO_CHAR(dt.full_date, 'Day'))
ORDER BY weekday_number;
