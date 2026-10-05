"""Класс парсинга для Сайта Золотое яблоко."""

import sys
import time
import logging
import re
import random
import typing

from pathlib import Path
from bs4 import BeautifulSoup
from typing import Any, List, Dict, Generator
from playwright.sync_api import sync_playwright

from src.core.base_classes import BaseParser, BaseDBParsingConfig, BaseExtractor
from src.database.sqlite_manager import DatabaseManager
from src.my_exceptions.exceptions import ExceptionStopParser


logger = logging.getLogger(__name__)

PARSER_DESCRIPTION = (
    "-" * 85 + "\n"
    "Парсер добавляет товары в БД из выбранных РАЗДЕЛОВ сайта.\n"
    "Введите ключевую фразу, например: 'parfjumerija/uniseks-aromaty'.\n"
    "Парсер НЕ ищет товары по запросу вида: 'крем' или 'помада'\n"
    "Экспорт данных из базы доступен в формате .xlsx или .csv.\n"
)


class GoldenAppleParser(BaseParser):
    """Парсинг Сайта Golden Apple."""

    def __init__(self, config: BaseDBParsingConfig, extractor: BaseExtractor, manager: DatabaseManager):
        super().__init__(config, extractor, manager)
        self.description = PARSER_DESCRIPTION
        # Номер текущей страницы, всегда начинаем с первой страницы
        self.current_page = 1
        # Счетчик пустых страниц подряд для надежной остановки
        self.empty_pages_count = 0
        # Создаем папку для профиля браузера:
        # Определяем корень проекта/папку с .exe в зависимости от режима запуска
        if getattr(sys, "frozen", False):
            # В PyInstaller используем директорию с exe файлом
            root_dir = Path(sys.executable).resolve().parent
        else:
            # Если в IDE запускается из корня через main, используем Path.cwd()
            root_dir = Path.cwd()

        # Создаем папку для профиля браузера в надежном месте
        self.user_data_dir = root_dir / "chrome_user_profile"
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        # Переводим в строку, так как Playwright ожидает именно строковый тип пути (str)
        self.user_data_dir = str(self.user_data_dir)

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
        Открытие фоновой вкладки товара.
        Терпеливо дожидается, пока лоадер сайта (дефис) не сменится реальным текстом товара.
        """

        page = None

        try:
            # Создаем чистую страницу в текущем изолированном контексте
            page = context.new_page()

            # Переходим на страницу товара с ограничением по времени (60 секунд)
            page.goto(product_url, wait_until="domcontentloaded", timeout=60000)

            # ЖЕСТКИЙ СТОПОР: Ждем появление главного заголовка страницы (название духов / бренд)
            # Задаем конечный таймаут в 60 секунд, чтобы поток не завис, если страница недоступна
            page.locator("h1").first.wait_for(state="attached", timeout=60000)

            # Небольшая контролируемая пауза для окончательного монтажа Vue-компонентов
            self._smart_sleep(1.0)

            return page

        except Exception as e:
            # Если пользователь нажал Отмена во время ожидания карточки, мгновенно выходим
            if not self._is_running:
                raise ExceptionStopParser("Процесс отменен пользователем.") from e
            logger.error(f"Ошибка. Не удалось дождаться загрузки карточки ID {product_id}: {e}")
            if page is not None:
                page.close()
            return None

    def load_catalog_page(self, page, url: str) -> Any:
        """Загрузка страницы каталога с защитой от Lazy-Render скрытого режима."""
        try:
            # Загружаем переданный URL
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Ждем прикрепления тега в DOM (attached)
            try:
                page.locator("article").first.wait_for(state="attached", timeout=60000)
            except Exception as e:
                first_line = str(e).splitlines()[0] if str(e) else "Unknown error"
                logger.debug(f"Загрузка тегов для товара не отвечает: {first_line}")

            # ЭМУЛЯЦИЯ СКРОЛЛА:
            page.evaluate("window.scrollTo(0, 2500);")
            self._smart_sleep(0.3)

            # Даем умный сон 3 секунды, чтобы сетка полностью стабилизировалась
            self._smart_sleep(3.0)

            return page

        except Exception as e:
            if not self._is_running:
                raise ExceptionStopParser("Процесс отменен пользователем.") from e
            logger.error(
                f"Ошибка. Не удалось прогрузить страницу каталога №{self.current_page}: {str(e).splitlines()[0]}"
            )
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
            logger.error(f"Ошибка. Не удалось определить количество товаров на странице №{self.current_page}: {e}")
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
        """Запуск основного цикла парсинга."""

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
                    "--no-sandbox",  # ОБЯЗАТЕЛЬНО ДЛЯ LINUX (под root)
                    "--disable-setuid-sandbox",  # ОБЯЗАТЕЛЬНО ДЛЯ LINUX (под root)
                    "--disable-dev-shm-usage",  # ОБЯЗАТЕЛЬНО ДЛЯ VPS (память в /dev/shm)
                    "--disable-gpu",  # ОБЯЗАТЕЛЬНО ДЛЯ СЕРВЕРА (нет видеокарты)
                ],
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                " AppleWebKit/537.36 (KHTML, like Gecko)"
                " Chrome/124.0.0.0 Safari/537.36",
                locale="ru-RU",
                timezone_id="Europe/Moscow",
            )

            # Очищаем куки и разрешения от предыдущего запуска
            context.clear_cookies()
            context.clear_permissions()

            page = context.new_page()

            # 1. БЛОКИРОВКА КАРТИНОК И ШРИФТОВ ДЛЯ СКОРОСТИ И ЭКОНОМИИ ОЗУ (ОСТАВЛЯЕМ)
            page.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in ["image", "font", "media", "image-set"]
                    else route.continue_()
                ),
            )

            # 2. АКТИВАЦИЯ ПОЛНОГО STEALTH-СЛЕПОК ЧЕРЕЗ БИБЛИОТЕКУ (ОСТАВЛЯЕМ)
            try:
                from playwright_stealth import stealth_sync

                stealth_sync(page)
                to_gui("🎭 Успешно сформирован новый уникальный слепок устройства.")
            except Exception as stealth_err:
                logger.debug(f"Ошибка активации stealth-маскировки: {stealth_err}")
            # ---------------------------------------------------------------

            try:
                while True:
                    if not self._is_running:
                        raise ExceptionStopParser("Процесс отменен пользователем.")

                    url = self._build_url(self.current_page)
                    to_gui(f"🌐 Загрузка страницы каталога №{self.current_page}...")

                    catalog_page = self.load_catalog_page(page, url)

                    # Получение карточек товара на странице
                    product_cards = self.count_and_get_products_on_page(catalog_page)

                    to_gui(f"🔎 Найдено {len(product_cards)} карточек. Сбор базовых данных...")

                    # Извлекаем карточки товаров
                    base_items = self.extractor.extract_data(product_cards)

                    # Инициализируем список товаров для детального просмотра (по умолчанию все)
                    new_base_items = base_items

                    # ----------------- Логика для остановки процесса пагинации ------------------------
                    # Собираем чистый список ID товаров с текущей страницы парсинга
                    item_id_list = [item.get("item_id") for item in base_items if item.get("item_id")]

                    # Страховочное условие остановки - получения 2 страниц подряд без товаров
                    if len(item_id_list) == 0:
                        # Увеличиваем счетчик пустых страниц
                        self.empty_pages_count += 1

                        if self.empty_pages_count >= 2:
                            to_gui(f"🏁 {self.empty_pages_count} пустые страницы подряд. Остановка парсера.")
                            break

                        continue

                    # Обнуляем счетчик пустых страниц
                    self.empty_pages_count = 0

                    # Делаем ОДИН запрос к БД и получаем словарь {id: page_number}
                    db_items_pages = self.manager.check_existing_items_with_pages(item_id_list)

                    # Считаем, сколько товаров с текущей страницы УЖЕ лежат в БД на СТАРЫХ страницах
                    old_duplicates_count = 0

                    for item_id in item_id_list:
                        string_id = str(item_id)

                        if string_id in db_items_pages:
                            # Если есть дубликаты, увеличиваем счетчик
                            old_duplicates_count += 1

                    to_gui(f"📊 Обнаружено дубликатов в базе: {old_duplicates_count} из {len(item_id_list)}")

                    # Если есть дубликаты
                    if old_duplicates_count:
                        # Собираем НЕзадублированнные товары
                        new_base_items = [item for item in base_items if str(item.get("item_id")) not in db_items_pages]

                    # Если на странице все товары уже есть в БД завершаем цикл
                    if len(item_id_list) == old_duplicates_count:
                        # --- Проверка на зацикливание парсинга ---
                        # Получаем максимальный номер страницы из БД
                        max_page_in_db = self.manager.get_last_page_number()

                        # Если текущий номер больше максимального - ЗАЦИКЛИВАНИЕ
                        if self.current_page > max_page_in_db:
                            to_gui("🏁 Зацикливание пагинации. Остановка. Все товары сохранены.")
                            break

                        self.current_page += 1
                        continue
                    # ------------------------------------------------------------------------------------

                    page_batch = []
                    total_in_batch = len(new_base_items)
                    saved_in_page = 0

                    to_gui(f"🚀 Запуск глубокого обхода {total_in_batch} карточек поштучно...")

                    for idx, item in enumerate(new_base_items, start=1):
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
                            self.manager.save([item])  # Передаем чистый список из одного товара
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
                        self.manager.save([item])  # Передаем чистый список из одного товара
                        saved_in_page += 1
                        # --------------------------------------

                        page_batch.append(item)

                        if idx < total_in_batch:
                            self._smart_sleep(random.uniform(1.5, 3.0))  # noqa: S311

                    # Отдаем пакет воркеру ТОЛЬКО для статистики
                    yield page_batch

                    to_gui(
                        f"🟢 Страница №{self.current_page} обработана.\n"
                        f"💾 Сохранено {saved_in_page} из {total_in_batch} товаров."
                    )

                    # Увеличиваем счетчик страницы ТОЛЬКО после полной обработки текущей
                    self.current_page += 1

            except ExceptionStopParser as e:
                raise e
            except Exception as e:
                raise e
            finally:
                # Корректная очистка ресурсов: сначала страница, потом контекст
                if "page" in locals() and not page.is_closed():
                    page.close()
                if "context" in locals():
                    context.close()
