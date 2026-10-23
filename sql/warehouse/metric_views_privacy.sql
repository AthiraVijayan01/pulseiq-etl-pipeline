
-- PulseIQ Task 4: Privacy-protected metric views
-- Suppress department-level groups with fewer than 5 distinct employees.

CREATE OR REPLACE VIEW v_monthly_headcount AS
SELECT
    d.full_date AS month_start,
    dep.department_name,
    h.headcount
FROM fact_monthly_headcount h
JOIN dim_date d
    ON d.date_key = h.month_key
JOIN dim_department dep
    ON dep.department_key = h.department_key
WHERE h.headcount >= 5;


CREATE OR REPLACE VIEW v_monthly_attendance_rate AS
SELECT
    DATE_TRUNC('month', d.full_date)::date AS month_start,
    dep.department_name,
    COUNT(*) AS attendance_records,
    COUNT(*) FILTER (
        WHERE LOWER(TRIM(a.attendance_status)) IN ('present', 'p')
    ) AS present_records,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE LOWER(TRIM(a.attendance_status)) IN ('present', 'p')
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS attendance_rate_percent
FROM fact_attendance a
JOIN dim_date d
    ON d.date_key = a.date_key
JOIN dim_employee e
    ON e.employee_key = a.employee_key
JOIN dim_department dep
    ON dep.department_key = e.department_key
GROUP BY
    DATE_TRUNC('month', d.full_date)::date,
    dep.department_name
HAVING COUNT(DISTINCT e.employee_id) >= 5;


CREATE OR REPLACE VIEW v_monthly_leave_days AS
SELECT
    DATE_TRUNC('month', start_date.full_date)::date AS month_start,
    dep.department_name,
    lt.leave_type_name,
    SUM(l.days) AS total_leave_days,
    COUNT(*) AS leave_events
FROM fact_leave l
JOIN dim_date start_date
    ON start_date.date_key = l.leave_start_key
JOIN dim_employee e
    ON e.employee_key = l.employee_key
JOIN dim_department dep
    ON dep.department_key = e.department_key
JOIN dim_leave_type lt
    ON lt.leave_type_key = l.leave_type_key
GROUP BY
    DATE_TRUNC('month', start_date.full_date)::date,
    dep.department_name,
    lt.leave_type_name
HAVING COUNT(DISTINCT e.employee_id) >= 5;


CREATE OR REPLACE VIEW v_monthly_net_payroll AS
SELECT
    DATE_TRUNC('month', p.pay_period)::date AS month_start,
    dep.department_name,
    SUM(p.net_pay) AS total_net_payroll,
    COUNT(*) AS payroll_records
FROM fact_payroll p
JOIN dim_employee e
    ON e.employee_key = p.employee_key
JOIN dim_department dep
    ON dep.department_key = e.department_key
GROUP BY
    DATE_TRUNC('month', p.pay_period)::date,
    dep.department_name
HAVING COUNT(DISTINCT e.employee_id) >= 5;

DROP VIEW metric_catalog;

CREATE VIEW metric_catalog AS

SELECT
    'headcount'::text AS metric_name,
    'Employee headcount by month and department; groups below 5 are suppressed.'::text AS metric_description,
    'employees'::text AS unit,
    'v_monthly_headcount'::text AS source_view,
    'HR Analytics'::text AS owner

UNION ALL

SELECT
    'attendance_rate',
    'Present attendance records divided by all recorded attendance records; groups below 5 employees are suppressed.',
    'percent',
    'v_monthly_attendance_rate',
    'HR Analytics'

UNION ALL

SELECT
    'total_leave_days',
    'Sum of recorded leave days grouped by month leave starts; groups below 5 employees are suppressed.',
    'days',
    'v_monthly_leave_days',
    'HR Analytics'

UNION ALL

SELECT
    'total_net_payroll',
    'Sum of net payroll by pay-period month and department; groups below 5 employees are suppressed.',
    'database_currency_units',
    'v_monthly_net_payroll',
    'Finance';
