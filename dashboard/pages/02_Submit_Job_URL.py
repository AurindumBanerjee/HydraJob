"""Submit Job URL page: safe ingestion, extraction preview, manual edits, and reprocess."""

from __future__ import annotations

import streamlit as st

from components.status_badge import format_status_badge_html
from components.system_view import render_sidebar
from components.theme import (
    inject_editorial_theme,
    render_callout,
    render_page_hero,
    render_section_kicker,
)
from components.widgets import format_csv_list, parse_csv_list, show_api_error
from services.api_client import build_api_client_from_env
from services.time_utils import format_kolkata_timestamp


def main() -> None:
    """Render the Submit Job URL ingestion and correction workflow."""
    st.set_page_config(page_title="HydraJob — Submit Job URL", layout="wide")
    inject_editorial_theme()

    with build_api_client_from_env() as client:
        render_sidebar(client.base_url, client.has_api_key)

    render_page_hero(
        kicker="HydraJob · Phase 2",
        title="Submit Job URL",
        subtitle=(
            "Ingest an individual job posting URL with SSRF checks, inspect extracted fields, "
            "correct errors before finalizing, or reprocess."
        ),
    )

    render_section_kicker(
        number="01",
        label="Intake",
        title="Submit Public Job Posting URL",
        subtitle="Private/localhost/link-local addresses and credentials in URLs are blocked.",
    )

    with st.form("ingest_url_form"):
        job_url = st.text_input(
            "Job Posting URL",
            placeholder="https://boards.greenhouse.io/example/jobs/12345",
        )
        use_ollama = st.checkbox(
            "Enhance missing structured fields with local Ollama extraction",
            value=True,
        )
        submitted = st.form_submit_button("Ingest Job URL", type="primary")

    if submitted:
        if not job_url.strip():
            st.warning("Enter an HTTP or HTTPS job URL.")
        else:
            with (
                st.spinner("Validating URL and extracting structured job details..."),
                build_api_client_from_env() as client,
            ):
                ingest_res = client.ingest_job_url(job_url.strip(), use_ollama=use_ollama)
            if not show_api_error(ingest_res, "Job URL Ingestion"):
                data = ingest_res.data if isinstance(ingest_res.data, dict) else {}
                st.session_state["last_ingestion_run_id"] = data.get("ingestion_id") or data.get("id")
                st.session_state["last_ingested_job_id"] = data.get("job_id") or data.get("extracted_job_id")
                st.success(f"Ingestion recorded (status: {data.get('status', 'COMPLETED')}).")

    run_id = st.session_state.get("last_ingestion_run_id")
    job_id = st.session_state.get("last_ingested_job_id")

    render_section_kicker(
        number="02",
        label="Ingestion Run",
        title="Processing Status & Preview",
        subtitle="Review recent ingestion runs, reprocess failures, and approve extracted job fields.",
    )

    with build_api_client_from_env() as client:
        runs_res = client.list_discovery_runs(run_type="URL_INGEST", limit=10)

    if runs_res.ok and runs_res.items:
        run_choices = {
            f"{str(r.get('id'))[:8]} · {r.get('status')} · {r.get('url', '')}": r
            for r in runs_res.items
        }
        chosen_run_label = st.selectbox("Recent URL Ingestion Runs", options=list(run_choices.keys()))
        active_run = run_choices[chosen_run_label]
        run_id = str(active_run.get("id"))
        job_id = active_run.get("extracted_job_id") or job_id
    elif run_id:
        with build_api_client_from_env() as client:
            single_run = client.get_ingestion_run(str(run_id))
        active_run = single_run.data if single_run.ok and isinstance(single_run.data, dict) else {}
    else:
        active_run = {}

    if active_run:
        r_status = str(active_run.get("status") or "UNKNOWN")
        c1, c2, c3 = st.columns([1.2, 2, 1])
        with c1:
            st.markdown(
                f"**Status:** {format_status_badge_html(r_status, label_override=r_status)}",
                unsafe_allow_html=True,
            )
        with c2:
            st.caption(f"Canonical URL: `{active_run.get('canonical_url') or active_run.get('url')}`")
            st.caption(f"Started: `{format_kolkata_timestamp(active_run.get('started_at'))}`")
        with c3:
            if st.button("Reprocess Run", key=f"reprocess_{run_id}"):
                with build_api_client_from_env() as client:
                    retry_res = client.reprocess_ingestion_run(str(run_id))
                if not show_api_error(retry_res, "Reprocess Ingestion"):
                    st.success("Reprocess queued/completed.")
                    st.rerun()

        if active_run.get("errors"):
            render_callout(
                title="Extraction Notes / Errors",
                body=str(active_run.get("errors")),
                tone="warning",
            )

    if job_id:
        with build_api_client_from_env() as client:
            job_res = client.get_job(str(job_id))
        if job_res.ok and isinstance(job_res.data, dict):
            job = job_res.data
            st.subheader("Editable Extracted Job Preview")
            with st.form(f"approve_job_{job_id}"):
                ed_title = st.text_input("Title", value=str(job.get("title") or ""))
                j1, j2, j3 = st.columns(3)
                ed_loc = j1.text_input("Location", value=str(job.get("location") or ""))
                ed_emp = j2.text_input(
                    "Employment Type", value=str(job.get("employment_type") or "")
                )
                ed_work = j3.text_input(
                    "Workplace Type", value=str(job.get("workplace_type") or "")
                )
                ed_skills = st.text_input(
                    "Required Skills (comma-separated)",
                    value=format_csv_list(job.get("required_skills")),
                )
                ed_deadline = st.text_input(
                    "Application Deadline (ISO-8601 or blank)",
                    value=str(job.get("application_deadline") or ""),
                )
                ed_desc = st.text_area(
                    "Description", value=str(job.get("description") or ""), height=180
                )
                c_save, c_eval = st.columns(2)
                approve_clicked = c_save.form_submit_button("Approve & Save Job", type="primary")
                eval_clicked = c_eval.form_submit_button("Save & Run Evaluation")
                if approve_clicked or eval_clicked:
                    payload = {
                        "title": ed_title.strip(),
                        "location": ed_loc.strip() or None,
                        "employment_type": ed_emp.strip() or None,
                        "workplace_type": ed_work.strip() or None,
                        "required_skills": parse_csv_list(ed_skills),
                        "application_deadline": ed_deadline.strip() or None,
                        "description": ed_desc.strip() or None,
                        "status": "ACTIVE",
                    }
                    with build_api_client_from_env() as client:
                        upd_res = client.update_job(str(job_id), payload)
                        if upd_res.ok and eval_clicked:
                            client.evaluate_job(str(job_id))
                    if not show_api_error(upd_res, "Approve Extracted Job"):
                        st.success("Extracted job approved and saved.")
    else:
        st.caption("Submit a URL or select an ingestion run above to preview and edit extracted fields.")


if __name__ == "__main__":
    main()
