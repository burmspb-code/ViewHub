"""
Модуль универсального асинхронного экспресс-сканирования API.
Автоматически адаптируется под структуру сайта и выводит HTTP-коды безопасности.
"""

import asyncio
import json
import logging
import os
import re
from contextlib import suppress

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

# Маркер для идентификации API путей
API_PATH_MARKER = "/api/"

# Маркер для административного пути
ADMIN_PATH = "/admin/"

def extract_api_hints(html_text):
    """Ищет скрытые текстовые зацепки и пути в HTML-разметке сайта."""
    hints = set()
    raw_paths = re.findall(r'(?:href|src|data-url|action)=["\']([^"\']+)["\']', html_text)
    for path in raw_paths:
        if any(marker in path for marker in [API_PATH_MARKER, "/v1/", "/v2/", "/auth/", "/login", "/admin", "/users"]):
            # Забираем только чистую строку пути до знака вопроса
            hints.add(path.split('?')[0])
    return hints

def is_static_file(path: str) -> bool:
    """Проверяет, является ли путь медиа-файлом или стилем."""
    ignored_extensions = ('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2')
    return path.lower().endswith(ignored_extensions) or '/static/' in path.lower()


def _generate_web_routes(app, web_actions, routes):
    """Generate flat web routes for an app."""
    for action in web_actions:
        routes.append(f"/{app}/{action}")
        routes.append(f"/{app}/{action}/")


def _generate_api_auth_routes(app, api_auth_endpoints, routes):
    """Generate REST API auth routes for an app."""
    for endpoint in api_auth_endpoints:
        routes.append(f"/{app}/api/v1/{endpoint}")
        routes.append(f"/{app}/api/v1/{endpoint}/")


def _generate_nested_entity_routes(app, entities, routes):
    """Generate nested entity routes for an app."""
    for entity in entities:
        for action in ["list", "view", "create", "update", "delete", "all"]:
            routes.append(f"/{app}/{entity}/api/v1/{action}")
            routes.append(f"/{app}/{entity}/api/v1/{action}/")
        routes.append(f"/{app}/api/v1/auth/{entity}")
        routes.append(f"/{app}/api/v1/auth/{entity}/")


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
        ADMIN_PATH, "/login/", "/register/", "/catalog/", "/contacts/", "/openapi.json", "/swagger.json"
    ]

    if detected_apps:
        for app in detected_apps:
            _generate_web_routes(app, web_actions, routes)
            _generate_api_auth_routes(app, api_auth_endpoints, routes)
            _generate_nested_entity_routes(app, entities, routes)

    return list(set(routes))


def _check_custom_404_page(res):
    """Check if response is a custom 404 page based on title."""
    if "<title>" in res.text.lower() and "</title>" in res.text.lower():
        try:
            page_title = res.text.lower().split("<title>")[1].split("</title>")[0]
            if any(msg in page_title for msg in ["страница не найдена", "page not found", "404"]):
                return True
        except (IndexError, AttributeError):
            pass
    return False


def _is_api_path(path_clean):
    """Check if path looks like an API endpoint."""
    return any(marker in path_clean.lower() for marker in [API_PATH_MARKER, "/v1/", "/v2/"])


def _classify_endpoint(path_clean):
    """Classify endpoint as API or WEB."""
    return "API" if any(x in path_clean for x in [API_PATH_MARKER, "schema", "docs", "swagger"]) else "WEB"


async def test_single_path(client, target_url, path_clean, valid_endpoints, semaphore: asyncio.Semaphore):
    """Асинхронная корутина проверки эндпоинта методами GET и POST для пробива API."""
    if path_clean.startswith(ADMIN_PATH) and path_clean != ADMIN_PATH:
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
            if status_code == 200 and _check_custom_404_page(res):
                status_code = 404

            # 2. Если GET выдал 404, но путь явно похож на API, пробуем бахнуть POST-запросом!
            if status_code == 404 and _is_api_path(path_clean):
                # Указываем только сетевые исключения и таймауты
                with suppress(httpx.RequestError, asyncio.TimeoutError):
                    post_res = await client.post(full_test_url, timeout=3.0)
                    if post_res.status_code != 404:
                        status_code = post_res.status_code

            # Если точка ответила хоть чем-то, кроме 404 — заносим в отчет
            if status_code != 404:
                marker = _classify_endpoint(path_clean)
                valid_endpoints.add((marker, path_clean, status_code))

        except httpx.HTTPError:
            pass


def print_progress_bar(current, total, bar_length=30):
    """Рисует динамическую полосу прогресса в консоли."""
    fraction = current / total
    arrow = int(fraction * bar_length - 1) * "▓" + "▓"
    padding = int(bar_length - len(arrow)) * "░"
    percent = int(fraction * 100)

    # \r возвращает курсор в начало строки, а end="" не дает перенестись на новую строку
    print(f"\r[📡] Прогресс сканирования: [{arrow}{padding}] {percent}% ({current}/{total})", end="", flush=True)


def _append_to_display(obj, message):
    """Helper to safely append messages to result display."""
    if hasattr(obj, 'result_display') and obj.result_display:
        obj.result_display.append(message)


def _discover_api_markers(raw_discovered_paths):
    """Extract API markers from discovered paths."""
    discovered_api_markers = set()
    for path in raw_discovered_paths:
        api_matches = re.findall(r'(api|v\d+)', path.lower())
        if api_matches:
            discovered_api_markers.update(api_matches)
    return discovered_api_markers


async def _probe_api_structure(client, target_url, obj):
    """Probe server for hidden API structure via black-box testing."""
    _append_to_display(obj, "[🔎] Маркеры не найдены в HTML. Запуск Black-Box зондирования корня API...")

    test_api_paths = [API_PATH_MARKER, f"{API_PATH_MARKER}v1/"]
    api_detected_in_wild = False

    for api_path in test_api_paths:
        try:
            api_check_res = await client.get(f"{target_url.rstrip('/')}{api_path}", timeout=3.0)
            if api_check_res.status_code != 404:
                api_detected_in_wild = True
                break
        except Exception as e:
            logger.debug("[🔍] Пропущена ошибка при фаззинге пути: %s", e)

    if api_detected_in_wild:
        _append_to_display(obj, "[🧠] Динамическое зондирование подтвердило скрытую REST-структуру!")
        return {"api", "v1"}
    else:
        _append_to_display(
            obj,
            "[ℹ️] Зондирование завершено: Скрытая REST-архитектура отсутствует. Переход в WEB-режим."
        )
        return set()


def _generate_crud_matrix(detected_apps, wordlist):
    """Generate flat CRUD matrix for detected applications."""
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


def _add_flat_route(app, slug, action, wordlist):
    """Add standard flat routing path."""
    wordlist.append(f"/{app}/{slug}/{action}")


def _add_nested_routes(app, slug, action, wordlist):
    """Add nested structure routes for blogs and REST."""
    for sub_entity in ["post", "item", "api", "v1"]:
        wordlist.append(f"/{app}/{sub_entity}/{slug}/{action}")


def _generate_dynamic_id_routes(detected_apps, wordlist):
    """Generate dynamic ID and SLUG routes for edit/delete operations."""
    dynamic_actions = ["edit", "update", "delete", "delete-image"]
    test_slugs = ["1", "2", "test", "item", "product"]

    for app in detected_apps:
        for action in dynamic_actions:
            for slug in test_slugs:
                _add_flat_route(app, slug, action, wordlist)
                _add_nested_routes(app, slug, action, wordlist)


def _build_marker_combos(discovered_api_markers):
    """Build marker combinations from discovered API markers."""
    marker_combos = list(discovered_api_markers)
    if "api" in discovered_api_markers and len(discovered_api_markers) > 1:
        for m in discovered_api_markers:
            if m != "api":
                marker_combos.append(f"api/{m}")
    return marker_combos


def _generate_flat_action_routes(app, entity, marker, actions, wordlist):
    """Generate standard flat action routes for an app/entity/marker combo."""
    for action in actions:
        wordlist.append(f"/{app}/{entity}/{marker}/{action}")
        wordlist.append(f"/{app}/{marker}/{entity}/{action}")


def _generate_rest_id_routes(app, entity, marker, rest_ids, wordlist):
    """Generate REST ID routes for an app/entity/marker combo."""
    for r_id in rest_ids:
        wordlist.append(f"/{app}/{marker}/{entity}/{r_id}")
        wordlist.append(f"/{marker}/{entity}/{r_id}")


def _generate_api_routes(detected_apps, discovered_api_markers, wordlist):
    """Generate inverted API routing based on discovered markers."""
    entities = ["task", "tasks", "user", "users", "bookmark", "bookmarks"]
    actions = ["list", "view", "create", "update", "delete", "create-api", "update-api"]
    rest_ids = ["1"]

    marker_combos = _build_marker_combos(discovered_api_markers)

    for app in detected_apps:
        for entity in entities:
            for marker in marker_combos:
                _generate_flat_action_routes(app, entity, marker, actions, wordlist)
                _generate_rest_id_routes(app, entity, marker, rest_ids, wordlist)


def _collect_detected_apps(wordlist):
    """Extract unique application modules from wordlist."""
    detected_apps = set()
    for path in wordlist:
        if path and path.startswith("/"):
            parts = path.split("/")[1] if len(path.split("/")) > 1 else ""
            if parts and parts not in ["admin", "api", "static", "product", "category", "contacts", "blog"]:
                detected_apps.add(parts)

    common_web_apps = ["library", "mailings", "mailing", "blog", "shop", "orders", "cart", "profile", "dashboard"]
    detected_apps.update(common_web_apps)

    return detected_apps


def _extract_paths_from_html(response_text, wordlist, raw_discovered_paths):
    """Extract paths from HTML forms, hints, and links."""
    soup = BeautifulSoup(response_text, "html.parser")

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


async def _discover_api_markers_with_fallback(client, target_url, obj, raw_discovered_paths):
    """Discover API markers from HTML or via black-box probing."""
    discovered_api_markers = _discover_api_markers(raw_discovered_paths)

    if not discovered_api_markers:
        discovered_markers = await _probe_api_structure(client, target_url, obj)
        discovered_api_markers.update(discovered_markers)
    else:
        discovered_api_markers.add("api")
        discovered_api_markers.add("v1")

    return discovered_api_markers


def _clean_and_normalize_paths(wordlist):
    """Clean and normalize paths, removing static files and ensuring trailing slashes."""
    raw_clean = set()
    for p in wordlist:
        if p and not is_static_file(p):
            stripped = p.strip('/')
            raw_clean.add(f"/{stripped}/" if stripped else "/")

    clean_paths = sorted(raw_clean)
    clean_paths = [p if p != "//" else "/" for p in clean_paths]
    return clean_paths


def _update_progress_bar(obj, completed_count, total_tasks):
    """Update the progress bar in the UI."""
    if completed_count % 10 == 0 or completed_count == total_tasks:
        if hasattr(obj, 'result_display') and obj.result_display:
            cursor = obj.result_display.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.select(cursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()

            bar_length = 20
            fraction = completed_count / total_tasks
            arrow = int(fraction * bar_length - 1) * "▓" + "▓" if completed_count > 0 else ""
            padding = int(bar_length - len(arrow)) * "░"
            percent = int(fraction * 100)
            progress_text = (
                f"[📡] Прогресс сканирования: [{arrow}{padding}] {percent}% "
                f"({completed_count}/{total_tasks})"
            )

            cursor.insertText(progress_text)
            QCoreApplication.processEvents()


def _save_results_to_json(sorted_results, output_json_path, obj):
    """Save scan results to JSON file."""
    json_endpoints = []
    for marker, path, status in sorted_results:
        json_endpoints.append(f"[{marker}] {path} (Код: {status})")

    try:
        os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as json_file:
            json.dump(json_endpoints, json_file, indent=4, ensure_ascii=False)
        obj.result_display.append(f"[💾] Тотальная карта безопасности сохранена: {output_json_path}")
    except Exception as e:
        logger.exception("[❌] Ошибка сохранения JSON: %s", e)


def _get_status_note(status):
    """Get human-readable note for HTTP status code."""
    if status in [401, 403]:
        return "Защищен (Token Req)"
    elif status == 405:
        return "Метод не разрешен"
    elif status == 200:
        return "Открыт (200 OK)"
    else:
        return f"Статус {status}"


def _display_results_table(sorted_results, obj):
    """Display results as a formatted table in the UI."""
    msg_success = f"\n[🎉] Сканирование успешно завершено! В таблице отображено целей: {len(sorted_results)}"
    line_equal = "=" * 75
    line_dash = "-" * 75
    header_text = (f"{'№':<3} | {'ТИП':<5} | {'КОД':<5} | {'ПОЯСНЕНИЕ':<18} |"
                   f" {'ЭНДПОИНТ ДЛЯ ТЕСТИРОВАНИЯ БЕЗОПАСНОСТИ'}")

    if hasattr(obj, 'result_display') and obj.result_display:
        obj.result_display.append("")
        obj.result_display.append(msg_success)
        obj.result_display.append(line_equal)
        obj.result_display.append(header_text)
        obj.result_display.append(line_dash)

    for index, (marker, path, status) in enumerate(sorted_results, 1):
        note = _get_status_note(status)
        row_text = f"{index:<3} | {marker:<5} | {status:<5} | {note:<18} | {path}"

        if hasattr(obj, 'result_display') and obj.result_display:
            obj.result_display.append(row_text)

    if hasattr(obj, 'result_display') and obj.result_display:
        obj.result_display.append(line_equal)


async def main_async_scan(obj, target_url, output_json_path):
    """Главный управляющий асинхронный движок."""
    wordlist = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    valid_endpoints = set()

    async with httpx.AsyncClient(headers=headers, trust_env=False, follow_redirects=True) as client:
        try:
            response = await client.get(target_url, timeout=5.0)
        except Exception as e:
            logger.exception("[❌] Ошибка первичного подключения к серверу: %s", e)
            return

        _append_to_display(obj, "[🔎] Анализ структуры и извлечение явных путей...")
        raw_discovered_paths = set()
        _extract_paths_from_html(response.text, wordlist, raw_discovered_paths)
        discovered_api_markers = await _discover_api_markers_with_fallback(
            client, target_url, obj, raw_discovered_paths
        )

        # === СБОР УНИКАЛЬНЫХ МОДУЛЕЙ СИСТЕМЫ ===
        detected_apps = _collect_detected_apps(wordlist)

        # Вывод зацепок в графическое окно PyQt/PySide
        if hasattr(obj, 'result_display') and obj.result_display:
            if discovered_api_markers:
                obj.result_display.append(f"[🧠] Активные API-маркеры матрицы: {list(discovered_api_markers)}")
            if detected_apps:
                obj.result_display.append(f"[🧠] Обнаружены уникальные модули системы: {list(detected_apps)}")

            _generate_crud_matrix(detected_apps, wordlist)

        obj.result_display.append("[💀] Компиляция универсальной матрицы путей (Мировой стандарт + ИИ)...")
        wordlist.extend(generate_universal_express_wordlist(detected_apps=detected_apps))

        _generate_dynamic_id_routes(detected_apps, wordlist)

        # ТВОЯ СТРАТЕГИЯ В ДЕЙСТВИИ: Если зацепки найдены, генерируем под них перевернутый API-роутинг
        if detected_apps and discovered_api_markers:
            _generate_api_routes(detected_apps, discovered_api_markers, wordlist)

        clean_paths = _clean_and_normalize_paths(wordlist)
        total_paths = len(clean_paths)

        obj.result_display.append(f"[🚀] Сгенерировано чистых уникальных комбинаций: {total_paths}")
        obj.result_display.append("[⚡] Запуск параллельного экспресс-сканирования. Пожалуйста, подождите...")

        # === МОДЕРНИЗИРОВАННЫЙ СЕТЕВОЙ ДВИЖОК С АСИНХРОННЫМ ИНДИКАТОРОМ ===
        # ИСПРАВЛЕНО: Создаем семафор внутри текущего event loop, чтобы избежать RuntimeError
        # Вы можете изменить число 20 на нужный вам лимит параллельных запросов
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        # Передаем созданный semaphore аргументом в функцию-тестировщик
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
            _update_progress_bar(obj, completed_count, total_tasks)

        # === КОНЕЦ ЦИКЛА (Сканирование успешно завершено!) ===

        msg_finished = (f"[📊] Сетевой движок завершил работу. Сырое множество содержит:"
                        f" {len(valid_endpoints)} элементов.")
        _append_to_display(obj, msg_finished)

        sorted_results = sorted(valid_endpoints, key=lambda x: (x, x))
        _save_results_to_json(sorted_results, output_json_path, obj)

        _display_results_table(sorted_results, obj)

def run_security_api_scan(obj, output_json_path=None):
    """Синхронный инициализатор асинхронного ядра."""
    if output_json_path is None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        output_json_path = os.path.join(current_dir, "endpoints_config.json")

    obj.result_display.append("[🔄] Инициализация УНИВЕРСАЛЬНОГО ЭКСПРЕСС-ФАЗЗЕРА...")

    target_url = obj.base_url_input.text() # Базовый путь для сканирования

    asyncio.run(main_async_scan(obj, target_url, output_json_path))


if __name__ == "__main__":
    URL_TO_SCAN = "http://127.0.0.1:8000"
    run_security_api_scan(URL_TO_SCAN)
