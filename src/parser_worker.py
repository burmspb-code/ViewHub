"""Базовый класс для потоков парсинга."""


from PyQt6.QtCore import QThread, pyqtSignal

from parser_classes import BaseParser, BaseSaver
from exceptions import ExceptionStopParser


class ParserWorker(QThread):
    """
    Универсальный рабочий поток PyQt6.
    """

    progress_signal = pyqtSignal(str)  # Статус для GUI
    finished_signal = pyqtSignal(str)  # Сигнал об успешном завершении (передает путь к файлу или статус)
    logging_signal = pyqtSignal(str)  # Сигнал ошибок/логов

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
                self.progress_signal.emit(
                    f"📦 Получено в чанке: {len(data_chunk)} | Всего собрано: {total_items_count}"
                )

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
