from pathlib import Path

import pandas as pd

from src.db import get_connection


ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "clean"


TABLES = [
    {
        "file": "dim_date.csv",
        "table": "dim_date",
        "key": "date_key",
        "rename": {"date": "full_date"},
        "dates": {"full_date", "month_start_date", "month_end_date"},
        "booleans": {"is_weekend", "is_holiday", "is_working_day", "is_month_end"},
    },
    {
        "file": "dim_department.csv",
        "table": "dim_department",
        "key": "department_id",
        "rename": {},
        "dates": set(),
        "booleans": {"is_leadership"},
    },
    {
        "file": "dim_employee.csv",
        "table": "dim_employee",
        "key": "employee_key",
        "rename": {},
        "dates": {"date_of_birth", "hire_date", "exit_date", "valid_from", "valid_to"},
        "booleans": {"is_current"},
    },
    {
        "file": "dim_leave_type.csv",
        "table": "dim_leave_type",
        "key": "leave_type_code",
        "rename": {},
        "dates": set(),
        "booleans": {"prorated_for_joiners", "carry_forward_allowed"},
    },
    {
        "file": "fact_attendance_monthly.csv",
        "table": "fact_attendance_monthly",
        "key": "attendance_fact_id",
        "rename": {},
        "dates": {"period_end_date"},
        "booleans": set(),
    },
    {
        "file": "fact_leave.csv",
        "table": "fact_leave",
        "key": "leave_request_id",
        "rename": {},
        "dates": {"start_date", "end_date", "applied_on", "decided_on"},
        "booleans": set(),
    },
    {
        "file": "fact_headcount_monthly.csv",
        "table": "fact_headcount_monthly",
        "key": ["date_key", "department_id"],
        "rename": {},
        "dates": {"month_start_date"},
        "booleans": set(),
    },
    {
        "file": "fact_attrition_risk.csv",
        "table": "fact_attrition_risk",
        "key": "prediction_id",
        "rename": {},
        "dates": {"as_of_date"},
        "booleans": set(),
    },
]


def clean_value(value, column, date_columns, bool_columns):
    if pd.isna(value):
        return None

    if column in date_columns:
        return pd.to_datetime(value, errors="raise").date()

    if column in bool_columns:
        if isinstance(value, bool):
            return value

        normalized = str(value).strip().lower()

        if normalized in {"y", "yes", "true", "1"}:
            return True

        if normalized in {"n", "no", "false", "0"}:
            return False

        raise ValueError(
            f"Unexpected boolean value for {column}: {value!r}"
        )

    if hasattr(value, "item"):
        value = value.item()

    return value


def load_table(connection, config):
    path = CLEAN / config["file"]

    if not path.exists():
        raise FileNotFoundError(f"Missing input file: {path}")

    frame = pd.read_csv(path, low_memory=False)
    frame = frame.rename(columns=config["rename"])

    if config["table"] == "dim_date":
        weekday_numbers = {
            "Monday": 0,
            "Tuesday": 1,
            "Wednesday": 2,
            "Thursday": 3,
            "Friday": 4,
            "Saturday": 5,
            "Sunday": 6,
        }

        frame["day_of_week"] = (
            frame["day_of_week"]
            .astype(str)
            .str.strip()
            .map(weekday_numbers)
        )

        if frame["day_of_week"].isna().any():
            raise ValueError("Unknown weekday value found in dim_date.csv")

    if config["table"] == "fact_leave":
        starts = pd.to_datetime(frame["start_date"], errors="coerce")
        ends = pd.to_datetime(frame["end_date"], errors="coerce")
        invalid = starts.isna() | ends.isna() | (ends < starts)
        skipped = int(invalid.sum())
        frame = frame.loc[~invalid].copy()
        print(f"Invalid leave date ranges skipped: {skipped}")

    key_columns = config["key"]
    if isinstance(key_columns, str):
        key_columns = [key_columns]

    missing_keys = [
        column for column in key_columns if column not in frame.columns
    ]
    if missing_keys:
        raise ValueError(
            f"{config['file']} is missing key columns: {missing_keys}"
        )

    missing_columns = [
        column for column in frame.columns
        if frame[column].isna().all()
    ]
    if missing_columns:
        print(
            f"Warning: columns entirely empty in {config['file']}: "
            f"{missing_columns}"
        )

    if frame[key_columns].isna().any().any():
        raise ValueError(
            f"Null key values found in {config['file']}: {key_columns}"
        )

    if frame.duplicated(subset=key_columns).any():
        raise ValueError(
            f"Duplicate keys found in {config['file']}: {key_columns}"
        )

    columns = list(frame.columns)
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    conflict_target = ", ".join(f'"{column}"' for column in key_columns)

    update_columns = [
        column for column in columns if column not in key_columns
    ]

    if update_columns:
        updates = ", ".join(
            f'"{column}" = EXCLUDED."{column}"'
            for column in update_columns
        )
        conflict_action = f"DO UPDATE SET {updates}"
    else:
        conflict_action = "DO NOTHING"

    sql = (
        f'INSERT INTO phase2."{config["table"]}" ({quoted_columns}) '
        f"VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_target}) {conflict_action}"
    )

    rows = [
        tuple(
            clean_value(
                value,
                column,
                config["dates"],
                config["booleans"],
            )
            for column, value in zip(columns, record)
        )
        for record in frame.itertuples(index=False, name=None)
    ]

    with connection.cursor() as cursor:
        cursor.executemany(sql, rows)

    print(f"{config['table']}: processed {len(rows)} source rows")


def main():
    print("Loading Phase 2 CSV data into PostgreSQL...")
    print("Existing public schema will not be modified.")

    with get_connection() as connection:
        for config in TABLES:
            load_table(connection, config)

    print("\nPhase 2 data load completed successfully.")


if __name__ == "__main__":
    main()
