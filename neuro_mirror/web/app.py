"""Thin HTTP/WebSocket transport layer.

All business logic lives in plugins. This module only:
- accepts HTTP / WebSocket requests
- publishes events to the EventBus (using ``bus.request`` for request-reply)
- returns results from the plugins or from ``WebUIPlugin.state_store``
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import (
    FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from neuro_mirror.app.runtime import RuntimeHandle, create_runtime
from neuro_mirror.core.dataset_store import DatasetCaptureError
from neuro_mirror.core.speech_synthesis import (
    SpeechSynthesisUnavailable,
    SpeechSynthesizer,
)
from neuro_mirror.core.settings import Settings
from neuro_mirror.core.user_profiles import (
    CONSENT_TEXT,
    CONSENT_TEXTS,
    KNOWN_AVATARS,
    PRESET_AVATARS,
    UserProfileStore,
)
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.games.registry import (
    all_game_definitions,
    game_asset_path,
    get_available_game_definition,
    implemented_game_codes,
)
from neuro_mirror.core.access_journal import (
    EXPORT_RESULTS,
    VIEW_RESULTS,
    AccessJournal,
)
from neuro_mirror.screening.san_survey import (
    MOMENTS,
    questionnaire as san_questionnaire,
    score_san,
)
from neuro_mirror.plugins.games.course_store import ITEM_DONE, CourseError
from neuro_mirror.screening.difficulty_policy import describe
from neuro_mirror.screening.training_course import (
    COURSE_SESSIONS,
    form_states,
    stage_for,
)
from neuro_mirror.screening.training_session import build_training_session
from neuro_mirror.plugins.ui.web_plugin import WebUIPlugin, WebUIStateStore
from neuro_mirror.plugins.user_progress.plugin import UserProgressPlugin
from neuro_mirror.version import APP_VERSION, SCENARIO_VERSIONS

_log = logging.getLogger("neuro_mirror.web")

# Одна модель на процесс: загрузка отложена до первой озвучки.
_synthesizer = SpeechSynthesizer()


# ---- Pydantic request models ----

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
    personal_data_consent: bool | None = None
    audio_data_consent: bool | None = None
    video_data_consent: bool | None = None
    # Retention consent is opt-in and never inherited from ``consent``.
    dataset_consent: bool = False
    avatar_preset: str = ""
    photo_base64: str = ""


class ConsentUpdateIn(BaseModel):
    consent_type: str
    given: bool


class DatasetVideoStartIn(BaseModel):
    session_id: str
    client_started_at: str
    mime_type: str = ""


class DatasetTimelineIn(BaseModel):
    session_id: str
    stage: str = ""
    screen: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class ClientLogIn(BaseModel):
    level: str = "info"
    message: str = ""


class SessionFrameIn(BaseModel):
    image_base64: str


class TrainingFinishIn(BaseModel):
    reason: str = ""


class TrainingPauseIn(BaseModel):
    # Номер задания занятия, на котором нажата пауза; пусто — между заданиями.
    position: int | None = None


class SanAnswersIn(BaseModel):
    # Когда опросник заполнен: до занятия или после. Сравнение «до» и
    # «после» — и есть смысл этой оценки.
    moment: str = "before"
    answers: dict[str, int] = Field(default_factory=dict)
    session_id: str = ""


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

def ensure_static_mime_types() -> None:
    """Закрепить типы файлов интерфейса, не полагаясь на систему.

    Windows берёт тип из реестра, и там расширение .js нередко помечено как
    text/plain. Классический сценарий браузер при этом всё равно выполняет, а
    модульный отвергает: для модулей проверка типа строгая. Интерфейс,
    собранный из модулей, тогда не запускается вовсе — страница остаётся
    пустой, и в журнале сервера никаких ошибок нет.
    """
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/javascript", ".mjs")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("application/json", ".json")
    mimetypes.add_type("image/svg+xml", ".svg")


ensure_static_mime_types()


def create_app() -> FastAPI:
    static_dir = Path(__file__).resolve().parent / "static"
    game_assets_dir = Path(__file__).resolve().parents[1] / "plugins" / "games" / "assets"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = Settings.from_env()

        # create_runtime now includes AI plugin with request-reply support
        runtime = create_runtime(
            settings,
            stop_event=asyncio.Event(),
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
    access_journal = AccessJournal()
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.mount("/game-assets", StaticFiles(directory=str(game_assets_dir)), name="game-assets")

    def _active_user_or_400() -> dict[str, Any]:
        ctx: WebAppContext = app.state.context
        user = ctx.user_store.get_active_user()
        if user is None:
            raise HTTPException(status_code=400, detail="Сначала выберите пользователя.")
        return user

    def _require_consent(consent_type: str) -> dict[str, Any]:
        ctx: WebAppContext = app.state.context
        user = _active_user_or_400()
        if not ctx.user_store.has_consent(str(user.get("id") or ""), consent_type):
            labels = {
                "personal": "персональных данных",
                "audio": "аудиоданных",
                "video": "видеоданных",
            }
            if consent_type == "dataset":
                raise HTTPException(
                    status_code=403,
                    detail="Нет согласия на сохранение записей в набор данных.",
                )
            raise HTTPException(
                status_code=403,
                detail=f"Нет согласия на обработку {labels.get(consent_type, consent_type)}.",
            )
        return user

    def _dataset_capture_payload() -> dict[str, Any]:
        """Tell the aggregator whether raw media may be retained this session."""
        ctx: WebAppContext = app.state.context
        user = ctx.user_store.get_active_user()
        if user is None or not ctx.user_store.active_has_consent("dataset"):
            return {"dataset_allowed": False}
        entry = (user.get("consents") or {}).get("dataset") or {}
        return {
            "dataset_allowed": True,
            "dataset_consent": {
                "given": True,
                "text": entry.get("text", CONSENT_TEXTS.get("dataset", "")),
                "timestamp": entry.get("timestamp"),
            },
        }

    # ---- Read-only endpoints ----

    @app.get("/")
    async def root() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/state")
    async def get_state() -> JSONResponse:
        ctx: WebAppContext = app.state.context
        return JSONResponse(await ctx.state_store.get_snapshot())

    async def _game_reply(topic: str, source: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx: WebAppContext = app.state.context
        reply = await ctx.runtime.bus.request(Event(topic=topic, source=source, payload=payload or {}))
        if not reply.get("ok"):
            raise HTTPException(status_code=400, detail=reply.get("message", "Ошибка игры."))
        reply.pop("_reply_to", None)
        return reply

    @app.get("/api/games/catalog")
    async def game_catalog() -> JSONResponse:
        implemented = implemented_game_codes()
        return JSONResponse(
            [item.to_public_dict(implemented=item.code in implemented) for item in all_game_definitions()]
        )

    @app.get("/api/questionnaires/san")
    async def san_questions() -> JSONResponse:
        """Вопросы опросника самочувствия.

        Содержание опросника принадлежит ядру, как у MoCA и HADS: интерфейс
        его только показывает.
        """
        return JSONResponse(san_questionnaire())

    @app.post("/api/questionnaires/san")
    async def save_san_answers(payload: SanAnswersIn) -> JSONResponse:
        ctx: WebAppContext = app.state.context
        active = _active_user_or_400()
        moment = payload.moment.strip().lower()
        if moment not in MOMENTS:
            raise HTTPException(
                status_code=400,
                detail="Укажите, когда заполнен опросник: до занятия или после.",
            )
        result = score_san(payload.answers)
        record = {
            "report_type": "san_survey",
            "type": "san_survey",
            "moment": moment,
            "user_id": str(active.get("id") or ""),
            "session_id": payload.session_id,
            "stored_at": datetime.now(UTC).isoformat(),
            **result,
        }
        await ctx.runtime.bus.publish(
            Event(topic=Topics.STORAGE_WRITE, source="web.san", payload=record)
        )
        return JSONResponse(result)

    async def _latest_moca(user_id: str) -> tuple[list[dict[str, Any]], str, str]:
        """Профиль доменов из последнего результата MoCA: профиль, сессия, время."""
        ctx: WebAppContext = app.state.context
        try:
            reply = await ctx.runtime.bus.request(
                Event(
                    topic=Topics.REQ_STORAGE_QUERY,
                    source="web.training",
                    payload={"user_id": user_id},
                ),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Хранилище не ответило.")

        items = list(reply.get("items") or [])
        items.sort(key=lambda item: str(item.get("stored_at") or ""), reverse=True)
        for item in items:
            candidate = ((item.get("domains") or {}).get("moca_domains")) or []
            if candidate:
                return list(candidate), str(item.get("session_id") or ""), str(item.get("stored_at") or "")
        return [], "", ""

    def _moment(value: Any) -> datetime | None:
        try:
            moment = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
        return moment if moment.tzinfo else moment.replace(tzinfo=UTC)

    def _course_payload(course: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
        store = app.state.context.runtime.training_course_store
        number = int(session["number"])
        return {
            "course": {
                "course_id": course["course_id"],
                "session_number": number,
                "sessions_total": COURSE_SESSIONS,
                "completed_sessions": len(store.closed_sessions(course)),
                "stage": stage_for(number).to_dict(),
                # Все 12 слотов курса: номер, этап и состояние каждого.
                "slots": [
                    {"number": item["number"], "stage": item["stage"], "status": item["status"]}
                    for item in course["sessions"]
                ],
            },
            "status": session["status"],
            "plan": course["plan"],
            "games": session["games"],
            "session_size": len(session["games"]),
            "skipped": course["skipped"],
            "level_changes": session["level_changes"],
            "profile": course["entry"]["profile"],
            "source_session_id": course["entry"]["session_id"],
        }

    @app.get("/api/training/session")
    async def training_session() -> JSONResponse:
        """Текущее занятие курса.

        Курс формируется сразу на 12 занятий: состав и задания выбираются один
        раз по входному скринингу и во всех занятиях одинаковы. Когда занятие
        открывается, в него проставляются уровни форм по правильности
        предыдущих прохождений; дальше план не меняется, и перезагрузка
        страницы возвращает то же занятие. Новый курс начинается только после
        выходного скрининга — когнитивного теста, пройденного после 12-го
        занятия.
        """
        ctx: WebAppContext = app.state.context
        active = _active_user_or_400()
        user_id = str(active.get("id") or "")
        store = ctx.runtime.training_course_store

        course = store.latest_course(user_id)
        session = store.open_session(user_id)
        if course is not None and session is not None:
            return JSONResponse(_course_payload(course, session))

        if course is None or store.is_finished(course):
            profile, entry_session, entry_at = await _latest_moca(user_id)
            if not profile:
                raise HTTPException(
                    status_code=409,
                    detail="Сначала пройдите когнитивный тест: занятие подбирается по его результату.",
                )
            if course is not None:
                finished_at = _moment(course.get("finished_at"))
                tested_at = _moment(entry_at)
                if finished_at is None or tested_at is None or tested_at <= finished_at:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Курс из {COURSE_SESSIONS} занятий пройден. Следующий шаг — "
                            "выходной скрининг: пройдите когнитивный тест ещё раз, и по "
                            "его результату начнётся новый курс."
                        ),
                    )
            composition = build_training_session(
                profile,
                history=ctx.runtime.game_history_store.for_user(user_id),
                available_codes=implemented_game_codes(),
            )
            if not composition["games"]:
                raise HTTPException(status_code=409, detail="Не удалось подобрать ни одного задания.")
            course = store.create_course(
                user_id=user_id,
                entry_session_id=entry_session,
                profile=profile,
                composition=composition,
            )

        slot = store.next_slot(course)
        number = int(slot["number"])
        states, log = form_states(store.passes(course), number)
        session = store.open_slot(
            course,
            slot,
            states=states,
            level_changes=[entry for entry in log if entry["before_session"] == number],
        )
        return JSONResponse(_course_payload(course, session))

    @app.post("/api/training/session/finish")
    async def finish_training_session(payload: TrainingFinishIn | None = None) -> JSONResponse:
        """Завершить занятие — по окончании всех заданий или досрочно.

        Начатое и не законченное задание получает статус «прервано»: нулём
        оно не считается и уровень формы не меняет.
        """
        ctx: WebAppContext = app.state.context
        active = _active_user_or_400()
        reason = (payload.reason if payload else "").strip() or "пользователь завершил занятие"
        session = ctx.runtime.training_course_store.finish_session(str(active.get("id") or ""), reason=reason)
        if session is None:
            return JSONResponse({"finished": False})
        done = sum(1 for item in session["games"] if item["status"] == ITEM_DONE)
        return JSONResponse({
            "finished": True,
            "session_number": session["number"],
            "status": session["status"],
            "done": done,
            "total": len(session["games"]),
        })

    @app.post("/api/training/session/pause")
    async def pause_training_session(payload: TrainingPauseIn | None = None) -> JSONResponse:
        """Отметить паузу в журнале занятия: где нажата и когда."""
        ctx: WebAppContext = app.state.context
        active = _active_user_or_400()
        try:
            record = ctx.runtime.training_course_store.pause(
                str(active.get("id") or ""), position=payload.position if payload else None
            )
        except CourseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(record)

    @app.post("/api/training/session/resume")
    async def resume_training_session() -> JSONResponse:
        ctx: WebAppContext = app.state.context
        active = _active_user_or_400()
        record = ctx.runtime.training_course_store.resume(str(active.get("id") or ""))
        return JSONResponse(record or {})

    @app.get("/api/training/course")
    async def training_course() -> JSONResponse:
        """Курс целиком: занятия, исходы заданий, уровни форм и их переходы.

        Это данные для отчёта специалиста о занятии и о курсе.
        """
        ctx: WebAppContext = app.state.context
        active = _active_user_or_400()
        user_id = str(active.get("id") or "")
        store = ctx.runtime.training_course_store
        course = store.latest_course(user_id)
        if course is None:
            raise HTTPException(status_code=404, detail="Курс тренировок ещё не начат.")
        next_number = min(len(store.closed_sessions(course)) + 1, COURSE_SESSIONS)
        states, log = form_states(store.passes(course), next_number)
        access_journal.record(
            action=VIEW_RESULTS,
            user_id=user_id,
            details={"kind": "training_course", "sessions": len(course["sessions"])},
        )
        return JSONResponse({
            **course,
            "sessions_total": COURSE_SESSIONS,
            "completed_sessions": len(store.closed_sessions(course)),
            "finished": store.is_finished(course),
            "levels": {code: describe(state) for code, state in sorted(states.items())},
            "level_changes": log,
        })

    @app.get("/api/games/{game_code}/renderer.js")
    async def game_renderer(game_code: str) -> FileResponse:
        try:
            definition = get_available_game_definition(game_code)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        path = game_asset_path(definition.code, "web.js")
        if path is None:
            raise HTTPException(status_code=404, detail="У игры нет отдельного браузерного модуля.")
        return FileResponse(
            path,
            media_type="text/javascript",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/games/{game_code}/start")
    async def generic_game_start(
        game_code: str,
        payload: dict[str, Any] | None = None,
    ) -> JSONResponse:
        try:
            definition = get_available_game_definition(game_code)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if definition.code not in implemented_game_codes():
            raise HTTPException(status_code=501, detail="Игра присутствует в каталоге, но ещё не реализована.")
        active_user = _active_user_or_400()
        user_id = str(active_user.get("id") or "")
        store = app.state.context.runtime.training_course_store
        body = dict(payload or {})
        course_session = body.pop("course_session", None)
        course_position = body.pop("course_position", None)
        in_course = course_session is not None and course_position is not None
        if in_course:
            # Задание курса: уровень, стимульный набор и зерно берутся из
            # сохранённого плана занятия, а не из запроса интерфейса.
            try:
                item = store.begin_item(
                    user_id=user_id,
                    session_number=int(course_session),
                    position=int(course_position),
                    game_code=definition.code,
                )
            except (CourseError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            body.update(
                difficulty_level=item["difficulty_level"],
                stimulus_set=item["stimulus_set"],
                randomization_seed=item["randomization_seed"],
            )
        reply = await _game_reply(
            definition.start_request_topic,
            f"web.game.{definition.topic_prefix}",
            {**body, "user_id": user_id},
        )
        if in_course and reply.get("session_id"):
            store.attach_game_session(
                user_id=user_id,
                session_number=int(course_session),
                position=int(course_position),
                game_session_id=str(reply["session_id"]),
            )
        return JSONResponse(reply)

    @app.post("/api/games/{game_code}/answer")
    async def generic_game_answer(game_code: str, payload: dict[str, Any]) -> JSONResponse:
        try:
            definition = get_available_game_definition(game_code)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if definition.code not in implemented_game_codes():
            raise HTTPException(status_code=501, detail="Игра присутствует в каталоге, но ещё не реализована.")
        return JSONResponse(await _game_reply(
            definition.answer_request_topic,
            f"web.game.{definition.topic_prefix}",
            payload,
        ))

    @app.get("/api/config")
    async def get_config() -> JSONResponse:
        return JSONResponse(
            {
                # Голос берётся у синтезатора, которым программа реально
                # озвучивает: прежде здесь стояло название голоса облачной
                # озвучки, удалённой при переходе на работу без сети.
                "tts_voice": _synthesizer.voice_path.stem,
                "tts_available": _synthesizer.available,
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
            # Profiles created with a removed preset get the first current one
            if preset not in KNOWN_AVATARS:
                preset = PRESET_AVATARS[0]
            avatar_url = f"/static/assets/avatars/{preset}.svg"
        return {
            "id": user.get("id", ""),
            "name": user.get("name", ""),
            "avatar_url": avatar_url,
            "created_at": user.get("created_at", ""),
            "progress": user.get("progress") or {},
            "consents": {
                consent_type: bool(
                    isinstance((user.get("consents") or {}).get(consent_type), dict)
                    and (user.get("consents") or {}).get(consent_type, {}).get("given")
                )
                for consent_type in CONSENT_TEXTS
            },
        }

    def _serialize_incomplete_session(session: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": session.get("session_id", ""),
            "scenario": session.get("scenario", ""),
            "status": session.get("status", ""),
            "started_at": session.get("started_at"),
            "updated_at": session.get("updated_at"),
            "interruption_reason": session.get("interruption_reason", ""),
            "checkpoint": session.get("checkpoint") or {},
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
                "consent_texts": CONSENT_TEXTS,
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
                personal_data_consent=payload.personal_data_consent,
                audio_data_consent=payload.audio_data_consent,
                video_data_consent=payload.video_data_consent,
                dataset_consent=payload.dataset_consent,
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
                payload={"user_id": user["id"]},
            )
        )
        greeting = f"Здравствуйте, {user['name']}! {_next_step_suggestion(user)}"
        await ctx.state_store.apply_update(
            {
                "screen": "idle",
                "active_user": serialized,
                "message": greeting,
            },
            source="web.users",
        )
        incomplete_sessions = ctx.runtime.session_store.list_for_user(
            str(user.get("id") or ""),
            resumable_only=True,
        )
        return JSONResponse(
            {
                "user": serialized,
                "incomplete_sessions": [
                    _serialize_incomplete_session(item) for item in incomplete_sessions
                ],
            }
        )

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
        access_journal.record(
            action=VIEW_RESULTS,
            user_id=str(active.get("id") or ""),
            details={"count": len(items)},
        )
        return JSONResponse({"user": _serialize_user(active), "items": items})

    @app.get("/api/results/games/export")
    async def export_game_results() -> JSONResponse:
        """Download only training-game reports belonging to the active user."""
        ctx: WebAppContext = app.state.context
        active = _active_user_or_400()
        try:
            reply = await ctx.runtime.bus.request(
                Event(
                    topic=Topics.REQ_STORAGE_QUERY,
                    source="web.results.games_export",
                    payload={"user_id": active["id"]},
                ),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Хранилище не ответило.")

        games = [
            item
            for item in (reply.get("items") or [])
            if item.get("report_type") == "training_game"
        ]
        games.sort(key=lambda item: str(item.get("stored_at") or ""), reverse=True)
        access_journal.record(
            action=EXPORT_RESULTS,
            user_id=str(active.get("id") or ""),
            details={"kind": "training_game", "count": len(games)},
        )
        return JSONResponse(
            {
                "user_id": str(active.get("id") or ""),
                "exported_at": datetime.now(UTC).isoformat(),
                "game_results": games,
            },
            headers={
                "Content-Disposition": 'attachment; filename="game-results.json"',
            },
        )

    @app.get("/api/sessions/incomplete")
    async def incomplete_sessions() -> JSONResponse:
        ctx: WebAppContext = app.state.context
        active = _active_user_or_400()
        items = ctx.runtime.session_store.list_for_user(
            str(active.get("id") or ""),
            resumable_only=True,
        )
        return JSONResponse(
            {"items": [_serialize_incomplete_session(item) for item in items]}
        )

    @app.post("/api/sessions/{session_id}/resume")
    async def resume_session(session_id: str) -> JSONResponse:
        ctx: WebAppContext = app.state.context
        active = _active_user_or_400()
        session = ctx.runtime.session_store.get(session_id)
        if session is None or session.get("user_id") != active.get("id"):
            raise HTTPException(status_code=404, detail="Незавершенная сессия не найдена.")
        if session.get("status") != "interrupted":
            raise HTTPException(status_code=409, detail="Сессия не является прерванной.")
        scenario = str(session.get("scenario") or "")
        if scenario == "moca":
            _require_consent("audio")
        elif scenario == "screening":
            _require_consent("video")
        reply = await ctx.runtime.bus.request(
            Event(
                topic=Topics.UI_ACTION,
                source="web.sessions",
                payload={
                    "action": "resume_session",
                    "session_id": session_id,
                    "audio_allowed": ctx.user_store.active_has_consent("audio"),
                    "video_allowed": ctx.user_store.active_has_consent("video"),
                    **_dataset_capture_payload(),
                },
            )
        )
        if not reply.get("accepted"):
            raise HTTPException(status_code=409, detail="Не удалось продолжить сессию. Завершите текущий тест и обновите список.")
        return JSONResponse({"accepted": True, "session_id": session_id})

    @app.post("/api/session/check-voice")
    async def session_check_voice() -> JSONResponse:
        """Probe the microphone the test itself records with.

        The browser-side level meter only proves that ``getUserMedia`` works.
        Answers are captured by ``VoiceRecorder`` in this process, so the probe
        has to go through the same path — device, recorder and speech model —
        before the test starts.
        """
        ctx: WebAppContext = app.state.context
        _require_consent("audio")

        from neuro_mirror.screening.voice_probe import (
            PROBE_SECONDS,
            evaluate_probe,
            is_silent,
            measure_peak_level,
        )
        from neuro_mirror.utils.audio import VoiceRecorder, delete_temp_audio

        recorder = VoiceRecorder(
            sample_rate=ctx.settings.voice_sample_rate,
            channels=ctx.settings.voice_channels,
            max_seconds=PROBE_SECONDS,
            stop_on_silence=False,
        )
        if not recorder.available:
            result = evaluate_probe(
                recorded=False, peak_level=None, transcript="", failure_reason="no_device",
            )
            return JSONResponse(result.__dict__)

        try:
            audio_path = await asyncio.to_thread(recorder.start)
        except Exception as exc:  # noqa: BLE001 — the cause is reported, not raised
            _log.warning("check-voice: не удалось начать запись: %s", exc)
            result = evaluate_probe(
                recorded=False, peak_level=None, transcript="", failure_reason="busy",
            )
            return JSONResponse(result.__dict__)

        transcript = ""
        peak_level: float | None = None
        try:
            await asyncio.sleep(PROBE_SECONDS + 0.3)
            audio_path = await asyncio.to_thread(recorder.stop) or audio_path
            peak_level = await asyncio.to_thread(measure_peak_level, audio_path)
            # Transcribing silence only wastes time on the speech model
            if not is_silent(peak_level):
                try:
                    reply = await ctx.runtime.bus.request(
                        Event(
                            topic=Topics.REQ_SPEECH_TRANSCRIBE,
                            source="web.check_voice",
                            payload={"audio_path": audio_path, "suppress_ui": True},
                        ),
                        timeout=120.0,
                    )
                    transcript = str(reply.get("transcript") or "")
                except Exception as exc:  # noqa: BLE001
                    _log.warning("check-voice: распознавание не удалось: %s", exc)
        finally:
            delete_temp_audio(audio_path)

        result = evaluate_probe(
            recorded=True, peak_level=peak_level, transcript=transcript,
        )
        return JSONResponse(result.__dict__)

    # ---- Session conditions check (ТЗ 6.3.2): face / lighting / distance ----

    @app.post("/api/session/check-face")
    async def session_check_face(payload: SessionFrameIn) -> JSONResponse:
        _require_consent("video")
        import base64 as _base64

        from neuro_mirror.screening.session_check import analyze_frame_conditions

        stripped = payload.image_base64.split(",", 1)[-1].strip()
        try:
            jpeg_bytes = _base64.b64decode(stripped, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="Некорректное изображение.")
        if len(jpeg_bytes) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Кадр слишком большой.")

        try:
            result = await asyncio.to_thread(analyze_frame_conditions, jpeg_bytes)
        except Exception:
            _log.exception("Ошибка серверной проверки лица")
            result = {
                "frame_ok": True,
                "face_detected": False,
                "face_count": 0,
                "face_ratio": 0.0,
                "face_close_enough": False,
                "brightness": 0.0,
                "brightness_ok": False,
                "detector_available": False,
                "advice": [
                    "Проверка лица не запустилась. Перезапустите приложение и нажмите «Проверить снова». "
                    "Если сообщение повторится, видео-скрининг на этом компьютере недоступен."
                ],
            }
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

    @app.post("/api/users/{user_id}/consents")
    async def update_consent(user_id: str, payload: ConsentUpdateIn) -> JSONResponse:
        """Grant or withdraw one consent for an existing profile."""
        ctx: WebAppContext = app.state.context
        try:
            user = ctx.user_store.set_consent(user_id, payload.consent_type, payload.given)
        except KeyError:
            raise HTTPException(status_code=404, detail="Пользователь или тип согласия не найден.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return JSONResponse({"user": _serialize_user(user)})

    # ---- Dataset capture (requires the separate retention consent) ----

    @app.get("/api/dataset/status")
    async def dataset_status() -> JSONResponse:
        """Tell the browser whether it should be recording, and for which session."""
        ctx: WebAppContext = app.state.context
        active = ctx.user_store.get_active_user()
        if active is None or not ctx.user_store.active_has_consent("dataset"):
            return JSONResponse({"capture": False, "session_id": ""})
        sessions = ctx.runtime.session_store.list_for_user(str(active.get("id") or ""))
        for session in sessions:
            session_id = str(session.get("session_id") or "")
            if session.get("status") == "in_progress" and ctx.runtime.dataset_store.is_open(session_id):
                return JSONResponse({
                    "capture": True,
                    "session_id": session_id,
                    "scenario": session.get("scenario", ""),
                    "next_video_sequence": ctx.runtime.dataset_store.next_video_sequence(session_id),
                })
        return JSONResponse({"capture": False, "session_id": ""})

    @app.post("/api/dataset/video-start")
    async def dataset_video_start(payload: DatasetVideoStartIn) -> JSONResponse:
        """Pin the browser video clock to the server clock for this session."""
        ctx: WebAppContext = app.state.context
        _require_consent("dataset")
        store = ctx.runtime.dataset_store
        if not store.is_open(payload.session_id):
            raise HTTPException(status_code=409, detail="Запись для этой сессии не открыта.")
        try:
            capture = store.register_video_start(
                payload.session_id,
                client_started_at=payload.client_started_at,
                mime_type=payload.mime_type,
            )
        except DatasetCaptureError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return JSONResponse({"accepted": True, **capture})

    @app.post("/api/dataset/video-chunk")
    async def dataset_video_chunk(
        session_id: str = Form(...),
        sequence: int = Form(...),
        offset_ms: float | None = Form(None),
        chunk: UploadFile = File(...),
    ) -> JSONResponse:
        """Store one browser-recorded media chunk for the running session."""
        ctx: WebAppContext = app.state.context
        _require_consent("dataset")
        store = ctx.runtime.dataset_store
        # MediaRecorder can deliver its final chunk just after the test result
        # closes the dataset session. Preserve that already-consented tail.
        if not store.session_exists(session_id):
            raise HTTPException(status_code=409, detail="Запись для этой сессии не открыта.")
        data = await chunk.read()
        try:
            record = store.append_video_chunk(
                session_id,
                data=data,
                sequence=sequence,
                mime_type=chunk.content_type or "video/webm",
                offset_ms=offset_ms,
            )
        except DatasetCaptureError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return JSONResponse({"accepted": True, **record})

    @app.post("/api/dataset/timeline")
    async def dataset_timeline(payload: DatasetTimelineIn) -> JSONResponse:
        """Record which stage was on screen, so media can be aligned later."""
        ctx: WebAppContext = app.state.context
        _require_consent("dataset")
        store = ctx.runtime.dataset_store
        # Allow the browser's final capture_stopped marker to arrive just
        # after the result closes the session.
        if not store.session_exists(payload.session_id):
            raise HTTPException(status_code=409, detail="Запись для этой сессии не открыта.")
        store.append_timeline(
            payload.session_id,
            {"stage": payload.stage, "screen": payload.screen, "details": payload.details},
        )
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
        if action == "resume_session":
            raise HTTPException(status_code=400, detail="Используйте /api/sessions/{session_id}/resume.")
        event_payload: dict[str, Any] = {"action": action}
        if request.headers.get("content-type", "").lower().startswith("application/json"):
            try:
                body = await request.json()
            except Exception:
                body = None
            if isinstance(body, dict):
                event_payload.update(body)
        event_payload["action"] = action
        if action in {"start_moca", "start_voice_capture"}:
            _require_consent("audio")
            event_payload["audio_allowed"] = True
        if action in {"start_screening", "measure_pulse", "start_preview"}:
            _require_consent("video")
            event_payload["video_allowed"] = True
        if action in {"start_screening", "start_hads"}:
            _active_user_or_400()
            event_payload["audio_allowed"] = ctx.user_store.active_has_consent("audio")
        if action == "start_screening":
            event_payload["video_allowed"] = True
        if action in {"start_screening", "start_moca", "start_hads"}:
            event_payload.update(_dataset_capture_payload())
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

    @app.post("/api/speech/transcribe")
    async def speech_transcribe(audio: UploadFile = File(...)) -> JSONResponse:
        ctx: WebAppContext = app.state.context
        _require_consent("audio")
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

        return JSONResponse(
            {
                "accepted": True,
                "transcript": stt_result.get("transcript", ""),
                "raw_transcript": stt_result.get("raw_transcript", ""),
                "notes": stt_result.get("notes", ""),
                "stt_model": stt_result.get("model", stt_result.get("stt_model", "")),
                "stt_device": stt_result.get("device", stt_result.get("stt_device", "")),
            }
        )

    # ---- TTS (pure transport, no business logic) ----

    @app.post("/api/tts/speak")
    async def tts_speak(payload: TTSRequest) -> Response:
        """Озвучить текст локальной моделью.

        Синтез выполняется на устройстве: текст инструкций никуда не
        передаётся, и проведение теста не зависит от подключения к сети.
        """
        if not payload.text.strip():
            raise HTTPException(status_code=400, detail="text is required")
        try:
            audio = await asyncio.to_thread(_synthesizer.synthesize_wav, payload.text)
        except SpeechSynthesisUnavailable as exc:
            _log.error("tts: синтез недоступен: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Синтез речи недоступен: не установлен голос. "
                       "Инструкции не будут озвучены.",
            )
        return Response(
            content=audio,
            media_type="audio/wav",
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
        if (
            ctx.user_store.get_active_user() is None
            or not ctx.user_store.active_has_consent("video")
        ):
            await websocket.close(code=4403, reason="Требуется согласие на обработку видеоданных.")
            return
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
                "video_quality_issues": [] if face_boxes else ["no_face"],
                "video_usable": bool(face_boxes),
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
