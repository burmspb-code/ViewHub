"""Вспомогательные функции для обновления UI."""

import logging

logger = logging.getLogger(__name__)


def _update_parsing_status(obj, message: str) -> None:
    """Пишет рабочие сообщения в информационное окно."""
    obj.result_display.append(message)


def _stop_handler(obj, msg: str) -> None:
    """Информирует о принудительной остановке процесса пользователем."""
    obj.result_display.append("🛑 Процесс остановлен!")
    obj.result_display.append(msg)

    # Разблокируем интерфейс обратно
    if getattr(obj, "btn_send_scanning", None):
        obj.btn_send_scanning.setEnabled(True)

    if getattr(obj, "btn_send_parsing", None):
        obj.btn_send_parsing.setEnabled(True)

    # Отключаем кнопку отмены парсинга
    if getattr(obj, "btn_cancel_parsing", None):
        obj.btn_cancel_parsing.setEnabled(False)

    if getattr(obj, "btn_cancel_scanning", None):
        obj.btn_cancel_scanning.setEnabled(True)


def _parsing_success_handler(obj, output_file: str = "") -> None:
    """Вызывается автоматически при успешном завершении парсинга."""
    # Разблокируем интерфейс обратно
    if getattr(obj, "btn_send_scanning", None):
        obj.btn_send_scanning.setEnabled(True)

    if getattr(obj, "btn_send_parsing", None):
        obj.btn_send_parsing.setEnabled(True)

    # Отключаем кнопку отмены
    if getattr(obj, "btn_cancel_parsing", None):
        obj.btn_cancel_parsing.setEnabled(False)

    if output_file:
        # Показываем сообщение об успешном завершении
        obj.result_display.append("🎉 Успех!")
        obj.result_display.append("📊 Парсинг сайта успешно завершен!")
        obj.result_display.append(f"Результат парсинга сохранен в файл: {output_file}\n\n")

    logger.info("Завершение работы парсера.")


def _scanning_success_handler(obj, obj_scan) -> None:
    """Вызывается автоматически при завершении сканирования."""
    # Сразу разблокируем интерфейс в любом случае (успех, отмена или ошибка)
    if getattr(obj, "btn_cancel_parsing", None):
        obj.btn_cancel_parsing.setEnabled(True)

    if getattr(obj, "btn_cancel_scanning", None):
        obj.btn_cancel_scanning.setEnabled(True)

    # Проверяем, получили ли мы валидный результат
    if obj_scan is None:
        obj.result_display.append("⚠️ Сканирование не выдало результатов (было прервано или произошло исключение).")
        logger.warning("Сканер завершил работу без данных (результат равен None).")
        return

    # Обрабатываем успешный результат (предполагаем, что obj_scan — это список или коллекция)
    obj.result_display.append("🔹 Успех")
    obj.result_display.append(f"🔹 Выявлено эндпоинтов: {len(obj_scan)}")
    obj.result_display.append("🎉 Сканирование сайта успешно завершено!")

    logger.info(f"Завершение работы сканера. Найдено эндпоинтов: {len(obj_scan)}")
