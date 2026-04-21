from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from neuro_mirror.core.gpu_scheduler import exclusive_gpu_task_sync

_log = logging.getLogger("neuro_mirror.appearance_response")


@dataclass(slots=True)
class AppearanceResponseComposer:
    enabled: bool
    ai_backend: str
    ollama_base_url: str
    ollama_model: str
    ollama_vision_model: str
    timeout_seconds: float

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
                "Попробуйте сесть чуть ближе к камере или добавить света, и я дам более точное описание. "
                "Это не медицинская оценка."
            )

        emotion = str(analysis.get("emotion") or "").strip().lower()
        observed = str(analysis.get("observed") or "").strip()
        appearance_desc = self._normalize_generated_description(
            str(analysis.get("appearance_description") or "").strip()
        )

        compliment_map = {
            "радость": "Сегодня вы выглядите дружелюбно и очень живо.",
            "спокойствие": "Сегодня вы выглядите спокойно и собранно.",
            "удивление": "Сегодня у вас очень живое и выразительное лицо.",
            "грусть": "Сегодня вы выглядите немного уставшей, но аккуратной и собранной.",
            "злость": "Сегодня вы выглядите сосредоточенно и напряжённо.",
            "страх": "Сегодня вы выглядите внимательной и немного напряжённой.",
            "отвращение": "Сегодня вы выглядите серьёзно и сдержанно.",
            "презрение": "Сегодня вы выглядите уверенно и немного строже обычного.",
        }
        compliment = compliment_map.get(emotion, "Сегодня вы выглядите аккуратно и уверенно.")

        if appearance_desc:
            observation = appearance_desc
        elif observed:
            observation = self._normalize_observed_text(observed, emotion)
            if not self._is_safe_russian_output(
                observation,
                min_cyrillic_ratio=0.78,
                max_foreign_tokens=1,
            ):
                observation = "Лицо хорошо видно, а кадр получился достаточно чётким для общей оценки."
        else:
            observation = "Лицо хорошо видно, а кадр получился достаточно чётким для общей оценки."

        return f"{compliment} {observation} Это не медицинская оценка."

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
            "You are a friendly personal stylist assistant. "
            "Describe the person's appearance in detail from the camera frame.\n"
            "Cover these aspects in order (skip any that are not visible):\n"
            "1. Overall impression and vibe (confident, calm, energetic, elegant, etc.)\n"
            "2. Face and gaze — expression, eyes, skin tone\n"
            "3. Hair — style, length, color, how it frames the face\n"
            "4. Clothing — style, colors, how it fits\n"
            "5. Accessories — glasses, jewelry, headphones, etc.\n"
            "6. One-sentence summary of the overall look\n\n"
            "Be warm, genuine and complimentary. Do not diagnose health conditions.\n"
            "Answer in 4-6 short sentences in English.\n"
            f"{emotion_hint}"
        )
        prompt_en += (
            "\nFocus especially on the details people consciously work on: hair, styling, clothing, "
            "accessories and overall polish. If any of those are visible, mention them explicitly."
        )
        payload = {
            "model": vision_model,
            "prompt": prompt_en,
            "images": [frame_base64],
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 250},
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
        translate_prompt = (
            "Ты ассистент приложения Нейро-зеркало.\n"
            "Переведи описание внешности ниже на русский язык.\n"
            "Сделай текст тёплым, доброжелательным и естественным.\n"
            "Сохрани все детали: лицо, волосы, одежду, аксессуары.\n"
            "Ответь только переводом в 4-6 предложениях, без пояснений.\n\n"
            f"{en_description}"
        )
        translate_payload = {
            "model": translate_model,
            "prompt": translate_prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 250},
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
        prompt = (
            "Ты помощник интерфейса Нейро-зеркало.\n"
            "Пользователь попросил оценить внешний вид — дай развёрнутую, тёплую оценку образа.\n\n"
            "Структура ответа (4-6 предложений):\n"
            "1. Общее впечатление и атмосфера образа (уверенность, спокойствие, лёгкость и т.д.)\n"
            "2. Лицо и взгляд — выражение, настроение\n"
            "3. Волосы — как уложены, как дополняют образ\n"
            "4. Одежда — стиль, как подчёркивает характер\n"
            "5. Аксессуары (если есть) — как дополняют\n"
            "6. Фраза «Это не медицинская оценка.»\n\n"
            "Если какой-то детали не видно в черновике — не выдумывай, просто пропусти.\n"
            "Тон: доброжелательный, как комплимент от подруги.\n\n"
            f"Черновик:\n{template}\n\n"
            f"Контекст анализа: {json.dumps(safe_analysis, ensure_ascii=False)}"
        )
        prompt += (
            "\n\nAdditional instruction: answer in Russian with a fuller, more personal appearance review. "
            "Do not stop at face and mood only. If visible, explicitly mention hair, clothing style, "
            "accessories and the overall image the person creates. End exactly with: Это не медицинская оценка."
        )
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.35, "num_predict": 320},
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
        if len(cleaned) < 55 or sentence_count < 2:
            return template
        if "это не медицинская оценка" not in lowered:
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
