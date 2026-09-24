"""
Модуль базовых абстрактных классов для создания гибкой системы парсинга.
Обеспечивает разделение бизнес-логики сетевых запросов, извлечения данных,
сохранения результатов и работы в фоновом потоке PyQt6.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, List


class BaseConfig:
    """
    Абстрактный класс конфигурации.
    """

    def __init__(
        self, target_url: str, keyword: str = "", file_name: str = "", config: Dict[str, Any] | None = None
    ) -> None:

        self.target_url = target_url
        self.keyword = keyword
        self.file_name = file_name
        self.config = config if config is not None else {}


class BaseSaver(ABC):
    """
    Абстрактный класс для сохранения результатов.
    Позволяет абстрагировать способ вывода данных (CSV, Excel, База данных).
    """

    def __init__(self, file_name: str):
        self.file_name = file_name

    @abstractmethod
    def save(self, data: List[Dict[str, Any]]) -> bool:
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
    def _on_cancel(self) -> None:
        pass # noqa: B027

    @abstractmethod
    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        """
        Основной метод-генератор, реализующий логику сбора данных.
        """
        pass
