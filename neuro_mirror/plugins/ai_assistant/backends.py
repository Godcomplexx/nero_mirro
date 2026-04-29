from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib import error, parse, request

from neuro_mirror.core.gpu_scheduler import exclusive_gpu_task_sync
from neuro_mirror.core.settings import Settings
from neuro_mirror.plugins.ai_assistant.rules import load_assistant_rules


@dataclass(slots=True)
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
        weather_enabled: bool = True,
        weather_location: str = "",
        weather_base_url: str = "https://wttr.in",
        currency_enabled: bool = True,
        currency_base_url: str = "https://api.frankfurter.dev",
        internet_fallback_enabled: bool = True,
        internet_fallback_base_url: str = "https://api.duckduckgo.com",
        rules_path: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.fallback_model = fallback_model.strip()
        self.timeout_seconds = timeout_seconds
        self.weather_enabled = weather_enabled
        self.weather_location = weather_location.strip()
        self.weather_base_url = weather_base_url.rstrip("/")
        self.currency_enabled = currency_enabled
        self.currency_base_url = currency_base_url.rstrip("/")
        self.internet_fallback_enabled = internet_fallback_enabled
        self.internet_fallback_base_url = internet_fallback_base_url.rstrip("/")
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

        if self.weather_enabled and detect_weather_request(utterance):
            try:
                weather_reply = await asyncio.to_thread(self._lookup_weather_sync, utterance)
                return AssistantDecision(
                    command=None,
                    reply=weather_reply,
                    backend_name="интернет:погода",
                )
            except Exception as exc:
                return AssistantDecision(
                    command=None,
                    reply=f"Не удалось получить погоду: {exc}",
                    backend_name="интернет:погода",
                )

        if self.currency_enabled and detect_currency_request(utterance):
            try:
                currency_reply = await asyncio.to_thread(self._lookup_currency_sync, utterance)
                return AssistantDecision(
                    command=None,
                    reply=currency_reply,
                    backend_name="интернет:валюта",
                )
            except Exception as exc:
                return AssistantDecision(
                    command=None,
                    reply=f"Не удалось получить курс валют: {exc}",
                    backend_name="интернет:валюта",
                )

        if detect_current_date_request(utterance):
            return AssistantDecision(
                command=None,
                reply=build_current_date_reply(),
                backend_name=self.name,
            )

        if self.internet_fallback_enabled and should_prefer_internet_answer(utterance):
            internet_answer = await self._try_answer_from_internet(resolved_model, utterance)
            if internet_answer is not None:
                return internet_answer

        # Single combined call: classify intent AND answer in one LLM request
        local_answer = await self._classify_and_answer(resolved_model, utterance)
        if local_answer.command is not None:
            return local_answer

        if self.internet_fallback_enabled and should_use_internet_fallback(
            utterance, local_answer.reply
        ):
            try:
                search_results = await asyncio.to_thread(
                    self._lookup_internet_sync, utterance
                )
                summary = await asyncio.to_thread(
                    self._summarize_with_context_sync,
                    resolved_model,
                    utterance,
                    search_results,
                )
                if _is_unsuccessful_assistant_reply(summary):
                    raise RuntimeError("internet summary is empty or unreliable")
                return AssistantDecision(
                    command=None,
                    reply=summary,
                    backend_name="интернет:поиск",
                )
            except Exception:
                fallback_reply = local_answer.reply
                if _is_unsuccessful_assistant_reply(fallback_reply):
                    fallback_reply = (
                        "Не удалось получить надёжный ответ из интернета. "
                        "Повторите вопрос позже или уточните формулировку."
                    )
                return AssistantDecision(
                    command=None,
                    reply=fallback_reply,
                    backend_name=f"{local_answer.backend_name} [без интернета]",
                    raw_response=local_answer.raw_response,
                )

        return local_answer

    async def _try_answer_from_internet(
        self,
        resolved_model: str,
        utterance: str,
    ) -> AssistantDecision | None:
        try:
            search_results = await asyncio.to_thread(
                self._lookup_internet_sync, utterance
            )
            summary = await asyncio.to_thread(
                self._summarize_with_context_sync,
                resolved_model,
                utterance,
                search_results,
            )
        except Exception:
            return None

        if _is_unsuccessful_assistant_reply(summary):
            return None

        return AssistantDecision(
            command=None,
            reply=summary,
            backend_name="интернет:поиск",
        )

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
            '- "none" если это не команда приложения.\n'
            "Для обычного вопроса всегда выбирай command=none.\n"
            "Ответь только JSON по схеме:\n"
            '{"command":"start_screening|analyze_appearance|camera_vision_query|none","reply":"короткий нейтральный текст для UI"}\n'
            "Примеры:\n"
            'Пользователь: "Начать когнитивный скрининг" -> {"command":"start_screening","reply":"Запускаю скрининг."}\n'
            'Пользователь: "Как я сегодня выгляжу?" -> {"command":"analyze_appearance","reply":"Сейчас посмотрю в камеру и дам короткий комментарий."}\n'
            'Пользователь: "Что ты видишь на камере?" -> {"command":"camera_vision_query","reply":"Сейчас посмотрю на камеру и расскажу что вижу."}\n'
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
            "camera_vision_query (что видно на камере).\n"
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
        command = raw_command if raw_command in {"start_screening", "analyze_appearance", "camera_vision_query"} else None
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
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            if path == "/api/generate":
                with exclusive_gpu_task_sync("ollama"):
                    with request.urlopen(req, timeout=self.timeout_seconds) as response:
                        raw_body = response.read().decode("utf-8")
            else:
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
        command = raw_command if raw_command in {"start_screening", "analyze_appearance", "camera_vision_query"} else None
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
        public_translation = self._translate_text_with_public_service_sync(en_response)
        cleaned_public = _sanitize_vision_russian_reply(public_translation)
        if len(cleaned_public) >= 10 and _is_mostly_cyrillic(cleaned_public):
            return cleaned_public

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

    def _translate_text_with_public_service_sync(self, text: str) -> str:
        if not text.strip():
            return ""

        user_agent = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

        google_url = (
            "https://translate.googleapis.com/translate_a/single?"
            + parse.urlencode(
                {
                    "client": "gtx",
                    "sl": "en",
                    "tl": "ru",
                    "dt": "t",
                    "q": text,
                }
            )
        )
        try:
            google_req = request.Request(google_url, headers=user_agent, method="GET")
            with request.urlopen(google_req, timeout=self.timeout_seconds) as response:
                raw_google = response.read().decode("utf-8", errors="replace")
            parsed_google = json.loads(raw_google)
            parts = parsed_google[0] if isinstance(parsed_google, list) and parsed_google else []
            translated = "".join(
                str(item[0]) for item in parts if isinstance(item, list) and item and item[0]
            ).strip()
            if translated:
                return translated
        except Exception:
            pass

        memory_url = (
            "https://api.mymemory.translated.net/get?"
            + parse.urlencode({"q": text, "langpair": "en|ru"})
        )
        try:
            memory_req = request.Request(memory_url, headers=user_agent, method="GET")
            with request.urlopen(memory_req, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw_body)
            response_data = parsed.get("responseData") or {}
            return str(response_data.get("translatedText") or "").strip()
        except Exception:
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

    def _lookup_weather_sync(self, utterance: str) -> str:
        query_location = extract_weather_location(utterance)
        effective_location = query_location or self.weather_location
        location_path = ""
        if effective_location:
            location_path = "/" + parse.quote(effective_location)

        req = request.Request(
            f"{self.weather_base_url.rstrip('/')}{location_path}?format=j1&lang=ru",
            headers={"User-Agent": "NeuroMirror/0.1"},
            method="GET",
        )
        with request.urlopen(req, timeout=self.timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")

        parsed = json.loads(raw_body)
        current = parsed["current_condition"][0]
        desc_list = current.get("lang_ru") or current.get("weatherDesc") or []
        description = desc_list[0].get("value", "") if desc_list else ""
        temp_c = current.get("temp_C", "?")
        feels_like_c = current.get("FeelsLikeC", "?")
        humidity = current.get("humidity", "?")
        wind_kmph = current.get("windspeedKmph", "?")
        area = effective_location or self._extract_area_name(parsed) or "текущая локация"

        return (
            f"Сейчас в {area}: {description}, {temp_c}°C, "
            f"ощущается как {feels_like_c}°C, влажность {humidity}%, ветер {wind_kmph} км/ч."
        )

    def _lookup_currency_sync(self, utterance: str) -> str:
        base_currency, target_currency = extract_currency_pair(utterance)
        urls = self._build_currency_urls(base_currency, target_currency)
        last_error = ""

        for currency_url in urls:
            req = request.Request(
                currency_url,
                headers={"User-Agent": "NeuroMirror/0.1"},
                method="GET",
            )
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as response:
                    raw_body = response.read().decode("utf-8")
            except error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                last_error = f"HTTP {exc.code}: {error_body or 'Not Found'}"
                continue

            parsed = json.loads(raw_body)
            rate, date = self._extract_currency_response(parsed, target_currency)
            return f"1 {base_currency} = {rate} {target_currency} по данным на {date}."

        raise RuntimeError(last_error or "не удалось получить ответ от сервиса валют")

    def _lookup_internet_sync(self, utterance: str) -> list[dict[str, str]]:
        """Search DuckDuckGo HTML and return list of {title, snippet} dicts."""
        encoded_query = parse.quote(utterance)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        req = request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
            method="GET",
        )
        with request.urlopen(req, timeout=self.timeout_seconds) as response:
            raw_html = response.read().decode("utf-8", errors="replace")

        parser = _DuckDuckGoHTMLParser()
        parser.feed(raw_html)
        if not parser.results:
            raise RuntimeError("DuckDuckGo не вернул результатов")
        return parser.results[:5]

    def _summarize_with_context_sync(
        self, resolved_model: str, utterance: str, search_results: list[dict[str, str]]
    ) -> str:
        """Ask Ollama to answer the question using search results as context (RAG)."""
        context_parts = []
        compact_results = search_results[:3]
        for i, item in enumerate(compact_results, 1):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            context_parts.append(f"{i}. {title}\n{snippet}")
        context_text = "\n\n".join(context_parts)
        current_date = _format_russian_absolute_date(datetime.now())

        prompt = self._rules_block() + (
            "Ниже приведены результаты интернет-поиска. "
            "Используй их, чтобы дать точный и краткий ответ на вопрос пользователя.\n"
            "Отвечай на том же языке, что и пользователь. "
            "Держи ответ в пределах 2-4 коротких предложений.\n"
            "Если в результатах нет нужной информации, скажи об этом.\n\n"
            f"Результаты поиска:\n{context_text}\n\n"
            f'Вопрос пользователя: "{utterance}"'
        )
        prompt += (
            f"\n\nCurrent date: {current_date}. "
            'If search results mention other dates, do not refer to them as "today".'
        )

        payload = {
            "model": resolved_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 120},
        }
        raw = self._post_json_sync("/api/generate", payload)
        reply = str(raw.get("response", "")).strip()
        if not reply:
            return self._build_extract_answer_from_search_results(utterance, compact_results)

        cleaned = _sanitize_assistant_reply(reply)
        if _is_unsuccessful_assistant_reply(cleaned):
            return self._build_extract_answer_from_search_results(utterance, compact_results)
        return cleaned

    @staticmethod
    def _build_extract_answer_from_search_results(
        utterance: str,
        search_results: list[dict[str, str]],
    ) -> str:
        snippets: list[str] = []
        for item in search_results:
            snippet = " ".join(str(item.get("snippet", "")).split()).strip()
            if not snippet:
                continue
            if snippet not in snippets:
                snippets.append(snippet)
            if len(snippets) >= 2:
                break

        if snippets:
            parts = []
            for snippet in snippets:
                parts.append(snippet if snippet.endswith((".", "!", "?")) else f"{snippet}.")
            return " ".join(parts)

        titles: list[str] = []
        for item in search_results:
            title = " ".join(str(item.get("title", "")).split()).strip()
            if title and title not in titles:
                titles.append(title)
            if len(titles) >= 2:
                break

        if titles:
            parts = [title if title.endswith((".", "!", "?")) else f"{title}." for title in titles]
            return " ".join(parts)

        return (
            f"Не удалось кратко суммировать результаты поиска по запросу «{utterance}». "
            "Попробуйте уточнить вопрос."
        )

    @staticmethod
    def _extract_area_name(payload: dict) -> str:
        areas = payload.get("nearest_area") or []
        if not areas:
            return ""
        first = areas[0]
        names = first.get("areaName") or []
        if not names:
            return ""
        return str(names[0].get("value", ""))

    def _build_currency_urls(self, base_currency: str, target_currency: str) -> list[str]:
        base_url = self.currency_base_url.rstrip("/")
        lowered = base_url.lower()
        urls: list[str] = []

        if lowered.endswith("/v1"):
            urls.append(f"{base_url}/latest?base={base_currency}&symbols={target_currency}")
            urls.append(f"{base_url}/latest?from={base_currency}&to={target_currency}")
            return urls

        if lowered.endswith("/v2"):
            urls.append(f"{base_url}/rate/{base_currency}/{target_currency}")
            urls.append(f"{base_url}/rates?from={base_currency}&to={target_currency}")
            return urls

        if "frankfurter.dev" in lowered:
            urls.append(f"{base_url}/v2/rate/{base_currency}/{target_currency}")
            urls.append(f"{base_url}/v1/latest?base={base_currency}&symbols={target_currency}")
            urls.append(f"{base_url}/v1/latest?from={base_currency}&to={target_currency}")
            return urls

        if "frankfurter.app" in lowered:
            urls.append(f"{base_url}/latest?base={base_currency}&symbols={target_currency}")
            urls.append(f"{base_url}/latest?from={base_currency}&to={target_currency}")
            return urls

        urls.append(f"{base_url}/v2/rate/{base_currency}/{target_currency}")
        urls.append(f"{base_url}/latest?base={base_currency}&symbols={target_currency}")
        return urls

    @staticmethod
    def _extract_currency_response(payload: dict, target_currency: str) -> tuple[str, str]:
        if "rate" in payload:
            return str(payload["rate"]), str(payload.get("date", ""))

        rates = payload.get("rates", {})
        if isinstance(rates, dict) and target_currency in rates:
            return str(rates[target_currency]), str(payload.get("date", ""))

        amount = payload.get("amount")
        if amount is not None:
            return str(amount), str(payload.get("date", ""))

        raise RuntimeError("целевая валюта отсутствует в ответе сервиса")


class _DuckDuckGoHTMLParser(HTMLParser):
    """Parses DuckDuckGo HTML search results page into a list of {title, snippet}."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] = {}
        self._capture: str | None = None  # "title" or "snippet"
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "") or ""

        if tag == "a" and "result__a" in cls:
            self._capture = "title"
            self._current["title"] = ""
        elif tag == "a" and "result__snippet" in cls:
            self._capture = "snippet"
            self._current["snippet"] = ""
        elif "result__body" in cls or "result__extras" in cls:
            pass

    def handle_endtag(self, tag: str) -> None:
        if self._capture == "title" and tag == "a":
            self._capture = None
        elif self._capture == "snippet" and tag == "a":
            self._capture = None
            if self._current.get("title") or self._current.get("snippet"):
                self.results.append(self._current)
            self._current = {}

    def handle_data(self, data: str) -> None:
        if self._capture == "title":
            self._current["title"] = self._current.get("title", "") + data
        elif self._capture == "snippet":
            self._current["snippet"] = self._current.get("snippet", "") + data


def build_assistant_backend(settings: Settings) -> AssistantBackend:
    if settings.ai_backend == "ollama":
        return OllamaAssistantBackend(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            fallback_model=settings.ollama_fallback_model,
            timeout_seconds=settings.ollama_timeout_seconds,
            weather_enabled=settings.weather_enabled,
            weather_location=settings.weather_location,
            weather_base_url=settings.weather_base_url,
            currency_enabled=settings.currency_enabled,
            currency_base_url=settings.currency_base_url,
            internet_fallback_enabled=settings.internet_fallback_enabled,
            internet_fallback_base_url=settings.internet_fallback_base_url,
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


def detect_weather_request(utterance: str) -> bool:
    lowered = utterance.strip().lower()
    weather_markers = (
        "погод",
        "температ",
        "дожд",
        "снег",
        "weather",
        "temperature",
        "forecast",
        "rain",
        "snow",
    )
    return any(marker in lowered for marker in weather_markers)


def extract_weather_location(utterance: str) -> str:
    text = utterance.strip()
    lowered = text.lower()
    pattern = r"\b(?:в|во|для|по|in|for)\s+([A-Za-zА-Яа-яЁё\- ]{2,})"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match:
        location = _cleanup_location_phrase(match.group(1))
        if location:
            return location

    if lowered.startswith("погода "):
        location = _cleanup_location_phrase(text[7:])
        if location:
            return location

    for alias, normalized in sorted(_weather_location_fixes().items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lowered, flags=re.IGNORECASE):
            return normalized

    return ""


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


def _weather_location_fixes() -> dict[str, str]:
    return {
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


def detect_currency_request(utterance: str) -> bool:
    lowered = utterance.strip().lower()
    currency_markers = (
        "валют",
        "курс",
        "доллар",
        "евро",
        "рубл",
        "usd",
        "eur",
        "rub",
        "exchange rate",
        "currency",
        "dollar",
        "euro",
    )
    return any(marker in lowered for marker in currency_markers)


def extract_currency_pair(utterance: str) -> tuple[str, str]:
    lowered = utterance.strip().lower()
    if "рубл" in lowered and ("доллар" in lowered or "usd" in lowered):
        return "RUB", "USD"
    if "рубл" in lowered and ("евро" in lowered or "eur" in lowered):
        return "RUB", "EUR"
    if "евро" in lowered or "eur" in lowered:
        return "EUR", "RUB"
    if "доллар" in lowered or "usd" in lowered:
        return "USD", "RUB"
    return "USD", "RUB"


def should_use_internet_fallback(utterance: str, local_reply: str) -> bool:
    lowered_reply = local_reply.lower()

    no_access_markers = (
        "не имею доступа",
        "нет доступа",
        "не могу получить",
        "не знаю",
        "не могу проверить",
        "нужен интернет",
        "не понимаю ваш запрос",
        "используйте команды",
        "команды приложения",
        "подходящая команда не найдена",
        "do not have access",
        "don't have access",
        "cannot access",
        "no access",
    )
    if any(marker in lowered_reply for marker in no_access_markers):
        return True

    return is_time_sensitive_request(utterance)


def should_prefer_internet_answer(utterance: str) -> bool:
    lowered = _normalized_text(utterance)
    if not lowered:
        return False
    if is_local_only_request(lowered):
        return False
    if detect_current_date_request(lowered):
        return False
    return is_time_sensitive_request(lowered)


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
