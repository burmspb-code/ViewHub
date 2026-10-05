import sys
import os
from pathlib import Path
from typing import Optional


class DBParsingConfig:
    """
    Слой конфигурации базы данных для парсинга.
    Отвечает за формирование пути к БД и чтение переменных окружения.
    """

    DEFAULT_DB_NAME = "viewhub_parsing.db"

    @classmethod
    def get_db_path(cls, custom_path: Optional[str] = None) -> Path:
        """
        Возвращает абсолютный путь к файлу БД.
        Приоритет:
        1. Переданный аргумент custom_path — явное указание побеждает всё
        2. Переменная окружения DB_PATH_PARSING — настройка по умолчанию для машины
        3. Путь по умолчанию: storage/viewhub_parsing.db
        """
        # 1. Определяем корень там, откуда ЗАПУЩЕНА программа
        if getattr(sys, "frozen", False):
            # Если запущен скомпилированный .exe, берем папку, где лежит этот .exe
            root_dir = Path(sys.executable).resolve().parent
        else:
            # Если запускаем main.py из корня проекта, то текущая рабочая директория (CWD)
            # и есть корень нашего проекта.
            root_dir = Path.cwd()

        # 2. Явный аргумент
        if custom_path:
            return Path(custom_path).expanduser().resolve()

        # 3. Переменная окружения
        env_path = os.getenv("DB_PATH_PARSING")
        if env_path:
            path_obj = Path(env_path)
            if not path_obj.is_absolute():
                resolved_path = (root_dir / path_obj).resolve()
            else:
                resolved_path = path_obj.expanduser().resolve()

            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            return resolved_path

        # 4. Путь по умолчанию (создает storage/ в корне, где лежит main.py или .exe)
        data_dir = root_dir / "storage"
        data_dir.mkdir(parents=True, exist_ok=True)

        return data_dir / cls.DEFAULT_DB_NAME