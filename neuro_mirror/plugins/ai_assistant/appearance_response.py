from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from neuro_mirror.core.gpu_scheduler import exclusive_gpu_task_sync
from neuro_mirror.plugins.ai_assistant.rules import load_assistant_rules

_log = logging.getLogger("neuro_mirror.appearance_response")


@dataclass(slots=True)
class AppearanceResponseComposer:
    enabled: bool
    ai_backend: str
    ollama_base_url: str
    ollama_model: str
    ollama_vision_model: str
    timeout_seconds: float
    assistant_rules: str = ""

    def _rules_block(self) -> str:
        rules = self.assistant_rules.strip() or load_assistant_rules()
        return f"Общие правила поведения ассистента:\n{rules}\n\n"

    async def compose(self, analysis: dict[str, Any]) -> str:
        # --- Step 1: try to get a rich visual description via Ollama Vision ---
        if self.enabled and self.ai_backend == "ollama":
            frame_b64 = str(analysis.get("frame_base64") or "").strip()
            if frame_b64 and not analysis.get("appearance_description"):
                try:
                    vision_desc = await asyncio.to_thread(
                        self._describe_appearance_with_vision_sync, frame_b64, analysis
                    )
                    if vision_desc:
                        analysis = dict(analysis, appearance_description=vision_desc)
                except Exception as exc:
                    _log.warning("Vision appearance description failed: %s", exc)

        # --- Step 2: build template from analysis data ---
        template = self._build_template(analysis)
        if not self.enabled or self.ai_backend != "ollama":
            return template

        # --- Step 3: polish the template with LLM rewrite ---
        try:
            polished = await asyncio.to_thread(self._rewrite_with_ollama_sync, template, analysis)
        except Exception:
            return template

        return self._sanitize_polished_response(polished, template)

    def _build_template(self, analysis: dict[str, Any]) -> str:
        if not analysis.get("face_detected"):
            return (
                "Я не смог уверенно рассмотреть лицо на кадре. "
                "Попробуй сесть чуть ближе к камере или добавить света, и я дам более точное описание."
            )

        emotion = str(analysis.get("emotion") or "").strip().lower()
        observed = str(analysis.get("observed") or "").strip()
        appearance_desc = self._normalize_generated_description(
            str(analysis.get("appearance_description") or "").strip()
        )

        # --- Emotion → opening line with vibe + atmosphere ---
        compliment_map = {
            "радость": (
                "Ты выглядишь как человек с очень живой и открытой внешностью — "
                "в тебе сразу чувствуется лёгкость и дружелюбие."
            ),
            "спокойствие": (
                "Ты выглядишь как человек с уравновешенной, приятной внешностью — "
                "в тебе сразу чувствуется спокойствие и уверенность."
            ),
            "удивление": (
                "Ты выглядишь как человек с выразительной внешностью — "
                "в тебе сразу чувствуется живость и любопытство."
            ),
            "грусть": (
                "Ты выглядишь как человек с аккуратной, мягкой внешностью — "
                "в тебе чувствуется задумчивость и глубина."
            ),
            "злость": (
                "Ты выглядишь как человек с яркой, выразительной внешностью — "
                "в тебе чувствуется решительность и внутренняя сила."
            ),
            "страх": (
                "Ты выглядишь как человек с внимательной, чуткой внешностью — "
                "в тебе чувствуется сосредоточенность и настороженность."
            ),
            "отвращение": (
                "Ты выглядишь как человек с серьёзной, строгой внешностью — "
                "в тебе чувствуется характер и сдержанность."
            ),
            "презрение": (
                "Ты выглядишь как человек с уверенной, стильной внешностью — "
                "в тебе чувствуется самодостаточность и твёрдость."
            ),
        }
        opening = compliment_map.get(
            emotion,
            "Ты выглядишь как человек с приятной внешностью — "
            "в тебе сразу чувствуется уверенность и аккуратность.",
        )

        # --- Rich description or basic observation ---
        if appearance_desc:
            observation = appearance_desc
        elif observed:
            observation = self._normalize_observed_text(observed, emotion)
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
            "Лицо хорошо видно в кадре, но чтобы оценить волосы, стиль одежды и аксессуары, "
            "нужен более детальный кадр — попробуй отодвинуться чуть дальше от камеры."
        )

    def _describe_appearance_with_vision_sync(
        self, frame_base64: str, analysis: dict[str, Any]
    ) -> str:
        """Ask Ollama Vision model to describe the person's appearance from the camera frame.

        Uses English prompt for llava (better quality), then translates to Russian
        via the main text model.
        """
        vision_model = self.ollama_vision_model or self.ollama_model
        emotion = str(analysis.get("emotion") or "").strip()

        # --- Step A: get English description from vision model ---
        emotion_hint = f" The emotion model detected the mood as '{emotion}'." if emotion else ""
        prompt_en = (
            f"{self._rules_block()}"
            "You are a warm, observant personal stylist giving a friend a genuine appearance review.\n\n"
            "Describe the person from the camera frame. Follow this structure strictly — "
            "skip any section that is NOT visible, but cover every section you CAN see:\n\n"
            "1. OVERALL VIBE: What impression does this person make at first glance? "
            "(confident, calm, energetic, elegant, cozy, edgy, etc.) — one sentence.\n"
            "2. FACE & GAZE: Expression, eyes, how they look at the camera — one sentence.\n"
            "3. HAIR (important!): Style, length, color, texture, how it frames the face, "
            "whether it looks styled or natural. People invest effort into their hair — notice it.\n"
            "4. CLOTHING (important!): What are they wearing? Colors, style (casual, formal, "
            "streetwear, minimalist, etc.), how the outfit fits, what it says about their personality.\n"
            "5. ACCESSORIES: Glasses, jewelry, watch, headphones, piercings, hat — anything visible. "
            "Note how they complement the look.\n"
            "6. PERSONAL GUESS: One sentence guessing something about their personality or lifestyle "
            "based on the overall look (e.g., 'You look like someone who values comfort but "
            "never compromises on style').\n\n"
            "Rules:\n"
            "- Be warm, genuine and complimentary — like a supportive friend, not a judge.\n"
            "- Do NOT diagnose health conditions.\n"
            "- Do NOT mention image quality, camera angle, or technical aspects.\n"
            "- If hair, clothing or accessories are visible, you MUST mention them.\n"
            "- Answer in 5-8 sentences in English.\n"
            f"{emotion_hint}"
        )
        payload = {
            "model": vision_model,
            "prompt": prompt_en,
            "images": [frame_base64],
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 400},
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
            _log.warning("Vision describe failed: %s", exc)
            return ""

        parsed = json.loads(raw_body)
        en_description = str(parsed.get("response") or "").strip()
        if len(en_description) < 15:
            _log.warning("Vision returned too short response: %r", en_description)
            return ""

        # --- Step B: translate English description to Russian via text model ---
        translate_model = self.ollama_model
        translate_prompt = self._rules_block() + (
            "Переведи описание внешности ниже на русский язык.\n\n"
            "Правила перевода:\n"
            "- Сделай текст тёплым, доброжелательным и естественным — как комплимент от подруги.\n"
            "- Обращайся на «ты».\n"
            "- ОБЯЗАТЕЛЬНО сохрани ВСЕ упомянутые детали: волосы, одежда, аксессуары, "
            "общее впечатление, предположение о характере.\n"
            "- Если в оригинале упомянуты конкретные вещи (цвет одежды, тип причёски, "
            "украшения) — они ДОЛЖНЫ быть в переводе.\n"
            "- Ответь только переводом в 5-8 предложениях, без пояснений и заголовков.\n\n"
            f"Оригинал:\n{en_description}"
        )
        translate_payload = {
            "model": translate_model,
            "prompt": translate_prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 350},
        }
        translate_body = json.dumps(translate_payload).encode("utf-8")
        translate_req = request.Request(
            f"{self.ollama_base_url.rstrip('/')}/api/generate",
            data=translate_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with exclusive_gpu_task_sync("ollama"):
                with request.urlopen(translate_req, timeout=max(self.timeout_seconds, 12.0)) as resp:
                    translate_raw = resp.read().decode("utf-8")
        except (error.URLError, error.HTTPError) as exc:
            _log.warning("Vision translate failed, using English: %s", exc)
            return ""

        translate_parsed = json.loads(translate_raw)
        ru_description = str(translate_parsed.get("response") or "").strip()

        if len(ru_description) < 15:
            return ""
        if not self._is_mostly_cyrillic(ru_description):
            _log.warning("Translated response still not Cyrillic: %.80s...", ru_description)
            return ""
        return ru_description

    def _rewrite_with_ollama_sync(self, template: str, analysis: dict[str, Any]) -> str:
        # Filter out heavy fields (frame_base64) from analysis context
        safe_analysis = {
            k: v for k, v in analysis.items()
            if k != "frame_base64" and v
        }
        prompt = self._rules_block() + (
            "Пользователь попросил оценить внешний вид — перепиши черновик в развёрнутую, "
            "тёплую и персональную оценку образа.\n\n"
            "Структура ответа (обязательно соблюдай порядок, пропускай только то, чего НЕТ в черновике):\n\n"
            "1. ОБЩЕЕ ВПЕЧАТЛЕНИЕ: Какую атмосферу создаёт человек — уверенность, спокойствие, "
            "лёгкость, загадочность? Одно предложение.\n"
            "2. ЛИЦО И ВЗГЛЯД: Выражение, глаза, какое ощущение создаёт взгляд. Одно предложение.\n"
            "3. ВОЛОСЫ (важно!): Как уложены, какой эффект создают — собранность, естественность, "
            "динамику. Люди вкладываются в волосы — обязательно отметь. Одно-два предложения.\n"
            "4. ОДЕЖДА (важно!): Стиль, как подчёркивает характер или индивидуальность. "
            "Не надо выдумывать цвета или бренды, если их нет в черновике. Одно-два предложения.\n"
            "5. АКСЕССУАРЫ: Если упомянуты в черновике — как дополняют образ, что добавляют "
            "(изюминку, завершённость, характер). Одно предложение.\n"
            "6. ПЕРСОНАЛЬНОЕ ПРЕДПОЛОЖЕНИЕ: Одно предложение-догадка о характере или стиле жизни "
            "человека на основе образа. Например: «Мне кажется, ты из тех людей, кто ценит "
            "комфорт, но не готов жертвовать стилем».\n\n"
            "Правила:\n"
            "- Обращайся на «ты».\n"
            "- Тон: тёплый, доброжелательный, как искренний комплимент от подруги.\n"
            "- Если детали НЕТ в черновике — НЕ выдумывай, просто пропусти этот пункт.\n"
            "- Если деталь ЕСТЬ — обязательно упомяни, не сокращай.\n"
            "- Ответ: 5-9 предложений на русском.\n\n"
            f"Черновик:\n{template}\n\n"
            f"Контекст анализа: {json.dumps(safe_analysis, ensure_ascii=False)}"
        )
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.35, "num_predict": 450},
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
                with request.urlopen(req, timeout=max(self.timeout_seconds, 12.0)) as response:
                    raw_body = response.read().decode("utf-8")
        except error.URLError:
            return template

        parsed = json.loads(raw_body)
        return str(parsed.get("response") or "").strip()

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
        if not AppearanceResponseComposer._is_safe_russian_output(cleaned):
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
            return template
        if not AppearanceResponseComposer._is_safe_russian_output(cleaned):
            return template
        return cleaned

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
