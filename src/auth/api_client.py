"""
Модуль для работы с сетевыми запросами к Django API.
"""

import requests


def login_to_django(url: str, username: str, password: str) -> dict:
    """
    Отправляет POST-запрос на Django API для авторизации пользователя.

    Args:
        url (str): Полный URL эндпоинта авторизации.
        username (str): Логин пользователя.
        password (str): Пароль пользователя.

    Returns:
        dict: Словарь с результатами запроса.
            Структура: {
                "success": bool,
                "message": str,
                "token": str или None,
                "details": str (опционально для ошибок)
            }
    """
    payload = {
        "username": username,
        "password": password
    }

    try:
        response = requests.post(url, json=payload, timeout=7)

        if response.status_code == 200:
            try:
                data = response.json()
                # Пытаемся вытащить токен (поддерживаем Djoser и стандартный JWT)
                token = data.get("auth_token") or data.get("access") or "Токен получен"
                return {
                    "success": True,
                    "message": "Авторизация успешно пройдена.",
                    "token": token
                }
            except Exception:
                return {
                    "success": True,
                    "message": "Успешный вход, но ответ сервера не в JSON.",
                    "token": None
                }

        elif response.status_code in (400, 401):
            return {
                "success": False,
                "message": "Неверный логин или пароль.",
                "token": None
            }
        else:
            return {
                "success": False,
                "message": f"Сервер вернул ошибку: {response.status_code}",
                "details": response.text,
                "token": None
            }

    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "message": "Ошибка соединения с сервером.",
            "details": "Проверьте URL/IP адрес и запущен ли Django на VPS.",
            "token": None
        }
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "message": "Время ожидания запроса истекло.",
            "details": "Сервер слишком долго не отвечал (Таймаут).",
            "token": None
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Произошла неизвестная ошибка.",
            "details": str(e),
            "token": None
        }
