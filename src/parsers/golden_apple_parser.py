"""Класс парсинга для Сайта Золотое яблоко."""

import os
import time
import logging
import re
import random
import typing

from bs4 import BeautifulSoup
from typing import Any, List, Dict, Generator
from playwright.sync_api import sync_playwright

from core.base_classes import BaseParser, BaseDBParsingConfig, BaseExtractor
from savers import SQLiteSaver
from exceptions import ExceptionStopParser


logger = logging.getLogger(__name__)


class GoldenAppleParser(BaseParser):
    """Парсинг Сайта Golden Apple."""

    def __init__(self, config: BaseDBParsingConfig, extractor: BaseExtractor, saver: SQLiteSaver):
        super().__init__(config, extractor, saver)
        # Задаем начальные значения для пагинации
        self.current_page = 1
        # Создаем папку для профиля браузера
        self.user_data_dir = os.path.join(os.getcwd(), "chrome_user_profile")

    def _build_url(self, page: int = 1) -> str:
        """
        Строит URL для указанной страницы категории каталога.
        Склеивает базовый домен со слагом раздела и добавляет пагинацию.
        """
        # Очищаем базовый домен и слаг категории от крайних слешей, чтобы избежать двойных косых линий //
        base_url = self.config.target_url.strip("/")
        category_slug = self.config.keyword.strip("/")

        # Собираем чистый, красивый путь к разделу (например: https://goldapple.ru)
        url = f"{base_url}/{category_slug}"

        # Добавляем стандартный для Зотолого Яблока параметр страницы пагинации
        if page > 1:
            url += f"?p={page}"

        return url

    def load_product_detail_page(self, context, product_url: str, product_id: str) -> Any:
        """
        Модуль 3 (СИНХРОННЫЙ ООП вариант): Открытие фоновой вкладки товара.
        Терпеливо дожидается, пока лоадер сайта (дефис) не сменится реальным текстом товара.
        """

        page = None

        try:
            # Создаем чистую страницу в текущем изолированном контексте
            page = context.new_page()

            # Переходим на страницу товара с ограничением по времени (30 секунд)
            page.goto(product_url, wait_until="domcontentloaded", timeout=30000)

            # ЖЕСТКИЙ СТОПОР: Ждем появление главного заголовка страницы (название духов / бренд)
            # Задаем конечный таймаут в 20 секунд, чтобы поток не завис, если страница недоступна
            page.locator("h1").first.wait_for(state="attached", timeout=20000)

            # Небольшая контролируемая пауза для окончательного монтажа Vue-компонентов
            self._smart_sleep(2.0)

            return page

        except Exception as e:
            # Если пользователь нажал Отмена во время ожидания карточки, мгновенно выходим
            if not self._is_running:
                raise ExceptionStopParser("Процесс отменен пользователем.") from e
            logger.error(f"    [-] [Детальная Ошибка] Не удалось дождаться загрузки карточки ID {product_id}: {e}")
            if page is not None:
                page.close()
            return None

    def load_catalog_page(self, page, url: str) -> Any:
        """Загрузка страницы каталога с защитой от Lazy-Render скрытого режима."""
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page.route(
            "**/*",
            lambda route: (
                route.abort()
                if route.request.resource_type in ["image", "font", "media", "image-set"]
                else route.continue_()
            ),
        )

        try:
            # Загружаем базовый URL
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # ИСПРАВЛЕНО: Ждем прикрепления тега в DOM (attached) вместо видимости на экране (visible)
            # Это полностью исключает TimeoutError в скрытом (headless) режиме!
            page.locator("article").first.wait_for(state="attached", timeout=15000)

            # ЭМУЛЯЦИЯ СКРОЛЛА: Плавно прокручиваем страницу вниз на 1500 пикселей,
            # Вместо резкого прыжка делаем три небольших шага для эмуляции реального человека
            for offset in range(500, 1501, 500):
                page.evaluate(f"window.scrollTo(0, {offset});")
                self._smart_sleep(0.3) # Даем Nuxt 3 время среагировать на скролл

            # Даем умный сон 4 секунды, чтобы сетка полностью стабилизировалась в памяти
            self._smart_sleep(4.0)

            return page

        except Exception as e:
            if not self._is_running:
                raise ExceptionStopParser("Процесс отменен пользователем.") from e
            logger.error(f"❌ Не удалось прогрузить страницу каталога №{self.current_page}: {e}")
            raise e


    def count_and_get_products_on_page(self, page) -> Any:
        """
        Определение количества товаров на странице.
        Считывает HTML открытой вкладки и находит все контейнеры карточек товаров.
        """
        try:
            # Извлекаем текущий HTML из оперативной памяти вкладки
            html_content = page.content()
            soup = BeautifulSoup(html_content, "html.parser")

            # Находим контейнеры карточек по логике тегов <article>
            cards = soup.find_all("article")

            return cards

        except Exception as e:
            logger.error(f"❌ Не удалось определить количество товаров на странице №{self.current_page}: {e}")
            raise e

    def _smart_sleep(self, seconds: float) -> None:
        """
        Потокобезопасная микро-пауза. Разбивает долгое ожидание на шаги по 0.1 секунды
        и постоянно проверяет флаг отмены, предотвращая намертво зависание QThread.
        """
        start_time = time.time()
        while time.time() - start_time < seconds:
            # Если пользователь нажал Стоп в GUI, мгновенно прерываем паузу
            if not self._is_running:
                raise ExceptionStopParser("Процесс отменен пользователем во время паузы.")
            time.sleep(0.1)

    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        def to_gui(msg: str):
            callback = getattr(self, "progress_callback", None)
            if callback is not None and callable(callback):
                typing.cast(typing.Callable[[str], None], callback)(msg)

        to_gui("=== ЗАПУСК СКРЫТОГО КОНВЕЙЕРА ПАРСИНГА ===")

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--blink-settings=imagesEnabled=false",
                ],
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                           " AppleWebKit/537.36 (KHTML, like Gecko)"
                           " Chrome/124.0.0.0 Safari/537.36",
                locale="ru-RU",
                timezone_id="Europe/Moscow",
            )

            page = context.new_page()

            try:
                while True:
                    if not self._is_running:
                        raise ExceptionStopParser("Процесс отменен пользователем.")

                    url = self._build_url(self.current_page)
                    to_gui(f"🌐 Загрузка страницы каталога №{self.current_page}...")

                    catalog_page = self.load_catalog_page(page, url)
                    current_url = catalog_page.url

                    # Проверка на конец пагинации
                    if self.current_page > 1 and f"p={self.current_page}" not in current_url:
                        to_gui("🏁 Каталог полностью пройден. Завершение работы.")
                        break

                    product_cards = self.count_and_get_products_on_page(catalog_page)
                    if not product_cards:
                        to_gui(f"🏁 На странице №{self.current_page} нет товаров. Останов.")
                        break

                    to_gui(f"🔎 Найдено {len(product_cards)} карточек. Сбор базовых данных...")
                    base_items = self.extractor.extract_data(product_cards)

                    page_batch = []
                    total_in_batch = len(base_items)
                    saved_in_page = 0

                    to_gui(f"🚀 Запуск глубокого обхода {total_in_batch} карточек поштучно...")

                    for idx, item in enumerate(base_items, start=1):
                        if not self._is_running:
                            raise ExceptionStopParser("Процесс отменен пользователем.")

                        item["catalog_page_url"] = url
                        product_id = item.get("item_id", "Неизвестен")
                        product_url = item.get("url", "")

                        # Нормализация URL
                        if product_url and "goldapple.ru/" not in product_url:
                            product_url = re.sub(r"goldapple\.ru(?=\d)", "goldapple.ru/", product_url)
                            item["url"] = product_url

                        to_gui(
                            f" 📦 [{idx}/{total_in_batch}]"
                            f" Товар ID: {product_id} ({item.get('brand')} -"
                            f" {item.get('name')})"
                        )

                        deep_data = {
                            "description": "Описание отсутствует",
                            "usage": "Не указано",
                            "country_of_origin": "Не указана",
                        }

                        # --- БЛОК ДЛЯ БИТОГО URL ---
                        if not product_url or product_url in ["https://goldapple.ru", "https://goldapple.ru"]:
                            item.update(deep_data)

                            # Записываем номер страницы прямо в словарь товара перед сохранением
                            item["page_number"] = self.current_page

                            page_batch.append(item)
                            self.saver.save([item]) # Передаем чистый список из одного товара
                            saved_in_page += 1
                            continue
                        # --------------------------

                        detail_page = self.load_product_detail_page(context, product_url, product_id)

                        if detail_page:
                            try:
                                html_content = detail_page.content()
                                deep_data = self.extractor.extract_deep_data(html_content)
                                to_gui(f"    └─ ✅ Характеристики собраны! Страна: {deep_data['country_of_origin']}")
                            except Exception as e:
                                if not self._is_running:
                                    raise ExceptionStopParser("Процесс отменен пользователем.") from e
                                # Ошибку гасим, данные останутся дефолтными
                            finally:
                                detail_page.close()

                        item.update(deep_data)

                        # Записываем номер страницы прямо в словарь товара перед сохранением
                        item["page_number"] = self.current_page

                        # ПОСТРОЧНАЯ ЗАПИСЬ
                        self.saver.save([item]) # Передаем чистый список из одного товара
                        saved_in_page += 1
                        # --------------------------------------

                        page_batch.append(item)

                        if idx < total_in_batch:
                            self._smart_sleep(random.uniform(1.5, 3.0)) # noqa: S311

                    # Отдаем пакет воркеру ТОЛЬКО для статистики
                    yield page_batch

                    to_gui(f"💾 Страница №{self.current_page}: записано {saved_in_page} из {total_in_batch} товаров.")

                    # Увеличиваем счетчик страницы ТОЛЬКО после полной обработки текущей
                    self.current_page += 1

            except ExceptionStopParser as e:
                context.close()
                raise e
            except Exception as e:
                context.close()
                raise e
