# PulseIQ — Workforce Analytics & ETL Pipeline

## Project Overview

PulseIQ is a workforce analytics and data engineering training project that processes employee, attendance, leave, salary, payroll, and related business datasets. It provides a structured data pipeline for data extraction, cleaning, validation, storage, and analytical reporting.

The project uses Python and pandas for ETL processing, Pandera for data validation, PostgreSQL for analytical storage, and Streamlit for dashboard visualization. Docker Compose is used to configure and run the application services.

The project also includes SQL-based analytical queries, metric views, data-quality checks, execution logs, and supporting documentation.

## Project Objectives

- Build a repeatable ETL pipeline for structured business datasets.
- Clean and standardize source data.
- Validate records and separate rejected data.
- Generate clean CSV and Parquet outputs.
- Load processed data into a PostgreSQL analytical warehouse.
- Support workforce and business analytics through SQL queries and dashboard visualizations.
- Implement data-quality checks and validation procedures.
- Containerize the application services using Docker Compose.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python 3.12 | ETL processing and application logic |
| pandas | Data transformation and cleaning |
| Pandera | Data validation |
| PostgreSQL 16 | Analytical data warehouse |
| psycopg | PostgreSQL connectivity |
| Streamlit | Interactive analytics dashboard |
| Plotly | Data visualization |
| Docker | Application containerization |
| Docker Compose | Multi-service orchestration |
| SQL | Warehouse schema, metric views and analytical queries |
| CSV and Parquet | Data storage and exchange formats |
| Git and GitHub | Version control and project hosting |

## Key Features

### 1. ETL Pipeline

The ETL pipeline processes structured datasets through extraction, transformation, validation, and output generation.

Key capabilities include:

- Reading source CSV files from the `raw/` directory.
- Cleaning and standardizing data using pandas.
- Validating records against configured data-quality rules.
- Separating rejected records from accepted records.
- Exporting processed datasets in CSV and Parquet formats.
- Recording execution information in the `logs/` directory.

### 2. Data Quality and Validation

The project includes validation scripts and data-quality checks designed to identify inconsistencies across business datasets.

Examples of checks include:

- Payroll-to-ledger reconciliation.
- Ledger balancing.
- Duplicate payroll detection.
- Employee reference validation.
- Attendance and leave date validation.
- Invoice and expense arithmetic.
- Dimension history overlap checks.
- AI-feed freshness validation.

The project maintains separate outputs for rejected records to support investigation and correction.

### 3. PostgreSQL Data Warehouse

The warehouse is defined through SQL schema files and populated by the warehouse loading module.

The warehouse includes employee, department, role, date, and leave-type dimensions, together with attendance, leave, payroll, and monthly headcount facts.

The employee dimension includes Slowly Changing Dimension Type 2 (SCD Type 2) history fields, including effective dates and a current-record indicator.

SQL scripts provide analytical queries, attendance analysis, metric views, and supporting warehouse operations.

### 4. Streamlit Dashboard

The Streamlit dashboard provides a visual interface for exploring workforce data and HR metrics.

The dashboard implementation includes workforce summary metrics, department and role distributions, monthly headcount information, and analytical filters.

Dashboard results depend on the data loaded into the PostgreSQL warehouse and the selected reporting period.

### 5. Docker-Based Execution

Docker Compose configures three services:

- `postgres` — PostgreSQL database.
- `etl` — ETL processing service.
- `dashboard` — Streamlit dashboard service.

The ETL service may exit after successfully completing its one-time processing job. An `Exited (0)` status indicates successful process termination, provided the service logs confirm that the job completed without errors.

## Project Structure

```text
pulseiq-etl/
├── raw/                         # Source CSV datasets
├── clean/                       # Cleaned CSV and Parquet outputs
├── rejected/                    # Rejected data records
├── logs/                        # ETL execution logs
├── docs/                        # Project documentation and findings
│   ├── attendance_insights.md
│   ├── c01_reconciliation_investigation.md
│   ├── dashboard_style_guide.md
│   ├── data_quality_report.md
│   ├── metric_dictionary.md
│   ├── metric_view_validation.md
│   └── task4_insights.md
├── dashboards/
│   └── app.py                   # Streamlit dashboard
├── sql/
│   ├── analysis_queries.sql
│   ├── task4_analytics.sql
│   └── warehouse/
│       ├── schema.sql
│       ├── analysis_queries.sql
│       ├── attendance_analysis.sql
│       ├── attendance_trends.sql
│       ├── metric_views.sql
│       └── metric_views_privacy.sql
├── src/
│   ├── db.py                    # Database connectivity
│   ├── etl.py                   # ETL processing
│   └── warehouse.py             # Warehouse loading
├── add_salary_loader.py
├── check_dashboard.py
├── check_dashboard_data.py
├── check_warehouse.py
├── inspect_payroll_mismatches.py
├── run_data_quality_checks.py
├── run_official_dq_checks.py
├── test_data_quality_checks.py
├── test_official_dq_negative.py
├── test_scd2_temp.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .dockerignore
├── .env.example
├── .gitignore
└── README.md
```

The structure above lists the principal project files and directories. Generated outputs, runtime files, and local development artifacts are not all shown.

## Prerequisites

Install or configure the following before running the project:

- Python 3.12.
- Docker Desktop with Docker Compose.
- Git, if cloning the repository.
- The Python packages listed in `requirements.txt`.

## Setup and Installation

### 1. Clone the repository

```powershell
git clone https://github.com/AthiraVijayan01/pulseiq-etl-pipeline.git
cd pulseiq-etl-pipeline
```

If working from an existing local checkout, open PowerShell in the project directory instead.

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file using `.env.example` as the configuration reference.

Set the database connection values required by the application and the execution environment. Confirm whether a command is connecting from the host machine or from a Docker container, because the appropriate database hostname and port may differ.

Do not commit `.env` or expose passwords, credentials, or other secrets.

## Running the Project

### Run the ETL Pipeline Locally

From the project root, execute:

```powershell
python -m src.etl
```

Review the terminal output and the generated files in `clean/`, `rejected/`, and `logs/`.

### Load the Data Warehouse

Ensure that PostgreSQL is running and that the configured database connection is correct.

Execute:

```powershell
python -m src.warehouse
```

Inspect the warehouse tables and verify that the expected data has been loaded.

### Run with Docker Compose

Build the configured services and start them:

```powershell
docker compose up -d --build
```

Check service status:

```powershell
docker compose ps
```

Inspect the service logs:

```powershell
docker compose logs --tail 60 postgres
docker compose logs --tail 60 etl
docker compose logs --tail 60 dashboard
```

The ETL container may stop after completing its processing job. Check its exit status and logs before interpreting this as an error.

### Open the Dashboard

Once the dashboard service is running, open:

http://localhost:8501

The current Compose configuration exposes PostgreSQL on host port `5433`, mapped to the container's PostgreSQL port `5432`.

## Data Outputs

| Directory | Description |
|---|---|
| `raw/` | Input CSV datasets |
| `clean/` | Processed datasets in CSV and Parquet formats |
| `rejected/` | Records rejected during validation |
| `logs/` | ETL execution and diagnostic logs |

The project includes workforce datasets and related business data covering areas such as payroll, attendance, leave, accounting, invoices, expenses, tasks, forecasts, anomalies, and analytical metrics.

The exact contents of each output depend on the source files and the ETL execution.

## Data Warehouse and Analytics

The SQL components support warehouse creation, data loading, analytical queries, attendance analysis, and metric-view validation.

Important SQL files include:

- `sql/warehouse/schema.sql`
- `sql/warehouse/analysis_queries.sql`
- `sql/warehouse/attendance_analysis.sql`
- `sql/warehouse/attendance_trends.sql`
- `sql/warehouse/metric_views.sql`
- `sql/warehouse/metric_views_privacy.sql`
- `sql/analysis_queries.sql`
- `sql/task4_analytics.sql`

Refer to the SQL definitions and the metric dictionary for the calculation rules and intended meaning of individual metrics.

## Testing and Verification

The repository includes scripts for checking the ETL pipeline, warehouse, dashboard data, data-quality rules, and employee history.

Run the following checks from the project root when the required database services and configuration are available.

### Python Syntax Validation

```powershell
python -m py_compile src\db.py src\etl.py src\warehouse.py dashboards\app.py
```

### Dashboard and Warehouse Checks

```powershell
python check_dashboard.py
python check_dashboard_data.py
python check_warehouse.py
```

### Data-Quality Checks

```powershell
python run_data_quality_checks.py
python run_official_dq_checks.py
python test_data_quality_checks.py
python test_official_dq_negative.py
```

Review each script's output to distinguish passing checks from failures, blocked checks, or tests that could not run.

**Current verification note:** In the latest recorded isolated negative-test run, 11 checks passed, zero checks failed, and DQ-C11 (AI-feed freshness) was blocked because the baseline unexpectedly returned one row. The script reported that no official DQ result rows were written. This issue requires further investigation before claiming that all official data-quality checks have passed.

Test results can change as the code, input data, configuration, or database state changes. Rerun the checks against the version being submitted.

## Documentation

The `docs/` directory contains supporting project documentation.

| Document | Purpose |
|---|---|
| `metric_dictionary.md` | Metric definitions and calculation guidance |
| `dashboard_style_guide.md` | Dashboard presentation guidance |
| `attendance_insights.md` | Attendance analysis findings |
| `task4_insights.md` | Task-related analytical insights |
| `data_quality_report.md` | Data-quality findings |
| `c01_reconciliation_investigation.md` | Payroll and ledger reconciliation investigation |
| `metric_view_validation.md` | Metric-view validation findings |

## Security and Submission Notes

- Keep `.env` private and exclude it from Git and submission archives.
- Use `.env.example` to document configuration requirements without real credentials.
- Do not include `.venv/`, `__pycache__/`, or unnecessary backup files in the submission.
- Review generated data files and logs for sensitive information before sharing.
- Verify that the GitHub repository and submission archive contain the intended source code and documentation.
- Include evidence for tests that passed and disclose unresolved validation issues.

## Current Project Status

The project contains the main ETL, PostgreSQL warehouse, SQL analytics, data-quality scripts, documentation, and Streamlit dashboard components.

The latest recorded runtime checks showed that the dashboard container was running, PostgreSQL was healthy, the Python compilation command completed without errors, and the dashboard data checks returned workforce analytics results.

The AI-feed freshness negative test remains blocked and should be investigated separately. Completion of the full assignment should be assessed against the official requirements and verified test results.

## Repository

GitHub: https://github.com/AthiraVijayan01/pulseiq-etl-pipeline

## Acknowledgement

Developed as part of data analyst internship training, with a focus on ETL development, data quality, SQL analytics, PostgreSQL warehousing, and dashboard reporting.
