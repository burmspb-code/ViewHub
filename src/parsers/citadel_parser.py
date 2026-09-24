"""Класс парсинга для Сайта Цитадель."""

from typing import Any, Dict, Generator, List

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from exceptions import ExceptionStopParser
from parser_classes import BaseParser


class CitadelParser(BaseParser):
    """Парсинг Сайта Цитадель."""

    def _build_url(self, page: int = 1) -> str:
        """Строит URL для указанной страницы."""

        base_url = self.config.target_url.rstrip("/") + "/"
        url = f"{base_url}catalog/?q={self.config.keyword}"
        if page > 1:
            url += f"&PAGEN_2={page}"
        return url


    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        """Пошагово возвращает списки словарей с данными (постранично)."""
        current_page = 1
        max_pages = 50
        no_items_streak = 0

        # Инициализация Playwright внутри метода парсинга
        with sync_playwright() as p:
            # Запускаем браузер в фоновом (headless) режиме
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            while current_page <= max_pages:
                # Обязательная проверка флага остановки из интерфейса
                if not self._is_running:
                    raise ExceptionStopParser("Процесс отменен пользователем.")

                url = self._build_url(current_page)

                try:
                    # Переход по URL
                    page.goto(url, wait_until="networkidle", timeout=60000)

                    # Ожидание появления карточек товара
                    page.wait_for_selector('a[href*="/catalog/"]', state="attached", timeout=30000)
                    page.wait_for_timeout(2000)

                except PlaywrightTimeoutError as e:
                    # Если это первая страница — падаем, если последующие — возможно, каталог кончился
                    if current_page == 1:
                        raise RuntimeError(f"❌ Ссылки не появились на первой странице: {e}") from e
                    break
                except Exception as e:
                    raise RuntimeError(f"❌ Ошибка навигации на странице {current_page}: {e}") from e

                # Извлекаем данные из HTML текущей страницы
                html_content = page.content()
                new_items = self.extractor.extract_data(html_content)

                # Обработка пустых страниц (streak)
                if new_items:
                    no_items_streak = 0
                    # Возвращаем ТОЛЬКО новые элементы текущей страницы
                    yield new_items
                else:
                    no_items_streak += 1
                    if no_items_streak >= 2:
                        # Штатное завершение по условию - последние две пустые страницы
                        break

                current_page += 1
