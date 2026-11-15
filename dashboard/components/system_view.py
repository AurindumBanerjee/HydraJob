"""Shared system status and sidebar helpers for the HydraJob dashboard."""

from __future__ import annotations

import html

import streamlit as st

from components.status_badge import format_status_badge_html, render_service_card
from components.theme import (
    inject_editorial_theme,
    render_callout,
    render_page_hero,
    render_section_kicker,
    render_summary_panel,
)
from services.api_client import SystemOverview, build_api_client_from_env
from services.time_utils import format_kolkata_timestamp, now_kolkata_formatted


def render_sidebar(api_base_url: str, has_api_key: bool) -> bool:
    """Render the common sidebar with connection metadata and refresh control."""
    with st.sidebar:
        st.markdown("### HydraJob Control")
        st.caption("Warm-Paper Editorial Console")
        st.markdown(f"**Backend URL:** `{api_base_url}`")
        st.markdown(
            f"**API Key Auth:** `{'Configured (X-API-Key)' if has_api_key else 'Not set'}`"
        )
        st.markdown("**Timezone:** `Asia/Kolkata`")
        refresh_clicked = st.button("Refresh View", use_container_width=True, type="primary")
        st.divider()
        st.caption(
            "Dashboard communicates exclusively with FastAPI over HTTP. "
            "PostgreSQL and Ollama remain isolated on the backend network."
        )
    return refresh_clicked


def resolve_service_states(overview: SystemOverview) -> tuple[str, str, str]:
    """Combine endpoint results to determine FastAPI, PostgreSQL, and Ollama states."""
    health = overview.health
    readiness = overview.readiness
    sys_status = overview.system_status

    if sys_status.reachable and sys_status.status_code == 200:
        fastapi_state = sys_status.fastapi.status
        postgres_state = sys_status.postgres.status
        ollama_state = sys_status.ollama.status
    else:
        fastapi_state = health.status if health.reachable else "unavailable"
        postgres_state = readiness.database_status if readiness.reachable else "unknown"
        ollama_state = sys_status.ollama.status if sys_status.reachable else "unknown"

    if postgres_state == "unknown" and readiness.reachable:
        postgres_state = readiness.database_status

    return fastapi_state, postgres_state, ollama_state


def render_service_health_strip(overview: SystemOverview) -> None:
    """Render a compact 3-service health strip for the Overview page."""
    fastapi_state, postgres_state, ollama_state = resolve_service_states(overview)
    sys_status = overview.system_status
    model_name = sys_status.ollama_model or sys_status.ollama.model or "Not configured"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_summary_panel(
            "FastAPI Backend",
            format_status_badge_html(fastapi_state),
            raw_html=True,
        )
    with c2:
        render_summary_panel(
            "PostgreSQL",
            format_status_badge_html(postgres_state),
            raw_html=True,
        )
    with c3:
        render_summary_panel(
            "Ollama LLM",
            format_status_badge_html(ollama_state),
            raw_html=True,
        )
    with c4:
        render_summary_panel("Active Model", model_name)


def render_phase0_dashboard(show_endpoint_breakdown: bool = True) -> None:
    """Fetch system status via FastAPI and render the System Health monitoring UI."""
    inject_editorial_theme()

    with build_api_client_from_env() as client:
        render_sidebar(client.base_url, client.has_api_key)
        overview = client.fetch_overview()
        runs_res = client.list_discovery_runs(limit=10)
        failed_res = client.list_failed_sources(limit=10)

    render_page_hero(
        kicker="HydraJob · System Health",
        title="Infrastructure, Services & Retries",
        subtitle=(
            "Live backend, PostgreSQL, Ollama, discovery scan timestamps, "
            "and failed ingestion retry status."
        ),
    )

    fastapi_state, postgres_state, ollama_state = resolve_service_states(overview)
    sys_status = overview.system_status

    overall = sys_status.overall_status
    if overall == "unknown":
        all_healthy = all(s == "healthy" for s in (fastapi_state, postgres_state, ollama_state))
        overall = "healthy" if all_healthy else "degraded"

    render_section_kicker(
        number="01",
        label="Overview",
        title="Platform Summary",
        subtitle="Aggregated readiness and Asia/Kolkata inspection timestamp.",
    )

    col_overall, col_env, col_time = st.columns([1.2, 1.0, 1.8])
    with col_overall:
        render_summary_panel(
            "Overall System Status",
            format_status_badge_html(overall),
            raw_html=True,
        )
    with col_env:
        render_summary_panel("Environment", sys_status.environment or "unknown")
    with col_time:
        checked_display = overview.checked_at_ist or now_kolkata_formatted()
        render_summary_panel("Dashboard Time (Asia/Kolkata)", checked_display)

    errors = [
        err
        for err in (overview.health.error, overview.readiness.error, sys_status.error)
        if err
    ]
    if errors:
        unique_errors = list(dict.fromkeys(errors))
        if not overview.health.reachable:
            render_callout(
                title="FastAPI Backend Unreachable",
                body=unique_errors[0],
                tone="critical",
            )
        else:
            for msg in unique_errors:
                render_callout(
                    title="Service Attention Required",
                    body=msg,
                    tone="warning",
                )

    render_section_kicker(
        number="02",
        label="Core Services",
        title="Subsystem Reachability",
        subtitle="FastAPI API tier, PostgreSQL source of truth, local Ollama, and n8n orchestrator.",
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_service_card(
            title="FastAPI Backend",
            status=fastapi_state,
            subtitle=f"Endpoint: {overview.api_base_url}",
            detail=sys_status.fastapi.detail
            or (
                f"HTTP {overview.health.status_code}"
                if overview.health.status_code
                else "Unreachable"
            ),
        )

    with c2:
        pg_detail = sys_status.postgres.detail
        if not pg_detail and overview.readiness.reachable:
            pg_detail = (
                "Readiness check passed" if overview.readiness.ready else "Readiness check failed"
            )
        render_service_card(
            title="PostgreSQL",
            status=postgres_state,
            subtitle="Single source of truth (via FastAPI)",
            detail=pg_detail or "Awaiting backend response",
        )

    with c3:
        model_name = sys_status.ollama_model or sys_status.ollama.model or "Not reported"
        ollama_detail = sys_status.ollama.detail
        if not ollama_detail:
            ollama_info = sys_status.raw.get("services", {}).get("ollama", {})
            if isinstance(ollama_info, dict) and "model_available" in ollama_info:
                avail = ollama_info["model_available"]
                if avail is True:
                    ollama_detail = "Configured model is pulled and available"
                elif avail is False:
                    ollama_detail = "Ollama reachable; configured model not yet pulled"
        render_service_card(
            title="Ollama LLM",
            status=ollama_state,
            subtitle=f"Configured model: {model_name}",
            detail=ollama_detail or "Checked via backend /api/v1/system/status",
        )

    with c4:
        render_service_card(
            title="n8n Orchestrator",
            status="info",
            subtitle="Scheduled triggers & webhook intake",
            detail="Calls FastAPI internal routes using X-API-Key",
        )

    render_section_kicker(
        number="03",
        label="Clock & Timezone",
        title="Backend Time Synchronization",
        subtitle="UTC storage canonical time paired with Asia/Kolkata user display.",
    )

    t_col1, t_col2 = st.columns(2)
    with t_col1:
        ist_source = sys_status.server_time_ist or sys_status.server_time_utc
        st.metric(
            label="Backend Time (Asia/Kolkata)",
            value=format_kolkata_timestamp(ist_source) if ist_source else "Unavailable",
        )
    with t_col2:
        st.metric(
            label="Backend Time (UTC)",
            value=sys_status.server_time_utc or "Unavailable",
        )

    render_section_kicker(
        number="04",
        label="Runs & Failures",
        title="Recent Discovery Runs & Failed Sources",
        subtitle="Latest background/scheduled ingestion runs and unresolved source failures.",
    )

    r_col1, r_col2 = st.columns(2)
    with r_col1:
        st.markdown("**Recent Ingestion & Discovery Runs**")
        if runs_res.ok and runs_res.items:
            for run in runs_res.items[:5]:
                run_id = str(run.get("id", ""))[:8]
                r_type = html.escape(str(run.get("run_type", "RUN")))
                r_status = str(run.get("status", "UNKNOWN"))
                started = format_kolkata_timestamp(run.get("started_at"))
                st.markdown(
                    f"- `{run_id}` · **{r_type}** · `{r_status}` · {started}"
                )
        elif runs_res.ok:
            st.caption("No discovery or ingestion runs recorded yet.")
        else:
            st.caption(runs_res.error or "Discovery runs endpoint unavailable.")

    with r_col2:
        st.markdown("**Failed Sources**")
        if failed_res.ok and failed_res.items:
            for src in failed_res.items[:5]:
                src_name = str(src.get("source_name") or src.get("id"))
                failures = src.get("consecutive_failures", 0)
                last_err = str(src.get("last_error") or "Unknown error")
                st.markdown(f"- **{src_name}** ({failures} failures): `{last_err}`")
        elif failed_res.ok:
            st.caption("No failing career sources reported.")
        else:
            st.caption(failed_res.error or "Failed sources endpoint unavailable.")

    render_section_kicker(
        number="05",
        label="Diagnostics",
        title="Endpoint Payloads",
        subtitle="Secret-free raw responses returned by FastAPI health endpoints.",
    )

    if show_endpoint_breakdown:
        e1, e2, e3 = st.columns(3)
        with e1:
            st.markdown("**GET `/health`**")
            st.caption(f"HTTP `{overview.health.status_code}`")
            st.json(overview.health.raw or {"error": overview.health.error})
        with e2:
            st.markdown("**GET `/health/ready`**")
            st.caption(
                f"HTTP `{overview.readiness.status_code}` · Ready: `{overview.readiness.ready}`"
            )
            st.json(overview.readiness.raw or {"error": overview.readiness.error})
        with e3:
            st.markdown("**GET `/api/v1/system/status`**")
            st.caption(f"HTTP `{sys_status.status_code}`")
            st.json(sys_status.raw or {"error": sys_status.error})
    else:
        with st.expander("Raw Backend Diagnostics (Secret-Free)", expanded=False):
            st.json(
                {
                    "health": overview.health.raw or {"error": overview.health.error},
                    "readiness": overview.readiness.raw or {"error": overview.readiness.error},
                    "system_status": sys_status.raw or {"error": sys_status.error},
                }
            )
