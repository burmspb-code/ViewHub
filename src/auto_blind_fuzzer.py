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
MAX_CONCURRENT_REQUESTS = 5
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
    """Ультимативный и полностью универсальный генератор путей под любой сайт в интернете."""

    # 1. Действия и суффиксы для веб-интерфейса (HTML-страницы и формы)
    web_actions = [
        "register", "email-confirmation-sent", "login", "logout",
        "password-reset", "password-reset/done", "password-reset/complete",
        "create-api", "update-api", "delete-api", "add", "create", "edit", "update", "delete",
        "bookmark/add", "bookmark/update-api", "task/create-api", "task/update-api", "task/delete-api"
    ]

    # 2. Суффиксы для глубокого пробива REST API / JWT
    api_auth_endpoints = [
        "auth/login", "auth/token/refresh", "auth/logout",
        "register", "email-verify", "me", "list", "all", "view",
        "password-reset", "password-reset/confirm"
    ]

    # 3. Список сущностей для построения вложенных REST-путей (Мировой стандарт)
    entities = [
        "user", "users", "me", "profile", "account", "token", "session",
        "task", "tasks", "bookmark", "bookmarks", "catalog", "product", "products",
        "category", "categories", "cart", "order", "orders", "item", "items", "post", "posts"
    ]

    # Гарантированные базовые системные пути
    routes = [
        "/admin/", "/login/", "/register/", "/catalog/", "/contacts/", "/openapi.json", "/swagger.json"
    ]

    # Если наш "паук" успешно нашел хоть какие-то модули на чужом сайте
    if detected_apps:
        for app in detected_apps:
            # А. Генерируем плоские веб-маршруты (например: /cars/login/, /cars/register/)
            for action in web_actions:
                routes.append(f"/{app}/{action}")
                routes.append(f"/{app}/{action}/")

            # Б. Генерируем глубокие REST API маршруты под ЛЮБОЕ обнаруженное приложение
            # При подстановке 'users' соберет: /users/api/v1/auth/login/
            # При подстановке 'cars' соберет: /cars/api/v1/me/
            for endpoint in api_auth_endpoints:
                routes.append(f"/{app}/api/v1/{endpoint}")
                routes.append(f"/{app}/api/v1/{endpoint}/")

            # В. Генерируем глубокий вложенный и перевернутый роутинг (например: /daily/task/api/v1/list/)
            for entity in entities:
                # Шаблон: /имя_приложения/сущность/api/v1/действие/
                for action in ["list", "view", "create", "update", "delete", "all"]:
                    routes.append(f"/{app}/{entity}/api/v1/{action}")
                    routes.append(f"/{app}/{entity}/api/v1/{action}/")

                # Шаблон: /имя_приложения/api/v1/auth/сущность/
                routes.append(f"/{app}/api/v1/auth/{entity}")
                routes.append(f"/{app}/api/v1/auth/{entity}/")

    return list(set(routes))


async def test_single_path(client, target_url, path_clean, valid_endpoints):
    """Асинхронная корутина проверки эндпоинта методами GET и POST для пробива API."""
    if path_clean.startswith("/admin/") and path_clean != "/admin/":
        return

    # Жесткая и надежная склейка хоста и пути
    base_host = target_url.rstrip('/')
    pure_path = f"/{path_clean.lstrip('/')}"
    full_test_url = f"{base_host}{pure_path}"

    async with semaphore:
        try:
            # 1. Первая попытка: стандартный GET-запрос
            res = await client.get(full_test_url, timeout=4.0)
            status_code = res.status_code

            # Фильтр кастомных 404 страниц в <title>
            if status_code == 200:
                page_title = ""
                if "<title>" in res.text.lower() and "</title>" in res.text.lower():
                    try:
                        page_title = res.text.lower().split("<title>")[1].split("</title>")[0]
                    except: pass
                if any(msg in page_title for msg in ["страница не найдена", "page not found", "404"]):
                    status_code = 404

            # 2. ТВОЙ ПРОБИВ: Если GET выдал 404, но путь явно похож на API, пробуем бахнуть POST-запросом!
            if status_code == 404 and any(api_marker in path_clean.lower() for api_marker in ["/api/", "/v1/", "/v2/"]):
                try:
                    post_res = await client.post(full_test_url, timeout=3.0)
                    # Если POST вернул любой код кроме 404 (например, 400, 401, 403, 405) — эндпоинт ЖИВОЙ!
                    if post_res.status_code != 404:
                        status_code = post_res.status_code
                except:
                    pass

            # Если точка ответила хоть чем-то, кроме 404 — заносим в отчет
            if status_code != 404:
                marker = "API" if any(x in path_clean for x in ["/api/", "schema", "docs", "swagger"]) else "WEB"
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

        # Сюда собираем сырые пути для поиска скрытых API-маркеров
        raw_discovered_paths = set()

        for form in soup.find_all("form"):
            action = form.get("action")
            if action:
                wordlist.append(action)
                raw_discovered_paths.add(action)

        # Вытаскиваем хинты
        hints = extract_api_hints(response.text)
        wordlist.extend(hints)
        raw_discovered_paths.update(hints)

        # ДОБАВЛЕНО: Собираем обычные ссылки, чтобы расширить базу поиска маркеров API
        for a in soup.find_all("a", href=True):
            href = a["href"].split('?')[0]
            if href.startswith("/"):
                wordlist.append(href)
                raw_discovered_paths.add(href)

        # ТВОЯ СТРАТЕГИЯ: Динамический поиск маркеров API (api, v1, v2...) отдельно
        discovered_api_markers = set()
        for path in raw_discovered_paths:
            api_matches = re.findall(r'(api|v[0-9]+)', path.lower())
            if api_matches:
                for match in api_matches:
                    discovered_api_markers.add(match)

        detected_apps = set()
        for path in wordlist:
            if path and path.startswith("/"):
                parts = path.split("/")[1] if len(path.split("/")) > 1 else ""
                if parts and parts not in ["admin", "api", "static"]:
                    detected_apps.add(parts)


        if discovered_api_markers:
            print(f"[🧠] Зацепка! Найдены скрытые API-маркеры: {list(discovered_api_markers)}")
        if detected_apps:
            print(f"[🧠] Обнаружены уникальные модули системы: {list(detected_apps)}")

            # ПОЛНАЯ ПЛОСКАЯ CRUD-МАТРИЦА (Доработана под структуру blog/post и product)
            crud_actions = [
                "", "list", "all", "view", "detail", "catalog", "contacts",
                "add", "create", "new", "edit", "update", "delete", "remove"
            ]

            for app in detected_apps:
                for action in crud_actions:
                    if action == "":
                        wordlist.append(f"/{app}")
                    else:
                        wordlist.append(f"/{app}/{action}")

            # ДОБАВЛЕНО: Пробив вложенных сущностей, специфичных для блогов и магазинов
            if "blog" in detected_apps:
                wordlist.extend(["/blog/post/create", "/blog/post/create/"])
            if "product" in detected_apps or "catalog" in detected_apps:
                wordlist.extend(["/catalog/list", "/catalog/list/"])

        print("[💀] Компиляция универсальной матрицы путей (Мировой стандарт + ИИ)...")
        wordlist.extend(generate_universal_express_wordlist(detected_apps=detected_apps))

        # ДИНАМИЧЕСКИЙ ПРОБИВ ID И SLUG (Для вскрытия страниц редактирования/удаления)
        dynamic_actions = ["edit", "update", "delete", "delete-image"]
        test_slugs = ["1", "2", "test", "item", "product"]

        if detected_apps:
            for app in detected_apps:
                for action in dynamic_actions:
                    for slug in test_slugs:
                        # 1. Проверяем стандартный плоский роутинг: /имя_модуля/1/edit/
                        wordlist.append(f"/{app}/{slug}/{action}")

                        # 2. Проверяем вложенную структуру (на случай блогов и REST): /имя_модуля/post/1/edit/
                        for sub_entity in ["post", "item", "api", "v1"]:
                            wordlist.append(f"/{app}/{sub_entity}/{slug}/{action}")

        # ТВОЯ СТРАТЕГИЯ В ДЕЙСТВИИ: Если зацепки найдены, генерируем под них перевернутый API-роутинг
        if detected_apps and discovered_api_markers:
            entities = ["task", "user", "product", "order", "bookmark"]
            actions = ["list", "view", "create", "update", "delete", "create-api", "update-api"]

            # Собираем комбинации вроде 'api/v1'
            marker_combos = list(discovered_api_markers)
            if "api" in discovered_api_markers and len(discovered_api_markers) > 1:
                for m in discovered_api_markers:
                    if m != "api":
                        marker_combos.append(f"api/{m}")

            for app in detected_apps:
                for entity in entities:
                    for marker in marker_combos:
                        for action in actions:
                            # Шаблон: /daily/task/api/v1/list
                            wordlist.append(f"/{app}/{entity}/{marker}/{action}")
                            # Шаблон: /daily/api/v1/task/list
                            wordlist.append(f"/{app}/{marker}/{entity}/{action}")

        # Умное выравнивание: ставит слэш на конце, но защищает корень сайта '/' от превращения в '//'
        raw_clean = set()
        for p in wordlist:
            if p and not is_static_file(p):
                stripped = p.strip('/')
                # Если путь пустой (был корнем), оставляем "/", иначе делаем "/путь/"
                raw_clean.add(f"/{stripped}/" if stripped else "/")

        clean_paths = sorted(list(raw_clean))

        # Исправление аномалии корня (чтобы не было '//')
        clean_paths = [p if p != "//" else "/" for p in clean_paths]
        total_paths = len(clean_paths)

        print(f"[🚀] Сгенерировано чистых уникальных комбинаций: {total_paths}")
        print("[⚡] Запуск параллельного экспресс-сканирования. Пожалуйста, подождите...")

        tasks = [
            test_single_path(client, target_url, path, valid_endpoints)
            for path in clean_paths
        ]
        await asyncio.gather(*tasks)

        # ПОСТОЯННЫЙ ИНДИКАТОР: Показывает реальное количество найденных сетевых ответов
        print(f"[📊] Сетевой движок завершил работу. Сырое множество содержит: {len(valid_endpoints)} элементов.")

        # Безопасное извлечение 3-х базовых элементов (marker, path, status)
        sanitized_results = []
        for item in valid_endpoints:
            marker, path, status, *extra = item
            sanitized_results.append((marker, path, status))

        sorted_results = sorted(list(set(sanitized_results)), key=lambda x: (x, x))

        # Формируем чистый JSON для PyQt6 QComboBox
        json_endpoints = [f"[{item}] {item}" for item in sorted_results]

        try:
            os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
            with open(output_json_path, "w", encoding="utf-8") as json_file:
                json.dump(json_endpoints, json_file, indent=4, ensure_ascii=False)
            print(f"[💾] Тотальная карта безопасности сохранена: {output_json_path}")
        except Exception as e:
            print(f"[❌] Ошибка сохранения JSON: {e}")

        # Печать красивой итоговой таблицы безопасности С КОДАМИ ОТВЕТОВ!
        print(f"\n[🎉] Сканирование успешно завершено! В таблице отображено целей: {len(sorted_results)}")
        print("=" * 90)
        print(f"{'№':<3} | {'ТИП':<5} | {'КОД':<5} | {'ПОЯСНЕНИЕ':<18} | {'ЭНДПОИНТ ДЛЯ ТЕСТИРОВАНИЯ БЕЗОПАСНОСТИ'}")
        print("-" * 90)
        for index, (marker, path, status) in enumerate(sorted_results, 1):
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
