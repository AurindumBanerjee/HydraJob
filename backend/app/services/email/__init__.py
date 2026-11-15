"""Recruitment email classification, application matching, and read-only Gmail adapters."""

from app.services.email.classifier import (
    EMAIL_CATEGORIES,
    EmailCategory,
    EmailClassificationResult,
    OllamaEmailClassificationSchema,
    aclassify_email,
    classify_email,
)
from app.services.email.gmail_adapter import (
    GMAIL_READONLY_SCOPE,
    EmailSyncCheckpoint,
    GmailAdapter,
    GmailNotConfiguredError,
    NormalizedEmailMessage,
    ReadOnlyGmailApiAdapter,
    SyntheticGmailAdapter,
    parse_synthetic_messages,
)
from app.services.email.matcher import (
    AUTO_APPLY_CONFIDENCE_THRESHOLD,
    REVIEW_CONFIDENCE_THRESHOLD,
    ApplicationMatchCandidate,
    ApplicationStatusType,
    EmailMatchResult,
    EmailMatchSignal,
    MatchDecisionType,
    is_status_regression,
    match_email_to_applications,
)

__all__ = [
    "AUTO_APPLY_CONFIDENCE_THRESHOLD",
    "ApplicationMatchCandidate",
    "ApplicationStatusType",
    "EMAIL_CATEGORIES",
    "EmailCategory",
    "EmailClassificationResult",
    "EmailMatchResult",
    "EmailMatchSignal",
    "EmailSyncCheckpoint",
    "GMAIL_READONLY_SCOPE",
    "GmailAdapter",
    "GmailNotConfiguredError",
    "MatchDecisionType",
    "NormalizedEmailMessage",
    "OllamaEmailClassificationSchema",
    "REVIEW_CONFIDENCE_THRESHOLD",
    "ReadOnlyGmailApiAdapter",
    "SyntheticGmailAdapter",
    "aclassify_email",
    "classify_email",
    "is_status_regression",
    "match_email_to_applications",
    "parse_synthetic_messages",
]
