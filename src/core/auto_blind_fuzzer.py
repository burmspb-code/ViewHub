"""
Модуль универсального асинхронного экспресс-сканирования API.
Автоматически адаптируется под структуру сайта и выводит HTTP-коды безопасности.
"""

import asyncio
import json
import logging
import os
import re

import httpx
from bs4 import BeautifulSoup

# Импортируем ядро Qt для управления событиями интерфейса
from PyQt6.QtCore import QCoreApplication

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
# Подавляем DEBUG-логи от системного асинхронного ядра Python и httpx
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Ограничение на количество одновременных сетевых соединений (защита от бана VPS)
MAX_CONCURRENT_REQUESTS = 5

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


def _get_base_system_routes() -> list:
    """Возвращает базовые системные пути."""
    return [
        "/admin/", "/login/", "/register/", "/catalog/", "/contacts/", "/openapi.json", "/swagger.json"
    ]


def _get_web_actions() -> list:
    """Возвращает список действий для веб-интерфейса."""
    return [
        "register", "email-confirmation-sent", "login", "logout",
        "password-reset", "password-reset/done", "password-reset/complete",
        "create-api", "update-api", "delete-api", "add", "create", "edit", "update", "delete",
        "bookmark/add", "bookmark/update-api", "task/create-api", "task/update-api", "task/delete-api"
    ]


def _get_api_auth_endpoints() -> list:
    """Возвращает список эндпоинтов для REST API/JWT."""
    return [
        "auth/login", "auth/token/refresh", "auth/logout",
        "register", "email-verify", "me", "list", "all", "view",
        "password-reset", "password-reset/confirm"
    ]


def _get_rest_entities() -> list:
    """Возвращает список сущностей для REST-путей."""
    return [
        "user", "users", "me", "profile", "account", "token", "session",
        "task", "tasks", "bookmark", "bookmarks", "catalog", "product", "products",
        "category", "categories", "cart", "order", "orders", "item", "items", "post", "posts"
    ]


def _generate_web_routes_for_app(app: str, web_actions: list) -> list:
    """Генерирует плоские веб-маршруты для приложения."""
    routes = []
    for action in web_actions:
        routes.append(f"/{app}/{action}")
        routes.append(f"/{app}/{action}/")
    return routes


def _generate_api_auth_routes_for_app(app: str, api_auth_endpoints: list) -> list:
    """Генерирует REST API маршруты аутентификации для приложения."""
    routes = []
    for endpoint in api_auth_endpoints:
        routes.append(f"/{app}/api/v1/{endpoint}")
        routes.append(f"/{app}/api/v1/{endpoint}/")
    return routes


def _generate_nested_rest_routes_for_app(app: str, entities: list) -> list:
    """Генерирует вложенные REST маршруты для приложения."""
    routes = []
    entity_actions = ["list", "view", "create", "update", "delete", "all"]

    for entity in entities:
        for action in entity_actions:
            routes.append(f"/{app}/{entity}/api/v1/{action}")
            routes.append(f"/{app}/{entity}/api/v1/{action}/")
        routes.append(f"/{app}/api/v1/auth/{entity}")
        routes.append(f"/{app}/api/v1/auth/{entity}/")

    return routes


def generate_universal_express_wordlist(detected_apps=None) -> list:
    """Ультимативный и полностью универсальный генератор путей под любой сайт в интернете."""
    routes = _get_base_system_routes()

    if detected_apps:
        web_actions = _get_web_actions()
        api_auth_endpoints = _get_api_auth_endpoints()
        entities = _get_rest_entities()

        for app in detected_apps:
            routes.extend(_generate_web_routes_for_app(app, web_actions))
            routes.extend(_generate_api_auth_routes_for_app(app, api_auth_endpoints))
            routes.extend(_generate_nested_rest_routes_for_app(app, entities))

    return list(set(routes))


def _is_invalid_admin_path(path_lower: str) -> bool:
    """Проверяет, является ли путь глубоким вложенным путем админки."""
    return path_lower.startswith("admin") and path_lower != "admin"


def _is_custom_404_page(html_content: str) -> bool:
    """Определяет кастомную 404 страницу по тегу <title>."""
    html_lower = html_content.lower()
    if "<title>" not in html_lower or "</title>" not in html_lower:
        return False

    try:
        title = html_lower.split("<title>")[1].split("</title>")[0]
        return any(msg in title for msg in ["страница не найдена", "page not found", "404"])
    except IndexError:
        return False


def _get_endpoint_marker(path_lower: str) -> str:
    """Определяет маркер эндпоинта (API или WEB)."""
    api_markers = ["api", "schema", "docs", "swagger"]
    return "API" if any(m in path_lower for m in api_markers) else "WEB"


async def test_single_path(
        client: httpx.AsyncClient,
        target_url: str,
        path_clean: str,
        valid_endpoints: set,
        semaphore: asyncio.Semaphore
):
    """Асинхронная корутина проверки эндпоинта методами GET и POST."""
    path_lower = path_clean.lower().strip('/')

    if _is_invalid_admin_path(path_lower):
        return

    full_test_url = f"{target_url.rstrip('/')}/{path_lower}"

    async with semaphore:
        try:
            # 1. Проверка методом GET
            res = await client.get(full_test_url, timeout=4.0)
            status_code = res.status_code

            if status_code == 200 and _is_custom_404_page(res.text):
                status_code = 404

            # 2. Проверка методом POST (если GET вернул 404 на API-подобном пути)
            is_api_route = any(m in path_lower for m in ["api", "v1", "v2"])
            if status_code == 404 and is_api_route:
                try:
                    post_res = await client.post(full_test_url, timeout=3.0)
                    if post_res.status_code != 404:
                        status_code = post_res.status_code
                except (httpx.HTTPError, asyncio.TimeoutError):
                    pass  # Игнорируем ошибки POST, оставляя статус 404 от GET

            # 3. Регистрация живого эндпоинта
            if status_code != 404:
                marker = _get_endpoint_marker(path_lower)
                valid_endpoints.add((marker, f"/{path_lower}", status_code))

        except (httpx.HTTPError, asyncio.TimeoutError):
            pass

def print_progress_bar(current, total, bar_length=30):
    """Рисует динамическую полосу прогресса в консоли."""
    fraction = current / total
    arrow = int(fraction * bar_length - 1) * "▓" + "▓"
    padding = int(bar_length - len(arrow)) * "░"
    percent = int(fraction * 100)

    # \r возвращает курсор в начало строки, а end="" не дает перенестись на новую строку
    print(f"\r[📡] Прогресс сканирования: [{arrow}{padding}] {percent}% ({current}/{total})", end="", flush=True)


def _extract_paths_from_html(soup: BeautifulSoup, response_text: str) -> tuple[list, set]:
    """Извлекает пути из HTML: формы, ссылки и API-хинты."""
    wordlist = []
    raw_discovered_paths = set()

    for form in soup.find_all("form"):
        action = form.get("action")
        if action:
            action_str = str(action)
            wordlist.append(action_str)
            raw_discovered_paths.add(action_str)

    hints = extract_api_hints(response_text)
    wordlist.extend(hints)
    raw_discovered_paths.update(hints)

    for a in soup.find_all("a", href=True):
        href = str(a["href"]).split('?')[0]
        if href.startswith("/"):
            wordlist.append(href)
            raw_discovered_paths.add(href)

    return wordlist, raw_discovered_paths


def _extract_api_markers_from_paths(raw_paths: set) -> set:
    """Извлекает API-маркеры из списка путей с помощью regex."""
    discovered_api_markers = set()
    for path in raw_paths:
        api_matches = re.findall(r'(api|v\d+)', path.lower())
        if api_matches:
                discovered_api_markers.update(api_matches)
    return discovered_api_markers


async def _perform_black_box_api_probing(client: httpx.AsyncClient, target_url: str, obj) -> set:
    """Выполняет Black-Box зондирование для обнаружения скрытых API-маркеров."""
    if hasattr(obj, 'result_display') and obj.result_display:
        obj.result_display.append(
            "[🔎] Маркеры не найдены в HTML. Запуск Black-Box зондирования корня API...")

    test_api_paths = ["/api/", "/api/v1/"]
    discovered_api_markers = set()

    for api_path in test_api_paths:
        try:
            api_check_res = await client.get(f"{target_url.rstrip('/')}{api_path}", timeout=3.0)
            if api_check_res.status_code != 404:
                discovered_api_markers.add("api")
                discovered_api_markers.add("v1")
                if hasattr(obj, 'result_display') and obj.result_display:
                    obj.result_display.append("[🧠] Динамическое зондирование подтвердило скрытую REST-структуру!")
                break
        except httpx.HTTPError:
            pass

    if not discovered_api_markers and hasattr(obj, 'result_display') and obj.result_display:
        obj.result_display.append(
            "[ℹ️] Зондирование завершено: Скрытая REST-архитектура отсутствует. Переход в WEB-режим.")

    return discovered_api_markers


def _add_default_api_markers(markers: set) -> set:
    """Добавляет стандартные API-маркеры если они еще не добавлены."""
    markers.add("api")
    markers.add("v1")
    return markers


async def _discover_api_markers(client: httpx.AsyncClient, target_url: str,
                                  raw_paths: set, obj) -> set:
    """Обнаруживает API-маркеры через HTML анализ и Black-Box зондирование."""
    discovered_api_markers = _extract_api_markers_from_paths(raw_paths)

    if not discovered_api_markers:
        discovered_api_markers = await _perform_black_box_api_probing(client, target_url, obj)
    else:
        discovered_api_markers = _add_default_api_markers(discovered_api_markers)

    return discovered_api_markers


def _detect_applications(wordlist: list) -> set:
    """Обнаруживает уникальные модули/приложения из списка путей."""
    detected_apps = set()
    system_prefixes = ["admin", "api", "static", "product", "category", "contacts", "blog"]

    for path in wordlist:
        if path and path.startswith("/"):
            parts = path.split("/")[1] if len(path.split("/")) > 1 else ""
            if parts and parts not in system_prefixes:
                detected_apps.add(parts)

    common_web_apps = ["library", "mailings", "mailing", "blog", "shop", "orders", "cart", "profile", "dashboard"]
    detected_apps.update(common_web_apps)

    return detected_apps


def _generate_crud_wordlist(detected_apps: set) -> list:
    """Генерирует CRUD-пути для обнаруженных приложений."""
    wordlist = []
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

    if "blog" in detected_apps:
        wordlist.extend(["/blog/post/create", "/blog/post/create/"])
    if "product" in detected_apps or "catalog" in detected_apps:
        wordlist.extend(["/catalog/list", "/catalog/list/"])

    return wordlist


def _generate_dynamic_id_wordlist(detected_apps: set) -> list:
    """Генерирует пути с ID для тестирования редактирования/удаления."""
    wordlist = []
    dynamic_actions = ["edit", "update", "delete", "delete-image"]
    test_slugs = ["1", "2", "test", "item", "product"]
    sub_entities = ["post", "item", "api", "v1"]

    for app in detected_apps:
        for action in dynamic_actions:
            for slug in test_slugs:
                wordlist.append(f"/{app}/{slug}/{action}")
                for sub_entity in sub_entities:
                    wordlist.append(f"/{app}/{sub_entity}/{slug}/{action}")

    return wordlist


def _build_marker_combos(discovered_api_markers: set) -> list:
    """Строит комбинации API-маркеров для версионирования."""
    marker_combos = list(discovered_api_markers)
    if "api" in discovered_api_markers and len(discovered_api_markers) > 1:
        for m in discovered_api_markers:
            if m != "api":
                marker_combos.append(f"api/{m}")
    return marker_combos


def _generate_action_paths(app: str, entity: str, marker: str, actions: list) -> list:
    """Генерирует пути с действиями для заданного приложения и сущности."""
    paths = []
    for action in actions:
        paths.append(f"/{app}/{entity}/{marker}/{action}")
        paths.append(f"/{app}/{marker}/{entity}/{action}")
    return paths


def _generate_id_paths(app: str, marker: str, entity: str, rest_ids: list) -> list:
    """Генерирует пути с ID для REST API."""
    paths = []
    for r_id in rest_ids:
        paths.append(f"/{app}/{marker}/{entity}/{r_id}")
        paths.append(f"/{marker}/{entity}/{r_id}")
    return paths


def _generate_rest_api_wordlist(detected_apps: set, discovered_api_markers: set) -> list:
    """Генерирует REST API пути с маркерами версионирования."""
    wordlist = []
    entities = ["task", "tasks", "user", "users", "bookmark", "bookmarks"]
    actions = ["list", "view", "create", "update", "delete", "create-api", "update-api"]
    rest_ids = ["1"]

    marker_combos = _build_marker_combos(discovered_api_markers)

    for app in detected_apps:
        for entity in entities:
            for marker in marker_combos:
                wordlist.extend(_generate_action_paths(app, entity, marker, actions))
                wordlist.extend(_generate_id_paths(app, marker, entity, rest_ids))

    return wordlist


def _clean_and_normalize_paths(wordlist: list) -> list:
    """Очищает и нормализует пути (убирает дубликаты, статические файлы)."""
    raw_clean = set()
    for p in wordlist:
        if p and not is_static_file(p):
            stripped = p.strip('/')
            raw_clean.add(f"/{stripped}/" if stripped else "/")

    clean_paths = sorted(raw_clean)
    clean_paths = [p if p != "//" else "/" for p in clean_paths]
    return clean_paths


async def _run_parallel_scan(client: httpx.AsyncClient, target_url: str,
                            clean_paths: list, obj) -> set:
    """Запускает параллельное сканирование путей с индикатором прогресса."""
    valid_endpoints = set()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    tasks = [
        asyncio.create_task(test_single_path(client, target_url, path, valid_endpoints, semaphore))
        for path in clean_paths
    ]

    completed_count = 0
    total_tasks = len(tasks)

    def get_ui_progress_text(current, total, bar_length=20):
        fraction = current / total
        arrow = int(fraction * bar_length - 1) * "▓" + "▓" if current > 0 else ""
        padding = int(bar_length - len(arrow)) * "░"
        percent = int(fraction * 100)
        return f"[📡] Прогресс сканирования: [{arrow}{padding}] {percent}% ({current}/{total})"

    if hasattr(obj, 'result_display') and obj.result_display:
        obj.result_display.append(get_ui_progress_text(completed_count, total_tasks))

    for future in asyncio.as_completed(tasks):
        await future
        completed_count += 1

        if completed_count % 10 == 0 or completed_count == total_tasks:
            if hasattr(obj, 'result_display') and obj.result_display:
                cursor = obj.result_display.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)
                cursor.select(cursor.SelectionType.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.insertText(get_ui_progress_text(completed_count, total_tasks))
                QCoreApplication.processEvents()

    return valid_endpoints


def _save_and_display_results(valid_endpoints: set, output_json_path: str, obj):
    """Сохраняет результаты в JSON и выводит таблицу в UI."""
    sanitized_results = [(marker, path, status) for marker, path, status in valid_endpoints]
    sorted_results = sorted(set(sanitized_results), key=lambda x: (x[0], x[1]))

    json_endpoints = [f"[{marker}] {path} (Код: {status})" for marker, path, status in sorted_results]

    try:
        os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as json_file:
            json.dump(json_endpoints, json_file, indent=4, ensure_ascii=False)
        obj.result_display.append(f"[💾] Тотальная карта безопасности сохранена: {output_json_path}")
    except (TypeError, ValueError):
        logger.exception("[❌] Ошибка сохранения JSON:")

    msg_finished = f"[📊] Сетевой движок завершил работу. Сырое множество содержит: {len(valid_endpoints)} элементов."
    msg_success = f"\n[🎉] Сканирование успешно завершено! В таблице отображено целей: {len(sorted_results)}"
    line_equal = "=" * 75
    line_dash = "-" * 75
    header_text = f"{'№':<3} | {'ТИП':<5} | {'КОД':<5} | {'ПОЯСНЕНИЕ':<18} | {'ЭНДПОИНТ ДЛЯ ТЕСТИРОВАНИЯ БЕЗОПАСНОСТИ'}"

    if hasattr(obj, 'result_display') and obj.result_display:
        obj.result_display.append("")
        obj.result_display.append(msg_finished)
        obj.result_display.append(msg_success)
        obj.result_display.append(line_equal)
        obj.result_display.append(header_text)
        obj.result_display.append(line_dash)

        for index, (marker, path, status) in enumerate(sorted_results, 1):
            if status in [401, 403]:
                note = "Защищен (Token Req)"
            elif status == 405:
                note = "Метод не разрешен"
            elif status == 200:
                note = "Открыт (200 OK)"
            else:
                note = f"Статус {status}"

            row_text = f"{index:<3} | {marker:<5} | {status:<5} | {note:<18} | {path}"
            obj.result_display.append(row_text)

        obj.result_display.append(line_equal)


async def main_async_scan(obj, target_url, output_json_path):
    """Главный управляющий асинхронный движок."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    async with httpx.AsyncClient(headers=headers, trust_env=False, follow_redirects=True) as client:
        try:
            response = await client.get(target_url, timeout=5.0)

        except httpx.TimeoutException:
            # Отдельно выделяем таймаут, так как при сканировании это частая ситуация
            logger.warning("[❌] Превышено время ожидания (Timeout) при первичном подключении")
            return

        except (httpx.RequestError, asyncio.TimeoutError) as e:
            # Ловим все остальные проблемы с сетью/DNS/SSL и стандартные таймауты asyncio
            logger.exception("[❌] Ошибка первичного подключения к серверу: %s", e)
            return

        obj.result_display.append("[🔎] Анализ структуры и извлечение явных путей...")
        soup = BeautifulSoup(response.text, "html.parser")

        wordlist, raw_discovered_paths = _extract_paths_from_html(soup, response.text)
        discovered_api_markers = await _discover_api_markers(client, target_url, raw_discovered_paths, obj)
        detected_apps = _detect_applications(wordlist)

        if hasattr(obj, 'result_display') and obj.result_display:
            if discovered_api_markers:
                obj.result_display.append(f"[🧠] Активные API-маркеры матрицы: {list(discovered_api_markers)}")
            if detected_apps:
                obj.result_display.append(f"[🧠] Обнаружены уникальные модули системы: {list(detected_apps)}")

            wordlist.extend(_generate_crud_wordlist(detected_apps))

        obj.result_display.append("[💀] Компиляция универсальной матрицы путей (Мировой стандарт + ИИ)...")
        wordlist.extend(generate_universal_express_wordlist(detected_apps=detected_apps))
        wordlist.extend(_generate_dynamic_id_wordlist(detected_apps))
        wordlist.extend(_generate_rest_api_wordlist(detected_apps, discovered_api_markers))

        clean_paths = _clean_and_normalize_paths(wordlist)
        total_paths = len(clean_paths)

        obj.result_display.append(f"[🚀] Сгенерировано чистых уникальных комбинаций: {total_paths}")
        obj.result_display.append("[⚡] Запуск параллельного экспресс-сканирования. Пожалуйста, подождите...")

        valid_endpoints = await _run_parallel_scan(client, target_url, clean_paths, obj)
        _save_and_display_results(valid_endpoints, output_json_path, obj)

def run_security_api_scan(obj, output_json_path=None):
    """Синхронный инициализатор асинхронного ядра."""
    if output_json_path is None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        output_json_path = os.path.join(current_dir, "endpoints_config.json")

    obj.result_display.append("[🔄] Инициализация УНИВЕРСАЛЬНОГО ЭКСПРЕСС-ФАЗЗЕРА...")

    target_url = obj.base_url_input.text() # Базовый путь для сканирования

    asyncio.run(main_async_scan(obj, target_url, output_json_path))


if __name__ == "__main__":
    class MockObj:
        def __init__(self):
            self.base_url_input = MockInput()
            self.result_display = MockDisplay()

    class MockInput:
        def text(self):
            return "http://127.0.0.1:8000"

    class MockDisplay:
        def __init__(self):
            self.messages = []
        def append(self, text):
            self.messages.append(text)
            print(text)

    mock_obj = MockObj()
    run_security_api_scan(mock_obj)
