
SELECT
    dt.full_date,
    COUNT(*) AS total_records,
    COUNT(*) FILTER (WHERE LOWER(a.attendance_status) = 'present') AS present_records,
    COUNT(*) FILTER (WHERE LOWER(a.attendance_status) = 'absent') AS absent_records,
    COUNT(*) FILTER (WHERE LOWER(a.attendance_status) = 'late') AS late_records,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE LOWER(a.attendance_status) = 'present')
        / NULLIF(COUNT(*), 0),
        2
    ) AS present_share_percent,
    ROUND(AVG(a.hours_worked), 2) AS average_hours_worked
FROM fact_attendance a
JOIN dim_date dt ON dt.date_key = a.date_key
GROUP BY dt.full_date
ORDER BY dt.full_date;


SELECT
    EXTRACT(ISODOW FROM dt.full_date) AS weekday_number,
    TRIM(TO_CHAR(dt.full_date, 'Day')) AS weekday,
    COUNT(*) AS total_records,
    COUNT(*) FILTER (WHERE LOWER(a.attendance_status) = 'present') AS present_records,
    COUNT(*) FILTER (WHERE LOWER(a.attendance_status) = 'absent') AS absent_records,
    COUNT(*) FILTER (WHERE LOWER(a.attendance_status) = 'late') AS late_records
FROM fact_attendance a
JOIN dim_date dt ON dt.date_key = a.date_key
GROUP BY
    EXTRACT(ISODOW FROM dt.full_date),
    TRIM(TO_CHAR(dt.full_date, 'Day'))
ORDER BY weekday_number;


SELECT
    DATE_TRUNC('month', dt.full_date)::date AS attendance_month,
    COUNT(*) AS total_records,
    COUNT(*) FILTER (WHERE LOWER(a.attendance_status) = 'present') AS present_records,
    COUNT(*) FILTER (WHERE LOWER(a.attendance_status) = 'absent') AS absent_records,
    COUNT(*) FILTER (WHERE LOWER(a.attendance_status) = 'late') AS late_records,
    ROUND(AVG(a.hours_worked), 2) AS average_hours_worked
FROM fact_attendance a
JOIN dim_date dt ON dt.date_key = a.date_key
GROUP BY DATE_TRUNC('month', dt.full_date)::date
ORDER BY attendance_month;


SELECT
    dt.full_date,
    d.department_name,
    COUNT(*) AS total_records,
    COUNT(*) FILTER (WHERE LOWER(a.attendance_status) = 'present') AS present_records,
    COUNT(*) FILTER (WHERE LOWER(a.attendance_status) = 'absent') AS absent_records,
    COUNT(*) FILTER (WHERE LOWER(a.attendance_status) = 'late') AS late_records,
    ROUND(AVG(a.hours_worked), 2) AS average_hours_worked
FROM fact_attendance a
JOIN dim_date dt ON dt.date_key = a.date_key
JOIN dim_employee e ON e.employee_key = a.employee_key
JOIN dim_department d ON d.department_key = e.department_key
GROUP BY dt.full_date, d.department_name
ORDER BY dt.full_date, d.department_name;


SELECT
    DATE_TRUNC('month', dt.full_date)::date AS leave_month,
    lt.leave_type_name,
    COUNT(*) AS leave_events,
    COALESCE(SUM(l.days), 0) AS total_leave_days
FROM fact_leave l
JOIN dim_date dt ON dt.date_key = l.leave_start_key
JOIN dim_leave_type lt ON lt.leave_type_key = l.leave_type_key
GROUP BY
    DATE_TRUNC('month', dt.full_date)::date,
    lt.leave_type_name
ORDER BY leave_month, lt.leave_type_name;
