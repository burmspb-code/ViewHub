import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import httpx

# Регулярное выражение для поиска путей API в коде (например: /api/v1/users, /v2/tasks)
API_PATTERN = re.compile(
    r'(?:"|\')((?:/api/|/v\d+/|/endpoint/)[a-zA-Z0-9_\-\.\/]+)(?:"|\')'
)


def get_js_links(base_url: str, html_content: str) -> set:
    """Находит все ссылки на JS-файлы на странице."""
    soup = BeautifulSoup(html_content, "html.parser")
    js_links = set()

    for script in soup.find_all("script"):
        src = script.get("src")
        if src:
            # Превращаем относительные ссылки в абсолютные (например, /static/main.js -> http://site.com)
            full_js_url = urljoin(base_url, src)
            # Сканируем только скрипты текущего сайта (игнорируем яндекс-метрики, гугл-аналитику)
            if urlparse(base_url).netloc in urlparse(full_js_url).netloc:
                js_links.add(full_js_url)

    return js_links


def scan_text_for_endpoints(text: str) -> set:
    """Ищет совпадения паттернов API в тексте или коде скрипта."""
    endpoints = set()
    matches = API_PATTERN.findall(text)
    for match in matches:
        # Убираем дубли слешей и мусор на концах строк
        clean_route = re.sub(r"/+", "/", match).strip()
        if len(clean_route) > 4:  # Игнорируем слишком короткие совпадения вроде '/api/'
            endpoints.add(clean_route)
    return endpoints


def auto_scan_site_api(target_url: str):
    """Главная функция сканирования сайта."""
    print(f"[🔄] Запуск сканирования сайта: {target_url}")

    # Заголовки, чтобы сайт не заблокировал нас как робота
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    found_endpoints = set()

    try:
        with httpx.Client(headers=headers, trust_env=False, timeout=15.0, follow_redirects=True) as client:
            # 1. Сканируем главную страницу
            response = client.get(target_url)
            if response.status_code != 200:
                print(
                    f"[❌] Не удалось загрузить сайт. Статус-код: {response.status_code}"
                )
                return

            print("[📌] Сканируем HTML-код главной страницы...")
            found_endpoints.update(scan_text_for_endpoints(response.text))

            # 2. Находим все JS-файлы на этой странице
            js_files = get_js_links(target_url, response.text)
            print(f"[📦] Найдено связанных JS-скриптов для анализа: {len(js_files)}")

            # 3. Сканируем каждый JS-файл внутри
            for js_url in js_files:
                try:
                    print(f"    ➡️ Сканируем скрипт: {urlparse(js_url).path}")
                    js_res = client.get(js_url)
                    if js_res.status_code == 200:
                        found_endpoints.update(
                            scan_text_for_endpoints(js_res.text)
                        )
                except httpx.HTTPError:
                    continue

    except Exception as e:
        print(f"[❌] Критическая ошибка при подключении: {e}")
        return

    # Выводим результат
    print(
        f"\n[🎉] Сканирование завершено! Автоматически найдено эндпоинтов: {len(found_endpoints)}"
    )
    print("=" * 60)
    for route in sorted(found_endpoints):
        print(f"📍 {route}")
    print("=" * 60)


if __name__ == "__main__":
    # Укажите адрес сайта, который вы хотите автоматически просканировать.
    # Например, для вашего локального проекта: "http://127.0.0"
    # Для внешнего сайта: "https://example.com"
    URL_TO_SCAN = "http://127.0.0.1:8000/"
    auto_scan_site_api(URL_TO_SCAN)
