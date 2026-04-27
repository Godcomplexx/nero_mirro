from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neuro_mirror.core.settings import Settings
from neuro_mirror.interfaces.device import IDeviceProvider
from neuro_mirror.interfaces.plugin import Plugin
from neuro_mirror.models.device import DeviceInfo, DeviceSelection, DeviceValidation, SelectedDevices
from neuro_mirror.models.events import Event, Topics


@dataclass(slots=True)
class DeviceCatalog:
    cameras: list[DeviceInfo]
    microphones: list[DeviceInfo]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cameras": [item.to_dict() for item in self.cameras],
            "microphones": [item.to_dict() for item in self.microphones],
        }


class LocalDeviceProvider(IDeviceProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def list_cameras(self) -> list[DeviceInfo]:
        return [
            DeviceInfo(
                device_id=str(self.settings.camera_index),
                kind="camera",
                label=f"Camera {self.settings.camera_index}",
                available=True,
                metadata={"source": "settings", "index": self.settings.camera_index},
            )
        ]

    def list_microphones(self) -> list[DeviceInfo]:
        try:
            import sounddevice as sd  # type: ignore
        except Exception as exc:
            return [
                DeviceInfo(
                    device_id="default",
                    kind="microphone",
                    label="Default microphone",
                    available=False,
                    metadata={"error": str(exc)},
                )
            ]

        devices: list[DeviceInfo] = []
        try:
            for index, raw in enumerate(sd.query_devices()):
                max_input_channels = int(raw.get("max_input_channels") or 0)
                if max_input_channels <= 0:
                    continue
                devices.append(
                    DeviceInfo(
                        device_id=str(index),
                        kind="microphone",
                        label=str(raw.get("name") or f"Microphone {index}"),
                        available=True,
                        metadata={
                            "index": index,
                            "channels": max_input_channels,
                            "default_samplerate": raw.get("default_samplerate"),
                        },
                    )
                )
        except Exception as exc:
            devices.append(
                DeviceInfo(
                    device_id="default",
                    kind="microphone",
                    label="Default microphone",
                    available=False,
                    metadata={"error": str(exc)},
                )
            )

        return devices or [
            DeviceInfo(
                device_id="default",
                kind="microphone",
                label="Default microphone",
                available=False,
                metadata={"error": "input devices not found"},
            )
        ]

    def validate_selection(self, selection: DeviceSelection) -> DeviceValidation:
        cameras = self.list_cameras()
        microphones = self.list_microphones()
        camera = self._find_or_default(cameras, selection.camera_id)
        microphone = self._find_or_default(microphones, selection.microphone_id)
        selected = SelectedDevices(camera=camera, microphone=microphone)
        errors: list[str] = []

        if camera is None or not camera.available:
            errors.append("Камера недоступна или не выбрана.")
        if microphone is None or not microphone.available:
            errors.append("Микрофон недоступен или не выбран.")

        return DeviceValidation(ok=not errors, selected_devices=selected, errors=errors)

    @staticmethod
    def _find_or_default(items: list[DeviceInfo], device_id: str) -> DeviceInfo | None:
        if device_id:
            for item in items:
                if item.device_id == device_id:
                    return item
        for item in items:
            if item.available:
                return item
        return items[0] if items else None


class DeviceManager(Plugin):
    plugin_name = "device_manager"

    def __init__(
        self,
        bus,
        *,
        settings: Settings,
        provider: IDeviceProvider | None = None,
        selection_path: Path | None = None,
    ) -> None:
        super().__init__(bus)
        self.settings = settings
        self.provider = provider or LocalDeviceProvider(settings)
        self.selection_path = selection_path or Path("runtime") / "device_selection.json"
        self._last_catalog = DeviceCatalog(cameras=[], microphones=[])
        self._last_selection = DeviceSelection()

    def subscribed_topics(self) -> tuple[str, ...]:
        return (
            Topics.SYSTEM_BOOTSTRAP,
            Topics.PREPARE_SESSION,
            Topics.UI_DEVICE_SELECTED,
        )

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.SYSTEM_BOOTSTRAP:
            await self._publish_catalog()
            return

        if event.topic == Topics.UI_DEVICE_SELECTED:
            self._last_selection = DeviceSelection.from_payload(event.payload)
            self._save_selection(self._last_selection)
            await self._resolve_selection(event.payload)
            return

        if event.topic == Topics.PREPARE_SESSION:
            await self._resolve_selection(event.payload)

    async def _publish_catalog(self) -> None:
        self._last_catalog = DeviceCatalog(
            cameras=self.provider.list_cameras(),
            microphones=self.provider.list_microphones(),
        )
        self._last_selection = self._load_selection()
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "device_catalog": self._last_catalog.to_dict(),
                    "selected_devices": self._last_selection.to_dict(),
                    "worker_statuses": self._build_statuses(self._last_catalog),
                },
            )
        )

    async def _resolve_selection(self, payload: dict[str, Any]) -> None:
        if not self._last_catalog.cameras and not self._last_catalog.microphones:
            await self._publish_catalog()

        selection = DeviceSelection.from_payload(payload)
        if not selection.camera_id and not selection.microphone_id:
            selection = self._last_selection

        validation = self.provider.validate_selection(selection)
        require_microphone = bool(payload.get("require_microphone", False))
        if not require_microphone and validation.errors:
            validation = DeviceValidation(
                ok=not any("Камера" in item for item in validation.errors),
                selected_devices=validation.selected_devices,
                errors=[item for item in validation.errors if "Камера" in item],
            )
        resolved_payload = {
            **payload,
            **validation.to_dict(),
        }

        if not validation.ok:
            await self.bus.publish(
                Event(
                    topic=Topics.DEVICE_VALIDATION_FAILED,
                    source=self.name,
                    payload=resolved_payload,
                )
            )
            await self.bus.publish(
                Event(
                    topic=Topics.UI_DEVICE_WIZARD_OPEN,
                    source=self.name,
                    payload={
                        "device_catalog": self._last_catalog.to_dict(),
                        "selection": selection.to_dict(),
                        "errors": validation.errors,
                    },
                )
            )
            await self.bus.publish(
                Event(
                    topic=Topics.UI_UPDATE,
                    source=self.name,
                    payload={
                        "screen": "idle",
                        "message": "Проверьте выбор камеры и микрофона перед стартом.",
                        "device_errors": validation.errors,
                    },
                )
            )
            return

        self._last_selection = DeviceSelection(
            camera_id=validation.selected_devices.camera.device_id
            if validation.selected_devices.camera
            else "",
            microphone_id=validation.selected_devices.microphone.device_id
            if validation.selected_devices.microphone
            else "",
        )
        self._save_selection(self._last_selection)
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "selected_devices": self._last_selection.to_dict(),
                    "device_errors": [],
                    "screen": "idle",
                    "message": "Устройства подтверждены. Сеанс готов к запуску.",
                    "assistant_source": "устройства",
                },
            )
        )
        await self.bus.publish(
            Event(
                topic=Topics.DEVICE_SELECTION_RESOLVED,
                source=self.name,
                payload=resolved_payload,
            )
        )

    @staticmethod
    def _build_statuses(catalog: DeviceCatalog) -> dict[str, dict[str, Any]]:
        camera_available = any(item.available for item in catalog.cameras)
        microphone_available = any(item.available for item in catalog.microphones)
        return {
            "camera": {
                "available": camera_available,
                "detail": "Камера выбрана DeviceManager" if camera_available else "Камера не найдена",
            },
            "microphone": {
                "available": microphone_available,
                "detail": "Микрофон выбран DeviceManager" if microphone_available else "Микрофон не найден",
            },
        }

    def _load_selection(self) -> DeviceSelection:
        try:
            raw = json.loads(self.selection_path.read_text(encoding="utf-8"))
        except Exception:
            return DeviceSelection(camera_id=str(self.settings.camera_index), microphone_id="")
        return DeviceSelection.from_payload(raw if isinstance(raw, dict) else {})

    def _save_selection(self, selection: DeviceSelection) -> None:
        try:
            self.selection_path.parent.mkdir(parents=True, exist_ok=True)
            self.selection_path.write_text(
                json.dumps(selection.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return
