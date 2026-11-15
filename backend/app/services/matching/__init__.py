"""Profile matching, mandatory eligibility checks, weighted scoring, and task policy."""

from app.services.matching.eligibility import (
    ConditionCheckResult,
    ConditionStatus,
    EligibilityResult,
    EligibilityStatus,
    JobRequirementsSnapshot,
    ProfileSnapshot,
    ResumeSnapshot,
    evaluate_eligibility,
)
from app.services.matching.scorer import (
    EVALUATION_VERSION,
    SCORE_WEIGHTS,
    ComponentScores,
    JobEvaluationResult,
    OllamaJobEvaluationSchema,
    RecommendationType,
    aevaluate_job,
    compute_weighted_score,
    evaluate_job,
    recommend_best_resume,
)
from app.services.matching.task_policy import (
    ScoreBandLabel,
    ScoreBandResult,
    TaskPolicyThresholds,
    TaskTemplate,
    classify_score_band,
    generate_application_tasks,
)

__all__ = [
    "ComponentScores",
    "ConditionCheckResult",
    "ConditionStatus",
    "EVALUATION_VERSION",
    "EligibilityResult",
    "EligibilityStatus",
    "JobEvaluationResult",
    "JobRequirementsSnapshot",
    "OllamaJobEvaluationSchema",
    "ProfileSnapshot",
    "RecommendationType",
    "ResumeSnapshot",
    "SCORE_WEIGHTS",
    "ScoreBandLabel",
    "ScoreBandResult",
    "TaskPolicyThresholds",
    "TaskTemplate",
    "aevaluate_job",
    "classify_score_band",
    "compute_weighted_score",
    "evaluate_eligibility",
    "evaluate_job",
    "generate_application_tasks",
    "recommend_best_resume",
]
