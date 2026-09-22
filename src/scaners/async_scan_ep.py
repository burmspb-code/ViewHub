import asyncio
import logging
import re
import uuid
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from scaner_classes import BaseScaner

logger = logging.getLogger(__name__)

DEBUG_MODE = True


class AsyncScanEndpoint(BaseScaner):
    """
    Асинхронный сканер эндпоинтов.
    """

    def __init__(self, base_url: str):
        super().__init__(base_url)

    def run_scanning(self, worker) -> list:
        """
        Основной метод логики сканирования.
        Запускает асинхронный контекст и передает объект worker.
        """
        return asyncio.run(self._run_async_scan(worker))

    async def _run_async_scan(self, worker) -> list:
        """
        Асинхронная обертка для контроля состояния потока внутри asyncio loop.
        """
        return await scan_black_box_api(self.base_url, worker)


async def get_soft_404_fingerprint(client, base_url, prefix=""):
    """
    Делает запрос на заведомо фейковый путь, чтобы понять,
    как конкретный модуль (например, /admin/ или корень) маскирует ошибки под 200 OK.
    """
    fake_path = f"{prefix}/non_existent_{uuid.uuid4().hex[:8]}/"
    url = urljoin(base_url, fake_path)
    try:
        res = await client.get(url, timeout=3.0)
        return {"len": len(res.text), "status": res.status_code}
    except httpx.HTTPError:
        return {"len": 0, "status": 404}


def extract_paths_from_html(soup, response_text):
    """
    Извлекает пути из HTML-тегов и текста страницы.
    """
    raw_paths = set()

    # Извлекаем пути из тегов
    for tag in soup.find_all(['a', 'form', 'script']):
        path = tag.get('href') or tag.get('action') or tag.get('src')
        if path and path.startswith("/"):
            clean_path = path.split('?')[0]
            raw_paths.add(clean_path)

    # Извлекаем пути из текста через regex
    text_paths = re.findall(r'["\'](/[a-zA-Z0-9\-_/]+)["\']', response_text)
    raw_paths.update(text_paths)

    return raw_paths


def extract_module_from_path(path):
    """
    Извлекает имя модуля из пути (первый сегмент).
    Возвращает None, если модуль не подходит.
    """
    if not isinstance(path, str):
        return None

    parts = path.strip("/").split("/")
    if not parts or not parts[0]:
        return None

    module_candidate = parts[0].lower()
    excluded_modules = ["static", "media", "favicon.ico", "assets", "admin"]

    if module_candidate in excluded_modules:
        return None

    return module_candidate


async def collect_modules_from_html(client, base_url, worker):
    """
    Собирает модули из HTML-страницы (этап spidering).
    """
    detected_modules = set()

    try:
        if DEBUG_MODE:
            worker.progress_signal.emit(f"[📡] Подключение к цели: {base_url}")

        response = await client.get(base_url, timeout=5.0)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Извлекаем все пути
        raw_paths = extract_paths_from_html(soup, response.text)

        # Извлекаем модули из путей
        for path in raw_paths:
            module = extract_module_from_path(path)
            if module:
                detected_modules.add(module)

    except Exception as e:
        logger.info("[⚠️] Корень недоступен: %s", e)

    return detected_modules


def get_scan_dictionaries():
    """
    Возвращает предзагруженные словари для сканирования.
    """
    generic_actions = [
        "", "list", "all", "create", "add", "edit", "update", "delete", "remove", "refresh",
        "create-api", "update-api", "delete-api", "delete-image"
    ]
    generic_pks = ["1", "2"]
    generic_slugs = ["test", "sample", "item", "product", "category"]

    business_entities = [
        "task", "tasks", "bookmark", "bookmarks", "daily", "todo", "courses", "lessons",
        "product", "products", "category", "categories", "catalog", "shop", "cart", "orders", "vendor"
    ]
    auth_tokens = [
        "auth", "login", "register", "logout", "token", "refresh", "me", "profile", "payments",
        "password-reset", "password-reset/done", "password-reset/confirm"
    ]
    target_prefixes = ["users", "auth", "api", "v1", "v2", "aurora"]

    return {
        "actions": generic_actions,
        "pks": generic_pks,
        "slugs": generic_slugs,
        "entities": business_entities,
        "tokens": auth_tokens,
        "prefixes": target_prefixes
    }


def generate_flat_paths(module, dictionaries):
    """
    Генерирует плоские пути для одного модуля.
    """
    paths = set()
    paths.add(f"/{module}/")

    for action in dictionaries["actions"]:
        if action:
            paths.add(f"/{module}/{action}/")

    for pk in dictionaries["pks"]:
        paths.add(f"/{module}/{pk}/")

    for slug in dictionaries["slugs"]:
        paths.add(f"/{module}/{slug}/")
        for action in ["edit", "update", "delete", "delete-image"]:
            paths.add(f"/{module}/{slug}/{action}/")

    return paths


def generate_nested_paths(module, dictionaries):
    """
    Генерирует вложенные пути (модуль + сущность).
    """
    paths = set()

    for entity in dictionaries["entities"]:
        if module == entity:
            continue

        base = f"/{module}/{entity}"
        paths.add(f"{base}/")

        for action in dictionaries["actions"]:
            if action:
                paths.add(f"{base}/{action}/")

        for pk in dictionaries["pks"]:
            paths.add(f"{base}/{pk}/")

        for slug in dictionaries["slugs"]:
            paths.add(f"{base}/{slug}/")

    return paths


def generate_triple_nested_paths(p1, p2, p3, tokens):
    """
    Генерирует пути для тройной вложенности префиксов с токенами.
    """
    paths = set()
    base_3 = f"/{p1}/{p2}/{p3}"
    paths.add(f"{base_3}/")

    for token in tokens:
        paths.add(f"{base_3}/{token}/")
        paths.add(f"/{p1}/{p2}/{p3}/auth/{token}/")
        paths.add(f"/{p1}/{p2}/{p3}/{token}/")

    return paths


def generate_deep_rest_paths(dictionaries):
    """
    Генерирует глубоко вложенные REST-пути (снайперский пробив).
    """
    paths = set()
    prefixes = dictionaries["prefixes"]
    tokens = dictionaries["tokens"]

    for p1 in prefixes:
        for p2 in prefixes:
            if p1 == p2:
                continue

            paths.add(f"/{p1}/{p2}/")

            for p3 in prefixes:
                if p3 in [p1, p2]:
                    continue

                paths.update(generate_triple_nested_paths(p1, p2, p3, tokens))

    return paths

def generate_root_paths(dictionaries):
    """
    Генерирует корневые пути для монолитных приложений.
    """
    paths = set()
    for token in dictionaries["tokens"]:
        paths.add(f"/{token}/")
    return paths


def generate_path_matrix(discovered_modules):
    """
    Генерирует матрицу путей для сканирования на основе обнаруженных модулей.
    """
    dictionaries = get_scan_dictionaries()
    generated_paths = set()
    generated_paths.add("/admin/")

    # Генерация путей для каждого обнаруженного модуля
    for module in discovered_modules:
        generated_paths.update(generate_flat_paths(module, dictionaries))
        generated_paths.update(generate_nested_paths(module, dictionaries))

    # Снайперский пробив аномальной вложенности
    generated_paths.update(generate_deep_rest_paths(dictionaries))

    # Чистый корневой пробив для монолитов
    generated_paths.update(generate_root_paths(dictionaries))

    return sorted(generated_paths), dictionaries["entities"], dictionaries["tokens"]


def display_scan_statistics(worker, discovered_modules, business_entities, auth_tokens, paths_count):
    """
    Выводит статистику сканирования в UI.
    """
    worker.progress_signal.emit("\n" + "=" * 70)
    worker.progress_signal.emit("[🧠 СТАТУС СБОРА ЗАЦЕПОК И СЛОВАРЕЙ]")
    worker.progress_signal.emit("=" * 70)

    worker.progress_signal.emit("[🔹] ОБНАРУЖЕННЫЕ ЖИВЫЕ МОДУЛИ (Приложения сайта):")
    if discovered_modules:
        for m in discovered_modules:
            worker.progress_signal.emit(f"    └── /{m}/")
    else:
        worker.progress_signal.emit("    └── (Живых модулей на главной странице не обнаружено)")

    worker.progress_signal.emit("-" * 50)

    worker.progress_signal.emit("[🔸] ПРЕДЗАГРУЖЕННЫЙ ИИ-СЛОВАРЬ ДЛЯ ПОИСКА СКРЫТЫХ ЗОН:")
    worker.progress_signal.emit(f"    ├── Бизнес-сущности ({len(business_entities)} шт.):"
                                f" {', '.join(business_entities[:6])}...")
    worker.progress_signal.emit(f"    ├── ИБ-токены/Авторизация ({len(auth_tokens)} шт.):"
                                f" {', '.join(auth_tokens[:5])}...")
    worker.progress_signal.emit("=" * 70 + "\n")

    worker.progress_signal.emit(f"[📡] Снайперская матрица сгенерировала ОПТИМАЛЬНОЕ покрытие:"
                                f" {paths_count} комбинаций путей.")


def format_endpoint_info(endpoint_status):
    """
    Форматирует информацию о статусе эндпоинта.
    """
    if endpoint_status in [401, 403]:
        return "🔒 Защищен (Нужна авторизация / Token)"
    elif endpoint_status == 405:
        return "🚫 Метод GET не разрешен (Ожидает POST/PUT/DELETE)"
    elif endpoint_status == 200:
        return "🔓 Открыт (200 OK)"
    elif endpoint_status in [301, 302, 303, 307, 308]:
        return f"🔄 Перенаправление (Redirect {endpoint_status})"
    else:
        return f"📡 Код ответа: {endpoint_status}"


def display_final_report(worker, found_endpoints):
    """
    Выводит финальный отчёт о найденных эндпоинтах.
    """
    worker.progress_signal.emit(f"\n[🎉] Сканирование завершено. Найдено РЕАЛЬНЫХ точек: {len(found_endpoints)}")
    worker.progress_signal.emit("=" * 70)
    for ep in sorted(found_endpoints):
        worker.progress_signal.emit(f"  - {ep}")
    worker.progress_signal.emit("=" * 70)


async def check_single_endpoint(client, semaphore, base_url, endpoint_path, root_fingerprint, auth_patterns, worker):
    """
    Проверяет один эндпоинт и возвращает результат или None.
    """
    if not endpoint_path.startswith("/"):
        return None

    full_url = urljoin(base_url, endpoint_path)
    is_target_path = bool(auth_patterns.search(endpoint_path))

    async with semaphore:
        try:
            endpoint_response = await client.get(full_url, timeout=4.0)
            endpoint_status = endpoint_response.status_code
            response_len = len(endpoint_response.text)

            if is_target_path and endpoint_status != 404:
                worker.progress_signal.emit(
                    f"[🔍 REGEX СЕТЬ] Перехват роута: {endpoint_path} | "
                    f"Статус: {endpoint_status} | Длина: {response_len}")

            if endpoint_status == 404:
                return None

            # Исключения из фильтров для админки и целевых путей
            if "/admin" in endpoint_path or is_target_path:
                return endpoint_path, endpoint_status

            # Фильтр мягких 404 для обычных страниц
            if endpoint_status == 200:
                root_len = root_fingerprint.get("len", 0)
                if root_len > 0 and endpoint_path != "/":
                    diff = abs(response_len - root_len) / root_len
                    if diff < 0.02:
                        return None

            return endpoint_path, endpoint_status
        except httpx.HTTPError:
            pass
        return None


async def perform_fingerprinting(client, base_url, worker):
    """
    Выполняет фингерпринтинг для определения мягких 404.
    Возвращает fingerprint или None при отмене.
    """
    if worker.is_stopped():
        return None

    worker.progress_signal.emit("[🔄] Анализ ложных срабатываний (Калибровка детекторов ошибок)...")
    root_fingerprint = await get_soft_404_fingerprint(client, base_url, prefix="")

    if worker.is_stopped():
        return None

    if DEBUG_MODE:
        worker.progress_signal.emit("[⚙️] Фингерпринты ложных страниц успешно собраны")

    return root_fingerprint


async def scan_endpoints(client, semaphore, base_url, paths_to_check, root_fingerprint, auth_patterns, worker):
    """
    Сканирует список эндпоинтов и возвращает найденные.
    """
    worker.progress_signal.emit("[🚀] Запуск сканирования с регулярными исключениями...")

    tasks = [
        check_single_endpoint(client, semaphore, base_url, p, root_fingerprint, auth_patterns, worker)
        for p in paths_to_check
    ]
    results = await asyncio.gather(*tasks)

    # Формирование результатов
    found_endpoints = set()
    for res in results:
        if res:
            endpoint_path, endpoint_status = res
            info = format_endpoint_info(endpoint_status)
            found_endpoints.add(f"{endpoint_path:<45} | {info}")

    return found_endpoints


async def scan_black_box_api(base_url: str, worker) -> list:
    """
    Главная функция сканирования API (упрощённая версия).
    """
    found_endpoints = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NeoMarket-Sniper/5.2",
        "Accept": "application/json, text/html, */*",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }

    semaphore = asyncio.Semaphore(15)

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, trust_env=False) as client:
        # ЭТАП 1: Сбор зацепок
        detected_modules = await collect_modules_from_html(client, base_url, worker)

        # ЭТАП 2: Фингерпринтинг
        root_fingerprint = await perform_fingerprinting(client, base_url, worker)
        if root_fingerprint is None:
            return list(found_endpoints)

        # ЭТАП 3: Генерация матрицы путей
        discovered_modules = sorted({m.strip("/") for m in detected_modules if m and m != "__debug__"})
        paths_to_check, business_entities, auth_tokens = generate_path_matrix(discovered_modules)

        # Вывод статистики
        display_scan_statistics(worker, discovered_modules, business_entities, auth_tokens, len(paths_to_check))

        # Контрольная проверка
        auth_patterns = re.compile(r'(login|register|auth|password-reset|me|payments)')
        bug_path_check = "/users/api/v1/auth/login/"
        worker.progress_signal.emit(
            f"[🔍 REGEX ПРОВЕРКА] Присутствует ли /users/api/v1/auth/login/ в матрице? ->"
            f" {bug_path_check in set(paths_to_check)}")

        # ЭТАП 4: Активное зондирование
        found_endpoints = await scan_endpoints(
            client, semaphore, base_url, paths_to_check,
            root_fingerprint, auth_patterns, worker
        )

    display_final_report(worker, found_endpoints)
    return list(found_endpoints)