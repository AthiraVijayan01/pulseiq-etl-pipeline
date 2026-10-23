from pathlib import Path

path = Path("src/warehouse.py")
source = path.read_text(encoding="utf-8")

if "def load_salary(" in source:
    raise SystemExit("STOP: load_salary() already exists; no changes made.")

function_anchor = "def load_monthly_headcount("
warehouse_anchor = '    leave = read_csv("leave")'
validation_anchor = '''    validate_columns(
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
'''
load_anchor = '''                results["employees"] = len(employee_keys)

                results["attendance"] = load_attendance(
'''

salary_function = '''def load_salary(
    cursor,
    salary: pd.DataFrame,
) -> int:
    validate_columns(
        salary,
        {"employee_id", "salary", "effective_date"},
        "salary",
    )

    from math import isfinite

    count = 0

    for row_number, row in salary.iterrows():
        employee_id = safe_text(row["employee_id"], "").strip()
        effective_date = as_date(row["effective_date"])
        raw_amount = pd.to_numeric(row["salary"], errors="coerce")

        if not employee_id or employee_id == UNKNOWN:
            raise ValueError(
                f"salary row {row_number}: employee_id is missing"
            )

        if effective_date is None:
            raise ValueError(
                f"salary row {row_number}: effective_date is invalid"
            )

        if pd.isna(raw_amount) or not isfinite(float(raw_amount)):
            raise ValueError(
                f"salary row {row_number}: salary must be a finite number"
            )

        salary_amount = float(raw_amount)

        if salary_amount < 0:
            raise ValueError(
                f"salary row {row_number}: salary cannot be negative"
            )

        employee_key = get_employee_key_as_of(
            cursor,
            employee_id,
            effective_date,
        )

        cursor.execute(
            """
            INSERT INTO fact_salary (
                employee_key,
                effective_date,
                salary_amount
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (employee_key, effective_date)
            DO UPDATE SET
                salary_amount = EXCLUDED.salary_amount
            """,
            (employee_key, effective_date, salary_amount),
        )

        count += 1

    return count


'''

checks = {
    "function insertion point": source.count(function_anchor) == 1,
    "salary read insertion point": source.count(warehouse_anchor) == 1,
    "leave validation block": source.count(validation_anchor) == 1,
    "fact loading insertion point": source.count(load_anchor) == 1,
}

failed = [name for name, passed in checks.items() if not passed]
if failed:
    raise SystemExit(
        "STOP: expected code was not found uniquely: "
        + ", ".join(failed)
        + ". No changes made."
    )

updated = source.replace(
    function_anchor,
    salary_function + function_anchor,
    1,
)

updated = updated.replace(
    warehouse_anchor,
    warehouse_anchor + '\n    salary = read_csv("salary")',
    1,
)

updated = updated.replace(
    validation_anchor,
    validation_anchor + '''
    validate_columns(
        salary,
        {"employee_id", "salary", "effective_date"},
        "salary",
    )
''',
    1,
)

updated = updated.replace(
    load_anchor,
    '''                results["employees"] = len(employee_keys)

                results["salary"] = load_salary(
                    cursor,
                    salary,
                )

                results["attendance"] = load_attendance(
''',
    1,
)

compile(updated, str(path), "exec")
path.write_text(updated, encoding="utf-8")
print("SUCCESS: salary loader added to src/warehouse.py")
print("Python syntax check passed.")
