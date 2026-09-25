"""Класс парсинга для Сайта Золотое яблоко."""

import os
import time
import logging

from bs4 import BeautifulSoup
from typing import Any, List, Dict, Generator
from playwright.sync_api import sync_playwright

from exceptions import ExceptionStopParser


logger = logging.getLogger(__name__)


class GoldenAppleParser(BaseParser):
    """Парсинг Сайта Golden Apple."""

    def __init__(self, config: BaseConfig, extractor: BaseExtractor, saver: BaseSaver):
        super().__init__(config, extractor, saver)
        # Задаем начальные значения для пагинации
        self.current_page = 1
        # Создаем папку для профиля браузера
        self.user_data_dir = os.path.join(os.getcwd(), "chrome_user_profile")

    def _build_url(self, page: int = 1) -> str:
        """
        Строит URL для указанной страницы.
        """
        # Строим начальный url с пагинацией
        base_url = self.config.target_url.rstrip("/") + "/"
        url = f"{base_url}?q={self.config.keyword}"  # Добавлен знак '=' после 'q'
        if page > 1:
            url += f"&p={page}"
        return url

    def load_catalog_page(self, page, url: str) -> Any:
        """
        Загрузка конкретной страницы каталога.
        Открывает скрытую вкладку, дожидается отрисовки Nuxt-карточек и возвращает страницу.
        """
        # Скрытие автоматизации на уровне браузера
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Оптимизация сети (ИСПРАВЛЕНО ДЛЯ СИНХРОННОГО РЕЖИМА):
        # Убран лишний аргумент 'request' из сигнатуры лямбды
        page.route(
            "**/*",
            lambda route: (
                route.abort()
                if route.request.resource_type in ["image", "font", "media", "image-set"]
                else route.continue_()
            ),
        )

        try:
            # Загружаем базовую структуру
            page.goto(url, wait_until="domcontentloaded", timeout=0)

            # Жестко ждем, пока интернет физически не отрисует карточки товаров в DOM
            page.locator("article").first.wait_for(state="visible", timeout=0)

            # Пауза для окончательного монтажа сетки товаров во Vue/Nuxt
            time.sleep(4.0)

            return page

        except Exception as e:
            logger.error(f"❌ Не удалось прогрузить страницу каталога №{self.current_page}: {e}")
            page.close()
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

    def run_parsing(self) -> Generator[Dict[str, Any], None, None]:
        """
        Пошагово возвращает ОДИН словарь с полными данными товара (поштучный генератор).
        Идеально подходит для плавной отрисовки ProgressBar в PyQt6.
        """
        # Инициализация Playwright внутри метода парсинга
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,  # Директория с профилем браузера
                headless=True,  # Полностью невидимый интерфейс в памяти
                args=[
                    "--disable-blink-features=AutomationControlled",  # МАСКИРОВОЧНЫЙ ФЛАГ
                    "--blink-settings=imagesEnabled=false",  # ОТКЛЮЧЕНИЕ КАРТИНОК
                ],
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="ru-RU",
                timezone_id="Europe/Moscow",
            )

            page = context.new_page()

            try:
                while True:
                    # ЗАЩИТА №1: Проверка флага остановки перед загрузкой новой страницы
                    if not self._is_running:
                        raise ExceptionStopParser("Процесс отменен пользователем.")

                    url = self._build_url(self.current_page)
                    catalog_page = self.load_catalog_page(page, url)

                    # ЗАЩИТА №2: Контроль редиректа пагинации сайта
                    current_url = catalog_page.url
                    if self.current_page > 1 and f"p={self.current_page}" not in current_url:
                        logger.info(f"🏁 Редирект на {current_url}. Каталог полностью пройден.")
                        break

                    # Получаем карточки товаров из DOM текущей страницы
                    product_cards = self.count_and_get_products_on_page(catalog_page)

                    # ЗАЩИТА №3: Проверка пустого DOM-дерева листинга
                    if not product_cards:
                        logger.info(f"🏁 На странице №{self.current_page} нет карточек. Останов.")
                        break

                    # Извлекаем пачку базовых данных и URL без открытия детальных вкладок товара
                    base_items = self.extractor.extract_data(product_cards)

                    # Поштучный конвейер обогащения характеристиками
                    total_in_batch = len(base_items)
                    for idx, item in enumerate(base_items, start=1):
                        # Обязательная проверка флага остановки ПЕРЕД каждым вложенным товаром
                        if not self._is_running:
                            raise ExceptionStopParser("Процесс отменен пользователем.")

                        product_url = item.get("url")
                        if not product_url or product_url == "https://goldapple.ru":
                            yield item
                            continue

                        # Открываем фоновую вкладку для ОДНОГО товара
                        detail_page = self.load_product_detail_page(context, product_url, item.get("item_id"))

                        deep_data = {
                            "description": "Описание отсутствует",
                            "usage": "Не указано",
                            "country_of_origin": "Не указана",
                        }

                        if detail_page:
                            try:
                                html_content = detail_page.content()
                                # Вызов функции извлечения детальных характеристик товара
                                deep_data = self.extractor.extract_deep_data(html_content)
                            except Exception as e:
                                logger.error(f"⚠️ Ошибка сбора PDP для товара {item.get('item_id')}: {e}")
                            finally:
                                detail_page.close()  # Гарантированно чистим ОЗУ

                        # Добавляем нужные характеристики
                        item.update(deep_data)

                        # Отдаем один готовый товар
                        yield item

                        # Имитируем поведение человека (пауза перед следующим товаром в пачке)
                        if idx < total_in_batch:
                            time.sleep(random.uniform(1.5, 3.0))

                    # Переходим к следующей странице каталога
                    self.current_page += 1

            except Exception as e:
                raise e