
from datetime import date, timedelta
from uuid import uuid4

import pandas as pd

from src.db import get_connection
from src.warehouse import (
    ensure_employee_dimension,
    get_employee_key_as_of,
)


def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            today = date.today()
            employee_id = f"SCD2_TEST_{uuid4().hex[:12]}"

            employee = pd.DataFrame(
                [
                    {
                        "employee_id": employee_id,
                        "first_name": "Temporary",
                        "last_name": "Test",
                        "department": "SCD2 Test Department A",
                        "role": "SCD2 Test Role",
                        "joining_date": today - timedelta(days=10),
                        "leaving_date": None,
                    }
                ]
            )

            first_result = ensure_employee_dimension(
                cursor, employee
            )
            first_key = first_result[employee_id]

            changed_employee = employee.copy()
            changed_employee.loc[0, "department"] = (
                "SCD2 Test Department B"
            )

            second_result = ensure_employee_dimension(
                cursor, changed_employee
            )
            second_key = second_result[employee_id]

            assert first_key != second_key, (
                "FAIL: The department change did not create "
                "a new employee version."
            )

            cursor.execute(
                """
                SELECT employee_key, department_key,
                       effective_from, effective_to, is_current
                FROM dim_employee
                WHERE employee_id = %s
                ORDER BY effective_from
                """,
                (employee_id,),
            )
            versions = cursor.fetchall()

            assert len(versions) == 2, (
                f"FAIL: Expected 2 versions, got {len(versions)}."
            )

            old_version, new_version = versions

            assert old_version[0] == first_key
            assert old_version[3] == today - timedelta(days=1)
            assert old_version[4] is False
            assert new_version[0] == second_key
            assert new_version[2] == today
            assert new_version[4] is True

            yesterday_key = get_employee_key_as_of(
                cursor, employee_id, today - timedelta(days=1)
            )
            today_key = get_employee_key_as_of(
                cursor, employee_id, today
            )

            assert yesterday_key == first_key
            assert today_key == second_key

            print("PASS: A change created a new employee version.")
            print("PASS: The previous version was closed.")
            print("PASS: The new version is current.")
            print("PASS: Historical lookups return correct keys.")
            print("All SCD Type 2 checks passed.")

    finally:
        connection.rollback()
        connection.close()
        print("Transaction rolled back; test changes were not committed.")


if __name__ == "__main__":
    main()
