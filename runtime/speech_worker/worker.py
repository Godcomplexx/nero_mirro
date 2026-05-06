from __future__ import annotations

import json
import sys
import time
from typing import Any

try:
    from faster_whisper import WhisperModel  # type: ignore
except Exception:
    WhisperModel = None

MODEL_CACHE: dict[str, Any] = {}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            request_payload = json.loads(raw_line)
            response_payload = handle_request(request_payload)
        except Exception as exc:
            response_payload = {
                "id": _safe_id(raw_line),
                "ok": False,
                "error": {
                    "code": "worker_exception",
                    "message": str(exc),
                },
            }

        sys.stdout.write(json.dumps(response_payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    return 0


def handle_request(request_payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(request_payload.get("id") or "")
    action = str(request_payload.get("action") or "")
    payload = request_payload.get("payload") or {}

    if action == "health":
        result = build_health()
    elif action == "warmup_model":
        result = warmup_model(
            model_name=str(payload.get("model_name") or "small"),
            device=str(payload.get("device") or "auto"),
            compute_type=str(payload.get("compute_type") or "int8"),
        )
    elif action == "transcribe_audio_file":
        result = transcribe_audio_file(
            audio_path=str(payload.get("audio_path") or ""),
            model_name=str(payload.get("model_name") or "small"),
            language=str(payload.get("language") or "ru"),
            device=str(payload.get("device") or "auto"),
            compute_type=str(payload.get("compute_type") or "int8"),
            beam_size=max(1, int(payload.get("beam_size") or 5)),
            best_of=max(1, int(payload.get("best_of") or 5)),
            vad_filter=bool(payload.get("vad_filter", True)),
            hotwords=str(payload.get("hotwords") or "").strip(),
        )
    else:
        return {
            "id": request_id,
            "ok": False,
            "error": {
                "code": "unknown_action",
                "message": f"unknown action: {action}",
            },
        }

    return {
        "id": request_id,
        "ok": True,
        "result": result,
    }


def build_health() -> dict[str, Any]:
    return {
        "worker_available": True,
        "stt_available": WhisperModel is not None,
        "python_executable": sys.executable,
        "cached_models": list(MODEL_CACHE.keys()),
    }


def warmup_model(model_name: str, device: str, compute_type: str) -> dict[str, Any]:
    started_at = time.perf_counter()
    model, resolved_device, resolved_compute_type = load_model(model_name, device, compute_type)
    return {
        "model_name": model_name,
        "device": resolved_device,
        "compute_type": compute_type,
        "resolved_compute_type": resolved_compute_type,
        "ready": model is not None,
        "load_ms": round((time.perf_counter() - started_at) * 1000, 1),
    }


def transcribe_audio_file(
    audio_path: str,
    model_name: str,
    language: str,
    device: str,
    compute_type: str,
    beam_size: int,
    best_of: int,
    vad_filter: bool,
    hotwords: str,
) -> dict[str, Any]:
    if WhisperModel is None:
        return {
            "transcript": "",
            "language": language,
            "model_name": model_name,
            "segments": [],
            "notes": "faster-whisper не установлен в speech worker.",
        }

    load_started_at = time.perf_counter()
    model, resolved_device, resolved_compute_type = load_model(model_name, device, compute_type)
    load_ms = round((time.perf_counter() - load_started_at) * 1000, 1)

    transcribe_started_at = time.perf_counter()
    fallback_note = ""
    try:
        segments, info = _run_transcription(
            model,
            audio_path=audio_path,
            language=language,
            beam_size=beam_size,
            best_of=best_of,
            vad_filter=vad_filter,
            hotwords=hotwords,
        )
    except Exception as exc:
        if resolved_device != "cuda" or not _is_cuda_runtime_error(exc):
            raise
        cpu_fallback_started_at = time.perf_counter()
        model, resolved_device, resolved_compute_type = load_model(model_name, "cpu", compute_type)
        load_ms += round((time.perf_counter() - cpu_fallback_started_at) * 1000, 1)
        segments, info = _run_transcription(
            model,
            audio_path=audio_path,
            language=language,
            beam_size=beam_size,
            best_of=best_of,
            vad_filter=vad_filter,
            hotwords=hotwords,
        )
        fallback_note = f"CUDA STT недоступен, использован CPU fallback: {exc}"
    items = list(segments)
    transcript = " ".join(segment.text.strip() for segment in items if segment.text.strip()).strip()
    average_logprob = _average_metric(items, "avg_logprob")
    max_no_speech_prob = _max_metric(items, "no_speech_prob")
    confidence_score = _estimate_confidence(
        transcript,
        average_logprob=average_logprob,
        max_no_speech_prob=max_no_speech_prob,
    )
    return {
        "transcript": transcript,
        "language": getattr(info, "language", language),
        "model_name": model_name,
        "device": resolved_device,
        "compute_type": resolved_compute_type,
        "beam_size": beam_size,
        "best_of": best_of,
        "vad_filter": vad_filter,
        "hotwords": hotwords,
        "load_ms": load_ms,
        "transcribe_ms": round((time.perf_counter() - transcribe_started_at) * 1000, 1),
        "average_logprob": average_logprob,
        "max_no_speech_prob": max_no_speech_prob,
        "confidence_score": confidence_score,
        "segments": [
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
            }
            for segment in items
        ],
        "notes": fallback_note,
    }


def load_model(model_name: str, device: str, compute_type: str):
    candidate_configs = _build_model_candidates(device, compute_type)
    last_error: Exception | None = None
    for candidate_device, candidate_compute_type in candidate_configs:
        cache_key = f"{model_name}:{candidate_device}:{candidate_compute_type}"
        model = MODEL_CACHE.get(cache_key)
        if model is not None:
            return model, candidate_device, candidate_compute_type
        try:
            model = WhisperModel(model_name, device=candidate_device, compute_type=candidate_compute_type)
            MODEL_CACHE[cache_key] = model
            return model, candidate_device, candidate_compute_type
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise RuntimeError("Не удалось загрузить faster-whisper модель.")


def _build_model_candidates(device: str, compute_type: str) -> list[tuple[str, str]]:
    normalized_device = str(device or "auto").strip().lower() or "auto"
    normalized_compute = str(compute_type or "int8").strip().lower() or "int8"

    candidates: list[tuple[str, str]] = []

    def add(candidate_device: str, candidate_compute_type: str) -> None:
        item = (candidate_device, candidate_compute_type)
        if item not in candidates:
            candidates.append(item)

    if normalized_device in {"auto", "cuda"}:
        add("cuda", normalized_compute)
        add("cuda", "float16")
        add("cuda", "int8_float16")

    if normalized_device in {"auto", "cpu", "cuda"}:
        add("cpu", normalized_compute)
        add("cpu", "int8")
        add("cpu", "float32")

    return candidates


def _run_transcription(
    model,
    *,
    audio_path: str,
    language: str,
    beam_size: int,
    best_of: int,
    vad_filter: bool,
    hotwords: str,
):
    # temperature fallback list: start greedy, step up if model is uncertain
    temperatures = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    return model.transcribe(
        audio_path,
        language=language,
        beam_size=beam_size,
        best_of=best_of,
        condition_on_previous_text=False,
        vad_filter=vad_filter,
        without_timestamps=True,
        temperature=temperatures,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
        hotwords=hotwords or None,
        initial_prompt=(
            "Разговорная речь на русском языке. Короткие фразы и вопросы. "
            "Имена, города, бытовые слова. Зеркало, камера, погода, время."
        ),
    )


def _is_cuda_runtime_error(exc: Exception) -> bool:
    message = str(exc).lower()
    markers = (
        "cublas",
        "cudnn",
        "cuda",
        "cannot be loaded",
        "dll is not found",
        "dll not found",
    )
    return any(marker in message for marker in markers)


def _average_metric(items: list[Any], field_name: str) -> float | None:
    values: list[float] = []
    for item in items:
        value = getattr(item, field_name, None)
        if isinstance(value, (int, float)):
            values.append(float(value))
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _max_metric(items: list[Any], field_name: str) -> float | None:
    values: list[float] = []
    for item in items:
        value = getattr(item, field_name, None)
        if isinstance(value, (int, float)):
            values.append(float(value))
    if not values:
        return None
    return round(max(values), 3)


def _estimate_confidence(
    transcript: str,
    *,
    average_logprob: float | None,
    max_no_speech_prob: float | None,
) -> float:
    if not transcript.strip():
        return 0.0

    score = 0.65
    word_count = len(transcript.split())
    # Short commands (1-2 words) are normal for a voice assistant — only penalise single
    # characters or obvious noise (single letter / punctuation only)
    if word_count == 1:
        score -= 0.06

    if average_logprob is not None:
        if average_logprob < -1.4:
            score -= 0.25
        elif average_logprob < -1.0:
            score -= 0.12
        elif average_logprob < -0.7:
            score -= 0.05
        else:
            score += 0.08

    if max_no_speech_prob is not None:
        if max_no_speech_prob > 0.75:
            score -= 0.25
        elif max_no_speech_prob > 0.5:
            score -= 0.10

    # Single character output is almost always a hallucination
    cleaned = transcript.strip(" .,!?:;\"'")
    if cleaned and len(cleaned) <= 2:
        score -= 0.15

    return round(max(0.0, min(1.0, score)), 3)


def _safe_id(raw_line: str) -> str:
    try:
        return str(json.loads(raw_line).get("id") or "")
    except Exception:
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
