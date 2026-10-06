"""
Модуль для управления внешними ресурсами (иконки, изображения, шрифты) приложения ViewHub.
"""

import sys
import logging
from pathlib import Path

from PyQt6.QtGui import QIcon

logger = logging.getLogger()


def load_app_icon() -> QIcon:
    """
    Находит на диске и возвращает объект иконки приложения.
    """
    if getattr(sys, "frozen", False):
        # Безопасно получаем путь к временной папке через getattr
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            root_dir = Path(meipass)
        else:
            root_dir = Path(sys.executable).resolve().parent
    else:
        root_dir = Path.cwd()

    # Точный путь, как у вас на скриншоте
    icon_path = root_dir / "src" / "core" / "assets" / "app_icon.png"

    if icon_path.exists():
        logger.info("Файл иконки успешно найден и загружен.")
        return QIcon(str(icon_path))

    logger.warning(f"Файл иконки не найден по пути: {icon_path}. Будет использована системная иконка по умолчанию.")
    return QIcon()
