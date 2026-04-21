from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_LOCAL_LIVE2D_MODEL_URL = "/static/assets/live2d/HiyoriAiri/unzipped/hiyori_free_zh/runtime/hiyori_free_t08.model3.json"


@dataclass(slots=True)
class Settings:
    enable_ai_assistant: bool = True
    auto_start: bool | None = None
    web_host: str = "127.0.0.1"
    web_port: int = 8000
    web_live2d_model_url: str = ""
    web_live2d_cubism_core_url: str = "https://cdn.jsdelivr.net/npm/live2dcubismcore@1.0.2/live2dcubismcore.min.js"

    ai_backend: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:e2b"
    ollama_fallback_model: str = ""
    ollama_vision_model: str = "llava"
    ollama_timeout_seconds: float = 30.0

    weather_enabled: bool = True
    weather_location: str = ""
    weather_base_url: str = "https://wttr.in"
    currency_enabled: bool = True
    currency_base_url: str = "https://api.frankfurter.dev"
    internet_fallback_enabled: bool = True
    internet_fallback_base_url: str = "https://html.duckduckgo.com"

    vision_worker_python: str = sys.executable
    vision_worker_script: str = ""
    speech_worker_python: str = sys.executable
    speech_worker_script: str = ""
    worker_request_timeout_seconds: float = 90.0
    preview_interval_seconds: float = 0.10
    camera_index: int = 0
    emotion_model_name: str = "enet_b2_7"
    emotion_engine: str = "onnx"
    emotion_device: str = "cpu"

    stt_model_name: str = "medium"
    stt_language: str = "ru"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    stt_beam_size: int = 5
    stt_best_of: int = 5
    stt_vad_filter: bool = True
    stt_hotwords: str = "камера, что у меня в руках, что в руках, в руках, в руке, держу, покажи, посмотри в камеру, как я выгляжу, оцени внешний вид, скрининг"
    voice_sample_rate: int = 16000
    voice_channels: int = 1
    voice_max_record_seconds: float = 12.0
    tts_voice: str = "ru-RU-SvetlanaNeural"
    tts_rate: str = "+15%"

    @classmethod
    def from_env(cls) -> "Settings":
        base_dir = Path(__file__).resolve().parents[2]
        default_vision_script = base_dir / "runtime" / "vision_worker" / "worker.py"
        default_speech_script = base_dir / "runtime" / "speech_worker" / "worker.py"
        default_live2d_model_file = (
            base_dir
            / "neuro_mirror"
            / "web"
            / "static"
            / "assets"
            / "live2d"
            / "HiyoriAiri"
            / "unzipped"
            / "hiyori_free_zh"
            / "runtime"
            / "hiyori_free_t08.model3.json"
        )
        default_live2d_model_url = (
            DEFAULT_LOCAL_LIVE2D_MODEL_URL
            if default_live2d_model_file.exists()
            else ""
        )

        raw_ai = os.getenv("NEURO_MIRROR_ENABLE_AI_ASSISTANT", "1").strip().lower()
        raw_auto_start = os.getenv("NEURO_MIRROR_AUTO_START", "").strip().lower()
        raw_web_host = os.getenv("NEURO_MIRROR_WEB_HOST", "127.0.0.1").strip()
        raw_web_port = os.getenv("NEURO_MIRROR_WEB_PORT", "8000").strip()
        raw_web_live2d_model_url = os.getenv(
            "NEURO_MIRROR_WEB_LIVE2D_MODEL_URL",
            default_live2d_model_url,
        ).strip()
        raw_web_live2d_cubism_core_url = os.getenv(
            "NEURO_MIRROR_WEB_LIVE2D_CUBISM_CORE_URL",
            "https://cdn.jsdelivr.net/npm/live2dcubismcore@1.0.2/live2dcubismcore.min.js",
        ).strip()

        raw_ai_backend = os.getenv("NEURO_MIRROR_AI_BACKEND", "ollama").strip().lower()
        raw_ollama_base_url = os.getenv(
            "NEURO_MIRROR_OLLAMA_BASE_URL", "http://127.0.0.1:11434"
        ).strip()
        raw_ollama_model = os.getenv("NEURO_MIRROR_OLLAMA_MODEL", "gemma4:e2b").strip()
        raw_ollama_fallback_model = os.getenv("NEURO_MIRROR_OLLAMA_FALLBACK_MODEL", "").strip()
        raw_ollama_vision_model = os.getenv("NEURO_MIRROR_OLLAMA_VISION_MODEL", "llava").strip()
        raw_ollama_timeout = os.getenv("NEURO_MIRROR_OLLAMA_TIMEOUT_SECONDS", "30").strip()

        raw_weather_enabled = os.getenv("NEURO_MIRROR_WEATHER_ENABLED", "1").strip().lower()
        raw_weather_location = os.getenv("NEURO_MIRROR_WEATHER_LOCATION", "").strip()
        raw_weather_base_url = os.getenv("NEURO_MIRROR_WEATHER_BASE_URL", "https://wttr.in").strip()
        raw_currency_enabled = os.getenv("NEURO_MIRROR_CURRENCY_ENABLED", "1").strip().lower()
        raw_currency_base_url = os.getenv(
            "NEURO_MIRROR_CURRENCY_BASE_URL", "https://api.frankfurter.dev"
        ).strip()
        raw_internet_fallback_enabled = os.getenv(
            "NEURO_MIRROR_INTERNET_FALLBACK_ENABLED", "1"
        ).strip().lower()
        raw_internet_fallback_base_url = os.getenv(
            "NEURO_MIRROR_INTERNET_FALLBACK_BASE_URL", "https://html.duckduckgo.com"
        ).strip()

        raw_vision_worker_python = os.getenv("NEURO_MIRROR_VISION_WORKER_PYTHON", sys.executable).strip()
        raw_vision_worker_script = os.getenv(
            "NEURO_MIRROR_VISION_WORKER_SCRIPT", str(default_vision_script)
        ).strip()
        raw_speech_worker_python = os.getenv("NEURO_MIRROR_SPEECH_WORKER_PYTHON", sys.executable).strip()
        raw_speech_worker_script = os.getenv(
            "NEURO_MIRROR_SPEECH_WORKER_SCRIPT", str(default_speech_script)
        ).strip()
        raw_worker_timeout = os.getenv("NEURO_MIRROR_WORKER_TIMEOUT_SECONDS", "45").strip()
        raw_preview_interval = os.getenv("NEURO_MIRROR_PREVIEW_INTERVAL_SECONDS", "0.10").strip()
        raw_camera_index = os.getenv("NEURO_MIRROR_CAMERA_INDEX", "0").strip()
        raw_emotion_model_name = os.getenv("NEURO_MIRROR_EMOTION_MODEL", "enet_b2_7").strip()
        raw_emotion_engine = os.getenv("NEURO_MIRROR_EMOTION_ENGINE", "onnx").strip().lower()
        raw_emotion_device = os.getenv("NEURO_MIRROR_EMOTION_DEVICE", "cpu").strip().lower()

        raw_stt_model = os.getenv("NEURO_MIRROR_STT_MODEL", "medium").strip()
        raw_stt_language = os.getenv("NEURO_MIRROR_STT_LANGUAGE", "ru").strip()
        raw_stt_device = os.getenv("NEURO_MIRROR_STT_DEVICE", "cpu").strip().lower()
        raw_stt_compute_type = os.getenv("NEURO_MIRROR_STT_COMPUTE_TYPE", "int8").strip()
        raw_stt_beam_size = os.getenv("NEURO_MIRROR_STT_BEAM_SIZE", "5").strip()
        raw_stt_best_of = os.getenv("NEURO_MIRROR_STT_BEST_OF", "5").strip()
        raw_stt_vad_filter = os.getenv("NEURO_MIRROR_STT_VAD_FILTER", "1").strip().lower()
        raw_stt_hotwords = os.getenv(
            "NEURO_MIRROR_STT_HOTWORDS",
            "камера, в руках, в руке, держу, скрининг, внешний вид",
        ).strip()
        if "РєР°РјРµСЂР°" in raw_stt_hotwords:
            raw_stt_hotwords = (
                "камера, что у меня в руках, что в руках, в руках, в руке, держу, "
                "покажи, посмотри в камеру, как я выгляжу, оцени внешний вид, скрининг"
            )
        raw_voice_sample_rate = os.getenv("NEURO_MIRROR_VOICE_SAMPLE_RATE", "16000").strip()
        if raw_stt_hotwords.startswith("\u0420") and "\u043a\u0430\u043c\u0435\u0440\u0430" not in raw_stt_hotwords.lower():
            raw_stt_hotwords = (
                "\u043a\u0430\u043c\u0435\u0440\u0430, \u0447\u0442\u043e \u0443 \u043c\u0435\u043d\u044f \u0432 \u0440\u0443\u043a\u0430\u0445, "
                "\u0447\u0442\u043e \u0432 \u0440\u0443\u043a\u0430\u0445, \u0432 \u0440\u0443\u043a\u0430\u0445, \u0432 \u0440\u0443\u043a\u0435, "
                "\u0434\u0435\u0440\u0436\u0443, \u043f\u043e\u043a\u0430\u0436\u0438, \u043f\u043e\u0441\u043c\u043e\u0442\u0440\u0438 \u0432 \u043a\u0430\u043c\u0435\u0440\u0443, "
                "\u043a\u0430\u043a \u044f \u0432\u044b\u0433\u043b\u044f\u0436\u0443, \u043e\u0446\u0435\u043d\u0438 \u0432\u043d\u0435\u0448\u043d\u0438\u0439 \u0432\u0438\u0434, "
                "\u0441\u043a\u0440\u0438\u043d\u0438\u043d\u0433"
            )
        raw_voice_channels = os.getenv("NEURO_MIRROR_VOICE_CHANNELS", "1").strip()
        raw_voice_max_seconds = os.getenv("NEURO_MIRROR_VOICE_MAX_SECONDS", "12").strip()
        raw_tts_voice = os.getenv("NEURO_MIRROR_TTS_VOICE", "ru-RU-SvetlanaNeural").strip()
        raw_tts_rate = os.getenv("NEURO_MIRROR_TTS_RATE", "+0%").strip()

        auto_start: bool | None
        if raw_auto_start == "":
            auto_start = None
        else:
            auto_start = raw_auto_start not in {"0", "false", "no"}

        return cls(
            enable_ai_assistant=raw_ai not in {"0", "false", "no"},
            auto_start=auto_start,
            web_host=raw_web_host,
            web_port=int(raw_web_port),
            web_live2d_model_url=raw_web_live2d_model_url,
            web_live2d_cubism_core_url=raw_web_live2d_cubism_core_url,
            ai_backend=raw_ai_backend,
            ollama_base_url=raw_ollama_base_url,
            ollama_model=raw_ollama_model,
            ollama_fallback_model=raw_ollama_fallback_model,
            ollama_vision_model=raw_ollama_vision_model,
            ollama_timeout_seconds=float(raw_ollama_timeout),
            weather_enabled=raw_weather_enabled not in {"0", "false", "no"},
            weather_location=raw_weather_location,
            weather_base_url=raw_weather_base_url,
            currency_enabled=raw_currency_enabled not in {"0", "false", "no"},
            currency_base_url=raw_currency_base_url,
            internet_fallback_enabled=raw_internet_fallback_enabled not in {"0", "false", "no"},
            internet_fallback_base_url=raw_internet_fallback_base_url,
            vision_worker_python=raw_vision_worker_python,
            vision_worker_script=raw_vision_worker_script,
            speech_worker_python=raw_speech_worker_python,
            speech_worker_script=raw_speech_worker_script,
            worker_request_timeout_seconds=float(raw_worker_timeout),
            preview_interval_seconds=float(raw_preview_interval),
            camera_index=int(raw_camera_index),
            emotion_model_name=raw_emotion_model_name,
            emotion_engine=raw_emotion_engine,
            emotion_device=raw_emotion_device,
            stt_model_name=raw_stt_model,
            stt_language=raw_stt_language,
            stt_device=raw_stt_device if raw_stt_device in {"auto", "cpu", "cuda"} else "auto",
            stt_compute_type=raw_stt_compute_type,
            stt_beam_size=max(1, int(raw_stt_beam_size)),
            stt_best_of=max(1, int(raw_stt_best_of)),
            stt_vad_filter=raw_stt_vad_filter not in {"0", "false", "no"},
            stt_hotwords=raw_stt_hotwords,
            voice_sample_rate=int(raw_voice_sample_rate),
            voice_channels=int(raw_voice_channels),
            voice_max_record_seconds=float(raw_voice_max_seconds),
            tts_voice=raw_tts_voice,
            tts_rate=raw_tts_rate,
        )
