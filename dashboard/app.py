"""HydraJob Streamlit Dashboard — Overview Entry Point."""

from __future__ import annotations

import streamlit as st

from components.status_badge import format_status_badge_html
from components.system_view import render_service_health_strip, render_sidebar
from components.theme import (
    inject_editorial_theme,
    render_callout,
    render_page_hero,
    render_section_kicker,
)
from components.widgets import show_api_error
from services.api_client import build_api_client_from_env
from services.time_utils import format_kolkata_timestamp, now_kolkata_formatted


def _is_high_priority(app_or_job: dict) -> bool:
    priority = str(app_or_job.get("priority") or "").upper()
    score = app_or_job.get("match_score")
    return priority in {"HIGH", "HIGH_PRIORITY", "EXCELLENT"} or (
        isinstance(score, (int, float)) and score >= 85
    )


def main() -> None:
    """Render the HydraJob Overview dashboard page."""
    st.set_page_config(
        page_title="HydraJob — Overview",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_editorial_theme()

    with build_api_client_from_env() as client:
        render_sidebar(client.base_url, client.has_api_key)
        overview = client.fetch_overview()
        jobs_res = client.list_jobs(limit=100)
        apps_res = client.list_applications(limit=100)
        runs_res = client.list_discovery_runs(limit=10)
        failed_res = client.list_failed_sources(limit=10)

    render_page_hero(
        kicker="HydraJob · Workspace Overview",
        title="Job Discovery & Application Control",
        subtitle=(
            f"Snapshot updated {now_kolkata_formatted()} (Asia/Kolkata). "
            "All operations communicate exclusively with the FastAPI backend."
        ),
    )

    if not overview.health.reachable:
        render_callout(
            title="Backend Connection Unavailable",
            body=overview.health.error or "Cannot connect to FastAPI backend.",
            tone="critical",
        )

    render_section_kicker(
        number="01",
        label="Services",
        title="System Health Strip",
        subtitle="FastAPI, PostgreSQL, and Ollama status.",
    )
    render_service_health_strip(overview)

    jobs = jobs_res.items if jobs_res.ok else []
    apps = apps_res.items if apps_res.ok else []
    runs = runs_res.items if runs_res.ok else []
    failed_sources = failed_res.items if failed_res.ok else []

    if not jobs_res.ok:
        show_api_error(jobs_res, "Loading Jobs")
    if not apps_res.ok:
        show_api_error(apps_res, "Loading Applications")

    high_priority_count = sum(1 for item in apps if _is_high_priority(item))
    to_prepare_count = sum(
        1
        for item in apps
        if str(item.get("status") or "").upper() in {"DISCOVERED", "TO_APPLY", "PREPARING"}
    )
    submitted_count = sum(
        1
        for item in apps
        if str(item.get("status") or "").upper()
        not in {"DISCOVERED", "TO_APPLY", "PREPARING", "WITHDRAWN", "CLOSED"}
    )

    render_section_kicker(
        number="02",
        label="Pipeline Metrics",
        title="Discovery & Application Counters",
        subtitle="Active job records, high-priority targets, and submission queue.",
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Jobs Discovered", jobs_res.total if jobs_res.ok else "—")
    m2.metric("High-Priority Targets", high_priority_count if apps_res.ok else "—")
    m3.metric("Applications to Prepare", to_prepare_count if apps_res.ok else "—")
    m4.metric("Applications Submitted", submitted_count if apps_res.ok else "—")

    render_section_kicker(
        number="03",
        label="Deadlines & Activity",
        title="Upcoming Deadlines, Recent Scans & Failed Sources",
        subtitle="Time-sensitive job windows and discovery reliability.",
    )

    col_deadlines, col_scans = st.columns(2)
    with col_deadlines:
        st.markdown("**Upcoming Application Deadlines**")
        jobs_with_deadlines = [j for j in jobs if j.get("application_deadline")]
        jobs_with_deadlines.sort(key=lambda item: str(item.get("application_deadline")))
        if jobs_with_deadlines:
            for job in jobs_with_deadlines[:6]:
                deadline_ist = format_kolkata_timestamp(job.get("application_deadline"))
                st.markdown(
                    f"- **{job.get('title', 'Untitled')}** — Deadline: `{deadline_ist}`"
                )
        else:
            st.caption("No upcoming application deadlines recorded.")

    with col_scans:
        st.markdown("**Recent Source & Discovery Scans**")
        if runs:
            for run in runs[:6]:
                run_status = str(run.get("status") or "UNKNOWN")
                badge = format_status_badge_html(run_status, label_override=run_status)
                started = format_kolkata_timestamp(run.get("started_at"))
                st.markdown(
                    f"- **{run.get('run_type', 'RUN')}** {badge} · "
                    f"New: `{run.get('jobs_new', 0)}` · {started}",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No recent discovery scans recorded.")

    st.markdown("**Failed Sources Requiring Attention**")
    if failed_sources:
        for src in failed_sources[:6]:
            render_callout(
                title=f"{src.get('source_name', 'Source')} ({src.get('consecutive_failures', 0)} failures)",
                body=str(src.get("last_error") or "Scan failed; review source configuration."),
                tone="warning",
            )
    else:
        render_callout(
            title="All Monitored Sources Healthy",
            body="No career sources are currently flagged with scan failures.",
            tone="healthy",
        )


if __name__ == "__main__":
    main()
