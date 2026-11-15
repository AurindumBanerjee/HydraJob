"""Offline engine tests for 18-category email classification, matching, and Gmail adapter."""

import json
from pathlib import Path

import httpx
import pytest

from app.services.email import (
    EMAIL_CATEGORIES,
    GMAIL_READONLY_SCOPE,
    ApplicationMatchCandidate,
    EmailCategory,
    EmailClassificationResult,
    EmailMatchSignal,
    EmailSyncCheckpoint,
    GmailNotConfiguredError,
    ReadOnlyGmailApiAdapter,
    SyntheticGmailAdapter,
    aclassify_email,
    classify_email,
    is_status_regression,
    match_email_to_applications,
    parse_synthetic_messages,
)
from app.services.llm import OllamaClient

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Email Classification (All 18 Categories + Ollama Refinement/Fallback)
# ---------------------------------------------------------------------------


def test_classifier_covers_all_18_categories() -> None:
    assert len(EMAIL_CATEGORIES) == 18

    cases: list[tuple[str, str, EmailCategory]] = [
        (
            "Thank you for applying to Acme AI",
            "We appreciate your application for ML Intern.",
            EmailCategory.APPLICATION_ACKNOWLEDGEMENT,
        ),
        (
            "Application received - Data Science Intern",
            "We have received your application and it has been submitted.",
            EmailCategory.APPLICATION_RECEIVED,
        ),
        (
            "Your application is under review",
            "Our hiring team is currently reviewing your application.",
            EmailCategory.UNDER_REVIEW,
        ),
        (
            "HackerRank Online Assessment Invitation",
            "You are invited to complete an online assessment within 48 hours.",
            EmailCategory.OA_INVITATION,
        ),
        (
            "Assessment Reminder: Complete your coding challenge",
            "Deadline approaching soon for your HackerRank assessment.",
            EmailCategory.ASSESSMENT_REMINDER,
        ),
        (
            "Assessment Submission Confirmed",
            "Thank you for completing the online assessment.",
            EmailCategory.ASSESSMENT_COMPLETED,
        ),
        (
            "Take-home technical test for AI Engineer",
            "Please submit your take-home assignment within 3 days.",
            EmailCategory.TECHNICAL_TEST,
        ),
        (
            "Interview Invitation - Applied AI Team",
            "We would like to schedule a technical interview. Please book an interview slot.",
            EmailCategory.INTERVIEW_INVITATION,
        ),
        (
            "Interview Rescheduled - New Time",
            "We have rescheduled your interview to Friday at 3 PM IST.",
            EmailCategory.INTERVIEW_RESCHEDULE,
        ),
        (
            "Following up on your recent interview",
            "Thank you for interviewing with our team; sharing brief interview feedback.",
            EmailCategory.INTERVIEW_FEEDBACK,
        ),
        (
            "Next Round Invitation - Final Round",
            "You have been invited to the final round of interviews.",
            EmailCategory.NEXT_ROUND,
        ),
        (
            "Update on your application",
            "Regret to inform you that we are not moving forward with your candidacy.",
            EmailCategory.REJECTION,
        ),
        (
            "Formal Offer of Employment - Acme AI",
            "We are pleased to extend a formal offer letter for ML Engineer.",
            EmailCategory.OFFER,
        ),
        (
            "Document Verification Request",
            "Please upload your official transcript and degree certificate.",
            EmailCategory.DOCUMENT_REQUEST,
        ),
        (
            "Additional Information Required",
            "Could you confirm your graduation date and notice period?",
            EmailCategory.INFORMATION_REQUEST,
        ),
        (
            "Application Withdrawal Confirmation",
            "Confirming your withdrawal; your application has been withdrawn.",
            EmailCategory.WITHDRAWAL,
        ),
        (
            "Monthly Newsletter & Invoice #9123",
            "Your invoice #9123 is attached. Unsubscribe from marketing emails.",
            EmailCategory.NON_RECRUITMENT,
        ),
        (
            "Quick hello",
            "Checking in regarding Tuesday notes.",
            EmailCategory.UNKNOWN,
        ),
    ]

    seen_categories = set()
    for subject, snippet, expected in cases:
        result = classify_email(subject=subject, snippet=snippet, sender_domain="acmeai.com")
        assert result.category == expected
        seen_categories.add(result.category.value)

    assert seen_categories == set(EMAIL_CATEGORIES)


async def test_aclassify_email_ollama_refinement_and_fallback() -> None:
    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "category": "NEXT_ROUND",
                            "confidence": 0.94,
                            "rationale": "Invites candidate to final onsite round.",
                        }
                    )
                }
            },
        )

    ok_client = OllamaClient(
        model="llama3.1:8b",
        backoff_seconds=0.0,
        async_transport=httpx.MockTransport(ok_handler),
    )
    refined = await aclassify_email(
        subject="Tuesday conversation",
        snippet="Meet our VP for final discussion.",
        sender_domain="acmeai.com",
        ollama_client=ok_client,
        use_ollama=True,
    )
    assert refined.used_llm is True
    assert refined.category == EmailCategory.NEXT_ROUND
    assert refined.confidence == 0.94

    def bad_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "invalid json"}})

    bad_client = OllamaClient(
        model="llama3.1:8b",
        max_retries=1,
        backoff_seconds=0.0,
        async_transport=httpx.MockTransport(bad_handler),
    )
    fallback = await aclassify_email(
        subject="HackerRank Online Assessment Invitation",
        snippet="Complete your online assessment.",
        sender_domain="acmeai.com",
        ollama_client=bad_client,
        use_ollama=True,
    )
    assert fallback.used_llm is False
    assert fallback.category == EmailCategory.OA_INVITATION


# ---------------------------------------------------------------------------
# Matching, Ambiguity, Confidence Policy, and Regression Prevention Tests
# ---------------------------------------------------------------------------


def _candidate_pool() -> list[ApplicationMatchCandidate]:
    return [
        ApplicationMatchCandidate(
            application_id=101,
            job_id=1,
            company_name="Acme AI",
            company_domain="acmeai.com",
            job_title="Machine Learning Engineer Intern",
            current_status="APPLIED",
            thread_id="thr-acme-ml",
            application_ref="APP-1001",
        ),
        ApplicationMatchCandidate(
            application_id=102,
            job_id=2,
            company_name="NovaQuant",
            company_domain="novaquant.com",
            job_title="AI Systems Engineer",
            current_status="INTERVIEW_COMPLETED",
            thread_id="thr-nova-offer",
            application_ref="APP-2002",
        ),
        ApplicationMatchCandidate(
            application_id=103,
            job_id=3,
            company_name="VectorLabs",
            company_domain="vectorlabs.com",
            job_title="NLP Research Intern",
            current_status="REJECTED",
            thread_id="thr-vector-rej",
        ),
        ApplicationMatchCandidate(
            application_id=104,
            job_id=4,
            company_name="BigTech",
            company_domain="bigtech.com",
            job_title="Machine Learning Intern",
            current_status="APPLIED",
        ),
        ApplicationMatchCandidate(
            application_id=105,
            job_id=5,
            company_name="BigTech",
            company_domain="bigtech.com",
            job_title="Backend Systems Intern",
            current_status="APPLIED",
        ),
    ]


def test_matching_confidence_policy_ambiguity_and_duplicates() -> None:
    pool = _candidate_pool()

    # 1. >=0.90 + unambiguous -> auto apply
    oa_cls = classify_email(
        subject="HackerRank Online Assessment Invitation - Machine Learning Engineer Intern",
        snippet="Complete your online assessment within 72 hours.",
        sender_domain="acmeai.com",
    )
    oa_match = match_email_to_applications(
        signal=EmailMatchSignal(
            gmail_message_id="msg-oa-1",
            thread_id="thr-acme-ml",
            sender="careers@acmeai.com",
            sender_domain="acmeai.com",
            subject="HackerRank Online Assessment Invitation",
            snippet="Complete your online assessment.",
        ),
        classification=oa_cls,
        candidates=pool,
    )
    assert oa_match.decision == "AUTO_APPLY"
    assert oa_match.should_apply_status is True
    assert oa_match.needs_review is False
    assert oa_match.matched_application_id == 101
    assert oa_match.proposed_status == "OA_RECEIVED"

    # 2. Match by application_ref (without thread_id)
    offer_cls = classify_email(
        subject="Formal Offer of Internship - APP-2002",
        snippet="We are pleased to extend a formal offer letter.",
        sender_domain="novaquant.com",
    )
    offer_match = match_email_to_applications(
        signal=EmailMatchSignal(
            gmail_message_id="msg-offer-1",
            thread_id="thr-brand-new",
            sender="talent@novaquant.com",
            sender_domain="novaquant.com",
            subject="Formal Offer of Internship (APP-2002)",
            snippet="Formal offer attached.",
            application_ref="APP-2002",
        ),
        classification=offer_cls,
        candidates=pool,
    )
    assert offer_match.decision == "AUTO_APPLY"
    assert offer_match.matched_application_id == 102
    assert offer_match.proposed_status == "OFFER_RECEIVED"

    # 3. Multiple active applications at BigTech without disambiguating title -> AMBIGUOUS -> review
    ambig_cls = classify_email(
        subject="Interview invitation at BigTech",
        snippet="We would like to schedule an interview.",
        sender_domain="bigtech.com",
    )
    ambig_match = match_email_to_applications(
        signal=EmailMatchSignal(
            gmail_message_id="msg-ambig-1",
            sender="recruiting@bigtech.com",
            sender_domain="bigtech.com",
            subject="Interview invitation at BigTech",
            snippet="Schedule an interview.",
        ),
        classification=ambig_cls,
        candidates=pool,
    )
    assert ambig_match.is_ambiguous is True
    assert ambig_match.needs_review is True
    assert ambig_match.should_apply_status is False
    assert set(ambig_match.candidate_application_ids) == {104, 105}

    # 4. Multiple active applications at BigTech WITH distinct job title -> disambiguated!
    disambig_match = match_email_to_applications(
        signal=EmailMatchSignal(
            gmail_message_id="msg-disambig-1",
            sender="recruiting@bigtech.com",
            sender_domain="bigtech.com",
            subject="Interview Invitation - Machine Learning Intern at BigTech",
            snippet="Schedule your Machine Learning Intern technical interview.",
        ),
        classification=ambig_cls,
        candidates=pool,
    )
    assert disambig_match.is_ambiguous is False
    assert disambig_match.matched_application_id == 104
    assert disambig_match.should_apply_status is True
    assert disambig_match.proposed_status == "INTERVIEW_SCHEDULED"

    # 5. Confidence 0.70-0.89 -> needs_review=True, no auto update
    med_cls = EmailClassificationResult(
        category=EmailCategory.INTERVIEW_INVITATION,
        confidence=0.80,
        rationale="Weak interview mention",
    )
    med_match = match_email_to_applications(
        signal=EmailMatchSignal(
            gmail_message_id="msg-med-1",
            thread_id="thr-acme-ml",
            sender="careers@acmeai.com",
            sender_domain="acmeai.com",
            subject="Quick interview chat",
            snippet="Let us chat.",
        ),
        classification=med_cls,
        candidates=pool,
    )
    assert med_match.decision == "NEEDS_REVIEW"
    assert med_match.needs_review is True
    assert med_match.should_apply_status is False

    # 6. Confidence < 0.70 -> no auto update
    low_cls = EmailClassificationResult(
        category=EmailCategory.UNDER_REVIEW,
        confidence=0.55,
        rationale="Uncertain phrasing",
    )
    low_match = match_email_to_applications(
        signal=EmailMatchSignal(
            gmail_message_id="msg-low-1",
            thread_id="thr-acme-ml",
            sender="careers@acmeai.com",
            sender_domain="acmeai.com",
            subject="Checking in",
            snippet="Status update",
        ),
        classification=low_cls,
        candidates=pool,
    )
    assert low_match.decision == "NO_AUTO_UPDATE"
    assert low_match.should_apply_status is False

    # 7. Duplicate message ignored
    dup_match = match_email_to_applications(
        signal=EmailMatchSignal(
            gmail_message_id="msg-oa-1",
            thread_id="thr-acme-ml",
            sender="careers@acmeai.com",
            sender_domain="acmeai.com",
            subject="HackerRank Online Assessment Invitation",
            snippet="Complete your online assessment.",
        ),
        classification=oa_cls,
        candidates=pool,
        processed_message_ids={"msg-oa-1"},
    )
    assert dup_match.is_duplicate_message is True
    assert dup_match.decision == "DUPLICATE_IGNORED"
    assert dup_match.should_apply_status is False


def test_status_regression_prevention() -> None:
    assert is_status_regression("INTERVIEW_SCHEDULED", "ACKNOWLEDGED") is True
    assert is_status_regression("REJECTED", "INTERVIEW_SCHEDULED") is True
    assert is_status_regression("OFFER_RECEIVED", "UNDER_REVIEW") is True
    assert is_status_regression("APPLIED", "OA_RECEIVED") is False
    assert is_status_regression("OA_RECEIVED", "REJECTED") is False

    # Delayed acknowledgement arriving for an already REJECTED application must be blocked
    pool = _candidate_pool()
    ack_cls = classify_email(
        subject="Thank you for applying to VectorLabs",
        snippet="Thank you for applying for NLP Research Intern.",
        sender_domain="vectorlabs.com",
    )
    reg_match = match_email_to_applications(
        signal=EmailMatchSignal(
            gmail_message_id="msg-delayed-ack",
            thread_id="thr-vector-rej",
            sender="no-reply@vectorlabs.com",
            sender_domain="vectorlabs.com",
            subject="Thank you for applying",
            snippet="We acknowledge receipt of your application.",
        ),
        classification=ack_cls,
        candidates=pool,
    )
    assert reg_match.regression_blocked is True
    assert reg_match.should_apply_status is False
    assert reg_match.needs_review is True
    assert reg_match.decision == "NO_UPDATE_REGRESSION_BLOCKED"


# ---------------------------------------------------------------------------
# Offline Synthetic Inbox & Read-only Gmail Adapter Tests
# ---------------------------------------------------------------------------


async def test_synthetic_fixture_and_readonly_gmail_adapter() -> None:
    raw_fixture = (FIXTURES_DIR / "synthetic_emails.json").read_text(encoding="utf-8")
    parsed = parse_synthetic_messages(raw_fixture)
    # 8 fixture entries, 1 duplicate msg-001 -> 7 unique normalized messages
    assert len(parsed) == 7
    assert parsed[0].gmail_message_id == "msg-001"
    assert parsed[0].application_ref == "APP-1001"
    assert parsed[0].received_at.utcoffset().total_seconds() == 0

    adapter = SyntheticGmailAdapter(raw_fixture)
    assert adapter.is_configured() is True
    batch1, ckpt1 = await adapter.list_messages(label="recruitment", max_results=3)
    assert len(batch1) == 3
    assert len(ckpt1.seen_message_ids) == 3

    batch2, ckpt2 = await adapter.list_messages(
        label="recruitment",
        checkpoint=ckpt1,
        max_results=10,
    )
    assert len(batch2) == 4
    assert len(ckpt2.seen_message_ids) == 7

    # Read-only Gmail API adapter without credentials fails clearly
    unconfigured = ReadOnlyGmailApiAdapter()
    assert unconfigured.scopes == (GMAIL_READONLY_SCOPE,)
    assert unconfigured.is_configured() is False
    with pytest.raises(GmailNotConfiguredError):
        await unconfigured.list_messages()

    # Read-only Gmail API adapter with mocked HTTPX transport
    def gmail_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer mock-ro-token"
        if request.url.path.endswith("/users/me/messages"):
            return httpx.Response(200, json={"messages": [{"id": "g-1"}]})
        if request.url.path.endswith("/users/me/messages/g-1"):
            assert request.url.params.get("format") == "metadata"
            return httpx.Response(
                200,
                json={
                    "id": "g-1",
                    "threadId": "thr-g-1",
                    "historyId": "9001",
                    "internalDate": "1762000000000",
                    "snippet": "We received your application for ML Intern (APP-555).",
                    "labelIds": ["recruitment"],
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Talent <jobs@example.org>"},
                            {"name": "Subject", "value": "Application Received"},
                        ]
                    },
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(gmail_handler)) as http_client:
        ro_adapter = ReadOnlyGmailApiAdapter(access_token="mock-ro-token", client=http_client)
        assert ro_adapter.is_configured() is True
        msgs, ckpt = await ro_adapter.list_messages(checkpoint=EmailSyncCheckpoint())
        assert len(msgs) == 1
        assert msgs[0].sender_domain == "example.org"
        assert msgs[0].application_ref == "APP-555"
        assert ckpt.last_history_id == "9001"
