from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from neuro_mirror.interfaces.plugin import Plugin


class IUIContract(ABC):
    @abstractmethod
    async def apply_update(self, payload: dict[str, Any], *, source: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_snapshot(self) -> dict[str, Any]:
        raise NotImplementedError


class IOutputPlugin(Plugin, IUIContract):
    """Marker interface for UI/output plugins."""
