from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class DeviceInfo:
    device_id: str
    kind: str
    label: str
    available: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DeviceSelection:
    camera_id: str = ""
    microphone_id: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DeviceSelection":
        return cls(
            camera_id=str(payload.get("camera_id") or payload.get("selected_camera_id") or ""),
            microphone_id=str(payload.get("microphone_id") or payload.get("selected_microphone_id") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SelectedDevices:
    camera: DeviceInfo | None = None
    microphone: DeviceInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera": self.camera.to_dict() if self.camera else None,
            "microphone": self.microphone.to_dict() if self.microphone else None,
            "selected_camera_id": self.camera.device_id if self.camera else "",
            "selected_microphone_id": self.microphone.device_id if self.microphone else "",
        }


@dataclass(slots=True)
class DeviceValidation:
    ok: bool
    selected_devices: SelectedDevices
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "selected_devices": self.selected_devices.to_dict(),
            "errors": list(self.errors),
        }
