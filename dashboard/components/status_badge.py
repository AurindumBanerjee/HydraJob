"""Status badge and service card components for HydraJob monitoring."""

from __future__ import annotations

import html
from dataclasses import dataclass

import streamlit as st

from components.theme import PALETTE


@dataclass(frozen=True)
class StatusPresentation:
    """Visual styling metadata for a normalized service or domain status."""

    label: str
    bg_color: str
    text_color: str
    border_color: str
    accent_color: str
    icon: str


STATUS_STYLES: dict[str, StatusPresentation] = {
    "healthy": StatusPresentation(
        label="Healthy",
        bg_color=PALETTE["sage_bg"],
        text_color=PALETTE["sage"],
        border_color="#C4D4C7",
        accent_color=PALETTE["sage"],
        icon="●",
    ),
    "degraded": StatusPresentation(
        label="Degraded",
        bg_color=PALETTE["amber_bg"],
        text_color=PALETTE["amber"],
        border_color="#E4CFA9",
        accent_color=PALETTE["amber"],
        icon="▲",
    ),
    "unavailable": StatusPresentation(
        label="Unavailable",
        bg_color=PALETTE["accent_bg"],
        text_color=PALETTE["accent"],
        border_color="#DFB8C0",
        accent_color=PALETTE["accent"],
        icon="■",
    ),
    "info": StatusPresentation(
        label="Info",
        bg_color=PALETTE["blueprint_bg"],
        text_color=PALETTE["blueprint"],
        border_color="#B8CDD5",
        accent_color=PALETTE["blueprint"],
        icon="◆",
    ),
    "unknown": StatusPresentation(
        label="Unknown",
        bg_color=PALETTE["paper_cool"],
        text_color=PALETTE["graphite"],
        border_color=PALETTE["rule"],
        accent_color=PALETTE["graphite"],
        icon="○",
    ),
}

_DOMAIN_STATUS_MAP: dict[str, str] = {
    "eligible": "healthy",
    "ready": "healthy",
    "active": "healthy",
    "completed": "healthy",
    "offer_received": "healthy",
    "acknowledged": "healthy",
    "applied": "info",
    "discovered": "info",
    "to_apply": "info",
    "queued": "info",
    "running": "info",
    "in_progress": "degraded",
    "preparing": "degraded",
    "under_review": "degraded",
    "oa_received": "degraded",
    "oa_completed": "info",
    "technical_test": "degraded",
    "interview_scheduled": "degraded",
    "interview_completed": "info",
    "further_rounds": "degraded",
    "uncertain": "degraded",
    "needs_configuration": "degraded",
    "needs_review": "degraded",
    "pending": "degraded",
    "ineligible": "unavailable",
    "failed": "unavailable",
    "rejected": "unavailable",
    "disabled": "unavailable",
    "cancelled": "unknown",
    "withdrawn": "unknown",
    "closed": "unknown",
    "archived": "unknown",
    "not_evaluated": "unknown",
}


def get_status_presentation(status: str) -> StatusPresentation:
    """Return consistent styling metadata for a normalized or domain status string."""
    key = status.strip().lower()
    mapped = _DOMAIN_STATUS_MAP.get(key, key)
    return STATUS_STYLES.get(mapped, STATUS_STYLES["unknown"])


def format_status_badge_html(status: str, label_override: str | None = None) -> str:
    """Build an HTML pill badge string for a normalized service or domain status."""
    style = get_status_presentation(status)
    text = html.escape(label_override or style.label)
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f"padding:3px 10px;border-radius:999px;font-size:0.78rem;font-weight:600;"
        f"background-color:{style.bg_color};color:{style.text_color};"
        f'border:1px solid {style.border_color};">'
        f"<span>{style.icon}</span><span>{text}</span></span>"
    )


def render_status_badge(status: str, label_override: str | None = None) -> None:
    """Render a colored pill status badge in Streamlit."""
    st.markdown(format_status_badge_html(status, label_override), unsafe_allow_html=True)


def render_service_card(
    title: str,
    status: str,
    subtitle: str | None = None,
    detail: str | None = None,
) -> None:
    """Render a warm-paper left-accented status card for a HydraJob service."""
    style = get_status_presentation(status)
    badge_html = format_status_badge_html(status)
    safe_title = html.escape(title)
    safe_subtitle = html.escape(subtitle) if subtitle else ""
    safe_detail = html.escape(detail) if detail else ""

    subtitle_html = (
        f'<div style="margin-top:10px;font-size:0.86rem;color:{PALETTE["ink_soft"]};">'
        f"{safe_subtitle}</div>"
        if safe_subtitle
        else ""
    )
    detail_html = (
        f'<div style="margin-top:6px;font-size:0.82rem;color:{PALETTE["graphite"]};">'
        f"{safe_detail}</div>"
        if safe_detail
        else ""
    )

    card_html = (
        f'<div style="padding:16px;border-radius:6px;'
        f'border:1px solid {PALETTE["rule"]};'
        f'border-left:4px solid {style.accent_color};'
        f'background-color:{PALETTE["paper_warm"]};min-height:126px;">'
        '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">'
        f'<span style="font-size:1.02rem;font-weight:650;color:{PALETTE["ink"]};">'
        f"{safe_title}</span>"
        f"{badge_html}"
        "</div>"
        f"{subtitle_html}"
        f"{detail_html}"
        "</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)
