from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib import error, parse, request

from neuro_mirror.core.settings import Settings
from neuro_mirror.plugins.ai_assistant.rules import load_assistant_rules


class AssistantDecision:
    command: str | None
    reply: str
    backend_name: str
    raw_response: str | None = None


class AssistantBackend(Protocol):
    name: str

    async def decide(self, utterance: str) -> AssistantDecision:
        raise NotImplementedError


class RuleBasedAssistantBackend:
    name = "rule_based"

    async def decide(self, utterance: str) -> AssistantDecision:
        utterance = normalize_user_utterance(utterance)
        appearance_command = detect_appearance_request(utterance)
        if appearance_command is not None:
            return AssistantDecision(
                command=appearance_command,
                reply="Сейчас посмотрю в камеру и дам короткий комментарий.",
                backend_name=self.name,
            )

        if detect_camera_vision_request(utterance):
            return AssistantDecision(
                command="camera_vision_query",
                reply="Сейчас посмотрю на камеру и расскажу что вижу.",
                backend_name="vision:камера",
            )

        command = detect_start_screening_command(utterance)
        reply = (
            "Запускаю скрининг."
            if command == "start_screening"
            else "Не могу надёжно ответить на этот вопрос без локальной модели. Повторите его или уточните формулировку."
        )
        return AssistantDecision(command=command, reply=reply, backend_name=self.name)


class OllamaAssistantBackend:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        fallback_model: str = "",
        rules_path: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.fallback_model = fallback_model.strip()
        self.timeout_seconds = timeout_seconds
        self.rules_path = rules_path
        self.name = f"ollama:{model}"
        self._resolved_model_cache: str = ""

    async def decide(self, utterance: str) -> AssistantDecision:
        utterance = normalize_user_utterance(utterance)
        appearance_command = detect_appearance_request(utterance)
        if appearance_command is not None:
            return AssistantDecision(
                command=appearance_command,
                reply="Сейчас посмотрю в камеру и дам короткий комментарий.",
                backend_name="визуальный анализ",
            )

        if detect_camera_vision_request(utterance):
            return AssistantDecision(
                command="camera_vision_query",
                reply="Сейчас посмотрю на камеру и расскажу что вижу.",
                backend_name="vision:камера",
            )

        shortcut_command = detect_start_screening_command(utterance)
        if shortcut_command is not None:
            return AssistantDecision(
                command=shortcut_command,
                reply="Запускаю скрининг.",
                backend_name="скрининг",
            )

        # Resolve model once and cache for this request
        if not self._resolved_model_cache:
            self._resolved_model_cache = await asyncio.to_thread(self._resolve_model_name_sync)
        resolved_model = self._resolved_model_cache

        if detect_current_date_request(utterance):
            return AssistantDecision(
                command=None,
                reply=build_current_date_reply(),
                backend_name=self.name,
            )

        # Single combined call: classify intent AND answer in one LLM request
        local_answer = await self._classify_and_answer(resolved_model, utterance)
        if local_answer.command is not None:
            return local_answer

        return local_answer

    def _rules_block(self) -> str:
        rules = load_assistant_rules(self.rules_path)
        return f"Общие правила поведения ассистента:\n{rules}\n\n"

    def _build_prompt(self, utterance: str) -> str:
        return self._rules_block() + (
            "Ты строгий классификатор интентов для приложения Нейро-зеркало.\n"
            "Твоя задача: сопоставить реплику пользователя с одной командой приложения.\n"
            "Доступные команды:\n"
            '- "start_screening" если пользователь хочет начать скрининг, проверку, тест или оценку.\n'
            '- "analyze_appearance" если пользователь просит посмотреть на него через камеру и оценить внешний вид.\n'
            '- "camera_vision_query" если пользователь просит описать что видно на камере, или спрашивает что перед ним/в кадре.\n'
            '- "measure_pulse" если пользователь просит измерить, померить, показать, проверить пульс или сердцебиение.\n'
            '- "none" если это не команда приложения.\n'
            "Для обычного вопроса всегда выбирай command=none.\n"
            "Ответь только JSON по схеме:\n"
            '{"command":"start_screening|analyze_appearance|camera_vision_query|measure_pulse|none","reply":"короткий нейтральный текст для UI"}\n'
            "Примеры:\n"
            'Пользователь: "Начать когнитивный скрининг" -> {"command":"start_screening","reply":"Запускаю скрининг."}\n'
            'Пользователь: "Как я сегодня выгляжу?" -> {"command":"analyze_appearance","reply":"Сейчас посмотрю в камеру и дам короткий комментарий."}\n'
            'Пользователь: "Что ты видишь на камере?" -> {"command":"camera_vision_query","reply":"Сейчас посмотрю на камеру и расскажу что вижу."}\n'
            'Пользователь: "Померь пульс" -> {"command":"measure_pulse","reply":"Запускаю мониторинг пульса."}\n'
            'Пользователь: "Какая сегодня погода?" -> {"command":"none","reply":"Это обычный вопрос, не команда приложения."}\n'
            f'Пользователь: "{utterance}"'
        )

    def _build_general_prompt(self, utterance: str) -> str:
        return self._rules_block() + (
            "Ответь на обычный вопрос пользователя как помощник приложения Нейро-зеркало.\n"
            "Если вопрос неясен, похож на ошибку распознавания речи или тебе не хватает контекста,\n"
            "ответь только: 'Не могу надёжно ответить на этот вопрос. Повторите его или уточните формулировку.'.\n"
            "ВАЖНО: если вопрос требует актуальных данных (новости, цены, события, "
            "расписания, текущие факты), которых у тебя нет — обязательно начни ответ "
            'со слов "Не имею доступа к актуальным данным" или "Не могу проверить". '
            "Не выдумывай факты и не отвечай устаревшей информацией как актуальной.\n"
            f'Вопрос пользователя: "{utterance}"'
        )

    def _build_combined_prompt(self, utterance: str) -> str:
        return self._rules_block() + (
            "Сначала определи, является ли реплика командой приложения.\n"
            "Команды: start_screening (скрининг/тест/проверка), "
            "analyze_appearance (оценить внешний вид), "
            "camera_vision_query (что видно на камере), "
            "measure_pulse (измерить/померить/показать пульс или сердцебиение).\n"
            "Если это команда — верни JSON: "
            '{"command":"<команда>","reply":"<короткий текст>"}\n'
            "Если это НЕ команда — ответь как ассистент кратко (1-3 предложения) на языке пользователя. "
            "Не предлагай список команд приложения в ответ на обычный вопрос. "
            "Верни JSON: "
            '{"command":"none","reply":"<твой ответ>"}\n'
            "ВАЖНО: если вопрос требует актуальных данных, начни reply со слов "
            '"Не имею доступа к актуальным данным".\n'
            "Не выдумывай факты. Ответь ТОЛЬКО JSON.\n"
            f'Пользователь: "{utterance}"'
        )

    async def _classify_and_answer(
        self,
        resolved_model: str,
        utterance: str,
    ) -> AssistantDecision:
        """Single LLM call: classify intent AND generate answer together."""
        payload = {
            "model": resolved_model,
            "prompt": self._build_combined_prompt(utterance),
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 256},
        }
        raw = await asyncio.to_thread(self._post_json_sync, "/api/generate", payload)
        response_text = raw.get("response", "")

        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            # Fallback: treat the whole response as a text reply
            cleaned = _sanitize_assistant_reply(response_text)
            return AssistantDecision(
                command=None,
                reply=cleaned,
                backend_name=source_label_for_backend(f"ollama:{resolved_model}:chat"),
                raw_response=response_text,
            )

        raw_command = parsed.get("command")
        command = raw_command if raw_command in {"start_screening", "analyze_appearance", "camera_vision_query", "measure_pulse"} else None
        reply = str(parsed.get("reply") or "").strip()

        if not reply or reply == "Подходящая команда не найдена.":
            reply = _sanitize_assistant_reply(reply)

        if command is None:
            reply = _sanitize_assistant_reply(reply)

        return AssistantDecision(
            command=command,
            reply=reply,
            backend_name=source_label_for_backend(f"ollama:{resolved_model}:chat"),
            raw_response=response_text,
        )

    def _post_json_sync(self, path: str, payload: dict) -> dict:
        # Inject keep_alive=-1 so the model stays loaded in VRAM between calls
        if path in {"/api/generate", "/api/chat"}:
            payload = {**payload, "keep_alive": -1}
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ошибка HTTP Ollama {exc.code}: {error_body}") from exc
        except error.URLError as exc:
            raise RuntimeError(
                f"Не удалось подключиться к Ollama по адресу {self.base_url}: {exc.reason}"
            ) from exc

        parsed = json.loads(raw_body)
        if "error" in parsed:
            raise RuntimeError(f"Ошибка Ollama: {parsed['error']}")
        return parsed

    async def _classify_command(self, resolved_model: str, utterance: str) -> AssistantDecision:
        payload = {
            "model": resolved_model,
            "prompt": self._build_prompt(utterance),
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
        }
        raw = await asyncio.to_thread(self._post_json_sync, "/api/generate", payload)
        response_text = raw.get("response", "")

        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Ollama вернула не-JSON ответ для классификации: {response_text!r}"
            ) from exc

        raw_command = parsed.get("command")
        command = raw_command if raw_command in {"start_screening", "analyze_appearance", "camera_vision_query", "measure_pulse"} else None
        reply = str(parsed.get("reply") or parsed.get("reason") or "Команда распознана.")

        return AssistantDecision(
            command=command,
            reply=reply,
            backend_name=source_label_for_backend(f"ollama:{resolved_model}"),
            raw_response=response_text,
        )

    async def _answer_general_question(
        self,
        resolved_model: str,
        utterance: str,
    ) -> AssistantDecision:
        payload = {
            "model": resolved_model,
            "prompt": self._build_general_prompt(utterance),
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 200},
        }
        raw = await asyncio.to_thread(self._post_json_sync, "/api/generate", payload)
        response_text = str(raw.get("response", "")).strip() or "Ответ не был сгенерирован."
        response_text = _sanitize_assistant_reply(response_text)
        return AssistantDecision(
            command=None,
            reply=response_text,
            backend_name=source_label_for_backend(f"ollama:{resolved_model}:chat"),
            raw_response=response_text,
        )

    async def answer_vision_question(
        self,
        utterance: str,
        image_base64: str,
        *,
        vision_model: str = "",
    ) -> AssistantDecision:
        """Send an image + question to Ollama vision model and get a natural language reply.

        Prefer an English answer from the vision model and then translate it to Russian.
        Vision models such as llava are noticeably less stable when asked to answer in Russian
        directly, so English -> Russian produces better final UI/TTS output.
        """
        if vision_model.strip():
            resolved_vision = vision_model.strip()
        elif self._resolved_model_cache:
            resolved_vision = self._resolved_model_cache
        else:
            resolved_vision = await asyncio.to_thread(self._resolve_model_name_sync)
            self._resolved_model_cache = resolved_vision

        prompt_en = (
            f"{self._rules_block()}"
            "You are a helpful assistant. "
            "You are given a camera frame and the user's question. "
            "Answer the question using only what is visible in the image. "
            "Be concrete about objects, colors, brands, and positions when visible. "
            "If something is uncertain, say so briefly. "
            "Keep your answer to 1-3 short sentences in English.\n"
            f'User question: "{utterance}"'
        )
        payload_en = {
            "model": resolved_vision,
            "prompt": prompt_en,
            "images": [image_base64],
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 120},
        }
        try:
            raw_en = await asyncio.to_thread(self._post_json_sync, "/api/generate", payload_en)
        except RuntimeError as exc:
            return AssistantDecision(
                command=None,
                reply=f"Не удалось отправить изображение в модель: {exc}",
                backend_name=f"vision:{resolved_vision}",
            )

        en_response = str(raw_en.get("response", "")).strip()
        if not en_response:
            return AssistantDecision(
                command=None,
                reply="Не удалось получить содержательный ответ по кадру. Попробуйте ещё раз.",
                backend_name=f"vision:{resolved_vision}",
            )

        if not self._resolved_model_cache:
            self._resolved_model_cache = await asyncio.to_thread(self._resolve_model_name_sync)
        text_model = self._resolved_model_cache

        ru_response = await asyncio.to_thread(
            self._translate_vision_response_to_russian_sync,
            text_model,
            utterance,
            en_response,
        )
        response_text = ru_response or (
            "Не удалось надёжно перевести ответ камеры на русский язык. Попробуйте ещё раз."
        )

        return AssistantDecision(
            command=None,
            reply=response_text,
            backend_name=source_label_for_backend(f"vision:{resolved_vision}"),
            raw_response=en_response,
        )

    def _translate_vision_response_to_russian_sync(
        self,
        text_model: str,
        utterance: str,
        en_response: str,
    ) -> str:
        # Перевод выполняется локально размещённой языковой моделью: раньше
        # текст уходил во внешние переводчики вместе с описанием пользователя.
        prompts = [
            (
                self._rules_block()
                + (
                "Переведи текст ниже на русский язык. "
                "Сохрани смысл и тон. Ответь только переводом на русском языке, без пояснений и без английских фраз.\n"
                f"Контекст: пользователь спросил «{utterance}» и получил ответ по кадру с камеры.\n\n"
                f"{en_response}"
                )
            ),
            (
                self._rules_block()
                + (
                "Ниже дано английское описание кадра с камеры. "
                "Сформулируй короткий ответ пользователю полностью на русском языке. "
                "Не оставляй английские слова, если есть русский эквивалент. "
                "Ответь 1-3 короткими предложениями.\n"
                f"Вопрос пользователя: {utterance}\n"
                f"Английское описание: {en_response}"
                )
            ),
        ]

        for prompt in prompts:
            payload = {
                "model": text_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 160},
            }
            try:
                translate_raw = self._post_json_sync("/api/generate", payload)
            except Exception:
                continue

            ru_response = str(translate_raw.get("response", "")).strip()
            cleaned = _sanitize_vision_russian_reply(ru_response)
            if len(cleaned) >= 10 and _is_mostly_cyrillic(cleaned):
                return cleaned

        return ""

    def _resolve_model_name_sync(self) -> str:
        installed_models = self._list_models_sync()
        if not installed_models:
            return self.model
        if self.model in installed_models:
            return self.model
        if self.fallback_model and self.fallback_model in installed_models:
            return self.fallback_model
        return installed_models[0]

    def warmup_sync(self, model_name: str) -> None:
        """Load model into VRAM with a minimal prompt so it's ready for the first real request."""
        payload = {
            "model": model_name,
            "prompt": "Привет",
            "stream": False,
            "keep_alive": -1,
            "options": {"num_predict": 1},
        }
        try:
            self._post_json_sync("/api/generate", payload)
        except Exception:
            pass

    def _list_models_sync(self) -> list[str]:
        req = request.Request(
            f"{self.base_url}/api/tags",
            headers={"Content-Type": "application/json"},
            method="GET",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except Exception:
            return []

        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError:
            return []

        names: list[str] = []
        for item in parsed.get("models", []):
            name = item.get("name")
            if isinstance(name, str) and name:
                names.append(name)
        return names





def build_assistant_backend(settings: Settings) -> AssistantBackend:
    if settings.ai_backend == "ollama":
        return OllamaAssistantBackend(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            fallback_model=settings.ollama_fallback_model,
            timeout_seconds=settings.ollama_timeout_seconds,
            rules_path=settings.assistant_rules_path,
        )
    return RuleBasedAssistantBackend()


def detect_start_screening_command(utterance: str) -> str | None:
    lowered = utterance.strip().lower()
    start_markers = (
        "нач",
        "старт",
        "запус",
        "скрининг",
        "провер",
        "тест",
        "screen",
        "check",
        "assessment",
    )
    if any(marker in lowered for marker in start_markers):
        return "start_screening"
    return None


def detect_appearance_request(utterance: str) -> str | None:
    lowered = utterance.strip().lower()
    markers = (
        "как я выгляжу",
        "как сегодня выгляжу",
        "как я сегодня выгляжу",
        "как выгляжу",
        "оцени мой внешний вид",
        "оцени мою внешность",
        "посмотри на меня",
        "посмотри в камеру",
        "мое лицо",
        "моё лицо",
        "мой внешний вид",
        "моя внешность",
    )
    if any(marker in lowered for marker in markers):
        return "analyze_appearance"
    return None


def detect_camera_vision_request(utterance: str) -> bool:
    """Detect when the user asks the AI to look at the camera and describe/answer about what it sees."""
    lowered = _normalized_text(utterance)
    markers = (
        "что ты видишь",
        "что видишь",
        "что на камере",
        "что на экране",
        "что перед тобой",
        "опиши что видишь",
        "расскажи что видишь",
        "что ты видишь на камере",
        "посмотри на камеру",
        "что видно на камере",
        "покажи что на камере",
        "что сейчас на камере",
        "что перед камерой",
        "что в кадре",
        "что у меня в руках",
        "что у меня в руке",
        "что я держу",
        "что держу в руках",
        "что у меня перед камерой",
        "что я показываю",
        "что это у меня в руках",
        "what do you see",
        "what is on camera",
        "describe what you see",
        "what am i holding",
        "what is in my hand",
    )
    if any(marker in lowered for marker in markers):
        return True

    regex_patterns = (
        r"\bчто\s+у\s+меня\s+в\s+рук\w*\b",
        r"\bчто\s+это\s+у\s+меня\s+в\s+рук\w*\b",
        r"\bчто\s+я\s+держ\w*\b",
        r"\bчто\s+держ\w*\s+в\s+рук\w*\b",
        r"\bwhat\s+am\s+i\s+hold\w*\b",
        r"\bwhat\s+is\s+in\s+my\s+hand\b",
    )
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in regex_patterns)


def _cleanup_location_phrase(value: str) -> str:
    phrase = re.sub(r"\s+", " ", value.strip(" ?!.,")).strip()
    if not phrase:
        return ""

    words = phrase.split()
    stop_words = {
        "сейчас",
        "сегодня",
        "завтра",
        "послезавтра",
        "пожалуйста",
        "please",
        "now",
        "today",
        "tomorrow",
    }
    filtered = [word for word in words if word.lower() not in stop_words]
    if not filtered:
        return ""

    candidate = " ".join(filtered[:3])
    fixes = {
        "самара": "Самара",
        "самаре": "Самара",
        "москва": "Москва",
        "москве": "Москва",
        "питер": "Санкт-Петербург",
        "питере": "Санкт-Петербург",
        "санкт-петербург": "Санкт-Петербург",
        "санкт-петербурге": "Санкт-Петербург",
        "спб": "Санкт-Петербург",
        "казань": "Казань",
        "казани": "Казань",
        "нижний новгород": "Нижний Новгород",
        "нижнем новгороде": "Нижний Новгород",
        "екатеринбург": "Екатеринбург",
        "екатеринбурге": "Екатеринбург",
        "новосибирск": "Новосибирск",
        "новосибирске": "Новосибирск",
    }
    return fixes.get(candidate.lower(), candidate)


def is_local_only_request(utterance: str) -> bool:
    lowered = _normalized_text(utterance).strip("!?.,")
    if not lowered:
        return True

    simple_markers = (
        "привет",
        "здравствуй",
        "здравствуйте",
        "доброе утро",
        "добрый день",
        "добрый вечер",
        "спасибо",
        "благодарю",
        "пока",
        "до свидания",
        "ок",
        "окей",
        "хорошо",
        "ясно",
        "понятно",
        "как дела",
        "кто ты",
        "что ты умеешь",
        "что ты можешь",
        "как тебя зовут",
    )
    if lowered in simple_markers:
        return True

    processing_markers = (
        "переведи",
        "перевод",
        "translate",
        "перепиши",
        "перефразируй",
        "исправь текст",
        "исправь ошибки",
        "сократи текст",
        "сделай короче",
        "rewrite",
        "rephrase",
    )
    return any(marker in lowered for marker in processing_markers)


def detect_current_date_request(utterance: str) -> bool:
    lowered = _normalized_text(utterance)
    markers = (
        "какое сегодня число",
        "какое сегодня число и день недели",
        "какой сегодня день",
        "какой сегодня день недели",
        "какая сегодня дата",
        "what date is today",
        "what day is it today",
        "what day is today",
        "today's date",
    )
    return any(marker in lowered for marker in markers)


def is_time_sensitive_request(utterance: str) -> bool:
    lowered = _normalized_text(utterance)
    if not lowered:
        return False

    markers = (
        "сейчас",
        "сегодня",
        "последн",
        "актуал",
        "курс",
        "цена",
        "новост",
        "погод",
        "температ",
        "дожд",
        "снег",
        "current",
        "latest",
        "today",
        "news",
        "weather",
        "forecast",
        "temperature",
        "price",
        "rate",
        "президент",
        "премьер",
        "глава государства",
        "president",
        "prime minister",
        "head of state",
    )
    return any(marker in lowered for marker in markers)


def build_current_date_reply(now: datetime | None = None) -> str:
    current = now or datetime.now()
    weekdays = (
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    )
    weekday = weekdays[current.weekday()]
    formatted_date = _format_russian_absolute_date(current)
    return f"Сегодня {formatted_date}, {weekday}."


def _format_russian_absolute_date(value: datetime) -> str:
    months = (
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    )
    return f"{value.day} {months[value.month - 1]} {value.year} года"


def source_label_for_backend(backend_name: str) -> str:
    lowered = backend_name.lower()
    if lowered.startswith("ollama:"):
        return "локальная модель"
    if lowered.startswith("интернет:погода"):
        return "интернет:погода"
    if lowered.startswith("интернет:валюта"):
        return "интернет:валюта"
    if lowered.startswith("интернет:поиск"):
        return "интернет:поиск"
    if lowered.startswith("vision:"):
        return "vision:камера"
    if lowered == "визуальный анализ":
        return "визуальный анализ"
    if lowered == "vision:камера":
        return "vision:камера"
    if lowered == "скрининг":
        return "скрининг"
    return backend_name


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def normalize_user_utterance(utterance: str) -> str:
    cleaned = " ".join(str(utterance or "").split()).strip()
    if not cleaned:
        return ""

    trailing_punctuation = ""
    if cleaned[-1] in "?!.":
        trailing_punctuation = cleaned[-1]

    normalized = _normalized_text(cleaned).replace("…", " ")
    replacements = (
        (r"\bчто\s+у\s+меня\s+в\s+рук\w*\b", "что у меня в руках"),
        (r"\bчто\s+это\s+у\s+меня\s+в\s+рук\w*\b", "что это у меня в руках"),
        (r"\bчто\s+я\s+держ\w*\b", "что я держу"),
        (r"\bчто\s+держ\w*\s+в\s+рук\w*\b", "что держу в руках"),
        (r"\bчто\s+ты\s+вид[ие]\w*\b", "что ты видишь"),
        (r"\bчто\s+вид[ие]\w*\b", "что видишь"),
        (r"\bна\s+кам[еи][рл]\w*\b", "на камере"),
        (r"\bв\s+кадр\w*\b", "в кадре"),
        (r"\bкак\s+я\s+выгл\w*\b", "как я выгляжу"),
        (r"\bкак\s+я\s+сегодня\s+выгл\w*\b", "как я сегодня выгляжу"),
        (r"\bнач(ать|ни)\s+скринин\w*\b", "начать скрининг"),
        (r"\bскрини\w*\b", "скрининг"),
        (r"\b(?:юсей|юэсэй|юэсей|ю\s*эс\s*эй|usa|u\.s\.a\.|u\.s\.|сша)\b", "сша"),
        (r"\bюрсц[иы]\b", "сша"),
        (r"\bсоедин[её]нн\w+\s+штат\w+\b", "сша"),
    )
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

    normalized = re.sub(r"^(?:ну|а|и|слушай|смотри|ээ+|эм+)\s+", "", normalized).strip()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if re.fullmatch(r"(?:кто\s+|последн\w+\s+)?президент\s+сша[.!?]?", normalized):
        normalized = "кто сейчас президент сша"
    if not normalized:
        return ""

    if trailing_punctuation and normalized[-1] not in "?!.":
        normalized = f"{normalized}{trailing_punctuation}"

    return normalized[0].upper() + normalized[1:]


def _sanitize_assistant_reply(reply: str) -> str:
    cleaned = " ".join(str(reply or "").strip().split())
    if not cleaned:
        return "Не могу надёжно ответить на этот вопрос. Повторите его или уточните формулировку."

    lowered = cleaned.lower()
    unreliable_markers = (
        "i am a large language model",
        "i don't understand",
        "i apologize",
        "please provide",
        "without context",
        "provided search results",
        "предоставленные результаты поиска",
        "не понимаю, что вы имеете в виду",
        "не понимаю ваш запрос",
        "используйте команды",
        "команды приложения",
        "подходящая команда не найдена",
        "без контекста",
        "пожалуйста, предоставьте изображение",
    )
    if any(marker in lowered for marker in unreliable_markers):
        return "Не могу надёжно ответить на этот вопрос. Повторите его или уточните формулировку."

    return cleaned


def _sanitize_vision_russian_reply(reply: str) -> str:
    cleaned = " ".join(str(reply or "").strip().split())
    if not cleaned:
        return ""

    lowered = cleaned.lower()
    blocked_markers = (
        "i am a large language model",
        "provided search results",
        "без контекста",
        "please provide",
        "на английском",
    )
    if any(marker in lowered for marker in blocked_markers):
        return ""

    return cleaned


def _is_unsuccessful_assistant_reply(reply: str) -> bool:
    lowered = " ".join(str(reply or "").strip().lower().split())
    if not lowered:
        return True

    bad_markers = (
        "не удалось сформировать ответ",
        "не могу надёжно ответить",
        "не удалось получить надёжный ответ",
        "не имею доступа к актуальным данным",
        "не могу проверить",
        "не понимаю ваш запрос",
        "используйте команды",
        "команды приложения",
        "подходящая команда не найдена",
    )
    return any(marker in lowered for marker in bad_markers)


def _is_mostly_cyrillic(text: str) -> bool:
    letters = [ch for ch in str(text or "") if ch.isalpha()]
    if not letters:
        return False
    cyrillic = sum(1 for ch in letters if "\u0400" <= ch <= "\u04ff")
    return cyrillic / len(letters) >= 0.6
