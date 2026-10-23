
from pathlib import Path
from datetime import datetime, timezone
import json
import logging
import re

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent

RAW_DIR = PROJECT_DIR / "raw"
CLEAN_DIR = PROJECT_DIR / "clean"
REJECTED_DIR = PROJECT_DIR / "rejected"
LOG_DIR = PROJECT_DIR / "logs"

for folder in [CLEAN_DIR, REJECTED_DIR, LOG_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

RUN_ID = datetime.now(timezone.utc).strftime(
    "%Y%m%dT%H%M%S%fZ"
)

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


def normalize_column_name(column):
    name = str(column).strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def extract_data():
    if not RAW_DIR.exists():
        raise FileNotFoundError(
            f"Raw data folder not found: {RAW_DIR}"
        )

    files = sorted(RAW_DIR.glob("*.csv"))

    if not files:
        raise FileNotFoundError(
            f"No CSV files found in {RAW_DIR}"
        )

    datasets = {}

    logger.info(
        "EXTRACT | source_directory=%s | files=%d",
        RAW_DIR,
        len(files),
    )

    for file_path in files:
        name = file_path.stem.lower()

        if name in datasets:
            raise ValueError(
                f"Duplicate dataset name: {name}"
            )

        logger.info(
            "EXTRACT | Reading %s",
            file_path.name,
        )

        df = pd.read_csv(
            file_path,
            dtype="string",
            keep_default_na=False,
            low_memory=False,
        )

        df.columns = [
            normalize_column_name(column)
            for column in df.columns
        ]

        if not df.columns.is_unique:
            raise ValueError(
                f"{file_path.name} has duplicate column names "
                "after normalization"
            )

        datasets[name] = df

        logger.info(
            "EXTRACT | %s | rows=%d | columns=%d",
            file_path.name,
            len(df),
            len(df.columns),
        )

    return datasets


def transform_one(name, original):
    df = original.copy()
    rows_before = len(df)

    for column in df.columns:
        df[column] = (
            df[column]
            .astype("string")
            .str.strip()
        )

        df[column] = df[column].replace("", pd.NA)

    empty_rows = df.isna().all(axis=1)

    rejected = df.loc[empty_rows].copy()

    if not rejected.empty:
        rejected["rejection_reason"] = "Entire row is empty"

    clean = df.loc[~empty_rows].copy()

    logger.info(
        "TRANSFORM | %s | input=%d | clean=%d | rejected=%d",
        name,
        rows_before,
        len(clean),
        len(rejected),
    )

    return (
        clean.reset_index(drop=True),
        rejected.reset_index(drop=True),
    )


def transform_data(datasets):
    cleaned = {}
    rejected = {}

    for name, original in datasets.items():
        cleaned[name], rejected[name] = transform_one(
            name,
            original,
        )

    return cleaned, rejected


def load_data(cleaned, rejected):
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
            "LOAD | %s | rows=%d | CSV and Parquet saved",
            name,
            len(df),
        )

    for name, df in rejected.items():
        rejected_path = (
            REJECTED_DIR / f"{name}_rejected.csv"
        )

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


def write_run_log(
    start_time,
    cleaned,
    rejected,
    status,
    error=None,
):
    report = {
        "started_at_utc": start_time.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "source_directory": str(RAW_DIR),
        "source_csv_files": sorted(
            path.name for path in RAW_DIR.glob("*.csv")
        ) if RAW_DIR.exists() else [],
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
        logger.info("PulseIQ ETL started")
        logger.info("Source folder: %s", RAW_DIR)

        datasets = extract_data()
        cleaned, rejected = transform_data(datasets)
        load_data(cleaned, rejected)

        status = "SUCCESS"

        logger.info(
            "PulseIQ ETL completed successfully"
        )

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
