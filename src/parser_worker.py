"""Базовый класс для потоков парсинга."""

import logging
import threading  # ИСПРАВЛЕНО: Добавлен обязательный импорт

from PyQt6.QtCore import QObject, pyqtSignal

from exceptions import ExceptionStopParser
from parser_classes import BaseParser, BaseSaver

logger = logging.getLogger(__name__)


class ParserWorker(QObject):
    """
    Универсальный рабочий поток PyQt6.
    """

    progress_signal = pyqtSignal(str)  # Статус для GUI
    finished_signal = pyqtSignal(str)  # Сигнал об успешном завершении (передает путь к файлу или статус)
    stop_signal = pyqtSignal(str)  # Сигнал о принудительной остановке

    def __init__(self, parser: BaseParser):
        super().__init__()
        self.parser: BaseParser = parser
        # Используем потокобезопасный Event вместо обычного bool
        self._stop_event = threading.Event()
        self.saver: BaseSaver = parser.saver
        if hasattr(parser, "config"):
            self.file_name: str = parser.config.file_name
        else:
            self.file_name: str = "result"

    def run(self) -> None:
        """
        Точка входа в поток.
        """

        total_items_count = 0
        try:
            # Итерируемся по генератору парсера
            for data_chunk in self.parser.run_parsing():
                # Проверяем остановку со стороны GUI
                if self._stop_event.is_set():
                    raise ExceptionStopParser("Процесс отменен пользователем.")

                if not data_chunk:
                    continue

                total_items_count += len(data_chunk)

                # Сохраняем данные чанками
                if self.saver:
                    self.saver.save(data_chunk)

                # Отправляем данные в интерфейс
                self.progress_signal.emit(
                    f"📦 Товаров на странице: {len(data_chunk)} | Всего собрано: {total_items_count}"
                )

            # Если нет данных выбрасываем исключение
            if total_items_count == 0:
                raise ExceptionStopParser("Данные не обнаружены.")

            # Формируем финальный статус завершения
            if not self._stop_event.is_set():
                self.progress_signal.emit(f"Всего обработано элементов: {total_items_count}")
                self.finished_signal.emit(self.file_name)

        except ExceptionStopParser as e:
            logger.info("Парсер сгенерировал исключение остановки: %s", e)
            self.stop_signal.emit(f"Всего найдено элементов: {total_items_count}")

        except Exception as e:
            error_text = str(e)
            logger.exception("❌ Критическая ошибка: %s", error_text)

            # Безопасное извлечение первой строки (без падения на пустых Exception)
            lines = error_text.splitlines()
            short_error = lines[0].strip() if lines else "Неизвестная ошибка выполнения"
            self.progress_signal.emit(short_error)

            self.finished_signal.emit("")

    def stop(self) -> None:
        """
        Вызывается из главного UI потока для остановки.
        """
        self._stop_event.set()
        # Сигнализируем самому парсеру (requests сессии или Playwright-циклу), что нужно прерваться
        self.parser.cancel()
