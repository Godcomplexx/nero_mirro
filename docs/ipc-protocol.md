# Связь интерфейса с ядром

Ядро запускается интерфейсом как дочерняя программа и общается с ним через
стандартные потоки ввода-вывода. Сетевой порт не открывается: подключиться к
ядру извне нельзя, отдельный сервер не разворачивается и не администрируется.

## Запуск ядра

```
D:\neuro_mirro\.venv\Scripts\python.exe -m neuro_mirror.app.pipe_host
```

Рабочий каталог — корень проекта. Ядро готово примерно через 5 секунд: столько
занимает запуск рабочих процессов распознавания речи и видеоанализа.

Из Electron:

```js
const { spawn } = require("node:child_process");

const core = spawn(pythonPath, ["-m", "neuro_mirror.app.pipe_host"], {
  cwd: projectRoot,
  stdio: ["pipe", "pipe", "pipe"],
});
```

- `stdin` — сообщения интерфейса ядру;
- `stdout` — сообщения ядра интерфейсу, **только протокол**;
- `stderr` — журнал работы ядра, к протоколу отношения не имеет.

Закрытие `stdin` завершает ядро штатно.

## Формат

Одно сообщение JSON на строку, кодировка UTF-8. Переводы строк внутри значений
экранируются, поэтому поток читается построчно.

### Готовность

Первым сообщением ядро присылает:

```json
{"type": "ready", "protocol": 1}
```

До него запросы отправлять не нужно.

### Запрос и ответ

Интерфейс отправляет:

```json
{"type": "request", "id": "1", "method": "GET", "path": "/api/state"}
```

```json
{"type": "request", "id": "2", "method": "POST", "path": "/api/games/select",
 "body": {"domain": "memory"}}
```

Ядро отвечает тем же `id`:

```json
{"type": "response", "id": "1", "status": 200, "body": {}}
```

`status` — код результата: `200` успех, `400` ошибка в запросе, `409` действие
сейчас невозможно (например, занятие запрошено до прохождения теста), `500`
внутренняя ошибка. При ошибке в `body.detail` лежит текст для показа человеку.

Порядок ответов не гарантирован: запросы выполняются одновременно, сопоставлять
нужно по `id`. Сбой одного запроса не разрывает канал — остальные продолжают
работать.

### События

Ядро само присылает изменения состояния, без запроса:

```json
{"type": "event", "event": "snapshot", "payload": {}}
{"type": "event", "event": "state",    "payload": {}}
```

`snapshot` приходит один раз сразу после `ready`, `state` — при каждом
изменении. В `payload` полный снимок: экран, сообщение, ход теста, состояние
устройств, журнал событий.

### Поток кадров

Для бесконтактного измерения пульса кадры передаются отдельным потоком.

Открыть:

```json
{"type": "stream", "channel": "rppg-1", "action": "open",
 "path": "/ws/rppg", "query": "mode=screening"}
```

Ядро подтверждает:

```json
{"type": "stream", "channel": "rppg-1", "action": "accepted"}
```

Передать кадр (JPEG, закодированный base64):

```json
{"type": "stream", "channel": "rppg-1", "action": "data", "data": "<base64>"}
```

Ответы ядра приходят как `action: "message"` с полем `payload`.

Закрыть — `action: "close"`. О закрытии со своей стороны ядро сообщает
`action: "closed"` с полями `code` и `reason`.

## Что меняется в коде интерфейса

Пути и состав данных прежние. Меняется только способ вызова.

```js
// было
const state = await fetch("/api/state").then(r => r.json());

// стало
const state = await core.request("GET", "/api/state");
```

События вместо веб-сокета:

```js
// было
ws.addEventListener("message", e => render(JSON.parse(e.data).payload));

// стало
core.onEvent(payload => render(payload));
```

Обёртка `core` пишется один раз в слое связи с вычислительной частью: она
нумерует запросы, складывает ответы по `id` и раздаёт события подписчикам.
Экраны правятся по одному, заменой вызова.

## Образец обёртки

Такого объекта в ядре нет — он пишется на стороне интерфейса, один раз, в слое
связи с вычислительной частью. Ниже минимальный рабочий вариант; при желании
замените на свой.

```js
const readline = require("node:readline");

function connectCore(child) {
  const pending = new Map();
  const listeners = [];
  let nextId = 0;
  let readyResolve;
  const ready = new Promise(resolve => { readyResolve = resolve; });

  readline.createInterface({ input: child.stdout }).on("line", line => {
    let message;
    try { message = JSON.parse(line); } catch { return; }

    if (message.type === "ready") { readyResolve(message); return; }

    if (message.type === "response") {
      const waiting = pending.get(message.id);
      if (!waiting) return;
      pending.delete(message.id);
      if (message.status >= 400) {
        const error = new Error((message.body && message.body.detail) || "Ошибка ядра");
        error.status = message.status;
        waiting.reject(error);
      } else {
        waiting.resolve(message.body);
      }
      return;
    }

    if (message.type === "event") {
      for (const fn of listeners) fn(message.payload, message.event);
    }
  });

  return {
    ready,
    request(method, path, body) {
      const id = String(++nextId);
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        child.stdin.write(JSON.stringify({ type: "request", id, method, path, body }) + "
");
      });
    },
    onEvent(fn) { listeners.push(fn); },
  };
}
```

Применение:

```js
const core = connectCore(child);
await core.ready;

core.onEvent(snapshot => render(snapshot));
const session = await core.request("GET", "/api/training/session");
```

Ответы с кодом 400 и выше приходят как отклонённое обещание, а текст для показа
человеку лежит в `body.detail` — именно он попадает в `error.message`.

## Перечень обращений

| Путь | Метод | Назначение |
|---|---|---|
| `/api/state` | GET | Текущее состояние экрана |
| `/api/config` | GET | Параметры запуска |
| `/api/devices`, `/api/devices/select` | GET, POST | Камеры и микрофоны |
| `/api/users`, `/api/users/{id}/select` | GET, POST | Профили |
| `/api/users/{id}/consents` | POST | Согласия |
| `/api/actions/{action}` | POST | Запуск сценариев |
| `/api/session/check-voice`, `/api/session/check-face` | POST | Проверка условий сессии |
| `/api/training/session` | GET | **Текущее занятие курса: игры по порядку** |
| `/api/training/session/pause`, `/resume`, `/finish` | POST | Пауза и завершение занятия |
| `/api/training/course` | GET | Курс целиком: занятия, исходы, уровни форм |
| `/api/games/catalog` | GET | Каталог игр для свободного выбора |
| `/api/games/{code}/renderer.js` | GET | Модуль отрисовки игры |
| `/api/games/{code}/start`, `/api/games/{code}/answer` | POST | Ход игры |
| `/api/results` | GET | История результатов |
| `/api/sessions/incomplete`, `/api/sessions/{id}/resume` | GET, POST | Продолжение прерванной сессии |
| `/api/tts/speak` | POST | Озвучивание текста |
| `/api/dataset/*` | GET, POST | Сбор набора данных |

## Отладка вёрстки без Electron

Прежний запуск с обращением по адресу остаётся на время перехода:

```
D:\neuro_mirro\.venv\Scripts\python.exe main.py
```

Он открывает `127.0.0.1:8000` и годится, чтобы посмотреть экран в браузере. В
готовой программе не используется и будет удалён, когда интерфейс перейдёт на
канал целиком.
