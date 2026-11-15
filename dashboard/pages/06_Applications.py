"""Applications page: Kanban pipeline, manual transitions, and event audit history."""

from __future__ import annotations

import html

import streamlit as st

from components.status_badge import format_status_badge_html
from components.system_view import render_sidebar
from components.theme import (
    PALETTE,
    inject_editorial_theme,
    render_callout,
    render_page_hero,
    render_section_kicker,
)
from components.widgets import pagination_controls, show_api_error
from services.api_client import build_api_client_from_env
from services.time_utils import format_kolkata_timestamp

ALL_APPLICATION_STATUSES = [
    "DISCOVERED",
    "TO_APPLY",
    "PREPARING",
    "APPLIED",
    "ACKNOWLEDGED",
    "UNDER_REVIEW",
    "OA_RECEIVED",
    "OA_COMPLETED",
    "TECHNICAL_TEST",
    "INTERVIEW_SCHEDULED",
    "INTERVIEW_COMPLETED",
    "FURTHER_ROUNDS",
    "OFFER_RECEIVED",
    "REJECTED",
    "WITHDRAWN",
    "CLOSED",
]

KANBAN_LANES: list[tuple[str, set[str]]] = [
    ("Prepare", {"DISCOVERED", "TO_APPLY", "PREPARING"}),
    ("Applied & Review", {"APPLIED", "ACKNOWLEDGED", "UNDER_REVIEW"}),
    ("Assessments & Interviews", {"OA_RECEIVED", "OA_COMPLETED", "TECHNICAL_TEST", "INTERVIEW_SCHEDULED", "INTERVIEW_COMPLETED", "FURTHER_ROUNDS"}),
    ("Outcomes", {"OFFER_RECEIVED", "REJECTED", "WITHDRAWN", "CLOSED"}),
]


def _render_kanban_card(app: dict, job_title: str, resume_name: str) -> None:
    status_str = str(app.get("status") or "DISCOVERED")
    score = app.get("match_score")
    score_label = f"{score}/100" if score is not None else "—"
    badge = format_status_badge_html(status_str, label_override=status_str)
    st.markdown(
        f'<div style="padding:10px 12px;margin-bottom:8px;border-radius:6px;'
        f'border:1px solid {PALETTE["rule"]};background-color:{PALETTE["paper_warm"]};">'
        f'<div style="font-weight:650;font-size:0.9rem;color:{PALETTE["ink"]};">'
        f"{html.escape(job_title)}</div>"
        f'<div style="margin:6px 0;">{badge}</div>'
        f'<div style="font-size:0.78rem;color:{PALETTE["graphite"]};">'
        f"Score: {html.escape(score_label)} · Resume: {html.escape(resume_name)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    """Render the Kanban-style Applications pipeline and audit history view."""
    st.set_page_config(page_title="HydraJob — Applications", layout="wide")
    inject_editorial_theme()

    with build_api_client_from_env() as client:
        render_sidebar(client.base_url, client.has_api_key)

    render_page_hero(
        kicker="HydraJob · Phase 1 & 6",
        title="Application Pipeline",
        subtitle=(
            "Track applications across all 16 lifecycle statuses. "
            "Every transition records an immutable ApplicationEvent."
        ),
    )

    f1, f2 = st.columns([1.5, 1.5])
    status_filter = f1.selectbox(
        "Filter by Status",
        options=["", *ALL_APPLICATION_STATUSES],
        key="apps_status_filter",
    )
    priority_filter = f2.selectbox(
        "Filter by Priority",
        options=["", "HIGH", "MEDIUM", "LOW"],
        key="apps_priority_filter",
    )

    with build_api_client_from_env() as client:
        init_apps = client.list_applications(
            status=status_filter or None,
            priority=priority_filter or None,
            limit=50,
            offset=0,
        )
        jobs_res = client.list_jobs(limit=200)
        resumes_res = client.list_resumes(limit=100)

    if show_api_error(init_apps, "Loading Applications"):
        return

    jobs_by_id = {
        str(j.get("id")): j for j in (jobs_res.items if jobs_res.ok else [])
    }
    resumes_by_id = {
        str(r.get("id")): str(r.get("name", "Resume"))
        for r in (resumes_res.items if resumes_res.ok else [])
    }

    limit, offset = pagination_controls("applications", init_apps.total, default_limit=50)
    if offset > 0 or limit != 50:
        with build_api_client_from_env() as client:
            apps_res = client.list_applications(
                status=status_filter or None,
                priority=priority_filter or None,
                limit=limit,
                offset=offset,
            )
    else:
        apps_res = init_apps

    apps = apps_res.items

    render_section_kicker(
        number="01",
        label="Pipeline",
        title=f"Kanban Board ({apps_res.total})",
    )
    if not apps:
        render_callout(
            "No Applications Yet",
            "Create an application from the Jobs page to start tracking progress.",
            tone="info",
        )
        return

    lane_cols = st.columns(len(KANBAN_LANES))
    for idx, (lane_name, lane_statuses) in enumerate(KANBAN_LANES):
        with lane_cols[idx]:
            lane_items = [
                a for a in apps if str(a.get("status") or "").upper() in lane_statuses
            ]
            st.markdown(f"**{lane_name} ({len(lane_items)})**")
            for item in lane_items:
                job_obj = jobs_by_id.get(str(item.get("job_id")), {})
                job_title = str(job_obj.get("title") or f"Job {str(item.get('job_id'))[:8]}")
                res_name = resumes_by_id.get(str(item.get("selected_resume_id")), "Unassigned")
                _render_kanban_card(item, job_title, res_name)

    render_section_kicker(
        number="02",
        label="Detail & Transitions",
        title="Inspect Application & Update Status",
        subtitle="HydraJob never auto-submits applications; manual transitions preserve full history.",
    )

    app_options = {
        f"{jobs_by_id.get(str(a.get('job_id')), {}).get('title', str(a.get('job_id'))[:8])} [{a.get('status')}]": a
        for a in apps
    }
    chosen_label = st.selectbox("Select Application", options=list(app_options.keys()))
    app = app_options[chosen_label]
    app_id = str(app.get("id"))
    current_status = str(app.get("status") or "DISCOVERED")

    with build_api_client_from_env() as client:
        events_res = client.list_application_events(app_id)

    c_detail, c_update = st.columns(2)
    with c_detail:
        job_obj = jobs_by_id.get(str(app.get("job_id")), {})
        st.markdown(f"**Job:** {job_obj.get('title') or app.get('job_id')}")
        st.markdown(f"**Resume Used:** {resumes_by_id.get(str(app.get('selected_resume_id')), 'None')}")
        st.markdown(f"**Match Score:** `{app.get('match_score') if app.get('match_score') is not None else '—'}`")
        st.markdown(f"**Eligibility:** `{app.get('eligibility_status') or 'NOT_EVALUATED'}`")
        st.markdown(f"**Application Date:** `{format_kolkata_timestamp(app.get('application_date'))}`")
        st.markdown(f"**Notes:** {app.get('notes') or 'None'}")

    with c_update, st.form(f"transition_app_{app_id}"):
        next_status = st.selectbox(
            "New Status",
            options=ALL_APPLICATION_STATUSES,
            index=ALL_APPLICATION_STATUSES.index(current_status)
            if current_status in ALL_APPLICATION_STATUSES
            else 0,
        )
        resume_map = {"Keep current": None, **{v: k for k, v in resumes_by_id.items()}}
        chosen_resume = st.selectbox("Update Resume", options=list(resume_map.keys()))
        note_text = st.text_area("Transition Notes", value=str(app.get("notes") or ""))
        if st.form_submit_button("Apply Status Transition", type="primary"):
            with build_api_client_from_env() as client:
                if resume_map[chosen_resume] is not None:
                    client.update_application(
                        app_id, {"selected_resume_id": resume_map[chosen_resume]}
                    )
                upd = client.update_application_status(
                    app_id,
                    next_status,
                    notes=note_text.strip() or None,
                )
            if not show_api_error(upd, "Update Application Status"):
                st.success(f"Status updated to {next_status}.")
                st.rerun()

    st.markdown("**Immutable Application Event History**")
    if events_res.ok and events_res.items:
        for ev in events_res.items:
            ts = format_kolkata_timestamp(ev.get("occurred_at"))
            st.markdown(
                f"- `{ts}` · **{ev.get('event_type')}**: "
                f"`{ev.get('previous_status') or '—'}` → `{ev.get('new_status') or '—'}` "
                f"({ev.get('source', 'manual')}) — {ev.get('description') or ''}"
            )
    else:
        st.caption("No application events recorded yet.")


if __name__ == "__main__":
    main()
