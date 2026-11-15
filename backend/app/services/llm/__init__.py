"""Local Ollama LLM service abstraction and versioned prompt templates."""

from app.services.llm.ollama_client import (
    OllamaClient,
    OllamaClientError,
    OllamaHealthStatus,
    OllamaStructuredResponse,
)
from app.services.llm.prompts import (
    EMAIL_CLASSIFICATION_PROMPT_VERSION,
    JOB_EVALUATION_PROMPT_VERSION,
    JOB_EXTRACTION_PROMPT_VERSION,
    PROMPT_VERSION,
    PromptTemplate,
    build_email_classification_prompt,
    build_job_evaluation_prompt,
    build_job_extraction_prompt,
)

__all__ = [
    "EMAIL_CLASSIFICATION_PROMPT_VERSION",
    "JOB_EVALUATION_PROMPT_VERSION",
    "JOB_EXTRACTION_PROMPT_VERSION",
    "OllamaClient",
    "OllamaClientError",
    "OllamaHealthStatus",
    "OllamaStructuredResponse",
    "PROMPT_VERSION",
    "PromptTemplate",
    "build_email_classification_prompt",
    "build_job_evaluation_prompt",
    "build_job_extraction_prompt",
]
