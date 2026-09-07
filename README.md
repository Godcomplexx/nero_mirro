# Neuro Mirror — Установка на новый ПК (пошагово)

Локальный прототип `Neuro Mirror`: Web UI, локальный ассистент через Ollama, камера, распознавание речи, TTS-озвучка, анализ эмоций.

---

## Требования

- Windows 10/11 (64-bit)
- Python 3.11 или 3.12 — [скачать здесь](https://www.python.org/downloads/)
- Git — [скачать здесь](https://git-scm.com/download/win)
- Ollama — [скачать здесь](https://ollama.com/download)
- Веб-камера (USB или встроенная)
- Микрофон

---

## Шаг 1 — Скачать проект

Открой PowerShell и выполни:

```powershell
git clone --recurse-submodules https://github.com/Godcomplexx/neuro-mirror.git
cd neuro-mirror
```

> Если репозиторий приватный — скачай ZIP с GitHub и распакуй в любую папку, затем `cd` в неё.

---

## Шаг 2 — Установить Python-зависимости

```powershell
python -m pip install --upgrade pip
python -m pip install -r runtime\vision_worker\requirements.txt
python -m pip install -r runtime\speech_worker\requirements.txt
python -m pip install sounddevice fastapi uvicorn websockets edge-tts httpx
```

> Если у тебя есть GPU NVIDIA — дополнительно установи PyTorch с CUDA:
> ```powershell
> python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
> ```
> Без GPU всё работает на CPU, просто медленнее.

---

## Шаг 3 — Установить и запустить Ollama

1. Установи [Ollama](https://ollama.com/download) — запускается как фоновый сервис автоматически.

2. Скачай языковую модель (нужен интернет, ~5 ГБ):

```powershell
ollama pull gemma4:e2b
```

3. Для работы анализа изображений с камеры — скачай vision-модель:

```powershell
ollama pull llava
```

4. Проверь, что Ollama работает:

```powershell
ollama list
```

Должны появиться скачанные модели.

---

## Шаг 4 — Первый запуск

Из папки проекта:

```powershell
python main.py
```

Подожди 20–60 секунд — при первом запуске загружаются веса моделей распознавания эмоций (~200 МБ).

Открой браузер и перейди по адресу:

```
http://127.0.0.1:8000
```

---

## Шаг 5 — Настройка (по желанию)

Все параметры задаются через переменные окружения перед запуском. Примеры:

### Принудительно CPU (если нет GPU):

```powershell
$env:NEURO_MIRROR_DEVICE = "cpu"
python main.py
```

### Принудительно GPU:

```powershell
python main.py -gpu
```

### Задать город для погоды:

```powershell
$env:NEURO_MIRROR_WEATHER_LOCATION = "Moscow"
python main.py
```

### Сменить камеру (если несколько камер):

```powershell
$env:NEURO_MIRROR_CAMERA_INDEX = "1"
python main.py
```

### Сменить голос TTS:

```powershell
$env:NEURO_MIRROR_TTS_VOICE = "ru-RU-DmitryNeural"
python main.py
```

### Использовать другую модель Ollama:

```powershell
$env:NEURO_MIRROR_OLLAMA_MODEL = "llava"
python main.py
```

---

## Все переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `NEURO_MIRROR_DEVICE` | `auto` | `auto` / `cpu` / `cuda` |
| `NEURO_MIRROR_AI_BACKEND` | `ollama` | Бэкенд ассистента |
| `NEURO_MIRROR_OLLAMA_MODEL` | `gemma4:e2b` | Модель для чата |
| `NEURO_MIRROR_OLLAMA_VISION_MODEL` | `llava` | Модель для анализа камеры |
| `NEURO_MIRROR_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Адрес Ollama |
| `NEURO_MIRROR_WEATHER_LOCATION` | _(пусто)_ | Город для погоды |
| `NEURO_MIRROR_CAMERA_INDEX` | `0` | Индекс камеры |
| `NEURO_MIRROR_TTS_VOICE` | `ru-RU-SvetlanaNeural` | Голос озвучки |
| `NEURO_MIRROR_TTS_RATE` | `+0%` | Скорость речи |
| `NEURO_MIRROR_STT_MODEL` | `v3_rnnt` | Модель GigaAM для распознавания речи |
| `NEURO_MIRROR_STT_LANGUAGE` | `ru` | Язык распознавания |
| `NEURO_MIRROR_WEB_HOST` | `127.0.0.1` | Адрес Web UI |
| `NEURO_MIRROR_WEB_PORT` | `8000` | Порт Web UI |
| `NEURO_MIRROR_EMOTION_MODEL` | `enet_b2_7` | Модель анализа эмоций |
| `NEURO_MIRROR_EMOTION_ENGINE` | `onnx` | Движок (`onnx` / `torch`) |

---

## Структура проекта

```
neuro-mirror/
├── main.py                    # Точка входа
├── runtime/
│   ├── vision_worker/
│   │   ├── worker.py          # Воркер камеры и эмоций
│   │   └── requirements.txt
│   └── speech_worker/
│       ├── worker.py          # Воркер распознавания речи
│       └── requirements.txt
├── neuro_mirror/
│   ├── core/                  # Настройки, менеджер устройств
│   ├── plugins/               # Ассистент, камера, STT, TTS, UI
│   └── web/                   # FastAPI + WebSocket + статика
└── external/
    └── rppg-heart-rate-measurement/  # Измерение пульса по видео
```

---

## Возможные проблемы

### Ошибка `No module named 'xxx'`

```powershell
python -m pip install xxx
```

### Ollama не отвечает

Убедись, что Ollama запущена. Открой Task Manager и проверь процесс `ollama.exe`, или запусти вручную:

```powershell
ollama serve
```

### Камера не работает

Попробуй другой индекс камеры:

```powershell
$env:NEURO_MIRROR_CAMERA_INDEX = "1"
python main.py
```

### Голос не слышен / микрофон не работает

Проверь, что микрофон разрешён в Windows: **Настройки → Конфиденциальность → Микрофон**.

### Медленно работает без GPU

GigaAM автоматически переключается на CPU, если CUDA недоступна. Режим
можно задать явно:

```powershell
$env:NEURO_MIRROR_STT_DEVICE = "cpu"
python main.py
```

---

## Что умеет система

- Чат с ИИ-ассистентом (голосом и текстом)
- TTS-озвучка ответов через `edge-tts` (русский голос)
- Просмотр камеры в браузере в реальном времени
- Анализ эмоций по лицу
- Голосовой ввод через GigaAM (локально, без интернета)
- Ответы на вопросы «Как я выгляжу?», «Что на камере?»
- Погода и курсы валют
- Измерение пульса по видео (rPPG)
- Маскот AIRI Hiyori с анимированными состояниями
- MoCA-тест когнитивных функций
