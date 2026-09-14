"""Persistent user profiles (личный кабинет).

Stores users in ``runtime/users.json`` and photo avatars in ``runtime/avatars/``.
Each user gets an auto-assigned sequential ID. Consent is recorded with the
exact text shown to the user and a timestamp.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONSENT_TEXTS: dict[str, str] = {
    "personal": "Я даю согласие на обработку персональных данных.",
    "audio": "Я даю согласие на запись и временную обработку аудиоданных.",
    "video": "Я даю согласие на запись и временную обработку видеоданных.",
    "dataset": (
        "Я даю согласие на сохранение аудио- и видеозаписей моего прохождения "
        "тестов для формирования исследовательского набора данных."
    ),
}
# Consents that permit *retention* rather than temporary processing. They are
# always opt-in: never granted by default and never inherited from the older
# combined consent, which promised temporary processing only.
RETENTION_CONSENTS = frozenset({"dataset"})
# Backward-compatible combined text used by older clients. Retention consents
# stay out of it — they were not part of what those clients displayed.
CONSENT_TEXT = " ".join(
    text for key, text in CONSENT_TEXTS.items() if key not in RETENTION_CONSENTS
)

# Preset avatars shipped with the web UI (web/static/assets/avatars/<id>.svg)
PRESET_AVATARS = ("a01", "a02", "a03", "a04", "a05", "a06")

# Пройденные этапы пользователя — по ним ассистент предлагает следующий шаг
DEFAULT_PROGRESS: dict[str, Any] = {
    "screening_done": False,       # базовая диагностика (видео + тревожность)
    "moca_done": False,            # тест MoCA пройден
    "hads_done": False,            # тест на тревожность пройден
    "training_course": "",         # выбранный курс тренировок ("" — не выбран)
    "last_screening_at": None,
    "last_moca_at": None,
    "last_hads_at": None,
}

_DATA_URL_RE = re.compile(r"^data:image/(png|jpe?g|webp);base64,", re.IGNORECASE)


class UserProfileStore:
    def __init__(self, runtime_dir: str | Path = "runtime") -> None:
        runtime_path = Path(runtime_dir)
        self.users_path = runtime_path / "users.json"
        self.avatars_dir = runtime_path / "avatars"
        self._users: list[dict[str, Any]] = self._load_users()
        self.active_user_id: str | None = None

    # ---- Queries ----

    def list_users(self) -> list[dict[str, Any]]:
        return [dict(user) for user in self._users]

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        for user in self._users:
            if user.get("id") == user_id:
                return dict(user)
        return None

    def get_active_user(self) -> dict[str, Any] | None:
        if not self.active_user_id:
            return None
        return self.get_user(self.active_user_id)

    def has_consent(self, user_id: str, consent_type: str) -> bool:
        user = self.get_user(user_id)
        if user is None:
            return False
        consents = user.get("consents") or {}
        entry = consents.get(consent_type) if isinstance(consents, dict) else None
        if isinstance(entry, dict):
            return bool(entry.get("given"))
        # Legacy profiles used one combined consent. They are migrated on load,
        # but keep this fallback for callers holding an older in-memory object.
        legacy = user.get("consent") or {}
        return bool(isinstance(legacy, dict) and legacy.get("given"))

    def active_has_consent(self, consent_type: str) -> bool:
        if not self.active_user_id:
            return False
        return self.has_consent(self.active_user_id, consent_type)

    def avatar_photo_path(self, user_id: str) -> Path | None:
        user = self.get_user(user_id)
        if not user or user.get("avatar", {}).get("type") != "photo":
            return None
        path = self.avatars_dir / f"{user_id}.png"
        return path if path.exists() else None

    # ---- Mutations ----

    def create_user(
        self,
        name: str,
        *,
        consent: bool,
        personal_data_consent: bool | None = None,
        audio_data_consent: bool | None = None,
        video_data_consent: bool | None = None,
        dataset_consent: bool = False,
        avatar_preset: str = "",
        photo_base64: str = "",
    ) -> dict[str, Any]:
        clean_name = " ".join(name.split())[:60]
        if not clean_name:
            raise ValueError("Имя не может быть пустым.")
        personal_allowed = consent if personal_data_consent is None else personal_data_consent
        audio_allowed = consent if audio_data_consent is None else audio_data_consent
        video_allowed = consent if video_data_consent is None else video_data_consent
        # Retention is opt-in only: the combined ``consent`` flag never grants it.
        dataset_allowed = bool(dataset_consent)
        if not personal_allowed:
            raise ValueError("Без согласия на обработку данных создать профиль нельзя.")
        if photo_base64 and not video_allowed:
            raise ValueError("Для фото-аватара требуется согласие на обработку видеоданных.")
        if dataset_allowed and not (audio_allowed and video_allowed):
            raise ValueError(
                "Для сохранения записей в набор данных нужны согласия "
                "на обработку аудио- и видеоданных."
            )

        user_id = self._next_id()
        avatar: dict[str, str]
        if photo_base64:
            self._save_photo(user_id, photo_base64)
            avatar = {"type": "photo", "value": ""}
        else:
            preset = avatar_preset if avatar_preset in PRESET_AVATARS else PRESET_AVATARS[0]
            avatar = {"type": "preset", "value": preset}

        consent_timestamp = datetime.now(timezone.utc).isoformat()
        user = {
            "id": user_id,
            "name": clean_name,
            "avatar": avatar,
            "consent": {
                "given": True,
                "text": CONSENT_TEXT,
                "timestamp": consent_timestamp,
            },
            "consents": {
                "personal": {
                    "given": bool(personal_allowed),
                    "text": CONSENT_TEXTS["personal"],
                    "timestamp": consent_timestamp if personal_allowed else None,
                },
                "audio": {
                    "given": bool(audio_allowed),
                    "text": CONSENT_TEXTS["audio"],
                    "timestamp": consent_timestamp if audio_allowed else None,
                },
                "video": {
                    "given": bool(video_allowed),
                    "text": CONSENT_TEXTS["video"],
                    "timestamp": consent_timestamp if video_allowed else None,
                },
                "dataset": {
                    "given": dataset_allowed,
                    "text": CONSENT_TEXTS["dataset"],
                    "timestamp": consent_timestamp if dataset_allowed else None,
                },
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "progress": dict(DEFAULT_PROGRESS),
        }
        self._users.append(user)
        self._save_users()
        return dict(user)

    def select_user(self, user_id: str) -> dict[str, Any]:
        user = self.get_user(user_id)
        if user is None:
            raise KeyError(user_id)
        self.active_user_id = user_id
        return user

    def set_consent(self, user_id: str, consent_type: str, given: bool) -> dict[str, Any]:
        """Grant or withdraw one consent for an existing profile.

        Retention consents can be toggled here so an existing user can opt into
        the dataset without recreating the profile; the exact text and the time
        of the decision are stored alongside the flag.
        """
        if consent_type not in CONSENT_TEXTS:
            raise KeyError(consent_type)
        user = next((item for item in self._users if item.get("id") == user_id), None)
        if user is None:
            raise KeyError(user_id)
        if consent_type == "personal" and not given:
            raise ValueError("Согласие на обработку персональных данных обязательно.")

        consents = user.setdefault("consents", {})
        if given and consent_type in RETENTION_CONSENTS:
            missing = [
                required for required in ("audio", "video")
                if not bool((consents.get(required) or {}).get("given"))
            ]
            if missing:
                raise ValueError(
                    "Для сохранения записей в набор данных нужны согласия "
                    "на обработку аудио- и видеоданных."
                )

        consents[consent_type] = {
            "given": bool(given),
            "text": CONSENT_TEXTS[consent_type],
            "timestamp": datetime.now(timezone.utc).isoformat() if given else None,
        }
        if not given and consent_type in {"audio", "video"}:
            # Retention cannot outlive permission to record in the first place.
            for retention_type in RETENTION_CONSENTS:
                entry = consents.get(retention_type)
                if isinstance(entry, dict) and entry.get("given"):
                    consents[retention_type] = {
                        "given": False,
                        "text": CONSENT_TEXTS[retention_type],
                        "timestamp": None,
                    }
        self._save_users()
        return dict(user)

    def update_progress(self, user_id: str, **flags: Any) -> dict[str, Any] | None:
        """Merge ``flags`` into the user's progress and persist."""
        for user in self._users:
            if user.get("id") != user_id:
                continue
            progress = user.setdefault("progress", dict(DEFAULT_PROGRESS))
            changed = False
            for key, value in flags.items():
                if progress.get(key) != value:
                    progress[key] = value
                    changed = True
            if changed:
                self._save_users()
            return dict(progress)
        return None

    # ---- Internals ----

    def _next_id(self) -> str:
        highest = 0
        for user in self._users:
            match = re.fullmatch(r"u(\d+)", str(user.get("id", "")))
            if match:
                highest = max(highest, int(match.group(1)))
        return f"u{highest + 1:04d}"

    def _save_photo(self, user_id: str, photo_base64: str) -> None:
        stripped = _DATA_URL_RE.sub("", photo_base64.strip())
        try:
            raw = base64.b64decode(stripped, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Не удалось прочитать фото аватара.") from exc
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError("Фото аватара слишком большое (максимум 8 МБ).")
        self.avatars_dir.mkdir(parents=True, exist_ok=True)
        (self.avatars_dir / f"{user_id}.png").write_bytes(raw)

    def _load_users(self) -> list[dict[str, Any]]:
        if not self.users_path.exists():
            return []
        try:
            # utf-8-sig: tolerate a BOM left by external editors
            parsed = json.loads(self.users_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(parsed, list):
            users = [item for item in parsed if isinstance(item, dict)]
            for user in users:
                # Backfill progress for profiles created before this field existed
                progress = user.setdefault("progress", {})
                for key, value in DEFAULT_PROGRESS.items():
                    progress.setdefault(key, value)
                self._backfill_consents(user)
            return users
        return []

    @staticmethod
    def _backfill_consents(user: dict[str, Any]) -> None:
        consents = user.setdefault("consents", {})
        legacy = user.get("consent") or {}
        legacy_given = bool(isinstance(legacy, dict) and legacy.get("given"))
        legacy_timestamp = legacy.get("timestamp") if isinstance(legacy, dict) else None
        for consent_type, text in CONSENT_TEXTS.items():
            entry = consents.setdefault(consent_type, {})
            if not isinstance(entry, dict):
                entry = {}
                consents[consent_type] = entry
            # A retention consent must be given explicitly: profiles created
            # before it existed never agreed to their recordings being kept.
            inherited = False if consent_type in RETENTION_CONSENTS else legacy_given
            entry.setdefault("given", inherited)
            entry.setdefault("text", text)
            entry.setdefault("timestamp", legacy_timestamp if entry.get("given") else None)

    def _save_users(self) -> None:
        self.users_path.parent.mkdir(parents=True, exist_ok=True)
        self.users_path.write_text(
            json.dumps(self._users, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
