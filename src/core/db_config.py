import os
from pathlib import Path
from typing import Optional


class DBConfig:
    """
    Слой конфигурации базы данных.
    Отвечает за формирование пути к БД и чтение переменных окружения.
    """

    DEFAULT_DB_NAME = "viewhub.db"

    @classmethod
    def get_db_path(cls, custom_path: Optional[str] = None) -> Path:
        """
        Возвращает абсолютный путь к файлу БД.
        Приоритет:
        1. Переданный аргумент custom_path — явное указание побеждает всё
        2. Переменная окружения DB_PATH — настройка по умолчанию для машины
        3. Путь по умолчанию (data/viewhub.db)
        """
        # 1. Явный аргумент имеет наивысший приоритет
        if custom_path:
            return Path(custom_path).expanduser().resolve()

        # 2. Переменная окружения
        env_path = os.getenv("DB_PATH")
        if env_path:
            return Path(env_path).expanduser().resolve()

        # 3. Путь по умолчанию
        # Поднимаемся из src/core/db_config.py на 3 уровня вверх,
        # чтобы попасть в корень проекта
        root_dir = Path(__file__).resolve().parent.parent.parent
        data_dir = root_dir / "data"

        # Создаем папку data, если её нет
        data_dir.mkdir(parents=True, exist_ok=True)

        return data_dir / cls.DEFAULT_DB_NAME

