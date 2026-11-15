"""Jobs management page: search, filter, inspect, edit, evaluate, and apply."""

from __future__ import annotations

import streamlit as st

from components.status_badge import format_status_badge_html
from components.system_view import render_sidebar
from components.theme import (
    inject_editorial_theme,
    render_callout,
    render_page_hero,
    render_section_kicker,
    render_tag_pills,
)
from components.widgets import (
    confirm_archive_action,
    format_csv_list,
    pagination_controls,
    parse_csv_list,
    render_evaluation_panel,
    show_api_error,
)
from services.api_client import build_api_client_from_env
from services.time_utils import format_kolkata_timestamp

JOB_STATUSES = ["", "ACTIVE", "NEEDS_REVIEW", "CLOSED", "ARCHIVED"]
EMPLOYMENT_TYPES = ["", "FULL_TIME", "INTERNSHIP", "CONTRACT", "PART_TIME"]
WORKPLACE_TYPES = ["", "ONSITE", "HYBRID", "REMOTE"]


def main() -> None:
    """Render the Jobs management page."""
    st.set_page_config(page_title="HydraJob — Jobs", layout="wide")
    inject_editorial_theme()

    with build_api_client_from_env() as client:
        render_sidebar(client.base_url, client.has_api_key)

    render_page_hero(
        kicker="HydraJob · Phase 1-3",
        title="Jobs Directory & Evaluation",
        subtitle="Filter discovered jobs, edit extracted fields, run Ollama evaluations, and create applications.",
    )

    render_section_kicker(
        number="01",
        label="Filters",
        title="Search & Filter Jobs",
    )
    f1, f2, f3, f4, f5 = st.columns([2, 1, 1, 1, 1])
    search_query = f1.text_input("Search title or keyword", key="jobs_search")
    status_filter = f2.selectbox("Status", options=JOB_STATUSES, key="jobs_status")
    emp_filter = f3.selectbox("Employment Type", options=EMPLOYMENT_TYPES, key="jobs_emp")
    work_filter = f4.selectbox("Workplace", options=WORKPLACE_TYPES, key="jobs_work")
    include_archived = f5.checkbox("Include archived", value=False, key="jobs_archived")

    with build_api_client_from_env() as client:
        companies_res = client.list_companies(limit=200)
        resumes_res = client.list_resumes(limit=50)
        initial_res = client.list_jobs(
            search=search_query or None,
            status=status_filter or None,
            employment_type=emp_filter or None,
            workplace_type=work_filter or None,
            include_archived=include_archived,
            limit=20,
            offset=0,
        )

    if show_api_error(initial_res, "Loading Jobs"):
        return

    company_map = {
        str(c.get("id")): str(c.get("name", "Unknown"))
        for c in (companies_res.items if companies_res.ok else [])
    }
    resumes = resumes_res.items if resumes_res.ok else []

    limit, offset = pagination_controls("jobs_list", initial_res.total, default_limit=20)
    if offset > 0 or limit != 20:
        with build_api_client_from_env() as client:
            jobs_res = client.list_jobs(
                search=search_query or None,
                status=status_filter or None,
                employment_type=emp_filter or None,
                workplace_type=work_filter or None,
                include_archived=include_archived,
                limit=limit,
                offset=offset,
            )
    else:
        jobs_res = initial_res

    jobs = jobs_res.items

    render_section_kicker(
        number="02",
        label="Manual Entry",
        title="Add Job Manually",
    )
    with st.expander("Create New Job Record", expanded=False), st.form("create_job_form"):
        c_names = {v: k for k, v in company_map.items()}
        selected_company_name = st.selectbox(
            "Company",
            options=list(c_names.keys()) or ["No companies available"],
        )
        new_title = st.text_input("Role Title *")
        c1, c2, c3 = st.columns(3)
        new_location = c1.text_input("Location")
        new_emp = c2.selectbox("Employment Type", options=EMPLOYMENT_TYPES[1:])
        new_work = c3.selectbox("Workplace Type", options=WORKPLACE_TYPES[1:])
        new_app_url = st.text_input("Application URL")
        new_skills = st.text_input("Required Skills (comma-separated)")
        new_desc = st.text_area("Job Description", height=120)
        submitted = st.form_submit_button("Save Job", type="primary")
        if submitted:
            if not new_title.strip() or not c_names:
                st.warning("Provide a company and role title before saving.")
            else:
                payload = {
                    "company_id": c_names[selected_company_name],
                    "title": new_title.strip(),
                    "location": new_location.strip() or None,
                    "employment_type": new_emp,
                    "workplace_type": new_work,
                    "application_url": new_app_url.strip() or None,
                    "required_skills": parse_csv_list(new_skills),
                    "description": new_desc.strip() or None,
                }
                with build_api_client_from_env() as client:
                    create_res = client.create_job(payload)
                if not show_api_error(create_res, "Create Job"):
                    st.success("Job created.")
                    st.rerun()

    render_section_kicker(
        number="03",
        label="Records",
        title=f"Discovered & Manual Jobs ({jobs_res.total})",
        subtitle="Select a job below to inspect descriptions, edit fields, evaluate, or start an application.",
    )
    if not jobs:
        render_callout("No Jobs Found", "Adjust filters or submit a job URL to populate jobs.", tone="info")
        return

    job_options = {
        f"{j.get('title', 'Untitled')} — {company_map.get(str(j.get('company_id')), 'Company')} ({j.get('status', 'ACTIVE')})": j
        for j in jobs
    }
    selected_label = st.selectbox("Select Job to Inspect", options=list(job_options.keys()))
    selected_job = job_options[selected_label]
    job_id = str(selected_job.get("id"))

    with build_api_client_from_env() as client:
        detail_res = client.get_job(job_id)
        evals_res = client.list_job_evaluations(job_id)

    job = detail_res.data if detail_res.ok and isinstance(detail_res.data, dict) else selected_job
    evaluations = evals_res.items if evals_res.ok else []

    status_str = str(job.get("status") or "ACTIVE")
    st.markdown(
        f"**Status:** {format_status_badge_html(status_str, label_override=status_str)} · "
        f"**First seen:** `{format_kolkata_timestamp(job.get('first_seen_at'))}` · "
        f"**Last seen:** `{format_kolkata_timestamp(job.get('last_seen_at'))}`",
        unsafe_allow_html=True,
    )

    tab_view, tab_edit, tab_eval, tab_apply = st.tabs(
        ["Description & Skills", "Edit Fields & Archive", "Evaluate Fit", "Create Application"]
    )

    with tab_view:
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Location:** {job.get('location') or 'Not disclosed'}")
        c2.markdown(f"**Experience:** {job.get('experience_requirement') or 'Not specified'}")
        c3.markdown(f"**Deadline:** {format_kolkata_timestamp(job.get('application_deadline'))}")
        if job.get("application_url"):
            st.markdown(f"**Application URL:** `{job.get('application_url')}`")
        st.markdown("**Required Skills**")
        render_tag_pills(list(job.get("required_skills") or []))
        st.markdown("**Preferred Skills**")
        render_tag_pills(list(job.get("preferred_skills") or []))
        st.markdown("**Job Description**")
        st.write(job.get("description") or "No description recorded.")

    with tab_edit:
        with st.form(f"edit_job_{job_id}"):
            ed_title = st.text_input("Title", value=str(job.get("title") or ""))
            e1, e2, e3 = st.columns(3)
            ed_loc = e1.text_input("Location", value=str(job.get("location") or ""))
            ed_grad = e2.text_input(
                "Graduation Year Req",
                value=str(job.get("graduation_year_requirement") or ""),
            )
            ed_status = e3.selectbox(
                "Status",
                options=JOB_STATUSES[1:],
                index=JOB_STATUSES[1:].index(status_str)
                if status_str in JOB_STATUSES[1:]
                else 0,
            )
            ed_req_skills = st.text_input(
                "Required Skills (comma-separated)",
                value=format_csv_list(job.get("required_skills")),
            )
            ed_pref_skills = st.text_input(
                "Preferred Skills (comma-separated)",
                value=format_csv_list(job.get("preferred_skills")),
            )
            ed_url = st.text_input(
                "Application URL",
                value=str(job.get("application_url") or ""),
            )
            ed_desc = st.text_area(
                "Description",
                value=str(job.get("description") or ""),
                height=160,
            )
            if st.form_submit_button("Update Job", type="primary"):
                grad_val: int | None = None
                if ed_grad.strip():
                    try:
                        grad_val = int(ed_grad.strip())
                    except ValueError:
                        st.warning("Graduation year requirement must be an integer (e.g. 2027).")
                        st.stop()
                patch_payload = {
                    "title": ed_title.strip(),
                    "location": ed_loc.strip() or None,
                    "graduation_year_requirement": grad_val,
                    "status": ed_status,
                    "required_skills": parse_csv_list(ed_req_skills),
                    "preferred_skills": parse_csv_list(ed_pref_skills),
                    "application_url": ed_url.strip() or None,
                    "description": ed_desc.strip() or None,
                }
                with build_api_client_from_env() as client:
                    upd_res = client.update_job(job_id, patch_payload)
                if not show_api_error(upd_res, "Update Job"):
                    st.success("Job updated.")
                    st.rerun()

        st.divider()
        if confirm_archive_action(f"archive_job_{job_id}", "Archive Job", f"'{job.get('title')}'"):
            with build_api_client_from_env() as client:
                arch_res = client.archive_job(job_id)
            if not show_api_error(arch_res, "Archive Job"):
                st.success("Job archived.")
                st.rerun()

    with tab_eval:
        resume_choices = {"Auto-select best resume": None}
        for r in resumes:
            resume_choices[str(r.get("name", r.get("id")))] = str(r.get("id"))
        chosen_resume_label = st.selectbox(
            "Resume for evaluation",
            options=list(resume_choices.keys()),
            key=f"eval_resume_{job_id}",
        )
        if st.button("Evaluate / Re-evaluate Job", key=f"eval_btn_{job_id}", type="primary"):
            with (
                st.spinner("Running eligibility and weighted relevance evaluation..."),
                build_api_client_from_env() as client,
            ):
                eval_run_res = client.evaluate_job(
                    job_id, resume_id=resume_choices[chosen_resume_label]
                )
            if not show_api_error(eval_run_res, "Evaluate Job"):
                st.success("Evaluation completed.")
                st.rerun()

        if evaluations:
            render_evaluation_panel(evaluations[0])
        else:
            st.caption("No evaluations recorded for this job yet.")

    with tab_apply, st.form(f"create_app_{job_id}"):
        app_resume_choices = {"None selected": None}
        for r in resumes:
            app_resume_choices[str(r.get("name", r.get("id")))] = str(r.get("id"))
        app_resume = st.selectbox("Selected Resume", options=list(app_resume_choices.keys()))
        app_priority = st.selectbox("Priority", options=["HIGH", "MEDIUM", "LOW"], index=1)
        app_notes = st.text_area("Application Notes")
        if st.form_submit_button("Create Application", type="primary"):
            with build_api_client_from_env() as client:
                app_res = client.create_application(
                    {
                        "job_id": job_id,
                        "selected_resume_id": app_resume_choices[app_resume],
                        "priority": app_priority,
                        "notes": app_notes.strip() or None,
                    }
                )
            if not show_api_error(app_res, "Create Application"):
                st.success("Application created in DISCOVERED/TO_APPLY pipeline.")


if __name__ == "__main__":
    main()
