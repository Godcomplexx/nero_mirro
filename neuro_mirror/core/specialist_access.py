"""Доступ специалиста к расширенному отчёту.

ТЗ, модуль отчётности и аналитики: «Разграничение видимости метрик для
пользователя и специалиста (в т.ч. правило не показывать интерпретацию HADS
пользователю)». Пользователь видит краткий отчёт, специалист — расширенный.

Программа локальная и однопользовательская, поэтому роль специалиста — это
режим, в который входят по PIN-коду. PIN задаёт администратор при установке в
переменной окружения ``NEURO_MIRROR_SPECIALIST_PIN`` (4–8 цифр). Из
интерфейса PIN не задаётся и не меняется: иначе его мог бы назначить тот,
кто первым откроет вкладку, — в том числе сам пользователь. Пока переменная
не задана, режим специалиста недоступен.

Режим держится, пока специалист не выйдет, и закрывается сам после
``IDLE_TIMEOUT`` без обращений: отойдя от компьютера, специалист не оставит
расширенный отчёт открытым для пользователя. После ``MAX_FAILED_ATTEMPTS``
неверных PIN подряд вход блокируется на ``LOCKOUT``.
"""
from __future__ import annotations

import hmac
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Callable

logger = logging.getLogger(__name__)

PIN_ENV = "NEURO_MIRROR_SPECIALIST_PIN"
PIN_PATTERN = re.compile(r"^\d{4,8}$")
IDLE_TIMEOUT = timedelta(minutes=15)
MAX_FAILED_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=5)


class SpecialistAccessError(ValueError):
    """Отказ с понятной человеку причиной."""


class SpecialistAccess:
    def __init__(
        self,
        pin: str | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        raw = (pin if pin is not None else os.getenv(PIN_ENV, "")).strip()
        if raw and not PIN_PATTERN.match(raw):
            # Сам PIN в журнал не пишется — только то, что он не годится.
            logger.warning("%s задан, но это не 4–8 цифр: режим специалиста недоступен", PIN_ENV)
            raw = ""
        self._pin = raw
        self._clock = clock
        self._active_until: datetime | None = None
        self._failed = 0
        self._locked_until: datetime | None = None

    @property
    def configured(self) -> bool:
        return bool(self._pin)

    def login(self, pin: str) -> None:
        if not self.configured:
            raise SpecialistAccessError(
                "PIN специалиста не задан. Его задаёт администратор при установке."
            )
        now = self._clock()
        if self._locked_until is not None and now < self._locked_until:
            minutes = max(1, int((self._locked_until - now).total_seconds() // 60) + 1)
            raise SpecialistAccessError(
                f"Слишком много неверных попыток. Повторите через {minutes} мин."
            )
        if not hmac.compare_digest(str(pin or "").strip().encode(), self._pin.encode()):
            self._failed += 1
            if self._failed >= MAX_FAILED_ATTEMPTS:
                self._failed = 0
                self._locked_until = now + LOCKOUT
            raise SpecialistAccessError("Неверный PIN.")
        self._failed = 0
        self._locked_until = None
        self._active_until = now + IDLE_TIMEOUT

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
