"""Runtime hook for Playwright in PyInstaller bundles."""

import os
import sys
from pathlib import Path

def _setup_playwright_paths():
    """Configure Playwright to find its binaries in PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle
        # Set PLAYWRIGHT_BROWSERS_PATH to the bundled chromium
        bundle_dir = Path(sys._MEIPASS)
        playwright_chromium_path = bundle_dir / 'playwright' / 'chromium'
        
        if playwright_chromium_path.exists():
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(playwright_chromium_path)
            print(f"Playwright browsers path set to: {playwright_chromium_path}")

# Execute at import time
_setup_playwright_paths()
