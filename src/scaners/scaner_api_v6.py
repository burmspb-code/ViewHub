import asyncio
import re
import uuid
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

DEBUG_MODE = True


async def get_soft_404_fingerprint(client, base_url, prefix=""):
    """
    Делает запрос на заведомо фейковый путь, чтобы понять,
    как конкретный модуль (например, /admin/ или корень) маскирует ошибки под 200 OK.
    """
    fake_path = f"{prefix}/non_existent_{uuid.uuid4().hex[:8]}/"
    url = urljoin(base_url, fake_path)
    try:
        res = await client.get(url, timeout=3.0)
        # Возвращаем длину страницы и статус-код
        return {"len": len(res.text), "status": res.status_code}
    except Exception:
        return {"len": 0, "status": 404}


async def scan_black_box_api(base_url: str):
    found_endpoints = set()
    detected_modules = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NeoMarket-Sniper/5.2",
        "Accept": "application/json, text/html, */*",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }

    semaphore = asyncio.Semaphore(15)

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, trust_env=False) as client:

        # --- ЭТАП 1: УМНЫЙ СБОР ЗАЦЕПОК (Spidering) ---
        try:
            if DEBUG_MODE:
                print(f"[📡] Подключение к цели: {base_url}")
            response = await client.get(base_url, timeout=5.0)

            soup = BeautifulSoup(response.text, 'html.parser')
            raw_paths = set()

            for tag in soup.find_all(['a', 'form', 'script']):
                # Безопасно получаем любой из существующих атрибутов
                path = tag.get('href') or tag.get('action') or tag.get('src')
                if path and path.startswith("/"):
                    # Берем только часть ДО знака вопроса (строку), а не список
                    clean_path = path.split('?')[0]
                    raw_paths.add(clean_path)

            text_paths = re.findall(r'["\'](/[a-zA-Z0-9\-_/]+)["\']', response.text)
            raw_paths.update(text_paths)

            for path in raw_paths:
                # Проверяем, что path действительно строка (защита от багов)
                if not isinstance(path, str):
                    continue

                parts = path.strip("/").split("/")
                # Проверяем, что список не пустой и первый элемент существует
                if parts and parts[0]:
                    module_candidate = parts[0].lower()  # Берем именно ПЕРВЫЙ элемент (строку)
                    if module_candidate not in ["static", "media", "favicon.ico", "assets", "admin"]:
                        detected_modules.add(module_candidate)

        except Exception as e:
            print(f"[⚠️] Корень недоступен: {e}")

        # Базовый ИИ-словарь для СНГ-разработки и стандартных API (добавляем к найденным)
        # detected_modules.update(global_standards)

        # --- ЭТАП 2: ФИНГЕРПРИНТИНГ ДЛЯ БОРЬБЫ С ФЕЙКАМИ ---
        print("[🔄] Анализ ложных срабатываний (Калибровка детекторов ошибок)...")
        # Получаем эталонные слепки ложных страниц для корня и для админки
        root_fingerprint = await get_soft_404_fingerprint(client, base_url, prefix="")
        await get_soft_404_fingerprint(client, base_url, prefix="/admin")

        # =========================================================================
        # --- ЭТАП 3: АВТОНОМНАЯ СНАЙПЕРСКАЯ МАТРИЦА (Версия 5.3) ---
        # =========================================================================
        generic_actions = [
            "", "list", "all", "create", "add", "edit", "update", "delete", "remove", "refresh",
            "create-api", "update-api", "delete-api", "delete-image"
        ]
        generic_pks = ["1", "2"]
        generic_slugs = ["test", "sample", "item", "product", "category"]

        # НАШ ПРЕДЗАГРУЖЕННЫЙ БАЗОВЫЙ СЛОВАРЬ (Бизнес-сущности + ИБ-токены)
        business_entities = [
            "task", "tasks", "bookmark", "bookmarks", "daily", "todo", "courses", "lessons",
            "product", "products", "category", "categories", "catalog", "shop", "cart", "orders", "vendor"
        ]
        auth_tokens = [
            "auth", "login", "register", "logout", "token", "refresh", "me", "profile", "payments",
            "password-reset", "password-reset/done", "password-reset/confirm"
        ]

        # --- 📦 КРАСИВЫЙ ИЗОЛИРОВАННЫЙ ВЫВОД ИНФОРМАЦИИ ---
        print("\n" + "=" * 90)
        print("[🧠 СТАТУС СБОРА ЗАЦЕПОК И СЛОВАРЕЙ]")
        print("=" * 90)

        # Теперь здесь будут ТОЛЬКО те модули, которые скрипт РЕАЛЬНО распарсил из HTML/скриптов
        discovered_modules = sorted(list(set(m.strip("/") for m in detected_modules if m and m != "__debug__")))
        print("[🔹] ОБНАРУЖЕННЫЕ ЖИВЫЕ МОДУЛИ (Приложения сайта):")
        if discovered_modules:
            for m in discovered_modules:
                print(f"    └── /{m}/")
        else:
            print("    └── (Живых модулей на главной странице не обнаружено)")

        print("-" * 50)

        print("[🔸] ПРЕДЗАГРУЖЕННЫЙ ИИ-СЛОВАРЬ ДЛЯ ПОИСКА СКРЫТЫХ ЗОН:")
        print(f"    ├── Бизнес-сущности ({len(business_entities)} шт.): {', '.join(business_entities[:6])}...")
        print(f"    ├── ИБ-токены/Авторизация ({len(auth_tokens)} шт.): {', '.join(auth_tokens[:5])}...")
        print(
            f"    └── Стандартные HTTP-действия ({len(generic_actions)} шт.):"
            f" {', '.join(filter(None, generic_actions[:5]))}..."
        )
        print("=" * 90 + "\n")

        # --- СБОРКА И МАТРИЧНАЯ ГЕНЕРАЦИЯ ПУТЕЙ ---
        generated_paths = set()
        generated_paths.add("/admin/")

        # ЖЕСТКИЕ ПРЕФИКСЫ ДЛЯ ГЛУБОКОГО REST-ПРОБИВА (Зашиваем их сюда, чтобы они не портили discovered_modules)
        target_prefixes = ["users", "auth", "api", "v1", "v2", "aurora"]

        # 1. ПЛОСКАЯ И ДВУХУРОВНЕВАЯ ГЕНЕРАЦИЯ (Используем discovered_modules)
        for mod in discovered_modules:
            generated_paths.add(f"/{mod}/")
            for action in generic_actions:
                if action:
                    generated_paths.add(f"/{mod}/{action}/")
            for pk in generic_pks:
                generated_paths.add(f"/{mod}/{pk}/")

            for slug in generic_slugs:
                generated_paths.add(f"/{mod}/{slug}/")
                for action in ["edit", "update", "delete", "delete-image"]:
                    generated_paths.add(f"/{mod}/{slug}/{action}/")

            for ent in business_entities:
                if mod == ent:
                    continue
                base_2 = f"/{mod}/{ent}"
                generated_paths.add(f"{base_2}/")
                for action in generic_actions:
                    if action:
                        generated_paths.add(f"{base_2}/{action}/")
                for pk in generic_pks:
                    generated_paths.add(f"{base_2}/{pk}/")
                for slug in generic_slugs:
                    generated_paths.add(f"{base_2}/{slug}/")

        # 2. СНАЙПЕРСКИЙ ПРОБИВ АНОМАЛЬНОЙ ВЛОЖЕННОСТИ
        for p1 in target_prefixes:
            for p2 in target_prefixes:
                if p1 == p2:
                    continue
                generated_paths.add(f"/{p1}/{p2}/")
                for p3 in target_prefixes:
                    if p3 in [p1, p2]:
                        continue
                    base_3 = f"/{p1}/{p2}/{p3}"
                    generated_paths.add(f"{base_3}/")
                    for token in auth_tokens:
                        generated_paths.add(f"{base_3}/{token}/")
                        generated_paths.add(f"/{p1}/{p2}/{p3}/auth/{token}/")
                        generated_paths.add(f"/{p1}/{p2}/{p3}/{token}/")

        # 3. ЧИСТЫЙ КОРНЕВОЙ ПРОБИВ ДЛЯ МОНОЛИТОВ
        for token in auth_tokens:
            generated_paths.add(f"/{token}/")

        paths_to_check = sorted(list(generated_paths))
        print(f"[📡] Снайперская матрица сгенерировала ОПТИМАЛЬНОЕ покрытие: {len(paths_to_check)} комбинаций путей.")

        # Контрольные принты отладки
        auth_patterns = re.compile(r'(login|register|auth|password-reset|me|payments)')
        bug_path_check = "/users/api/v1/auth/login/"
        print(
            f"[🔍 REGEX ПРОВЕРКА] Присутствует ли /users/api/v1/auth/login/ в матрице? ->"
            f" {bug_path_check in generated_paths}")
        # --- ЭТАП 4: АКТИВНОЕ ВАЛИДИРОВАННОЕ ЗОНДИРОВАНИЕ С REGEX ФИЛЬТРАЦИЕЙ ---
        async def check_endpoint(path):
            if not path.startswith("/"):
                return None
            full_url = urljoin(base_url, path)

            # Regex для отслеживания целевых путей в логах
            is_target_path = bool(auth_patterns.search(path))

            async with semaphore:
                try:
                    # Важно: для каноничности смотрим и на первоначальный ответ (без редиректа),
                    # поэтому временно отключаем follow_redirects для точечного анализа кодов 301/302
                    res = await client.get(full_url, timeout=4.0)
                    status = res.status_code
                    r_len = len(res.text)

                    if is_target_path and status != 404:
                        print(f"[🔍 REGEX СЕТЬ] Перехват роута: {path:<45} | Статус: {status} | Длина: {r_len}")

                    if status == 404:
                        return None

                    # --- ИСКЛЮЧЕНИЯ ИЗ ФИЛЬТРОВ ЧЕРЕЗ РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ ---
                    # Если в пути есть админка или ключевые ИБ-слова, спасаем путь от любых фильтров мягких 404
                    if "/admin" in path or is_target_path:
                        return (path, status)

                    # Фильтр общих мягких 404 с допуском 2% (применяем только к некритичным страницам 200 OK)
                    if status == 200:
                        root_len = root_fingerprint.get("len", 0)
                        if root_len > 0 and path != "/":
                            diff = abs(r_len - root_len) / root_len
                            if diff < 0.02:
                                return None

                    return (path, status)
                except httpx.HTTPError:
                    pass
                return None

        print("[🚀] Запуск сканирования с регулярными исключениями...")
        tasks = [check_endpoint(p) for p in paths_to_check]
        results = await asyncio.gather(*tasks)

        # Формирование красивого отчета
        for res in results:
            if res:
                path, status = res
                if status in [401, 403]:
                    info = "🔒 Защищен (Нужна авторизация / Token)"
                elif status == 405:
                    info = "🚫 Метод GET не разрешен (Ожидает POST/PUT/DELETE)"
                elif status == 200:
                    info = "🔓 Открыт (200 OK)"
                elif status in [301, 302, 303, 307, 308]:
                    info = f"🔄 Перенаправление (Redirect {status})"
                else:
                    info = f"📡 Код ответа: {status}"
                found_endpoints.add(f"{path:<45} | {info}")

    print(f"\n[🎉] Сканирование завершено. Найдено РЕАЛЬНЫХ точек: {len(found_endpoints)}")
    print("=" * 90)
    for ep in sorted(found_endpoints):
        print(f"  - {ep}")
    print("=" * 90)

if __name__ == "__main__":
    asyncio.run(scan_black_box_api("http://127.0.0.1:8000/"))
