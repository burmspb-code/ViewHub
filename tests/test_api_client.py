import pytest
import requests
from src.auth.api_client import login_to_django

TEST_URL = "http://127.0.0"


# Описываем тест-кейсы для параметризации:
# (Название сценария, Настройка мока, Ожидаемый результат функции)
@pytest.mark.parametrize(
    "scenario_name, mock_setup, expected_result",
    [
        # 1. Happy Path: Успешный вход (токен Djoser)
        (
            "success_djoser",
            {"status_code": 200, "json": {"auth_token": "djoser_xyz123"}},
            {"success": True, "message": "Авторизация успешно пройдена.", "token": "djoser_xyz123"},
        ),
        # 2. Happy Path: Успешный вход (стандартный JWT access токен)
        (
            "success_jwt",
            {"status_code": 200, "json": {"access": "jwt_token_abc"}},
            {"success": True, "message": "Авторизация успешно пройдена.", "token": "jwt_token_abc"},
        ),
        # 3. Крайний случай: Статус 200, но сервер прислал не JSON (битый ответ)
        (
            "success_invalid_json",
            {"status_code": 200, "text": "not a json string"},
            {"success": True, "message": "Успешный вход, но ответ сервера не в JSON: ", "token": None},
        ),
        # 4. Ошибка клиента: Неверный логин/пароль (400 или 401)
        (
            "wrong_credentials",
            {"status_code": 401, "json": {"non_field_errors": ["Unable to log in"]}},
            {"success": False, "message": "Неверный логин или пароль.", "token": None},
        ),
        # 5. Ошибка сервера: 500 Internal Server Error
        (
            "server_error_500",
            {"status_code": 500, "text": "Database is down"},
            {"success": False, "message": "Сервер вернул ошибку: 500", "details": "Database is down", "token": None},
        ),
        # 6. Сетевая ошибка: Таймаут (сервер долго отвечает)
        (
            "network_timeout",
            {"exc": requests.exceptions.Timeout},
            {
                "success": False,
                "message": "Время ожидания запроса истекло.",
                "details": "Сервер слишком долго не отвечал (Таймаут).",
                "token": None,
            },
        ),
        # 7. Сетевая ошибка: Ошибка соединения (сервер выключен)
        (
            "connection_error",
            {"exc": requests.exceptions.ConnectionError},
            {
                "success": False,
                "message": "Ошибка соединения с сервером.",
                "details": "Проверьте URL/IP адрес и запущен ли Django на VPS.",
                "token": None,
            },
        ),
    ],
)
def test_login_to_django_scenarios(requests_mock, scenario_name, mock_setup, expected_result):
    """Параметризованный тест всех сценариев авторизации в Django."""

    # Конфигурируем перехватчик запросов requests_mock на основе настроек тест-кейса
    if "exc" in mock_setup:
        # Имитируем падение сети (исключение)
        requests_mock.post(TEST_URL, exc=mock_setup["exc"])
    else:
        # Имитируем обычный ответ сервера с нужным статус-кодом и телом
        requests_mock.post(
            TEST_URL, status_code=mock_setup["status_code"], json=mock_setup.get("json"), text=mock_setup.get("text")
        )

    # Вызываем тестируемую функцию
    result = login_to_django(TEST_URL, username="test_user", password="safe_password")

    # Проверяем возвращаемую структуру данных
    assert result["success"] == expected_result["success"]

    # Для случая с невалидным JSON проверяем только начало сообщения, так как там динамический текст ошибки Python
    if scenario_name == "success_invalid_json":
        assert result["message"].startswith(expected_result["message"])
    else:
        assert result["message"] == expected_result["message"]

    assert result["token"] == expected_result["token"]

    if "details" in expected_result:
        assert result["details"] == expected_result["details"]
