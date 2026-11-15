"""Search Configuration page: manage saved searches and trigger discovery runs."""

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
from components.widgets import (
    confirm_archive_action,
    format_csv_list,
    pagination_controls,
    parse_csv_list,
    show_api_error,
)
from services.api_client import build_api_client_from_env


def main() -> None:
    """Render the Search Configuration and on-demand discovery execution page."""
    st.set_page_config(page_title="HydraJob — Search Configuration", layout="wide")
    inject_editorial_theme()

    with build_api_client_from_env() as client:
        render_sidebar(client.base_url, client.has_api_key)

    render_page_hero(
        kicker="HydraJob · Phase 5 & 6",
        title="Search Configuration & Discovery Triggers",
        subtitle="Configure role filters, target graduation year, minimum score thresholds, and trigger scans.",
    )

    if st.button("Scan All Active Sources Now", type="primary"):
        with (
            st.spinner("Triggering discovery scan across all active sources..."),
            build_api_client_from_env() as client,
        ):
            scan_all_res = client.trigger_scan_all()
        if not show_api_error(scan_all_res, "Scan All Active Sources"):
            st.success("Scan-all triggered.")

    with build_api_client_from_env() as client:
        init_searches = client.list_searches(limit=20, offset=0)

    if show_api_error(init_searches, "Loading Search Configurations"):
        return

    render_section_kicker(number="01", label="Create", title="New Search Configuration")
    with st.expander("Create Saved Search", expanded=False):
        form = st.form("create_search_form")
        with form:
            s_name = st.text_input("Search Name *", placeholder="2027 ML & LLM Intern/New Grad")
            c1, c2 = st.columns(2)
            s_keywords = c1.text_input("Keywords (comma-separated)", value="machine learning, llm, python")
            s_roles = c2.text_input("Target Roles (comma-separated)", value="ML Engineer, Data Scientist, Software Engineer")
            c3, c4, c5 = st.columns(3)
            s_locations = c3.text_input("Locations (comma-separated)", value="Bengaluru, Hyderabad, Remote")
            s_emp = c4.text_input("Employment Types (comma-separated)", value="FULL_TIME, INTERNSHIP")
            s_remote = c5.selectbox("Remote Preference", options=["ANY", "REMOTE", "HYBRID", "ONSITE"])
            c6, c7, c8 = st.columns(3)
            s_grad = c6.number_input("Graduation Year", min_value=2020, max_value=2035, value=2027)
            s_min_score = c7.slider("Minimum Match Score", min_value=0, max_value=100, value=65)
            s_active = c8.checkbox("Active", value=True)
            s_inc = st.text_input("Included Companies (comma-separated, optional)")
            s_exc = st.text_input("Excluded Companies (comma-separated, optional)")
            if st.form_submit_button("Create Search", type="primary"):
                if not s_name.strip():
                    st.warning("Search name is required.")
                else:
                    payload = {
                        "name": s_name.strip(),
                        "keywords": parse_csv_list(s_keywords),
                        "roles": parse_csv_list(s_roles),
                        "locations": parse_csv_list(s_locations),
                        "employment_types": parse_csv_list(s_emp),
                        "remote_preference": None if s_remote == "ANY" else s_remote,
                        "graduation_year": int(s_grad),
                        "min_match_score": int(s_min_score),
                        "included_companies": parse_csv_list(s_inc),
                        "excluded_companies": parse_csv_list(s_exc),
                        "is_active": s_active,
                    }
                    with build_api_client_from_env() as client:
                        cr = client.create_search(payload)
                    if not show_api_error(cr, "Create Search"):
                        st.success("Search configuration created.")
                        st.rerun()

    render_section_kicker(
        number="02",
        label="Saved Searches",
        title=f"Configured Searches ({init_searches.total})",
    )
    limit, offset = pagination_controls("searches", init_searches.total, default_limit=20)
    if offset > 0 or limit != 20:
        with build_api_client_from_env() as client:
            searches_res = client.list_searches(limit=limit, offset=offset)
    else:
        searches_res = init_searches

    searches = searches_res.items
    if not searches:
        render_callout("No Saved Searches", "Create a search configuration above.", tone="info")
        return

    for item in searches:
        sid = str(item.get("id"))
        active = bool(item.get("is_active"))
        badge = format_status_badge_html(
            "active" if active else "disabled",
            label_override="Active" if active else "Disabled",
        )
        with st.expander(f"{item.get('name')} · Min Score {item.get('min_match_score', 0)}", expanded=False):
            st.markdown(badge, unsafe_allow_html=True)
            c_run, c_tog = st.columns(2)
            if c_run.button("Run Search Now", key=f"run_search_{sid}", type="primary"):
                with build_api_client_from_env() as client:
                    run_res = client.trigger_run_search(sid)
                if not show_api_error(run_res, "Run Search"):
                    st.success("Search execution completed.")
            if c_tog.button("Disable" if active else "Enable", key=f"tog_search_{sid}"):
                with build_api_client_from_env() as client:
                    tog = client.update_search(sid, {"is_active": not active})
                if not show_api_error(tog, "Toggle Search"):
                    st.rerun()

            with st.form(f"edit_search_{sid}"):
                ed_name = st.text_input("Name", value=str(item.get("name") or ""))
                ed_kw = st.text_input("Keywords", value=format_csv_list(item.get("keywords")))
                ed_roles = st.text_input("Roles", value=format_csv_list(item.get("roles")))
                ed_locs = st.text_input("Locations", value=format_csv_list(item.get("locations")))
                ed_min = st.slider(
                    "Minimum Match Score",
                    min_value=0,
                    max_value=100,
                    value=int(item.get("min_match_score") or 55),
                    key=f"min_s_{sid}",
                )
                if st.form_submit_button("Save Search Changes"):
                    with build_api_client_from_env() as client:
                        upd = client.update_search(
                            sid,
                            {
                                "name": ed_name.strip(),
                                "keywords": parse_csv_list(ed_kw),
                                "roles": parse_csv_list(ed_roles),
                                "locations": parse_csv_list(ed_locs),
                                "min_match_score": int(ed_min),
                            },
                        )
                    if not show_api_error(upd, "Update Search"):
                        st.success("Search updated.")
                        st.rerun()

            if confirm_archive_action(
                f"arch_search_{sid}", "Archive Search", f"'{item.get('name')}'"
            ):
                with build_api_client_from_env() as client:
                    arch = client.archive_search(sid)
                if not show_api_error(arch, "Archive Search"):
                    st.success("Search archived.")
                    st.rerun()


if __name__ == "__main__":
    main()
