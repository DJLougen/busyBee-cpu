"""Workflow state machine for enforcing action sequencing and detecting loops.

Tracks per-session action history and suggests corrective actions when the
predicted tool violates workflow constraints (e.g., reading before patching).
"""
from __future__ import annotations

import time
from typing import Any

# Valid predecessor sets per action.  Empty set means "any predecessor is fine".
_TRANSITIONS: dict[str, frozenset[str]] = {
    "apply_patch": frozenset({"read_file"}),
    "run_tests": frozenset({"apply_patch", "run_tests", "read_file"}),
    "escalate": frozenset(),
    "clarify": frozenset(),
    # Browser export workflow
    "browser_navigate": frozenset(),
    "browser_click": frozenset({"browser_navigate", "browser_click", "browser_type"}),
    "browser_type": frozenset({"browser_navigate", "browser_click"}),
    "browser_export": frozenset({"browser_click", "browser_navigate"}),
}

# Forced first actions when no history exists and certain tools are available.
_FORCE_FIRST: dict[str, str] = {
    "apply_patch": "read_file",
    "browser_click": "browser_navigate",
    "browser_type": "browser_navigate",
    "browser_export": "browser_navigate",
}


class WorkflowTracker:
    """Tracks per-session action history and suggests workflow corrections."""

    def __init__(self, max_history: int = 20, ttl_seconds: int = 600) -> None:
        self._sessions: dict[str, list[dict[str, Any]]] = {}
        self._access: dict[str, float] = {}
        self._max_history = max_history
        self._ttl_seconds = ttl_seconds

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def record(self, session_id: str, tool: str) -> None:
        now = time.monotonic()
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._sessions[session_id].append({"tool": tool, "ts": now})
        if len(self._sessions[session_id]) > self._max_history:
            self._sessions[session_id] = self._sessions[session_id][-self._max_history :]
        self._access[session_id] = now
        self._evict(now)

    def get_history(self, session_id: str) -> list[str]:
        return [entry["tool"] for entry in self._sessions.get(session_id, [])]

    def suggest(self, predicted_tool: str, *, session_id: str, available: set[str] | None = None) -> str | None:
        """Return a forced action if the workflow dictates a different step.

        Returns ``None`` when the prediction is acceptable as-is.
        """
        history = self.get_history(session_id)
        last_tool = history[-1] if history else None

        # Force first action for certain tools
        if not last_tool and predicted_tool in _FORCE_FIRST:
            forced = _FORCE_FIRST[predicted_tool]
            if not available or forced in available:
                return forced

        # Check valid transitions
        valid_preds = _TRANSITIONS.get(predicted_tool)
        if valid_preds and last_tool and last_tool not in valid_preds:
            # Suggest the first valid predecessor if available
            for predecessor in valid_preds:
                if not available or predecessor in available:
                    return predecessor

        return None

    def check_loop(self, predicted_tool: str, *, session_id: str, target_tool: str | None = None) -> bool:
        """Return True if the prediction would create an unintended action loop."""
        history = self.get_history(session_id)
        if len(history) < 2:
            return False
        if target_tool == predicted_tool:
            return False
        return history[-1] == predicted_tool and history[-2] == predicted_tool

    def cleanup(self) -> int:
        """Remove expired sessions.  Returns count removed."""
        now = time.monotonic()
        expired = [
            sid
            for sid, ts in self._access.items()
            if now - ts > self._ttl_seconds
        ]
        for sid in expired:
            self._sessions.pop(sid, None)
            self._access.pop(sid, None)
        return len(expired)

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _evict(self, now: float) -> None:
        if len(self._sessions) > 500:
            self.cleanup()
