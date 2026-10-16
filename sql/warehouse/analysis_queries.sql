
SELECT
    DATE_TRUNC('month', p.pay_period)::date AS payroll_month,
    d.department_name,
    COUNT(DISTINCT e.employee_id) AS employees_paid,
    SUM(p.gross_pay) AS total_gross_pay,
    SUM(p.deductions) AS total_deductions,
    SUM(p.net_pay) AS total_net_pay
FROM fact_payroll AS p
JOIN dim_employee AS e
    ON e.employee_key = p.employee_key
JOIN dim_department AS d
    ON d.department_key = e.department_key
WHERE p.pay_period >= e.effective_from
  AND p.pay_period <= e.effective_to
GROUP BY
    DATE_TRUNC('month', p.pay_period)::date,
    d.department_name
ORDER BY payroll_month, d.department_name;


-- Query 2: Monthly attendance summary by department.
SELECT
    DATE_TRUNC('month', dt.full_date)::date AS attendance_month,
    d.department_name,
    COUNT(*) AS attendance_records,
    COUNT(*) FILTER (
        WHERE LOWER(a.attendance_status) = 'present'
    ) AS present_records,
    ROUND(AVG(a.hours_worked), 2) AS average_hours_worked
FROM fact_attendance AS a
JOIN dim_date AS dt
    ON dt.date_key = a.date_key
JOIN dim_employee AS e
    ON e.employee_key = a.employee_key
JOIN dim_department AS d
    ON d.department_key = e.department_key
GROUP BY
    DATE_TRUNC('month', dt.full_date)::date,
    d.department_name
ORDER BY attendance_month, d.department_name;


-- Query 3: Leave days by type and month.
SELECT
    DATE_TRUNC('month', start_date.full_date)::date AS leave_month,
    lt.leave_type_name,
    COUNT(*) AS leave_events,
    SUM(l.days) AS total_leave_days
FROM fact_leave AS l
JOIN dim_date AS start_date
    ON start_date.date_key = l.leave_start_key
JOIN dim_leave_type AS lt
    ON lt.leave_type_key = l.leave_type_key
GROUP BY
    DATE_TRUNC('month', start_date.full_date)::date,
    lt.leave_type_name
ORDER BY leave_month, lt.leave_type_name;
