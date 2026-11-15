"""Shared UI helpers for pagination, destructive confirmation, lists, and evaluations."""

from __future__ import annotations

from typing import Any

import streamlit as st

from components.status_badge import format_status_badge_html
from components.theme import render_callout, render_summary_panel, render_tag_pills
from services.api_client import ApiResponse
from services.time_utils import format_kolkata_timestamp


def parse_csv_list(raw: str) -> list[str]:
    """Split a comma-separated input string into trimmed non-empty items."""
    return [part.strip() for part in raw.split(",") if part.strip()]


def format_csv_list(items: list[str] | None) -> str:
    """Join a list of strings into a comma-separated string for form editing."""
    if not items:
        return ""
    return ", ".join(str(item) for item in items if str(item).strip())


def show_api_error(response: ApiResponse, context: str) -> bool:
    """Render a left-bordered error callout if an API response failed.

    Returns ``True`` when an error was displayed so callers can return early.
    """
    if response.ok:
        return False
    render_callout(
        title=f"{context} Failed",
        body=response.error or "Unexpected backend error.",
        tone="critical",
    )
    return True


def confirm_archive_action(key_prefix: str, button_label: str, item_label: str) -> bool:
    """Render an explicit confirmation checkbox + button pair for destructive archive actions."""
    confirmed = st.checkbox(
        f"Confirm archiving {item_label}",
        key=f"{key_prefix}_confirm",
        value=False,
    )
    return st.button(
        button_label,
        key=f"{key_prefix}_submit",
        disabled=not confirmed,
        type="secondary",
    )


def pagination_controls(
    key_prefix: str,
    total: int,
    *,
    default_limit: int = 20,
) -> tuple[int, int]:
    """Render clean pagination controls and return ``(limit, offset)``."""
    page_key = f"{key_prefix}_page"
    if page_key not in st.session_state:
        st.session_state[page_key] = 1

    limit = st.selectbox(
        "Rows per page",
        options=[10, 20, 50, 100],
        index=[10, 20, 50, 100].index(default_limit)
        if default_limit in (10, 20, 50, 100)
        else 1,
        key=f"{key_prefix}_limit",
    )
    total_pages = max(1, (total + limit - 1) // limit)
    current_page = min(max(1, int(st.session_state[page_key])), total_pages)

    c_prev, c_info, c_next = st.columns([1, 2, 1])
    with c_prev:
        if st.button("Previous", key=f"{key_prefix}_prev", disabled=current_page <= 1):
            st.session_state[page_key] = current_page - 1
            st.rerun()
    with c_info:
        st.caption(f"Page {current_page} of {total_pages} ({total} total records)")
    with c_next:
        if st.button("Next", key=f"{key_prefix}_next", disabled=current_page >= total_pages):
            st.session_state[page_key] = current_page + 1
            st.rerun()

    offset = (current_page - 1) * limit
    return int(limit), int(offset)


def render_evaluation_panel(evaluation: dict[str, Any]) -> None:
    """Render structured eligibility, weighted score breakdown, skills, and evidence."""
    eligibility = str(evaluation.get("eligibility_status") or "NOT_EVALUATED")
    overall_score = evaluation.get("overall_score")
    recommendation = str(evaluation.get("recommendation") or "REVIEW")
    model_name = str(evaluation.get("model_name") or "rule-based")
    eval_version = str(evaluation.get("evaluation_version") or "v1.0")
    evaluated_at = format_kolkata_timestamp(evaluation.get("evaluated_at"))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_summary_panel(
            "Eligibility",
            format_status_badge_html(eligibility, label_override=eligibility),
            raw_html=True,
        )
    with c2:
        score_text = f"{overall_score}/100" if overall_score is not None else "Not scored"
        render_summary_panel("Overall Score", score_text)
    with c3:
        render_summary_panel("Recommendation", recommendation)
    with c4:
        render_summary_panel("Evaluated (IST)", evaluated_at)

    component_scores = evaluation.get("component_scores") or {}
    if isinstance(component_scores, dict) and component_scores:
        st.markdown("**Weighted Component Breakdown (0-100)**")
        cols = st.columns(5)
        labels = [
            ("eligibility", "Eligibility (30%)"),
            ("technical", "Technical (30%)"),
            ("experience", "Experience (20%)"),
            ("role_relevance", "Role (10%)"),
            ("location", "Location (10%)"),
        ]
        for idx, (key, label) in enumerate(labels):
            with cols[idx]:
                val = component_scores.get(key)
                st.metric(label=label, value=f"{val}" if val is not None else "—")

    s_col1, s_col2 = st.columns(2)
    with s_col1:
        st.markdown("**Matched Skills**")
        render_tag_pills(list(evaluation.get("matched_skills") or []), "No matched skills listed")
        st.markdown("**Strengths**")
        for item in evaluation.get("strengths") or []:
            st.markdown(f"- {item}")
    with s_col2:
        st.markdown("**Missing Skills**")
        render_tag_pills(list(evaluation.get("missing_skills") or []), "No missing skills listed")
        st.markdown("**Concerns**")
        for item in evaluation.get("concerns") or []:
            st.markdown(f"- {item}")

    explanation = evaluation.get("explanation")
    if explanation:
        render_callout(
            title=f"Evaluation Rationale ({model_name} · {eval_version})",
            body=str(explanation),
            tone="info",
        )
