"""
Модуль базовых абстрактных классов для создания гибкой системы парсинга,
сканирования, логирования, сохранения данных.
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple, Generator, List, ClassVar, Optional

ColumnSpec = Tuple[str, ...]  # (тип, ограничение1, ограничение2, ...)


class BaseConfig:
    """Класс конфигурации. Единый формат: голые Python-типы."""

    # Бизнес-ключ для дедупликации (UPSERT)
    DEDUP_COLUMN: str = "item_id"

    # Схема: имя колонки -> Python-тип.
    # Технические поля (id, created_at, page_number, session_id) сюда НЕ входят:
    # их генерирует сейвер.
    COLUMNS: ClassVar[Dict[str, type]] = {
        "item_id": str,
        "name": str,
        "brand": str,
        "price": float,
        "url": str,
    }

    # Этим колонкам сейвер добавит NOT NULL при создании таблицы
    NOT_NULL_COLUMNS: Tuple[str, ...] = ("item_id",)

    # Ограничения уровня таблицы.
    # Если PRIMARY KEY здесь не указан — сейвер сам добавит технический "id".
    TABLE_CONSTRAINTS: Tuple[str, ...] = ("UNIQUE (item_id)",)

    def __init__(self, target_url: str, keyword: str, file_name: str) -> None:
        self.target_url = target_url
        self.keyword = keyword
        self.file_name = file_name

    @classmethod
    def get_table_columns(cls) -> Dict[str, type]:
        """Схема бизнес-колонок: имя -> Python-тип."""
        return dict(cls.COLUMNS)

    @classmethod
    def get_key_column(cls) -> str:
        """
        Ключ для UPSERT: берём PRIMARY KEY (col) из TABLE_CONSTRAINTS.
        Если его нет — используем DEDUP_COLUMN (технический 'id'
        сейвер создаст сам).
        """
        for constraint in cls.TABLE_CONSTRAINTS or ():
            m = re.search(
                r'\bPRIMARY\s+KEY\s*$\s*"?(\w+)"?\s*$',
                str(constraint),
                re.IGNORECASE,
            )
            if m:
                return m.group(1)
        return cls.DEDUP_COLUMN


class BaseSaver(ABC):
    """
    Абстрактный класс для сохранения результатов.
    Позволяет абстрагировать способ вывода данных (CSV, Excel, База данных).
    """

    def __init__(self, file_name: Optional[str] = None) -> None:
        self.file_name = file_name

    @abstractmethod
    def save(self, data: List[Dict[str, Any]], page_number: int | None) -> bool:
        """
        Записывает переданную порцию данных в целевое хранилище.
        """
        pass


class BaseExtractor(ABC):
    """
    Абстрактный класс для извлечения данных из сырого контента.
    """

    @abstractmethod
    def extract_data(self, raw_content: Any) -> List[Dict[str, Any]]:
        """
        Извлекает полезные данные из сырого ответа сервера.
        """
        pass


class BaseParser(ABC):
    """
    Абстрактный класс для управления сетевой логикой и навигацией по сайту.
    """

    def __init__(self, config: BaseConfig, extractor: BaseExtractor, saver: BaseSaver):
        self.config: BaseConfig = config
        self.extractor: BaseExtractor = extractor
        self.saver: BaseSaver = saver
        self._is_running: bool = True

    def cancel(self) -> None:
        """Метод для сигнализации парсеру о необходимости прервать работу."""
        self._is_running = False

    # Хук-обработчик отмены парсинга.
    # Вызывается автоматически внутри метода cancel() перед остановкой основного цикла.
    # Предназначен для кастомной очистки ресурсов конкретного сайта.
    # Переопределение метода опционально. При переопределении вызывайте super()._on_cancel().
    def _on_cancel(self) -> None: # noqa: B027
        pass

    @abstractmethod
    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        """
        Основной метод-генератор, реализующий логику сбора данных.
        """
        pass


class BaseScaner(ABC):
    """
    Абстрактный класс для управления сканированием.
    """
    def __init__(self, base_url: str):
        self.base_url = base_url

    @abstractmethod
    def run_scanning(self, worker) -> list:
        """
        Основной метод логики сканирования.
        Обязан регулярно проверять worker.is_stopped() для прерывания работы.
        """
        pass
