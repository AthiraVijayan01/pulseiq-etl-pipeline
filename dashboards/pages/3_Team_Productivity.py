
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

required = {
    "task_id", "team_id", "sprint_id", "status", "story_points",
    "cycle_time_days", "completed_on_time", "is_overdue_at_cutoff",
    "reopened_count",
}
missing = required - set(tasks.columns)

if missing:
    st.error(f"Missing required columns: {', '.join(sorted(missing))}")
    st.stop()

for col in ["story_points", "cycle_time_days", "reopened_count"]:
    tasks[col] = pd.to_numeric(tasks[col], errors="coerce")

for df in [tasks, teams, sprints]:
    if "team_id" in df.columns:
        df["team_id"] = df["team_id"].astype(str)
    if "sprint_id" in df.columns:
        df["sprint_id"] = df["sprint_id"].astype(str)

team_names = teams.set_index("team_id")["team_name"].to_dict()
sprint_names = sprints.set_index("sprint_id")["sprint_name"].to_dict()

tasks["team_name"] = tasks["team_id"].map(team_names).fillna(tasks["team_id"])
tasks["sprint_name"] = tasks["sprint_id"].map(sprint_names).fillna(tasks["sprint_id"])

with st.sidebar:
    st.header("Filters")

    all_teams = sorted(tasks["team_name"].dropna().unique().tolist())
    selected_teams = st.multiselect(
        "Teams",
        all_teams,
        default=all_teams,
    )

    sprint_options = sprints.sort_values("start_date").copy()
    sprint_options["label"] = (
        sprint_options["sprint_name"].astype(str)
        + " ("
        + sprint_options["start_date"].astype(str)
        + " to "
        + sprint_options["end_date"].astype(str)
        + ")"
    )

    selected_sprints = st.multiselect(
        "Sprints",
        sprint_options["label"].tolist(),
        default=sprint_options["label"].tolist(),
    )

    selected_ids = sprint_options.loc[
        sprint_options["label"].isin(selected_sprints), "sprint_id"
    ].tolist()

filtered = tasks[
    tasks["team_name"].isin(selected_teams)
    & tasks["sprint_id"].isin(selected_ids)
].copy()

if filtered.empty:
    st.warning("No tasks match the selected filters.")
    st.stop()

status = filtered["status"].fillna("").astype(str).str.casefold()
cancelled_mask = status.eq("cancelled")
done_mask = status.eq("done")
blocked_mask = status.eq("blocked")

eligible = filtered.loc[~cancelled_mask].copy()
eligible_status = eligible["status"].fillna("").astype(str).str.casefold()
completed = eligible.loc[eligible_status.eq("done")].copy()

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

on_time_values = completed["completed_on_time"].fillna("").astype(str).str.upper()
known_on_time = on_time_values.isin(["Y", "N"])
on_time_rate = (
    100 * on_time_values[known_on_time].eq("Y").mean()
    if known_on_time.any()
    else float("nan")
)

completed_points = completed["story_points"].fillna(0).sum()
blocked_count = int(blocked_mask.sum())
cancelled_count = int(cancelled_mask.sum())
overdue_count = int(
    filtered["is_overdue_at_cutoff"].fillna("").astype(str).str.upper().eq("Y").sum()
)
reopened_count = int((filtered["reopened_count"].fillna(0) > 0).sum())

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

st.divider()
left, right = st.columns(2)

with left:
    st.subheader("Task status by team")
    status_data = (
        filtered.groupby(["team_name", "status"], dropna=False)
        .size()
        .reset_index(name="task_count")
    )
    fig = px.bar(
        status_data,
        x="team_name",
        y="task_count",
        color="status",
        barmode="stack",
        labels={
            "team_name": "Team",
            "task_count": "Tasks",
            "status": "Status",
        },
    )
    fig.update_layout(xaxis_tickangle=-35)
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Sprint velocity")
    sprint_data = (
        filtered.assign(
            is_done=filtered["status"].fillna("").astype(str).str.casefold().eq("done")
        )
        .groupby(["sprint_id", "sprint_name"], as_index=False)
        .apply(
            lambda group: pd.Series({
                "completed_story_points": group.loc[
                    group["is_done"], "story_points"
                ].fillna(0).sum(),
                "completed_tasks": int(group["is_done"].sum()),
            }),
            include_groups=False,
        )
        .reset_index(drop=True)
    )

    fig = px.line(
        sprint_data,
        x="sprint_name",
        y="completed_story_points",
        markers=True,
        labels={
            "sprint_name": "Sprint",
            "completed_story_points": "Completed story points",
        },
    )
    fig.update_layout(xaxis_tickangle=-35)
    st.plotly_chart(fig, use_container_width=True)

st.divider()
left, right = st.columns(2)

with left:
    st.subheader("Cycle time by team")
    if valid_cycle.empty:
        st.info("No valid cycle-time records are available for this selection.")
    else:
        cycle_data = (
            valid_cycle.groupby("team_name", as_index=False)
            .agg(
                median_cycle_time_days=("cycle_time_days", "median"),
                valid_completed_tasks=("task_id", "count"),
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
        st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Delivery risks")
    risk_data = pd.DataFrame({
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
    })
    fig = px.bar(
        risk_data,
        x="Count",
        y="Measure",
        orientation="h",
        text="Count",
        labels={"Count": "Tasks"},
    )
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Team summary")

team_summary = (
    filtered.assign(
        is_done=filtered["status"].fillna("").astype(str).str.casefold().eq("done"),
        is_cancelled=filtered["status"].fillna("").astype(str).str.casefold().eq("cancelled"),
        is_blocked=filtered["status"].fillna("").astype(str).str.casefold().eq("blocked"),
        is_reopened=filtered["reopened_count"].fillna(0).gt(0),
    )
    .groupby("team_name", as_index=False)
    .agg(
        tasks=("task_id", "count"),
        completed=("is_done", "sum"),
        cancelled=("is_cancelled", "sum"),
        blocked=("is_blocked", "sum"),
        story_points=("story_points", "sum"),
        reopened_tasks=("is_reopened", "sum"),
    )
)

denominator = team_summary["tasks"] - team_summary["cancelled"]
team_summary["completion_rate_pct"] = (
    100 * team_summary["completed"] / denominator.where(denominator.ne(0))
).round(1)
team_summary["story_points"] = team_summary["story_points"].round(0).astype("Int64")
team_summary = team_summary.sort_values(
    "completion_rate_pct", ascending=False, na_position="last"
)
st.dataframe(team_summary, use_container_width=True, hide_index=True)

st.subheader("Three findings for the current selection")

if not sprint_data.empty:
    best_sprint = sprint_data.loc[
        sprint_data["completed_story_points"].idxmax()
    ]
    st.write(
        f"- Highest completed story-point total: **{best_sprint['sprint_name']}**, "
        f"with **{best_sprint['completed_story_points']:.0f} points**."
    )

if not valid_cycle.empty:
    fastest = cycle_data.iloc[0]
    slowest = cycle_data.iloc[-1]
    st.write(
        f"- Team median cycle time ranged from **{fastest['median_cycle_time_days']:.1f} days** "
        f"({fastest['team_name']}) to **{slowest['median_cycle_time_days']:.1f} days** "
        f"({slowest['team_name']})."
    )

st.write(
    f"- Current selection contains **{blocked_count:,} blocked**, "
    f"**{reopened_count:,} reopened**, and **{overdue_count:,} overdue** tasks."
)

with st.expander("Metric definitions and data-quality notes"):
    st.markdown(
        """
        - **Velocity:** sum of story points for tasks marked Done in each sprint.
        - **Completion rate:** Done tasks divided by all non-cancelled tasks.
        - **On-time completion:** Y divided by Y + N for completed tasks; missing values are excluded.
        - **Cycle time:** median of cycle_time_days for Done tasks with non-negative values.
        - **Blocked tasks:** tasks whose status is Blocked.
        - **Reopened tasks:** tasks with reopened_count greater than zero.
        - **Overdue:** tasks marked Y in is_overdue_at_cutoff.
        - **Cancelled tasks:** displayed separately and excluded from completion-rate denominators.
        - Negative cycle-time values are excluded from cycle-time metrics.
        - Team metrics are intended for process improvement, not individual employee ranking.
        """
    )

st.caption(
    f"Tasks in current selection: {len(filtered):,}. "
    f"Negative cycle-time records excluded from cycle-time calculations: {negative_cycle_count:,}."
)
