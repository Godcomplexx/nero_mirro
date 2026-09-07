"""Tracks per-user progress flags (какие этапы пользователь уже прошёл).

Flags live inside the user profile JSON (``runtime/users.json`` →
``progress``) and drive the assistant's next-step suggestions:
скрининг не пройден → предложить диагностику; MoCA не пройден →
предложить MoCA; всё пройдено и выбран курс → предлагать тренировки.

Updates:
  - STORAGE_WRITE — a new report was stored for the active user
  - SYSTEM_BOOTSTRAP — backfill flags from the stored history
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from neuro_mirror.core.user_profiles import UserProfileStore
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics

logger = logging.getLogger(__name__)


def _flags_for_report(report: dict[str, Any]) -> dict[str, Any]:
    report_type = str(report.get("report_type") or "")
    stored_at = report.get("stored_at")
    domains = report.get("domains") or {}
    flags: dict[str, Any] = {}

    if report_type == "screening":
        flags["screening_done"] = True
        flags["last_screening_at"] = stored_at
        # Базовый скрининг включает тест на тревожность
        if domains.get("hads_anxiety_score") is not None:
            flags["hads_done"] = True
            flags["last_hads_at"] = stored_at
        # Старые записи MoCA сохранялись с типом "screening"
        if domains.get("moca_score") is not None:
            flags["moca_done"] = True
            flags["last_moca_at"] = stored_at
    elif report_type == "hads":
        flags["hads_done"] = True
        flags["last_hads_at"] = stored_at
    elif report_type == "moca":
        flags["moca_done"] = True
        flags["last_moca_at"] = stored_at

    return flags


class UserProgressPlugin(ProcessorPlugin):
    plugin_name = "user_progress"

    def __init__(self, bus, *, user_store: UserProfileStore) -> None:
        super().__init__(bus)
        self.user_store = user_store

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.STORAGE_WRITE, Topics.SYSTEM_BOOTSTRAP)

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.SYSTEM_BOOTSTRAP:
            await self._backfill_from_history()
            return

        if event.topic == Topics.STORAGE_WRITE:
            user_id = str(event.payload.get("user_id") or self.user_store.active_user_id or "")
            if not user_id:
                return
            report = dict(event.payload)
            report.setdefault("stored_at", datetime.now(timezone.utc).isoformat())
            flags = _flags_for_report(report)
            if flags:
                self.user_store.update_progress(user_id, **flags)
                logger.info("user_progress: %s ← %s", user_id, flags)

    async def _backfill_from_history(self) -> None:
        """Derive flags from previously stored reports (e.g. after updates)."""
        try:
            reply = await self.bus.request(
                Event(
                    topic=Topics.REQ_STORAGE_QUERY,
                    source=self.name,
                    payload={},
                ),
                timeout=10.0,
            )
        except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
            logger.warning("user_progress: backfill failed: %s", exc)
            return

        merged: dict[str, dict[str, Any]] = {}
        for item in reply.get("items") or []:
            user_id = str(item.get("user_id") or "")
            if not user_id:
                continue
            flags = _flags_for_report(item)
            if flags:
                merged.setdefault(user_id, {}).update(flags)

        for user_id, flags in merged.items():
            if self.user_store.get_user(user_id) is not None:
                self.user_store.update_progress(user_id, **flags)
        if merged:
            logger.info("user_progress: backfilled %d users", len(merged))
