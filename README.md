# Neuro Mirror

Локальный прототип `Neuro Mirror` с основным `Web UI`, локальным ассистентом через `Ollama`, visual worker для камеры и speech worker для локального STT.

## Быстрый запуск

```powershell
python main.py
```

После старта web UI будет доступен по адресу `http://127.0.0.1:8000`, если вы не переопределили `NEURO_MIRROR_WEB_HOST` и `NEURO_MIRROR_WEB_PORT`.

## Что уже работает

- чат с ассистентом
- TTS-озвучка ответов через `edge-tts`
- browser preview локальной камеры
- отправка кадра на visual analysis
- голосовой ввод через `MediaRecorder -> speech worker`
- appearance-report по сценарию `Как я сегодня выгляжу?`
- журнал статусов и worker-модулей через `WebSocket`

## Ollama

Основная модель:

```powershell
ollama pull gemma4:e2b
```

Пример запуска с `Ollama`:

```powershell
$env:NEURO_MIRROR_AI_BACKEND="ollama"
$env:NEURO_MIRROR_OLLAMA_MODEL="gemma4:e2b"
python main.py
```

## Worker Runtime

В проекте есть:

```text
runtime/
  vision_worker/
    worker.py
    requirements.txt
  speech_worker/
    worker.py
    requirements.txt
```

По умолчанию оба worker'а запускаются через текущий `python`. При необходимости можно переопределить интерпретаторы и пути:

```powershell
$env:NEURO_MIRROR_VISION_WORKER_PYTHON="D:\\path\\to\\python.exe"
$env:NEURO_MIRROR_SPEECH_WORKER_PYTHON="D:\\path\\to\\python.exe"
$env:NEURO_MIRROR_VISION_WORKER_SCRIPT="D:\\neuro_mirro\\runtime\\vision_worker\\worker.py"
$env:NEURO_MIRROR_SPEECH_WORKER_SCRIPT="D:\\neuro_mirro\\runtime\\speech_worker\\worker.py"
python main.py
```

Рекомендуемые зависимости:

```powershell
python -m pip install -r runtime\vision_worker\requirements.txt
python -m pip install -r runtime\speech_worker\requirements.txt
python -m pip install sounddevice
```

## Переменные Окружения

- `NEURO_MIRROR_AI_BACKEND=ollama`
- `NEURO_MIRROR_OLLAMA_MODEL=gemma4:e2b`
- `NEURO_MIRROR_ASSISTANT_RULES_PATH=` — путь к кастомному rules-файлу ассистента; пусто = встроенный `assistant_rules.md`
- `NEURO_MIRROR_WEATHER_LOCATION=Samara`
- `NEURO_MIRROR_CAMERA_INDEX=0`
- `NEURO_MIRROR_PREVIEW_INTERVAL_SECONDS=1.2`
- `NEURO_MIRROR_WEB_HOST=127.0.0.1`
- `NEURO_MIRROR_WEB_PORT=8000`
- `NEURO_MIRROR_WEB_LIVE2D_MODEL_URL=`
- `NEURO_MIRROR_WEB_LIVE2D_CUBISM_CORE_URL=https://cdn.jsdelivr.net/npm/live2dcubismcore@1.0.2/live2dcubismcore.min.js`
- `NEURO_MIRROR_EMOTION_MODEL=enet_b2_7`
- `NEURO_MIRROR_EMOTION_ENGINE=onnx`
- `NEURO_MIRROR_EMOTION_DEVICE=cpu`
- `NEURO_MIRROR_TTS_VOICE=ru-RU-SvetlanaNeural`
- `NEURO_MIRROR_TTS_RATE=+0%`
- `NEURO_MIRROR_STT_MODEL=small`
- `NEURO_MIRROR_STT_LANGUAGE=ru`
- `NEURO_MIRROR_STT_COMPUTE_TYPE=int8`

## Web UI

Web-версия использует:

- `FastAPI + WebSocket`
- локальную камеру браузера для preview
- `edge-tts` для русской озвучки
- маскота `AIRI Hiyori` из `moeru-ai/airi` с состояниями `idle / listening / thinking / speaking`
- опциональный `Live2D` URL через `NEURO_MIRROR_WEB_LIVE2D_MODEL_URL`

## AIRI Mascot

В `web UI` интегрирован preview-ассет `Hiyori` из проекта `moeru-ai/airi`.

- локальный файл: `neuro_mirror/web/static/assets/airi/hiyori-preview.png`
- notice по источнику и лицензии: `neuro_mirror/web/static/assets/airi/NOTICE.txt`
- полный Live2D-модельный набор в этот репозиторий не включён
- если у вас есть `model3.json`, укажите `NEURO_MIRROR_WEB_LIVE2D_MODEL_URL`; web UI попробует загрузить живую модель через `pixi-live2d-display`

## EmotiEffLib Emotion Model

Vision worker использует `EmotiEffLib` для facial emotion recognition. По умолчанию:

```text
engine = onnx
model  = enet_b2_7
device = cpu
```

Веса скачиваются автоматически в пользовательский cache при первом запуске.

## Vision-запросы через камеру

Ассистент может смотреть в камеру и отвечать на вопросы о том, что видит.

Спросите:
- «Что ты видишь на камере?»
- «Что в кадре?»
- «Опиши что видишь»

Для этого используется Ollama vision-модель. Если у вас есть мультимодальная модель
(например `llava`, `llava-llama3`, `gemma4:e2b`), укажите её:

```powershell
$env:NEURO_MIRROR_OLLAMA_VISION_MODEL="llava"
python main_web.py
```

Если `NEURO_MIRROR_OLLAMA_VISION_MODEL` не задана, используется основная модель
из `NEURO_MIRROR_OLLAMA_MODEL`.

## Прогрев STT-модели

При запуске `main_web.py` speech worker автоматически прогревает модель Whisper,
чтобы первая транскрибация не занимала слишком много времени.
Таймаут транскрибации увеличен до 120 секунд (с 45).
