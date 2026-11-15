"""Companies page: manage company records, view career pages, jobs, and notes."""

from __future__ import annotations

import streamlit as st

from components.system_view import render_sidebar
from components.theme import (
    inject_editorial_theme,
    render_callout,
    render_page_hero,
    render_section_kicker,
)
from components.widgets import confirm_archive_action, pagination_controls, show_api_error
from services.api_client import build_api_client_from_env


def main() -> None:
    """Render the Companies directory and management page."""
    st.set_page_config(page_title="HydraJob — Companies", layout="wide")
    inject_editorial_theme()

    with build_api_client_from_env() as client:
        render_sidebar(client.base_url, client.has_api_key)

    render_page_hero(
        kicker="HydraJob · Phase 1",
        title="Companies Registry",
        subtitle="Add, edit, or archive target companies and inspect linked career sources and jobs.",
    )

    c_search, c_ind, c_arch = st.columns([2, 1, 1])
    search_text = c_search.text_input("Search company name", key="comp_search")
    industry_filter = c_ind.text_input("Industry filter", key="comp_ind")
    include_archived = c_arch.checkbox("Include archived", value=False, key="comp_arch")

    with build_api_client_from_env() as client:
        init_res = client.list_companies(
            search=search_text or None,
            industry=industry_filter or None,
            include_archived=include_archived,
            limit=20,
            offset=0,
        )

    if show_api_error(init_res, "Loading Companies"):
        return

    limit, offset = pagination_controls("companies", init_res.total, default_limit=20)
    if offset > 0 or limit != 20:
        with build_api_client_from_env() as client:
            comp_res = client.list_companies(
                search=search_text or None,
                industry=industry_filter or None,
                include_archived=include_archived,
                limit=limit,
                offset=offset,
            )
    else:
        comp_res = init_res

    render_section_kicker(
        number="01",
        label="Create",
        title="Add Company",
    )
    with st.expander("Add New Company", expanded=False), st.form("add_company_form"):
        name = st.text_input("Company Name *")
        c1, c2 = st.columns(2)
        website = c1.text_input("Main Website", placeholder="https://company.com")
        industry = c2.text_input("Industry", placeholder="Technology / AI / Quant")
        desc = st.text_area("Description")
        notes = st.text_area("Notes")
        if st.form_submit_button("Create Company", type="primary"):
            if not name.strip():
                st.warning("Company name is required.")
            else:
                with build_api_client_from_env() as client:
                    res = client.create_company(
                        {
                            "name": name.strip(),
                            "website": website.strip() or None,
                            "industry": industry.strip() or None,
                            "description": desc.strip() or None,
                            "notes": notes.strip() or None,
                        }
                    )
                if not show_api_error(res, "Create Company"):
                    st.success("Company created.")
                    st.rerun()

    render_section_kicker(
        number="02",
        label="Directory",
        title=f"Registered Companies ({comp_res.total})",
    )
    companies = comp_res.items
    if not companies:
        render_callout("No Companies Found", "Add a company or clear your search filter.", tone="info")
        return

    comp_map = {f"{c.get('name')} ({c.get('industry') or 'Unspecified'})": c for c in companies}
    selected_label = st.selectbox("Select Company", options=list(comp_map.keys()))
    comp = comp_map[selected_label]
    comp_id = str(comp.get("id"))

    with build_api_client_from_env() as client:
        sources_res = client.list_sources(company_id=comp_id, limit=50)
        jobs_res = client.list_jobs(company_id=comp_id, limit=50)

    tab_info, tab_edit = st.tabs(["Career Pages, Jobs & Notes", "Edit & Archive"])
    with tab_info:
        st.markdown(f"**Website:** `{comp.get('website') or 'Not set'}`")
        st.markdown(f"**Industry:** {comp.get('industry') or 'Not set'}")
        st.markdown(f"**Notes:** {comp.get('notes') or 'None'}")
        col_s, col_j = st.columns(2)
        with col_s:
            st.markdown("**Career Pages**")
            for src in (sources_res.items if sources_res.ok else []):
                st.markdown(
                    f"- **{src.get('source_name')}** (`{src.get('adapter_name') or src.get('source_type')}`) "
                    f"— `{src.get('status')}`"
                )
            if not (sources_res.ok and sources_res.items):
                st.caption("No career sources linked.")
        with col_j:
            st.markdown("**Company Jobs**")
            for j in (jobs_res.items if jobs_res.ok else []):
                st.markdown(f"- **{j.get('title')}** (`{j.get('status')}`)")
            if not (jobs_res.ok and jobs_res.items):
                st.caption("No jobs recorded for this company.")

    with tab_edit:
        with st.form(f"edit_company_{comp_id}"):
            ed_name = st.text_input("Name", value=str(comp.get("name") or ""))
            ed_web = st.text_input("Website", value=str(comp.get("website") or ""))
            ed_ind = st.text_input("Industry", value=str(comp.get("industry") or ""))
            ed_desc = st.text_area("Description", value=str(comp.get("description") or ""))
            ed_notes = st.text_area("Notes", value=str(comp.get("notes") or ""))
            if st.form_submit_button("Save Changes", type="primary"):
                with build_api_client_from_env() as client:
                    upd = client.update_company(
                        comp_id,
                        {
                            "name": ed_name.strip(),
                            "website": ed_web.strip() or None,
                            "industry": ed_ind.strip() or None,
                            "description": ed_desc.strip() or None,
                            "notes": ed_notes.strip() or None,
                        },
                    )
                if not show_api_error(upd, "Update Company"):
                    st.success("Company updated.")
                    st.rerun()

        st.divider()
        if confirm_archive_action(
            f"archive_comp_{comp_id}",
            "Archive Company",
            f"'{comp.get('name')}'",
        ):
            with build_api_client_from_env() as client:
                arch = client.archive_company(comp_id)
            if not show_api_error(arch, "Archive Company"):
                st.success("Company archived.")
                st.rerun()


if __name__ == "__main__":
    main()
