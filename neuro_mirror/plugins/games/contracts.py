"""Stable contracts shared by the game catalog, selector and plugins."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Domain(StrEnum):
    MEMORY = "memory"
    ATTENTION = "attention"
    SPEECH = "speech"
    ABSTRACTION = "abstraction"


class Modality(StrEnum):
    VISUAL = "visual"
    AUDITORY = "auditory"


class ResponseType(StrEnum):
    CLICK = "click"
    DRAG = "drag"
    POINTER = "pointer"
    SPOKEN = "spoken"


@dataclass(frozen=True, slots=True)
class DifficultyLevel:
    level: int
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GameDefinition:
    code: str
    slug: str
    title: str
    domains: tuple[Domain, ...]
    mechanics: tuple[str, ...]
    modalities: tuple[Modality, ...]
    response_type: ResponseType
    stimulus_sets: tuple[str, ...]
    difficulty_parameter: str = ""
    difficulty_levels: tuple[DifficultyLevel, ...] = ()
    primary_metrics: tuple[str, ...] = ()
    additional_metrics: tuple[str, ...] = ()

    @property
    def primary_domain(self) -> Domain:
        """The spreadsheet defines the first listed domain as the leading one."""
        return self.domains[0]

    @property
    def topic_prefix(self) -> str:
        return self.code.lower().replace("-", "")

    @property
    def start_request_topic(self) -> str:
        return f"req.game.{self.topic_prefix}.start"

    @property
    def start_response_topic(self) -> str:
        return f"resp.game.{self.topic_prefix}.start"

    @property
    def answer_request_topic(self) -> str:
        return f"req.game.{self.topic_prefix}.answer"

    @property
    def answer_response_topic(self) -> str:
        return f"resp.game.{self.topic_prefix}.answer"

    def to_public_dict(self, *, implemented: bool) -> dict[str, Any]:
        data = asdict(self)
        data["primary_domain"] = self.primary_domain.value
        data["implemented"] = implemented
        return data


@dataclass(frozen=True, slots=True)
class GameResult:
    game_code: str
    session_id: str
    completion_status: str
    technical_validity: str
    metrics: dict[str, Any]
    trials: tuple[dict[str, Any], ...]


def normalise_game_code(value: str) -> str:
    compact = value.strip().upper().replace("_", "-")
    if compact.startswith("GM") and not compact.startswith("GM-"):
        compact = f"GM-{compact[2:]}"
    return compact
