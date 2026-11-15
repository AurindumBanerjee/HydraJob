"""Career Sources page: register, test, scan, toggle, and inspect failures."""

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
from components.widgets import confirm_archive_action, pagination_controls, show_api_error
from services.api_client import build_api_client_from_env
from services.time_utils import format_kolkata_timestamp

ADAPTER_OPTIONS = [
    "auto",
    "greenhouse",
    "lever",
    "ashby",
    "generic_json",
    "json_ld",
    "generic_html",
    "browser_rendered",
]


def main() -> None:
    """Render the Career Sources onboarding and monitoring page."""
    st.set_page_config(page_title="HydraJob — Career Sources", layout="wide")
    inject_editorial_theme()

    with build_api_client_from_env() as client:
        render_sidebar(client.base_url, client.has_api_key)

    render_page_hero(
        kicker="HydraJob · Phase 4-5",
        title="Career-Page Sources",
        subtitle=(
            "Register career portals, detect adapters, run test extractions, trigger scans, "
            "and inspect source failures."
        ),
    )

    with build_api_client_from_env() as client:
        companies_res = client.list_companies(limit=200)
        init_sources = client.list_sources(limit=20, offset=0)

    if show_api_error(init_sources, "Loading Career Sources"):
        return

    companies = companies_res.items if companies_res.ok else []
    company_id_to_name = {str(c.get("id")): str(c.get("name")) for c in companies}
    company_name_to_id = {str(c.get("name")): str(c.get("id")) for c in companies}

    render_section_kicker(
        number="01",
        label="Onboarding",
        title="Register Career Source",
        subtitle="New sources are validated before activation.",
    )
    with st.expander("Register New Career Page", expanded=False):
        form = st.form("register_source_form")
        with form:
            s_comp = st.selectbox(
                "Company",
                options=list(company_name_to_id.keys()) or ["Create a company first"],
            )
            s_name = st.text_input("Source Name *", placeholder="Main Engineering Careers")
            s_url = st.text_input("Career Page URL *", placeholder="https://boards.greenhouse.io/company")
            c1, c2 = st.columns(2)
            s_adapter = c1.selectbox("Adapter Hint", options=ADAPTER_OPTIONS)
            s_active = c2.checkbox("Activate immediately if verified", value=False)
            if st.form_submit_button("Register Source", type="primary"):
                if not s_name.strip() or not s_url.strip() or not company_name_to_id:
                    st.warning("Company, source name, and career URL are required.")
                else:
                    payload: dict[str, object] = {
                        "company_id": company_name_to_id[s_comp],
                        "source_name": s_name.strip(),
                        "career_url": s_url.strip(),
                        "is_active": s_active,
                    }
                    if s_adapter != "auto":
                        payload["adapter_name"] = s_adapter
                    with build_api_client_from_env() as client:
                        reg_res = client.register_source(payload)
                    if not show_api_error(reg_res, "Register Source"):
                        st.success("Career source registered.")
                        st.rerun()

    render_section_kicker(
        number="02",
        label="Registry",
        title=f"Configured Sources ({init_sources.total})",
    )
    limit, offset = pagination_controls("sources", init_sources.total, default_limit=20)
    if offset > 0 or limit != 20:
        with build_api_client_from_env() as client:
            sources_res = client.list_sources(limit=limit, offset=offset)
    else:
        sources_res = init_sources

    sources = sources_res.items
    if not sources:
        render_callout("No Career Sources", "Register a company career page above.", tone="info")
        return

    src_options = {
        f"{company_id_to_name.get(str(s.get('company_id')), 'Company')} — {s.get('source_name')} [{s.get('status', 'NEEDS_CONFIGURATION')}]": s
        for s in sources
    }
    chosen_label = st.selectbox("Select Career Source", options=list(src_options.keys()))
    src = src_options[chosen_label]
    src_id = str(src.get("id"))
    src_status = str(src.get("status") or "NEEDS_CONFIGURATION")
    is_active = bool(src.get("is_active"))

    st.markdown(
        f"**Status:** {format_status_badge_html(src_status, label_override=src_status)} · "
        f"**Active:** `{is_active}` · "
        f"**Adapter:** `{src.get('adapter_name') or 'auto'}` · "
        f"**Last Success:** `{format_kolkata_timestamp(src.get('last_successful_scan_at'))}`",
        unsafe_allow_html=True,
    )
    if src.get("last_error"):
        render_callout("Latest Source Error", str(src.get("last_error")), tone="warning")

    b1, b2, b3 = st.columns(3)
    if b1.button("Test Source", key=f"test_src_{src_id}"):
        with (
            st.spinner("Inspecting career page and running sample extraction..."),
            build_api_client_from_env() as client,
        ):
            test_res = client.test_source(src_id)
        if not show_api_error(test_res, "Test Source"):
            st.session_state["last_source_test_result"] = test_res.data
            st.success("Source test completed.")

    if b2.button("Scan Now", key=f"scan_src_{src_id}", type="primary"):
        with (
            st.spinner("Scanning career source for openings..."),
            build_api_client_from_env() as client,
        ):
            scan_res = client.scan_source(src_id)
        if not show_api_error(scan_res, "Scan Source"):
            st.success("Source scan completed.")
            st.rerun()

    toggle_label = "Disable Source" if is_active else "Enable Source"
    if b3.button(toggle_label, key=f"toggle_src_{src_id}"):
        with build_api_client_from_env() as client:
            tog_res = client.toggle_source_active(src_id, not is_active)
        if not show_api_error(tog_res, "Toggle Source"):
            st.success(f"Source {'disabled' if is_active else 'enabled'}.")
            st.rerun()

    test_preview = st.session_state.get("last_source_test_result")
    if test_preview:
        with st.expander("Sample Extracted Openings & Adapter Recommendation", expanded=True):
            st.json(test_preview)

    with st.expander("Edit or Archive Source", expanded=False):
        with st.form(f"edit_source_{src_id}"):
            ed_name = st.text_input("Source Name", value=str(src.get("source_name") or ""))
            ed_url = st.text_input("Career URL", value=str(src.get("career_url") or ""))
            current_adapter = str(src.get("adapter_name") or "auto")
            ed_adapter = st.selectbox(
                "Adapter",
                options=ADAPTER_OPTIONS,
                index=ADAPTER_OPTIONS.index(current_adapter)
                if current_adapter in ADAPTER_OPTIONS
                else 0,
            )
            if st.form_submit_button("Save Source Updates", type="primary"):
                with build_api_client_from_env() as client:
                    upd = client.update_source(
                        src_id,
                        {
                            "source_name": ed_name.strip(),
                            "career_url": ed_url.strip(),
                            "adapter_name": None if ed_adapter == "auto" else ed_adapter,
                        },
                    )
                if not show_api_error(upd, "Update Source"):
                    st.success("Source updated.")
                    st.rerun()

        st.divider()
        if confirm_archive_action(
            f"archive_src_{src_id}",
            "Archive Source",
            f"'{src.get('source_name')}'",
        ):
            with build_api_client_from_env() as client:
                arch = client.archive_source(src_id)
            if not show_api_error(arch, "Archive Source"):
                st.success("Source archived.")
                st.rerun()


if __name__ == "__main__":
    main()
