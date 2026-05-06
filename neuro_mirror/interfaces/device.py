from __future__ import annotations

from abc import ABC, abstractmethod

from neuro_mirror.models.device import DeviceInfo, DeviceSelection, DeviceValidation


class IDeviceProvider(ABC):
    @abstractmethod
    def list_cameras(self) -> list[DeviceInfo]:
        raise NotImplementedError

    @abstractmethod
    def list_microphones(self) -> list[DeviceInfo]:
        raise NotImplementedError

    @abstractmethod
    def validate_selection(self, selection: DeviceSelection) -> DeviceValidation:
        raise NotImplementedError
