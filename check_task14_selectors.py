
import pandas as pd
from streamlit.testing.v1 import AppTest

PAGE = "dashboards/pages/9_AI_Signals.py"
FORECAST_FILE = "clean/fact_forecast.csv"

passed = 0
failed = 0


def check(name, condition):
    global passed, failed

    if condition:
        print(f"PASS: {name}")
        passed += 1
    else:
        print(f"FAIL: {name}")
        failed += 1


def check_page_errors(app):
    if app.exception:
        for error in app.exception:
            print("STREAMLIT ERROR:", error.message)
        raise RuntimeError("Dashboard page contains an exception")


def get_selectbox(app, label):
    matches = [
        widget for widget in app.selectbox
        if widget.label == label
    ]

    if not matches:
        raise RuntimeError(
            f"Selectbox not found: {label}"
        )

    return matches[0]


forecast = pd.read_csv(FORECAST_FILE)

print("=" * 60)
print("TASK 14 - STREAMLIT SELECTOR TEST")
print("=" * 60)

expected_metrics = {
    "headcount_end",
    "attrition_rate_monthly_pct",
}

expected_metric_labels = {
    "Ending headcount",
    "Monthly attrition rate",
}

expected_headcount_departments = set(
    forecast.loc[
        forecast["metric"] == "headcount_end",
        "department_id"
    ].dropna().unique()
)

expected_attrition_departments = set(
    forecast.loc[
        forecast["metric"] == "attrition_rate_monthly_pct",
        "department_id"
    ].dropna().unique()
)

# Run the actual Streamlit page
app = AppTest.from_file(
    PAGE,
    default_timeout=30
).run()

check_page_errors(app)

metric_widget = get_selectbox(
    app,
    "Select forecast metric"
)

department_widget = get_selectbox(
    app,
    "Select department"
)

# Test metric selector options
check(
    "Both forecast metric labels are available",
    set(metric_widget.options) == expected_metric_labels
)

check(
    "Underlying forecast metrics match source",
    expected_metrics == set(forecast["metric"].dropna().unique())
)

# Test attrition metric
metric_widget.set_value("attrition_rate_monthly_pct")
app.run()
check_page_errors(app)

metric_widget = get_selectbox(
    app,
    "Select forecast metric"
)

department_widget = get_selectbox(
    app,
    "Select department"
)

check(
    "Attrition metric can be selected",
    metric_widget.value == "attrition_rate_monthly_pct"
)

check(
    "Attrition department options match source",
    set(department_widget.options) == expected_attrition_departments
)

check(
    "ALL is available for attrition forecast",
    "ALL" in department_widget.options
)

# Test headcount metric
metric_widget.set_value("headcount_end")
app.run()
check_page_errors(app)

metric_widget = get_selectbox(
    app,
    "Select forecast metric"
)

department_widget = get_selectbox(
    app,
    "Select department"
)

check(
    "Headcount metric can be selected",
    metric_widget.value == "headcount_end"
)

check(
    "Headcount department options match source",
    set(department_widget.options) == expected_headcount_departments
)

check(
    "Headcount department options include ALL",
    "ALL" in department_widget.options
)

# Test individual department selection
individual_departments = [
    department
    for department in department_widget.options
    if department != "ALL"
]

if individual_departments:
    selected = individual_departments[0]

    department_widget.set_value(selected)
    app.run()
    check_page_errors(app)

    department_widget = get_selectbox(
        app,
        "Select department"
    )

    check(
        "Individual department can be selected",
        department_widget.value == selected
    )
else:
    check(
        "Individual department can be selected",
        False
    )

# Final result
print("\n" + "=" * 60)
print(f"RESULT: {passed} PASS | {failed} FAIL")
print("=" * 60)

if failed:
    raise SystemExit(1)
