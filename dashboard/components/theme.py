"""Warm-paper editorial theme and structured layout helpers for HydraJob."""

from __future__ import annotations

import html

import streamlit as st

PALETTE: dict[str, str] = {
    "paper": "#FBFAF6",
    "paper_warm": "#F3EFE5",
    "paper_cool": "#EEE9DD",
    "rule": "#D9D4C6",
    "ink": "#14140F",
    "ink_soft": "#3B3A34",
    "graphite": "#6B6960",
    "accent": "#7A2E3B",
    "accent_bg": "#F6E9EC",
    "blueprint": "#1F4A5C",
    "blueprint_bg": "#E9F0F3",
    "sage": "#4E6A56",
    "sage_bg": "#EDF2EC",
    "amber": "#B47A28",
    "amber_bg": "#FAF3E7",
}

_CALLOUT_TONES: dict[str, tuple[str, str]] = {
    "critical": (PALETTE["accent"], PALETTE["accent_bg"]),
    "error": (PALETTE["accent"], PALETTE["accent_bg"]),
    "info": (PALETTE["blueprint"], PALETTE["blueprint_bg"]),
    "healthy": (PALETTE["sage"], PALETTE["sage_bg"]),
    "warning": (PALETTE["amber"], PALETTE["amber_bg"]),
    "degraded": (PALETTE["amber"], PALETTE["amber_bg"]),
}


def get_theme_css() -> str:
    """Return the warm-paper editorial CSS using clean system fonts only."""
    return f"""
<style>
:root {{
    --paper: {PALETTE["paper"]};
    --paper-warm: {PALETTE["paper_warm"]};
    --paper-cool: {PALETTE["paper_cool"]};
    --rule: {PALETTE["rule"]};
    --ink: {PALETTE["ink"]};
    --ink-soft: {PALETTE["ink_soft"]};
    --graphite: {PALETTE["graphite"]};
    --accent: {PALETTE["accent"]};
    --blueprint: {PALETTE["blueprint"]};
    --sage: {PALETTE["sage"]};
    --amber: {PALETTE["amber"]};
}}

.stApp {{
    background-color: var(--paper);
    color: var(--ink);
}}

[data-testid="stSidebar"] {{
    background-color: var(--paper-warm);
    border-right: 1px solid var(--rule);
}}

.block-container {{
    padding-top: 2rem;
    padding-bottom: 3rem;
    max-width: 1220px;
}}

h1, h2, h3 {{
    color: var(--ink);
    letter-spacing: -0.01em;
}}

[data-testid="stMetric"] {{
    background-color: var(--paper-warm);
    border: 1px solid var(--rule);
    border-left: 3px solid var(--blueprint);
    border-radius: 6px;
    padding: 12px 16px;
}}

[data-testid="stMetricLabel"] {{
    color: var(--graphite);
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}

[data-testid="stMetricValue"] {{
    color: var(--ink);
    font-size: 1.15rem;
}}

[data-testid="stExpander"] {{
    background-color: var(--paper-warm);
    border: 1px solid var(--rule);
    border-radius: 6px;
}}

pre, code {{
    background-color: var(--paper-cool) !important;
    color: var(--ink) !important;
    border: 1px solid var(--rule);
    border-radius: 4px;
}}

.hj-hero {{
    padding-bottom: 1rem;
    margin-bottom: 1.4rem;
    border-bottom: 1px solid var(--rule);
}}

.hj-hero-kicker {{
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 0.35rem;
}}

.hj-hero-title {{
    font-size: 1.9rem;
    font-weight: 700;
    color: var(--ink);
    line-height: 1.2;
    margin: 0;
}}

.hj-hero-subtitle {{
    font-size: 0.95rem;
    color: var(--ink-soft);
    margin-top: 0.4rem;
}}

.hj-section-header {{
    margin-top: 1.5rem;
    margin-bottom: 0.85rem;
    padding-bottom: 0.45rem;
    border-bottom: 1px solid var(--rule);
}}

.hj-kicker {{
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--blueprint);
}}

.hj-section-title {{
    font-size: 1.15rem;
    font-weight: 650;
    color: var(--ink);
    margin: 0.15rem 0 0 0;
}}

.hj-section-subtitle {{
    font-size: 0.85rem;
    color: var(--graphite);
    margin-top: 0.2rem;
}}

.hj-panel {{
    background-color: var(--paper-warm);
    border: 1px solid var(--rule);
    border-radius: 6px;
    padding: 14px 16px;
    min-height: 92px;
}}

.hj-panel-label {{
    font-size: 0.74rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--graphite);
    margin-bottom: 8px;
}}

.hj-panel-value {{
    font-size: 0.98rem;
    font-weight: 600;
    color: var(--ink);
}}

.hj-callout {{
    padding: 12px 16px;
    border-radius: 6px;
    margin: 0.85rem 0;
    border: 1px solid var(--rule);
}}

.hj-callout-title {{
    font-size: 0.9rem;
    font-weight: 650;
    color: var(--ink);
    margin-bottom: 2px;
}}

.hj-callout-body {{
    font-size: 0.88rem;
    color: var(--ink-soft);
    line-height: 1.45;
}}

.hj-pill-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 6px 0;
}}

.hj-pill {{
    display: inline-block;
    padding: 2px 9px;
    font-size: 0.78rem;
    font-weight: 500;
    border-radius: 999px;
    background-color: var(--paper-cool);
    color: var(--ink-soft);
    border: 1px solid var(--rule);
}}
</style>
"""


def inject_editorial_theme() -> None:
    """Inject the warm-paper editorial CSS into the active Streamlit page."""
    st.markdown(get_theme_css(), unsafe_allow_html=True)


def render_page_hero(kicker: str, title: str, subtitle: str) -> None:
    """Render a clean editorial page header with a hairline bottom rule."""
    st.markdown(
        '<div class="hj-hero">'
        f'<div class="hj-hero-kicker">{html.escape(kicker)}</div>'
        f'<h1 class="hj-hero-title">{html.escape(title)}</h1>'
        f'<div class="hj-hero-subtitle">{html.escape(subtitle)}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def render_section_kicker(
    number: str,
    label: str,
    title: str,
    subtitle: str | None = None,
) -> None:
    """Render a numbered section header (`§ 01 / LABEL`) separated by a hairline rule."""
    kicker_text = html.escape(f"§ {number} / {label}")
    subtitle_html = (
        f'<div class="hj-section-subtitle">{html.escape(subtitle)}</div>'
        if subtitle
        else ""
    )
    st.markdown(
        '<div class="hj-section-header">'
        f'<div class="hj-kicker">{kicker_text}</div>'
        f'<div class="hj-section-title">{html.escape(title)}</div>'
        f"{subtitle_html}"
        "</div>",
        unsafe_allow_html=True,
    )


def render_callout(title: str, body: str, tone: str = "info") -> None:
    """Render a left-bordered semantic callout box."""
    accent_color, bg_color = _CALLOUT_TONES.get(tone.lower(), _CALLOUT_TONES["info"])
    st.markdown(
        f'<div class="hj-callout" style="background-color:{bg_color};'
        f'border-left:4px solid {accent_color};">'
        f'<div class="hj-callout-title" style="color:{accent_color};">'
        f"{html.escape(title)}</div>"
        f'<div class="hj-callout-body">{html.escape(body)}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def render_summary_panel(label: str, value: str, *, raw_html: bool = False) -> None:
    """Render a structured warm-paper summary tile."""
    body = value if raw_html else html.escape(value)
    st.markdown(
        '<div class="hj-panel">'
        f'<div class="hj-panel-label">{html.escape(label)}</div>'
        f'<div class="hj-panel-value">{body}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def render_tag_pills(items: list[str], empty_label: str = "None recorded") -> None:
    """Render a clean wrapped row of warm-paper pill tags."""
    if not items:
        st.caption(empty_label)
        return
    pills = "".join(f'<span class="hj-pill">{html.escape(str(item))}</span>' for item in items)
    st.markdown(f'<div class="hj-pill-row">{pills}</div>', unsafe_allow_html=True)
