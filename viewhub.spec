# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

# Dynamically collect Playwright binaries
datas = [
    ('src/core/assets/app_icon.png', 'src/core/assets')
]

# Try to find and add Playwright Chromium binaries
try:
    from playwright.sync_api import sync_playwright
    import playwright
    
    # Get playwright installation path
    playwright_path = Path(playwright.__file__).parent
    
    # Add chromium binaries if they exist
    chromium_path = playwright_path / 'driver' / 'packages' / 'chromium'
    if chromium_path.exists():
        for item in chromium_path.iterdir():
            if item.is_dir():
                datas.append((str(item), f'playwright/chromium/{item.name}'))
except Exception:
    pass

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'playwright',
        'playwright.sync_api',
        'playwright.async_api',
        'playwright_stealth',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_playwright.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='viewhub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Enable console for debugging on Linux
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
