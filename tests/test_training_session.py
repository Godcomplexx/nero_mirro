"""Готовое занятие: от когнитивного профиля до списка конкретных игр."""
from __future__ import annotations

from neuro_mirror.plugins.games.registry import implemented_game_codes
from neuro_mirror.screening.moca_scoring import COGNITIVE_DOMAINS, MOCA_MODULES
from neuro_mirror.screening.training_session import (
    DOMAIN_CODES,
    build_training_session,
    order_domains,
)

MEMORY, ATTENTION, SPEECH, ABSTRACTION = COGNITIVE_DOMAINS


def profile(memory: int, attention: int, speech: int, abstraction: int) -> list[dict]:
    pairs = ((MEMORY, memory, 5), (ATTENTION, attention, 5),
             (SPEECH, speech, 3), (ABSTRACTION, abstraction, 2))
    return [
        {"domain": name, "score": score, "max_score": maximum,
         "deficit": round((maximum - score) / maximum, 3)}
        for name, score, maximum in pairs
    ]


def build(*args, **kwargs):
    return build_training_session(
        *args, available_codes=implemented_game_codes(), **kwargs
    )


# ── Соответствие доменов ──────────────────────────────────────────────────────

def test_domain_codes_cover_every_domain_of_the_profile():
    """Профиль называет домены по-русски, игры — кодами; разойтись нельзя."""
    assert set(DOMAIN_CODES) == set(COGNITIVE_DOMAINS)
    assert set(DOMAIN_CODES.values()) == {str(m["id"]) for m in MOCA_MODULES}


# ── Порядок ───────────────────────────────────────────────────────────────────

def test_domains_are_interleaved_not_grouped():
    """Четыре игры одного домена подряд утомляют и сбивают чередование."""
    order = order_domains({MEMORY: 2, ATTENTION: 4, SPEECH: 3, ABSTRACTION: 1})
    assert len(order) == 10
    assert all(order[i] != order[i + 1] for i in range(len(order) - 1))


def test_order_keeps_the_planned_counts():
    plan = {MEMORY: 5, ATTENTION: 2, SPEECH: 2, ABSTRACTION: 1}
    order = order_domains(plan)
    for domain, count in plan.items():
        assert order.count(domain) == count


# ── Состав занятия ────────────────────────────────────────────────────────────

def test_session_has_one_game_per_planned_task():
    session = build(profile(3, 1, 0, 1))
    assert session["session_size"] == sum(session["plan"].values())
    assert session["skipped"] == []


def test_games_are_not_repeated_within_a_session():
    session = build(profile(0, 0, 0, 0))
    codes = [game["game_code"] for game in session["games"]]
    assert len(codes) == len(set(codes))


def test_every_game_matches_the_domain_it_was_picked_for():
    session = build(profile(2, 2, 1, 1))
    for game in session["games"]:
        assert game["domain_code"] == DOMAIN_CODES[game["domain"]]


def test_each_game_carries_what_the_interface_needs_to_run_it():
    session = build(profile(3, 3, 2, 1))
    for game in session["games"]:
        assert game["game_code"] and game["title"] and game["stimulus_set"]
        assert game["position"] >= 1


def test_empty_profile_yields_no_session_instead_of_failing():
    """Без пройденного теста занятие не собирается, но и не роняет запрос."""
    session = build([])
    assert session["games"] == []
    assert session["session_size"] == 0


def test_perfect_result_still_gives_a_full_session():
    """Поддерживающий режим: все домены сохранены, занятие всё равно есть."""
    session = build(profile(5, 5, 3, 2))
    assert session["session_size"] == 10
    assert {game["domain"] for game in session["games"]} == set(COGNITIVE_DOMAINS)


# ── Ручка ─────────────────────────────────────────────────────────────────────

def _client_with(tmp_path, stored_items):
    """Приложение с подставленным хранилищем и выбранным пользователем."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi.testclient import TestClient

    from neuro_mirror.core.user_profiles import UserProfileStore
    from neuro_mirror.web.app import create_app

    users = UserProfileStore(tmp_path)
    user = users.create_user("Test", consent=True, personal_data_consent=True,
                             audio_data_consent=True, video_data_consent=True)
    users.select_user(user["id"])

    bus = SimpleNamespace(request=AsyncMock(return_value={"items": stored_items}))
    history = SimpleNamespace(
        for_user=lambda _user_id: (),
        passes_for_game=lambda _user_id, _code: [],
    )
    app = create_app()
    app.state.context = SimpleNamespace(
        user_store=users,
        runtime=SimpleNamespace(bus=bus, game_history_store=history),
    )
    return TestClient(app)


def _stored_report(domains, *, session_id="s-1", stored_at="2026-09-29T10:00:00"):
    return {
        "session_id": session_id,
        "stored_at": stored_at,
        "domains": {"moca_domains": domains},
    }


def test_endpoint_returns_a_ready_session(tmp_path):
    client = _client_with(tmp_path, [_stored_report(profile(3, 1, 0, 1))])
    response = client.get("/api/training/session")
    assert response.status_code == 200
    body = response.json()
    assert body["session_size"] == sum(body["plan"].values())
    assert [game["position"] for game in body["games"]] == list(
        range(1, body["session_size"] + 1)
    )
    assert body["source_session_id"] == "s-1"
    client.close()


def test_endpoint_uses_the_most_recent_result(tmp_path):
    old = _stored_report(profile(5, 5, 3, 2), session_id="old", stored_at="2026-09-01T10:00:00")
    new = _stored_report(profile(0, 0, 0, 0), session_id="new", stored_at="2026-09-29T10:00:00")
    client = _client_with(tmp_path, [old, new])
    body = client.get("/api/training/session").json()
    assert body["source_session_id"] == "new"
    client.close()


def test_endpoint_explains_that_the_test_comes_first(tmp_path):
    """Без результата MoCA занятие не подобрать — это объяснимая причина, не сбой."""
    client = _client_with(tmp_path, [])
    response = client.get("/api/training/session")
    assert response.status_code == 409
    assert "когнитивный тест" in response.json()["detail"]
    client.close()
