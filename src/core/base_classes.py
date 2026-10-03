"""
Модуль базовых абстрактных классов для создания гибкой системы парсинга,
сканирования, логирования, сохранения данных.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, List, ClassVar, Optional


class BaseDataBase(ABC):
    """Абстрактный класс для работы с базами данных."""

    @abstractmethod
    def _connect(self):
        """Устанавливает соединение с БД."""
        pass


class BaseDBParsingConfig(ABC):
    """Абстрактный класс конфигурации базы данных для парсинга."""

    # Системные колонки по умолчанию для SQLite
    SYSTEM_COLUMNS: ClassVar[Dict[str, str]] = {
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "session_id": "TEXT NOT NULL",  # В SQLite UUID хранят как TEXT
    }

    # Дефолтные констрейнты таблицы (по умолчанию пустые)
    TABLE_CONSTRAINTS: ClassVar[tuple] = ()

    def __init__(self, target_url: str, keyword: str = "", file_name: str = "") -> None:
        self.target_url = target_url
        self.keyword = keyword
        self.file_name = file_name

    @classmethod
    def get_key_column(cls) -> str:
        """Возвращает системный PRIMARY KEY таблицы."""
        return "id"

    @classmethod
    @abstractmethod
    def get_full_schema(cls) -> Dict[str, str]:
        """Возвращает схему всех колонок таблицы."""
        pass


class BaseSaver(ABC):
    """
    Абстрактный класс для сохранения результатов.
    Позволяет абстрагировать способ вывода данных (CSV, Excel, База данных).
    """

    def __init__(self, file_name: Optional[str] = None) -> None:
        self.file_name = file_name

    @abstractmethod
    def save(self, data: List[Dict[str, Any]]) -> bool:
        """Записывает данные в файл."""
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

    def __init__(self, config: BaseDBParsingConfig, extractor: BaseExtractor, manager: BaseDataBase):
        self.config: BaseDBParsingConfig = config
        self.extractor: BaseExtractor = extractor
        self.manager: BaseDataBase = manager
        self._is_running: bool = True

    def cancel(self) -> None:
        """Метод для сигнализации парсеру о необходимости прервать работу."""
        self._is_running = False

    # Хук-обработчик отмены парсинга.
    # Вызывается автоматически внутри метода cancel() перед остановкой основного цикла.
    # Предназначен для кастомной очистки ресурсов конкретного сайта.
    # Переопределение метода опционально. При переопределении вызывайте super()._on_cancel().
    def _on_cancel(self) -> None:  # noqa: B027
        pass

    @abstractmethod
    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        """
        Основной метод-генератор, реализующий логику сбора данных.
        """
        pass


class BaseScanner(ABC):
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
