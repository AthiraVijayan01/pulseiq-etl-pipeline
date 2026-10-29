
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIRS = [PROJECT_DIR / "clean", PROJECT_DIR / "raw"]

st.set_page_config(
    page_title="PulseIQ | Team Productivity",
    page_icon="📈",
    layout="wide",
)


@st.cache_data
def load_csv(filename):
    for folder in DATA_DIRS:
        path = folder / filename
        if path.exists():
            return pd.read_csv(path)
    return pd.DataFrame()


def normalize_text(series):
    return series.fillna("").astype(str).str.strip().str.casefold()


def is_yes(series):
    return series.fillna("").astype(str).str.strip().str.upper().eq("Y")


def render_chart(fig):
    st.plotly_chart(fig, use_container_width=True)


tasks = load_csv("fact_task.csv")
teams = load_csv("dim_team.csv")
sprints = load_csv("dim_sprint.csv")

st.title("Team Productivity")
st.caption(
    "Sprint delivery, cycle time, completion reliability, blockers, and rework."
)

if tasks.empty or teams.empty or sprints.empty:
    st.error("Required task, team, or sprint data is missing from clean or raw.")
    st.stop()

required_task_columns = {
    "task_id",
    "team_id",
    "sprint_id",
    "status",
    "story_points",
    "cycle_time_days",
    "completed_on_time",
    "is_overdue_at_cutoff",
    "reopened_count",
}

missing_task_columns = required_task_columns - set(tasks.columns)

if missing_task_columns:
    st.error(
        "Missing task columns: "
        + ", ".join(sorted(missing_task_columns))
    )
    st.stop()

required_team_columns = {"team_id", "team_name"}
required_sprint_columns = {
    "sprint_id",
    "sprint_name",
    "start_date",
    "end_date",
}

missing_team_columns = required_team_columns - set(teams.columns)
missing_sprint_columns = required_sprint_columns - set(sprints.columns)

if missing_team_columns:
    st.error(
        "Missing team dimension columns: "
        + ", ".join(sorted(missing_team_columns))
    )
    st.stop()

if missing_sprint_columns:
    st.error(
        "Missing sprint dimension columns: "
        + ", ".join(sorted(missing_sprint_columns))
    )
    st.stop()

tasks = tasks.copy()
teams = teams.copy()
sprints = sprints.copy()

for column in ["story_points", "cycle_time_days", "reopened_count"]:
    tasks[column] = pd.to_numeric(tasks[column], errors="coerce")

tasks["team_id"] = tasks["team_id"].astype(str)
tasks["sprint_id"] = tasks["sprint_id"].astype(str)
teams["team_id"] = teams["team_id"].astype(str)
sprints["sprint_id"] = sprints["sprint_id"].astype(str)

sprints["start_date"] = pd.to_datetime(
    sprints["start_date"], errors="coerce"
)
sprints["end_date"] = pd.to_datetime(
    sprints["end_date"], errors="coerce"
)

team_names = (
    teams.drop_duplicates("team_id")
    .set_index("team_id")["team_name"]
    .to_dict()
)

sprint_names = (
    sprints.drop_duplicates("sprint_id")
    .set_index("sprint_id")["sprint_name"]
    .to_dict()
)

tasks["team_name"] = tasks["team_id"].map(team_names).fillna(tasks["team_id"])
tasks["sprint_name"] = (
    tasks["sprint_id"].map(sprint_names).fillna(tasks["sprint_id"])
)

tasks["status_normalized"] = normalize_text(tasks["status"])
tasks["is_done"] = tasks["status_normalized"].eq("done")
tasks["is_cancelled"] = tasks["status_normalized"].eq("cancelled")
tasks["is_blocked"] = tasks["status_normalized"].eq("blocked")
tasks["is_reopened"] = tasks["reopened_count"].fillna(0).gt(0)
tasks["is_overdue"] = is_yes(tasks["is_overdue_at_cutoff"])

sprint_options = sprints.sort_values(
    ["start_date", "sprint_id"], na_position="last"
).copy()

sprint_options["label"] = (
    sprint_options["sprint_name"].astype(str)
    + " ("
    + sprint_options["start_date"].dt.strftime("%Y-%m-%d").fillna("Unknown")
    + " to "
    + sprint_options["end_date"].dt.strftime("%Y-%m-%d").fillna("Unknown")
    + ")"
)

with st.sidebar:
    st.header("Filters")

    all_teams = sorted(tasks["team_name"].dropna().unique().tolist())

    selected_teams = st.multiselect(
        "Teams",
        options=all_teams,
        default=all_teams,
    )

    all_sprint_labels = sprint_options["label"].tolist()

    selected_sprints = st.multiselect(
        "Sprints",
        options=all_sprint_labels,
        default=all_sprint_labels,
    )

    selected_ids = sprint_options.loc[
        sprint_options["label"].isin(selected_sprints),
        "sprint_id",
    ].tolist()

filtered = tasks.loc[
    tasks["team_name"].isin(selected_teams)
    & tasks["sprint_id"].isin(selected_ids)
].copy()

if filtered.empty:
    st.warning("No tasks match the selected filters.")
    st.stop()

status = filtered["status_normalized"]

cancelled_mask = status.eq("cancelled")
done_mask = status.eq("done")
blocked_mask = status.eq("blocked")

completed = filtered.loc[done_mask].copy()

valid_cycle = completed.loc[
    completed["cycle_time_days"].notna()
    & completed["cycle_time_days"].ge(0)
].copy()

negative_cycle_count = int(
    (
        completed["cycle_time_days"].notna()
        & completed["cycle_time_days"].lt(0)
    ).sum()
)

missing_cycle_count = int(
    (
        completed["cycle_time_days"].isna()
        | completed["cycle_time_days"].lt(0)
    ).sum()
)

on_time_values = (
    completed["completed_on_time"]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
)

known_on_time = on_time_values.isin(["Y", "N"])
known_on_time_count = int(known_on_time.sum())

on_time_rate = (
    100 * on_time_values.loc[known_on_time].eq("Y").mean()
    if known_on_time_count
    else float("nan")
)

completed_points = completed["story_points"].fillna(0).sum()
blocked_count = int(blocked_mask.sum())
cancelled_count = int(cancelled_mask.sum())
overdue_count = int(filtered["is_overdue"].sum())
reopened_count = int(filtered["is_reopened"].sum())

st.subheader("Delivery overview")

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Tasks in scope", f"{len(filtered):,}")
c2.metric("Completed tasks", f"{len(completed):,}")
c3.metric("Completed story points", f"{completed_points:,.0f}")
c4.metric(
    "On-time completion",
    f"{on_time_rate:.1f}%" if pd.notna(on_time_rate) else "N/A",
)
c5.metric(
    "Median cycle time",
    f"{valid_cycle['cycle_time_days'].median():.1f} days"
    if not valid_cycle.empty
    else "N/A",
)

st.caption(
    f"On-time rate uses {known_on_time_count:,} completed tasks with a valid "
    "Y/N value. Cancelled tasks are excluded from completion-rate calculations."
)

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("Task status by team")

    status_data = (
        filtered.assign(
            status_label=filtered["status"].fillna("Unknown").astype(str)
        )
        .groupby(["team_name", "status_label"], as_index=False)
        .agg(task_count=("task_id", "nunique"))
    )

    fig = px.bar(
        status_data,
        x="team_name",
        y="task_count",
        color="status_label",
        barmode="stack",
        labels={
            "team_name": "Team",
            "task_count": "Tasks",
            "status_label": "Status",
        },
    )

    fig.update_layout(xaxis_tickangle=-35)
    render_chart(fig)

with right:
    st.subheader("Sprint velocity by team")

    sprint_order = sprint_options.loc[
        sprint_options["label"].isin(selected_sprints),
        "sprint_name",
    ].astype(str).tolist()

    completed_sprint_tasks = filtered.loc[filtered["is_done"]].copy()

    if completed_sprint_tasks.empty:
        st.info("No completed tasks are available for the selected sprints.")
        sprint_data = pd.DataFrame(
            columns=[
                "team_name",
                "sprint_id",
                "sprint_name",
                "completed_story_points",
                "completed_tasks",
            ]
        )
    else:
        sprint_data = (
            completed_sprint_tasks.groupby(
                ["team_name", "sprint_id", "sprint_name"],
                as_index=False,
            )
            .agg(
                completed_story_points=("story_points", "sum"),
                completed_tasks=("task_id", "nunique"),
            )
        )

        sprint_data["completed_story_points"] = (
            sprint_data["completed_story_points"].fillna(0)
        )
        sprint_data["sprint_name"] = sprint_data["sprint_name"].astype(str)
        sprint_data["sprint_order"] = sprint_data["sprint_name"].map(
            {name: index for index, name in enumerate(sprint_order)}
        )

        sprint_data = sprint_data.sort_values(
            "sprint_order", na_position="last"
        )

        fig = px.line(
            sprint_data,
            x="sprint_name",
            y="completed_story_points",
            color="team_name",
            markers=True,
            category_orders={"sprint_name": sprint_order},
            hover_data=["completed_tasks"],
            labels={
                "sprint_name": "Sprint",
                "completed_story_points": "Completed story points",
                "completed_tasks": "Completed tasks",
                "team_name": "Team",
            },
        )

        fig.update_layout(xaxis_tickangle=-35)
        render_chart(fig)

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("Cycle time by team")

    if valid_cycle.empty:
        st.info("No valid cycle-time records are available for this selection.")
        cycle_data = pd.DataFrame(
            columns=[
                "team_name",
                "median_cycle_time_days",
                "valid_completed_tasks",
            ]
        )
    else:
        cycle_data = (
            valid_cycle.groupby("team_name", as_index=False)
            .agg(
                median_cycle_time_days=("cycle_time_days", "median"),
                valid_completed_tasks=("task_id", "nunique"),
            )
            .sort_values("median_cycle_time_days")
        )

        fig = px.bar(
            cycle_data,
            x="team_name",
            y="median_cycle_time_days",
            hover_data=["valid_completed_tasks"],
            labels={
                "team_name": "Team",
                "median_cycle_time_days": "Median cycle time (days)",
                "valid_completed_tasks": "Valid completed tasks",
            },
        )

        fig.update_layout(xaxis_tickangle=-35)
        render_chart(fig)

with right:
    st.subheader("Delivery risks")

    risk_data = pd.DataFrame(
        {
            "Measure": [
                "Blocked tasks",
                "Overdue at cutoff",
                "Tasks reopened at least once",
                "Cancelled tasks",
            ],
            "Count": [
                blocked_count,
                overdue_count,
                reopened_count,
                cancelled_count,
            ],
        }
    )

    fig = px.bar(
        risk_data,
        x="Count",
        y="Measure",
        orientation="h",
        text="Count",
        labels={"Count": "Tasks"},
    )

    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    render_chart(fig)

st.divider()

st.subheader("Team summary")

team_summary = (
    filtered.groupby("team_name", as_index=False)
    .agg(
        tasks=("task_id", "nunique"),
        completed=("is_done", "sum"),
        cancelled=("is_cancelled", "sum"),
        blocked=("is_blocked", "sum"),
        reopened_tasks=("is_reopened", "sum"),
        overdue_tasks=("is_overdue", "sum"),
    )
)

completed_points_by_team = (
    completed.groupby("team_name")["story_points"]
    .sum(min_count=1)
    .rename("completed_story_points")
)

team_summary = team_summary.merge(
    completed_points_by_team,
    on="team_name",
    how="left",
)

team_summary["completed_story_points"] = (
    team_summary["completed_story_points"].fillna(0).round(0).astype("Int64")
)

denominator = team_summary["tasks"] - team_summary["cancelled"]

team_summary["completion_rate_pct"] = (
    100
    * team_summary["completed"]
    / denominator.where(denominator.ne(0))
).round(1)

team_summary = team_summary.sort_values(
    "completion_rate_pct",
    ascending=False,
    na_position="last",
)

st.dataframe(
    team_summary,
    use_container_width=True,
    hide_index=True,
    column_config={
        "team_name": st.column_config.TextColumn("Team"),
        "tasks": st.column_config.NumberColumn("Tasks", format="%d"),
        "completed": st.column_config.NumberColumn("Completed", format="%d"),
        "cancelled": st.column_config.NumberColumn("Cancelled", format="%d"),
        "blocked": st.column_config.NumberColumn("Blocked", format="%d"),
        "reopened_tasks": st.column_config.NumberColumn(
            "Reopened tasks", format="%d"
        ),
        "overdue_tasks": st.column_config.NumberColumn(
            "Overdue tasks", format="%d"
        ),
        "completed_story_points": st.column_config.NumberColumn(
            "Completed story points", format="%d"
        ),
        "completion_rate_pct": st.column_config.NumberColumn(
            "Completion rate (%)", format="%.1f%%"
        ),
    },
)

st.subheader("Blocked and reopened tasks by team")

risk_by_team = (
    filtered.groupby("team_name", as_index=False)
    .agg(
        blocked_tasks=("is_blocked", "sum"),
        reopened_tasks=("is_reopened", "sum"),
    )
)

risk_long = risk_by_team.melt(
    id_vars="team_name",
    value_vars=["blocked_tasks", "reopened_tasks"],
    var_name="risk_type",
    value_name="task_count",
)

risk_long["risk_type"] = risk_long["risk_type"].map(
    {
        "blocked_tasks": "Blocked tasks",
        "reopened_tasks": "Reopened tasks",
    }
)

fig = px.bar(
    risk_long,
    x="team_name",
    y="task_count",
    color="risk_type",
    barmode="group",
    labels={
        "team_name": "Team",
        "task_count": "Tasks",
        "risk_type": "Risk measure",
    },
)

fig.update_layout(xaxis_tickangle=-35)
render_chart(fig)

st.subheader("Three findings for the current selection")

if not sprint_data.empty:
    best_sprint = (
        sprint_data.groupby("sprint_name", as_index=False)
        .agg(completed_story_points=("completed_story_points", "sum"))
        .sort_values("completed_story_points", ascending=False)
        .iloc[0]
    )

    st.write(
        f"- Highest completed story-point total: **{best_sprint['sprint_name']}**, "
        f"with **{best_sprint['completed_story_points']:.0f} points**."
    )
else:
    st.write("- No completed story-point data is available for the selected sprints.")

if not cycle_data.empty:
    fastest = cycle_data.iloc[0]
    slowest = cycle_data.iloc[-1]

    st.write(
        f"- Team median cycle time ranged from "
        f"**{fastest['median_cycle_time_days']:.1f} days** "
        f"({fastest['team_name']}) to "
        f"**{slowest['median_cycle_time_days']:.1f} days** "
        f"({slowest['team_name']})."
    )
else:
    st.write("- No valid cycle-time data is available for the selected teams.")

highest_blocked = risk_by_team.sort_values(
    "blocked_tasks", ascending=False
).iloc[0]

st.write(
    f"- Highest blocker count: **{highest_blocked['team_name']}** has "
    f"**{int(highest_blocked['blocked_tasks']):,} blocked tasks** in the current selection. "
    f"Overall, the selection contains **{blocked_count:,} blocked**, "
    f"**{reopened_count:,} reopened**, and **{overdue_count:,} overdue** tasks."
)

with st.expander("Metric definitions and data-quality notes"):
    st.markdown(
        """
        - **Velocity:** sum of story points for tasks marked Done in each sprint.
        - **Completed tasks:** distinct task IDs with status Done.
        - **Completion rate:** Done tasks divided by all non-cancelled tasks.
        - **On-time completion:** Y divided by Y + N among completed tasks; missing or invalid values are excluded.
        - **Cycle time:** median of cycle_time_days for Done tasks with non-negative values.
        - **Blocked tasks:** tasks whose status is Blocked.
        - **Reopened tasks:** tasks with reopened_count greater than zero; each task is counted once.
        - **Overdue:** tasks marked Y in is_overdue_at_cutoff.
        - **Cancelled tasks:** reported separately and excluded from completion-rate denominators.
        - **Missing/negative cycle time:** excluded from cycle-time calculations.
        - **Story points:** completed story points include only tasks marked Done.
        - Team metrics are intended for process improvement, not individual employee ranking.
        """
    )

st.caption(
    f"Tasks in current selection: {len(filtered):,}. "
    f"Completed tasks excluded from cycle-time metrics due to missing or negative "
    f"cycle time: {missing_cycle_count:,}."
)
