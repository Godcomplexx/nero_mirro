"""Сохранение опроса самочувствия: когда он заполнен, записывается явно.

«До» и «после» относятся к занятию курса и сравниваются между собой. Опрос
на скрининге отмечается отдельно — иначе он попал бы в это сравнение как
«до» без занятия.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from neuro_mirror.core.user_profiles import UserProfileStore
from neuro_mirror.screening.san_survey import QUESTION_IDS
from neuro_mirror.web.app import create_app


@pytest.fixture
def client(tmp_path):
    users = UserProfileStore(tmp_path)
    user = users.create_user("Test", consent=True, personal_data_consent=True,
                             audio_data_consent=True, video_data_consent=True)
    users.select_user(user["id"])
    published = []

    async def publish(event):
        published.append(event)

    app = create_app()
    app.state.context = SimpleNamespace(user_store=users, runtime=SimpleNamespace(bus=SimpleNamespace(publish=publish)))
    test_client = TestClient(app)
    test_client.published = published
    yield test_client
    test_client.close()


ANSWERS = {key: 3 for key in QUESTION_IDS}


@pytest.mark.parametrize("moment", ["before", "after", "screening"])
def test_the_moment_is_stored_with_the_answers(client, moment):
    response = client.post("/api/questionnaires/san", json={"moment": moment, "answers": ANSWERS})
    assert response.status_code == 200
    assert client.published[-1].payload["moment"] == moment


def test_an_unknown_moment_is_refused(client):
    response = client.post("/api/questionnaires/san", json={"moment": "someday", "answers": ANSWERS})
    assert response.status_code == 400
    assert not client.published
