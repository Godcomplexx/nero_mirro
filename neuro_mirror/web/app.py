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
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from neuro_mirror.app.runtime import RuntimeHandle, create_runtime
from neuro_mirror.core.settings import Settings
from neuro_mirror.core.user_profiles import CONSENT_TEXT, PRESET_AVATARS, UserProfileStore
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.ui.web_plugin import WebUIPlugin, WebUIStateStore
from neuro_mirror.plugins.user_progress.plugin import UserProgressPlugin
from neuro_mirror.version import APP_VERSION, SCENARIO_VERSIONS

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


class UserCreateIn(BaseModel):
    name: str
    consent: bool = False
    avatar_preset: str = ""
    photo_base64: str = ""


class ClientLogIn(BaseModel):
    level: str = "info"
    message: str = ""


class SessionFrameIn(BaseModel):
    image_base64: str


# ---- Minimal application context ----

@dataclass(slots=True)
class WebAppContext:
    settings: Settings
    runtime: RuntimeHandle
    state_store: WebUIStateStore
    web_ui: WebUIPlugin
    user_store: UserProfileStore


# ---- Helpers ----

async def _wait_for_camera_release(
    state_store: WebUIStateStore,
    *,
    timeout_seconds: float = 8.0,
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

        user_store = UserProfileStore()
        runtime.plugin_manager.register(
            UserProgressPlugin(runtime.bus, user_store=user_store)
        )

        await runtime.start()
        await runtime.bootstrap(auto_start_override=False)

        app.state.context = WebAppContext(
            settings=settings,
            runtime=runtime,
            state_store=web_ui.state_store,
            web_ui=web_ui,
            user_store=user_store,
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
                "app_version": APP_VERSION,
                "scenario_versions": SCENARIO_VERSIONS,
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

    # ---- User profiles (личный кабинет) ----

    def _serialize_user(user: dict[str, Any]) -> dict[str, Any]:
        avatar = user.get("avatar") or {}
        if avatar.get("type") == "photo":
            avatar_url = f"/api/users/{user['id']}/avatar"
        else:
            preset = avatar.get("value") or PRESET_AVATARS[0]
            avatar_url = f"/static/assets/avatars/{preset}.svg"
        return {
            "id": user.get("id", ""),
            "name": user.get("name", ""),
            "avatar_url": avatar_url,
            "created_at": user.get("created_at", ""),
            "progress": user.get("progress") or {},
        }

    @app.get("/api/users")
    async def list_users() -> JSONResponse:
        ctx: WebAppContext = app.state.context
        active = ctx.user_store.get_active_user()
        return JSONResponse(
            {
                "users": [_serialize_user(user) for user in ctx.user_store.list_users()],
                "active_user": _serialize_user(active) if active else None,
                "consent_text": CONSENT_TEXT,
                "avatar_presets": [
                    {"id": preset, "url": f"/static/assets/avatars/{preset}.svg"}
                    for preset in PRESET_AVATARS
                ],
            }
        )

    @app.post("/api/users")
    async def create_user(payload: UserCreateIn) -> JSONResponse:
        ctx: WebAppContext = app.state.context
        try:
            user = ctx.user_store.create_user(
                payload.name,
                consent=payload.consent,
                avatar_preset=payload.avatar_preset.strip(),
                photo_base64=payload.photo_base64,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return JSONResponse({"user": _serialize_user(user)}, status_code=201)

    def _next_step_suggestion(user: dict[str, Any]) -> str:
        """Assistant onboarding: suggest the next step from progress flags."""
        progress = user.get("progress") or {}
        if not progress.get("screening_done"):
            return "Давайте начнём с быстрой диагностики — нажмите «Проверка» внизу экрана."
        if not progress.get("moca_done"):
            return "Предлагаю пройти голосовой тест MoCA — нажмите «Тест MoCA» внизу экрана."
        if progress.get("training_course"):
            return (
                f"Продолжим тренировки по курсу «{progress['training_course']}»? "
                "Откройте «Меню» → «Тренировка»."
            )
        return (
            "Все базовые проверки пройдены. Можно повторить проверку "
            "или посмотреть «Мои результаты»."
        )

    @app.post("/api/users/{user_id}/select")
    async def select_user(user_id: str) -> JSONResponse:
        ctx: WebAppContext = app.state.context
        try:
            user = ctx.user_store.select_user(user_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Пользователь не найден.")

        serialized = _serialize_user(user)
        await ctx.runtime.bus.publish(
            Event(
                topic=Topics.USER_SELECTED,
                source="web.users",
                payload={"user_id": user["id"], "user_name": user["name"]},
            )
        )
        greeting = f"Здравствуйте, {user['name']}! {_next_step_suggestion(user)}"
        await ctx.state_store.apply_update(
            {
                "screen": "assistant",
                "active_user": serialized,
                "message": greeting,
                "assistant_source": "ассистент",
            },
            source="web.users",
        )
        return JSONResponse({"user": serialized})

    @app.get("/api/results")
    async def user_results() -> JSONResponse:
        """Stored screening history for the active user (newest first)."""
        ctx: WebAppContext = app.state.context
        active = ctx.user_store.get_active_user()
        if active is None:
            raise HTTPException(status_code=400, detail="Сначала выберите пользователя.")
        try:
            reply = await ctx.runtime.bus.request(
                Event(
                    topic=Topics.REQ_STORAGE_QUERY,
                    source="web.results",
                    payload={"user_id": active["id"]},
                ),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Хранилище не ответило.")

        items = reply.get("items") or []
        items.sort(key=lambda item: str(item.get("stored_at") or ""), reverse=True)
        return JSONResponse({"user": _serialize_user(active), "items": items})

    # ---- Session conditions check (ТЗ 6.3.2): face / lighting / distance ----

    @app.post("/api/session/check-face")
    async def session_check_face(payload: SessionFrameIn) -> JSONResponse:
        import base64 as _base64

        from neuro_mirror.screening.session_check import analyze_frame_conditions

        stripped = payload.image_base64.split(",", 1)[-1].strip()
        try:
            jpeg_bytes = _base64.b64decode(stripped, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="Некорректное изображение.")
        if len(jpeg_bytes) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Кадр слишком большой.")

        result = await asyncio.to_thread(analyze_frame_conditions, jpeg_bytes)
        return JSONResponse(result)

    # ---- Client-side log relay (browser errors go to the server terminal) ----

    _client_log = logging.getLogger("neuro_mirror.web.client")

    @app.post("/api/client-log")
    async def client_log(payload: ClientLogIn) -> JSONResponse:
        message = payload.message.strip()[:2000]
        if message:
            level = payload.level.lower()
            if level == "error":
                _client_log.error("[browser] %s", message)
            elif level in ("warn", "warning"):
                _client_log.warning("[browser] %s", message)
            else:
                _client_log.info("[browser] %s", message)
        return JSONResponse({"accepted": True})

    @app.get("/api/users/{user_id}/avatar")
    async def user_avatar(user_id: str) -> FileResponse:
        ctx: WebAppContext = app.state.context
        path = ctx.user_store.avatar_photo_path(user_id)
        if path is None:
            raise HTTPException(status_code=404, detail="Аватар не найден.")
        return FileResponse(path, media_type="image/png")

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
    async def ui_action(action: str, request: Request) -> JSONResponse:
        ctx: WebAppContext = app.state.context
        event_payload: dict[str, Any] = {"action": action}
        if request.headers.get("content-type", "").lower().startswith("application/json"):
            try:
                body = await request.json()
            except Exception:
                body = None
            if isinstance(body, dict):
                event_payload.update(body)
        await ctx.runtime.bus.publish(
            Event(topic=Topics.UI_ACTION, source="web.action", payload=event_payload)
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
                timeout=max(ctx.settings.worker_request_timeout_seconds, ctx.settings.ollama_timeout_seconds + 90),
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

    @app.websocket("/ws/rppg")
    async def websocket_rppg(websocket: WebSocket) -> None:
        """Receive JPEG frames from browser camera, run rPPG, publish RPPG_RESULT.

        Query params:
          mode=screening  (default) — collect one window, run once, publish to EventBus, close
          mode=monitor    — sliding window: run rPPG every WINDOW_SEC, stream results back, repeat
          duration=N      — total monitor seconds (default 60, ignored in screening mode)
        """
        ctx: WebAppContext = app.state.context
        await websocket.accept()

        # Parse query params from the request scope
        qs: dict[str, str] = {}
        for pair in (websocket.scope.get("query_string") or b"").decode().split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                qs[k] = v
        mode = qs.get("mode", "screening")
        monitor_duration = max(10, min(300, int(qs.get("duration", "60"))))

        _log.info("[rppg_ws] connected mode=%s", mode)

        fps_target = 15.0
        window_seconds = ctx.settings.rppg_duration_seconds
        window_frames = int(window_seconds * fps_target)
        worker_script = str(Path(ctx.settings.vision_worker_script).resolve())

        def _run_rppg_on_frames(raw_frames: list[bytes], source: str) -> dict:
            import sys
            import importlib.util
            import cv2
            import numpy as np

            frames = []
            for raw in raw_frames:
                arr = np.frombuffer(raw, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    frames.append(frame)

            if not frames:
                return {
                    "heart_rate_bpm": None,
                    "heart_rate_status": "unavailable",
                    "heart_rate_algorithm": "",
                    "heart_rate_error": "Нет декодированных кадров.",
                    "face_detected": False,
                    "face_count": 0,
                    "screening_frame_count": 0,
                    "source_backend": source,
                }

            actual_fps = min(fps_target, len(frames) / max(window_seconds, 1.0))
            mod_name = "vision_worker_rppg"
            if mod_name not in sys.modules:
                spec = importlib.util.spec_from_file_location(mod_name, worker_script)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
            vw = sys.modules[mod_name]

            face_boxes = vw.detect_face_regions(frames[-1])
            rppg = vw.estimate_heart_rate_from_frames(frames, fps=actual_fps)
            return {
                **rppg,
                "analysis_type": "screening" if source == "browser_rppg" else "monitor",
                "face_detected": len(face_boxes) > 0,
                "face_count": len(face_boxes),
                "attention_score": 0.78 if face_boxes else 0.42,
                "gaze_stability": 0.72 if face_boxes else 0.0,
                "screening_frame_count": len(frames),
                "screening_fps": round(actual_fps, 2),
                "source_backend": source,
            }

        if mode == "monitor":
            # Sliding-window monitor: collect frames, run rPPG every window, send result, repeat
            ring: list[bytes] = []
            max_ring = window_frames * 2  # keep up to 2 windows in memory
            total_received = 0
            deadline = asyncio.get_event_loop().time() + monitor_duration
            next_analysis_at = window_frames  # run first analysis after one full window

            try:
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        data = await asyncio.wait_for(websocket.receive_bytes(), timeout=3.0)
                    except asyncio.TimeoutError:
                        break
                    if data:
                        ring.append(data)
                        if len(ring) > max_ring:
                            ring.pop(0)
                        total_received += 1

                    # Run analysis when we have enough frames for a full window
                    if total_received >= next_analysis_at and len(ring) >= window_frames:
                        window = list(ring[-window_frames:])
                        next_analysis_at = total_received + window_frames // 2  # overlap 50%
                        try:
                            result = await asyncio.to_thread(_run_rppg_on_frames, window, "browser_monitor")
                        except Exception as exc:
                            _log.warning("[rppg_ws] monitor rPPG error: %s", exc)
                            result = {"heart_rate_bpm": None, "heart_rate_status": "unavailable",
                                      "heart_rate_algorithm": "", "heart_rate_error": str(exc),
                                      "source_backend": "browser_monitor"}

                        _log.info("[rppg_ws] monitor result: bpm=%s status=%s",
                                  result.get("heart_rate_bpm"), result.get("heart_rate_status"))
                        # Monitor mode: only push HR widget update, never trigger screening
                        await ctx.runtime.bus.publish(
                            Event(topic=Topics.UI_UPDATE, source="web.rppg_monitor", payload={
                                "heart_rate_bpm": result.get("heart_rate_bpm"),
                                "heart_rate_status": result.get("heart_rate_status"),
                                "heart_rate_algorithm": result.get("heart_rate_algorithm", ""),
                            })
                        )
                        try:
                            await websocket.send_json({
                                "heart_rate_bpm": result.get("heart_rate_bpm"),
                                "heart_rate_status": result.get("heart_rate_status"),
                                "heart_rate_algorithm": result.get("heart_rate_algorithm", ""),
                            })
                        except Exception:
                            break
            except WebSocketDisconnect:
                pass

            _log.info("[rppg_ws] monitor session ended: total_frames=%d", total_received)
            try:
                await websocket.send_json({"done": True})
                await websocket.close()
            except Exception:
                pass

        else:
            # One-shot screening mode: collect one full window, run once, publish, close
            frame_bytes_list: list[bytes] = []
            try:
                while len(frame_bytes_list) < window_frames:
                    try:
                        data = await asyncio.wait_for(websocket.receive_bytes(), timeout=3.0)
                    except asyncio.TimeoutError:
                        break
                    if data:
                        frame_bytes_list.append(data)
                        await websocket.send_json({"received": len(frame_bytes_list), "total": window_frames})
            except WebSocketDisconnect:
                pass

            _log.info("[rppg_ws] collected %d frames, running rPPG", len(frame_bytes_list))

            try:
                result = await asyncio.to_thread(_run_rppg_on_frames, frame_bytes_list, "browser_rppg")
            except Exception as exc:
                _log.exception("[rppg_ws] rPPG failed: %s", exc)
                result = {"heart_rate_bpm": None, "heart_rate_status": "unavailable",
                          "heart_rate_algorithm": "", "heart_rate_error": str(exc),
                          "face_detected": False, "face_count": 0,
                          "screening_frame_count": len(frame_bytes_list),
                          "source_backend": "browser_rppg"}

            _log.info("[rppg_ws] result: status=%s bpm=%s frames=%s",
                      result.get("heart_rate_status"), result.get("heart_rate_bpm"),
                      result.get("screening_frame_count"))

            await ctx.runtime.bus.publish(
                Event(topic=Topics.RPPG_RESULT, source="web.rppg", payload=result)
            )

            try:
                await websocket.send_json({"done": True, "heart_rate_bpm": result.get("heart_rate_bpm"),
                                           "heart_rate_status": result.get("heart_rate_status")})
                await websocket.close()
            except Exception:
                pass

    return app
