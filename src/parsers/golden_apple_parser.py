"""Класс парсинга для Сайта Золотое яблоко."""

import os
import sys
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
from src.core.logger import reset_log_file
from src.core.paths import app_root, ensure_writable, resolve_playwright_browsers_path
from src.database.sqlite_manager import DatabaseManager
from src.my_exceptions.exceptions import ExceptionStopParser

# Запасное имя папки с упакованным браузером. Основное значение объявлено в
# конфигурации парсера — GoldenAppleConfig.BROWSERS_DIR_NAME. Этот вариант
# нужен только на случай подмены конфигурации заглушкой в тестах.
BROWSERS_DIR_NAME_FALLBACK = "pw-browsers"


logger = logging.getLogger(__name__)

PROCESS_CANCELLED_MSG = "Процесс отменен пользователем."
UNKNOWN_ERROR_MSG = "Unknown error"

# Сколько позиций из списка незагруженных товаров показывать в панели вывода.
# Ограничение нужно, чтобы отчёт на сотни товаров не утопил всё остальное:
# остальные позиции остаются в logs/viewhub.log.
MAX_SKIPPED_REPORT_LINES = 15

# Сколько страниц подряд должны вернуть ОДИНАКОВЫЙ набор товаров, чтобы
# парсер признал это обманкой, а не концом каталога.
#
# Единица означала бы слишком строгое поведение: сайт может один раз
# отдать ту же страницу из-за кэша или редиректа, и парсер остановился бы
# на ровном месте. Две подряд — уже систематическое поведение.
REPEATED_PAGE_LIMIT = 2

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

# Запасной User-Agent для режима без отрисовки.
#
# Основное значение хранится в конфигурации парсера —
# GoldenAppleConfig.HEADLESS_USER_AGENT, а не здесь. Эта подмена относится
# ТОЛЬКО к Золотому Яблоку: к CitadelParser и GardarikaParser она отношения
# не имеет. Запасной вариант нужен лишь на случай подмены конфигурации
# заглушкой в тестах.
HEADLESS_USER_AGENT_FALLBACK = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

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

        # Лог обнуляется на клике кнопки «ПАРСИНГ», потому что только там
        # создаётся новый парсер. Все запуски внутри одного сеанса дописывают
        # в тот же файл — так разбираться с логом разработчику проще.
        reset_log_file()

        # Начальные значения состояния. Реальный сброс выполняется в начале
        # run_parsing(): объект парсера переиспользуется между нажатиями
        # «НАЧАТЬ», поэтому начать прогон нужно с чистого состояния.
        self.current_page = 1
        self.empty_pages_count = 0
        # HTTP-статус последнего загруженного документа (None — запрос не дошёл).
        self._last_document_status: Optional[int] = None
        # Список неудачных сетевых запросов для диагностики.
        self._failed_requests: List[str] = []
        # Товары текущего прогона, у которых не удалось снять детальные данные.
        # В основной таблице они лежат с заглушками, поэтому сбой парсера
        # невозможно отличить от пустого описания на сайте. Этот словарь
        # отделяет одно от другого и показывается пользователю в конце прогона.
        self._skipped_rows: List[Dict[str, Any]] = []

        # Слепок предыдущей страницы каталога и число страниц подряд с тем же
        # набором товаров. Нужны, чтобы отличить конец каталога от ситуации,
        # когда сервер отдаёт одну и ту же страницу вместо запрошенной.
        self._last_page_fingerprint: Optional[tuple] = None
        self._same_page_streak: int = 0
        # Слепок ПЕРВОЙ страницы раздела: по нему определяется, что повторяется
        # именно начало каталога — типичный признак антибот-заглушки.
        self._first_page_fingerprint: Optional[tuple] = None

        # Активный режим отрисовки фиксируем ЗДЕСЬ, а не только в run_parsing().
        # Раньше режим выводился в лог исключительно из run_parsing(), а это
        # генератор, который запускается только по кнопке «НАЧАТЬ». Из-за этого
        # проверить применение переменной окружения до старта парсинга было
        # невозможно — в логе просто не было строк. Теперь режим виден сразу
        # при создании парсера, то есть сразу после открытия раздела «ПАРСИНГ».
        logger.info(
            "Режим отрисовки (при создании парсера): %s",
            "headless" if self._resolve_headless() else "обычный браузер",
        )
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
            # Причина фиксируется ДО логирования: в список попадёт конкретный
            # текст ("таймаут ожидания заголовка", "HTTP 403"), а не общее
            # "не удалось загрузить".
            #
            # Уровень WARNING, а не EXCEPTION: трейлбек Playwright на каждый
            # товар не нужен ни в журнале, ни в файле лога — по коду видно,
            # что это штатная обработка таймаута, а не авария.
            reason = self._describe_load_failure(e)
            logger.warning("Не удалось загрузить карточку ID %s. Причина: %s", product_id, reason)

            if page is not None:
                with suppress(Exception):
                    page.close()

            return None

    def _flush_skipped(self, to_gui) -> None:
        """
        Показывает пользователю итоговый список товаров без детальных данных.

        Вызывается в finally, поэтому отчёт формируется и при штатном завершении,
        и при остановке по кнопке, и при аварии.

        Список целиком не выводится, если товаров много: панель вывода
        захлебнётся строками, и полезная информация окажется за пределами
        видимой области. В этом случае показывается число и первые позиции.

        Список очищается ПОСЛЕ отчёта и намеренно не копится между прогонами.
        Отчёт — это сигнал к решению: пользователь сразу решает, запускать ли
        раздел заново. Копить незачем, тем более что следующий прогон всё
        равно начинается с первой страницы и пройдёт по тем же товарам заново.
        """
        # Дедупликация по item_id: из-за перетусовки каталога прямо во время
        # обхода один товар может встретиться на нескольких страницах, и без
        # этого отчёт показал бы его дважды с разными номерами страниц.
        unique: Dict[str, Dict[str, Any]] = {}
        for row in self._skipped_rows:
            unique.setdefault(row["item_id"], row)

        self._skipped_rows.clear()
        rows = list(unique.values())

        if not rows:
            return

        total = len(rows)
        logger.info("Товаров без детальных данных за прогон: %s", total)

        # В файл лога пишем весь список: панель вывода показывает только первые
        # позиции, а разбираться по логу придётся уже после парсинга.
        for row in rows:
            logger.warning(
                "Товар без характеристик: ID=%s, бренд=%s, название=%s, страница=%s, причина=%s, ссылка=%s",
                row["item_id"],
                row["brand"],
                row["name"],
                row["page_number"],
                row["reason"],
                row["url"],
            )

        to_gui("")
        to_gui(f"⚠️ НЕ ЗАГРУЖЕНЫ ХАРАКТЕРИСТИКИ: {total} шт.")
        to_gui("Товар сохранился в базе, но вместо описания — заглушка. Проверьте вручную:")

        shown = rows[:MAX_SKIPPED_REPORT_LINES]
        for row in shown:
            to_gui(f"   • {row['item_id']} — {row['brand'] or '?'} / {row['name'] or '?'}")
            to_gui(f"     {row['url']}")
            to_gui(f"     причина: {row['reason']}")

        if total > len(shown):
            to_gui(f"   … и ещё {total - len(shown)}. Полный список — в logs/viewhub.log.")

    def _register_skipped(self, item: Dict[str, Any], reason: str) -> None:
        """
        Запоминает товар, у которого не снялись детальные характеристики.

        В основной таблице такой товар сохраняется с заглушками
        ("Описание отсутствует"), и по базе нельзя понять, был ли это сбой
        парсера или сайт действительно не публикует описание. Учёт решает это:
        сбой всегда попадает сюда, пустое описание на сайте — никогда.

        Список живёт только в памяти и показывается пользователю в конце
        прогона. Отдельная таблица в базе для этого не заводилась.
        """
        self._skipped_rows.append(
            {
                "item_id": str(item.get("item_id") or "").strip(),
                "url": item.get("url") or "",
                "brand": item.get("brand"),
                "name": item.get("name"),
                "page_number": self.current_page,
                "reason": reason,
            }
        )

    def _page_fingerprint(self, item_ids: List[str]) -> tuple:
        """
        Слепок страницы каталога: отсортированный кортеж артикулов.

        Порядок отображения карточек меняется при каждом рендере SPA, поэтому
        сравнивать его бессмысленно — два одинаковых набора в разном порядке
        дали бы ложное «страницы разные». Цены тоже не берутся: они могут
        обновиться между двумя загрузками одной и той же страницы.

        Артикулы же неизменны: это бизнес-ключ товара.
        """
        return tuple(sorted(item_ids))

    def _track_page_fingerprint(self, item_ids: List[str]) -> None:
        """
        Обновляет слепок текущей страницы и счётчик подряд идущих повторов.

        Счётчик считается по ВСЕМ страницам, включая те, что дали новые товары:
        при антиботе первая страница настоящая, а обманка начинается со второй,
        и без общего счёта мы бы пропустили самый частый случай — пустую базу.
        """
        fingerprint = self._page_fingerprint(item_ids)

        if fingerprint == self._last_page_fingerprint:
            self._same_page_streak += 1
        else:
            self._same_page_streak = 1
            self._last_page_fingerprint = fingerprint

        if self._first_page_fingerprint is None:
            self._first_page_fingerprint = fingerprint

    def _repeated_page_reason(self) -> str:
        """
        Текст причины остановки, когда сервер отдаёт одну и ту же страницу.

        Отличие от проверки в _track_page_fingerprint — смотрим не только на сам
        факт повтора, но и на то, какая именно страница повторилась:
        так антибот-заглушка отличается от сокращения каталога.
        """
        if self._last_page_fingerprint == self._first_page_fingerprint:
            return (
                f"Сайт {self._same_page_streak} раз подряд вернул одну и ту же страницу "
                f"(на запрос №{self.current_page} отдаёт страницу №1). Скорее всего, "
                f"сработала защита от роботов: нужен другой IP-адрес или residential-прокси."
            )

        return (
            f"Сайт {self._same_page_streak} раз подряд вернул одну и ту же страницу. "
            f"Парсер остановился на странице №{self.current_page}: номера страниц на сайте "
            f"перестали соответствовать запрошенным. Возможно, товаров на сайте стало меньше, "
            f"чем собрано ранее."
        )

    def _describe_load_failure(self, error: Exception) -> str:
        """Короткое описание причины, по которой карточка не открылась.

        HTTP-статус берётся из self._last_document_status: он уже собран
        обработчиком response на контексте, поэтому обращаться к умирающей
        вкладке page не нужно.
        """
        error_text = str(error)
        lowered = error_text.lower()

        if "timeout" in lowered or "exceeded" in lowered:
            reason = "таймаут ожидания заголовка карточки (60 с)"
        else:
            reason = (error_text.splitlines() or [UNKNOWN_ERROR_MSG])[0][:160]

        status = self._last_document_status
        if status:
            reason += f", HTTP {status}"

        return reason

    def _page_diagnostics(self, page) -> str:
        """
        Короткий слепок состояния страницы для диагностики.
        """
        # 1. Статус ответа
        status_val = self._last_document_status if self._last_document_status else 'нет ответа'
        status_part = f"http_status={status_val}"

        # 2. URL страницы
        if page:
            url_part = f"url={page.url}"
        else:
            url_part = "url=неизвестен"

        # 3. Заголовок (Title)
        try:
            title = page.title()
            title_part = f"title={title!r}"
        except Exception as e:
            first_line = str(e).splitlines()[0] if str(e) else UNKNOWN_ERROR_MSG
            title_part = f"title=ошибка({first_line})"

        # 4. Текст страницы (Snippet)
        try:
            body_text = page.inner_text("body", timeout=5000)
            snippet = " ".join(body_text.split())[:200]
            text_part = f"текст={snippet!r}" if snippet else "текст=СТРАНИЦА ПУСТАЯ"
        except Exception as e:
            first_line = str(e).splitlines()[0] if str(e) else UNKNOWN_ERROR_MSG
            text_part = f"текст=не удалось прочитать ({first_line})"

        # 5. Инициализируем список в один шаг (Литерал списка)
        parts: list[str] = [
            status_part,
            url_part,
            title_part,
            text_part,
        ]

        # 6. Добавляем информацию о неудачных запросах, если они есть
        if self._failed_requests:
            failed_part = f"неудачные запросы ({len(self._failed_requests)}): {self._failed_requests[:3]}"
            parts.append(failed_part)

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
                f"Сайт вернул HTTP {status} — запрос заблокирован защитой. Чаще всего это антибот по IP-адресу сервера."
            )

        if status is not None and status >= 500:
            return f"Сайт вернул HTTP {status} — проблема на стороне сайта, попробуйте позже."

        if status is None and self._failed_requests:
            return "Главный документ не загрузился, сетевые ошибки: " + "; ".join(self._failed_requests[:3])

        return None

    def _apply_browsers_path(self) -> None:
        """
        Определяет каталог с Chromium и выставляет PLAYWRIGHT_BROWSERS_PATH.
        Вызывается в момент запуска парсинга.
        """
        browsers_dir = self._cfg_str("BROWSERS_DIR_NAME", BROWSERS_DIR_NAME_FALLBACK)
        resolved = resolve_playwright_browsers_path(browsers_dir)

        if resolved is None:
            logger.warning(
                "Каталог браузеров Playwright не найден (проверялась папка %r). "
                "Установите Chromium на сервер: python -m playwright install chromium. "
                "Парсер попытается продолжить со штатным путём Playwright.",
                browsers_dir,
            )
            return

        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(resolved)
        logger.info("Каталог браузеров Playwright: %s", resolved)

    def _cfg_str(self, name: str, default: str) -> str:
        """
        Читает строковую настройку из конфигурации парсера.

        Проверка isinstance обязательна: в тестах конфигурация подменяется
        MagicMock, и getattr вернул бы объект-заглушку вместо строки.
        """
        value = getattr(self.config, name, None)
        return value if isinstance(value, str) and value else default

    def _cfg_bool(self, name: str, default: bool) -> bool:
        """Читает булеву настройку из конфигурации парсера."""
        value = getattr(self.config, name, None)
        return value if isinstance(value, bool) else default

    def _resolve_headless(self) -> bool:
        """
        Определяет режим отрисовки браузера.

        Значение задаётся константой GoldenAppleConfig.DEFAULT_HEADLESS.
        Переопределения через переменные окружения и .env намеренно нет:
        заказчик работает через графический интерфейс и не настраивает парсер.
        На этапе разработки такая возможность была нужна, чтобы перебирать
        режимы экспериментально без пересборки программы.

        Выбран headless: он проверен на Windows и Linux, проходит антибот-
        проверку, заметно экономнее по ресурсам и не требует ни X-сервера,
        ни виртуального дисплея.
        """
        return self._cfg_bool("DEFAULT_HEADLESS", True)

    def _wait_for_challenge_to_pass(self, page, timeout_ms: int = 45000) -> bool:
        """
        Ждёт, пока антибот-проверка завершится.

        Признаки проверки на goldapple.ru:
          * HTTP 200, но тело — один UUID вроде '9b858593-3bcb-4bd0-8fcb-f9707aa1dcc0'
          * title: 'Loading https://goldapple.ru/...', затем 'Gold Apple — checking device'

        ВАЖНО: 'checking device' — это всё ещё ПРОВЕРКА, а не каталог.
        Раньше любая смена заголовка считалась успехом, из-за чего парсер
        тратил по 60 секунд на каждую попытку и рапортовал «проверка пройдена»,
        хотя каталог так и не появился.

        Успех — только появление карточек <article>. Если проверка завершилась
        ошибкой, она остаётся на этой странице и ждать бессмысленно.
        """
        deadline = time.time() + (timeout_ms / 1000)
        reported = False

        while time.time() < deadline:
            if not self._is_running:
                raise ExceptionStopParser(PROCESS_CANCELLED_MSG)

            # Успех есть только один: появились реальные карточки товаров.
            try:
                if page.locator("article").count() > 0:
                    if reported:
                        logger.info("Проверка пройдена, каталог отрисован.")
                    return True
            except Exception as count_err:
                # Скорее всего страница переходит — ждём следующей итерации.
                logger.debug("Не удалось проверить наличие карточек: %s", count_err)

            try:
                title = page.title() or ""
            except Exception as e:
                logger.debug("Ошибка определения заголовка: %s", e)
                title = ""

            if not isinstance(title, str):
                title = ""

            if not reported:
                logger.info(
                    "Обнаружена страница проверки (антибот): title=%r. Ждём завершения...",
                    title,
                )
                reported = True

            self._smart_sleep(1.0)

        # Проверка не завершилась за отведённое время. Сообщаем, на чём остановились:
        # если заголовок всё ещё про проверку, антибот нас не пустил.
        try:
            final_title = page.title() or ""
        except Exception as e:
            logger.debug("Ошибка определения заголовка: %s", e)
            final_title = ""

        if "checking device" in final_title.lower():
            logger.warning(
                "Антибот-проверка не завершилась: устройство не прошло проверку "
                "(title=%r). Каталог недоступен с этого IP.",
                final_title,
            )
        else:
            logger.warning(
                "Каталог не отрисовался за %s мс. Итоговый заголовок: %r",
                timeout_ms // 1000,
                final_title,
            )

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

        raise RuntimeError(f"Не удалось прочитать HTML страницы после {attempts} попыток: {last_error}") from last_error

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
            except Exception as err:
                first_line = str(err).splitlines()[0] if str(err) else UNKNOWN_ERROR_MSG
                # Раньше здесь стоял logger.debug, из-за чего главная проблема
                # (каталог не отрендерился) была полностью невидима.
                logger.warning(
                    "Карточки товаров (<article>) не появились на странице каталога №%s: %s",
                    self.current_page,
                    first_line,
                )

                # Возможно, мы попали на антибот-проверку и просто не дождались
                # её завершения — даём ей ещё один шанс перед вердиктом.
                if self._wait_for_challenge_to_pass(page):
                    logger.info("Каталог отрисован после прохождения проверки (страница №%s)", self.current_page)
                else:
                    diagnostics = self._page_diagnostics(page)
                    logger.warning("Диагностика страницы: %s", diagnostics)

                    block_reason = self._detect_block_reason()
                    if block_reason:
                        raise ExceptionStopParser(block_reason) from err

                    # Проверка устройства не завершилась — дальше ждать бессмысленно,
                    # каждая страница каталога будет упираться в тот же антибот.
                    # Останавливаемся сразу, вместо ~2 минут бесполезного ожидания.
                    try:
                        final_title = (page.title() or "").lower()
                    except Exception as e:
                        logger.debug("Ошибка создания заголовка: %s", e)
                        final_title = ""

                    if "checking device" in final_title:
                        raise ExceptionStopParser(
                            "Антибот не пускает: проверка устройства не пройдена. "
                            "Нужен другой IP-адрес или residential-прокси."
                        ) from err

            # ЭМУЛЯЦИЯ СКРОЛЛА:
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
            # Для ExceptionStopParser уже была выведена понятная причина
            # (например, отказ антибот-проверки). Трейсбек Playwright с
            # TimeoutError ничего не добавляет и только засоряет лог.
            if isinstance(e, ExceptionStopParser):
                logger.warning(
                    "Загрузка страницы каталога №%s прекращена: %s", self.current_page, str(e).splitlines()[0]
                )
            else:
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

        # Состояние запуска обнуляется ЗДЕСЬ, а не в __init__. Раньше счётчики
        # создавались один раз, поэтому после отработки раздела на 26 страницах
        # следующий запуск с другой ссылкой продолжал со страницы 26 и сразу
        # выдавал ложное «зацикливание пагинации».
        #
        # Перезапуск всегда с первой страницы: возобновления с места остановки
        # нет намеренно. Между прогонами каталог мог перетушоваться (новинки
        # уходят в начало), и продолжение со старой страницы молча потеряло бы
        # новые товары. Цена решения — повторный проход по уже собранным
        # страницам, но это дешёво: глубокий обход карточек делается только
        # для новых товаров, дубликаты отсекаются одним SQL-запросом.
        #
        # _is_running сбрасывается потому, что cancel() выставляет его в False
        # навсегда: без этой строки повторный запуск после отмены мгновенно
        # падал бы с «Процесс отменен пользователем».
        self._is_running = True
        self.current_page = 1
        self.empty_pages_count = 0
        self._skipped_rows.clear()
        self._last_page_fingerprint = None
        self._same_page_streak = 0
        self._first_page_fingerprint = None

        to_gui("=== ЗАПУСК СКРЫТОГО КОНВЕЙЕРА ПАРСИНГА ===")

        # Путь к браузеру разрешается ЗДЕСЬ, а не при старте приложения.
        # Браузер нужен только этому парсеру: парсеры, работающие через API,
        # ничего подобного не делают и не должны зависеть от наличия Chromium.
        self._apply_browsers_path()

        with sync_playwright() as p:
            # 1. ЗАПУСК БРАУЗЕРА
            #
            # channel="chromium" принципиален: без него Playwright в headless
            # использует chromium-headless-shell, который в User-Agent отдаёт
            # "HeadlessChrome" — самый заметный признак автоматизации.
            # С обычным Chromium включается новый headless-режим, и браузер
            # называется настоящей версией.
            #
            # РАНЬШЕЙ ВЕРСИИ БЫЛА ОШИБКА: здесь стоял зашитый user_agent с
            # "Chrome/124.0.0.0", и я счёл его устаревшим расхождением и убрал.
            # На самом деле подмена обязательна для headless-режима: с
            # настоящим Chrome/153 сайт отдаёт отказ, с Chrome/124 — пропускает.
            # См. константу HEADLESS_USER_AGENT и комментарий ниже.
            #
            # РЕЖИМ ОТРИСОВКИ задаётся константой GoldenAppleConfig.DEFAULT_HEADLESS.
            # Переопределения через окружение нет: настройка нужна была только
            # при разработке, заказчик работает через графический интерфейс.
            headless_mode = self._resolve_headless()
            logger.info("Режим отрисовки: %s", "headless" if headless_mode else "обычный браузер")
            if headless_mode:
                logger.info("Отпечаток headless: User-Agent=Chrome/124, WebGL отключён (--disable-gpu).")

            launch_args = [
                "--disable-blink-features=AutomationControlled",
                # ЭКОНОМИЯ РЕСУРСОВ. Эти флаги не трогают WebGL и не меняют
                # отпечаток устройства — они лишь отключают то, что парсеру
                # всё равно не нужно для сбора HTML.
                "--blink-settings=imagesEnabled=false",  # картинки не декодируются
                "--blink-settings=cssAnimations=false",  # анимации CSS
                "--disable-renderer-backgrounding=false",  # не мешаем рендеру
                "--force-prefers-reduced-motion",  # сайт меньше анимирует
            ]

            if self._cfg_bool("HEADLESS_DISABLE_GPU", True) and headless_mode:
                launch_args.append("--disable-gpu")

            launch_kwargs: dict = {
                "user_data_dir": self.user_data_dir,
                "headless": headless_mode,
                "args": launch_args,
                "viewport": {"width": 1366, "height": 768},
                "locale": "ru-RU",
                "timezone_id": "Europe/Moscow",
                # locale выставлен выше, поэтому заголовок должен ему соответствовать,
                # иначе это ещё одно расхождение в отпечатке.
                "extra_http_headers": {"Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"},
            }

            # Подмена User-Agent обязательна в режиме без отрисовки —
            # проверено экспериментом на Windows и Linux.
            if headless_mode:
                launch_kwargs["user_agent"] = self._cfg_str("HEADLESS_USER_AGENT", HEADLESS_USER_AGENT_FALLBACK)
                logger.info("User-Agent подменён на Chrome/124 — требуется для headless.")

            # Флаги, нужные ТОЛЬКО на Linux. На Windows они бессмысленны,
            if sys.platform.startswith("linux"):
                launch_kwargs["args"] += [
                    "--no-sandbox",  # обязательно при запуске под root
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",  # на VPS /dev/shm ограничен
                ]

            if headless_mode:
                to_gui("🖥 Headless-режим: графическое окружение не требуется.")
            else:
                logger.warning(
                    "Включён обычный режим браузера с отрисовкой: он расходует больше "
                    "ресурсов. Рекомендуемый режим без отрисовки задан константой "
                    "GoldenAppleConfig.DEFAULT_HEADLESS."
                )
                to_gui("🖥 Обычный режим браузера с отрисовкой.")

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
                # В playwright_stealth 2.x функции stealth_sync/stealth_async
                # БОЛЬШЕ НЕТ: __init__.py экспортирует только Stealth и
                # ALL_EVASIONS_DISABLED_KWARGS. Старый код делал
                #     from playwright_stealth import stealth_sync
                # что всегда падало с ImportError, а try/except это скрывал —
                # маскировка не работала НИКОГДА, ни в исходниках, ни в сборке.
                # Правильный вызов для sync API — Stealth().apply_stealth_sync().
                #
                # ВАЖНО ДЛЯ ЭКСПЕРИМЕНТА: в исходной рабочей конфигурации
                # маскировка не работала, и сайт всё равно пропускал. Возможно,
                # подмены playwright_stealth (userAgentData, sec-ch-ua, WebGL)
                # противоречат настоящей версии браузера и делают хуже.
                from playwright_stealth import Stealth

                Stealth().apply_stealth_sync(context)
                to_gui("🎭 Успешно сформирован новый уникальный слепок устройства.")
            except Exception as stealth_err:
                message = f"Не удалось включить stealth-маскировку: {stealth_err}"
                logger.error(message)
                to_gui(f"⚠️ {message}")
                logger.error(
                    "Без маскировки парсер почти наверняка будет заблокирован сайтом. "
                    "Проверьте, что в сборку попала папка playwright_stealth/js."
                )

            # 3. БЛОКИРОВКА ТЯЖЁЛЫХ РЕСУРСОВ — главный рычаг экономии на слабом VPS.
            #
            #    Парсеру нужны только HTML, JSON и CSS. Всё остальное — это чистая
            #    нагрузка на CPU/RAM: картинки, видео, шрифты, аналитика, счётчики.
            #    На графическом VPS именно они обычно и съедают ресурсы.
            #
            #    ВАЖНО: script и stylesheet НЕ блокируются. Антибот-проверка
            #    исполняет их, и без них страница остаётся на 'checking device'.
            blocked_resource_types = {
                "image",
                "image-set",
                "media",
                "font",
                "imageset",
            }

            # Домены аналитики и счётчиков: не нужны для сбора данных.
            blocked_url_markers = (
                "googletagmanager",
                "google-analytics",
                "analytics",
                "facebook.net",
                "mc.yandex",
                "top-fwz1",
                "vk.com/rtrg",
                "criteo",
                "hotjar",
                "sentry",
                "amplitude",
                "matomo",
            )

            def _handle_route(route) -> None:
                request = route.request

                if request.resource_type in blocked_resource_types:
                    route.abort()
                    return

                request_url = request.url.lower()
                if any(marker in request_url for marker in blocked_url_markers):
                    route.abort()
                    return

                route.continue_()

            # Блокировка вешается на контекст, поэтому работает и для страниц
            # карточек товаров, которые создаются через context.new_page().
            context.route("**/*", _handle_route)

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
                    self._failed_requests.append(f"{request.resource_type} {request.url} :: {request.failure}")

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

                    # Слепок страницы считаем ВСЕГДА, до запроса к БД. Само
                    # сравнение делается ниже, в ветке полных дубликатов: там
                    # уже известно, что страница не дала ничего нового, и можно
                    # отличить антибот-заглушку от честного конца каталога.
                    self._track_page_fingerprint(item_id_list)

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
                        max_page_in_db = self.manager.get_last_page_number()
                        repeated = self._same_page_streak >= REPEATED_PAGE_LIMIT

                        # ПОРЯДОК ПРОВЕРОК ЗДЕСЬ СУЩЕСТВЕН.
                        #
                        # 1. Повтор слепка ПЕРВОЙ страницы — всегда обманка.
                        #    Сервер отдаёт начало каталога вместо запрошенной
                        #    страницы, и никакое сравнение номеров это не поймает.
                        #    Особенно важно при небольшой базе: если в базе всего
                        #    одна страница, проверка «номер больше максимума»
                        #    сработала бы раньше и объявила конец каталога, хотя
                        #    на сайте их пять.
                        if repeated and self._last_page_fingerprint == self._first_page_fingerprint:
                            to_gui(f"🛑 {self._repeated_page_reason()}")
                            logger.warning("Остановка парсинга: %s", self._repeated_page_reason())
                            break

                        # 2. Мы обошли все страницы, записанные в базу, и на
                        #    каждой не нашли ничего нового. Повтор страницы здесь
                        #    означает, что запрошенной страницы просто не
                        #    существует — каталог закончился штатно.
                        if self.current_page > max_page_in_db:
                            to_gui(
                                f"🏁 Отработан весь каталог: страницы до №{max_page_in_db} "
                                f"проверены, новых товаров больше нет."
                            )
                            break

                        # 3. Повтор не первой страницы, и мы ещё не вышли за
                        #    пределы базы. Значит номера страниц на сайте не
                        #    совпадают с запрошенными — каталог сократился.
                        if repeated:
                            to_gui(f"🛑 {self._repeated_page_reason()}")
                            logger.warning("Остановка парсинга: %s", self._repeated_page_reason())
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
                            self._register_skipped(item, "битая ссылка в каталоге")

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
                                # Ошибку гасим, данные останутся дефолтными, но товар
                                # попадёт в учёт: характеристики с него не сняты.
                                parse_error = (str(e).splitlines() or [UNKNOWN_ERROR_MSG])[0][:120]
                                self._register_skipped(item, f"ошибка разбора карточки: {parse_error}")
                            finally:
                                detail_page.close()
                        else:
                            # Карточка не открылась. Причина уже записана в лог
                            # подробно, здесь нужен короткий итог для учёта.
                            self._register_skipped(item, "карточка не загрузилась")

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
                # Учёт сбоев сохраняется ПОСЛЕ остановки парсера и в finally:
                # иначе при аварийной остановке или отмене пользователем список
                # незакрытых карточек потерялся бы вместе с процессом.
                self._flush_skipped(to_gui)

                # Корректная очистка ресурсов: сначала страница, потом контекст
                if "page" in locals() and not page.is_closed():
                    page.close()
                if "context" in locals():
                    context.close()
