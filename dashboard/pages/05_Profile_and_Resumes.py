"""Profile and Resumes management page."""

from __future__ import annotations

import streamlit as st

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
    parse_csv_list,
    show_api_error,
)
from services.api_client import build_api_client_from_env


def main() -> None:
    """Render the configurable User Profile and Resume Versions page."""
    st.set_page_config(page_title="HydraJob — Profile & Resumes", layout="wide")
    inject_editorial_theme()

    with build_api_client_from_env() as client:
        render_sidebar(client.base_url, client.has_api_key)
        profile_res = client.get_profile()
        resumes_res = client.list_resumes(limit=50)

    render_page_hero(
        kicker="HydraJob · Phase 1 & 3",
        title="Candidate Profile & Resume Versions",
        subtitle="Maintain editable profile criteria and multiple tailored resume versions (never exposed publicly).",
    )

    render_section_kicker(
        number="01",
        label="Profile",
        title="Editable Candidate Profile",
        subtitle="Used by the eligibility gate and weighted relevance scorer.",
    )
    if show_api_error(profile_res, "Loading Profile"):
        profile: dict = {}
    else:
        profile = profile_res.data if isinstance(profile_res.data, dict) else {}

    with st.form("profile_form"):
        p1, p2 = st.columns(2)
        name = p1.text_input("Full Name", value=str(profile.get("name") or ""))
        email = p2.text_input("Email", value=str(profile.get("email") or ""))

        e1, e2, e3, e4 = st.columns(4)
        university = e1.text_input("University", value=str(profile.get("university") or ""))
        degree = e2.text_input("Degree", value=str(profile.get("degree") or ""))
        branch = e3.text_input("Branch", value=str(profile.get("branch") or ""))
        grad_year = e4.number_input(
            "Graduation Year",
            min_value=2000,
            max_value=2040,
            value=int(profile.get("graduation_year") or 2027),
        )

        cgpa_val = profile.get("cgpa")
        cgpa = st.number_input(
            "CGPA (10-point scale)",
            min_value=0.0,
            max_value=10.0,
            step=0.05,
            value=float(cgpa_val) if cgpa_val is not None else 0.0,
        )
        experience_summary = st.text_area(
            "Experience & Projects Summary",
            value=str(profile.get("experience_summary") or ""),
            height=110,
        )
        skills = st.text_input(
            "Skills (comma-separated)",
            value=format_csv_list(profile.get("skills")),
        )
        projects = st.text_input(
            "Key Projects (comma-separated)",
            value=format_csv_list(profile.get("projects")),
        )
        work_auth = st.text_input(
            "Work Authorization",
            value=str(profile.get("work_authorization") or ""),
        )
        r1, r2, r3 = st.columns(3)
        pref_roles = r1.text_input(
            "Preferred Roles (comma-separated)",
            value=format_csv_list(profile.get("preferred_roles")),
        )
        pref_locs = r2.text_input(
            "Preferred Locations (comma-separated)",
            value=format_csv_list(profile.get("preferred_locations")),
        )
        excl_locs = r3.text_input(
            "Excluded Locations (comma-separated)",
            value=format_csv_list(profile.get("excluded_locations")),
        )
        if st.form_submit_button("Save Profile", type="primary"):
            payload = {
                "name": name.strip() or None,
                "email": email.strip() or None,
                "university": university.strip() or None,
                "degree": degree.strip() or None,
                "branch": branch.strip() or None,
                "graduation_year": int(grad_year),
                "cgpa": float(cgpa) if cgpa > 0 else None,
                "experience_summary": experience_summary.strip() or None,
                "skills": parse_csv_list(skills),
                "projects": parse_csv_list(projects),
                "work_authorization": work_auth.strip() or None,
                "preferred_roles": parse_csv_list(pref_roles),
                "preferred_locations": parse_csv_list(pref_locs),
                "excluded_locations": parse_csv_list(excl_locs),
            }
            with build_api_client_from_env() as client:
                upd = client.update_profile(payload)
            if not show_api_error(upd, "Update Profile"):
                st.success("Profile updated.")
                st.rerun()

    render_section_kicker(
        number="02",
        label="Resumes",
        title="Resume Versions",
        subtitle="Manage role-specific resume versions, preferred default, and extracted skills.",
    )
    with st.expander("Add Resume Version", expanded=False), st.form("add_resume_form"):
        r_name = st.text_input("Resume Name *", placeholder="ML & LLM Engineer Resume v2")
        rc1, rc2 = st.columns(2)
        r_path = rc1.text_input("Internal File Path", placeholder="data/private/resume_ml.pdf")
        r_type = rc2.selectbox("File Type", options=["pdf", "docx", "txt", "md"])
        r_skills = st.text_input("Extracted Skills (comma-separated)")
        r_text = st.text_area("Extracted Text / Summary", height=120)
        r_pref = st.checkbox("Mark as Preferred Resume", value=False)
        if st.form_submit_button("Create Resume Version", type="primary"):
            if not r_name.strip():
                st.warning("Resume name is required.")
            else:
                with build_api_client_from_env() as client:
                    cr = client.create_resume(
                        {
                            "name": r_name.strip(),
                            "file_path": r_path.strip() or None,
                            "file_type": r_type,
                            "skills": parse_csv_list(r_skills),
                            "extracted_text": r_text.strip() or None,
                            "is_preferred": r_pref,
                            "is_active": True,
                        }
                    )
                if not show_api_error(cr, "Create Resume"):
                    st.success("Resume version saved.")
                    st.rerun()

    if show_api_error(resumes_res, "Loading Resumes"):
        return

    resumes = resumes_res.items
    if not resumes:
        render_callout("No Resumes Added", "Add a resume version above to enable tailored resume recommendations.", tone="info")
        return

    for res in resumes:
        rid = str(res.get("id"))
        pref_tag = " · Preferred" if res.get("is_preferred") else ""
        with st.expander(f"{res.get('name', 'Resume')}{pref_tag}", expanded=False):
            st.caption(f"Type: `{res.get('file_type') or 'unknown'}` · Active: `{res.get('is_active')}`")
            st.markdown("**Extracted Skills**")
            render_tag_pills(list(res.get("skills") or []))
            c_pref, c_arch = st.columns(2)
            if c_pref.button(
                "Set as Preferred" if not res.get("is_preferred") else "Unset Preferred",
                key=f"pref_res_{rid}",
            ):
                with build_api_client_from_env() as client:
                    upd_res = client.update_resume(
                        rid, {"is_preferred": not bool(res.get("is_preferred"))}
                    )
                if not show_api_error(upd_res, "Update Resume"):
                    st.rerun()
            with c_arch:
                if confirm_archive_action(
                    f"arch_res_{rid}", "Archive Resume", f"'{res.get('name')}'"
                ):
                    with build_api_client_from_env() as client:
                        arch = client.archive_resume(rid)
                    if not show_api_error(arch, "Archive Resume"):
                        st.success("Resume archived.")
                        st.rerun()


if __name__ == "__main__":
    main()
