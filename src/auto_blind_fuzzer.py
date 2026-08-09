"""
Модуль универсального асинхронного экспресс-сканирования API.
Автоматически адаптируется под структуру сайта и выводит HTTP-коды безопасности.
"""

import asyncio
import json
import os
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import httpx

# Ограничение на количество одновременных сетевых соединений (защита от бана VPS)
MAX_CONCURRENT_REQUESTS = 60
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

def extract_api_hints(html_text):
    """Ищет скрытые текстовые зацепки и пути в HTML-разметке сайта."""
    hints = set()
    raw_paths = re.findall(r'(?:href|src|data-url|action)=["\']([^"\']+)["\']', html_text)
    for path in raw_paths:
        if any(marker in path for marker in ["/api/", "/v1/", "/v2/", "/auth/", "/login", "/admin", "/users"]):
            # Забираем только чистую строку пути до знака вопроса
            hints.add(path.split('?')[0])
    return hints

def is_static_file(path: str) -> bool:
    """Проверяет, является ли путь медиа-файлом или стилем."""
    ignored_extensions = ('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2')
    return path.lower().endswith(ignored_extensions) or '/static/' in path.lower()

def generate_universal_express_wordlist(detected_apps=None) -> list:
    """Генератор универсальной матрицы путей на основе TOP мировых стандартов."""
    prefixes = ["api", "api/v1", "api/v2", "v1", "v2", "auth", "core", "rest", "services"]

    if detected_apps:
        for app in detected_apps:
            prefixes.append(app)
            prefixes.append(f"{app}/api/v1")
            prefixes.append(f"{app}/api/v1/auth")

    entities = [
        "user", "users", "me", "profile", "account", "accounts", "token", "tokens", "session",
        "task", "tasks", "todo", "todos", "list", "lists", "item", "items", "project", "projects",
        "bookmark", "bookmarks", "note", "notes", "post", "posts", "comment", "comments", "tag", "tags",
        "setting", "settings", "config", "status", "health", "info", "file", "upload", "media", "data"
    ]

    actions = [
        "login", "logout", "register", "signup", "signin", "signout",
        "refresh", "token/refresh", "verify", "email-verify",
        "password-reset", "password-reset/confirm", "reset", "confirm",
        "create", "delete", "update", "all", "view", "list"
    ]

    routes = [
        "/admin/", "/login/", "/register/", "/openapi.json", "/swagger.json", "/api/schema/", "/api/docs/"
    ]

    for pref in prefixes:
        routes.append(f"/{pref}/")
        for action in actions:
            routes.append(f"/{pref}/{action}/")
        for entity in entities:
            routes.append(f"/{pref}/{entity}/")
            if entity in ["user", "users", "token", "auth", "account", "task", "tasks"]:
                for action in ["login", "logout", "register", "refresh", "confirm", "me", "email-verify", "list"]:
                    routes.append(f"/{pref}/{entity}/{action}/")

    return list(set(routes))


async def test_single_path(client, target_url, path_clean, valid_endpoints):
    """Асинхронная корутина проверки эндпоинта методом HEAD/GET с фиксацией HTTP-кода."""
    if path_clean.startswith("/admin/") and path_clean != "/admin/":
        return

    full_test_url = urljoin(target_url, path_clean)

    async with semaphore:
        try:
            # Отправляем легкий асинхронный HEAD-запрос
            res = await client.head(full_test_url, timeout=2.0)
            status_code = res.status_code

            if status_code != 404:
                if status_code == 200 and path_clean != "/admin/":
                    get_res = await client.get(full_test_url, timeout=2.0)
                    if "django-admin" in get_res.text.lower():
                        return
                    status_code = get_res.status_code

                marker = "API" if any(x in path_clean for x in ["/api/", "/v1/", "/v2/", "schema", "docs", "swagger"]) else "WEB"

                # Сохраняем структуру данных в множество
                valid_endpoints.add((marker, path_clean, status_code))

        except httpx.HTTPError:
            pass


async def main_async_scan(target_url, output_json_path):
    """Главный управляющий асинхронный движок."""
    wordlist = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    valid_endpoints = set()

    async with httpx.AsyncClient(headers=headers, trust_env=False, follow_redirects=True) as client:
        try:
            response = await client.get(target_url, timeout=5.0)
        except Exception as e:
            print(f"[❌] Ошибка первичного подключения к серверу: {e}")
            return

        print("[🔎] Анализ структуры и извлечение явных путей...")
        soup = BeautifulSoup(response.text, "html.parser")
        for form in soup.find_all("form"):
            action = form.get("action")
            if action:
                wordlist.append(action)
        wordlist.extend(extract_api_hints(response.text))

        detected_apps = set()
        for path in wordlist:
            if path and path.startswith("/"):
                parts = path.split("/")[1] if len(path.split("/")) > 1 else ""
                if parts and parts not in ["admin", "api", "static"]:
                    detected_apps.add(parts)

        detected_apps.add("daily")

        if detected_apps:
            print(f"[🧠] Обнаружены уникальные модули системы: {list(detected_apps)}")

        print("[💀] Компиляция универсальной матрицы путей (Мировой стандарт + ИИ)...")
        wordlist.extend(generate_universal_express_wordlist(detected_apps=detected_apps))

        # Выравниваем слэши на этапе подготовки
        clean_paths = sorted(list(set([f"/{p.strip('/')}/" for p in wordlist if p and not is_static_file(p)])))
        total_paths = len(clean_paths)

        print(f"[🚀] Сгенерировано чистых уникальных комбинаций: {total_paths}")
        print("[⚡] Запуск параллельного экспресс-сканирования. Пожалуйста, подождите...")

        tasks = [
            test_single_path(client, target_url, path, valid_endpoints)
            for path in clean_paths
        ]
        await asyncio.gather(*tasks)

    # Превращаем в отсортированный список по типу и путям
    sorted_results = sorted(list(valid_endpoints), key=lambda x: (x[0], x[1]))

    # Формируем чистый JSON для PyQt6 QComboBox (как и раньше, с префиксами для удобства нарезки)
    json_endpoints = [f"[{item[0]}] {item[1]}" for item in sorted_results]

    try:
        os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as json_file:
            json.dump(json_endpoints, json_file, indent=4, ensure_ascii=False)
        print(f"[💾] Тотальная карта безопасности сохранена: {output_json_path}")
    except Exception as e:
        print(f"[❌] Ошибка сохранения JSON: {e}")

    # Печать красивой итоговой таблицы безопасности С КОДАМИ ОТВЕТОВ!
    print(f"\n[🎉] Сканирование успешно завершено! Найдено целей: {len(sorted_results)}")
    print("=" * 90)
    print(f"{'№':<3} | {'ТИП':<5} | {'КОД':<5} | {'ПОЯСНЕНИЕ':<18} | {'ЭНДПОИНТ ДЛЯ ТЕСТИРОВАНИЯ БЕЗОПАСНОСТИ'}")
    print("-" * 90)
    for index, (marker, path, status) in enumerate(sorted_results, 1):
        # ИСПРАВЛЕНО: Указаны точные коды 401 и 403 для анализа уровня защиты
        if status in [401, 403]:
            note = "Защищен (Token Req)"
        elif status == 405:
            note = "Метод не разрешен"
        elif status == 200:
            note = "Открыт (200 OK)"
        else:
            note = f"Статус {status}"

        print(f"{index:<3} | {marker:<5} | {status:<5} | {note:<18} | {path}")
    print("=" * 90)


def run_security_api_scan(target_url, output_json_path=None):
    """Синхронный инициализатор асинхронного ядра."""
    if output_json_path is None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        output_json_path = os.path.join(current_dir, "endpoints_config.json")

    print(f"[🔄] Инициализация УНИВЕРСАЛЬНОГО ЭКСПРЕСС-ФАЗЗЕРА...")
    asyncio.run(main_async_scan(target_url, output_json_path))


if __name__ == "__main__":
    URL_TO_SCAN = "http://127.0.0.1:8000"
    run_security_api_scan(URL_TO_SCAN)
