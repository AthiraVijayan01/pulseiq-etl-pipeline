
st.divider()
st.subheader("Predicted, not certain")

st.warning(
    "Risk scores are model predictions, not confirmed future exits. "
    "They must not be used alone to make employment decisions. Use them "
    "only as a signal for supportive, human-led review."
)

available_snapshots = sorted(risk["as_of_date"].dropna().unique())

if not available_snapshots:
    st.info("No prediction snapshot dates are available.")
else:
    snapshot_labels = {
        pd.Timestamp(value).strftime("%Y-%m-%d"): pd.Timestamp(value)
        for value in available_snapshots
    }

    selected_snapshot_label = st.selectbox(
        "Prediction snapshot date",
        list(snapshot_labels.keys()),
        index=len(snapshot_labels) - 1,
    )
    selected_snapshot = snapshot_labels[selected_snapshot_label]

    snapshot = risk[risk["as_of_date"] == selected_snapshot].copy()
    snapshot = (
        snapshot.dropna(subset=["employee_id"])
        .sort_values("as_of_date")
        .drop_duplicates("employee_id", keep="last")
    )

    employee_count = snapshot["employee_id"].nunique()

    if employee_count == 0:
        st.info("No predictions exist for this snapshot.")

    elif employee_count <= MIN_GROUP_SIZE:
        st.warning(
            f"This snapshot contains {employee_count} distinct employees. "
            "To protect privacy, the risk-band chart, department summaries, "
            "and reason-theme breakdown are hidden for this small cohort."
        )

        model_notes = snapshot["model_note"].dropna().unique()
        if len(model_notes):
            st.info(str(model_notes[0]))

    else:
        model_versions = sorted(
            snapshot["model_version"].dropna().astype(str).unique()
        )

        st.caption(
            f"Snapshot: {selected_snapshot_label} | "
            f"Employees scored: {employee_count:,} | "
            f"Model: {', '.join(model_versions) if model_versions else 'Not specified'}"
        )

        band_order = ["Low", "Medium", "High"]
        band_counts = (
            snapshot["risk_band"]
            .value_counts()
            .reindex(band_order, fill_value=0)
        )

        # If any risk band contains 1–4 employees, hide the whole
        # breakdown to avoid revealing the small band by subtraction.
        small_nonzero_band = (
            (band_counts > 0) & (band_counts < MIN_GROUP_SIZE)
        ).any()

        if small_nonzero_band:
            st.info(
                "The risk-band breakdown is hidden because at least one "
                "non-zero band contains fewer than five employees."
            )
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Employees scored", f"{employee_count:,}")
            c2.metric("High risk band", f"{int(band_counts['High']):,}")
            c3.metric("Medium risk band", f"{int(band_counts['Medium']):,}")

            band_chart = (
                band_counts.rename_axis("Risk band")
                .reset_index(name="Predicted employees")
            )

            fig = px.bar(
                band_chart,
                x="Risk band",
                y="Predicted employees",
                category_orders={"Risk band": band_order},
                labels={"Predicted employees": "Employees"},
            )
            st.plotly_chart(fig, use_container_width=True)

        # Department results are only displayed for groups of at least five.
        risk_department = (
            snapshot.groupby("department", as_index=False)
            .agg(
                employee_count=("employee_id", "nunique"),
                mean_risk_score=("risk_score_12m", "mean"),
                high_risk_count=(
                    "risk_band",
                    lambda values: int((values == "High").sum()),
                ),
                medium_risk_count=(
                    "risk_band",
                    lambda values: int((values == "Medium").sum()),
                ),
            )
        )

        risk_department = risk_department[
            risk_department["employee_count"] >= MIN_GROUP_SIZE
        ].copy()

        if risk_department.empty:
            st.info(
                "Department summaries are hidden because no department "
                "meets the minimum group size of five."
            )
        else:
            risk_department["mean_risk_score_pct"] = (
                risk_department["mean_risk_score"] * 100
            ).round(2)

            def safe_count_display(value):
                value = int(value)
                if 0 < value < MIN_GROUP_SIZE:
                    return "Suppressed (<5)"
                return str(value)

            risk_department["high_display"] = (
                risk_department["high_risk_count"].apply(safe_count_display)
            )
            risk_department["medium_display"] = (
                risk_department["medium_risk_count"].apply(safe_count_display)
            )

            st.subheader("Department risk summary")
            st.caption(
                "Only departments with at least five distinct employees are "
                "shown. Small non-zero risk-band counts are suppressed."
            )

            fig = px.bar(
                risk_department.sort_values(
                    "mean_risk_score_pct", ascending=False
                ),
                x="department",
                y="mean_risk_score_pct",
                labels={
                    "department": "Department",
                    "mean_risk_score_pct": "Average predicted risk score (%)",
                },
            )
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(
                risk_department[
                    [
                        "department",
                        "employee_count",
                        "mean_risk_score_pct",
                        "high_display",
                        "medium_display",
                    ]
                ].rename(
                    columns={
                        "department": "Department",
                        "employee_count": "Employees in group",
                        "mean_risk_score_pct": "Mean predicted risk (%)",
                        "high_display": "High-band count",
                        "medium_display": "Medium-band count",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

        # Count distinct employees per reason, not repeated reason-field entries.
        reason_columns = [
            "top_reason_1",
            "top_reason_2",
            "top_reason_3",
        ]

        reasons = snapshot[
            ["employee_id"] + reason_columns
        ].melt(
            id_vars=["employee_id"],
            value_vars=reason_columns,
            var_name="reason_rank",
            value_name="reason",
        )

        reasons["reason"] = (
            reasons["reason"].fillna("").astype(str).str.strip()
        )
        reasons = reasons[reasons["reason"] != ""]
        reasons = reasons.drop_duplicates(["employee_id", "reason"])

        if reasons.empty:
            st.info("No model reason themes are available for this snapshot.")
        else:
            reason_counts = (
                reasons.groupby("reason")["employee_id"]
                .nunique()
                .sort_values(ascending=False)
                .rename("Distinct employees")
                .reset_index()
            )

            reason_counts = reason_counts[
                reason_counts["Distinct employees"] >= MIN_GROUP_SIZE
            ].head(10)

            if reason_counts.empty:
                st.info(
                    "Reason themes are hidden because no theme is associated "
                    "with at least five distinct employees."
                )
            else:
                st.subheader("Common model reason themes")
                st.caption(
                    "Counts represent distinct employees associated with each "
                    "theme, not proof of causation. Themes involving fewer than "
                    "five employees are excluded."
                )
                st.dataframe(
                    reason_counts.rename(
                        columns={
                            "reason": "Model reason theme",
                            "Distinct employees": "Employees",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

        model_notes = snapshot["model_note"].dropna().unique()
        if len(model_notes):
            st.info(str(model_notes[0]))
