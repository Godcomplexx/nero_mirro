from __future__ import annotations

import asyncio
import logging
import tempfile
import time
import unittest
from pathlib import Path

from neuro_mirror.core.settings import Settings
from neuro_mirror.plugins.ai_assistant.appearance_response import AppearanceResponseComposer
from neuro_mirror.plugins.ai_assistant.backends import (
    OllamaAssistantBackend,
    build_assistant_backend,
    detect_appearance_request,
    detect_camera_vision_request,
    detect_start_screening_command,
    normalize_user_utterance,
    should_prefer_internet_answer,
    should_use_internet_fallback,
    _is_unsuccessful_assistant_reply,
    _sanitize_assistant_reply,
)
from neuro_mirror.plugins.ai_assistant.rules import (
    invalidate_rules_cache,
    load_assistant_rules,
    validate_assistant_rules,
)


class AssistantRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        invalidate_rules_cache()

    def test_stt_president_variants_normalize_to_current_us_president_query(self) -> None:
        samples = (
            "Президент… юрсци.",
            "кто президент USA",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                normalized = normalize_user_utterance(sample)
                self.assertEqual(normalized.rstrip("."), "Кто сейчас президент сша")
                self.assertTrue(should_prefer_internet_answer(normalized))

        normalized = normalize_user_utterance("кто последний президент юсей")
        self.assertEqual(normalized, "Кто последний президент сша")
        self.assertTrue(should_prefer_internet_answer(normalized))

    def test_application_commands_still_route_before_general_chat(self) -> None:
        self.assertEqual(
            detect_start_screening_command(normalize_user_utterance("начать скрининг")),
            "start_screening",
        )
        self.assertEqual(
            detect_appearance_request(normalize_user_utterance("как я выгляжу")),
            "analyze_appearance",
        )
        self.assertTrue(
            detect_camera_vision_request(normalize_user_utterance("что ты видишь на камере"))
        )

    def test_command_only_fallback_is_treated_as_bad_answer(self) -> None:
        bad_reply = (
            "Я не понимаю ваш запрос. Пожалуйста, используйте команды приложения "
            "Нейро-зеркало: start_screening, analyze_appearance или camera_vision_query."
        )
        self.assertTrue(should_use_internet_fallback("кто сейчас президент сша", bad_reply))
        self.assertTrue(_is_unsuccessful_assistant_reply(bad_reply))
        self.assertNotIn("используйте команды", _sanitize_assistant_reply(bad_reply).lower())

    def test_custom_rules_file_is_loaded_into_backend_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rules_path = Path(temp_dir) / "rules.md"
            rules_path.write_text("CUSTOM RULE: answer briefly.", encoding="utf-8")

            backend = build_assistant_backend(
                Settings(assistant_rules_path=str(rules_path)),
            )

            self.assertIsInstance(backend, OllamaAssistantBackend)
            prompt = backend._build_combined_prompt("кто такой Ньютон")
            self.assertIn("CUSTOM RULE: answer briefly.", prompt)
            self.assertIn('{"command":"none","reply":"<твой ответ>"}', prompt)

    # --- Hot-reload tests ---

    def test_rules_hot_reload_detects_file_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rules_path = Path(temp_dir) / "rules.md"
            rules_path.write_text("VERSION 1: original rules.", encoding="utf-8")

            result1 = load_assistant_rules(str(rules_path))
            self.assertIn("VERSION 1", result1)

            # Ensure mtime actually changes (some filesystems have 1s resolution)
            time.sleep(0.05)
            rules_path.write_text("VERSION 2: updated rules.", encoding="utf-8")

            result2 = load_assistant_rules(str(rules_path))
            self.assertIn("VERSION 2", result2)
            self.assertNotIn("VERSION 1", result2)

    def test_rules_cache_returns_same_content_without_reread(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rules_path = Path(temp_dir) / "rules.md"
            rules_path.write_text("CACHED CONTENT.", encoding="utf-8")

            result1 = load_assistant_rules(str(rules_path))
            result2 = load_assistant_rules(str(rules_path))
            self.assertEqual(result1, result2)
            self.assertIn("CACHED CONTENT", result1)

    def test_rules_fallback_when_file_missing(self) -> None:
        result = load_assistant_rules("/nonexistent/path/rules.md")
        self.assertIn("Нейро-зеркало", result)
        self.assertIn("помощник", result)

    # --- Validation tests ---

    def test_rules_validation_warns_on_missing_sections(self) -> None:
        incomplete_rules = (
            "# Правила\n\n"
            "## Роль\n- Я помощник.\n\n"
            "## Тон и формат\n- Кратко.\n"
        )
        warnings = validate_assistant_rules(incomplete_rules)
        self.assertTrue(len(warnings) > 0)
        missing_names = " ".join(warnings)
        self.assertIn("Команды приложения", missing_names)
        self.assertIn("Медицина и психология", missing_names)
        self.assertIn("Vision и внешность", missing_names)

    def test_rules_validation_passes_for_complete_file(self) -> None:
        complete_rules = load_assistant_rules()
        warnings = validate_assistant_rules(complete_rules)
        self.assertEqual(warnings, [])

    def test_rules_validation_is_case_insensitive(self) -> None:
        rules = (
            "## роль\n- ok\n"
            "## тон и формат\n- ok\n"
            "## команды приложения\n- ok\n"
            "## медицина и психология\n- ok\n"
            "## vision и внешность\n- ok\n"
        )
        warnings = validate_assistant_rules(rules)
        self.assertEqual(warnings, [])

    def test_rules_validation_logs_warnings_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rules_path = Path(temp_dir) / "rules.md"
            rules_path.write_text("# Minimal rules\n- just a line", encoding="utf-8")

            with self.assertLogs("neuro_mirror.assistant_rules", level=logging.WARNING) as cm:
                load_assistant_rules(str(rules_path))

            log_text = " ".join(cm.output)
            self.assertIn("Роль", log_text)

    # --- rules_path propagation tests ---

    def test_rules_path_propagates_to_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rules_path = Path(temp_dir) / "rules.md"
            rules_path.write_text("BACKEND RULE: be concise.", encoding="utf-8")

            backend = build_assistant_backend(
                Settings(assistant_rules_path=str(rules_path)),
            )
            self.assertIsInstance(backend, OllamaAssistantBackend)

            rules_block = backend._rules_block()
            self.assertIn("BACKEND RULE: be concise.", rules_block)

    def test_rules_path_propagates_to_appearance_composer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rules_path = Path(temp_dir) / "rules.md"
            rules_path.write_text("APPEARANCE RULE: mention hair.", encoding="utf-8")

            composer = AppearanceResponseComposer(
                enabled=True,
                ai_backend="ollama",
                ollama_base_url="http://localhost:11434",
                ollama_model="test",
                ollama_vision_model="test",
                timeout_seconds=10.0,
                rules_path=str(rules_path),
            )

            rules_block = composer._rules_block()
            self.assertIn("APPEARANCE RULE: mention hair.", rules_block)

    def test_appearance_composer_persists_vision_description_in_analysis(self) -> None:
        class Composer(AppearanceResponseComposer):
            def _describe_appearance_with_vision_sync(self, frame_base64, analysis):  # type: ignore[no-untyped-def]
                return (
                    "В кадре виден человек в наушниках, тёмной толстовке и с волосами средней длины. "
                    "На фоне заметна светлая стена, а человек расположен близко к центру кадра. "
                    "Описание опирается на видимые детали кадра."
                )

            def _rewrite_with_ollama_sync(self, template, analysis):  # type: ignore[no-untyped-def]
                return template

        composer = Composer(
            enabled=True,
            ai_backend="ollama",
            ollama_base_url="http://localhost:11434",
            ollama_model="test",
            ollama_vision_model="test",
            timeout_seconds=10.0,
        )
        analysis = {
            "frame_base64": "abc",
            "face_detected": True,
            "observed": "Лицо в кадре найдено.",
        }

        reply = asyncio.run(composer.compose(analysis))

        self.assertIn("толстов", reply)
        self.assertIn("наушниках", analysis["appearance_description"])
        self.assertIn("accessories", analysis["appearance_checklist"])
        self.assertEqual(analysis["vision_status"], "ok:en_to_ru")


if __name__ == "__main__":
    unittest.main()
