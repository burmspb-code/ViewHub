"""Сервисный слой для парсинга."""

import logging

from contextlib import suppress

from PyQt6.QtCore import QThread

from src.extractors.golden_apple_extractor import GoldenAppleExtractor
from src.parsers.golden_apple_parser import GoldenAppleParser
from src.parsers_config.golden_apple_config import GoldenAppleConfig
from src.database.sqlite_manager import DatabaseManager
from src.workers.parser_worker import ParserWorker

from .ui_helpers import _update_parsing_status, _stop_handler, _parsing_success_handler

logger = logging.getLogger(__name__)


def parsing_on_click(obj) -> None:
    """Запуск парсинга выбранного сайта в фоновом потоке."""
    # Считываем данные из текстовых полей переданного UI-объекта
    target_url = obj.target_url_input.text().strip()
    keyword = obj.key_word_input.text().strip()

    # Если менеджер забыл ввести ссылку, подсвечиваем поле
    if not target_url:
        with suppress(Exception):
            obj.target_url_input.setStyleSheet("border: 1px solid #ef4444;")
        return

    if not keyword:
        with suppress(Exception):
            obj.key_word_input.setStyleSheet("border: 1px solid #ef4444;")
        return

    # Сбрасываем красную рамку, если ссылка введена
    with suppress(Exception):
        obj.target_url_input.setStyleSheet("")

    with suppress(Exception):
        obj.key_word_input.setStyleSheet("")

    # Блокируем элементы управления, чтобы избежать повторных кликов во время работы
    if hasattr(obj, "btn_send_scanning"):
        obj.btn_send_scanning.setEnabled(False)

    if hasattr(obj, "btn_send_parsing"):
        obj.btn_send_parsing.setEnabled(False)

    # Включаем кнопку отмены
    if hasattr(obj, "btn_cancel_parsing"):
        obj.btn_cancel_parsing.setEnabled(True)

    obj.result_display.append(f"⏳ Запуск парсера для сайта: {target_url}, ключ: {keyword}")
    logger.info(f"Старт парсера по адресу {target_url}")

    # ================ Конфигурируем парсер под конкретную задачу ========================

    config = GoldenAppleConfig(target_url, keyword)
    extractor = GoldenAppleExtractor(config)

    manager = DatabaseManager()  # db_path подхватится из DBConfig: storage/viewhub_parsing.db
    parser = None  # Инициализируем для использования после try-except

    try:
        # Создаём таблицу и привязываем конфиг + session_id к сейверу
        table_name = manager.init_for_config(config)
        logger.info(f"Инициализация БД. Таблица: {table_name}, файл: {manager.db_path}")

        # Парсер создаем только если БД успешно инициализирована
        parser = GoldenAppleParser(config=config, extractor=extractor, manager=manager)

        # Сохраняем парсер в объекте окна для использования в экспорте
        obj.parser = parser

    except Exception as e:
        # Критическая ошибка инициализации БД: дальше запускать парсер нельзя
        error_msg = f"❌ Критическая ошибка инициализации базы данных: {e}"
        logger.error(error_msg)
        # Прерываем выполнение этого блока (в зависимости от твоей архитектуры, здесь может быть return или raise)
        raise RuntimeError("Не удалось подготовить базу данных. Парсинг остановлен.") from e

    # ====================================================================================

    # Включаем кнопку просмотра
    if hasattr(obj, "btn_cancel_parsing"):
        obj.btn_preview_parsing.setEnabled(True)

    # Включаем кнопку экспорта
    if hasattr(obj, "btn_cancel_parsing"):
        obj.btn_export_parsing.setEnabled(True)

    # Сначала создаем чистый системный поток QThread
    obj.parser_thread = QThread()

    # Затем создаем рабочий объект (Воркер) и передаем ему парсер
    obj.parser_worker = ParserWorker(parser=parser)

    # Прикрепляем сигнал к парсеру
    parser.progress_callback = obj.parser_worker.progress_signal.emit

    # Перемещаем воркер в фоновый поток
    obj.parser_worker.moveToThread(obj.parser_thread)

    # Связываем запуск потока с выполнением метода run() воркера
    obj.parser_thread.started.connect(obj.parser_worker.run)

    # АВТОМАТИЧЕСКАЯ ЦЕПОЧКА ОЧИСТКИ при завершении потока:
    obj.parser_worker.finished_signal.connect(obj.parser_thread.quit)
    obj.parser_worker.stop_signal.connect(obj.parser_thread.quit)

    # Безопасное удаление треда и воркера из памяти операционной системы
    obj.parser_thread.finished.connect(obj.parser_thread.deleteLater)
    obj.parser_thread.finished.connect(obj.parser_worker.deleteLater)

    # Подключаем сигналы воркера к функциям обновления UI вашего приложения
    obj.parser_worker.progress_signal.connect(lambda msg: _update_parsing_status(obj, msg))
    obj.parser_worker.finished_signal.connect(lambda path: _parsing_success_handler(obj, path))
    obj.parser_worker.stop_signal.connect(lambda msg: _stop_handler(obj, msg))

    # Запускаем фоновый поток выполнения Playwright
    obj.parser_thread.start()


def parsing_cancel_on_click(obj) -> None:
    """Обработчик нажатия на кнопку 'ОТМЕНИТЬ' во время парсинга."""
    # Проверяем, запущен ли поток парсера в данный момент
    if hasattr(obj, "parser_thread") and obj.parser_thread.isRunning():
        logger.info("Запрос на отмену сканирования отправлен пользователем...")

        # Выводим красивый статус пользователю в текстовую панель
        if hasattr(obj, "result_display"):
            obj.result_display.append("🛑 Останавливаем парсинг, пожалуйста, подождите...")

        # Делаем кнопку отмены временно неактивной, чтобы избежать спам-кликов
        if hasattr(obj, "btn_cancel_parsing"):
            obj.btn_cancel_parsing.setEnabled(False)

        # Поднимаем потокобезопасный флаг остановки внутри воркера.
        if hasattr(obj, "parser_worker"):
            obj.parser_worker.stop()
    else:
        logger.warning("Невозможно отменить парсинг: процесс не запущен или уже завершен.")
