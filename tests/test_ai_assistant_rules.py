from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from neuro_mirror.core.settings import Settings
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
from neuro_mirror.plugins.ai_assistant.rules import load_assistant_rules


class AssistantRulesTest(unittest.TestCase):
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
            rules = load_assistant_rules(str(rules_path))

            backend = build_assistant_backend(
                Settings(assistant_rules_path=str(rules_path)),
                assistant_rules=rules,
            )

        self.assertIsInstance(backend, OllamaAssistantBackend)
        prompt = backend._build_combined_prompt("кто такой Ньютон")
        self.assertIn("CUSTOM RULE: answer briefly.", prompt)
        self.assertIn('{"command":"none","reply":"<твой ответ>"}', prompt)


if __name__ == "__main__":
    unittest.main()
