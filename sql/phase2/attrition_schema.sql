CREATE TABLE IF NOT EXISTS phase2.fact_headcount_monthly (
    date_key INTEGER NOT NULL REFERENCES phase2.dim_date(date_key),
    month_start_date DATE NOT NULL,
    department_id TEXT NOT NULL
        REFERENCES phase2.dim_department(department_id),
    headcount_start INTEGER,
    hires INTEGER,
    exits INTEGER,
    voluntary_exits INTEGER,
    transfers_in INTEGER,
    transfers_out INTEGER,
    headcount_end INTEGER,
    attrition_rate_monthly_pct NUMERIC,
    CONSTRAINT pk_phase2_headcount_monthly
        PRIMARY KEY (date_key, department_id),
    CONSTRAINT uq_phase2_headcount_month_department
        UNIQUE (month_start_date, department_id),
    CONSTRAINT ck_phase2_voluntary_exits
        CHECK (
            voluntary_exits IS NULL
            OR exits IS NULL
            OR voluntary_exits <= exits
        )
);

CREATE TABLE IF NOT EXISTS phase2.fact_attrition_risk (
    prediction_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    as_of_date_key INTEGER REFERENCES phase2.dim_date(date_key),
    department_id TEXT REFERENCES phase2.dim_department(department_id),
    as_of_date DATE NOT NULL,
    risk_score_12m NUMERIC,
    risk_band TEXT,
    top_reason_1 TEXT,
    top_reason_2 TEXT,
    top_reason_3 TEXT,
    model_version TEXT,
    model_note TEXT,
    employee_key BIGINT REFERENCES phase2.dim_employee(employee_key),
    CONSTRAINT uq_phase2_attrition_prediction_snapshot
        UNIQUE (employee_id, as_of_date)
);
