"""
Модуль базовых абстрактных классов для создания гибкой системы парсинга.
Обеспечивает разделение бизнес-логики сетевых запросов, извлечения данных,
сохранения результатов и работы в фоновом потоке PyQt6.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, List

from PyQt6.QtCore import QThread, pyqtSignal

# Убедитесь, что этот модуль существует в вашем проекте
from exceptions import ExceptionStopParser


class BaseConfig:
    """
    Абстрактный класс конфигурации.
    """

    def __init__(
            self,
            target_url: str,
            keyword: str = "",
            file_name: str = "",
            config: Dict[str, Any] | None = None
    ) -> None:

        self.target = target_url
        self.keyword = keyword
        self.file_name = file_name
        self.config = config if config is not None else {}


class BaseSaver(ABC):
    """
    Абстрактный класс для сохранения результатов.
    Позволяет абстрагировать способ вывода данных (CSV, Excel, База данных).
    """

    @abstractmethod
    def initialize(self, file_name: str) -> None:
        """
        Подготавливает целевое хранилище к новому запуску (например, очищает файл).
        Переопределяется в дочерних классах по мере необходимости.
        """
        pass

    @abstractmethod
    def save(self, data: List[Dict[str, Any]], file_name: str) -> bool:
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
        self.setup: BaseConfig = config
        self.extractor: BaseExtractor = extractor
        self.saver: BaseSaver = saver
        self._is_running: bool = True

    def cancel(self) -> None:
        """Метод для сигнализации парсеру о необходимости прервать работу."""
        self._is_running = False

    @abstractmethod
    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        """
        Основной метод-генератор, реализующий логику сбора данных.
        """
        pass


class BaseParserWorker(QThread):
    """
    Универсальный рабочий поток PyQt6.
    """

    progress_signal = pyqtSignal(str)  # Статус для GUI
    finished_signal = pyqtSignal(str)  # Сигнал об успешном завершении (передает путь к файлу или статус)
    logging_signal = pyqtSignal(str)   # Сигнал ошибок/логов

    def __init__(self, parser: BaseParser):
        super().__init__()
        self.parser: BaseParser = parser
        self._is_running: bool = True
        self.saver: BaseSaver = parser.saver
        self.file_name: str = parser.setup.file_name

    def run(self) -> None:
        """
        Точка входа в поток.
        """
        try:

            # Универсальный вызов подготовки файла:
            # Работает прозрачно для любого Saver-а (CSV, JSON, XLSX)
            if self.saver:
                self.saver.initialize(self.file_name)

            total_items_count = 0

            # Итерируемся по генератору парсера
            for data_chunk in self.parser.run_parsing():
                # Проверяем остановку со стороны GUI
                if not self._is_running:
                    self.parser.cancel()
                    break

                if not data_chunk:
                    continue

                total_items_count += len(data_chunk)

                # Архитектурное улучшение: сохраняем порцию сразу, чтобы не терять данные
                if self.saver:
                    self.saver.save(data_chunk, self.file_name)

                # Отправляем данные в интерфейс
                self.progress_signal.emit(f"📦 Получено в чанке: {len(data_chunk)}"
                                          f" | Всего собрано: {total_items_count}")

            # Формируем финальный статус завершения
            if self._is_running:
                self.progress_signal.emit(f"🎉 Готово! Всего обработано элементов: {total_items_count}")
                self.finished_signal.emit(self.file_name)
            else:
                self.finished_signal.emit("Процесс парсинга был остановлен пользователем.")

        except ExceptionStopParser as e:
            self.logging_signal.emit(f"🛑 Процесс остановлен по условию: {e}")
            self.finished_signal.emit(self.file_name)

        except Exception as e:
            error_text = str(e)
            self.logging_signal.emit(f"❌ Критическая ошибка: {error_text}")
            self.progress_signal.emit(error_text.splitlines()[0].strip())
            self.finished_signal.emit("")

    def stop(self) -> None:
        """
        Вызывается из главного UI потока для остановки.
        """
        self._is_running = False
        self.parser.cancel()
