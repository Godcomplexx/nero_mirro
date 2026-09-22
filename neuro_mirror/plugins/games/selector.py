"""Deterministic, testable rules for selecting a game form within a domain."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from neuro_mirror.plugins.games.catalog import GAME_CATALOG
from neuro_mirror.plugins.games.contracts import Domain, GameDefinition, Modality


class NoEligibleGameError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class Presentation:
    game_code: str
    mechanics: tuple[str, ...]
    modalities: tuple[Modality, ...]
    stimulus_set: str
    presented_at: datetime


@dataclass(frozen=True, slots=True)
class SelectionDecision:
    game: GameDefinition
    stimulus_set: str
    reasons: tuple[str, ...]


def select_game(
    primary_domain: Domain,
    *,
    session_game_codes: frozenset[str] = frozenset(),
    session_stimulus_sets: frozenset[tuple[str, str]] = frozenset(),
    history: tuple[Presentation, ...] = (),
    available_codes: frozenset[str] | None = None,
) -> SelectionDecision:
    """Select without repeating a form; preferences are compared lexicographically.

    The matrix does not define numeric weights, so none are invented here.
    Mechanic alternation, modality alternation and prior exposure are ordered,
    observable conditions with a stable game-code tie breaker.
    """
    candidates = [item for item in GAME_CATALOG if item.primary_domain == primary_domain]
    if available_codes is not None:
        candidates = [item for item in candidates if item.code in available_codes]
    candidates = [item for item in candidates if item.code not in session_game_codes]
    if not candidates:
        raise NoEligibleGameError(
            f"Нет неповторяющейся формы для ведущего домена {primary_domain.value}"
        )

    last = history[-1] if history else None
    counts = {item.code: 0 for item in candidates}
    latest: dict[str, float] = {item.code: float("-inf") for item in candidates}
    for entry in history:
        if entry.game_code in counts:
            counts[entry.game_code] += 1
            latest[entry.game_code] = max(latest[entry.game_code], entry.presented_at.timestamp())

    def rank(item: GameDefinition) -> tuple[object, ...]:
        repeats_mechanic = bool(last and set(item.mechanics) & set(last.mechanics))
        repeats_modality = bool(last and set(item.modalities) & set(last.modalities))
        return (
            repeats_mechanic,
            repeats_modality,
            counts[item.code],
            latest[item.code],
            item.code,
        )

    selected = min(candidates, key=rank)
    used_sets = {
        entry.stimulus_set for entry in history if entry.game_code == selected.code
    }
    stimulus_candidates = [
        value
        for value in selected.stimulus_sets
        if (selected.code, value) not in session_stimulus_sets and value not in used_sets
    ]
    if not stimulus_candidates:
        stimulus_candidates = [
            value
            for value in selected.stimulus_sets
            if (selected.code, value) not in session_stimulus_sets
        ]
    if not stimulus_candidates:
        stimulus_candidates = list(selected.stimulus_sets)
    stimulus_set = stimulus_candidates[0] if stimulus_candidates else ""
    reasons = ["ведущий домен совпадает", "форма не повторяется в занятии"]
    if last and not set(selected.mechanics) & set(last.mechanics):
        reasons.append("механика чередуется")
    if last and not set(selected.modalities) & set(last.modalities):
        reasons.append("модальность чередуется")
    if counts[selected.code] == 0:
        reasons.append("форма ранее не предъявлялась")
    return SelectionDecision(selected, stimulus_set, tuple(reasons))
