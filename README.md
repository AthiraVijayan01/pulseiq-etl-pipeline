# PulseIQ ETL Pipeline

## Overview

PulseIQ is a data engineering project that extracts, cleans, validates, and loads employee-related datasets. It produces clean CSV and Parquet files, separates rejected records, loads data into a PostgreSQL warehouse, and provides a Streamlit dashboard for HR analytics.

## GitHub Repository

**Project Repository:** [PulseIQ ETL Pipeline](https://github.com/AthiraVijayan01/pulseiq-etl-pipeline)

The repository contains the project source code, ETL pipeline, PostgreSQL warehouse, SQL queries, Streamlit dashboard, configuration files, and project documentation.

## Features

- Extract employee, salary, attendance, leave, and payroll datasets.
- Clean and standardize data using pandas.
- Validate data and reject invalid or inconsistent records.
- Perform referential validation across related datasets.
- Export clean data in CSV and Parquet formats.
- Maintain ETL execution logs.
- Load data into a PostgreSQL analytical warehouse.
- Visualize HR metrics using a Streamlit dashboard.
- Run configured services using Docker Compose.

## Project Structure

```text
pulseiq-etl/
├── raw/
├── clean/
├── rejected/
├── logs/
├── docs/
│   ├── attendance_insights.md
│   ├── dashboard_style_guide.md
│   ├── metric_dictionary.md
│   └── task4_insights.md
├── dashboards/
│   └── app.py
├── sql/
│   └── warehouse/
├── src/
│   ├── db.py
│   ├── etl.py
│   └── warehouse.py
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

The structure above describes the main project components. Some files may differ depending on the current project version.

## Requirements

- Python 3.12 or a compatible version.
- PostgreSQL.
- Docker Desktop with Docker Compose.
- Python packages listed in `requirements.txt`.

## Local Setup

Open PowerShell in the project directory:

```powershell
cd D:\pulseiq-etl
```

Create a virtual environment if one does not already exist:

```powershell
python -m venv .venv
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the required packages:

```powershell
python -m pip install -r requirements.txt
```

Create a local `.env` file using `.env.example` as a reference. Configure the database connection values for your environment.

Do not commit `.env` or expose database passwords.

## Run the ETL Pipeline

Run the following command from the project root:

```powershell
python -m src.etl
```

The pipeline processes the input datasets, validates records, writes clean CSV and Parquet outputs, saves rejected records, and records execution details in the logs directory.

## Load the Data Warehouse

Ensure PostgreSQL is running and the database settings in `.env` match the database you intend to use.

Run:

```powershell
python -m src.warehouse
```

The warehouse module loads the clean datasets into PostgreSQL analytical tables.

## Run with Docker Compose

Build the dashboard image and start the configured services:

```powershell
docker compose build dashboard
docker compose up -d
docker compose ps
```

Inspect service logs:

```powershell
docker compose logs --tail 60 etl
docker compose logs --tail 60 dashboard
docker compose logs --tail 60 postgres
```

The ETL service runs as a one-time job and may show `Exited (0)` after successful completion.

Open the dashboard in your browser:

[http://localhost:8501](http://localhost:8501)

The Compose PostgreSQL service is exposed on port 5433 on the host in the current configuration. Containers communicate using their configured Compose service names and internal ports.

## Output Directories

- `clean/`: Validated datasets in CSV and Parquet formats.
- `rejected/`: Records rejected during data-quality or referential validation.
- `logs/`: ETL execution logs and diagnostic information.

## Warehouse

The PostgreSQL warehouse includes employee, department, role, and date dimensions, along with attendance, leave, payroll, and monthly headcount facts.

The warehouse supports analytical queries for employee headcount, department distribution, attendance, leave, payroll, and related HR metrics.

## Validation and Verification

- Review ETL logs for extraction counts, transformation results, rejected rows, and final validation status.
- Check warehouse tables and row counts using PostgreSQL.
- Confirm employee references are valid.
- Verify that repeated loads do not create unintended duplicates.
- Open the dashboard in a browser and check that metrics, charts, date filters, and department filters work correctly.
- Confirm that Docker services start and the application is accessible.

## Documentation

- `docs/metric_dictionary.md`: Definitions and calculation rules for dashboard metrics.
- `docs/dashboard_style_guide.md`: Dashboard design and presentation guidance.
- `docs/attendance_insights.md`: Attendance analysis and findings.
- `docs/task4_insights.md`: HR analytics insights and limitations.

## Security

- Keep `.env` private.
- Use `.env.example` to document required configuration without real credentials.
- Do not commit passwords, database secrets, or private data.
- Restrict dashboard access to trusted users and networks.
- Review files before uploading the project ZIP or pushing changes to GitHub.

## Current Status

The ETL pipeline has completed successfully in testing. Docker services have started successfully, the dashboard has returned HTTP 200, and expected row counts have been verified in the PostgreSQL warehouse.

Final visual dashboard checks, repeatability checks, documentation review, and confirmation against all project requirements should be completed before declaring the project fully finished.

## Project Links

- **GitHub Repository:** https://github.com/AthiraVijayan01/pulseiq-etl-pipeline
- **Local Dashboard:** http://localhost:8501 (available when the dashboard service is running)
