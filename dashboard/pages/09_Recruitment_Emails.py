"""Recruitment Emails page: classification review queue, linking, and synthetic testing."""

from __future__ import annotations

from uuid import uuid4

import streamlit as st

from components.status_badge import format_status_badge_html
from components.system_view import render_sidebar
from components.theme import (
    inject_editorial_theme,
    render_callout,
    render_page_hero,
    render_section_kicker,
)
from components.widgets import pagination_controls, show_api_error
from services.api_client import build_api_client_from_env
from services.time_utils import format_kolkata_timestamp

EMAIL_CLASSIFICATIONS = [
    "APPLICATION_ACKNOWLEDGEMENT",
    "APPLICATION_RECEIVED",
    "UNDER_REVIEW",
    "OA_INVITATION",
    "ASSESSMENT_REMINDER",
    "ASSESSMENT_COMPLETED",
    "TECHNICAL_TEST",
    "INTERVIEW_INVITATION",
    "INTERVIEW_RESCHEDULE",
    "INTERVIEW_FEEDBACK",
    "NEXT_ROUND",
    "REJECTION",
    "OFFER",
    "DOCUMENT_REQUEST",
    "INFORMATION_REQUEST",
    "WITHDRAWAL",
    "NON_RECRUITMENT",
    "UNKNOWN",
]


def main() -> None:
    """Render the Recruitment Emails classification and review queue page."""
    st.set_page_config(page_title="HydraJob — Recruitment Emails", layout="wide")
    inject_editorial_theme()

    with build_api_client_from_env() as client:
        render_sidebar(client.base_url, client.has_api_key)

    render_page_hero(
        kicker="HydraJob · Phase 8",
        title="Recruitment Email Intelligence",
        subtitle=(
            "Inspect classified recruitment updates, resolve ambiguous matches (0.70-0.89 confidence), "
            "and test synthetic inbox messages without exposing raw email bodies."
        ),
    )

    c1, c2 = st.columns(2)
    review_filter = c1.selectbox(
        "Review Queue Filter",
        options=["All Messages", "Needs Review Only", "Resolved Only"],
    )
    class_filter = c2.selectbox("Classification", options=["", *EMAIL_CLASSIFICATIONS])

    needs_review_param: bool | None = None
    if review_filter == "Needs Review Only":
        needs_review_param = True
    elif review_filter == "Resolved Only":
        needs_review_param = False

    render_section_kicker(
        number="01",
        label="Synthetic Test",
        title="Ingest Synthetic Recruitment Email",
        subtitle="Offline-safe test hook for classification, matching, and confidence policy verification.",
    )
    with st.expander("Test Synthetic Email Classification", expanded=False):
        form = st.form("synthetic_email_form")
        with form:
            e_msg_id = st.text_input(
                "Message ID (auto-generated if blank)",
                placeholder="synthetic-oa-001",
            )
            e_sender = st.text_input("Sender", value="recruiting@example-ai.com")
            e_subject = st.text_input("Subject", value="Online Assessment Invitation — ML Engineer")
            e_snippet = st.text_area(
                "Short Snippet (no private credentials)",
                value="Thank you for applying. Please complete your HackerRank OA within 5 days.",
            )
            e_thread = st.text_input("Thread ID (optional)")
            if st.form_submit_button("Classify & Ingest Synthetic Email", type="primary"):
                gmail_msg_id = e_msg_id.strip() or f"synthetic-{uuid4().hex[:12]}"
                with build_api_client_from_env() as client:
                    ing = client.ingest_synthetic_email(
                        {
                            "gmail_message_id": gmail_msg_id,
                            "sender": e_sender.strip(),
                            "subject": e_subject.strip(),
                            "snippet": e_snippet.strip(),
                            "thread_id": e_thread.strip() or None,
                        }
                    )
                if not show_api_error(ing, "Ingest Synthetic Email"):
                    st.success("Synthetic email classified and recorded.")

    with build_api_client_from_env() as client:
        init_emails = client.list_email_messages(
            needs_review=needs_review_param,
            classification=class_filter or None,
            limit=20,
            offset=0,
        )
        apps_res = client.list_applications(limit=100)

    apps = apps_res.items if apps_res.ok else []

    if show_api_error(init_emails, "Loading Recruitment Emails"):
        return

    render_section_kicker(
        number="02",
        label="Inbox Feed",
        title=f"Classified Messages ({init_emails.total})",
        subtitle="Confidence >= 0.90 unambiguous auto-updates; 0.70-0.89 queued for manual confirmation.",
    )
    limit, offset = pagination_controls("emails", init_emails.total, default_limit=20)
    if offset > 0 or limit != 20:
        with build_api_client_from_env() as client:
            emails_res = client.list_email_messages(
                needs_review=needs_review_param,
                classification=class_filter or None,
                limit=limit,
                offset=offset,
            )
    else:
        emails_res = init_emails

    messages = emails_res.items
    if not messages:
        render_callout("No Messages Recorded", "Ingest a synthetic message above or sync when Gmail is enabled.", tone="info")
        return

    app_choices = {"Unlinked": None}
    for app in apps:
        app_choices[f"App {str(app.get('id'))[:8]} ({app.get('status')})"] = str(app.get("id"))

    for msg in messages:
        mid = str(msg.get("id"))
        cls_name = str(msg.get("classification") or "UNKNOWN")
        needs_rev = bool(msg.get("needs_review"))
        conf = msg.get("confidence")
        conf_str = f"{float(conf):.2f}" if isinstance(conf, (int, float)) else "—"
        badge = format_status_badge_html(
            "needs_review" if needs_rev else "completed",
            label_override="Needs Review" if needs_rev else "Resolved",
        )
        with st.expander(f"{msg.get('subject', '(No Subject)')} · {cls_name} ({conf_str})", expanded=needs_rev):
            st.markdown(
                f"{badge} · **Sender:** `{msg.get('sender', 'unknown')}` · "
                f"**Received:** `{format_kolkata_timestamp(msg.get('received_at'))}`",
                unsafe_allow_html=True,
            )
            st.caption(f"Snippet: {msg.get('snippet') or 'No snippet stored'}")
            with st.form(f"review_email_{mid}"):
                new_cls = st.selectbox(
                    "Classification",
                    options=EMAIL_CLASSIFICATIONS,
                    index=EMAIL_CLASSIFICATIONS.index(cls_name)
                    if cls_name in EMAIL_CLASSIFICATIONS
                    else len(EMAIL_CLASSIFICATIONS) - 1,
                )
                linked_app = st.selectbox("Link to Application", options=list(app_choices.keys()))
                apply_status = st.checkbox("Apply status transition to linked application", value=True)
                notes = st.text_input("Review Notes", value=str(msg.get("review_notes") or ""))
                if st.form_submit_button("Confirm / Correct Classification", type="primary"):
                    with build_api_client_from_env() as client:
                        rev = client.review_email_message(
                            mid,
                            {
                                "classification": new_cls,
                                "matched_application_id": app_choices[linked_app],
                                "apply_status_update": apply_status,
                                "review_notes": notes.strip() or None,
                            },
                        )
                    if not show_api_error(rev, "Review Email Message"):
                        st.success("Email review saved.")
                        st.rerun()


if __name__ == "__main__":
    main()
