"""Run lifecycle constants and transition rules."""

TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})
RESUMABLE_RUN_STATUSES = frozenset({"failed", "cancelled", "paused"})


def can_cancel(status: str) -> bool:
    return status not in TERMINAL_RUN_STATUSES


def can_resume(status: str) -> bool:
    return status in RESUMABLE_RUN_STATUSES
