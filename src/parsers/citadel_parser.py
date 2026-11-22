"""Класс парсинга для Сайта Цитадель."""

import logging

from typing import Any, Dict, Generator, List
from urllib.parse import quote_plus

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from src.my_exceptions.exceptions import ExceptionStopParser
from src.core.base_classes import BaseParser, BaseDBParsingConfig, BaseExtractor
from src.database.sqlite_manager import DatabaseManager

logger = logging.getLogger(__name__)

PARSER_DESCRIPTION = (
    "-" * 85 + "\n"
    "Парсер добавляет товары в БД из поисковых ответов сайта Цитадель.\n"
    "Введите ключевое слово, например: 'замок' или 'петля'.\n"
    "После выдачи отдельно открываются карточки товаров, чтобы получить код и бренд —\n"
    "это дольше, чем обычный обход списка. Цена скрыта до авторизации и может быть пустой.\n"
    "Экспорт данных из базы доступен в формате .xlsx или .csv.\n"
)

MAX_PAGES = 150
EMPTY_PAGES_LIMIT = 2
DETAIL_NAV_TIMEOUT = 60000


class CitadelParser(BaseParser):
    """Парсинг Сайта Цитадель."""

    def __init__(self, config: BaseDBParsingConfig, extractor: BaseExtractor, manager: DatabaseManager):
        super().__init__(config, extractor, manager)
        self.description = PARSER_DESCRIPTION
        self._cancel_requested = False
        self._page: Any = None
        self._context: Any = None
        self._browser: Any = None
        self._detail_page: Any = None

    def _report(self, message: str) -> None:
        """Отправляет статус в лог-панель, если колбэк подключён воркером."""
        callback = getattr(self, "progress_callback", None)
        if callable(callback):
            callback(message)

    def _on_cancel(self) -> None:
        """
        Хук отмены из BaseParser.

        Закрывать объекты Playwright из потока интерфейса небезопасно:
        они принадлежат потоку воркера. Здесь только поднимаем флаг,
        а ресурсы закрываются в finally основного цикла.
        """
        super()._on_cancel()
        self._cancel_requested = True
        self._report("🛑 Запрошена остановка парсинга Цитадели...")

    def _close_resources(self) -> None:
        """Закрывает страницы, контекст и браузер в правильном порядке."""
        for page in (self._detail_page, self._page):
            if page is None:
                continue
            try:
                if not page.is_closed():
                    page.close()
            except Exception as exc:
                logger.warning("Не удалось закрыть страницу Playwright: %s", exc)

        for resource in (self._context, self._browser):
            if resource is None:
                continue
            try:
                resource.close()
            except Exception as exc:
                logger.warning("Не удалось закрыть ресурс Playwright: %s", exc)

        self._detail_page = None
        self._page = None
        self._context = None
        self._browser = None

    def _build_url(self, page: int = 1) -> str:
        """Строит URL для указанной страницы поиска."""
        base_url = self.config.target_url.rstrip("/") + "/"
        url = f"{base_url}catalog/?q={quote_plus(self.config.keyword)}"
        if page > 1:
            url += f"&PAGEN_2={page}"
        return url

    def _enrich_item(self, item: Dict[str, Any]) -> None:
        """
        Отдельный проход по карточке товара: код и бренд есть только на странице товара.

        Недоступность карточки не должна терять данные из выдачи — в этом случае
        item остаётся с пустыми code/brand и всё равно сохраняется.
        """
        url = item.get("url")
        if not url:
            return

        try:
            detail = self._context.new_page()
            self._detail_page = detail
            detail.goto(url, wait_until="domcontentloaded", timeout=DETAIL_NAV_TIMEOUT)
            details = self.extractor.extract_detail_data(detail.content())
            for key in ("code", "brand"):
                if details.get(key):
                    item[key] = details[key]
        except Exception as exc:
            # Карточка может быть битой или закрытой — продолжаем остальные.
            logger.warning("Не удалось обогатить карточку %s: %s", url, exc)
            self._report(f"⚠️ Карточка без кода/бренда: {url}")
        finally:
            if self._detail_page is not None:
                try:
                    if not self._detail_page.is_closed():
                        self._detail_page.close()
                except Exception as exc:
                    logger.warning("Не удалось закрыть страницу товара: %s", exc)
            self._detail_page = None

    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        """Пошагово возвращает списки словарей с данными (постранично)."""
        current_page = 1
        no_items_streak = 0

        try:
            with sync_playwright() as p:
                # Закрытие должно произойти ПОКА event loop Playwright жив:
                # после выхода из with он уже остановлен и close() бесполезен.
                try:
                    self._browser = p.chromium.launch(headless=True)
                    self._context = self._browser.new_context()
                    self._page = self._context.new_page()

                    while current_page <= MAX_PAGES:
                        if not self._is_running or self._cancel_requested:
                            raise ExceptionStopParser("Процесс отменен пользователем.")

                        url = self._build_url(current_page)

                        try:
                            self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
                            # Ждём именно карточки товаров: ссылки /catalog/ есть
                            # и в меню категорий, они не означают загрузку выдачи.
                            self._page.wait_for_selector(".product-card", state="attached", timeout=30000)
                        except PlaywrightTimeoutError as e:
                            # Первая страница без карточек — ошибка, последующие — конец выдачи.
                            if current_page == 1:
                                raise RuntimeError(f"❌ Карточки товаров не появились на первой странице: {e}") from e
                            break
                        except Exception as e:
                            raise RuntimeError(f"❌ Ошибка навигации на странице {current_page}: {e}") from e

                        html_content = self._page.content()
                        new_items = self.extractor.extract_data(html_content)

                        if new_items:
                            # Проход по карточкам отдельно от выдачи: код и бренд
                            # доступны только на странице товара. Сохраняем поштучно,
                            # чтобы данные не терялись при отмене посреди страницы.
                            for item in new_items:
                                if not self._is_running or self._cancel_requested:
                                    raise ExceptionStopParser("Процесс отменен пользователем.")
                                self._enrich_item(item)
                                self.manager.save([item])

                            enriched = sum(1 for item in new_items if item.get("code"))
                            no_items_streak = 0
                            self._report(
                                f"🟢 Страница №{current_page} обработана.\n"
                                f"💾 Сохранено товаров: {len(new_items)}, с кодом: {enriched}"
                            )
                            yield new_items
                        else:
                            no_items_streak += 1
                            if no_items_streak >= EMPTY_PAGES_LIMIT:
                                break

                        current_page += 1
                finally:
                    self._close_resources()
        finally:
            self._cancel_requested = False
