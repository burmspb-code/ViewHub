"""
Модуль базовых абстрактных классов для создания гибкой системы парсинга.
Обеспечивает разделение бизнес-логики сетевых запросов, извлечения данных,
сохранения результатов и работы в фоновом потоке PyQt6.
"""

from abc import ABC, abstractmethod
from typing import Generator, Any, List, Dict
from PyQt6.QtCore import QThread, pyqtSignal


class BaseExtractor(ABC):
    """
    Абстрактный класс для извлечения данных из сырого контента.
    Реализации этого класса будут отвечать исключительно за парсинг HTML/JSON
    (например, с помощью BeautifulSoup, lxml, selectolax или регулярных выражений).
    """

    @abstractmethod
    def extract_data(self, raw_content: Any) -> List[Dict[str, Any]]:
        """
        Извлекает полезные данные из сырого ответа сервера.

        :param raw_content: Строка HTML, JSON-словарь или любой другой сырой объект.
        :return: Список словарей с извлеченными данными.
        """
        pass


class BaseParser(ABC):
    """
    Абстрактный класс для управления сетевой логикой и навигацией по сайту.
    Определяет стратегию обхода страниц (классический цикл, скролл, запросы к API).
    """

    def __init__(self, base_url: str, extractor: BaseExtractor):
        """
        Инициализирует парсер. Внедряет зависимость экстрактора (композиция).

        :param base_url: Стартовый URL-адрес для парсинга.
        :param extractor: Экземпляр класса, реализующего BaseExtractor.
        """
        self.base_url: str = base_url
        self.extractor: BaseExtractor = extractor
        # Флаг для остановки внутренних циклов парсера (например, в Selenium/Playwright)
        self._is_running: bool = True

    def cancel(self) -> None:
        """Метод для сигнализации парсеру о необходимости прервать работу."""
        self._is_running = False

    @abstractmethod
    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        """
        Основной метод-генератор, реализующий логику сбора данных.
        Должен пошагово возвращать (yield) порции данных по мере их получения.
        Внутри метода необходимо проверять состояние self._is_running в циклах.

        :return: Генератор, выдающий списки словарей с данными.
        """
        pass


class BaseSaver(ABC):
    """
    Абстрактный класс для сохранения результатов.
    Позволяет абстрагировать способ вывода данных (CSV, Excel, База данных).
    """

    @abstractmethod
    def save(self, data: List[Dict[str, Any]], destination: str) -> None:
        """
        Записывает переданную порцию данных в целевое хранилище.

        :param data: Список словарей с данными.
        :param destination: Путь к файлу или строка подключения к БД.
        """
        pass


class BaseParserWorker(QThread):
    """
    Универсальный рабочий поток PyQt6.
    Управляет жизненным циклом парсинга в фоновом режиме, исключая зависание GUI.
    Не привязан к конкретному сайту или структуре данных.
    """
    # Безопасные сигналы для взаимодействия с главным окном PyQt
    data_parsed = pyqtSignal(list)          # Передает очередную пачку данных (List[Dict])
    progress_updated = pyqtSignal(str)     # Передает текстовый статус для GUI (например, "Обработано 3 страницы")
    finished_success = pyqtSignal(str)      # Сигнал об успешном завершении
    error_occurred = pyqtSignal(str)        # Сигнал в случае критического сбоя

    def __init__(self, parser: BaseParser, saver: BaseSaver = None, save_destination: str = ""):
        """
        Инициализирует рабочий поток.

        :param parser: Объект конкретного парсера, унаследованный от BaseParser.
        :param saver: Опциональный объект сейвера для автоматического сохранения на лету.
        :param save_destination: Путь к файлу или БД, куда saver будет писать данные.
        """
        super().__init__()
        self.parser: BaseParser = parser
        self.saver: BaseSaver = saver
        self.save_destination: str = save_destination
        self._is_running: bool = True

    def run(self) -> None:
        """
        Точка входа в поток. Запускается автоматически при вызове .start() из GUI.
        Последовательно итерируется по генератору парсера.
        """
        try:
            # Запрашиваем генератор у парсера
            for data_chunk in self.parser.run_parsing():
                # Проверяем, не нажал ли пользователь "Стоп" в интерфейсе
                if not self._is_running:
                    self.parser.cancel()
                    break

                if not data_chunk:
                    continue

                # 1. Отправляем данные в интерфейс (например, для отображения в QTableWidget)
                self.data_parsed.emit(data_chunk)

                # 2. Если передан класс сохранения, автоматически пишем данные на диск/в БД
                if self.saver and self.save_destination:
                    self.saver.save(data_chunk, self.save_destination)

            # Формируем финальный статус завершения
            if self._is_running:
                self.finished_success.emit("Парсинг успешно завершен!")
            else:
                self.finished_success.emit("Процесс парсинга был остановлен пользователем.")

        except Exception as e:
            # Перехватываем любые ошибки (Network, Parsing, IO) и отправляем в GUI для вывода в QMessageBox
            self.error_occurred.emit(f"Критическая ошибка в потоке: {str(e)}")

    def stop(self) -> None:
        """
        Вызывается из главного UI потока для экстренной или плановой
        остановки сбора данных.
        """
        self._is_running = False
        self.parser.cancel()
