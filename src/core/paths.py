"""
Единый источник правды для вычисления путей приложения.

Раньше логика «где мы находимся» дублировалась в четырёх местах
(`src/__init__.py`, `src/core/resources.py`, `src/database/db_config.py`,
`src/parsers/golden_apple_parser.py`) и в собранном приложении ломалась:
на Linux путь к браузерам Playwright был захардкожен под `/root/.cache`.

Здесь собрано одно место, которое корректно работает и при запуске из
исходников, и в скомпилированном бинарнике (PyInstaller `onedir`/`onefile`).
"""

import os
import sys
import tempfile

from pathlib import Path
from typing import Optional

#: Имя папки с браузерами Playwright, если они упакованы в сборку.
#: Должно совпадать с BROWSERS_DEST в viewhub.spec.
BROWSERS_DIR_NAME = "pw-browsers"


def is_frozen() -> bool:
    """True, если код запущен из скомпилированного бинарника."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """
    Корень, где лежат РЕСУРСЫ (только чтение).

    В скомпилированном приложении:
      * `onedir`  -> `dist/viewhub/_internal`
      * `onefile` -> временная папка распаковки в /tmp

    При разработке возвращается корень проекта (текущий рабочий каталог).
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path.cwd()


def app_root() -> Path:
    """
    Корень, рядом с которым приложение может СИСТЕМНО ПИСАТЬ данные:
    база данных, профиль Chromium, логи.

    В скомпилированном приложении это папка рядом с исполняемым файлом
    (НЕ `_internal`, которая может оказаться только на чтение).
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def ensure_writable(path: Path) -> Path:
    """
    Создаёт каталог и проверяет, что в него реально можно записать.

    Если запись невозможна (например, бинарник запущен из read-only каталога
    или от пользователя без прав), возвращает безопасный каталог в %TEMP%.
    Иначе приложение падало бы с PermissionError прямо во время парсинга.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".viewhub_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return path
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "viewhub"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _platform_default_browsers_dir() -> Path:
    """
    Штатный каталог кэша браузеров Playwright для текущей ОС.

    ВАЖНО: используется Path.home(), а не жёстко зашитый '/root/.cache'.
    Прежняя константа ломала запуск от любого пользователя, кроме root.
    """
    if sys.platform.startswith("win"):
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def _is_usable_browsers_dir(path: Path) -> bool:
    """
    Каталог считается пригодным, только если он существует И не пуст.

    Пустая папка (например, остаток от неудачной сборки) хуже, чем её
    отсутствие: Playwright получит валидный на вид путь, не найдёт в нём
    браузер и упадёт с невнятной ошибкой, хотя рабочий кэш рядом есть.
    """
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return False


def resolve_playwright_browsers_path() -> Optional[Path]:
    """
    Определяет каталог с браузерами Chromium для Playwright.

    Порядок приоритета:
      1. `PLAYWRIGHT_BROWSERS_PATH` из окружения или `.env` — явная настройка
         пользователя всегда побеждает.
      2. Папка `pw-browsers`, упакованная внутрь сборки (когда в spec
         выставлен BUNDLE_BROWSERS = True).
      3. Штатный кэш текущей ОС (`~/.cache/ms-playwright` на Linux,
         `%LOCALAPPDATA%/ms-playwright` на Windows).

    Возвращает None, если ни один каталог не найден: в этом случае
    переменную окружения задавать нельзя, иначе Playwright будет искать
    браузер по неверному пути и упадёт с невнятной ошибкой.
    """
    for env_key in ("PLAYWRIGHT_BROWSERS_PATH", "PW_BROWSERS_PATH"):
        raw_value = os.environ.get(env_key)
        if not raw_value:
            continue
        candidate = Path(raw_value).expanduser()
        if not candidate.is_absolute():
            candidate = bundle_root() / candidate
        if _is_usable_browsers_dir(candidate):
            return candidate

    bundled = bundle_root() / BROWSERS_DIR_NAME
    if _is_usable_browsers_dir(bundled):
        return bundled

    default = _platform_default_browsers_dir()
    if _is_usable_browsers_dir(default):
        return default

    return None
