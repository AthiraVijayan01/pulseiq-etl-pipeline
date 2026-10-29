CREATE OR REPLACE VIEW phase2.v_monthly_attrition_exits AS
SELECT
    f.month_start_date,
    TO_CHAR(f.month_start_date, 'YYYY-MM') AS year_month,
    f.department_id,
    d.department_name,
    SUM(f.headcount_start)::BIGINT AS headcount_start,
    SUM(f.hires)::BIGINT AS hires,
    SUM(f.exits)::BIGINT AS exits,
    SUM(f.voluntary_exits)::BIGINT AS voluntary_exits,
    CASE
        WHEN COUNT(*) FILTER (
            WHERE f.exits IS NULL OR f.voluntary_exits IS NULL
        ) = 0
        THEN SUM(GREATEST(f.exits - f.voluntary_exits, 0))::BIGINT
        ELSE NULL
    END AS other_exits,
    SUM(f.transfers_in)::BIGINT AS transfers_in,
    SUM(f.transfers_out)::BIGINT AS transfers_out,
    SUM(f.headcount_end)::BIGINT AS headcount_end,
    AVG(f.attrition_rate_monthly_pct) AS attrition_rate_monthly_pct
FROM phase2.fact_headcount_monthly f
JOIN phase2.dim_department d
    ON d.department_id = f.department_id
GROUP BY
    f.month_start_date,
    f.department_id,
    d.department_name;


CREATE OR REPLACE VIEW phase2.v_department_attrition_exits AS
SELECT
    department_id,
    department_name,
    SUM(exits)::BIGINT AS exits,
    SUM(voluntary_exits)::BIGINT AS voluntary_exits,
    CASE
        WHEN COUNT(*) FILTER (
            WHERE exits IS NULL OR voluntary_exits IS NULL
        ) = 0
        THEN SUM(GREATEST(exits - voluntary_exits, 0))::BIGINT
        ELSE NULL
    END AS other_exits,
    SUM(hires)::BIGINT AS hires,
    AVG(attrition_rate_monthly_pct) AS avg_monthly_attrition_rate_pct
FROM phase2.v_monthly_attrition_exits
GROUP BY department_id, department_name;


CREATE OR REPLACE VIEW phase2.v_attrition_risk_department_snapshot AS
WITH risk_counts AS (
    SELECT
        r.as_of_date,
        r.department_id,
        d.department_name,
        COUNT(DISTINCT r.employee_id)::BIGINT AS employee_count,
        COUNT(DISTINCT r.employee_id) FILTER (
            WHERE LOWER(TRIM(r.risk_band)) = 'low'
        )::BIGINT AS low_count,
        COUNT(DISTINCT r.employee_id) FILTER (
            WHERE LOWER(TRIM(r.risk_band)) = 'medium'
        )::BIGINT AS medium_count,
        COUNT(DISTINCT r.employee_id) FILTER (
            WHERE LOWER(TRIM(r.risk_band)) = 'high'
        )::BIGINT AS high_count
    FROM phase2.fact_attrition_risk r
    LEFT JOIN phase2.dim_department d
        ON d.department_id = r.department_id
    GROUP BY r.as_of_date, r.department_id, d.department_name
)
SELECT
    as_of_date,
    department_id,
    department_name,
    CASE WHEN employee_count >= 5 THEN employee_count END
        AS employee_count,
    CASE
        WHEN employee_count >= 5
         AND (low_count = 0 OR low_count >= 5)
         AND (medium_count = 0 OR medium_count >= 5)
         AND (high_count = 0 OR high_count >= 5)
        THEN low_count
        ELSE NULL
    END AS low_risk_count,
    CASE
        WHEN employee_count >= 5
         AND (low_count = 0 OR low_count >= 5)
         AND (medium_count = 0 OR medium_count >= 5)
         AND (high_count = 0 OR high_count >= 5)
        THEN medium_count
        ELSE NULL
    END AS medium_risk_count,
    CASE
        WHEN employee_count >= 5
         AND (low_count = 0 OR low_count >= 5)
         AND (medium_count = 0 OR medium_count >= 5)
         AND (high_count = 0 OR high_count >= 5)
        THEN high_count
        ELSE NULL
    END AS high_risk_count,
    CASE
        WHEN employee_count >= 5
        THEN 'Predicted, not certain'
        ELSE 'Suppressed: group below minimum size'
    END AS interpretation
FROM risk_counts;


CREATE OR REPLACE VIEW phase2.v_attrition_risk_reasons AS
WITH reasons AS (
    SELECT
        r.as_of_date,
        r.department_id,
        d.department_name,
        r.employee_id,
        BTRIM(reason.reason_text) AS reason
    FROM phase2.fact_attrition_risk r
    LEFT JOIN phase2.dim_department d
        ON d.department_id = r.department_id
    CROSS JOIN LATERAL (
        VALUES (r.top_reason_1), (r.top_reason_2), (r.top_reason_3)
    ) AS reason(reason_text)
    WHERE NULLIF(BTRIM(reason.reason_text), '') IS NOT NULL
)
SELECT
    as_of_date,
    department_id,
    department_name,
    reason,
    COUNT(DISTINCT employee_id)::BIGINT AS employee_count
FROM reasons
GROUP BY as_of_date, department_id, department_name, reason
HAVING COUNT(DISTINCT employee_id) >= 5;
