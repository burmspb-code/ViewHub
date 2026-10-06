"""
Инициализация пакета src.

Выполняется автоматически при первом импорте `src` (в том числе из
`main.py`), до создания QApplication. Здесь настраивается логирование
и определяется путь к браузерам Playwright.
"""

import os
import logging

from dotenv import load_dotenv

from src.core.logger import setup_logger
from src.core.paths import resolve_playwright_browsers_path

logger = logging.getLogger(__name__)

# .env читается первым, чтобы пользователь мог задать пути переопределением.
load_dotenv()

setup_logger(name="", level=logging.INFO)

# Путь к Chromium для Playwright.
# Раньше здесь стоял жёстко зашитый '/root/.cache/ms-playwright' для Linux,
# из-за чего упакованный в бинарник браузер игнорировался, а запуск
# от непривилегированного пользователя падал. Теперь путь вычисляется
# в src.core.paths с проверкой существования каталога.
_browsers_path = resolve_playwright_browsers_path()

if _browsers_path is not None:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_browsers_path)
    logger.info("Каталог браузеров Playwright: %s", _browsers_path)
else:
    logger.warning(
        "Каталог браузеров Playwright не найден. Установите Chromium на сервере "
        "(python -m playwright install chromium) или задайте PLAYWRIGHT_BROWSERS_PATH в .env"
    )
