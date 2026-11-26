"""Versioned backend architecture policies used by generation workflows."""

from src.policy.backend_policy import (
    BACKEND_POLICY_PROMPT_VERSION,
    load_backend_policy,
    policy_sections,
    policy_text_for_task,
)

__all__ = [
    "BACKEND_POLICY_PROMPT_VERSION",
    "load_backend_policy",
    "policy_sections",
    "policy_text_for_task",
]
