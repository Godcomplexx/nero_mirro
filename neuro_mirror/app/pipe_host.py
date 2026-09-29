"""Канал обмена между интерфейсом и ядром поверх стандартных потоков.

Ядро запускается как дочерняя программа интерфейса и общается с ним через
стандартный ввод и вывод. Сетевой порт не открывается, подключиться извне
нельзя: это внутренний интерфейс между компонентами одной программы.

Формат — по одному сообщению JSON на строку. Три вида сообщений:

* request/response — обращение к обработчику по пути и ответ на него;
* event — сообщение ядра интерфейсу без запроса (состояние экрана, ход теста);
* stream — двусторонний поток для передачи видеокадров.

Маршруты обработчиков остаются прежними: тот же путь и тот же состав данных,
что и раньше, поэтому интерфейсу достаточно заменить способ вызова.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

# Диагностика уходит в поток ошибок: в стандартном выводе только сообщения
# протокола, иначе интерфейс получит мусор вместо JSON.
PROTOCOL_VERSION = 1


class ProtocolWriter:
    """Последовательная запись сообщений в стандартный вывод."""

    def __init__(self, stream=None) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._lock = asyncio.Lock()

    async def send(self, message: dict[str, Any]) -> None:
        line = json.dumps(message, ensure_ascii=False)
        async with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()


class EventSubscriber:
    """Приёмник обновлений состояния вместо соединения с интерфейсом.

    Хранилище состояния рассылает снимки всем подписчикам, вызывая у них
    ``send_json``. Здесь тот же вызов направляется в канал, поэтому само
    хранилище менять не требуется.
    """

    def __init__(self, writer: ProtocolWriter) -> None:
        self._writer = writer

    async def accept(self) -> None:
        return None

    async def send_json(self, payload: dict[str, Any]) -> None:
        # Вид обновления кладётся в отдельное поле: если разложить содержимое
        # в корень сообщения, его ключ "type" затрёт вид самого сообщения.
        await self._writer.send({
            "type": "event",
            "event": payload.get("type", "state"),
            "payload": payload.get("payload"),
        })

    async def close(self, *_args, **_kwargs) -> None:
        return None


class PipeSocket:
    """Двусторонний поток кадров с интерфейсом эквивалентом веб-сокета.

    Обработчик измерения пульса принимает кадры и отвечает результатами. Он
    оставлен без изменений: здесь воспроизведены те методы, которыми он
    пользуется, а данные приходят из канала.
    """

    def __init__(self, channel: str, writer: ProtocolWriter, query_string: str = "") -> None:
        self.channel = channel
        self._writer = writer
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.scope = {"query_string": query_string.encode("utf-8")}
        self.closed = False

    async def accept(self) -> None:
        await self._writer.send({"type": "stream", "channel": self.channel, "action": "accepted"})

    async def close(self, code: int = 1000, reason: str = "") -> None:
        if self.closed:
            return
        self.closed = True
        await self._queue.put(None)
        await self._writer.send({
            "type": "stream", "channel": self.channel, "action": "closed",
            "code": code, "reason": reason,
        })

    async def send_json(self, payload: dict[str, Any]) -> None:
        await self._writer.send({
            "type": "stream", "channel": self.channel, "action": "message", "payload": payload,
        })

    async def receive_bytes(self) -> bytes:
        item = await self._queue.get()
        if item is None:
            raise asyncio.TimeoutError("поток закрыт интерфейсом")
        return item

    async def receive_text(self) -> str:
        return (await self.receive_bytes()).decode("utf-8", "replace")

    def feed(self, data: bytes) -> None:
        self._queue.put_nowait(data)



async def call_handler(app, method: str, path: str, body: Any = None) -> tuple[int, bytes]:
    """Вызвать обработчик ядра напрямую, без посредника и без сети.

    Приложение вызывается как обычная функция: сокет не открывается, адрес не
    разрешается, сетевой стек не задействован. Путь и данные те же, что и
    раньше, поэтому обработчики менять не требуется.
    """
    from urllib.parse import quote, urlencode

    query = b""
    payload = b""
    if body is not None:
        if method == "GET":
            query = urlencode(
                {k: v for k, v in body.items() if not isinstance(v, (dict, list))},
                doseq=True,
            ).encode()
        else:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")

    if "?" in path:
        path, _, inline = path.partition("?")
        query = inline.encode() if not query else query

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": quote(path).encode(),
        "query_string": query,
        "root_path": "",
        "headers": [
            (b"host", b"neuro-mirror.local"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode()),
        ],
        "client": None,
        "server": None,
    }

    sent = {"status": 500, "body": bytearray()}
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            sent["status"] = int(message["status"])
        elif message["type"] == "http.response.body":
            sent["body"].extend(message.get("body") or b"")

    await app(scope, receive, send)
    return sent["status"], bytes(sent["body"])


class PipeHost:
    """Приём сообщений интерфейса и вызов обработчиков ядра."""

    def __init__(self, app, writer: ProtocolWriter) -> None:
        self.app = app
        self.writer = writer
        self._streams: dict[str, PipeSocket] = {}
        self._stream_tasks: dict[str, asyncio.Task] = {}
        self._client = None

    async def __aenter__(self) -> "PipeHost":
        return self

    async def __aexit__(self, *_exc) -> None:
        for task in list(self._stream_tasks.values()):
            task.cancel()

    async def handle_request(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        method = str(message.get("method") or "GET").upper()
        path = str(message.get("path") or "/")
        body = message.get("body")
        try:
            status, raw = await call_handler(self.app, method, path, body)
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else None
            except ValueError:
                payload = {"raw": raw.decode("utf-8", "replace")}
            await self.writer.send({
                "type": "response", "id": request_id,
                "status": status, "body": payload,
            })
        except Exception as exc:  # noqa: BLE001 — сбой обработчика не роняет канал
            logger.exception("pipe: ошибка обработки %s %s", method, path)
            await self.writer.send({
                "type": "response", "id": request_id,
                "status": 500, "body": {"detail": str(exc)},
            })

    async def handle_stream(self, message: dict[str, Any]) -> None:
        channel = str(message.get("channel") or "")
        action = str(message.get("action") or "")
        if not channel:
            return

        if action == "open":
            socket = PipeSocket(channel, self.writer, str(message.get("query") or ""))
            self._streams[channel] = socket
            handler = self._resolve_stream_handler(str(message.get("path") or ""))
            if handler is None:
                await self.writer.send({
                    "type": "stream", "channel": channel, "action": "closed",
                    "code": 4404, "reason": "неизвестный поток",
                })
                return
            self._stream_tasks[channel] = asyncio.create_task(self._run_stream(channel, handler, socket))
            return

        socket = self._streams.get(channel)
        if socket is None:
            return
        if action == "data":
            socket.feed(base64.b64decode(message.get("data") or ""))
        elif action == "close":
            await socket.close()

    async def _run_stream(self, channel: str, handler, socket: PipeSocket) -> None:
        try:
            await handler(socket)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("pipe: поток %s завершился ошибкой", channel)
            await socket.close(code=1011, reason=str(exc))
        finally:
            self._streams.pop(channel, None)
            self._stream_tasks.pop(channel, None)

    def _resolve_stream_handler(self, path: str):
        for route in self.app.routes:
            if getattr(route, "path", None) == path and hasattr(route, "endpoint"):
                if path.startswith("/ws/"):
                    return route.endpoint
        return None

    async def dispatch(self, message: dict[str, Any]) -> None:
        kind = str(message.get("type") or "request")
        if kind == "request":
            await self.handle_request(message)
        elif kind == "stream":
            await self.handle_stream(message)
        else:
            await self.writer.send({
                "type": "response", "id": message.get("id"),
                "status": 400, "body": {"detail": f"неизвестный вид сообщения: {kind}"},
            })


async def _read_lines(loop: asyncio.AbstractEventLoop):
    """Чтение стандартного ввода без блокировки цикла событий.

    Чтение вынесено в отдельный поток намеренно. Штатный для asyncio способа
    подключить стандартный ввод (``connect_read_pipe``) на Windows неприменим:
    цикл событий Proactor не умеет работать с этим дескриптором и первое же
    чтение завершается ошибкой «дескриптор недействителен». Отдельный поток
    работает одинаково во всех операционных системах.
    """
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            return
        text = line.strip()
        if text:
            yield text


async def serve(app=None) -> None:
    """Запустить ядро и обслуживать канал до закрытия стандартного ввода."""
    from neuro_mirror.web.app import create_app

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    app = app or create_app()
    writer = ProtocolWriter()

    # Ядро поднимается тем же способом, что и раньше: жизненный цикл
    # приложения создаёт модули, рабочие процессы и хранилища.
    from contextlib import AsyncExitStack

    async with AsyncExitStack() as stack:
        lifespan = app.router.lifespan_context(app)
        await stack.enter_async_context(lifespan)
        host = await stack.enter_async_context(PipeHost(app, writer))

        # Готовность объявляется до подписки на события: подписка сразу
        # присылает снимок состояния, и он не должен опередить это сообщение.
        await writer.send({"type": "ready", "protocol": PROTOCOL_VERSION})

        context = getattr(app.state, "context", None)
        state_store = getattr(context, "state_store", None)
        if state_store is not None:
            await state_store.connect(EventSubscriber(writer))

        loop = asyncio.get_running_loop()
        async for line in _read_lines(loop):
            try:
                message = json.loads(line)
            except ValueError:
                await writer.send({"type": "response", "status": 400,
                                   "body": {"detail": "строка не является JSON"}})
                continue
            asyncio.create_task(host.dispatch(message))


def main() -> None:
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
