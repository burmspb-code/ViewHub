# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import copy_metadata

# Собираем метаданные Playwright
datas = []
datas += copy_metadata('playwright')

# Упаковываем локальный браузер Chromium
# ВАЖНО!!! Требует предварительного выполнения $env:PLAYWRIGHT_BROWSERS_PATH="pw-browsers" и playwright install chromium
datas += [('pw-browsers', 'pw-browsers')]

# Указываем PyInstaller взять папку с иконкой и положить ее по точно такому же пути внутрь exe
datas += [('src/core/assets', 'src/core/assets')]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['playwright'], # Прямо говорим импортировать playwright
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Упаковка чистых скриптов Python
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,       # Вшиваем бинарники внутрь EXE
    a.datas,          # Вшиваем данные и картинки внутрь EXE
    [],
    exclude_binaries=False,
    name='viewhub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    onefile=True,     # <--- ЯВНО УКАЗЫВАЕМ СБОРКУ В ОДИН ФАЙЛ
)
