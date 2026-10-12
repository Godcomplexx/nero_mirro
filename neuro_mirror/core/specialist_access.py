"""Доступ специалиста к расширенному отчёту.

ТЗ, модуль отчётности и аналитики: «Разграничение видимости метрик для
пользователя и специалиста (в т.ч. правило не показывать интерпретацию HADS
пользователю)». Пользователь видит краткий отчёт, специалист — расширенный.

Программа локальная и однопользовательская, поэтому роль специалиста — это
режим, в который входят по PIN-коду. PIN задаётся при первом входе (это
делает специалист при установке) и хранится только как солёный хеш.

Режим держится, пока специалист не выйдет, и закрывается сам после
``IDLE_TIMEOUT`` без обращений: отойдя от компьютера, специалист не оставит
расширенный отчёт открытым для пользователя. После ``MAX_FAILED_ATTEMPTS``
неверных PIN подряд вход блокируется на ``LOCKOUT``.

Забытый PIN сбрасывается удалением файла ``runtime/specialist.json``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path("runtime/specialist.json")
PIN_PATTERN = re.compile(r"^\d{4,8}$")
PIN_RULE = "PIN — от 4 до 8 цифр."
IDLE_TIMEOUT = timedelta(minutes=15)
MAX_FAILED_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=5)
_ITERATIONS = 200_000


class SpecialistAccessError(ValueError):
    """Отказ с понятной человеку причиной."""


def _hash(pin: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, _ITERATIONS).hex()


class SpecialistAccess:
    def __init__(
        self,
        path: str | Path | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.path = Path(path) if path is not None else DEFAULT_PATH
        self._clock = clock
        self._active_until: datetime | None = None
        self._failed = 0
        self._locked_until: datetime | None = None

    # ---- PIN ----

    @property
    def configured(self) -> bool:
        return self._stored() is not None

    def set_pin(self, pin: str) -> None:
        """Задать PIN при первом входе; сразу открывает режим специалиста."""
        if self.configured:
            raise SpecialistAccessError("PIN уже задан. Войдите с ним.")
        self._write(pin)
        self._open()

    def change_pin(self, pin: str) -> None:
        """Сменить PIN — только из открытого режима специалиста."""
        if not self.is_active():
            raise SpecialistAccessError("Сначала войдите в режим специалиста.")
        self._write(pin)

    # ---- Режим ----

    def login(self, pin: str) -> None:
        now = self._clock()
        if self._locked_until is not None and now < self._locked_until:
            minutes = max(1, int((self._locked_until - now).total_seconds() // 60) + 1)
            raise SpecialistAccessError(
                f"Слишком много неверных попыток. Повторите через {minutes} мин."
            )
        stored = self._stored()
        if stored is None:
            raise SpecialistAccessError("PIN ещё не задан.")
        salt, expected = stored
        if not hmac.compare_digest(_hash(str(pin), salt), expected):
            self._failed += 1
            if self._failed >= MAX_FAILED_ATTEMPTS:
                self._failed = 0
                self._locked_until = now + LOCKOUT
            raise SpecialistAccessError("Неверный PIN.")
        self._failed = 0
        self._locked_until = None
        self._open()

    def logout(self) -> None:
        self._active_until = None

    def is_active(self) -> bool:
        """Открыт ли режим; каждое обращение продлевает его."""
        if self._active_until is None:
            return False
        now = self._clock()
        if now >= self._active_until:
            self._active_until = None
            return False
        self._active_until = now + IDLE_TIMEOUT
        return True

    def status(self) -> dict[str, bool]:
        return {"configured": self.configured, "active": self.is_active()}

    # ---- Служебное ----

    def _open(self) -> None:
        self._active_until = self._clock() + IDLE_TIMEOUT

    def _write(self, pin: str) -> None:
        pin = str(pin or "").strip()
        if not PIN_PATTERN.match(pin):
            raise SpecialistAccessError(PIN_RULE)
        salt = secrets.token_bytes(16)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps({"salt": salt.hex(), "hash": _hash(pin, salt), "iterations": _ITERATIONS}),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def _stored(self) -> tuple[bytes, str] | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return bytes.fromhex(str(data["salt"])), str(data["hash"])
        except (OSError, ValueError, KeyError, TypeError):
            logger.warning("файл PIN специалиста повреждён: %s", self.path)
            return None
