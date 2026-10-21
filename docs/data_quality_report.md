# PulseIQ Data Quality Report

## Overview

The PulseIQ warehouse data quality framework contains 14 SQL-based checks covering employee history, dimension references, attendance, leave, payroll, salary, and monthly headcount integrity.

## Latest Warehouse Validation

- Total checks: 14
- Passed: 14
- Failed: 0
- SQL errors: 0
- Exit code: 0
- Latest run ID: `252a638e-0818-4147-8814-e53005939e14`
- Results table: PostgreSQL `dq_results`

The latest run confirms that all 14 checks passed against the current warehouse data.

## Baseline Execution

The original baseline run also passed all 14 checks.

- Original run ID: `93ba6261-7945-413b-ad06-48f072a8da7c`

## Severity

- Critical checks: 12
- Warning checks: 2

Warning checks are DQ07 (attendance hours range) and DQ12 (duplicate payroll period).

## Negative Test Evidence

All 14 SQL detection rules were tested with deliberately invalid examples against isolated temporary tables.

- Tests executed: 14
- Detection tests passed: 14
- Failed or errored tests: 0
- Test script: `test_data_quality_checks.py`

Each test passed when its associated SQL query detected one or more violations. DQ14 detected two violations in its synthetic test data: a negative headcount and invalid references.

These tests validate SQL detection logic. They do not establish that every database constraint or the full runner's failure-handling and exit-code behavior has been tested.

## Database Constraint Evidence

The PostgreSQL constraint `ck_attendance_hours` rejected an attempted update setting attendance hours to 25. This confirms that the database prevents that invalid value from being stored.

Other inspected constraints include checks for payroll amounts, leave dates, salary amounts, nonnegative headcount, foreign keys, and duplicate business keys.

## Limitations and Next Steps

- Negative tests exercise SQL rules using temporary test tables, not invalid records inserted into permanent warehouse tables.
- The exit-policy function has dedicated unit tests. End-to-end tests of the complete runner's database-error handling remain a possible improvement.
- Additional constraint-specific tests may be added where required.
- The latest clean warehouse run is evidence of the current dataset's status, not proof that all possible future data will be valid.


## Runner Exit-Policy Tests

Four unit tests validated the `should_fail_run()` policy:

- Critical check failure: correctly requires exit code 1.
- Warning-only failure: correctly allows exit code 0.
- SQL error result: correctly requires exit code 1.
- All checks passing: correctly allows exit code 0.

Results: 4/4 passed. These tests exercise the exit-policy function, not the complete runner's database-error handling end to end.
