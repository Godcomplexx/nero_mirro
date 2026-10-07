"""Shared trial journal primitives for browser-based training games."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True, frozen=True)
class TrialRecord:
    """One presented stimulus and the response received for it."""

    index: int
    stimulus: dict[str, Any]
    answer: dict[str, Any]
    elapsed_ms: float
    valid: bool
    recorded_at: str = field(default_factory=_utc_now)


class TrialJournal:
    """Accumulates serialisable trial records and builds checkpoints/reports."""

    def __init__(self, *, game_id: str, session_id: str) -> None:
        self.game_id = game_id
        self.session_id = session_id
        self._records: list[TrialRecord] = []

    def append(
        self,
        *,
        index: int,
        stimulus: dict[str, Any],
        answer: dict[str, Any],
        elapsed_ms: float,
        valid: bool,
    ) -> TrialRecord:
        record = TrialRecord(
            index=index,
            stimulus=deepcopy(stimulus),
            answer=deepcopy(answer),
            elapsed_ms=max(0.0, float(elapsed_ms)),
            valid=bool(valid),
        )
        self._records.append(record)
        return record

    def records(self) -> list[dict[str, Any]]:
        return [asdict(record) for record in self._records]

    def checkpoint(self, *, next_index: int) -> dict[str, Any]:
        return {
            "source": self.game_id,
            "session_id": self.session_id,
            "next_index": next_index,
            "trials": self.records(),
        }

    def report(self, *, metrics: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "training_game",
            "game_id": self.game_id,
            "session_id": self.session_id,
            "metrics": deepcopy(metrics),
            "trials": self.records(),
        }
