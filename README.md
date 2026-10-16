# PulseIQ ETL Pipeline

## Overview

PulseIQ is a data engineering project that extracts, cleans, validates, and loads employee-related datasets. It produces clean CSV and Parquet files, separates rejected records, loads data into a PostgreSQL warehouse, and provides a Streamlit dashboard for HR analytics.

## Features

- Extract employee, salary, attendance, leave, and payroll datasets.
- Clean and standardize data using pandas.
- Validate data and reject invalid or inconsistent records.
- Perform referential validation across related datasets.
- Export clean data in CSV and Parquet formats.
- Maintain ETL logs.
- Load data into a PostgreSQL analytical warehouse.
- Visualize HR metrics using a Streamlit dashboard.
- Run services using Docker Compose.

## Project Structure

```text
pulseiq-etl/
├── raw/
├── clean/
├── rejected/
├── logs/
├── docs/
│   ├── dashboard_style_guide.md
│   └── metric_dictionary.md
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

## Requirements

- Python 3.12 or compatible version
- PostgreSQL
- Docker Desktop with Docker Compose
- Python packages listed in requirements.txt

## Local Setup

Open a terminal in the project directory.

Create and activate a virtual environment if one does not already exist:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Create a local `.env` file using `.env.example` as a reference. Configure the database connection values for your environment. Do not commit `.env` or expose database passwords.

## Run the ETL Pipeline

```powershell
python -m src.etl
```

The pipeline processes the input datasets, validates records, writes clean CSV and Parquet outputs, saves rejected records, and records execution details in the logs directory.

## Load the Data Warehouse

Ensure PostgreSQL is running and the database settings in `.env` match the database you intend to use.

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

Open the dashboard at:

http://localhost:8501

The Compose PostgreSQL service is exposed on port 5433 on the host in the current configuration. Containers communicate using their configured Compose service names and internal ports.

## Output Directories

- `clean/`: validated datasets in CSV and Parquet formats.
- `rejected/`: records rejected during data-quality or referential validation.
- `logs/`: ETL execution logs and diagnostic information.

## Warehouse

The PostgreSQL warehouse includes employee, department, role, and date dimensions, along with attendance, leave, payroll, and monthly headcount facts.

## Validation and Verification

Review ETL logs for extraction counts, transformation results, rejected rows, and final validation status.

Check warehouse tables and row counts using PostgreSQL. Confirm that employee references are valid and that repeated loads do not create unintended duplicates.

Check the dashboard in a browser and verify that metrics, charts, date filters, and department filters work as expected.

## Documentation

- `docs/metric_dictionary.md`: definitions of dashboard metrics.
- `docs/dashboard_style_guide.md`: dashboard design and presentation guidance.

## Security

- Keep `.env` private.
- Use `.env.example` to document required configuration without real credentials.
- Do not commit passwords, database secrets, or private data.
- Restrict dashboard access to trusted users and networks.

## Current Status

The ETL pipeline has completed successfully in testing. Docker services have started successfully, the dashboard has returned HTTP 200, and expected row counts have been verified in the PostgreSQL warehouse. Final visual dashboard checks and repeatability checks should be completed before declaring the project fully finished.
