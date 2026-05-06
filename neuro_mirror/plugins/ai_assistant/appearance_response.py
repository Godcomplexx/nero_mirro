from __future__ import annotations

import asyncio
import json
import logging
import time
import re
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from neuro_mirror.core.gpu_scheduler import exclusive_gpu_task_sync
from neuro_mirror.plugins.ai_assistant.appearance_memory import (
    AppearanceMemoryStore,
    build_memory_note,
)
from neuro_mirror.plugins.ai_assistant.rules import load_assistant_rules

_log = logging.getLogger("neuro_mirror.appearance_response")


_EMOTION_FALLBACK: dict[str, str] = {
    "positive": "Ты выглядишь тепло и располагающе.",
    "negative": "У тебя выразительный и запоминающийся взгляд.",
    "neutral": "Ты выглядишь уверенно и спокойно.",
}
_POSITIVE_EMOTIONS: frozenset[str] = frozenset({"радость", "удивление"})
_NEGATIVE_EMOTIONS: frozenset[str] = frozenset({"грусть", "злость", "страх", "отвращение", "презрение"})


def _is_health_alert(wellness_suggestion: str) -> bool:
    lowered = wellness_suggestion.lower()
    return any(marker in lowered for marker in ("покрасн", "давлен", "скрининг", "груст", "задумч", "устал"))


def _emotion_fallback(emotion: str) -> str:
    if emotion in _POSITIVE_EMOTIONS:
        return _EMOTION_FALLBACK["positive"]
    if emotion in _NEGATIVE_EMOTIONS:
        return _EMOTION_FALLBACK["negative"]
    return _EMOTION_FALLBACK["neutral"]


@dataclass(slots=True)
class AppearanceResponseComposer:
    enabled: bool
    ai_backend: str
    ollama_base_url: str
    ollama_model: str
    ollama_vision_model: str
    timeout_seconds: float
    rules_path: str = ""
    memory_store: AppearanceMemoryStore | None = None

    def _rules_block(self) -> str:
        rules = load_assistant_rules(self.rules_path)
        return f"Общие правила поведения ассистента:\n{rules}\n\n"

    def _list_ollama_model_items_sync(self) -> list[dict[str, Any]]:
        try:
            req = request.Request(
                f"{self.ollama_base_url.rstrip('/')}/api/tags",
                method="GET",
            )
            with request.urlopen(req, timeout=min(max(self.timeout_seconds, 5.0), 10.0)) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning("Could not list Ollama models: %s", exc)
            return []

        raw_models = parsed.get("models")
        if not isinstance(raw_models, list):
            return []
        return [item for item in raw_models if isinstance(item, dict)]

    def _installed_model_names_sync(self) -> list[str]:
        model_names = [
            str(item.get("name") or "").strip()
            for item in self._list_ollama_model_items_sync()
        ]
        return [name for name in model_names if name]

    def _resolve_vision_model_sync(self) -> str:
        configured = (self.ollama_vision_model or "").strip()
        fallback = (self.ollama_model or "").strip()
        selected = configured or fallback
        if not configured:
            return selected

        model_items = self._list_ollama_model_items_sync()
        if not model_items:
            return selected

        model_names = [str(item.get("name") or "").strip() for item in model_items]
        model_names = [name for name in model_names if name]

        if configured in model_names:
            return configured

        latest_name = f"{configured}:latest"
        if latest_name in model_names:
            _log.info("Resolved Ollama vision model %r to %r", configured, latest_name)
            return latest_name

        configured_base = configured.split(":", 1)[0]
        for name in model_names:
            if name.split(":", 1)[0] == configured_base:
                _log.info("Resolved Ollama vision model %r to installed tag %r", configured, name)
                return name

        for item in model_items:
            name = str(item.get("name") or "").strip()
            details = item.get("details") if isinstance(item.get("details"), dict) else {}
            families = details.get("families") if isinstance(details, dict) else None
            family_text = " ".join(str(value).lower() for value in families) if isinstance(families, list) else ""
            lowered_name = name.lower()
            if name and ("clip" in family_text or "llava" in lowered_name or "vision" in lowered_name):
                _log.info("Using installed vision-capable Ollama model %r instead of configured %r", name, configured)
                return name

        _log.warning("Configured Ollama vision model %r was not found in installed models: %s", configured, model_names)
        return selected

    def _text_model_candidates_sync(self) -> list[str]:
        installed = self._installed_model_names_sync()
        candidates: list[str] = []
        primary = (self.ollama_model or "").strip()
        if primary:
            candidates.append(primary)

        for preferred in ("qwen2.5:latest", "qwen2.5", "llama3.2:latest", "llama3.1:latest"):
            if preferred in installed:
                candidates.append(preferred)

        for name in installed:
            lowered = name.lower()
            if any(marker in lowered for marker in ("qwen", "llama", "mistral", "gemma")):
                candidates.append(name)

        result: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in result:
                result.append(candidate)
        return result

    def _generate_text_with_fallback_sync(
        self,
        prompt: str,
        *,
        options: dict[str, Any],
        timeout_seconds: float,
        purpose: str,
    ) -> str:
        last_error = ""
        for model in self._text_model_candidates_sync():
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": options,
            }
            body = json.dumps(payload).encode("utf-8")
            req = request.Request(
                f"{self.ollama_base_url.rstrip('/')}/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with exclusive_gpu_task_sync("ollama"):
                    with request.urlopen(req, timeout=timeout_seconds) as resp:
                        raw_body = resp.read().decode("utf-8")
                parsed = json.loads(raw_body)
            except (error.URLError, error.HTTPError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                _log.warning("%s with model %r failed: %s", purpose, model, exc)
                continue

            if parsed.get("error"):
                last_error = str(parsed["error"])
                _log.warning("%s model %r returned Ollama error: %s", purpose, model, parsed["error"])
                continue

            response_text = str(parsed.get("response") or "").strip()
            if response_text:
                if model != self.ollama_model:
                    _log.info("%s used fallback text model %r", purpose, model)
                return response_text

            _log.info("%s model %r returned empty response; trying next model", purpose, model)

        if last_error:
            _log.warning("%s failed for all text models; last error: %s", purpose, last_error)
        else:
            _log.warning("%s failed: no usable text models found", purpose)
        return ""

    async def compose(self, analysis: dict[str, Any]) -> str:
        # --- Step 1: try to get a rich visual description via Ollama Vision ---
        _t_start = time.perf_counter()
        emotion_val = str(analysis.get("emotion") or "").strip().lower()
        if self.enabled and self.ai_backend == "ollama":
            frame_b64 = str(analysis.get("frame_base64") or "").strip()
            has_desc = bool(analysis.get("appearance_description"))
            if frame_b64:
                analysis["vision_status"] = "started"
            else:
                analysis["vision_status"] = "frame_base64_missing"
            _log.info(
                "compose: frame_base64=%s, existing_description=%s, face=%s, emotion=%s",
                f"{len(frame_b64)} chars" if frame_b64 else "MISSING",
                f"{len(str(analysis.get('appearance_description', '')))} chars" if has_desc else "NONE",
                analysis.get("face_detected"),
                analysis.get("emotion"),
            )
            if frame_b64 and not has_desc:
                try:
                    # If subclass overrides _describe_appearance_with_vision_sync (e.g. tests),
                    # use that method directly (sequential). Otherwise use the parallel path.
                    _overridden = (
                        type(self)._describe_appearance_with_vision_sync
                        is not AppearanceResponseComposer._describe_appearance_with_vision_sync
                    )
                    if _overridden:
                        vision_desc = await asyncio.to_thread(
                            self._describe_appearance_with_vision_sync, frame_b64, analysis
                        )
                        inferred_result: dict[str, str] | BaseException = {}
                        if vision_desc:
                            analysis["appearance_description"] = vision_desc
                            analysis["vision_status"] = "ok:en_to_ru"
                            try:
                                inferred_result = await asyncio.to_thread(
                                    self._infer_all_sync, vision_desc, emotion_val
                                )
                            except Exception:
                                pass
                        else:
                            analysis["vision_status"] = "empty:en_to_ru"
                        if isinstance(inferred_result, dict):
                            if inferred_result.get("style"):
                                analysis["inferred_style"] = inferred_result["style"]
                            if inferred_result.get("mood"):
                                analysis["inferred_mood"] = inferred_result["mood"]
                            if inferred_result.get("wellness"):
                                analysis["inferred_wellness"] = inferred_result["wellness"]
                            if inferred_result.get("opening"):
                                analysis["emotion_opening"] = inferred_result["opening"]
                    else:
                        _log.info("compose: Step A — getting EN description from vision model")
                        _t_a = time.perf_counter()
                        en_desc = await asyncio.to_thread(
                            self._vision_get_en_description_sync, frame_b64, emotion_val
                        )
                        if en_desc:
                            _log.info("compose: EN ready (%d chars) in %.1fs, running translation + inference in parallel", len(en_desc), time.perf_counter() - _t_a)
                            _t_b = time.perf_counter()
                            ru_desc, inferred = await asyncio.gather(
                                asyncio.to_thread(self._translate_en_description_sync, en_desc),
                                asyncio.to_thread(self._infer_all_sync, en_desc, emotion_val),
                                return_exceptions=True,
                            )
                            _log.info("compose: translate+infer gather done in %.1fs", time.perf_counter() - _t_b)
                            if isinstance(ru_desc, str) and ru_desc:
                                analysis["appearance_description"] = ru_desc
                                analysis["vision_status"] = "ok:en_to_ru"
                            else:
                                _log.warning("compose: translation empty, trying direct RU fallback")
                                analysis["vision_status"] = "empty:en_to_ru"
                                direct_desc = await asyncio.to_thread(
                                    self._describe_appearance_direct_russian_sync, frame_b64, analysis
                                )
                                if direct_desc:
                                    analysis["appearance_description"] = direct_desc
                                    analysis["vision_status"] = "ok:direct_ru"
                                else:
                                    analysis["vision_status"] = "empty:direct_ru"
                            if isinstance(inferred, dict):
                                if inferred.get("style"):
                                    analysis["inferred_style"] = inferred["style"]
                                if inferred.get("mood"):
                                    analysis["inferred_mood"] = inferred["mood"]
                                if inferred.get("wellness"):
                                    analysis["inferred_wellness"] = inferred["wellness"]
                                if inferred.get("opening"):
                                    analysis["emotion_opening"] = inferred["opening"]
                        else:
                            _log.warning("compose: EN description empty, trying direct RU fallback")
                            analysis["vision_status"] = "empty:en_to_ru"
                            direct_desc = await asyncio.to_thread(
                                self._describe_appearance_direct_russian_sync, frame_b64, analysis
                            )
                            if direct_desc:
                                analysis["appearance_description"] = direct_desc
                                analysis["vision_status"] = "ok:direct_ru"
                            else:
                                analysis["vision_status"] = "empty:direct_ru"
                except Exception as exc:
                    _log.warning("Vision appearance description failed: %s", exc)
                    analysis["vision_status"] = f"error:{exc}"
        else:
            _log.info("compose: skipping Vision pipeline (enabled=%s, backend=%s)", self.enabled, self.ai_backend)
            analysis["vision_status"] = "skipped"

        # If inference hasn't run yet (no frame_b64 path), run it now on existing description
        desc_for_inference = str(analysis.get("appearance_description") or "").strip()
        if (
            self.enabled
            and self.ai_backend == "ollama"
            and desc_for_inference
            and "inferred_style" not in analysis
            and "emotion_opening" not in analysis
        ):
            try:
                inferred = await asyncio.to_thread(
                    self._infer_all_sync, desc_for_inference, emotion_val
                )
                if isinstance(inferred, dict):
                    if inferred.get("style"):
                        analysis["inferred_style"] = inferred["style"]
                    if inferred.get("mood"):
                        analysis["inferred_mood"] = inferred["mood"]
                    if inferred.get("wellness"):
                        analysis["inferred_wellness"] = inferred["wellness"]
                    if inferred.get("opening"):
                        analysis["emotion_opening"] = inferred["opening"]
            except Exception:
                pass

        checklist = self._build_appearance_checklist(analysis)
        if self._has_checklist_info(checklist):
            memory_note = ""
            if self.memory_store is not None:
                memory_note = build_memory_note(checklist, self.memory_store.recent())
            wellness_suggestion = self._build_wellness_suggestion(checklist, analysis)
            analysis["appearance_checklist"] = checklist
            analysis["appearance_memory_notes"] = memory_note
            analysis["wellness_suggestion"] = wellness_suggestion

            if self.enabled and self.ai_backend == "ollama":
                try:
                    # Pass wellness_suggestion only as context for LLM when it's not a health alert
                    llm_wellness = wellness_suggestion if not _is_health_alert(wellness_suggestion) else ""
                    reply = await asyncio.to_thread(
                        self._build_reply_with_llm_sync,
                        checklist, memory_note, llm_wellness,
                    )
                except Exception:
                    reply = ""
            else:
                reply = ""
            if not reply:
                reply = self._build_personal_appearance_reply(
                    checklist,
                    memory_note=memory_note,
                    wellness_suggestion=wellness_suggestion,
                )
            if self.memory_store is not None and analysis.get("appearance_description"):
                self.memory_store.append(checklist)

            # Health-alert wellness is appended after shortening so it's never truncated
            if wellness_suggestion and _is_health_alert(wellness_suggestion):
                short_reply = self._shorten_voice_reply(reply, max_sentences=2, max_chars=280)
                result = f"{short_reply.rstrip()} {wellness_suggestion}"
            else:
                result = self._shorten_voice_reply(reply, max_sentences=3, max_chars=430)
            _log.info("compose: done via checklist path in %.1fs total", time.perf_counter() - _t_start)
            return result

        # --- Step 2: build template from analysis data ---
        template = self._build_template(analysis)
        if str(analysis.get("vision_status") or "").startswith("ok:"):
            _log.info("compose: done via template(ok) path in %.1fs total", time.perf_counter() - _t_start)
            return self._shorten_voice_reply(template)
        if not self.enabled or self.ai_backend != "ollama":
            _log.info("compose: done via template(offline) path in %.1fs total", time.perf_counter() - _t_start)
            return self._shorten_voice_reply(template)

        # --- Step 3: polish the template with LLM rewrite ---
        try:
            polished = await asyncio.to_thread(self._rewrite_with_ollama_sync, template, analysis)
        except Exception:
            _log.warning("compose: LLM rewrite failed, returning template")
            _log.info("compose: done via rewrite-fallback path in %.1fs total", time.perf_counter() - _t_start)
            return template

        _log.info("compose: done via rewrite path in %.1fs total", time.perf_counter() - _t_start)
        return self._shorten_voice_reply(self._sanitize_polished_response(polished, template))

    def _build_template(self, analysis: dict[str, Any]) -> str:
        emotion = str(analysis.get("emotion") or "").strip().lower()
        observed = str(analysis.get("observed") or "").strip()
        appearance_desc = self._normalize_generated_description(
            str(analysis.get("appearance_description") or "").strip()
        )
        if appearance_desc:
            return appearance_desc

        if not analysis.get("face_detected"):
            return (
                "Я не получила уверенное описание человека от vision-модели. "
                "Проверь, что кадр дошёл до анализа и Ollama vision-модель доступна."
            )

        # --- Emotion → opening line (LLM-generated or 3-bucket fallback) ---
        opening = (
            str(analysis.get("emotion_opening") or "").strip()
            or _emotion_fallback(emotion)
        )

        # --- Rich description or basic observation ---
        if appearance_desc:
            observation = appearance_desc
        elif observed:
            observation = self._normalize_observed_text(observed, emotion)
            if self._is_generic_observation(observation):
                return self._no_detailed_appearance_reply(analysis)
            if not self._is_safe_russian_output(
                observation,
                min_cyrillic_ratio=0.78,
                max_foreign_tokens=1,
            ):
                observation = self._generic_observation(emotion)
        else:
            observation = self._generic_observation(emotion)

        closing = (
            "В целом, твой образ воспринимается гармонично и цельно — "
            "в этом есть своя индивидуальность."
        )

        return f"{opening}\n\n{observation}\n\n{closing}"

    def _build_appearance_checklist(self, analysis: dict[str, Any]) -> dict[str, str]:
        has_vision_description = bool(str(analysis.get("appearance_description") or "").strip())
        description = " ".join(
            str(value or "").strip()
            for value in (
                analysis.get("appearance_description"),
                analysis.get("observed"),
            )
            if value
        )
        emotion = str(analysis.get("emotion") or "").strip().lower()
        if not description and not emotion:
            return {}
        if not has_vision_description and not emotion:
            return {}

        checklist = {
            "hair": self._find_sentence(
                description,
                ("волос", "причес", "причёс", "светл", "тёмн", "темн", "рыж", "каштан"),
            ),
            "clothing": self._find_sentence(
                description,
                ("одеж", "кофт", "худи", "толстов", "блуз", "футбол", "свитер", "рубаш", "плать", "куртк"),
            ),
            "accessories": self._find_sentence(
                description,
                ("наушник", "очки", "серёж", "сереж", "украшен", "цепоч", "аксесс", "час"),
            ),
            "style": (
                str(analysis.get("inferred_style") or "").strip()
                or (self._infer_style(description) if has_vision_description else "")
            ),
            "mood": (
                str(analysis.get("inferred_mood") or "").strip()
                or self._infer_mood(description, emotion)
            ),
            "wellness": (
                str(analysis.get("inferred_wellness") or "").strip()
                or self._infer_wellness_observation(description, emotion)
            ),
            "summary": self._find_sentence(
                description,
                ("аккурат", "опрят", "ухож", "спокой", "сосредоточ", "образ", "впечатлен", "впечатл"),
            ) or self._shorten_voice_reply(description, max_sentences=1, max_chars=180),
        }
        face_expression = self._find_sentence(
            description,
            ("лицо", "взгляд", "выражен", "улыб", "груст", "печал", "задум", "спокой", "сосредоточ"),
        )
        if face_expression:
            checklist["face_expression"] = face_expression
        background = self._find_sentence(
            description,
            ("фон", "стен", "стол", "монитор", "компьютер", "окно", "свет", "освещ"),
        )
        if background:
            checklist["background"] = background

        return {key: value for key, value in checklist.items() if value}

    @staticmethod
    def _has_checklist_info(checklist: dict[str, str]) -> bool:
        useful_fields = ("hair", "clothing", "accessories", "face_expression", "style", "mood", "wellness")
        return any(str(checklist.get(field) or "").strip() for field in useful_fields)

    @staticmethod
    def _find_sentence(text: str, keywords: tuple[str, ...]) -> str:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return ""
        sentences = re.findall(r"[^.!?]+[.!?]?", cleaned, flags=re.UNICODE) or [cleaned]
        for sentence in sentences:
            lowered = sentence.lower()
            if any(keyword in lowered for keyword in keywords):
                return sentence.strip().rstrip(".!?")
        return ""

    def _infer_all_sync(
        self, description: str, emotion: str
    ) -> dict[str, str]:
        """Single LLM call that returns style, mood, wellness, and emotion_opening together."""
        emotion_line = f"Эмоция по модели: «{emotion}».\n" if emotion else ""
        prompt = (
            "Извлеки из описания ниже только то, что явно упомянуто. "
            "Ответь строго JSON без пояснений, markdown и лишних символов.\n"
            "Если информации для поля нет — оставь пустую строку.\n"
            "НЕ додумывай и НЕ домысливай ничего, чего нет в описании.\n\n"
            "{\n"
            '  "style": "<фраза вида \'спокойный сдержанный образ\' на основе цветов, без типов одежды, иначе пустая строка>",\n'
            '  "mood": "<одно прилагательное или короткая фраза: \'спокойный\', \'немного грустный\' — ТОЛЬКО если явно в описании, иначе пустая строка>",\n'
            '  "wellness": "<самочувствие ТОЛЬКО если явный визуальный признак в описании, иначе пустая строка>",\n'
            '  "opening": "<1 тёплое предложение о конкретных деталях из описания, обращение на ты, без домыслов>"\n'
            "}\n\n"
            f"{emotion_line}"
            f"Описание: {description[:400]}"
        )
        result = self._generate_text_with_fallback_sync(
            prompt,
            options={"temperature": 0.5, "num_predict": 140},
            timeout_seconds=max(self.timeout_seconds, 20.0),
            purpose="Appearance inference",
        )
        try:
            json_start = result.find("{")
            json_end = result.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(result[json_start:json_end])
                out: dict[str, str] = {}
                for key in ("style", "mood", "wellness", "opening"):
                    val = " ".join(str(parsed.get(key) or "").split()).strip()
                    if val:
                        out[key] = val
                return out
        except (json.JSONDecodeError, AttributeError):
            pass
        return {}

    @staticmethod
    def _infer_style(description: str) -> str:
        lowered = str(description or "").lower()
        if any(word in lowered for word in ("аккурат", "опрят", "ухож")):
            return "аккуратный и опрятный образ"
        if any(word in lowered for word in ("худи", "толстов", "кофт", "футбол", "наушник")):
            return "спокойный повседневный образ"
        if any(word in lowered for word in ("блуз", "рубаш", "плать")):
            return "мягкий собранный образ"
        return "спокойный аккуратный образ"

    @staticmethod
    def _infer_mood(description: str, emotion: str) -> str:
        lowered = f"{description} {emotion}".lower()
        if any(word in lowered for word in ("грусть", "груст", "печал", "задум")):
            return "задумчивое или немного грустное настроение"
        if any(word in lowered for word in ("устал", "сонн", "напряж")):
            return "немного уставшее настроение"
        if any(word in lowered for word in ("радость", "улыб", "жив")):
            return "живое и открытое настроение"
        if any(word in lowered for word in ("спокой", "сосредоточ")):
            return "спокойное и сосредоточенное настроение"
        return ""

    @staticmethod
    def _infer_wellness_observation(description: str, emotion: str) -> str:
        lowered = f"{description} {emotion}".lower()
        if any(word in lowered for word in ("красное лицо", "лицо красн", "покрасн", "румян")):
            return "лицо выглядит немного покрасневшим"
        if any(word in lowered for word in ("грусть", "груст", "печал", "устал", "задум")):
            return "видно немного грустное или уставшее настроение"
        return ""

    def _build_wellness_suggestion(self, checklist: dict[str, str], analysis: dict[str, Any]) -> str:
        wellness = str(checklist.get("wellness") or "").lower()
        mood = str(checklist.get("mood") or "").lower()
        emotion = str(analysis.get("emotion") or "").lower()
        description = str(analysis.get("appearance_description") or analysis.get("observed") or "").lower()
        # Always check raw description for redness — LLM wellness field may miss it
        redness_signal = (
            "покрас" in wellness or "красн" in wellness
            or any(w in description for w in ("покрасн", "красное лицо", "лицо красн", "румян"))
        )
        if redness_signal:
            return (
                "Лицо выглядит немного покрасневшим; это может быть свет, жара или усталость. "
                "Если чувствуешь себя неважно, лучше измерить давление или пройти короткий скрининг."
            )
        if any(marker in f"{wellness} {mood} {emotion}" for marker in ("груст", "печал", "устал", "задум")):
            return "Взгляд кажется немного грустным или задумчивым; если хочешь, можем пройти короткий скрининг или просто поговорить."
        return ""

    def _build_reply_with_llm_sync(
        self,
        checklist: dict[str, str],
        memory_note: str,
        wellness_suggestion: str,
    ) -> str:
        details_lines = []
        for key in ("hair", "clothing", "accessories", "face_expression", "style", "mood"):
            val = str(checklist.get(key) or "").strip()
            if val:
                details_lines.append(f"- {key}: {val}")
        details_block = "\n".join(details_lines) if details_lines else "(детали не определены)"

        memory_block = f"Изменения по сравнению с прошлым визитом: {memory_note}" if memory_note else ""
        wellness_block = f"Наблюдение о самочувствии: {wellness_suggestion}" if wellness_suggestion else ""

        context_parts = [details_block]
        if memory_block:
            context_parts.append(memory_block)
        if wellness_block:
            context_parts.append(wellness_block)

        prompt = (
            "Ты — ассистент умного зеркала. Пользователь спросил, как он выглядит.\n"
            "Напиши тёплый живой ответ из 2–3 предложений СТРОГО на основе наблюдений ниже.\n\n"
            "ПРАВИЛА (нарушение делает ответ плохим):\n"
            "- Упоминай ТОЛЬКО то, что есть в наблюдениях — не домысливай позу, настроение, намерения.\n"
            "- Не называй тип одежды (куртка, рубашка, худи и т.д.) — говори о цветах и общем впечатлении.\n"
            "- Если видны цвета — скажи, что этот цвет или сочетание тебе идёт.\n"
            "- Обращайся на «ты», тон тёплый и конкретный.\n"
            "- Не начинай с «Ты выглядишь аккуратно» — придумай другое начало.\n"
            "- Если есть изменения по сравнению с прошлым — упомяни их естественно.\n"
            "- Максимум 3 коротких предложения. Не перечисляй всё подряд.\n"
            "- Ответь только текстом, без заголовков, кавычек и пояснений.\n\n"
            "Наблюдения:\n"
            + "\n".join(context_parts)
        )
        result = self._generate_text_with_fallback_sync(
            prompt,
            options={"temperature": 0.45, "num_predict": 120},
            timeout_seconds=max(self.timeout_seconds, 20.0),
            purpose="Appearance reply",
        )
        cleaned = " ".join(result.split()).strip()
        if not self._is_safe_russian_output(cleaned, min_cyrillic_ratio=0.70, max_foreign_tokens=4):
            return ""
        return cleaned

    def _build_personal_appearance_reply(
        self,
        checklist: dict[str, str],
        *,
        memory_note: str,
        wellness_suggestion: str,
    ) -> str:
        detail = self._best_compliment_detail(checklist)
        opening = "Ты выглядишь аккуратно и ухоженно"
        if detail:
            opening = f"{opening}: {detail}."
        else:
            style = checklist.get("style") or ""
            if style:
                opening = f"{opening}. {self._style_as_sentence(style)}"
            else:
                opening = f"{opening}."

        parts = [opening]
        if memory_note:
            parts.append(memory_note)
        if wellness_suggestion:
            parts.append(wellness_suggestion)
        elif checklist.get("mood"):
            parts.append(f"{self._mood_as_sentence(checklist['mood'])} Если нужно — я рядом.")
        else:
            parts.append("В целом образ выглядит спокойным и приятным.")
        return " ".join(parts)

    @staticmethod
    def _style_as_sentence(style: str) -> str:
        """Turn a style value into a grammatically correct Russian sentence."""
        s = style.strip().rstrip(".")
        lowered = s.lower()
        # already a full sentence-like phrase with a noun
        if any(w in lowered for w in ("образ", "стиль", "look", "вид")):
            return s[0].upper() + s[1:] + "."
        # adjectives only (no noun) — wrap into sentence
        return f"Образ смотрится {lowered}."

    @staticmethod
    def _mood_as_sentence(mood: str) -> str:
        """Turn a mood value into a grammatically correct Russian sentence."""
        s = mood.strip().rstrip(".")
        lowered = s.lower()
        # already contains a verb-compatible phrasing
        if any(w in lowered for w in ("настроение", "состояние")):
            # e.g. "спокойное и сосредоточенное настроение" → "У тебя спокойное настроение."
            return f"У тебя {lowered}."
        # short adjective / phrase — wrap naturally
        return f"Выглядишь {lowered}."

    @staticmethod
    def _best_compliment_detail(checklist: dict[str, str]) -> str:
        clothing = str(checklist.get("clothing") or "").strip()
        hair = str(checklist.get("hair") or "").strip()
        accessories = str(checklist.get("accessories") or "").strip()
        if clothing:
            color = AppearanceResponseComposer._extract_color_phrase(clothing)
            if color:
                return f"{color} тебе очень идёт"
            return "это цветовое сочетание смотрится на тебе гармонично"
        if hair:
            return "волосы выглядят аккуратно и хорошо обрамляют лицо"
        if accessories:
            return "аксессуары хорошо дополняют образ"
        return ""

    @staticmethod
    def _extract_color_phrase(text: str) -> str:
        lowered = text.lower()
        color_words = (
            "чёрн", "черн", "бел", "серый", "серо", "синий", "синего", "голуб",
            "красн", "зелён", "зелен", "жёлт", "желт", "коричнев", "бежев",
            "розов", "фиолет", "оранж", "тёмн", "темн", "светл",
        )
        found = [w for w in color_words if w in lowered]
        if not found:
            return ""
        # return first matched word as it appears in original text (title-cased)
        for word in found:
            idx = lowered.find(word)
            if idx >= 0:
                fragment = text[idx: idx + len(word) + 4].split()[0]
                return f"этот {fragment.lower()} цвет"
        return ""

    @staticmethod
    def _is_generic_observation(observed: str) -> bool:
        cleaned = " ".join(str(observed or "").lower().split())
        generic_markers = (
            "лицо хорошо видно в кадре",
            "лицо в кадре найдено",
            "лицо не удалось уверенно выделить",
            "черты лица видны неидеально",
        )
        return any(marker in cleaned for marker in generic_markers)

    @staticmethod
    def _no_detailed_appearance_reply(analysis: dict[str, Any]) -> str:
        if not analysis.get("face_detected"):
            return (
                "Я не получила детальное описание от vision-модели, поэтому не буду придумывать детали кадра. "
                "Проверь, что Ollama запущена и vision-модель доступна."
            )
        return (
            "Лицо в кадре видно, но vision-модель не вернула детальное описание всего кадра. "
            "Я не буду придумывать волосы, одежду, предметы или фон; проверь доступность Ollama vision-модели."
        )

    @staticmethod
    def _generic_observation(emotion: str) -> str:
        """Fallback when no vision description is available."""
        emotion_observation = {
            "радость": "У тебя открытый, располагающий взгляд, который создаёт ощущение тепла.",
            "спокойствие": "У тебя уверенный, спокойный взгляд, который создаёт ощущение гармонии.",
            "удивление": "У тебя любопытный, живой взгляд, который создаёт ощущение энергии.",
            "грусть": "У тебя задумчивый, глубокий взгляд, который создаёт ощущение искренности.",
        }
        base = emotion_observation.get(
            emotion,
            "У тебя уверенный взгляд, который создаёт приятное впечатление.",
        )
        return (
            f"{base} "
            "Лицо видно в кадре, но детальная vision-модель сейчас не вернула описание волос, одежды, аксессуаров и фона."
        )

    def _vision_get_en_description_sync(
        self, frame_base64: str, emotion: str
    ) -> str:
        """Step A: ask vision model for English description. Returns raw EN text or empty string."""
        vision_model = self._resolve_vision_model_sync()
        emotion_hint = f" The emotion model detected the mood as '{emotion}'." if emotion else ""
        prompt_en = (
            "You are a visual assistant for a smart mirror. Describe ONLY what is unmistakably visible.\n\n"
            "Use this order, skip any section you are not 100% certain about:\n"
            "- HAIR: color and length only if clearly visible (e.g. 'dark red shoulder-length hair')\n"
            "- CLOTHING COLOR: state the single most dominant color you can clearly see on the clothing — if you are not certain, skip this entirely\n"
            "- ACCESSORIES: headphones, glasses, earrings — only if unambiguously visible\n"
            "- FACE: one word for expression (e.g. 'neutral', 'slight smile')\n\n"
            "STRICT RULES:\n"
            "- If you are not certain about the clothing color — DO NOT mention clothing at all\n"
            "- Do NOT name garment types (jacket, shirt, hoodie, blouse, etc.)\n"
            "- Do NOT describe texture, patterns, or contrast unless unmistakably obvious\n"
            "- Do NOT describe posture, body language, or actions\n"
            "- Do NOT infer mood, age, profession, or identity\n"
            "- Do NOT use 'appears to', 'seems to', 'looks like'\n"
            "- Do NOT invent any detail — uncertainty = omit\n"
            "- Answer in 2-3 short factual sentences in English.\n"
            f"{emotion_hint}"
        )
        payload = {
            "model": vision_model,
            "prompt": prompt_en,
            "images": [frame_base64],
            "stream": False,
            "options": {"temperature": 0.15, "num_predict": 200},
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.ollama_base_url.rstrip('/')}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with exclusive_gpu_task_sync("ollama"):
                with request.urlopen(req, timeout=max(self.timeout_seconds, 45.0)) as resp:
                    raw_body = resp.read().decode("utf-8")
        except (error.URLError, error.HTTPError) as exc:
            _log.warning("Vision describe failed: %s", exc)
            return ""

        parsed = json.loads(raw_body)
        if parsed.get("error"):
            _log.warning("Vision model %r returned Ollama error: %s", vision_model, parsed["error"])
            return ""
        en_description = str(parsed.get("response") or "").strip()
        _log.info("Vision EN description (%d chars): %.200s", len(en_description), en_description)
        if len(en_description) < 15:
            _log.warning("Vision returned too short response: %r", en_description)
            return ""
        return en_description

    def _describe_appearance_with_vision_sync(
        self, frame_base64: str, analysis: dict[str, Any]
    ) -> str:
        """Sequential EN→RU pipeline kept for subclass overrides in tests."""
        emotion = str(analysis.get("emotion") or "").strip()
        en_desc = self._vision_get_en_description_sync(frame_base64, emotion)
        if not en_desc:
            return ""
        return self._translate_en_description_sync(en_desc)

    def _translate_en_description_sync(self, en_description: str) -> str:
        translate_prompt = self._rules_block() + (
            "Переведи описание всего кадра ниже на русский язык.\n\n"
            "Правила перевода:\n"
            "- Сделай текст тёплым, доброжелательным и естественным.\n"
            "- Обращайся на «ты».\n"
            "- ОБЯЗАТЕЛЬНО сохрани ВСЕ упомянутые детали: человека, лицо, волосы, цвета одежды, аксессуары, предметы, фон и освещение.\n"
            "- Если в оригинале упомянуты цвета одежды или тип причёски — они ДОЛЖНЫ быть в переводе.\n"
            "- НЕ называй тип одежды (куртка, рубашка, худи и т.д.) — говори только о цветах.\n"
            "- Не делай полный пересказ: выбери самые важные видимые детали и обобщи их.\n"
            "- Ответь только переводом-резюме в 2-4 коротких предложениях, без пояснений и заголовков.\n\n"
            f"Оригинал:\n{en_description}"
        )
        ru_description = self._generate_text_with_fallback_sync(
            translate_prompt,
            options={"temperature": 0.35, "num_predict": 180},
            timeout_seconds=max(self.timeout_seconds, 20.0),
            purpose="Vision translation",
        )
        _log.info("Vision RU translation (%d chars): %.200s", len(ru_description), ru_description)
        if len(ru_description) < 15:
            _log.warning("Translation too short (%d chars), discarding", len(ru_description))
            return ""
        if not self._is_mostly_cyrillic(ru_description):
            _log.warning("Translated response still not Cyrillic: %.120s...", ru_description)
            return ""
        cleaned = self._normalize_generated_description(ru_description)
        if len(cleaned) < 20:
            return ""
        return cleaned

    def _describe_appearance_direct_russian_sync(
        self, frame_base64: str, analysis: dict[str, Any]
    ) -> str:
        vision_model = self._resolve_vision_model_sync()
        emotion = str(analysis.get("emotion") or "").strip()
        emotion_hint = f"\nМодель эмоций определила настроение как: {emotion}." if emotion else ""
        prompt = (
            "Опиши только то, в чём ты на 100% уверен на изображении.\n"
            "Упомяни только если явно видно: волосы (цвет, длина), основной цвет одежды (только один — если не уверен, пропусти одежду вообще), "
            "аксессуары (только если однозначно видны), выражение лица (одно слово).\n"
            "Строгие правила:\n"
            "- Если цвет одежды неочевиден — НЕ упоминай одежду совсем.\n"
            "- НЕ называй тип одежды (куртка, рубашка, худи и т.д.).\n"
            "- НЕ описывай текстуру, узор, контраст одежды.\n"
            "- НЕ описывай позу, жесты или действия.\n"
            "- НЕ делай выводов о настроении или характере.\n"
            "- НЕ выдумывай — неуверен значит пропусти.\n"
            "Ответь 2-3 короткими фактическими предложениями на русском."
            f"{emotion_hint}"
        )
        payload = {
            "model": vision_model,
            "prompt": prompt,
            "images": [frame_base64],
            "stream": False,
            "options": {"temperature": 0.35, "num_predict": 160},
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.ollama_base_url.rstrip('/')}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with exclusive_gpu_task_sync("ollama"):
                with request.urlopen(req, timeout=max(self.timeout_seconds, 20.0)) as resp:
                    raw_body = resp.read().decode("utf-8")
        except (error.URLError, error.HTTPError) as exc:
            _log.warning("Direct RU Vision describe failed: %s", exc)
            return ""

        parsed = json.loads(raw_body)
        if parsed.get("error"):
            _log.warning("Direct RU vision model %r returned Ollama error: %s", vision_model, parsed["error"])
            return ""
        response_text = str(parsed.get("response") or "").strip()
        _log.info("Direct RU Vision description (%d chars): %.200s", len(response_text), response_text)
        cleaned = self._normalize_generated_description(response_text)
        if len(cleaned) >= 20:
            return cleaned

        translated = self._translate_description_to_russian_sync(response_text)
        cleaned_translated = self._normalize_generated_description(translated)
        if len(cleaned_translated) < 20:
            return ""
        return cleaned_translated

    def _translate_description_to_russian_sync(self, description: str) -> str:
        description = str(description or "").strip()
        if not description:
            return ""
        prompt = self._rules_block() + (
            "Переведи описание кадра на русский язык. "
            "Сохрани все видимые детали: человека, лицо, волосы, одежду, аксессуары, предметы, фон и освещение. "
            "Ответь только коротким переводом-резюме в 2-4 предложениях, без пояснений.\n\n"
            f"Описание:\n{description}"
        )
        return self._generate_text_with_fallback_sync(
            prompt,
            options={"temperature": 0.25, "num_predict": 180},
            timeout_seconds=max(self.timeout_seconds, 20.0),
            purpose="Description translation",
        )

    def _rewrite_with_ollama_sync(self, template: str, analysis: dict[str, Any]) -> str:
        # Filter out heavy fields (frame_base64) from analysis context
        safe_analysis = {
            k: v for k, v in analysis.items()
            if k != "frame_base64" and v
        }
        prompt = self._rules_block() + (
            "Пользователь попросил посмотреть, как он выглядит. Перепиши черновик в цельное описание всего кадра.\n\n"
            "Структура ответа: общее впечатление → лицо и взгляд → волосы → цвета одежды → аксессуары → фон.\n\n"
            "Правила:\n"
            "- Обращайся на «ты».\n"
            "- Тон: тёплый, доброжелательный, конкретный.\n"
            "- Если детали НЕТ в черновике — НЕ выдумывай, просто пропусти этот пункт.\n"
            "- НЕ называй тип одежды (куртка, рубашка, худи и т.д.) — говори только о цветах и общем впечатлении.\n"
            "- Не делай выводов о возрасте, этничности, здоровье, профессии или других чувствительных признаках.\n"
            "- Ответ: 2-4 коротких предложения на русском.\n"
            "- Выбери главное: лицо/взгляд, цвета в образе, фон. Не перечисляй всё подряд.\n\n"
            f"Черновик:\n{template}\n\n"
            f"Контекст анализа: {json.dumps(safe_analysis, ensure_ascii=False)}"
        )
        return self._generate_text_with_fallback_sync(
            prompt,
            options={"temperature": 0.5, "num_predict": 180},
            timeout_seconds=max(self.timeout_seconds, 20.0),
            purpose="Appearance rewrite",
        )

    @staticmethod
    def _normalize_observed_text(observed: str, emotion: str) -> str:
        cleaned = " ".join(observed.split()).strip()
        if not cleaned:
            return "Лицо хорошо видно, а кадр получился достаточно чётким для общей оценки."

        replacements = {
            "Лицо в кадре найдено.": "Лицо хорошо видно в кадре.",
            "Лицо не удалось уверенно выделить.": "Черты лица видны неидеально, но общий кадр всё же читается.",
        }
        for source, target in replacements.items():
            cleaned = cleaned.replace(source, target)

        if emotion:
            cleaned = cleaned.replace(f"Эмоция по модели: {emotion}.", "")
            cleaned = cleaned.replace(f"Эмоция по модели: {emotion}", "")

        cleaned = " ".join(cleaned.split()).strip()
        if not cleaned:
            return "Лицо хорошо видно, а кадр получился достаточно чётким для общей оценки."
        return cleaned

    @staticmethod
    def _normalize_generated_description(text: str) -> str:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return ""
        # Use relaxed thresholds — vision descriptions may contain English brand
        # names, style terms, etc.
        if not AppearanceResponseComposer._is_safe_russian_output(
            cleaned, min_cyrillic_ratio=0.55, max_foreign_tokens=6
        ):
            _log.warning(
                "normalize_generated_description: rejected as not safe Russian (len=%d): %.100s...",
                len(cleaned), cleaned,
            )
            return ""
        return cleaned

    @staticmethod
    def _sanitize_polished_response(polished: str, template: str) -> str:
        cleaned = " ".join(str(polished or "").split()).strip()
        if not cleaned:
            return template

        lowered = cleaned.lower()
        blocked_markers = (
            "i am a large language model",
            "disclaimer:",
            "emotion:",
            "эмоция:",
            "face_detected",
            "confidence",
            "observed:",
        )
        if any(marker in lowered for marker in blocked_markers):
            return template

        sentence_count = sum(cleaned.count(mark) for mark in ".!?")
        if len(cleaned) < 80 or sentence_count < 3:
            _log.warning(
                "sanitize_polished: rejected (len=%d, sentences=%d): %.100s...",
                len(cleaned), sentence_count, cleaned,
            )
            return template
        if not AppearanceResponseComposer._is_safe_russian_output(
            cleaned, min_cyrillic_ratio=0.55, max_foreign_tokens=6
        ):
            _log.warning(
                "sanitize_polished: rejected as not safe Russian: %.100s...", cleaned,
            )
            return template
        return cleaned

    @staticmethod
    def _shorten_voice_reply(text: str, *, max_sentences: int = 4, max_chars: int = 520) -> str:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return ""

        sentences = re.findall(r"[^.!?]+[.!?]?", cleaned, flags=re.UNICODE)
        selected: list[str] = []
        current_len = 0
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if sentence[-1] not in ".!?":
                sentence = f"{sentence}."
            projected_len = current_len + len(sentence) + (1 if selected else 0)
            if selected and (len(selected) >= max_sentences or projected_len > max_chars):
                break
            selected.append(sentence)
            current_len = projected_len

        if selected:
            return " ".join(selected)

        if len(cleaned) <= max_chars:
            return cleaned
        shortened = cleaned[:max_chars].rsplit(" ", 1)[0].strip()
        return f"{shortened}."

    @staticmethod
    def _is_mostly_cyrillic(text: str) -> bool:
        """Return True if at least 60% of letter characters in text are Cyrillic."""
        letters = [ch for ch in text if ch.isalpha()]
        if not letters:
            return False
        cyrillic = sum(1 for ch in letters if "\u0400" <= ch <= "\u04ff")
        return cyrillic / len(letters) >= 0.6

    @staticmethod
    def _is_safe_russian_output(
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
