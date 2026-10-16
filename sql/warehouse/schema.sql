
-- PulseIQ: PostgreSQL warehouse schema
-- Dimension tables

CREATE TABLE IF NOT EXISTS dim_department (
    department_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_role (
    role_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_leave_type (
    leave_type_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    leave_type_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key INTEGER PRIMARY KEY,             -- YYYYMMDD
    full_date DATE NOT NULL UNIQUE,
    day_of_month SMALLINT NOT NULL,
    month_number SMALLINT NOT NULL,
    month_name VARCHAR(12) NOT NULL,
    quarter_number SMALLINT NOT NULL,
    calendar_year SMALLINT NOT NULL,
    weekday_number SMALLINT NOT NULL,
    weekday_name VARCHAR(12) NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

-- Type 2 slowly changing dimension:
-- Each department/role version has its own employee_key.
-- Keep the previous row when department or role changes.
CREATE TABLE IF NOT EXISTS dim_employee (
    employee_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id VARCHAR(50) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    department_key BIGINT REFERENCES dim_department(department_key),
    role_key BIGINT REFERENCES dim_role(role_key),
    joining_date DATE,
    leaving_date DATE,
    effective_from DATE NOT NULL,
    effective_to DATE NOT NULL DEFAULT DATE '9999-12-31',
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_employee_effective_dates
        CHECK (effective_from <= effective_to),
    CONSTRAINT ck_employee_current_end_date
        CHECK (NOT is_current OR effective_to = DATE '9999-12-31')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_employee_current
    ON dim_employee(employee_id)
    WHERE is_current = TRUE;

CREATE INDEX IF NOT EXISTS ix_dim_employee_business_id
    ON dim_employee(employee_id, effective_from, effective_to);

-- Fact tables

-- Grain: one row per employee per attendance date.
CREATE TABLE IF NOT EXISTS fact_attendance (
    attendance_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_key BIGINT NOT NULL REFERENCES dim_employee(employee_key),
    date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    attendance_status VARCHAR(50) NOT NULL,
    hours_worked NUMERIC(6,2),
    CONSTRAINT uq_fact_attendance_employee_date
        UNIQUE (employee_key, date_key),
    CONSTRAINT ck_attendance_hours
        CHECK (hours_worked IS NULL OR hours_worked BETWEEN 0 AND 24)
);

-- Grain: one row per employee per payroll period.
CREATE TABLE IF NOT EXISTS fact_payroll (
    payroll_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_key BIGINT NOT NULL REFERENCES dim_employee(employee_key),
    pay_period DATE NOT NULL,
    pay_date DATE,
    gross_pay NUMERIC(14,2) NOT NULL,
    deductions NUMERIC(14,2) NOT NULL,
    net_pay NUMERIC(14,2) NOT NULL,
    CONSTRAINT uq_fact_payroll_employee_period
        UNIQUE (employee_key, pay_period),
    CONSTRAINT ck_payroll_amounts
        CHECK (gross_pay >= 0 AND deductions >= 0 AND net_pay >= 0)
);

-- Grain: one row per recorded leave event.
CREATE TABLE IF NOT EXISTS fact_leave (
    leave_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_key BIGINT NOT NULL REFERENCES dim_employee(employee_key),
    leave_start_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    leave_end_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    leave_type_key BIGINT NOT NULL REFERENCES dim_leave_type(leave_type_key),
    days NUMERIC(6,2) NOT NULL,
    CONSTRAINT ck_leave_dates
        CHECK (leave_start_key <= leave_end_key),
    CONSTRAINT ck_leave_days
        CHECK (days >= 0)
);

-- Grain: one row per calendar month and department.
-- This table is a snapshot/aggregate, not a transaction-level fact.
CREATE TABLE IF NOT EXISTS fact_monthly_headcount (
    monthly_headcount_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    month_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    department_key BIGINT NOT NULL REFERENCES dim_department(department_key),
    headcount INTEGER NOT NULL,
    CONSTRAINT uq_monthly_headcount_month_department
        UNIQUE (month_key, department_key),
    CONSTRAINT ck_headcount_nonnegative CHECK (headcount >= 0)
);

-- Query-supporting indexes
CREATE INDEX IF NOT EXISTS ix_attendance_date
    ON fact_attendance(date_key);

CREATE INDEX IF NOT EXISTS ix_attendance_employee
    ON fact_attendance(employee_key);

CREATE INDEX IF NOT EXISTS ix_payroll_period
    ON fact_payroll(pay_period);

CREATE INDEX IF NOT EXISTS ix_payroll_employee
    ON fact_payroll(employee_key);

CREATE INDEX IF NOT EXISTS ix_leave_start_date
    ON fact_leave(leave_start_key);

CREATE INDEX IF NOT EXISTS ix_monthly_headcount_month
    ON fact_monthly_headcount(month_key);
