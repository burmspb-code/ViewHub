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

    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        """
        Постранично возвращает СПИСОК словарей (пакетный генератор).
        Идеально состыкован с универсальным ParserWorker PyQt6 и QThread.
        """
        # Инициализация Playwright внутри метода парсинга
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,  # Директория с профилем браузера
                headless=True,  # Полностью невидимый интерфейс в памяти
                args=[
                    "--disable-blink-features=AutomationControlled",  # МАСКИРОВОЧНЫЙ ФЛАГ
                    "--blink-settings=imagesEnabled=false",  # ОТКЛЮЧЕНИЕ КАРТИНОК НА УРОВНЕ ЯДРА CHROMIUM
                ],
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="ru-RU",
                timezone_id="Europe/Moscow",
            )

            page = context.new_page()

            try:
                while True:
                    # 1. ЗАЩИТА №1: Проверка пользовательского флага остановки из GUI PyQt6
                    if not self._is_running:
                        raise ExceptionStopParser("Процесс отменен пользователем.")

                    url = self._build_url(self.current_page)
                    catalog_page = self.load_catalog_page(page, url)

                    # 2. ЗАЩИТА №2: Контроль редиректа пагинации сайта "Золотое Яблоко"
                    current_url = catalog_page.url
                    if self.current_page > 1 and f"p={self.current_page}" not in current_url:
                        logger.info(
                            f"🏁 Обнаружен редирект пагинации сайта на {current_url}. Каталог полностью пройден."
                        )
                        break

                    # Получаем карточки текущей страницы из DOM-дерева
                    product_cards = self.count_and_get_products_on_page(catalog_page)

                    # 3. ЗАЩИТА №3: Проверка пустого листинга товаров
                    if not product_cards:
                        logger.info(f"🏁 На странице №{self.current_page} физически отсутствуют карточки. Останов.")
                        break

                    # ШАГ 1: Извлекаем пачку базовых данных и URL (Вызов отлаженного нами экстрактора с циклом)
                    base_items = self.extractor.extract_data(product_cards)

                    # Локальный массив для сбора полной обогащенной страницы
                    page_batch = []
                    total_in_batch = len(base_items)

                    # ШАГ 2: Внутренний конвейер глубокого сбора характеристик карточек (Описание, Применение, Страна)
                    for idx, item in enumerate(base_items, start=1):
                        # Проверяем кнопку "Стоп" перед каждым вложенным товаром, чтобы воркер реагировал мгновенно!
                        if not self._is_running:
                            raise ExceptionStopParser("Процесс отменен пользователем.")

                        product_url = item.get("url")
                        if not product_url or product_url == "https://goldapple.ru":
                            page_batch.append(item)
                            continue

                        # Открываем скрытую вкладку товара
                        detail_page = self.load_product_detail_page(context, product_url, item.get("item_id"))

                        deep_data = {
                            "description": "Описание отсутствует",
                            "usage": "Не указано",
                            "country_of_origin": "Не указана",
                        }

                        if detail_page:
                            try:
                                html_content = detail_page.content()
                                # Вызываем сбор полей из нашего обновленного экстрактора
                                deep_data = self.extractor.extract_deep_data(html_content)
                            except Exception as e:
                                logger.error(f"⚠️ Ошибка сбора характеристик для товара {item.get('item_id')}: {e}")
                            finally:
                                detail_page.close()  # Гарантированно освобождаем оперативную память

                        # Обогащаем базовые поля глубокими параметрами
                        item.update(deep_data)
                        page_batch.append(item)

                        # Имитируем хаотичную паузу человека между кликами по карточкам
                        if idx < total_in_batch:
                            import random

                            time.sleep(random.uniform(1.5, 3.0))

                    # Отдаем ЦЕЛУЮ страницу с товарами в воркер
                    yield page_batch

                    # Переходим к следующей странице каталога "Золотого Яблока"
                    self.current_page += 1

            except Exception as e:
                raise e