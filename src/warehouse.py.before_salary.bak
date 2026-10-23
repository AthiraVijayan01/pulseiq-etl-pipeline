
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.db import database_connection


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLEAN_DIR = PROJECT_ROOT / "clean"
UNKNOWN = "Unknown"
OPEN_END_DATE = date(9999, 12, 31)


def read_csv(name: str) -> pd.DataFrame:
    path = CLEAN_DIR / f"{name}.csv"

    if not path.exists():
        raise FileNotFoundError(
            f"Required cleaned CSV file was not found: {path}"
        )

    return pd.read_csv(path)


def as_date(value) -> date | None:
    if value is None or pd.isna(value):
        return None

    if str(value).strip() == "":
        return None

    return pd.to_datetime(value, errors="raise").date()


def safe_text(value, default: str = UNKNOWN) -> str:
    if value is None or pd.isna(value):
        return default

    value = str(value).strip()

    if not value or value.lower() in {"nan", "none", "nat"}:
        return default

    return value


def date_key(value: date) -> int:
    return int(value.strftime("%Y%m%d"))


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def ensure_date(cursor, value: date) -> int:
    key = date_key(value)

    cursor.execute(
        """
        INSERT INTO dim_date (
            date_key,
            full_date,
            day_of_month,
            month_number,
            month_name,
            quarter_number,
            calendar_year,
            weekday_number,
            weekday_name,
            is_weekend
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (date_key) DO NOTHING
        """,
        (
            key,
            value,
            value.day,
            value.month,
            value.strftime("%B"),
            (value.month - 1) // 3 + 1,
            value.year,
            value.isoweekday(),
            value.strftime("%A"),
            value.isoweekday() >= 6,
        ),
    )

    return key


def ensure_named_key(
    cursor,
    table: str,
    key_column: str,
    name_column: str,
    value: str,
) -> int:
    allowed_dimensions = {
        ("dim_department", "department_key", "department_name"),
        ("dim_role", "role_key", "role_name"),
        ("dim_leave_type", "leave_type_key", "leave_type_name"),
    }

    if (table, key_column, name_column) not in allowed_dimensions:
        raise ValueError(
            f"Unsupported dimension configuration: {table}"
        )

    value = safe_text(value)

    cursor.execute(
        f"""
        INSERT INTO {table} ({name_column})
        VALUES (%s)
        ON CONFLICT ({name_column})
        DO UPDATE SET {name_column} = EXCLUDED.{name_column}
        RETURNING {key_column}
        """,
        (value,),
    )

    return cursor.fetchone()[0]


def ensure_employee_dimension(
    cursor,
    employees: pd.DataFrame,
) -> dict[str, int]:
    employee_keys: dict[str, int] = {}
    run_date = date.today()

    for _, row in employees.iterrows():
        employee_id = safe_text(row.get("employee_id"), "")

        if not employee_id:
            continue

        if employee_id in employee_keys:
            raise ValueError(
                f"Duplicate employee_id found in clean/employee.csv: "
                f"{employee_id}"
            )

        first_name = safe_text(row.get("first_name"))
        last_name = safe_text(row.get("last_name"))
        department = safe_text(row.get("department"))
        role = safe_text(row.get("role"))

        joining_date = as_date(row.get("joining_date"))
        leaving_date = as_date(row.get("leaving_date"))

        if (
            joining_date is not None
            and leaving_date is not None
            and joining_date > leaving_date
        ):
            raise ValueError(
                f"Employee {employee_id} has joining_date after leaving_date."
            )

        department_key = ensure_named_key(
            cursor,
            "dim_department",
            "department_key",
            "department_name",
            department,
        )

        role_key = ensure_named_key(
            cursor,
            "dim_role",
            "role_key",
            "role_name",
            role,
        )

        cursor.execute(
            """
            SELECT
                employee_key,
                first_name,
                last_name,
                department_key,
                role_key,
                joining_date,
                leaving_date,
                effective_from
            FROM dim_employee
            WHERE employee_id = %s
              AND is_current = TRUE
            """,
            (employee_id,),
        )

        existing = cursor.fetchone()

        if existing is None:
            cursor.execute(
                """
                SELECT MAX(effective_to)
                FROM dim_employee
                WHERE employee_id = %s
                """,
                (employee_id,),
            )

            previous_end = cursor.fetchone()[0]

            if previous_end is None:
                effective_from = joining_date or date(1900, 1, 1)
            else:
                effective_from = max(
                    run_date,
                    previous_end + timedelta(days=1),
                )

            cursor.execute(
                """
                INSERT INTO dim_employee (
                    employee_id,
                    first_name,
                    last_name,
                    department_key,
                    role_key,
                    joining_date,
                    leaving_date,
                    effective_from,
                    effective_to,
                    is_current
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                RETURNING employee_key
                """,
                (
                    employee_id,
                    first_name,
                    last_name,
                    department_key,
                    role_key,
                    joining_date,
                    leaving_date,
                    effective_from,
                    OPEN_END_DATE,
                ),
            )

            employee_key = cursor.fetchone()[0]

        else:
            (
                employee_key,
                old_first_name,
                old_last_name,
                old_department_key,
                old_role_key,
                old_joining_date,
                old_leaving_date,
                old_effective_from,
            ) = existing

            changed = (
                first_name != old_first_name
                or last_name != old_last_name
                or department_key != old_department_key
                or role_key != old_role_key
                or joining_date != old_joining_date
                or leaving_date != old_leaving_date
            )

            if changed:
                effective_from = max(
                    run_date,
                    old_effective_from + timedelta(days=1),
                )

                effective_to = effective_from - timedelta(days=1)

                cursor.execute(
                    """
                    UPDATE dim_employee
                    SET effective_to = %s,
                        is_current = FALSE
                    WHERE employee_key = %s
                    """,
                    (effective_to, employee_key),
                )

                cursor.execute(
                    """
                    INSERT INTO dim_employee (
                        employee_id,
                        first_name,
                        last_name,
                        department_key,
                        role_key,
                        joining_date,
                        leaving_date,
                        effective_from,
                        effective_to,
                        is_current
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                    RETURNING employee_key
                    """,
                    (
                        employee_id,
                        first_name,
                        last_name,
                        department_key,
                        role_key,
                        joining_date,
                        leaving_date,
                        effective_from,
                        OPEN_END_DATE,
                    ),
                )

                employee_key = cursor.fetchone()[0]

        employee_keys[employee_id] = employee_key

    return employee_keys


def get_employee_key(
    employee_keys: dict[str, int],
    employee_id,
) -> int:
    employee_id = safe_text(employee_id, "")

    if employee_id not in employee_keys:
        raise ValueError(
            f"Employee ID {employee_id!r} was not found in "
            "clean/employee.csv. Check the rejected employee records."
        )

    return employee_keys[employee_id]


def get_employee_key_as_of(
    cursor,
    employee_id,
    as_of_date: date,
) -> int:
    employee_id = safe_text(employee_id, "")

    cursor.execute(
        """
        SELECT employee_key
        FROM dim_employee
        WHERE employee_id = %s
          AND effective_from <= %s
          AND effective_to >= %s
        ORDER BY effective_from DESC
        LIMIT 1
        """,
        (employee_id, as_of_date, as_of_date),
    )

    result = cursor.fetchone()

    if result is None:
        raise ValueError(
            f"No employee dimension version exists for employee "
            f"{employee_id!r} on {as_of_date}."
        )

    return result[0]


def validate_columns(
    frame: pd.DataFrame,
    required_columns: set[str],
    filename: str,
) -> None:
    missing_columns = required_columns - set(frame.columns)

    if missing_columns:
        raise ValueError(
            f"clean/{filename}.csv is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )


def load_attendance(
    cursor,
    attendance: pd.DataFrame,
    employee_keys: dict[str, int],
) -> int:
    count = 0

    for _, row in attendance.iterrows():
        attendance_date = as_date(row.get("attendance_date"))

        if attendance_date is None:
            raise ValueError(
                "An attendance record is missing attendance_date."
            )

        employee_id = safe_text(row.get("employee_id"), "")

        get_employee_key(employee_keys, employee_id)

        employee_key = get_employee_key_as_of(
            cursor,
            employee_id,
            attendance_date,
        )

        dkey = ensure_date(cursor, attendance_date)
        status = safe_text(row.get("status"))
        hours_value = row.get("hours_worked")

        if (
            hours_value is None
            or pd.isna(hours_value)
            or str(hours_value).strip() == ""
        ):
            hours = None
        else:
            try:
                hours = float(hours_value)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid hours_worked value {hours_value!r} "
                    f"for employee {employee_id}."
                ) from error

            if not pd.notna(hours) or not 0 <= hours <= 24:
                raise ValueError(
                    f"Invalid hours_worked value {hours} "
                    f"for employee {employee_id}."
                )

        cursor.execute(
            """
            DELETE FROM fact_attendance
            WHERE date_key = %s
              AND employee_key IN (
                  SELECT employee_key
                  FROM dim_employee
                  WHERE employee_id = %s
              )
            """,
            (dkey, employee_id),
        )

        cursor.execute(
            """
            INSERT INTO fact_attendance (
                employee_key,
                date_key,
                attendance_status,
                hours_worked
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (employee_key, date_key)
            DO UPDATE SET
                attendance_status = EXCLUDED.attendance_status,
                hours_worked = EXCLUDED.hours_worked
            """,
            (employee_key, dkey, status, hours),
        )

        count += 1

    return count


def load_payroll(
    cursor,
    payroll: pd.DataFrame,
    employee_keys: dict[str, int],
) -> int:
    count = 0

    for _, row in payroll.iterrows():
        pay_period = as_date(row.get("pay_period"))

        if pay_period is None:
            raise ValueError("A payroll record is missing pay_period.")

        employee_id = safe_text(row.get("employee_id"), "")

        get_employee_key(employee_keys, employee_id)

        employee_key = get_employee_key_as_of(
            cursor,
            employee_id,
            pay_period,
        )

        pay_date = as_date(row.get("pay_date"))
        amounts: dict[str, float] = {}

        for column in ("gross_pay", "deductions", "net_pay"):
            value = row.get(column)

            if (
                value is None
                or pd.isna(value)
                or str(value).strip() == ""
            ):
                raise ValueError(
                    f"Payroll field {column} is missing for employee "
                    f"{employee_id}."
                )

            try:
                amount = float(value)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid {column} for employee "
                    f"{employee_id}: {value!r}"
                ) from error

            if not pd.notna(amount) or amount < 0:
                raise ValueError(
                    f"Invalid or negative {column} for employee "
                    f"{employee_id}."
                )

            amounts[column] = amount

        gross_pay = amounts["gross_pay"]
        deductions = amounts["deductions"]
        net_pay = amounts["net_pay"]

        if abs((gross_pay - deductions) - net_pay) > 0.02:
            raise ValueError(
                f"Payroll amounts do not reconcile for employee "
                f"{employee_id} in pay period {pay_period}."
            )

        cursor.execute(
            """
            DELETE FROM fact_payroll
            WHERE pay_period = %s
              AND employee_key IN (
                  SELECT employee_key
                  FROM dim_employee
                  WHERE employee_id = %s
              )
            """,
            (pay_period, employee_id),
        )

        cursor.execute(
            """
            INSERT INTO fact_payroll (
                employee_key,
                pay_period,
                pay_date,
                gross_pay,
                deductions,
                net_pay
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (employee_key, pay_period)
            DO UPDATE SET
                pay_date = EXCLUDED.pay_date,
                gross_pay = EXCLUDED.gross_pay,
                deductions = EXCLUDED.deductions,
                net_pay = EXCLUDED.net_pay
            """,
            (
                employee_key,
                pay_period,
                pay_date,
                gross_pay,
                deductions,
                net_pay,
            ),
        )

        count += 1

    return count


def load_leave(
    cursor,
    leave: pd.DataFrame,
    employee_keys: dict[str, int],
) -> int:
    count = 0

    for _, row in leave.iterrows():
        leave_start = as_date(row.get("leave_start"))
        leave_end = as_date(row.get("leave_end"))

        if leave_start is None or leave_end is None:
            raise ValueError(
                f"Leave record for employee {row.get('employee_id')} "
                "has a missing date."
            )

        if leave_start > leave_end:
            raise ValueError(
                f"Leave start is after leave end for employee "
                f"{row.get('employee_id')}."
            )

        employee_id = safe_text(row.get("employee_id"), "")

        get_employee_key(employee_keys, employee_id)

        employee_key = get_employee_key_as_of(
            cursor,
            employee_id,
            leave_start,
        )

        start_key = ensure_date(cursor, leave_start)
        end_key = ensure_date(cursor, leave_end)

        leave_type_key = ensure_named_key(
            cursor,
            "dim_leave_type",
            "leave_type_key",
            "leave_type_name",
            safe_text(row.get("leave_type")),
        )

        try:
            days = float(row.get("days"))
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Invalid leave days for employee {employee_id}."
            ) from error

        if not pd.notna(days) or days < 0:
            raise ValueError(
                f"Invalid leave days for employee {employee_id}."
            )

        cursor.execute(
            """
            DELETE FROM fact_leave
            WHERE employee_key IN (
                SELECT employee_key
                FROM dim_employee
                WHERE employee_id = %s
            )
              AND leave_start_key = %s
              AND leave_end_key = %s
              AND leave_type_key = %s
              AND days = %s
            """,
            (
                employee_id,
                start_key,
                end_key,
                leave_type_key,
                days,
            ),
        )

        cursor.execute(
            """
            INSERT INTO fact_leave (
                employee_key,
                leave_start_key,
                leave_end_key,
                leave_type_key,
                days
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                employee_key,
                start_key,
                end_key,
                leave_type_key,
                days,
            ),
        )

        count += 1

    return count


def load_monthly_headcount(
    cursor,
    employees: pd.DataFrame,
    attendance: pd.DataFrame,
    payroll: pd.DataFrame,
) -> int:
    observed_dates: list[date] = []

    for column, frame in (
        ("attendance_date", attendance),
        ("pay_period", payroll),
    ):
        if column in frame.columns:
            for value in frame[column].dropna():
                parsed = as_date(value)

                if parsed is not None:
                    observed_dates.append(parsed)

    for _, employee in employees.iterrows():
        joining_date = as_date(employee.get("joining_date"))
        leaving_date = as_date(employee.get("leaving_date"))

        if joining_date is not None:
            observed_dates.append(joining_date)

        if leaving_date is not None:
            observed_dates.append(leaving_date)

    if not observed_dates:
        return 0

    first_month = month_start(min(observed_dates))
    last_month = month_start(max(observed_dates))

    months: list[date] = []
    current_month = first_month

    while current_month <= last_month:
        months.append(current_month)

        if current_month.month == 12:
            current_month = date(current_month.year + 1, 1, 1)
        else:
            current_month = date(
                current_month.year,
                current_month.month + 1,
                1,
            )

    cursor.execute(
        "SELECT department_key FROM dim_department"
    )
    department_keys = [
        row[0] for row in cursor.fetchall()
    ]

    count = 0

    for current_month in months:
        if current_month.month == 12:
            next_month = date(current_month.year + 1, 1, 1)
        else:
            next_month = date(
                current_month.year,
                current_month.month + 1,
                1,
            )

        month_end = next_month - timedelta(days=1)
        month_date_key = ensure_date(cursor, current_month)
        totals: dict[int, int] = {}

        for _, employee in employees.iterrows():
            employee_id = safe_text(
                employee.get("employee_id"),
                "",
            )

            if not employee_id:
                continue

            joining_date = (
                as_date(employee.get("joining_date"))
                or date(1900, 1, 1)
            )
            leaving_date = as_date(employee.get("leaving_date"))

            employed_in_month = (
                joining_date <= month_end
                and (
                    leaving_date is None
                    or leaving_date > month_end
                )
            )

            if not employed_in_month:
                continue

            cursor.execute(
                """
                SELECT department_key
                FROM dim_employee
                WHERE employee_id = %s
                  AND effective_from <= %s
                  AND effective_to >= %s
                ORDER BY effective_from DESC
                LIMIT 1
                """,
                (employee_id, month_end, month_end),
            )

            version = cursor.fetchone()

            if version is None:
                continue

            department_key = version[0]

            totals[department_key] = (
                totals.get(department_key, 0) + 1
            )

        for department_key in department_keys:
            cursor.execute(
                """
                INSERT INTO fact_monthly_headcount (
                    month_key,
                    department_key,
                    headcount
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (month_key, department_key)
                DO UPDATE SET
                    headcount = EXCLUDED.headcount
                """,
                (
                    month_date_key,
                    department_key,
                    totals.get(department_key, 0),
                ),
            )

            count += 1

    return count


def load_warehouse() -> dict[str, int]:
    employees = read_csv("employee")
    attendance = read_csv("attendance")
    payroll = read_csv("payroll")
    leave = read_csv("leave")

    validate_columns(
        employees,
        {
            "employee_id",
            "first_name",
            "last_name",
            "department",
            "joining_date",
            "leaving_date",
        },
        "employee",
    )

    validate_columns(
        attendance,
        {
            "employee_id",
            "attendance_date",
            "status",
            "hours_worked",
        },
        "attendance",
    )

    validate_columns(
        payroll,
        {
            "employee_id",
            "pay_period",
            "pay_date",
            "gross_pay",
            "deductions",
            "net_pay",
        },
        "payroll",
    )

    validate_columns(
        leave,
        {
            "employee_id",
            "leave_start",
            "leave_end",
            "leave_type",
            "days",
        },
        "leave",
    )

    results: dict[str, int] = {}

    with database_connection() as connection:
        with connection.transaction():
            with connection.cursor() as cursor:
                employee_keys = ensure_employee_dimension(
                    cursor,
                    employees,
                )

                results["employees"] = len(employee_keys)

                results["attendance"] = load_attendance(
                    cursor,
                    attendance,
                    employee_keys,
                )

                results["payroll"] = load_payroll(
                    cursor,
                    payroll,
                    employee_keys,
                )

                results["leave"] = load_leave(
                    cursor,
                    leave,
                    employee_keys,
                )

                results["monthly_headcount"] = load_monthly_headcount(
                    cursor,
                    employees,
                    attendance,
                    payroll,
                )

    return results


if __name__ == "__main__":
    try:
        row_counts = load_warehouse()

        print("PulseIQ warehouse load completed successfully.")

        for table_name, count in row_counts.items():
            print(f"  {table_name}: {count} rows processed")

    except Exception as error:
        print("PulseIQ warehouse load failed.")
        print(f"Reason: {error}")
        raise
