from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, request

import edge_tts
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from neuro_mirror.app.runtime import RuntimeHandle, create_runtime
from neuro_mirror.core.gpu_scheduler import exclusive_gpu_task, exclusive_gpu_task_sync
from neuro_mirror.core.settings import Settings
from neuro_mirror.core.worker_client import WorkerClient
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.ai_assistant.appearance_response import AppearanceResponseComposer
from neuro_mirror.plugins.ai_assistant.backends import (
    AssistantBackend,
    AssistantDecision,
    build_assistant_backend,
    detect_camera_vision_request,
    normalize_user_utterance,
    source_label_for_backend,
)


class AssistantMessageIn(BaseModel):
    text: str


class CameraVisionRequest(BaseModel):
    text: str
    image_base64: str


class TTSRequest(BaseModel):
    text: str


@dataclass(slots=True)
class WebStateStore:
    snapshot: dict[str, Any] = field(
        default_factory=lambda: {
            "screen": "idle",
            "message": "Веб-интерфейс готов.",
            "assistant_source": "",
            "transcript_text": "",
            "report": None,
            "worker_statuses": {},
            "recording_active": False,
            "event_log": [],
        }
    )
    sockets: set[WebSocket] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self.lock:
            self.sockets.add(websocket)
            snapshot = json.loads(json.dumps(self.snapshot, ensure_ascii=False))
        await websocket.send_json({"type": "snapshot", "payload": snapshot})

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self.lock:
            self.sockets.discard(websocket)

    async def apply_update(self, payload: dict[str, Any], *, source: str) -> None:
        async with self.lock:
            worker_statuses = payload.get("worker_statuses")
            if isinstance(worker_statuses, dict):
                current = self.snapshot.setdefault("worker_statuses", {})
                current.update(worker_statuses)

            for key, value in payload.items():
                if key == "worker_statuses":
                    continue
                self.snapshot[key] = value

            message = payload.get("message")
            if message:
                event_log = self.snapshot.setdefault("event_log", [])
                event_log.append(f"[{source}] {message}")
                self.snapshot["event_log"] = event_log[-80:]

            snapshot = json.loads(json.dumps(self.snapshot, ensure_ascii=False))
            sockets = list(self.sockets)

        stale: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json({"type": "state", "payload": snapshot})
            except Exception:
                stale.append(websocket)

        if stale:
            async with self.lock:
                for websocket in stale:
                    self.sockets.discard(websocket)

    async def get_snapshot(self) -> dict[str, Any]:
        async with self.lock:
            return json.loads(json.dumps(self.snapshot, ensure_ascii=False))


@dataclass(slots=True)
class WebAppContext:
    settings: Settings
    runtime: RuntimeHandle
    state_store: WebStateStore
    assistant_backend: AssistantBackend
    appearance_composer: AppearanceResponseComposer
    vision_worker: WorkerClient
    speech_worker: WorkerClient
    ui_subscription_task: asyncio.Task[None]


async def _consume_ui_updates(runtime: RuntimeHandle, state_store: WebStateStore) -> None:
    subscription = runtime.bus.subscribe(Topics.UI_UPDATE)
    try:
        while True:
            event = await subscription.queue.get()
            await state_store.apply_update(event.payload, source=event.source)
    finally:
        subscription.close()


async def _publish_ui_message(runtime: RuntimeHandle, *, screen: str, message: str, assistant_source: str = "", transcript_text: str | None = None, report: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {
        "screen": screen,
        "message": message,
        "assistant_source": assistant_source,
    }
    if transcript_text is not None:
        payload["transcript_text"] = transcript_text
    if report is not None:
        payload["report"] = report
    await runtime.bus.publish(Event(topic=Topics.UI_UPDATE, source="web", payload=payload))


async def _wait_for_camera_release(context: WebAppContext, *, timeout_seconds: float = 3.0) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    snapshot: dict[str, Any] = {}
    released = False

    while True:
        snapshot = await context.state_store.get_snapshot()
        worker_statuses = snapshot.get("worker_statuses")
        if isinstance(worker_statuses, dict):
            vision_status = worker_statuses.get("vision_worker")
            camera_status = worker_statuses.get("camera")
            vision_available = bool(vision_status.get("available")) if isinstance(vision_status, dict) else False
            camera_available = bool(camera_status.get("available")) if isinstance(camera_status, dict) else False
            if not vision_available and not camera_available:
                released = True
                break

        if asyncio.get_running_loop().time() >= deadline:
            break
        await asyncio.sleep(0.05)

    return {
        "released": released,
        "worker_statuses": snapshot.get("worker_statuses") if isinstance(snapshot, dict) else {},
    }


async def _handle_assistant_text(context: WebAppContext, text: str, *, source: str) -> AssistantDecision:
    text = normalize_user_utterance(text)
    lowered = " ".join(text.strip().lower().split())
    if any(
        marker in lowered
        for marker in (
            "как я выгляжу",
            "как я сегодня выгляжу",
            "оцени мой внешний вид",
            "оцени мою внешность",
            "посмотри на меня",
        )
    ):
        decision = AssistantDecision(
            command="analyze_appearance",
            reply="Сейчас посмотрю на кадр и дам короткий комментарий.",
            backend_name="визуальный анализ",
        )
        await _publish_ui_message(
            context.runtime,
            screen="assistant",
            message=decision.reply,
            assistant_source="визуальный анализ",
        )
        return decision

    if detect_camera_vision_request(text):
        decision = AssistantDecision(
            command="camera_vision_query",
            reply="Сейчас посмотрю на камеру и расскажу что вижу.",
            backend_name="vision:камера",
        )
        await _publish_ui_message(
            context.runtime,
            screen="assistant",
            message=decision.reply,
            assistant_source="vision:камера",
        )
        return decision

    if any(marker in lowered for marker in ("начать скрининг", "запусти скрининг", "start screening")):
        decision = AssistantDecision(
            command="start_screening",
            reply="Запускаю скрининг.",
            backend_name="скрининг",
        )
        await context.runtime.bus.publish(
            Event(
                topic=Topics.AI_COMMAND,
                source=source,
                payload={
                    "command": "start_screening",
                    "raw_intent": text,
                    "reply": decision.reply,
                    "backend": decision.backend_name,
                },
            )
        )
        return decision

    decision = await context.assistant_backend.decide(text)
    if decision.command == "start_screening":
        await context.runtime.bus.publish(
            Event(
                topic=Topics.AI_COMMAND,
                source=source,
                payload={
                    "command": "start_screening",
                    "raw_intent": text,
                    "reply": decision.reply,
                    "backend": decision.backend_name,
                },
            )
        )
        return decision

    if decision.command == "analyze_appearance":
        await _publish_ui_message(
            context.runtime,
            screen="assistant",
            message=decision.reply,
            assistant_source="визуальный анализ",
        )
        return decision

    if decision.command == "camera_vision_query":
        await _publish_ui_message(
            context.runtime,
            screen="assistant",
            message=decision.reply,
            assistant_source="vision:камера",
        )
        return decision

    await _publish_ui_message(
        context.runtime,
        screen="assistant",
        message=f"{decision.reply} [{decision.backend_name}]",
        assistant_source=source_label_for_backend(decision.backend_name),
    )
    return decision


async def _analyze_uploaded_image(context: WebAppContext, image_path: str) -> dict[str, Any]:
    await context.vision_worker.start()
    response = await context.vision_worker.request("analyze_image_file", {"image_path": image_path})
    if not response.ok:
        raise RuntimeError(response.error_message)

    result = dict(response.result, source_backend="vision_worker:web")
    frame_base64 = str(result.pop("frame_base64", "") or "").strip()
    if frame_base64:
        try:
            vision_description = await asyncio.to_thread(
                _call_ollama_vision_sync,
                context.settings,
                frame_base64,
            )
            vision_description = _sanitize_vision_description(vision_description)
            if vision_description:
                result["appearance_description"] = vision_description
        except Exception as exc:
            notes = str(result.get("notes") or "").strip()
            result["notes"] = f"{notes} Ollama Vision: {exc}".strip()

    reply_text = await context.appearance_composer.compose(result)
    if not _is_safe_russian_text(reply_text):
        result["appearance_description"] = ""
        reply_text = context.appearance_composer._build_template(result)
    report_payload = {
        "report_type": "appearance",
        "state": "completed",
        "compliment": reply_text,
        "observed": result.get("observed") or "",
        "suggestion": "Можно повторить анализ при другом освещении или под другим углом камеры.",
        "face_detected": result.get("face_detected"),
        "face_count": result.get("face_count"),
        "confidence": result.get("confidence"),
        "emotion": result.get("emotion") or "",
        "appearance_description": result.get("appearance_description") or "",
        "emotiefflib_available": result.get("emotiefflib_available"),
        "notes": result.get("notes") or "",
        "source_backend": result.get("source_backend") or "vision_worker:web",
    }

    await context.runtime.bus.publish(Event(topic=Topics.REPORT_DATA, source="web.appearance", payload=report_payload))
    await context.runtime.bus.publish(Event(topic=Topics.STORAGE_WRITE, source="web.appearance", payload=report_payload))
    await _publish_ui_message(
        context.runtime,
        screen="summary",
        message=reply_text,
        assistant_source="визуальный анализ",
        report=report_payload,
    )
    return {"reply": reply_text, "report": report_payload}


def _call_ollama_vision_sync(settings: Settings, image_base64: str) -> str:
    ollama_url = settings.ollama_base_url.rstrip("/")
    model = settings.ollama_vision_model or settings.ollama_model
    payload = {
        "model": model,
        "prompt": (
            "Опиши внешность человека на фото кратко и тактично, 2-3 предложениями на русском. "
            "Укажи общее впечатление, выражение лица и заметные детали кадра, если они различимы. "
            "Не ставь диагнозы и не перечисляй технические поля."
        ),
        "images": [image_base64],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 140},
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{ollama_url}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with exclusive_gpu_task_sync("ollama"):
            with request.urlopen(req, timeout=settings.ollama_timeout_seconds) as resp:
                raw_body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {error_body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Ollama недоступен: {exc.reason}") from exc

    parsed = json.loads(raw_body)
    if "error" in parsed:
        raise RuntimeError(f"Ollama: {parsed['error']}")
    return str(parsed.get("response", "")).strip()


def _sanitize_vision_description(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""

    lowered = cleaned.lower()
    blocked_markers = (
        "i am a large language model",
        "cannot generate images",
        "не могу генерировать изображения",
        "disclaimer:",
        "эмоция:",
    )
    if any(marker in lowered for marker in blocked_markers):
        return ""
    if len(cleaned) < 28:
        return ""
    if not _is_safe_russian_text(cleaned):
        return ""
    return cleaned


def _is_mostly_cyrillic_text(text: str) -> bool:
    letters = [ch for ch in str(text or "") if ch.isalpha()]
    if not letters:
        return False
    cyrillic = sum(1 for ch in letters if "\u0400" <= ch <= "\u04ff")
    return cyrillic / len(letters) >= 0.6


def _is_safe_russian_text(
    text: str,
    *,
    min_cyrillic_ratio: float = 0.82,
    max_foreign_tokens: int = 2,
) -> bool:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return False

    letters = [ch for ch in cleaned if ch.isalpha()]
    if not letters:
        return False

    cyrillic_letters = sum(1 for ch in letters if "\u0400" <= ch <= "\u04ff")
    if cyrillic_letters / len(letters) < min_cyrillic_ratio:
        return False

    foreign_tokens = 0
    for token in re.findall(r"[\w'-]+", cleaned, flags=re.UNICODE):
        token_letters = [ch for ch in token if ch.isalpha()]
        if len(token_letters) < 2:
            continue

        has_cyrillic = any("\u0400" <= ch <= "\u04ff" for ch in token_letters)
        has_foreign = any(not ("\u0400" <= ch <= "\u04ff") for ch in token_letters)
        if has_cyrillic and has_foreign:
            return False
        if has_foreign:
            foreign_tokens += 1
            if foreign_tokens > max_foreign_tokens:
                return False

    return True


async def _transcribe_uploaded_audio(context: WebAppContext, audio_path: str) -> dict[str, Any]:
    await context.speech_worker.start()
    # Use a generous timeout: first call may need to load the Whisper model
    transcribe_timeout = max(context.settings.worker_request_timeout_seconds, 120.0)
    payload = {
        "audio_path": audio_path,
        "model_name": context.settings.stt_model_name,
        "language": context.settings.stt_language,
        "device": context.settings.stt_device,
        "compute_type": context.settings.stt_compute_type,
        "beam_size": context.settings.stt_beam_size,
        "best_of": context.settings.stt_best_of,
        "vad_filter": context.settings.stt_vad_filter,
        "hotwords": context.settings.stt_hotwords,
    }
    if context.settings.stt_device == "cpu":
        response = await context.speech_worker.request(
            "transcribe_audio_file",
            payload,
            timeout=transcribe_timeout,
        )
    else:
        async with exclusive_gpu_task("stt"):
            response = await context.speech_worker.request(
                "transcribe_audio_file",
                payload,
                timeout=transcribe_timeout,
            )
    if not response.ok:
        raise RuntimeError(response.error_message)
    return response.result


async def _answer_camera_vision_query(
    context: WebAppContext,
    utterance: str,
    image_base64: str,
) -> dict[str, Any]:
    """Send a camera frame + user question to the Ollama vision model."""
    from neuro_mirror.plugins.ai_assistant.backends import OllamaAssistantBackend

    backend = context.assistant_backend
    if not isinstance(backend, OllamaAssistantBackend):
        return {
            "reply": "Vision-запросы доступны только с Ollama бэкендом.",
            "backend": "unavailable",
        }

    vision_model = context.settings.ollama_vision_model or context.settings.ollama_model
    decision = await backend.answer_vision_question(
        utterance,
        image_base64,
        vision_model=vision_model,
    )
    if decision.reply and not _is_mostly_cyrillic_text(decision.reply):
        text_model = (
            backend._resolved_model_cache
            or await asyncio.to_thread(backend._resolve_model_name_sync)
        )
        translated_reply = await asyncio.to_thread(
            backend._translate_vision_response_to_russian_sync,
            text_model,
            utterance,
            decision.reply,
        )
        if translated_reply:
            decision = AssistantDecision(
                command=decision.command,
                reply=translated_reply,
                backend_name=decision.backend_name,
                raw_response=decision.raw_response,
            )

    await _publish_ui_message(
        context.runtime,
        screen="assistant",
        message=decision.reply,
        assistant_source="vision:камера",
    )
    return {
        "reply": decision.reply,
        "backend": decision.backend_name,
    }


async def _synthesize_tts(context: WebAppContext, text: str) -> bytes:
    communicate = edge_tts.Communicate(text=text, voice=context.settings.tts_voice, rate=context.settings.tts_rate)
    chunks: list[bytes] = []
    try:
        async for item in communicate.stream():
            if item["type"] == "audio":
                chunks.append(item["data"])
    except Exception as exc:
        raise RuntimeError(f"TTS недоступен: {exc}") from exc
    return b"".join(chunks)


def _is_low_confidence_transcript(result: dict[str, Any], transcript: str) -> bool:
    if not transcript.strip():
        return True

    confidence_score = result.get("confidence_score")
    average_logprob = result.get("average_logprob")
    max_no_speech_prob = result.get("max_no_speech_prob")

    if isinstance(confidence_score, (int, float)) and float(confidence_score) < 0.45:
        return True
    if isinstance(average_logprob, (int, float)) and float(average_logprob) < -1.4:
        return True
    if isinstance(max_no_speech_prob, (int, float)) and float(max_no_speech_prob) > 0.75:
        return True
    return False


def create_app() -> FastAPI:
    static_dir = Path(__file__).resolve().parent / "static"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = Settings.from_env()
        runtime = create_runtime(
            settings,
            stop_event=asyncio.Event(),
            include_ai_plugin=False,
        )
        state_store = WebStateStore()
        assistant_backend = build_assistant_backend(settings)
        appearance_composer = AppearanceResponseComposer(
            enabled=settings.enable_ai_assistant,
            ai_backend=settings.ai_backend,
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            ollama_vision_model=settings.ollama_vision_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
        vision_worker = WorkerClient(
            name="vision_worker_web_api",
            python_executable=settings.vision_worker_python,
            script_path=settings.vision_worker_script,
            request_timeout_seconds=settings.worker_request_timeout_seconds,
        )
        speech_worker = WorkerClient(
            name="speech_worker_web_api",
            python_executable=settings.speech_worker_python,
            script_path=settings.speech_worker_script,
            request_timeout_seconds=settings.worker_request_timeout_seconds,
        )

        await runtime.start()
        ui_subscription_task = asyncio.create_task(_consume_ui_updates(runtime, state_store), name="web-ui-state")
        await runtime.bootstrap(auto_start_override=False)

        # Pre-warm speech worker so the first transcription doesn't timeout
        try:
            await speech_worker.start()
            warmup_payload = {
                "model_name": settings.stt_model_name,
                "device": settings.stt_device,
                "compute_type": settings.stt_compute_type,
            }
            if settings.stt_device == "cpu":
                await asyncio.wait_for(
                    speech_worker.request("warmup_model", warmup_payload),
                    timeout=180.0,
                )
            else:
                async with exclusive_gpu_task("stt"):
                    await asyncio.wait_for(
                        speech_worker.request("warmup_model", warmup_payload),
                        timeout=180.0,
                    )
        except Exception as exc:
            logging.getLogger("neuro_mirror.web").warning("Speech worker warmup failed: %s", exc)

        app.state.context = WebAppContext(
            settings=settings,
            runtime=runtime,
            state_store=state_store,
            assistant_backend=assistant_backend,
            appearance_composer=appearance_composer,
            vision_worker=vision_worker,
            speech_worker=speech_worker,
            ui_subscription_task=ui_subscription_task,
        )
        try:
            yield
        finally:
            ui_subscription_task.cancel()
            try:
                await ui_subscription_task
            except asyncio.CancelledError:
                pass
            await vision_worker.stop()
            await speech_worker.stop()
            await runtime.stop()

    app = FastAPI(title="Neuro Mirror Web", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def root() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/state")
    async def get_state() -> JSONResponse:
        context: WebAppContext = app.state.context
        return JSONResponse(await context.state_store.get_snapshot())

    @app.get("/api/config")
    async def get_config() -> JSONResponse:
        context: WebAppContext = app.state.context
        return JSONResponse(
            {
                "assistant_enabled": context.settings.enable_ai_assistant,
                "tts_voice": context.settings.tts_voice,
                "live2d_model_url": context.settings.web_live2d_model_url,
                "live2d_cubism_core_url": context.settings.web_live2d_cubism_core_url,
                "weather_source_label": context.runtime.weather_source_label,
                "assistant_backend_label": context.runtime.assistant_backend_label,
            }
        )

    @app.post("/api/assistant/message")
    async def assistant_message(payload: AssistantMessageIn) -> JSONResponse:
        context: WebAppContext = app.state.context
        decision = await _handle_assistant_text(context, payload.text.strip(), source="web.assistant")
        return JSONResponse(
            {
                "accepted": True,
                "command": decision.command,
                "reply": decision.reply,
                "backend": decision.backend_name,
            }
        )

    @app.post("/api/actions/{action}")
    async def ui_action(action: str) -> JSONResponse:
        context: WebAppContext = app.state.context
        await context.runtime.bus.publish(
            Event(topic=Topics.UI_ACTION, source="web.action", payload={"action": action})
        )
        if action == "release_camera":
            release_result = await _wait_for_camera_release(context)
            status_code = 200 if release_result["released"] else 409
            return JSONResponse(
                {
                    "accepted": release_result["released"],
                    "action": action,
                    "released": release_result["released"],
                    "worker_statuses": release_result["worker_statuses"] or {},
                },
                status_code=status_code,
            )
        return JSONResponse({"accepted": True, "action": action})

    @app.post("/api/appearance/analyze")
    async def appearance_analyze(image: UploadFile = File(...)) -> JSONResponse:
        context: WebAppContext = app.state.context
        await _publish_ui_message(
            context.runtime,
            screen="assistant",
            message="Сейчас оцениваю внешний вид по кадру. Это может занять несколько секунд.",
            assistant_source="визуальный анализ",
        )
        suffix = Path(image.filename or "frame.jpg").suffix or ".jpg"
        fd, temp_path = tempfile.mkstemp(prefix="neuro_mirror_frame_", suffix=suffix)
        os.close(fd)
        try:
            with open(temp_path, "wb") as output_file:
                output_file.write(await image.read())
            result = await _analyze_uploaded_image(context, temp_path)
            return JSONResponse(result)
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass

    @app.post("/api/camera/vision")
    async def camera_vision(payload: CameraVisionRequest) -> JSONResponse:
        """Send a camera frame + question to the Ollama vision model."""
        context: WebAppContext = app.state.context
        if not payload.text.strip():
            raise HTTPException(status_code=400, detail="text is required")
        if not payload.image_base64.strip():
            raise HTTPException(status_code=400, detail="image_base64 is required")

        await _publish_ui_message(
            context.runtime,
            screen="assistant",
            message="Анализирую кадр с камеры...",
            assistant_source="vision:камера",
        )

        try:
            result = await _answer_camera_vision_query(
                context,
                payload.text.strip(),
                payload.image_base64.strip(),
            )
            return JSONResponse(result)
        except Exception as exc:
            message = f"Ошибка vision-запроса: {exc}"
            await _publish_ui_message(context.runtime, screen="assistant", message=message, assistant_source="vision:камера")
            raise HTTPException(status_code=500, detail=message) from exc

    @app.post("/api/speech/transcribe")
    async def speech_transcribe(audio: UploadFile = File(...)) -> JSONResponse:
        context: WebAppContext = app.state.context
        suffix = Path(audio.filename or "voice.webm").suffix or ".webm"
        fd, temp_path = tempfile.mkstemp(prefix="neuro_mirror_voice_", suffix=suffix)
        os.close(fd)
        try:
            with open(temp_path, "wb") as output_file:
                output_file.write(await audio.read())
            try:
                result = await _transcribe_uploaded_audio(context, temp_path)
            except (TimeoutError, asyncio.TimeoutError):
                message = "Распознавание заняло слишком долго. Модель ещё загружается — попробуйте через 30 секунд."
                await _publish_ui_message(context.runtime, screen="assistant", message=message, transcript_text="")
                return JSONResponse({"accepted": False, "transcript": "", "message": message})
            except RuntimeError as exc:
                message = f"Ошибка распознавания речи: {exc}"
                await _publish_ui_message(context.runtime, screen="assistant", message=message, transcript_text="")
                return JSONResponse({"accepted": False, "transcript": "", "message": message})
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass

        raw_transcript = str(result.get("transcript") or "").strip()
        if not raw_transcript:
            message = str(result.get("notes") or "Речь не распознана.")
            await _publish_ui_message(context.runtime, screen="assistant", message=message, transcript_text="")
            return JSONResponse({"accepted": False, "transcript": "", "message": message})

        transcript = normalize_user_utterance(raw_transcript) or raw_transcript

        if _is_low_confidence_transcript(result, raw_transcript):
            message = "Ещё раз сформулируйте вопрос: речь распознана неуверенно."
            await _publish_ui_message(context.runtime, screen="assistant", message=message, transcript_text=transcript)
            return JSONResponse(
                {
                    "accepted": False,
                    "transcript": transcript,
                    "raw_transcript": raw_transcript,
                    "message": message,
                }
            )

        await _publish_ui_message(
            context.runtime,
            screen="assistant",
            message=f"Распознан текст: {transcript}",
            transcript_text=transcript,
        )
        decision = await _handle_assistant_text(context, transcript, source="web.speech")
        return JSONResponse(
            {
                "accepted": True,
                "transcript": transcript,
                "raw_transcript": raw_transcript,
                "notes": str(result.get("notes") or ""),
                "stt_device": str(result.get("device") or ""),
                "stt_model": str(result.get("model_name") or context.settings.stt_model_name),
                "stt_compute_type": str(result.get("compute_type") or ""),
                "command": decision.command,
                "reply": decision.reply,
                "backend": decision.backend_name,
            }
        )

    @app.post("/api/tts/speak")
    async def tts_speak(payload: TTSRequest) -> StreamingResponse:
        context: WebAppContext = app.state.context
        if not payload.text.strip():
            raise HTTPException(status_code=400, detail="text is required")

        async def _stream_tts():
            communicate = edge_tts.Communicate(
                text=payload.text.strip(),
                voice=context.settings.tts_voice,
                rate=context.settings.tts_rate,
            )
            async for item in communicate.stream():
                if item["type"] == "audio":
                    yield item["data"]

        return StreamingResponse(
            _stream_tts(),
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-cache"},
        )

    @app.websocket("/ws/app")
    async def websocket_app(websocket: WebSocket) -> None:
        context: WebAppContext = app.state.context
        await context.state_store.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await context.state_store.disconnect(websocket)

    return app
