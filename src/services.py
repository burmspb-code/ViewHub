"""Модуль управления бизнес-логикой проекта."""

import logging

from PyQt6.QtWidgets import QApplication

from src.auth.api_client import login_to_django

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# ======================= Логика обработки пользовательских запросов ============================
def auth_on_click(obj):
    """
    Аутентификация через внешний API клиент.
    """
    url = obj.api_url_input.text().strip()
    username = obj.login_input.text().strip()
    password = obj.password_input.text()

    # Проверяем заполненность полей
    if not url or not username or not password:
        logger.warning("Заполните все поля для авторизации.")  # Само улетит и в файл, и в окно логов!
        return

    # Информируем пользователя о начале процесса
    pas_mask = "*" * len(password)
    logger.info(f"Отправка запроса на {url}...")  # Автоматически отобразится в логах как [🔄] или [INFO]

    # Окно «Данные/Результат» обновляем напрямую, так как это не лог, а отчет для пользователя
    obj.result_display.append(f"Запрос: POST {url}\nТело: username='{username}', password='{pas_mask}'")
    QApplication.processEvents()

    # Вызываем сетевую логику из нашего изолированного модуля
    result = login_to_django(url, username, password)

    # Обрабатываем стандартизированный ответ от модуля api_client
    if result["success"]:
        logger.info(f"УСПЕХ! {result['message']}")
        obj.result_display.append(f"Статус: Авторизован.\nТокен: {result['token']}")



        # Очищаем поля ввода
        obj.api_url_input.clear()
        obj.login_input.clear()
        obj.password_input.clear()
    else:
        logger.error(f"{result['message']}")
        if "details" in result:
            obj.result_display.append(f"Детали ошибки:\n{result['details']}")
        else:
            obj.result_display.append("Статус: Доступ отклонен.")


def requests_on_click(obj):
    """Отправка GET запроса."""
