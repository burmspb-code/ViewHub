"""
Модуль для управления внешними ресурсами (иконки, изображения, шрифты) приложения ViewHub.
"""

import logging
from pathlib import Path

from PyQt6.QtGui import QIcon

logger = logging.getLogger()


def load_app_icon() -> QIcon:
    """
    Находит на диске и возвращает объект иконки приложения.

    Если файл не найден, логирует предупреждение и возвращает пустой QIcon,
    что предотвращает падение графического интерфейса.
    """
    # Надежно вычисляем путь: данный файл лежит в src/core/,
    # выходим на два уровня вверх к корню проекта и идем в assets/
    icon_path = Path(__file__).resolve().parent / "assets" / "app_icon.png"

    if icon_path.exists():
        logger.info("Файл иконки успешно найден и загружен.")
        return QIcon(str(icon_path))

    logger.warning(
        f"Файл иконки не найден по пути: {icon_path}. "
        f"Будет использована системная иконка по умолчанию."
    )
    return QIcon()
