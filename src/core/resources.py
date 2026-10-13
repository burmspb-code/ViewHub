"""
Модуль для управления внешними ресурсами (иконки, изображения, шрифты) приложения ViewHub.
"""

import logging

from PyQt6.QtGui import QIcon

from src.core.paths import bundle_root

logger = logging.getLogger()


def load_app_icon() -> QIcon:
    """
    Находит на диске и возвращает объект иконки приложения.
    """
    # Ресурсы лежат в корне сборки (onedir -> _internal, onefile -> /tmp),
    # а не рядом с исполняемым файлом. Логика вынесена в src.core.paths.
    root_dir = bundle_root()

    # Точный путь, как у вас на скриншоте
    icon_path = root_dir / "src" / "core" / "assets" / "app_icon.png"

    if icon_path.exists():
        logger.info("Файл иконки успешно найден и загружен.")
        return QIcon(str(icon_path))

    logger.warning(f"Файл иконки не найден по пути: {icon_path}. Будет использована системная иконка по умолчанию.")
    return QIcon()
