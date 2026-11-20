"""
Тесты вычисления путей, в том числе каталога кэша браузеров Playwright.

Логика должна совпадать с реализацией Playwright
(computeDefaultCacheDirectory в coreBundle.js), иначе приложение будет
искать браузер не там, где он установлен.
"""

import sys

import pytest

from src.core import paths


class TestPlatformDefaultBrowsersDir:
    """Проверка штатного каталога кэша браузеров для каждой ОС."""

    def test_linux_uses_home_cache(self, monkeypatch):
        """Linux без XDG_CACHE_HOME -> ~/.cache/ms-playwright."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

        assert paths._platform_default_browsers_dir() == paths.Path.home() / ".cache" / "ms-playwright"

    def test_linux_respects_xdg_cache_home(self, monkeypatch, tmp_path):
        """
        Linux с XDG_CACHE_HOME -> $XDG_CACHE_HOME/ms-playwright.

        Это реальный сценарий в контейнерах и на серверах: без учёта этой
        переменной приложение искало бы браузер в ~/.cache, хотя Playwright
        установил его в другое место.
        """
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

        assert paths._platform_default_browsers_dir() == tmp_path / "ms-playwright"

    def test_linux_ignores_empty_xdg_cache_home(self, monkeypatch):
        """Пустая XDG_CACHE_HOME считается незаданной, как и в Playwright."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CACHE_HOME", "")

        assert paths._platform_default_browsers_dir() == paths.Path.home() / ".cache" / "ms-playwright"

    def test_macos_uses_library_caches(self, monkeypatch):
        """macOS -> ~/Library/Caches/ms-playwright."""
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

        expected = paths.Path.home() / "Library" / "Caches" / "ms-playwright"
        assert paths._platform_default_browsers_dir() == expected

    def test_windows_uses_local_appdata(self, monkeypatch, tmp_path):
        """Windows -> %LOCALAPPDATA%/ms-playwright."""
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

        assert paths._platform_default_browsers_dir() == tmp_path / "ms-playwright"

    def test_windows_falls_back_when_no_localappdata(self, monkeypatch):
        """Без %LOCALAPPDATA% -> ~/AppData/Local/ms-playwright."""
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.delenv("LOCALAPPDATA", raising=False)

        expected = paths.Path.home() / "AppData" / "Local" / "ms-playwright"
        assert paths._platform_default_browsers_dir() == expected

    def test_unknown_platform_falls_back_to_unix_cache(self, monkeypatch):
        """
        Неподдерживаемая платформа не должна ронять запуск.

        Playwright в этом случае бросает исключение, но для приложения это
        избыточно жёстко: лучше вернуть разумное значение по умолчанию.
        """
        monkeypatch.setattr(sys, "platform", "freebsd13")
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

        assert paths._platform_default_browsers_dir() == paths.Path.home() / ".cache" / "ms-playwright"

    @pytest.mark.parametrize(
        ("platform", "expected_tail"),
        [
            ("linux", ("Library",)),
            ("darwin", ("Library", "Caches")),
        ],
    )
    def test_path_always_ends_with_ms_playwright(self, monkeypatch, platform, expected_tail):
        """Во всех случаях путь заканчивается каталогом ms-playwright."""
        monkeypatch.setattr(sys, "platform", platform)
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)

        assert paths._platform_default_browsers_dir().name == "ms-playwright"


class TestUsableBrowsersDir:
    """Проверка отбраковки непригодных каталогов."""

    def test_existing_non_empty_dir_is_usable(self, tmp_path):
        (tmp_path / "chromium-1243").mkdir()
        assert paths._is_usable_browsers_dir(tmp_path) is True

    def test_empty_dir_is_not_usable(self, tmp_path):
        """
        Пустая папка хуже отсутствия: Playwright получил бы валидный на вид
        путь, не нашёл бы браузер и упал бы с невнятной ошибкой.
        """
        tmp_path.mkdir(exist_ok=True)
        assert paths._is_usable_browsers_dir(tmp_path) is False

    def test_missing_dir_is_not_usable(self, tmp_path):
        assert paths._is_usable_browsers_dir(tmp_path / "нет-такой") is False
