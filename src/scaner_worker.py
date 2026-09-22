"""Базовый класс для потоков сканеров."""

import threading

from PyQt6.QtCore import QThread, pyqtSignal

from scaner_classes import BaseScaner


class ScanerWorker(QThread):
    """
    Универсальный рабочий поток PyQt6 для работы с объектами сканеров.
    """
    # Определение сигналов для взаимодействия с главным UI-потоком
    progress_signal = pyqtSignal(str)  # Статус выполнения для GUI (например, "Обработано 5/100")
    finished_signal = pyqtSignal(object)  # Сигнал завершения (передает финальные данные)
    logging_signal = pyqtSignal(str)  # Сигнал для логирования ошибок и отладочной информации

    def __init__(self, scaner: "BaseScaner"):
        super().__init__()
        self.scaner: "BaseScaner" = scaner
        self._stop_event = threading.Event()  # Потокобезопасный флаг остановки

    def stop(self):
        """Метод для безопасной остановки потока извне."""
        self._stop_event.set()

    def is_stopped(self) -> bool:
        """Проверка, был ли сигнал на остановку потока."""
        return self._stop_event.is_set()

    def run(self):
        """Основная логика выполнения потока."""
        try:
            # Пример интеграции с вашим объектом BaseScaner
            # Внутри методов scaner обязательно проверяйте self.is_stopped()

            self.logging_signal.emit("Запуск процесса сканирования...")

            # Логика вашего сканера должна быть адаптирована под проверку _stop_event
            result = None # Временная заглушка
            # result = self.scaner.start_scan(worker=self)

            if self.is_stopped():
                self.logging_signal.emit("Сканирование прервано пользователем.")
                return

            self.finished_signal.emit(result)

        except Exception as e:
            self.logging_signal.emit(f"Критическая ошибка в потоке: {e!s}")
