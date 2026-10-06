# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — ViewHub.

Сборка выполняется ТОЛЬКО в ОС Linux и создаёт сборку в виде ДИРЕКТОРИИ
(`onedir`), а НЕ одного файла: это критично для скорости запуска, потому что
иначе ~400 МБ Chromium + Node драйвер распаковываются в /tmp при КАЖДОМ старте.

Порядок сборки (обязательно, иначе бинарник не запустится):
    cd <корень проекта>
    # только если BUNDLE_BROWSERS = True:
    PLAYWRIGHT_BROWSERS_PATH="pw-browsers" python -m playwright install chromium
    python -m PyInstaller viewhub.spec --clean --noconfirm

Результат: dist/viewhub/viewhub  (+ logs/ рядом с бинарником).
"""

import platform
import stat

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata

# =============================================================================
# НАСТРОЙКИ СБОРКИ
# =============================================================================

# Упаковывать ли Chromium внутрь сборки.
#   False (рекомендуется) — Chromium берётся из кэша Playwright, установленного
#                          на сервере (~/.cache/ms-playwright). Сборка весит
#                          ~120 МБ вместо ~550 МБ и стартует мгновенно.
#   True                 — автономный бинарник (~550 МБ). Тогда браузер обязан
#                          быть скачан под Linux на ЭТОЙ же машине.
BUNDLE_BROWSERS = False

# Печатать ли диагностику в stdout/терминал. На headless-VPS это единственный
# быстрый способ увидеть трейсбек Playwright прямо при запуске.
CONSOLE_MODE = True

# UPX-сжатие. Для сборки, содержащей Chromium и Node, UPX даёт минимальный
# выигрыш в размере, но сильно замедляет сборку и способен повредить крупные
# исполняемые файлы. По умолчанию выключено.
USE_UPX = False

# Куда класть браузеры, если BUNDLE_BROWSERS = True.
# ВНИМАНИЕ: значение должно совпадать с src.core.paths.BROWSERS_DIR_NAME,
# иначе собранное приложение не найдёт упакованный браузер.
BROWSERS_DEST = "pw-browsers"

PROJECT_ROOT = Path(SPECPATH).resolve()
BROWSERS_DIR = PROJECT_ROOT / "pw-browsers"
ASSETS_DIR = PROJECT_ROOT / "src" / "core" / "assets"

IS_LINUX = platform.system() == "Linux"


# =============================================================================
# ПРОВЕРКИ, ЧТОБЫ НЕ СОБИРАТЬ ЗАВЕДОМО СЛОМАННЫЙ БИНАРНИК
# =============================================================================

if not IS_LINUX:
    raise SystemExit(
        "\n[viewhub.spec] Сборка должна выполняться в Linux.\n"
        f"  Текущая ОС: {platform.system()}\n"
        "  Причина: Playwright Chromium платформенно-зависим. Собранный на Windows\n"
        "  Chromium внутри Linux-сборки не запустится, и парсер 'зависнет'.\n"
    )

if BUNDLE_BROWSERS and not BROWSERS_DIR.is_dir():
    raise SystemExit(
        f"[viewhub.spec] Не найдена папка с браузерами: {BROWSERS_DIR}\n"
        "  Выполните на ЭТОЙ ЖЕ Linux-машине:\n"
        '    PLAYWRIGHT_BROWSERS_PATH="pw-browsers" python -m playwright install chromium\n'
        "  Либо установите BUNDLE_BROWSERS = False в начале этого файла.\n"
    )


# =============================================================================
# RUNTIME HOOKS
# =============================================================================
# Раньше здесь был сгенерированный runtime hook, который подменял os.environ,
# чтобы пережить перетирание PLAYWRIGHT_BROWSERS_PATH в src/__init__.py.
# Этот костыль удалён: путь теперь корректно вычисляется в src/core/paths.py
# (без жёстко зашитого '/root/.cache'), а файловый логгер создаётся
# в src/core/logger.py и не стирается GUI-обработчиком.
# Хуки не нужны — оставляем список пустым.
RUNTIME_HOOKS = []


# =============================================================================
# СБОРКА ФАЙЛОВ
# =============================================================================

datas = []
binaries = []
hiddenimports = []

# --- 1. Playwright: драйвер (node + package/**) ОБЯЗАТЕЛЕН для frozen-приложения.
# compute_driver_executable() ищет <MEIPASS>/playwright/driver/node и
# <MEIPASS>/playwright/driver/package/cli.js. Собираем явно через collect_all,
# а не полагаясь на то, что PyInstaller «зацепит» их сам.
_pw_datas, _pw_binaries, _pw_hidden = collect_all("playwright")
datas += _pw_datas
binaries += _pw_binaries
hiddenimports += _pw_hidden

# --- 1a. playwright_stealth: ТОЖЕ ОБЯЗАТЕЛЕН, иначе маскировка молча отключается.
#
# В stealth.py (строки 20-42) файлы evasions/*.js читаются через
#     (Path(__file__).parent / "js" / name).read_text()
# на уровне МОДУЛЯ, то есть в момент import. Если папка js/ не попала в сборку,
# импорт падает с FileNotFoundError, а код оборачивает его в try/except —
# и парсер продолжает работу ПОЛНОСТЬЮ БЕЗ МАСКИРОВКИ, при этом
# navigator.webdriver остаётся равным true. Сайт отвечает антибот-челленджем,
# каталог не рендерится, и всё выглядит как «зависание парсера».
datas += collect_all("playwright_stealth")[0]

datas += copy_metadata("playwright")

# --- 2. Динамические импорты, которые не находит статический анализ.
hiddenimports += [
    "playwright",
    "playwright.sync_api",
    "playwright.async_api",
    "playwright._impl._driver",
    "playwright._impl._transport",
    "playwright._repo_version",
    "playwright_stealth",
    "greenlet",  # обязателен для sync_api: без него парсер падает на старте
    "greenlet._greenlet",
    "bs4",
    "soupSieve",
    "dotenv",
]

# --- 3. Ресурсы GUI (QIcon). Путь читает src/core/resources.py: _MEIPASS/src/core/assets
if ASSETS_DIR.is_dir():
    datas += [(str(ASSETS_DIR), "src/core/assets")]

# --- 4. Браузеры: по умолчанию НЕ упаковываем (см. BUNDLE_BROWSERS).
# Кладём в binaries, а не datas: COLLECT ставит 0o755 для BINARY-записей,
# поэтому исполняемые файлы Chromium (chrome, headless_shell, chrome_sandbox)
# остаются запускаемыми. Тип BINARY на Linux не зависит от расширения файла.
if BUNDLE_BROWSERS:
    binaries += [(str(BROWSERS_DIR), BROWSERS_DEST)]

# --- 5. Исключаем то, что точно не используется: ускоряет сборку и уменьшает размер.
excludes = [
    "tkinter",
    "matplotlib",
    "IPython",
    "notebook",
    "pytest",
    "PyQt6.Qt3D",
    "PyQt6.QtBluetooth",
    "PyQt6.QtCharts",
    "PyQt6.QtDataVisualization",
    "PyQt6.QtMultimedia",
    "PyQt6.QtNfc",
    "PyQt6.QtPositioning",
    "PyQt6.QtQml",
    "PyQt6.QtQuick",
    "PyQt6.QtRemoteObjects",
    "PyQt6.QtSensors",
    "PyQt6.QtSerialPort",
    "PyQt6.QtSpatialAudio",
    "PyQt6.QtSql",
    "PyQt6.QtTest",
    "PyQt6.QtWebChannel",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
]


# =============================================================================
# ANALYSIS / PYZ / EXE / COLLECT  (onedir: сборка в директорию, НЕ один файл)
# =============================================================================

a = Analysis(
    ["main.py"],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=RUNTIME_HOOKS,
    excludes=excludes,
    noarchive=False,
    optimize=0,  # НЕ включать: Playwright использует рефлексию/докстринги
)

pyz = PYZ(a.pure)

# EXE содержит ТОЛЬКО загрузчик и запись точки входа.
# Всё остальное раскладывается COLLECT в dist/viewhub/.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # <-- onedir: бинарники уходят в COLLECT
    name="viewhub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=USE_UPX,
    console=CONSOLE_MODE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=USE_UPX,
    upx_exclude=["node", "chrome", "headless_shell", "chrome_sandbox", "ffmpeg"],
    name="viewhub",
)


# =============================================================================
# ПОСТ-СБОРКА
# =============================================================================
# Гарантируем, что исполняемые файлы Playwright/Chromium имеют +x даже если
# исходные права были потеряны при копировании (git/архивы часто снимают бит).
def _fix_permissions():
    targets = ["_internal/playwright/driver/node"]
    if BUNDLE_BROWSERS:
        targets.append(f"_internal/{BROWSERS_DEST}")

    fixed = []
    dist_dir = Path(DISTPATH).resolve() / "viewhub"
    for relative in targets:
        path = dist_dir / relative
        if path.is_file():
            mode = path.stat().st_mode
            path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            fixed.append(relative)

    if BUNDLE_BROWSERS:
        browsers_root = dist_dir / "_internal" / BROWSERS_DEST
        for item in browsers_root.rglob("*"):
            if item.is_file() and not item.name.endswith((".pak", ".bin", ".dat", ".json", ".png", ".so")):
                item.chmod(item.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                fixed.append(str(item.relative_to(dist_dir)))

    if fixed:
        print(f"[viewhub.spec] Права +x установлены для {len(fixed)} исполняемых файлов")


_fix_permissions()

print(
    "\n[viewhub.spec] Сборка завершена.\n"
    f"  Режим:        onedir (директория), целевая ОС: {platform.system()}\n"
    f"  Браузеры:     {'упакованы внутрь' if BUNDLE_BROWSERS else 'берутся из глобального кэша Playwright'}\n"
    f"  Консоль:      {'включена' if CONSOLE_MODE else 'выключена'}\n"
    f"  Результат:    {Path(DISTPATH).resolve() / 'viewhub'}\n"
)