"""Канал между интерфейсом и ядром поверх стандартных потоков.

Проверяется на отдельном лёгком приложении: протокол не должен зависеть от
того, какие именно обработчики зарегистрированы, а поднимать рабочие процессы
и загружать модели ради проверки формата сообщений не нужно.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json

import pytest
from fastapi import FastAPI, WebSocket

from neuro_mirror.app.pipe_host import (
    EventSubscriber,
    PipeHost,
    PipeSocket,
    ProtocolWriter,
)


class Collector(ProtocolWriter):
    """Запоминает отправленные сообщения вместо записи в стандартный вывод."""

    def __init__(self) -> None:
        super().__init__(stream=io.StringIO())
        self.messages: list[dict] = []

    async def send(self, message: dict) -> None:
        self.messages.append(message)

    def of_type(self, kind: str) -> list[dict]:
        return [m for m in self.messages if m.get("type") == kind]


def demo_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/ping")
    async def ping() -> dict:
        return {"pong": True}

    @app.post("/api/echo")
    async def echo(payload: dict) -> dict:
        return {"received": payload}

    @app.get("/api/missing-on-purpose")
    async def missing() -> dict:
        raise ValueError("сбой обработчика")

    @app.websocket("/ws/frames")
    async def frames(websocket: WebSocket) -> None:
        await websocket.accept()
        first = await websocket.receive_bytes()
        await websocket.send_json({"received_bytes": len(first)})
        await websocket.close()

    return app


# ── Запрос и ответ ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_request_reaches_the_handler_and_keeps_its_identifier():
    writer = Collector()
    async with PipeHost(demo_app(), writer) as host:
        await host.dispatch({"type": "request", "id": "abc",
                             "method": "GET", "path": "/api/ping"})
    answer = writer.of_type("response")[0]
    assert answer["id"] == "abc"
    assert answer["status"] == 200
    assert answer["body"] == {"pong": True}


@pytest.mark.asyncio
async def test_request_body_is_passed_through_unchanged():
    writer = Collector()
    async with PipeHost(demo_app(), writer) as host:
        await host.dispatch({"type": "request", "id": "1", "method": "POST",
                             "path": "/api/echo", "body": {"домен": "Память", "n": 3}})
    assert writer.of_type("response")[0]["body"] == {"received": {"домен": "Память", "n": 3}}


@pytest.mark.asyncio
async def test_handler_failure_answers_instead_of_breaking_the_channel():
    """Сбой одного обращения не должен обрывать связь с интерфейсом."""
    writer = Collector()
    async with PipeHost(demo_app(), writer) as host:
        await host.dispatch({"type": "request", "id": "bad", "method": "GET",
                             "path": "/api/missing-on-purpose"})
        await host.dispatch({"type": "request", "id": "good", "method": "GET",
                             "path": "/api/ping"})
    answers = {m["id"]: m for m in writer.of_type("response")}
    assert answers["bad"]["status"] == 500
    assert answers["good"]["status"] == 200


@pytest.mark.asyncio
async def test_unknown_message_kind_is_reported():
    writer = Collector()
    async with PipeHost(demo_app(), writer) as host:
        await host.dispatch({"type": "непонятно", "id": "x"})
    assert writer.of_type("response")[0]["status"] == 400


# ── События ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_state_updates_are_delivered_as_events():
    """Обновления состояния идут без запроса — как раньше по сокету."""
    writer = Collector()
    subscriber = EventSubscriber(writer)
    await subscriber.accept()
    await subscriber.send_json({"type": "state", "payload": {"screen": "moca"}})
    event = writer.of_type("event")[0]
    assert event["event"] == "state"
    assert event["payload"] == {"screen": "moca"}


# ── Поток кадров ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_frame_stream_reaches_the_handler():
    writer = Collector()
    async with PipeHost(demo_app(), writer) as host:
        await host.dispatch({"type": "stream", "channel": "c1", "action": "open",
                             "path": "/ws/frames", "query": "mode=screening"})
        await asyncio.sleep(0)
        await host.dispatch({"type": "stream", "channel": "c1", "action": "data",
                             "data": base64.b64encode(b"0123456789").decode()})
        for _ in range(20):
            await asyncio.sleep(0.01)
            if any(m.get("action") == "message" for m in writer.of_type("stream")):
                break
    replies = [m for m in writer.of_type("stream") if m.get("action") == "message"]
    assert replies and replies[0]["payload"] == {"received_bytes": 10}


@pytest.mark.asyncio
async def test_unknown_stream_is_refused_with_a_reason():
    writer = Collector()
    async with PipeHost(demo_app(), writer) as host:
        await host.dispatch({"type": "stream", "channel": "c9", "action": "open",
                             "path": "/ws/нет-такого"})
    closed = [m for m in writer.of_type("stream") if m.get("action") == "closed"]
    assert closed and closed[0]["code"] == 4404


@pytest.mark.asyncio
async def test_stream_query_parameters_reach_the_handler():
    """Режим и длительность передаются так же, как передавались в адресе."""
    writer = Collector()
    socket = PipeSocket("c", writer, "mode=monitor&duration=30")
    assert socket.scope["query_string"] == b"mode=monitor&duration=30"


# ── Формат ────────────────────────────────────────────────────────────────────

def test_every_message_is_one_json_line():
    """Интерфейс читает поток построчно: перевод строки внутри сообщения недопустим."""
    buffer = io.StringIO()
    writer = ProtocolWriter(stream=buffer)
    asyncio.run(writer.send({"type": "event", "payload": {"text": "две\nстроки"}}))
    assert buffer.getvalue().count("\n") == 1
    assert json.loads(buffer.getvalue())["payload"]["text"] == "две\nстроки"


# ── Чтение ввода ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_input_is_read_line_by_line(monkeypatch):
    """Штатный для asyncio способ читать стандартный ввод на Windows не работает.

    Цикл событий Proactor не принимает этот дескриптор: подключение внешне
    проходит, но первое чтение падает с ошибкой «дескриптор недействителен»,
    и ядро молча перестаёт получать запросы, продолжая присылать события.
    Поэтому чтение вынесено в отдельный поток — проверяем, что оно работает.
    """
    from neuro_mirror.app.pipe_host import _read_lines

    monkeypatch.setattr("sys.stdin", io.StringIO('{"a": 1}\n\n{"b": 2}\n'))
    lines = [line async for line in _read_lines(asyncio.get_running_loop())]
    assert [json.loads(item) for item in lines] == [{"a": 1}, {"b": 2}]


@pytest.mark.asyncio
async def test_reading_stops_when_the_interface_closes_the_channel():
    """Закрытый ввод завершает ядро, а не оставляет его висеть."""
    from neuro_mirror.app.pipe_host import _read_lines

    import sys as _sys
    saved, _sys.stdin = _sys.stdin, io.StringIO("")
    try:
        assert [line async for line in _read_lines(asyncio.get_running_loop())] == []
    finally:
        _sys.stdin = saved
