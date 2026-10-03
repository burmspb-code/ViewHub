import os
import sys
import logging

from dotenv import load_dotenv
from src.core.logger import setup_logger

# Этот код сработает автоматически при первом импорте из папки src
load_dotenv()
setup_logger(name="", level=logging.INFO)

# Если приложение скомпилировано в PyInstaller
if getattr(sys, "frozen", False):
    # На Windows задаем путь к локальному AppData пользователя
    if sys.platform.startswith("win"):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.environ["LOCALAPPDATA"], "ms-playwright")
    # На Linux задаем путь к кэшу root, как мы настраивали на сервере
    elif sys.platform.startswith("linux"):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/root/.cache/ms-playwright"
