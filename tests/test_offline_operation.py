"""Работа без сети: страж от появления новых внешних зависимостей.

Программа должна проводить скрининг, тренировки и диалог с ассистентом на
устройстве. Тесты ниже не заменяют прогон с отключённым адаптером, но ловят
самое частое, как это ломается: кто-то добавил обращение к стороннему сервису
или вернул загрузку файла с чужого сайта.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from neuro_mirror.core.settings import Settings

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "neuro_mirror"
URL_RE = re.compile(r"https?://[a-zA-Z0-9._-]+")

# Локальные адреса и пространства имён XML внешними обращениями не являются.
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
IGNORED_SUBSTRINGS = ("w3.org", "schemas.openxmlformats.org", "schemas.microsoft.com")

# Внешних адресов в коде не должно остаться ни одного: справочные сервисы
# ассистента удалены вместе с настройками, а не просто выключены.
ALLOWED_OPTIONAL_HOSTS: set[str] = set()


def _external_hosts() -> dict[str, set[str]]:
    """Внешние хосты в нашем коде.

    Каталог сторонних библиотек не сканируется: адреса в нём — заголовки
    лицензий и ссылки на документацию внутри минифицированных файлов, а не
    обращения во время работы. Эти файлы проверяются лицензией, а не поиском.
    """
    found: dict[str, set[str]] = {}
    patterns = ("*.py", "*.js", "*.html", "*.css")
    for pattern in patterns:
        for path in SOURCE_ROOT.rglob(pattern):
            if "__pycache__" in path.parts or "vendor" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for url in URL_RE.findall(text):
                host = url.split("//", 1)[-1]
                if host in LOCAL_HOSTS or any(s in host for s in IGNORED_SUBSTRINGS):
                    continue
                found.setdefault(host, set()).add(
                    str(path.relative_to(SOURCE_ROOT.parent))
                )
    return found


def test_no_unexpected_external_hosts():
    """Новый сторонний адрес в коде — повод осознанно решить, нужен ли он."""
    unexpected = {
        host: sorted(files)
        for host, files in _external_hosts().items()
        if host not in ALLOWED_OPTIONAL_HOSTS
    }
    assert not unexpected, f"появились внешние обращения: {unexpected}"


@pytest.mark.parametrize(
    "name", ["weather_enabled", "currency_enabled", "internet_fallback_enabled",
             "weather_base_url", "currency_base_url", "internet_fallback_base_url"]
)
def test_reference_service_settings_are_gone(name):
    """Настройки удалены вместе с кодом: включить сервисы обратно нечем."""
    assert not hasattr(Settings(), name)


@pytest.mark.parametrize(
    "name", ["detect_weather_request", "detect_currency_request",
             "should_use_internet_fallback", "should_prefer_internet_answer"]
)
def test_reference_service_code_is_removed(name):
    """Отключённый, но живой код рано или поздно включают обратно."""
    from neuro_mirror.plugins.ai_assistant import backends

    assert not hasattr(backends, name)


def test_speech_synthesis_is_local():
    """Озвучка инструкций не должна зависеть от внешнего сервиса."""
    from neuro_mirror.core import speech_synthesis

    assert not URL_RE.findall(Path(speech_synthesis.__file__).read_text(encoding="utf-8"))


def test_interface_loads_fonts_and_scripts_from_the_project():
    static = SOURCE_ROOT / "web" / "static"
    markup = (static / "index.html").read_text(encoding="utf-8")
    script = (static / "app.js").read_text(encoding="utf-8")

    assert "fonts.googleapis.com" not in markup
    assert "fonts.gstatic.com" not in markup
    assert "/static/fonts/fonts.css" in markup
    assert "cdn.jsdelivr.net" not in script
    assert "/static/vendor/" in script


def test_bundled_assets_exist():
    static = SOURCE_ROOT / "web" / "static"
    assert (static / "fonts" / "fonts.css").is_file()
    assert list((static / "fonts").glob("*.woff2")), "нет файлов шрифтов"
    for name in ("pixi.min.js", "cubism4.min.js", "live2dcubismcore.min.js"):
        assert (static / "vendor" / name).is_file(), f"нет {name}"


def test_vision_translation_does_not_use_public_services():
    """Описание пользователя с камеры не должно уходить во внешний переводчик."""
    backends = (SOURCE_ROOT / "plugins" / "ai_assistant" / "backends.py").read_text(
        encoding="utf-8"
    )
    assert "translate.googleapis.com" not in backends
    assert "mymemory" not in backends.lower()


def test_runtime_actually_starts(tmp_path, monkeypatch):
    """Сборка runtime с настройками по умолчанию.

    Удаление настройки может оставить висячую ссылку в сборке приложения:
    все модульные тесты при этом проходят, а программа не запускается.

    Каталог подменяется: хранилища пишут файлы относительно текущего, и без
    подмены тест затирал бы рабочие данные и мешал соседним тестам.
    """
    import asyncio

    from neuro_mirror.app.runtime import create_runtime

    monkeypatch.chdir(tmp_path)
    handle = create_runtime(
        Settings.from_env(), stop_event=asyncio.Event(), include_ai_plugin=False
    )
    assert handle.session_store is not None
    assert handle.dataset_store is not None
