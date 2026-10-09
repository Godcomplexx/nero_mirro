"""Deterministic, testable rules for selecting a game form within a domain."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
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
class CourseRanking:
    """Приоритеты выбора формы внутри курса.

    Порядок — из «Методики подбора и оценки тренировочного курса», раздел
    4.4: формы с уровнями сложности (раздел 5.2: формы без уровней идут, когда
    домену не хватает адаптивных), реже выбираются отмеченные «трудная» и
    «потолок» (раздел 6.3), затем механика, реже встречавшаяся в курсе, и
    форма, которой не было в прошлом занятии.
    """

    adaptive_codes: frozenset[str] = frozenset()
    discouraged_codes: frozenset[str] = frozenset()
    mechanic_counts: Mapping[str, int] = field(default_factory=dict)
    previous_session_codes: frozenset[str] = frozenset()


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
    definitions: tuple[GameDefinition, ...] = GAME_CATALOG,
    previous: GameDefinition | None = None,
    course: CourseRanking | None = None,
) -> SelectionDecision:
    """Select without repeating a form; preferences are compared lexicographically.

    The matrix does not define numeric weights, so none are invented here.
    Mechanic alternation, modality alternation and prior exposure are ordered,
    observable conditions with a stable game-code tie breaker.

    ``previous`` is the form placed just before in the same session: mechanics
    and modalities alternate against it, and against the last presentation in
    history only at the start of a session.
    """
    candidates = [item for item in definitions if item.primary_domain == primary_domain]
    if available_codes is not None:
        candidates = [item for item in candidates if item.code in available_codes]
    candidates = [item for item in candidates if item.code not in session_game_codes]
    if not candidates:
        raise NoEligibleGameError(
            f"Нет неповторяющейся формы для ведущего домена {primary_domain.value}"
        )

    last = previous if previous is not None else (history[-1] if history else None)
    course = course or CourseRanking()
    counts = {item.code: 0 for item in candidates}
    latest: dict[str, float] = {item.code: float("-inf") for item in candidates}
    for entry in history:
        if entry.game_code in counts:
            counts[entry.game_code] += 1
            latest[entry.game_code] = max(latest[entry.game_code], entry.presented_at.timestamp())

    def mechanic_exposure(item: GameDefinition) -> int:
        return sum(course.mechanic_counts.get(mechanic, 0) for mechanic in item.mechanics)

    def rank(item: GameDefinition) -> tuple[object, ...]:
        repeats_mechanic = bool(last and set(item.mechanics) & set(last.mechanics))
        repeats_modality = bool(last and set(item.modalities) & set(last.modalities))
        return (
            bool(course.adaptive_codes) and item.code not in course.adaptive_codes,
            item.code in course.discouraged_codes,
            mechanic_exposure(item),
            item.code in course.previous_session_codes,
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
    if selected.code in course.adaptive_codes:
        reasons.append("у формы есть уровни сложности")
    if selected.code in course.discouraged_codes:
        reasons.append("форма с отметкой «трудная» или «потолок»: других форм домена нет")
    if course.previous_session_codes and selected.code not in course.previous_session_codes:
        reasons.append("формы не было в прошлом занятии")
    if last and not set(selected.mechanics) & set(last.mechanics):
        reasons.append("механика чередуется")
    if last and not set(selected.modalities) & set(last.modalities):
        reasons.append("модальность чередуется")
    if counts[selected.code] == 0:
        reasons.append("форма ранее не предъявлялась")
    return SelectionDecision(selected, stimulus_set, tuple(reasons))
