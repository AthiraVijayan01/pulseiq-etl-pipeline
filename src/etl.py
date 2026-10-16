
from pathlib import Path
from datetime import datetime, timezone
import json
import logging

import pandas as pd
import pandera.pandas as pa


PROJECT_DIR = Path(__file__).resolve().parent.parent

RAW_DIR = PROJECT_DIR / "raw"
CLEAN_DIR = PROJECT_DIR / "clean"
REJECTED_DIR = PROJECT_DIR / "rejected"
LOG_DIR = PROJECT_DIR / "logs"

FILES = ["employee", "salary", "attendance", "leave", "payroll"]

REFERENCE_DATE = pd.Timestamp("2025-12-31")

DATE_COLUMNS = {
    "employee": ["joining_date", "leaving_date"],
    "salary": ["effective_date"],
    "attendance": ["attendance_date"],
    "leave": ["leave_start", "leave_end"],
    "payroll": ["pay_period", "pay_date"],
}

NUMERIC_COLUMNS = {
    "salary": ["salary"],
    "attendance": ["hours_worked"],
    "leave": ["days"],
    "payroll": ["gross_pay", "deductions", "net_pay"],
}

REQUIRED_COLUMNS = {
    "employee": [
        "employee_id",
        "first_name",
        "last_name",
        "department",
        "joining_date",
        "leaving_date",
        "role",
    ],
    "salary": ["employee_id", "salary", "effective_date"],
    "attendance": [
        "employee_id",
        "attendance_date",
        "status",
        "hours_worked",
    ],
    "leave": [
        "employee_id",
        "leave_start",
        "leave_end",
        "leave_type",
        "days",
    ],
    "payroll": [
        "employee_id",
        "pay_period",
        "pay_date",
        "gross_pay",
        "deductions",
        "net_pay",
    ],
}

for folder in [CLEAN_DIR, REJECTED_DIR, LOG_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            LOG_DIR / f"etl_{RUN_ID}.log",
            encoding="utf-8",
        ),
    ],
)

logger = logging.getLogger("PulseIQ")


def extract_data():
    datasets = {}

    logger.info("PulseIQ ETL pipeline started")

    for name in FILES:
        file_path = RAW_DIR / f"{name}.csv"

        if not file_path.exists():
            raise FileNotFoundError(
                f"Required input file is missing: {file_path}"
            )

        df = pd.read_csv(
            file_path,
            dtype={"employee_id": "string"},
        )

        df.columns = [
            str(column).strip().lower()
            for column in df.columns
        ]

        missing_columns = set(REQUIRED_COLUMNS[name]) - set(df.columns)

        if missing_columns:
            raise ValueError(
                f"{name}.csv is missing required columns: "
                f"{sorted(missing_columns)}"
            )

        datasets[name] = df

        logger.info(
            "EXTRACT | %s | rows_in=%d",
            name,
            len(df),
        )

    return datasets


def standardize_names(df):
    text_columns = [
        "first_name",
        "last_name",
        "department",
        "role",
        "leave_type",
        "status",
    ]

    for column in text_columns:
        if column not in df.columns:
            continue

        df[column] = (
            df[column]
            .astype("string")
            .str.strip()
            .replace("", pd.NA)
        )

    for column in [
        "first_name",
        "last_name",
        "department",
        "role",
    ]:
        if column in df.columns:
            df[column] = df[column].str.title()

    return df


def transform_one(name, original):
    df = original.copy()
    rows_before = len(df)

    df["employee_id"] = (
        df["employee_id"]
        .astype("string")
        .str.strip()
        .str.upper()
        .replace("", pd.NA)
    )

    df = standardize_names(df)

    invalid_date_masks = {}

    for column in DATE_COLUMNS[name]:
        raw_values = df[column]

        nonblank = (
            raw_values.notna()
            & raw_values.astype("string").str.strip().ne("")
        )

        parsed = pd.to_datetime(raw_values, errors="coerce")

        invalid_date_masks[column] = nonblank & parsed.isna()
        df[column] = parsed

    for column in NUMERIC_COLUMNS.get(name, []):
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.drop_duplicates().copy()
    rejected_parts = []

    def reject_rows(mask, reason):
        nonlocal df

        mask = (
            pd.Series(mask, index=df.index)
            .fillna(False)
            .astype(bool)
        )

        if not mask.any():
            return

        bad_rows = df.loc[mask].copy()
        bad_rows["rejection_reason"] = reason
        rejected_parts.append(bad_rows)
        df = df.loc[~mask].copy()

    reject_rows(
        df["employee_id"].isna(),
        "Missing employee_id",
    )

    for column, mask in invalid_date_masks.items():
        reject_rows(mask, f"Invalid {column}")

    for column in DATE_COLUMNS[name]:
        if name == "employee" and column == "leaving_date":
            continue

        reject_rows(
            df[column].isna(),
            f"Missing or invalid {column}",
        )

    if name == "employee":
        reject_rows(
            df["first_name"].isna() | df["last_name"].isna(),
            "Missing first_name or last_name",
        )

        reject_rows(
            df["role"].isna(),
            "Missing role",
        )

        reject_rows(
            df["joining_date"].notna()
            & df["leaving_date"].notna()
            & (df["joining_date"] > df["leaving_date"]),
            "Joining date is after leaving date",
        )

        reject_rows(
            df["employee_id"].notna()
            & df["employee_id"].duplicated(keep="first"),
            "Duplicate employee_id",
        )

        df["tenure_days"] = (
            REFERENCE_DATE - df["joining_date"]
        ).dt.days

        df["tenure_years"] = (
            df["tenure_days"] / 365.25
        ).round(2)

        reject_rows(
            df["tenure_days"] < 0,
            "Joining date is after reference date",
        )

    for column in NUMERIC_COLUMNS.get(name, []):
        reject_rows(
            df[column].isna(),
            f"Missing or invalid {column}",
        )

        reject_rows(
            df[column] < 0,
            f"Negative {column} is not allowed",
        )

    if name == "attendance":
        reject_rows(
            df["hours_worked"] > 24,
            "hours_worked exceeds 24",
        )

    if name == "leave":
        reject_rows(
            df["leave_start"].notna()
            & df["leave_end"].notna()
            & (df["leave_start"] > df["leave_end"]),
            "leave_start is after leave_end",
        )

    if name == "payroll":
        reject_rows(
            df["net_pay"].notna()
            & df["gross_pay"].notna()
            & (df["net_pay"] > df["gross_pay"]),
            "net_pay exceeds gross_pay",
        )

        reject_rows(
            df["deductions"].notna()
            & df["gross_pay"].notna()
            & df["net_pay"].notna()
            & (
                (
                    df["gross_pay"]
                    - df["deductions"]
                    - df["net_pay"]
                ).abs() > 0.02
            ),
            "gross_pay minus deductions does not equal net_pay",
        )

    helper_dates = {
        "salary": "effective_date",
        "attendance": "attendance_date",
        "leave": "leave_start",
        "payroll": "pay_period",
    }

    helper_date = helper_dates.get(name)

    if helper_date:
        df["month"] = df[helper_date].dt.month
        df["year"] = df[helper_date].dt.year

    if name == "employee" and not df.empty:
        employee_schema = pa.DataFrameSchema(
            {
                "employee_id": pa.Column(
                    str,
                    nullable=False,
                    unique=True,
                ),
                "joining_date": pa.Column(
                    pd.Timestamp,
                    nullable=False,
                ),
            },
            strict=False,
        )

        employee_schema.validate(df, lazy=True)

    if name == "salary" and not df.empty:
        salary_schema = pa.DataFrameSchema(
            {
                "employee_id": pa.Column(
                    str,
                    nullable=False,
                ),
                "salary": pa.Column(
                    float,
                    nullable=False,
                    checks=pa.Check.ge(0),
                    coerce=True,
                ),
            },
            strict=False,
        )

        salary_schema.validate(df, lazy=True)

    rejected = (
        pd.concat(rejected_parts, ignore_index=True, sort=False)
        if rejected_parts
        else pd.DataFrame(
            columns=list(df.columns) + ["rejection_reason"]
        )
    )

    logger.info(
        "TRANSFORM | %s | input=%d | clean=%d | rejected=%d",
        name,
        rows_before,
        len(df),
        len(rejected),
    )

    return df.reset_index(drop=True), rejected.reset_index(drop=True)


def transform_data(datasets):
    cleaned = {}
    rejected = {}

    for name, original in datasets.items():
        cleaned[name], rejected[name] = transform_one(
            name,
            original,
        )

    return cleaned, rejected


def reject_orphan_employee_records(cleaned, rejected):
    valid_employee_ids = set(
        cleaned["employee"]["employee_id"]
        .dropna()
        .astype("string")
        .str.strip()
        .str.upper()
    )

    for name in ["salary", "attendance", "leave", "payroll"]:
        df = cleaned[name].copy()

        if df.empty:
            continue

        employee_ids = (
            df["employee_id"]
            .astype("string")
            .str.strip()
            .str.upper()
        )

        invalid_mask = ~employee_ids.isin(valid_employee_ids)

        if not invalid_mask.any():
            continue

        invalid_rows = df.loc[invalid_mask].copy()
        invalid_rows["rejection_reason"] = (
            "Employee ID not found in clean employee data"
        )

        rejected[name] = pd.concat(
            [rejected[name], invalid_rows],
            ignore_index=True,
            sort=False,
        )

        cleaned[name] = (
            df.loc[~invalid_mask]
            .copy()
            .reset_index(drop=True)
        )

        logger.warning(
            "REFERENTIAL VALIDATION | %s | rejected=%d",
            name,
            len(invalid_rows),
        )


def validate_data(cleaned):
    logger.info("VALIDATION | Starting final checks")

    employees = cleaned["employee"]

    if employees["employee_id"].isna().any():
        raise ValueError(
            "Clean employee data contains missing IDs"
        )

    if employees["employee_id"].duplicated().any():
        raise ValueError(
            "Clean employee data contains duplicate IDs"
        )

    if employees["role"].isna().any():
        raise ValueError(
            "Clean employee data contains missing roles"
        )

    valid_employee_ids = set(
        employees["employee_id"].astype(str)
    )

    for name in ["salary", "attendance", "leave", "payroll"]:
        related_ids = set(
            cleaned[name]["employee_id"].astype(str)
        )

        if not related_ids.issubset(valid_employee_ids):
            raise ValueError(
                f"Clean {name} data contains an unknown employee ID"
            )

    salaries = cleaned["salary"]

    if salaries["salary"].isna().any():
        raise ValueError(
            "Clean salary data contains missing salaries"
        )

    if (salaries["salary"] < 0).any():
        raise ValueError(
            "Clean salary data contains negative salaries"
        )

    logger.info("VALIDATION | All final checks passed")


def load_data(cleaned, rejected):
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)

    for name, df in cleaned.items():
        csv_path = CLEAN_DIR / f"{name}.csv"
        parquet_path = CLEAN_DIR / f"{name}.parquet"

        df.to_csv(
            csv_path,
            index=False,
            date_format="%Y-%m-%d",
            na_rep="",
        )

        df.to_parquet(
            parquet_path,
            index=False,
        )

        logger.info(
            "LOAD | %s | CSV and Parquet written | rows=%d",
            name,
            len(df),
        )

    for name, df in rejected.items():
        rejected_path = REJECTED_DIR / f"{name}_rejected.csv"

        df.to_csv(
            rejected_path,
            index=False,
            date_format="%Y-%m-%d",
            na_rep="",
        )

        logger.info(
            "REJECTED | %s | rows=%d",
            name,
            len(df),
        )


def write_run_log(start_time, cleaned, rejected, status, error=None):
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "started_at_utc": start_time.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "clean_rows": {
            name: len(df)
            for name, df in cleaned.items()
        },
        "rejected_rows": {
            name: len(df)
            for name, df in rejected.items()
        },
    }

    if error:
        report["error"] = error

    log_path = LOG_DIR / f"etl_{RUN_ID}.json"

    log_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )


def main():
    start_time = datetime.now(timezone.utc)
    cleaned = {}
    rejected = {}
    status = "FAILED"
    error = None

    try:
        datasets = extract_data()
        cleaned, rejected = transform_data(datasets)
        reject_orphan_employee_records(cleaned, rejected)
        validate_data(cleaned)
        load_data(cleaned, rejected)

        status = "SUCCESS"
        logger.info("PulseIQ ETL completed successfully")

    except Exception as exc:
        error = str(exc)
        logger.exception("ETL FAILED")
        raise

    finally:
        write_run_log(
            start_time,
            cleaned,
            rejected,
            status,
            error,
        )


if __name__ == "__main__":
    main()
