"""Класс парсинга для Сайта Золотое яблоко."""

import time
import logging
import re
import random
import typing

from contextlib import suppress

from bs4 import BeautifulSoup
from typing import Any, List, Dict, Generator, Optional
from playwright.sync_api import sync_playwright

from src.core.base_classes import BaseParser, BaseDBParsingConfig, BaseExtractor
from src.core.paths import app_root, ensure_writable
from src.database.sqlite_manager import DatabaseManager
from src.my_exceptions.exceptions import ExceptionStopParser


logger = logging.getLogger(__name__)

PROCESS_CANCELLED_MSG = "Процесс отменен пользователем."

# Playwright выбрасывает эту ошибку, когда во время вычисления
# document.documentElement.outerHTML страница начинает новую навигацию и
# execution context уничтожается. Золотое Яблоко — SPA, который после
# domcontentloaded делает клиентский редирект/гидратацию, поэтому гонка
# стабильно воспроизводится и просто обязана быть пережита повтором.
NAVIGATION_RACE_MARKERS = (
    "navigating and changing the content",
    "Execution context was destroyed",
    "Target closed",
)

# Сколько раз пробуем снять HTML, прежде чем считать это реальной ошибкой.
CONTENT_READ_ATTEMPTS = 5
CONTENT_RETRY_PAUSE = 1.5

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
        # HTTP-статус последнего загруженного документа (None — запрос не дошёл).
        self._last_document_status: Optional[int] = None
        # Список неудачных сетевых запросов для диагностики.
        self._failed_requests: List[str] = []
        # Создаем папку для профиля браузера:
        # app_root() -> папка рядом с бинарником в frozen-режиме, корень проекта при разработке.
        # ensure_writable() страхует от read-only каталога на сервере: раньше mkdir
        # бросал PermissionError прямо во время парсинга.
        self.user_data_dir = str(ensure_writable(app_root() / "chrome_user_profile"))

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
                raise ExceptionStopParser(PROCESS_CANCELLED_MSG) from e
            logger.exception("Ошибка. Не удалось дождаться загрузки карточки ID %s", product_id)
            if page is not None:
                page.close()
            return None

    def _page_diagnostics(self, page) -> str:
        """
        Короткий слепок состояния страницы для диагностики.

        Раньше здесь стоял suppress на каждый вызов, из-за чего «вызов упал»
        и «страница пустая» выглядели в логе одинаково — именно поэтому в
        предыдущем логе title и текст были пустыми, а что произошло на самом
        деле, осталось неизвестным. Теперь каждая проверка помечена явно.
        """
        parts: List[str] = []

        parts.append(f"http_status={self._last_document_status if self._last_document_status else 'нет ответа'}")

        with suppress(Exception):
            parts.append(f"url={page.url}")

        try:
            title = page.title()
            parts.append(f"title={title!r}")
        except Exception as e:
            parts.append(f"title=ошибка({str(e).splitlines()[0]})")

        try:
            body_text = page.inner_text("body", timeout=5000)
            snippet = " ".join(body_text.split())[:200]
            parts.append(f"текст={snippet!r}" if snippet else "текст=СТРАНИЦА ПУСТАЯ")
        except Exception as e:
            # Именно этот случай был в прошлом логе: страница была занята навигацией.
            parts.append(f"текст=не удалось прочитать ({str(e).splitlines()[0]})")

        if self._failed_requests:
            parts.append(f"неудачные запросы ({len(self._failed_requests)}): {self._failed_requests[:3]}")

        return " | ".join(parts)

    def _detect_block_reason(self) -> Optional[str]:
        """
        Возвращает текст причины, если сайт явно заблокировал запрос.

        Пустая страница сама по себе ни о чём не говорит: одинаково выглядят
        403 от антибота, неудачный DNS и ошибка TLS. Здесь мы разделяем эти
        случаи, чтобы пользователь получил конкретное сообщение вместо
        падения через минуту ожидания.
        """
        status = self._last_document_status

        if status in (401, 403, 429):
            return (
                f"Сайт вернул HTTP {status} — запрос заблокирован защитой. "
                "Чаще всего это антибот по IP-адресу сервера."
            )

        if status is not None and status >= 500:
            return f"Сайт вернул HTTP {status} — проблема на стороне сайта, попробуйте позже."

        if status is None and self._failed_requests:
            return (
                "Главный документ не загрузился, сетевые ошибки: "
                + "; ".join(self._failed_requests[:3])
            )

        return None

    def _wait_for_challenge_to_pass(self, page, timeout_ms: int = 30000) -> bool:
        """
        Ждёт, пока антибот-челлендж разрешится.

        Признаки челленджа, замеченные на goldapple.ru:
          * HTTP 200, но тело — один UUID вроде '9b858593-3bcb-4bd0-8fcb-f9707aa1dcc0'
          * title вида 'Loading https://goldapple.ru/...'

        Такой странице нужен JS-редирект на настоящий каталог. Если просто ждать
        <article> 60 секунд, челлендж не успевает отработать и парсер объявляет
        «данные не обнаружены». Поэтому отдельно ждём либо появления карточек,
        либо смены заголовка — что наступит раньше.
        """
        deadline = time.time() + (timeout_ms / 1000)
        seen = False

        while time.time() < deadline:
            if not self._is_running:
                raise ExceptionStopParser(PROCESS_CANCELLED_MSG)

            # Карточки появились — челлендж пройден, идём дальше.
            try:
                if page.locator("article").count() > 0:
                    return True
            except Exception as count_err:
                # Не смогли проверить наличие карточек: скорее всего страница
                # переходит. Это не повод прерываться — ждём следующей итерации.
                logger.debug("Не удалось проверить наличие карточек: %s", count_err)

            # Заголовок читаем без try/except: если он не читается, значит страница
            # занята навигацией — это само по себе признак незавершённой проверки.
            try:
                title = page.title() or ""
            except Exception:
                title = ""

            is_loading_title = isinstance(title, str) and title.lower().startswith("loading")

            if is_loading_title:
                if not seen:
                    logger.info(
                        "Обнаружена страница проверки (антибот-челлендж): title=%r. "
                        "Ждём завершения проверки...",
                        title,
                    )
                    seen = True
            elif seen:
                # Заголовок сменился — проверка пройдена.
                logger.info("Проверка пройдена, заголовок страницы: %r", title)
                return True

            self._smart_sleep(1.0)

        return False

    def _stable_page_content(self, page, attempts: int = CONTENT_READ_ATTEMPTS) -> str:
        """
        Надёжно снимает HTML страницы, переживая гонку с навигацией.

        Playwright выполняет document.documentElement.outerHTML в utility-мире.
        Если в этот момент SPA инициирует новый переход (клиентский редирект,
        гидратация, смена роута), execution context уничтожается и page.content()
        падает с ошибкой:
            "Unable to retrieve content because the page is navigating and
             changing the content."

        Это не поломка парсера, а штатная гонка. Лечится повтором: ждём
        окончания навигации и пробуем снова.
        """
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            # Проверка отмены до каждой попытки, иначе отмена не сработает.
            if not self._is_running:
                raise ExceptionStopParser(PROCESS_CANCELLED_MSG)

            try:
                return page.content()
            except Exception as e:
                last_error = e
                error_text = str(e)

                is_race = any(marker in error_text for marker in NAVIGATION_RACE_MARKERS)
                if not is_race:
                    # Это уже не гонка — настоящая ошибка, повтор не поможет.
                    raise

                if attempt == attempts:
                    break

                logger.warning(
                    "Страница переходит в режиме навигации во время чтения HTML "
                    "(попытка %s/%s). Ждём стабилизации и пробуем снова.",
                    attempt,
                    attempts,
                )

                # Даём навигации завершиться: load_state не бросит исключение,
                # если состояние уже достигнуто, а ожидание синхронизирует нас
                # с движением страницы.
                with suppress(Exception):
                    page.wait_for_load_state("load", timeout=15000)

                self._smart_sleep(CONTENT_RETRY_PAUSE)

        raise RuntimeError(
            f"Не удалось прочитать HTML страницы после {attempts} попыток: {last_error}"
        ) from last_error

    def load_catalog_page(self, page, url: str) -> Any:
        """Загрузка страницы каталога с защитой от Lazy-Render скрытого режима."""
        try:
            # Загружаем переданный URL
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Дожидаемся полной загрузки. Без этого page.content() ниже нередко
            # попадает ровно в момент клиентского редиректа SPA и падает.
            with suppress(Exception):
                page.wait_for_load_state("load", timeout=30000)

            # Ждем прикрепления тега в DOM (attached)
            try:
                page.locator("article").first.wait_for(state="attached", timeout=60000)
            except Exception as e:
                first_line = str(e).splitlines()[0] if str(e) else "Unknown error"
                # Раньше здесь стоял logger.debug, из-за чего главная проблема
                # (каталог не отрендерился) была полностью невидима.
                logger.warning(
                    "Карточки товаров (<article>) не появились на странице каталога №%s: %s",
                    self.current_page,
                    first_line,
                )

                # Возможно, мы попали на антибот-челлендж и просто не дождались
                # его завершения — даём ему ещё один шанс перед вердиктом.
                if self._wait_for_challenge_to_pass(page):
                    logger.info(
                        "Каталог отрисован после прохождения проверки (страница №%s)", self.current_page
                    )
                else:
                    diagnostics = self._page_diagnostics(page)
                    logger.warning("Диагностика страницы: %s", diagnostics)

                    # Если сайт нас заблокировал или документ не дошёл — сообщаем
                    # об этом сразу и понятно, вместо падения позже с непонятной
                    # ошибкой в page.evaluate().
                    block_reason = self._detect_block_reason()
                    if block_reason:
                        raise ExceptionStopParser(block_reason) from e

            # ЭМУЛЯЦИЯ СКРОЛЛА:
            # Это вспомогательная операция для lazy-render. Раньше её исключение
            # ("Execution context was destroyed") обрывало весь парсинг,
            # хотя потеря скролла ничего критичного не означает.
            try:
                page.evaluate("window.scrollTo(0, 2500);")
            except Exception as scroll_err:
                logger.warning(
                    "Не удалось выполнить эмуляцию скролла (страница переходит): %s",
                    str(scroll_err).splitlines()[0],
                )
            self._smart_sleep(0.3)

            # Даем умный сон 3 секунды, чтобы сетка полностью стабилизировалась
            self._smart_sleep(3.0)

            return page

        except Exception as e:
            if not self._is_running:
                raise ExceptionStopParser(PROCESS_CANCELLED_MSG) from e
            logger.exception("Ошибка. Не удалось прогрузить страницу каталога №%s", self.current_page)
            raise e

    def count_and_get_products_on_page(self, page) -> Any:
        """
        Определение количества товаров на странице.
        Считывает HTML открытой вкладки и находит все контейнеры карточек товаров.
        """
        try:
            # Извлекаем текущий HTML из оперативной памяти вкладки
            html_content = self._stable_page_content(page)
            soup = BeautifulSoup(html_content, "html.parser")

            # Находим контейнеры карточек по логике тегов <article>
            cards = soup.find_all("article")

            return cards

        except Exception as e:
            logger.exception("Ошибка. Не удалось определить количество товаров на странице №%s", self.current_page)
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
                raise ExceptionStopParser(PROCESS_CANCELLED_MSG)
            time.sleep(0.1)

    def run_parsing(self) -> Generator[List[Dict[str, Any]], None, None]:
        """Запуск основного цикла парсинга."""

        def to_gui(msg: str):
            callback = getattr(self, "progress_callback", None)
            if callback is not None and callable(callback):
                typing.cast(typing.Callable[[str], None], callback)(msg)

        to_gui("=== ЗАПУСК СКРЫТОГО КОНВЕЙЕРА ПАРСИНГА ===")

        with sync_playwright() as p:
            # 1. ЗАПУСК БРАУЗЕРА
            #
            # channel="chromium" принципиален: без него Playwright в headless
            # использует chromium-headless-shell, который в User-Agent отдаёт
            # "HeadlessChrome" — самый заметный признак автоматизации.
            # С обычным Chromium включается новый headless-режим, и браузер
            # называется настоящей версией.
            #
            # Раньше здесь был зашит user_agent с "Chrome/124.0.0.0", тогда как
            # встроенный в Playwright Chromium — 153.x. Разрыв в 29 версий
            # виден любой антибот-системе, из-за чего сайт отдавал пустую
            # страницу и не рендерил каталог.
            launch_kwargs = dict(
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
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                # locale выставлен выше, поэтому заголовок должен ему соответствовать,
                # иначе это ещё одно расхождение в отпечатке.
                extra_http_headers={"Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"},
            )

            try:
                context = p.chromium.launch_persistent_context(channel="chromium", **launch_kwargs)
            except Exception as channel_err:
                # Канал chromium иногда отсутствует при нестандартной сборке.
                logger.warning(
                    "Не удалось запустить Chromium с каналом 'chromium' (%s). Пробуем обычный "
                    "headless-запуск — в UA будет HeadlessChrome.",
                    str(channel_err).splitlines()[0],
                )
                context = p.chromium.launch_persistent_context(**launch_kwargs)

            # Очищаем куки и разрешения от предыдущего запуска
            context.clear_cookies()
            context.clear_permissions()

            # 2. STEALTH ПРИМЕНЯЕМ К КОНТЕКСТУ, А НЕ К ОДНОЙ СТРАНИЦЕ.
            #
            # add_init_script действует только на ту страницу, к которой применён,
            # и на страницы, созданные из того же контекста ПОСЛЕ этого.
            # Карточки товаров открываются через context.new_page() уже во время
            # обхода, поэтому раньше stealth к ним не применялся вовсе.
            #
            # Ошибку здесь поднимаем до ERROR и показываем в GUI: без маскировки
            # navigator.webdriver == true, сайт отдаёт антибот-челлендж, и парсер
            # выглядит «зависшим». Молча продолжать работу без маскировки нельзя —
            # это ровно тот случай, который стоит догадываться часами.
            try:
                from playwright_stealth import stealth_sync

                stealth_sync(context)
                to_gui("🎭 Успешно сформирован новый уникальный слепок устройства.")
            except Exception as stealth_err:
                message = f"Не удалось включить stealth-маскировку: {stealth_err}"
                logger.error(message)
                to_gui(f"⚠️ {message}")
                logger.error(
                    "Без маскировки парсер почти наверняка будет заблокирован сайтом. "
                    "Проверьте, что в сборку попала папка playwright_stealth/js."
                )

            # 3. БЛОКИРОВКА КАРТИНОК И ШРИФТОВ — тоже на уровне контекста,
            #    чтобы действовала и на страницах карточек товаров.
            context.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in ["image", "font", "media", "image-set"]
                    else route.continue_()
                ),
            )

            # 4. ДИАГНОСТИКА СЕТИ: запоминаем HTTP-статус главного документа и
            #    неудачные запросы. Без этого пустую страницу невозможно отличить
            #    от блокировки антиботом — а это разные проблемы с разным решением.
            self._last_document_status = None
            self._failed_requests = []

            def _on_response(response) -> None:
                if response.request.resource_type == "document":
                    self._last_document_status = response.status

            def _on_request_failed(request) -> None:
                # Интересуют только первые несколько, чтобы лог не разрастался
                if len(self._failed_requests) < 10:
                    self._failed_requests.append(
                        f"{request.resource_type} {request.url} :: {request.failure}"
                    )

            context.on("response", _on_response)
            context.on("requestfailed", _on_request_failed)

            page = context.new_page()
            # ---------------------------------------------------------------

            try:
                while True:
                    if not self._is_running:
                        raise ExceptionStopParser(PROCESS_CANCELLED_MSG)

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
                            raise ExceptionStopParser(PROCESS_CANCELLED_MSG)

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
                                html_content = self._stable_page_content(detail_page)
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

            finally:
                # Корректная очистка ресурсов: сначала страница, потом контекст
                if "page" in locals() and not page.is_closed():
                    page.close()
                if "context" in locals():
                    context.close()
