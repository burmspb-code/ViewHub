"""Сервисный слой для сканирования."""

import logging

from contextlib import suppress

from PyQt6.QtCore import QThread

from src.scanners.async_scan_ep import AsyncScanEndpoint
from src.workers.scanner_worker import ScannerWorker

from .ui_helpers import _update_parsing_status, _scanning_success_handler

logger = logging.getLogger(__name__)


def scanning_on_click(obj) -> None:
    """Запуск универсального асинхронного экспресс-сканирования."""

    # Считываем ссылку для сканирования
    base_url = obj.base_url_input.text().strip()
    # Устанавливаем нужный сканер
    scaner = AsyncScanEndpoint(base_url)

    # Если менеджер забыл ввести ссылку, подсвечиваем поле
    if not base_url:
        with suppress(Exception):
            obj.base_url_input.setStyleSheet("border: 1px solid #ef4444;")
        return

    # Сбрасываем красную рамку, если ссылка введена
    with suppress(Exception):
        obj.base_url_input.setStyleSheet("")

    # Блокируем элементы управления, чтобы избежать повторных кликов во время работы
    if obj.btn_send_scanning:
        obj.btn_send_scanning.setEnabled(False)

    if obj.btn_send_parsing:
        obj.btn_send_parsing.setEnabled(False)

    # Создаем чистый системный поток
    obj.scaner_thread = QThread()

    # Создаем рабочий объект
    obj.scaner_worker = ScannerWorker(scaner=scaner)

    # Перемещаем объект в фоновый поток
    obj.scaner_worker.moveToThread(obj.scaner_thread)

    # Связываем запуск потока с выполнением метода run()
    obj.scaner_thread.started.connect(obj.scaner_worker.run)

    # Цепочка очистки после остановки потока:
    # Закрываем поток после завершения работы воркера
    obj.scaner_worker.finished_signal.connect(obj.scaner_thread.quit)

    # Удаляем тред из памяти
    obj.scaner_thread.finished.connect(obj.scaner_thread.deleteLater)

    # Так же удаляем воркер из памяти
    obj.scaner_thread.finished.connect(obj.scaner_worker.deleteLater)

    # Подключаем сигналы воркера
    obj.scaner_worker.progress_signal.connect(lambda msg: _update_parsing_status(obj, msg))
    obj.scaner_worker.finished_signal.connect(lambda obj_scan: _scanning_success_handler(obj, obj_scan))

    obj.result_display.append(f"⏳ Запуск сканера для сайта: {base_url}")
    logger.info(f"Старт сканера по адресу {base_url}")

    # Запускаем поток
    obj.scaner_thread.start()


def scanning_cancel_on_click(obj) -> None:
    """Обработчик нажатия на кнопку 'ОТМЕНИТЬ' во время сканирования."""
    # Проверяем, запущен ли поток сканера в данный момент
    if hasattr(obj, "scaner_thread") and obj.scaner_thread.isRunning():
        logger.info("Запрос на отмену сканирования отправлен пользователем...")

        # Выводим красивый статус пользователю в текстовую панель
        if hasattr(obj, "result_display"):
            obj.result_display.append("🛑 Останавливаем сканирование, пожалуйста, подождите...")

        # Делаем кнопку отмены временно неактивной, чтобы избежать спам-кликов
        if hasattr(obj, "btn_cancel_scanning"):
            obj.btn_cancel_scanning.setEnabled(False)

        # Поднимаем потокобезопасный флаг остановки внутри воркера.
        # Асинхронный наблюдатель watcher_task внутри сканера поймает этот флаг
        # за 100 мс и мгновенно прервет сетевые запросы.
        if hasattr(obj, "scaner_worker"):
            obj.scaner_worker.stop()
    else:
        logger.warning("Невозможно отменить сканирование: процесс не запущен или уже завершен.")
