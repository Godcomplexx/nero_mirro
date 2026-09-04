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

CONSENT_TEXT = (
    "Я даю согласие на обработку персональных данных, "
    "в том числе биометрических данных."
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
        avatar_preset: str = "",
        photo_base64: str = "",
    ) -> dict[str, Any]:
        clean_name = " ".join(name.split())[:60]
        if not clean_name:
            raise ValueError("Имя не может быть пустым.")
        if not consent:
            raise ValueError("Без согласия на обработку данных создать профиль нельзя.")

        user_id = self._next_id()
        avatar: dict[str, str]
        if photo_base64:
            self._save_photo(user_id, photo_base64)
            avatar = {"type": "photo", "value": ""}
        else:
            preset = avatar_preset if avatar_preset in PRESET_AVATARS else PRESET_AVATARS[0]
            avatar = {"type": "preset", "value": preset}

        user = {
            "id": user_id,
            "name": clean_name,
            "avatar": avatar,
            "consent": {
                "given": True,
                "text": CONSENT_TEXT,
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
            return users
        return []

    def _save_users(self) -> None:
        self.users_path.parent.mkdir(parents=True, exist_ok=True)
        self.users_path.write_text(
            json.dumps(self._users, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
