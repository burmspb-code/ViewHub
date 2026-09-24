"""Базовый класс для потоков сканеров."""

import logging
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from scaner_classes import BaseScaner

logger = logging.getLogger(__name__)


class ScanerWorker(QObject):
    """
    Универсальный рабочий поток PyQt6 для работы с объектами сканеров.
    """
    # Определение сигналов для взаимодействия с главным UI-потоком
    progress_signal = pyqtSignal(str)     # Статус выполнения для GUI (например, "Обработано 5/100")
    finished_signal = pyqtSignal(object)  # Сигнал завершения (передает финальные данные или None)

    def __init__(self, scaner: "BaseScaner"):
        super().__init__()
        self.scaner: "BaseScaner" = scaner
        self._stop_event = threading.Event()  # Потокобезопасный флаг остановки

    def stop(self) -> None:
        """Метод для безопасной остановки потока извне."""
        self._stop_event.set()

    def is_stopped(self) -> bool:
        """Проверка, был ли сигнал на остановку потока."""
        return self._stop_event.is_set()

    def run(self):
        """Основная логика выполнения потока."""
        try:
            logger.info("Запуск процесса сканирования...")

            # Запускаем сканирование и передаем сам воркер (self) внутрь сканера
            result = self.scaner.run_scanning(worker=self)

            # Проверяем, не прервал ли пользователь поток во время долгой работы
            if self.is_stopped() or result is None:
                logger.info("Сканирование успешно прервано пользователем.")
                self.finished_signal.emit(None)
                return

            # Если всё прошло успешно — отправляем собранные данные
            self.finished_signal.emit(result)

        except Exception as e:
            logger.exception("Критическая ошибка в потоке: %s", e)
            # При ошибке также уведомляем интерфейс, чтобы избежать зависания кнопок
            self.finished_signal.emit(None)
