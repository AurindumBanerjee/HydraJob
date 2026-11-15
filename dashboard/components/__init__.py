"""Reusable Streamlit UI components for the HydraJob dashboard."""

from components.status_badge import (
    STATUS_STYLES,
    format_status_badge_html,
    get_status_presentation,
    render_service_card,
    render_status_badge,
)
from components.system_view import (
    render_phase0_dashboard,
    render_service_health_strip,
    render_sidebar,
)
from components.theme import (
    PALETTE,
    get_theme_css,
    inject_editorial_theme,
    render_callout,
    render_page_hero,
    render_section_kicker,
    render_summary_panel,
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

__all__ = [
    "PALETTE",
    "STATUS_STYLES",
    "confirm_archive_action",
    "format_csv_list",
    "format_status_badge_html",
    "get_status_presentation",
    "get_theme_css",
    "inject_editorial_theme",
    "pagination_controls",
    "parse_csv_list",
    "render_callout",
    "render_evaluation_panel",
    "render_page_hero",
    "render_phase0_dashboard",
    "render_section_kicker",
    "render_service_card",
    "render_service_health_strip",
    "render_sidebar",
    "render_status_badge",
    "render_summary_panel",
    "render_tag_pills",
    "show_api_error",
]
