from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path



@dataclass(slots=True)
class Settings:
    auto_start: bool | None = None
    web_host: str = "127.0.0.1"
    web_port: int = 8000


    # Global device flag: "auto" detects GPU, "cpu" forces CPU, "cuda" forces GPU
    device: str = "auto"

    vision_worker_python: str = sys.executable
    vision_worker_script: str = ""
    speech_worker_python: str = sys.executable
    speech_worker_script: str = ""
    worker_request_timeout_seconds: float = 90.0
    preview_interval_seconds: float = 0.10
    camera_index: int = 0
    rppg_duration_seconds: float = 20.0
    emotion_model_name: str = "enet_b2_7"

    stt_model_name: str = "v3_rnnt"
    stt_language: str = "ru"
    stt_device: str = "auto"
    stt_compute_type: str = "auto"
    stt_beam_size: int = 5
    stt_best_of: int = 5
    stt_vad_filter: bool = True
    stt_hotwords: str = "зеркало, камера, что у меня в руках, что в руках, в руках, в руке, держу, покажи, посмотри в камеру, как я выгляжу, оцени внешний вид, скрининг, погода, время, привет, как дела, расскажи, включи, выключи"
    voice_sample_rate: int = 16000
    voice_channels: int = 1
    voice_max_record_seconds: float = 12.0
    voice_silence_threshold: float = 0.012
    voice_silence_duration: float = 1.8
    voice_min_speech_duration: float = 0.4
    save_moca_audio: bool = True
    # Сколько ждать нажатия «Приступить» перед заданием MoCA. Ноль
    # означает «начинать сразу»: так проверки не простаивают.
    moca_start_grace_seconds: float = 25.0

    @classmethod
    def from_env(cls) -> "Settings":
        base_dir = Path(__file__).resolve().parents[2]
        default_vision_script = base_dir / "runtime" / "vision_worker" / "worker.py"
        default_speech_script = base_dir / "runtime" / "speech_worker" / "worker.py"
        raw_auto_start = os.getenv("NEURO_MIRROR_AUTO_START", "").strip().lower()
        raw_web_host = os.getenv("NEURO_MIRROR_WEB_HOST", "127.0.0.1").strip()
        raw_web_port = os.getenv("NEURO_MIRROR_WEB_PORT", "8000").strip()


        # Global device: "auto" = detect CUDA at runtime, "cpu" = force CPU, "cuda" = force GPU
        raw_device = os.getenv("NEURO_MIRROR_DEVICE", "auto").strip().lower()
        if raw_device not in {"auto", "cpu", "cuda"}:
            raw_device = "auto"

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
        raw_rppg_duration = os.getenv("NEURO_MIRROR_RPPG_SECONDS", "20").strip()
        raw_emotion_model_name = os.getenv("NEURO_MIRROR_EMOTION_MODEL", "enet_b2_7").strip()

        raw_stt_model = os.getenv(
            "NEURO_MIRROR_STT_MODEL",
            "v3_rnnt",
        ).strip()
        raw_stt_language = os.getenv("NEURO_MIRROR_STT_LANGUAGE", "ru").strip()
        raw_stt_device = os.getenv("NEURO_MIRROR_STT_DEVICE", raw_device).strip().lower()
        raw_stt_compute_type = os.getenv("NEURO_MIRROR_STT_COMPUTE_TYPE", "auto").strip()
        raw_stt_beam_size = os.getenv("NEURO_MIRROR_STT_BEAM_SIZE", "5").strip()
        raw_stt_best_of = os.getenv("NEURO_MIRROR_STT_BEST_OF", "5").strip()
        raw_stt_vad_filter = os.getenv("NEURO_MIRROR_STT_VAD_FILTER", "1").strip().lower()
        raw_stt_hotwords = os.getenv(
            "NEURO_MIRROR_STT_HOTWORDS",
            "камера, в руках, в руке, держу, скрининг, внешний вид, президент, сша, юсей, usa",
        ).strip()
        if "РєР°РјРµСЂР°" in raw_stt_hotwords:
            raw_stt_hotwords = (
                "камера, что у меня в руках, что в руках, в руках, в руке, держу, "
                "покажи, посмотри в камеру, как я выгляжу, оцени внешний вид, скрининг"
            )
        raw_voice_sample_rate = os.getenv("NEURO_MIRROR_VOICE_SAMPLE_RATE", "16000").strip()
        raw_voice_silence_threshold = os.getenv("NEURO_MIRROR_VOICE_SILENCE_THRESHOLD", "0.012").strip()
        raw_voice_silence_duration = os.getenv("NEURO_MIRROR_VOICE_SILENCE_DURATION", "1.8").strip()
        raw_voice_min_speech_duration = os.getenv("NEURO_MIRROR_VOICE_MIN_SPEECH_DURATION", "0.4").strip()
        raw_moca_grace = os.getenv("NEURO_MIRROR_MOCA_START_GRACE", "25").strip()
        raw_save_moca_audio = os.getenv(
            "NEURO_MIRROR_SAVE_MOCA_AUDIO",
            "1",
        ).strip().lower()
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

        auto_start: bool | None
        if raw_auto_start == "":
            auto_start = None
        else:
            auto_start = raw_auto_start not in {"0", "false", "no"}

        return cls(
            auto_start=auto_start,
            web_host=raw_web_host,
            web_port=int(raw_web_port),
            device=raw_device,
            vision_worker_python=raw_vision_worker_python,
            vision_worker_script=raw_vision_worker_script,
            speech_worker_python=raw_speech_worker_python,
            speech_worker_script=raw_speech_worker_script,
            worker_request_timeout_seconds=float(raw_worker_timeout),
            preview_interval_seconds=float(raw_preview_interval),
            camera_index=int(raw_camera_index),
            rppg_duration_seconds=float(raw_rppg_duration),
            emotion_model_name=raw_emotion_model_name,
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
            voice_silence_threshold=float(raw_voice_silence_threshold),
            voice_silence_duration=float(raw_voice_silence_duration),
            voice_min_speech_duration=float(raw_voice_min_speech_duration),
            save_moca_audio=raw_save_moca_audio not in {"0", "false", "no"},
            moca_start_grace_seconds=max(0.0, float(raw_moca_grace or 25)),
        )
