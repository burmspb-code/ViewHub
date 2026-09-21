"""
Модуль универсального асинхронного экспресс-сканирования API.
Автоматически адаптируется под структуру сайта и выводит HTTP-коды безопасности.
"""

import asyncio
import json
import logging
import os
import re
# Импортируем ядро Qt для управления событиями интерфейса
from PyQt6.QtCore import QCoreApplication

import httpx
from bs4 import BeautifulSoup

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


async def test_single_path(client, target_url, path_clean, valid_endpoints, semaphore: asyncio.Semaphore):
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

            # 2. Если GET выдал 404, но путь явно похож на API, пробуем бахнуть POST-запросом!
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


def print_progress_bar(current, total, bar_length=30):
    """Рисует динамическую полосу прогресса в консоли."""
    fraction = current / total
    arrow = int(fraction * bar_length - 1) * "▓" + "▓"
    padding = int(bar_length - len(arrow)) * "░"
    percent = int(fraction * 100)

    # \r возвращает курсор в начало строки, а end="" не дает перенестись на новую строку
    print(f"\r[📡] Прогресс сканирования: [{arrow}{padding}] {percent}% ({current}/{total})", end="", flush=True)


async def main_async_scan(obj, target_url, output_json_path):
    """Главный управляющий асинхронный движок."""
    wordlist = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    valid_endpoints = set()

    async with httpx.AsyncClient(headers=headers, trust_env=False, follow_redirects=True) as client:
        try:
            response = await client.get(target_url, timeout=5.0)
        except Exception as e:
            logger.error(f"[❌] Ошибка первичного подключения к серверу: {e}")
            return

        obj.result_display.append("[🔎] Анализ структуры и извлечение явных путей...")
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

        # === ИНТЕЛЛЕКТУАЛЬНЫЙ BLACK-BOX ПРЕД-ПРОБИВ СКРЫТОГО API ===
        # Если в HTML ничего не найдено, мы проверяем реакцию сервера напрямую через быстрые сетевые зонды
        if not discovered_api_markers:
            if hasattr(obj, 'result_display') and obj.result_display:
                obj.result_display.append(
                    "[🔎] Маркеры не найдены в HTML. Запуск Black-Box зондирования корня API...")

            test_api_paths = ["/api/", "/api/v1/"]
            api_detected_in_wild = False

            for api_path in test_api_paths:
                try:
                    api_check_res = await client.get(f"{target_url.rstrip('/')}{api_path}", timeout=3.0)
                    # Если код НЕ 404 — значит, там что-то живет (200, 401, 403 или 405)!
                    if api_check_res.status_code != 404:
                        api_detected_in_wild = True
                        break
                except Exception:
                    pass

            if api_detected_in_wild:
                if hasattr(obj, 'result_display') and obj.result_display:
                    obj.result_display.append("[🧠] Динамическое зондирование подтвердило скрытую REST-структуру!")
                discovered_api_markers.add("api")
                discovered_api_markers.add("v1")
            else:
                if hasattr(obj, 'result_display') and obj.result_display:
                    obj.result_display.append(
                        "[ℹ️] Зондирование завершено: Скрытая REST-архитектура отсутствует. Переход в WEB-режим.")
        else:
            # Если маркеры нашли в самом HTML — железно добавляем v1 для глубины матрицы
            discovered_api_markers.add("api")
            discovered_api_markers.add("v1")

        # === СБОР УНИКАЛЬНЫХ МОДУЛЕЙ СИСТЕМЫ ===
        detected_apps = set()
        for path in wordlist:
            if path and path.startswith("/"):
                parts = path.split("/")[1] if len(path.split("/")) > 1 else ""
                # Фильтруем системные префиксы
                if parts and parts not in ["admin", "api", "static", "product", "category", "contacts", "blog"]:
                    detected_apps.add(parts)

        # КЛАССИЧЕСКИЙ BLACK-BOX СЛОВАРЬ: Докидываем мировые стандарты и частые модули,
        # чтобы вскрыть скрытые приложения, на которые нет ссылок в интерфейсе
        common_web_apps = ["library", "mailings", "mailing", "blog", "shop", "orders", "cart", "profile", "dashboard"]
        for app in common_web_apps:
            # Чтобы не раздувать матрицу, добавляем их, только если сканер в чистом WEB-режиме
            detected_apps.add(app)

        # Вывод зацепок в графическое окно PyQt/PySide
        if hasattr(obj, 'result_display') and obj.result_display:
            if discovered_api_markers and any(m in clean_paths for m in ["api", "v1"]) if 'clean_paths' in locals() else discovered_api_markers:
                obj.result_display.append(f"[🧠] Активные API-маркеры матрицы: {list(discovered_api_markers)}")
            if detected_apps:
                obj.result_display.append(f"[🧠] Обнаружены уникальные модули системы: {list(detected_apps)}")

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

        obj.result_display.append("[💀] Компиляция универсальной матрицы путей (Мировой стандарт + ИИ)...")
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
            # Расширяем сущности (добавили множественное число по стандартам REST)
            entities = ["task", "tasks", "user", "users", "bookmark", "bookmarks"]
            actions = ["list", "view", "create", "update", "delete", "create-api", "update-api"]
            # Тестовые ID для проверки роутов типа /api/v1/bookmarks/1/
            rest_ids = ["1"]

            marker_combos = list(discovered_api_markers)
            if "api" in discovered_api_markers and len(discovered_api_markers) > 1:
                for m in discovered_api_markers:
                    if m != "api":
                        marker_combos.append(f"api/{m}")

            for app in detected_apps:
                for entity in entities:
                    for marker in marker_combos:
                        # 1. Стандартные плоские экшены (ваш старый код)
                        for action in actions:
                            wordlist.append(f"/{app}/{entity}/{marker}/{action}")
                            wordlist.append(f"/{app}/{marker}/{entity}/{action}")

                        # 2. НОВОЕ: Пробиваем REST стандарты с ID в середине
                        # Шаблон: /daily/api/v1/bookmarks/1
                        # Шаблон: /api/v1/bookmarks/1 (на случай если префикса приложения нет)
                        for r_id in rest_ids:
                            wordlist.append(f"/{app}/{marker}/{entity}/{r_id}")
                            wordlist.append(f"/{marker}/{entity}/{r_id}")

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

        # Логика формирования графической строки прогресса
        def get_ui_progress_text(current, total, bar_length=20):
            fraction = current / total
            arrow = int(fraction * bar_length - 1) * "▓" + "▓" if current > 0 else ""
            padding = int(bar_length - len(arrow)) * "░"
            percent = int(fraction * 100)
            return f"[📡] Прогресс сканирования: [{arrow}{padding}] {percent}% ({current}/{total})"

        # Выводим стартовый пустой индикатор в графическое текстовое поле
        if hasattr(obj, 'result_display') and obj.result_display:
            obj.result_display.append(get_ui_progress_text(completed_count, total_tasks))

        # Асинхронный опрос сети
            # Асинхронный опрос сети
            for future in asyncio.as_completed(tasks):
                await future  # Дожидаемся окончания конкретного запроса
                completed_count += 1

                # Обновляем прогресс-бар в графическом окне (каждые 10 запросов, чтобы интерфейс летал)
                if completed_count % 10 == 0 or completed_count == total_tasks:
                    if hasattr(obj, 'result_display') and obj.result_display:
                        # Удаляем старую строчку прогресса и пишем новую на её место
                        cursor = obj.result_display.textCursor()
                        cursor.movePosition(cursor.MoveOperation.End)
                        cursor.select(cursor.SelectionType.LineUnderCursor)
                        cursor.removeSelectedText()

                        # Вставляем обновленный текст прогресса
                        cursor.insertText(get_ui_progress_text(completed_count, total_tasks))

                        # Секретный фикс: принудительно заставляем PyQt перерисовать виджет на экране прямо сейчас
                        QCoreApplication.processEvents()

        # === КОНЕЦ ЦИКЛА (Сканирование успешно завершено!) ===

        # Формируем сообщение индикатора
        msg_finished = f"[📊] Сетевой движок завершил работу. Сырое множество содержит: {len(valid_endpoints)} элементов."

        # Извлекаем 3 элемента (marker, path, status), которые реально возвращает ядро
        sanitized_results = []
        for marker, path, status in valid_endpoints:
            sanitized_results.append((marker, path, status))

        # Сортируем результаты по типу маркера (API/WEB) и алфавиту путей
        sorted_results = sorted(list(set(sanitized_results)), key=lambda x: (x, x))

        # Формируем красивую структуру для сохранения в JSON
        json_endpoints = []
        for marker, path, status in sorted_results:
            json_endpoints.append(f"[{marker}] {path} (Код: {status})")

        try:
            os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
            with open(output_json_path, "w", encoding="utf-8") as json_file:
                json.dump(json_endpoints, json_file, indent=4, ensure_ascii=False)
            obj.result_display.append(f"[💾] Тотальная карта безопасности сохранена: {output_json_path}")
        except Exception as e:
            logger.error(f"[❌] Ошибка сохранения JSON: {e}")

        # === ВЫВОД КРАСИВОЙ ТАБЛИЦЫ В ГРАФИЧЕСКИЙ ИНТЕРФЕЙС ===
        msg_success = f"\n[🎉] Сканирование успешно завершено! В таблице отображено целей: {len(sorted_results)}"

        # Шапка таблицы
        line_equal = "=" * 75
        line_dash = "-" * 75
        header_text = f"{'№':<3} | {'ТИП':<5} | {'КОД':<5} | {'ПОЯСНЕНИЕ':<18} | {'ЭНДПОИНТ ДЛЯ ТЕСТИРОВАНИЯ БЕЗОПАСНОСТИ'}"

        # Выводим старт таблицы в интерфейс UI
        if hasattr(obj, 'result_display') and obj.result_display:
            obj.result_display.append("")  # Перенос строки после индикатора прогресса
            obj.result_display.append(msg_finished)
            obj.result_display.append(msg_success)
            obj.result_display.append(line_equal)
            obj.result_display.append(header_text)
            obj.result_display.append(line_dash)

        # Построчно выводим каждую цель в консоль и UI
        for index, (marker, path, status) in enumerate(sorted_results, 1):
            if status in [401, 403]:
                note = "Защищен (Token Req)"
            elif status == 405:
                note = "Метод не разрешен"
            elif status == 200:
                note = "Открыт (200 OK)"
            else:
                note = f"Статус {status}"

            # Форматируем строку
            row_text = f"{index:<3} | {marker:<5} | {status:<5} | {note:<18} | {path}"

            if hasattr(obj, 'result_display') and obj.result_display:
                obj.result_display.append(row_text)

        # Закрываем таблицу
        if hasattr(obj, 'result_display') and obj.result_display:
            obj.result_display.append(line_equal)

def run_security_api_scan(obj, output_json_path=None):
    """Синхронный инициализатор асинхронного ядра."""
    if output_json_path is None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        output_json_path = os.path.join(current_dir, "endpoints_config.json")

    obj.result_display.append(f"[🔄] Инициализация УНИВЕРСАЛЬНОГО ЭКСПРЕСС-ФАЗЗЕРА...")

    target_url = obj.base_url_input.text() # Базовый путь для сканирования

    asyncio.run(main_async_scan(obj, target_url, output_json_path))


if __name__ == "__main__":
    URL_TO_SCAN = "http://127.0.0.1:8000"
    run_security_api_scan(URL_TO_SCAN)
