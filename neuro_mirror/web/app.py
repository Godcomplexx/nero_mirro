"""Thin HTTP/WebSocket transport layer.

All business logic lives in plugins. This module only:
- accepts HTTP / WebSocket requests
- publishes events to the EventBus (using ``bus.request`` for request-reply)
- returns results from the plugins or from ``WebUIPlugin.state_store``
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import edge_tts
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from neuro_mirror.app.runtime import RuntimeHandle, create_runtime
from neuro_mirror.core.settings import Settings
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.ui.web_plugin import WebUIPlugin, WebUIStateStore

_log = logging.getLogger("neuro_mirror.web")


# ---- Pydantic request models ----

class AssistantMessageIn(BaseModel):
    text: str


class CameraVisionRequest(BaseModel):
    text: str
    image_base64: str


class DeviceSelectionIn(BaseModel):
    camera_id: str = ""
    microphone_id: str = ""


class TTSRequest(BaseModel):
    text: str


# ---- Minimal application context ----

@dataclass(slots=True)
class WebAppContext:
    settings: Settings
    runtime: RuntimeHandle
    state_store: WebUIStateStore
    web_ui: WebUIPlugin


# ---- Helpers ----

async def _wait_for_camera_release(
    state_store: WebUIStateStore,
    *,
    timeout_seconds: float = 3.0,
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    snapshot: dict[str, Any] = {}
    released = False

    while True:
        snapshot = await state_store.get_snapshot()
        worker_statuses = snapshot.get("worker_statuses")
        if isinstance(worker_statuses, dict):
            camera_status = worker_statuses.get("camera")
            camera_available = bool(camera_status.get("available")) if isinstance(camera_status, dict) else False
            if not camera_available:
                released = True
                break

        if asyncio.get_running_loop().time() >= deadline:
            break
        await asyncio.sleep(0.05)

    return {
        "released": released,
        "worker_statuses": snapshot.get("worker_statuses") if isinstance(snapshot, dict) else {},
    }


# ---- Application factory ----

def create_app() -> FastAPI:
    static_dir = Path(__file__).resolve().parent / "static"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = Settings.from_env()

        # create_runtime now includes AI plugin with request-reply support
        runtime = create_runtime(
            settings,
            stop_event=asyncio.Event(),
            include_ai_plugin=True,
        )
        web_ui = WebUIPlugin(runtime.bus)
        runtime.plugin_manager.register(web_ui)

        await runtime.start()
        await runtime.bootstrap(auto_start_override=False)

        app.state.context = WebAppContext(
            settings=settings,
            runtime=runtime,
            state_store=web_ui.state_store,
            web_ui=web_ui,
        )
        try:
            yield
        finally:
            await runtime.stop()

    app = FastAPI(title="Neuro Mirror Web", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # ---- Read-only endpoints ----

    @app.get("/")
    async def root() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/state")
    async def get_state() -> JSONResponse:
        ctx: WebAppContext = app.state.context
        return JSONResponse(await ctx.state_store.get_snapshot())

    @app.get("/api/config")
    async def get_config() -> JSONResponse:
        ctx: WebAppContext = app.state.context
        return JSONResponse(
            {
                "assistant_enabled": ctx.settings.enable_ai_assistant,
                "tts_voice": ctx.settings.tts_voice,
                "live2d_model_url": ctx.settings.web_live2d_model_url,
                "live2d_cubism_core_url": ctx.settings.web_live2d_cubism_core_url,
                "weather_source_label": ctx.runtime.weather_source_label,
                "assistant_backend_label": ctx.runtime.assistant_backend_label,
            }
        )

    @app.get("/api/devices")
    async def get_devices() -> JSONResponse:
        ctx: WebAppContext = app.state.context
        snapshot = await ctx.state_store.get_snapshot()
        return JSONResponse(
            {
                "device_catalog": snapshot.get("device_catalog") or {"cameras": [], "microphones": []},
                "selected_devices": snapshot.get("selected_devices") or {},
                "device_errors": snapshot.get("device_errors") or [],
            }
        )

    # ---- Action endpoints (fire-and-forget via EventBus) ----

    @app.post("/api/devices/select")
    async def select_devices(payload: DeviceSelectionIn) -> JSONResponse:
        ctx: WebAppContext = app.state.context
        await ctx.runtime.bus.publish(
            Event(
                topic=Topics.UI_DEVICE_SELECTED,
                source="web.devices",
                payload={
                    "camera_id": payload.camera_id.strip(),
                    "microphone_id": payload.microphone_id.strip(),
                },
            )
        )
        return JSONResponse({"accepted": True})

    @app.post("/api/actions/{action}")
    async def ui_action(action: str) -> JSONResponse:
        ctx: WebAppContext = app.state.context
        await ctx.runtime.bus.publish(
            Event(topic=Topics.UI_ACTION, source="web.action", payload={"action": action})
        )
        if action == "release_camera":
            release_result = await _wait_for_camera_release(ctx.state_store)
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

    # ---- Request-reply endpoints (business logic delegated to plugins) ----

    @app.post("/api/assistant/message")
    async def assistant_message(payload: AssistantMessageIn) -> JSONResponse:
        ctx: WebAppContext = app.state.context
        try:
            result = await ctx.runtime.bus.request(
                Event(
                    topic=Topics.REQ_ASSISTANT_MESSAGE,
                    source="web.assistant",
                    payload={"text": payload.text.strip(), "source": "web.assistant"},
                ),
                timeout=ctx.settings.ollama_timeout_seconds + 10,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Ассистент не ответил вовремя.")

        return JSONResponse(
            {
                "accepted": result.get("accepted", True),
                "command": result.get("command"),
                "reply": result.get("reply", ""),
                "backend": result.get("backend", ""),
            }
        )

    @app.post("/api/appearance/analyze")
    async def appearance_analyze(image: UploadFile = File(...)) -> JSONResponse:
        ctx: WebAppContext = app.state.context

        # Notify UI that analysis is starting
        await ctx.runtime.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source="web",
                payload={
                    "screen": "assistant",
                    "message": "Сейчас оцениваю внешний вид по кадру. Это может занять несколько секунд.",
                    "assistant_source": "визуальный анализ",
                },
            )
        )

        suffix = Path(image.filename or "frame.jpg").suffix or ".jpg"
        fd, temp_path = tempfile.mkstemp(prefix="neuro_mirror_frame_", suffix=suffix)
        os.close(fd)
        try:
            with open(temp_path, "wb") as output_file:
                output_file.write(await image.read())

            result = await ctx.runtime.bus.request(
                Event(
                    topic=Topics.REQ_APPEARANCE_ANALYZE,
                    source="web.appearance",
                    payload={"image_path": temp_path},
                ),
                timeout=ctx.settings.ollama_timeout_seconds + 30,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Анализ внешности занял слишком долго.")
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        return JSONResponse({"reply": result.get("reply", ""), "report": result.get("report")})

    @app.post("/api/camera/vision")
    async def camera_vision(payload: CameraVisionRequest) -> JSONResponse:
        ctx: WebAppContext = app.state.context
        if not payload.text.strip():
            raise HTTPException(status_code=400, detail="text is required")
        if not payload.image_base64.strip():
            raise HTTPException(status_code=400, detail="image_base64 is required")

        try:
            result = await ctx.runtime.bus.request(
                Event(
                    topic=Topics.REQ_CAMERA_VISION,
                    source="web.vision",
                    payload={
                        "text": payload.text.strip(),
                        "image_base64": payload.image_base64.strip(),
                    },
                ),
                timeout=ctx.settings.ollama_timeout_seconds + 15,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Vision-запрос не завершился вовремя.")

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        return JSONResponse({"reply": result.get("reply", ""), "backend": result.get("backend", "")})

    @app.post("/api/speech/transcribe")
    async def speech_transcribe(audio: UploadFile = File(...)) -> JSONResponse:
        ctx: WebAppContext = app.state.context
        suffix = Path(audio.filename or "voice.webm").suffix or ".webm"
        fd, temp_path = tempfile.mkstemp(prefix="neuro_mirror_voice_", suffix=suffix)
        os.close(fd)
        try:
            with open(temp_path, "wb") as output_file:
                output_file.write(await audio.read())

            # Step 1: transcribe via SpeechWorkerPlugin
            transcribe_timeout = max(ctx.settings.worker_request_timeout_seconds, 120.0)
            try:
                stt_result = await ctx.runtime.bus.request(
                    Event(
                        topic=Topics.REQ_SPEECH_TRANSCRIBE,
                        source="web.speech",
                        payload={"audio_path": temp_path},
                    ),
                    timeout=transcribe_timeout + 10,
                )
            except asyncio.TimeoutError:
                message = "Распознавание заняло слишком долго. Модель ещё загружается — попробуйте через 30 секунд."
                return JSONResponse({"accepted": False, "transcript": "", "message": message})
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass

        if not stt_result.get("accepted"):
            return JSONResponse({
                "accepted": False,
                "transcript": stt_result.get("transcript", ""),
                "raw_transcript": stt_result.get("raw_transcript", ""),
                "message": stt_result.get("message", ""),
            })

        transcript = stt_result.get("transcript", "")

        # Step 2: feed transcript to AIAssistantPlugin
        try:
            assistant_result = await ctx.runtime.bus.request(
                Event(
                    topic=Topics.REQ_ASSISTANT_MESSAGE,
                    source="web.speech",
                    payload={"text": transcript, "source": "web.speech"},
                ),
                timeout=ctx.settings.ollama_timeout_seconds + 10,
            )
        except asyncio.TimeoutError:
            assistant_result = {"command": None, "reply": "", "backend": "timeout"}

        return JSONResponse(
            {
                "accepted": True,
                "transcript": transcript,
                "raw_transcript": stt_result.get("raw_transcript", ""),
                "notes": stt_result.get("notes", ""),
                "stt_device": stt_result.get("stt_device", ""),
                "stt_model": stt_result.get("stt_model", ""),
                "stt_compute_type": stt_result.get("stt_compute_type", ""),
                "command": assistant_result.get("command"),
                "reply": assistant_result.get("reply", ""),
                "backend": assistant_result.get("backend", ""),
            }
        )

    # ---- TTS (pure transport, no business logic) ----

    @app.post("/api/tts/speak")
    async def tts_speak(payload: TTSRequest) -> StreamingResponse:
        ctx: WebAppContext = app.state.context
        if not payload.text.strip():
            raise HTTPException(status_code=400, detail="text is required")

        async def _stream_tts():
            communicate = edge_tts.Communicate(
                text=payload.text.strip(),
                voice=ctx.settings.tts_voice,
                rate=ctx.settings.tts_rate,
            )
            async for item in communicate.stream():
                if item["type"] == "audio":
                    yield item["data"]

        return StreamingResponse(
            _stream_tts(),
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-cache"},
        )

    # ---- WebSocket ----

    @app.websocket("/ws/app")
    async def websocket_app(websocket: WebSocket) -> None:
        ctx: WebAppContext = app.state.context
        await ctx.state_store.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await ctx.state_store.disconnect(websocket)

    return app
