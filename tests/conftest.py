"""Общие настройки для проверок.

Ожидание нажатия «Приступить» перед заданием MoCA по умолчанию равно
двадцати пяти секундам. В проверках кнопку нажимать некому, и это ожидание
растягивало прогон с полуминуты до четырёх минут, ничего не проверяя.
Здесь оно обнуляется: задания начинаются сразу, как было до появления
кнопки. Проверки самого ожидания задают значение явно.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _moca_starts_without_waiting(monkeypatch):
    from neuro_mirror.plugins.moca_test import plugin as moca_plugin

    monkeypatch.setenv("NEURO_MIRROR_MOCA_START_GRACE", "0")
    monkeypatch.setattr(moca_plugin, "start_grace_seconds", lambda _settings: 0.0)
