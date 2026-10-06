import os
import sys

import pytest


from src.parsers.golden_apple_parser import GoldenAppleParser
from src.parsers_config.golden_apple_config import GoldenAppleConfig
from src.extractors.golden_apple_extractor import GoldenAppleExtractor
from src.database.sqlite_manager import DatabaseManager
from src.parsers.golden_apple_parser import ExceptionStopParser


class FakeConfig:
    """Создание фейкового класса конфигурации."""

    target_url = "https://goldapple.ru"
    keyword = "/parfjumerija/novinki/"


def test_init_goldenapple_parser(monkeypatch):
    """Проверяет инициализацию GoldenAppleParser."""
    fake_path = "project_dir/work_dir/"

    monkeypatch.setattr(os, "getcwd", lambda: fake_path)

    parser = GoldenAppleParser(config=GoldenAppleConfig, extractor=GoldenAppleExtractor, manager=DatabaseManager)

    assert parser.current_page == 1
    assert parser.empty_pages_count == 0

    expected = os.path.join(fake_path, "chrome_user_profile")
    assert parser.user_data_dir == expected


def test_build_url_with_pagination(monkeypatch):
    """Проверяет построение URL для указанной страницы категории каталога."""

    parser = GoldenAppleParser(config=FakeConfig, extractor=GoldenAppleExtractor, manager=DatabaseManager)

    monkeypatch.setattr(parser, "config", FakeConfig)

    # Тест для первой страницы
    parser_url = parser._build_url(1)
    assert parser_url == "https://goldapple.ru/parfjumerija/novinki"

    # Тест для второй страницы
    parser_url = parser._build_url(2)
    assert parser_url == "https://goldapple.ru/parfjumerija/novinki?p=2"


class TestGoldenAppleParserSleepAndLoad:
    @pytest.fixture
    def mock_parser(self, mocker):
        """Фикстура для создания парсера с заглушенными зависимостями."""
        config = mocker.MagicMock()
        extractor = mocker.MagicMock()
        manager = mocker.MagicMock()

        parser = GoldenAppleParser(config=config, extractor=extractor, manager=manager)
        parser._is_running = True
        return parser

    def test_load_page_success(self, mock_parser, mocker):
        """1. Успешный сценарий: страница загружается, _smart_sleep вызывается."""
        # Глушим реальный сон, чтобы тест не ждал секунду
        mock_parser._smart_sleep = mocker.MagicMock()

        mock_context = mocker.MagicMock()
        mock_page = mocker.MagicMock()
        mock_context.new_page.return_value = mock_page

        result = mock_parser.load_product_detail_page(
            context=mock_context, product_url="https://goldapple.ru", product_id="123"
        )

        # Проверяем, что Playwright выполнил свои шаги
        mock_page.goto.assert_called_once_with("https://goldapple.ru", wait_until="domcontentloaded", timeout=60000)
        mock_parser._smart_sleep.assert_called_once_with(1.0)
        assert result == mock_page

    def test_load_page_user_cancel(self, mock_parser, mocker):
        """2. Сценарий отмены: парсер остановлен, ждем ExceptionStopParser."""
        mock_parser._smart_sleep = mocker.MagicMock()

        mock_context = mocker.MagicMock()
        mock_page = mocker.MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_page.goto.side_effect = Exception("Сбой браузера")

        # Имитируем остановку парсера пользователем
        mock_parser._is_running = False

        with pytest.raises(ExceptionStopParser) as exc_info:
            mock_parser.load_product_detail_page(mock_context, "https://url.com", "123")

        assert "Процесс отменен пользователем." in str(exc_info.value)

    def test_smart_sleep_normal(self, mock_parser, mocker):
        """3. Проверяет, что _smart_sleep успешно отрабатывает, если отмены нет."""
        # Заглушаем time.sleep, чтобы тест не ждал физически ни доли секунды
        mocker.patch("time.sleep")

        # Запускаем короткий сон (например, на 0.2 секунды)
        # Он сделает пару итераций цикла и спокойно завершится
        mock_parser._smart_sleep(0.2)

        # Если код не выкинул ошибку — тест пройден успешно

    def test_smart_sleep_interrupts_on_cancel(self, mock_parser, mocker):
        """4. Проверяет, что _smart_sleep мгновенно прерывается, если флаг _is_running стал False."""
        mocker.patch("time.sleep")

        # Имитируем, что пользователь нажал Стоп в GUI
        mock_parser._is_running = False

        # Код должен мгновенно среагировать и выбросить исключение
        with pytest.raises(ExceptionStopParser) as exc_info:
            mock_parser._smart_sleep(5.0)  # Задаем аж 5 секунд сна

        assert "Процесс отменен пользователем во время паузы." in str(exc_info.value)


class TestLoadCatalogPage:
    @pytest.fixture
    def mock_parser(self, mocker):
        """Фикстура pytest для создания изолированного парсера."""
        config = mocker.MagicMock()
        extractor = mocker.MagicMock()
        manager = mocker.MagicMock()

        parser = GoldenAppleParser(config=config, extractor=extractor, manager=manager)
        parser._is_running = True
        parser.current_page = 1

        # Полностью глушим микро-сны, чтобы тесты не ждали физически 0.3 и 3.0 секунды
        parser._smart_sleep = mocker.MagicMock()
        return parser

    def test_load_catalog_success(self, mock_parser, mocker):
        """1. Успешный сценарий: каталог полностью прогрузился, скролл сработал."""
        mock_page = mocker.MagicMock()
        target_url = "https://goldapple.ru"

        result = mock_parser.load_catalog_page(page=mock_page, url=target_url)

        # Проверяем корректность вызовов Playwright
        mock_page.goto.assert_called_once_with(target_url, wait_until="domcontentloaded", timeout=60000)
        mock_page.locator.assert_called_with("article")
        mock_page.locator.return_value.first.wait_for.assert_called_once_with(state="attached", timeout=60000)

        # Проверяем эмуляцию скролла на Vue-сайте
        mock_page.evaluate.assert_called_once_with("window.scrollTo(0, 2500);")

        # Проверяем, что оба сна (0.3с и 3.0с) были вызваны последовательно
        assert mock_parser._smart_sleep.call_args_list == [mocker.call(0.3), mocker.call(3.0)]

        # Функция должна вернуть объект страницы
        assert result == mock_page

    def test_load_catalog_inner_timeout_ignored(self, mock_parser, mocker):
        """2. Сценарий сбоя article: если карточки не ответили, код скроллит дальше."""
        # Перехватываем логгер, чтобы проверить запись о проблеме
        mock_logger = mocker.patch("src.parsers.golden_apple_parser.logger")
        # Ожидание челленджа здесь не проверяется — отключаем, чтобы тест был быстрым
        mocker.patch.object(mock_parser, "_wait_for_challenge_to_pass", return_value=False)

        mock_page = mocker.MagicMock()

        # Имитируем падение ожидания article (таймаут)
        mock_page.locator.return_value.first.wait_for.side_effect = Exception("Timeout 60000ms expired")

        # Вызываем метод (он не должен упасть благодаря внутреннему try/except)
        result = mock_parser.load_catalog_page(page=mock_page, url="https://goldapple.ru")

        # Проверяем, что проблема зафиксирована на уровне warning.
        # Раньше здесь стоял logger.debug, из-за чего главная проблема
        # (каталог не отрендерился) была полностью невидима в логах.
        assert mock_logger.warning.call_count >= 1
        # Разворачиваем %s-аргументы, иначе в тексте останутся плейсхолдеры
        logged = " ".join(
            (str(call.args[0]) % call.args[1:]) if len(call.args) > 1 else str(call.args[0])
            for call in mock_logger.warning.call_args_list
        )
        assert "не появились на странице каталога" in logged
        assert "Timeout 60000ms expired" in logged

        # Важно: скролл и сны ВСЁ РАВНО должны отработать
        mock_page.evaluate.assert_called_once_with("window.scrollTo(0, 2500);")
        assert result == mock_page

    def test_load_catalog_user_cancel(self, mock_parser, mocker):
        """3. Критический сбой: переход на страницу упал, и пользователь остановил парсер."""
        mock_page = mocker.MagicMock()
        # Имитируем падение самого перехода goto
        mock_page.goto.side_effect = Exception("Сеть недоступна")

        # Имитируем нажатие Стоп
        mock_parser._is_running = False

        # Ждем кастомное исключение отмены процесса
        with pytest.raises(ExceptionStopParser) as exc_info:
            mock_parser.load_catalog_page(page=mock_page, url="https://goldapple.ru")

        assert "Процесс отменен пользователем." in str(exc_info.value)

    def test_load_catalog_generic_error_reraised(self, mock_parser, mocker):
        """4. Критический сбой: переход упал во время штатной работы. Ошибка пишется в лог и пробрасывается вверх."""
        mock_logger = mocker.patch("src.parsers.golden_apple_parser.logger")
        mock_page = mocker.MagicMock()

        # Имитируем поломку страницы с многострочной ошибкой
        mock_page.goto.side_effect = Exception("Fatal Error\nConnection reset by peer")

        mock_parser._is_running = True
        mock_parser.current_page = 5

        # Код должен выкинуть исходное исключение (raise e)
        with pytest.raises(Exception) as exc_info:
            mock_parser.load_catalog_page(page=mock_page, url="https://goldapple.ru")

        # Убеждаемся, что пробросилась именно исходная ошибка
        assert "Fatal Error" in str(exc_info.value)

        # Проверяем логирование: текст должен взять только первую строчку ошибки и номер страницы
        mock_logger.error.assert_called_once()
        assert "Ошибка. Не удалось прогрузить страницу каталога №5: Fatal Error" in mock_logger.error.call_args[0][0]


class TestStablePageContent:
    """Тесты устойчивого чтения HTML в условиях гонки с навигацией SPA."""

    @pytest.fixture
    def parser(self, mocker):
        config = mocker.MagicMock()
        parser = GoldenAppleParser(
            config=config, extractor=mocker.MagicMock(), manager=mocker.MagicMock()
        )
        parser._is_running = True
        # Убираем паузу между попытками, чтобы тест был быстрым
        mocker.patch.object(parser, "_smart_sleep", return_value=None)
        return parser

    RACE_ERROR = (
        "Unable to retrieve content because the page is navigating and changing the content."
    )

    def test_retries_and_succeeds_on_navigation_race(self, parser, mocker):
        """Гонка с навигацией — не повод падать: повтор должен вернуть HTML."""
        page = mocker.MagicMock()
        page.content.side_effect = [Exception(self.RACE_ERROR), Exception(self.RACE_ERROR), "<html>ok</html>"]

        assert parser._stable_page_content(page) == "<html>ok</html>"
        assert page.content.call_count == 3

    def test_no_retry_on_unrelated_error(self, parser, mocker):
        """Настоящая ошибка не должна маскироваться бессмысленными повторами."""
        page = mocker.MagicMock()
        page.content.side_effect = Exception("net::ERR_CONNECTION_REFUSED")

        with pytest.raises(Exception) as exc_info:
            parser._stable_page_content(page)

        assert "net::ERR_CONNECTION_REFUSED" in str(exc_info.value)
        # Ровно одна попытка — повтор тут не поможет
        assert page.content.call_count == 1

    def test_raises_after_exhausting_attempts(self, parser, mocker):
        """Если гонка не проходит, выбрасываем внятную ошибку, а не голую Playwright."""
        page = mocker.MagicMock()
        page.content.side_effect = Exception(self.RACE_ERROR)

        with pytest.raises(RuntimeError) as exc_info:
            parser._stable_page_content(page, attempts=3)

        assert "3 попыток" in str(exc_info.value)
        assert page.content.call_count == 3

    def test_respects_user_cancel(self, parser, mocker):
        """Отмена пользователем должна срабатывать и на повторах."""
        page = mocker.MagicMock()
        page.content.side_effect = Exception(self.RACE_ERROR)
        parser._is_running = False

        with pytest.raises(ExceptionStopParser):
            parser._stable_page_content(page)


class TestBlockDetection:
    """Тесты определения блокировки и устойчивости к навигации при скролле."""

    @pytest.fixture
    def parser(self, mocker):
        config = mocker.MagicMock()
        parser = GoldenAppleParser(
            config=config, extractor=mocker.MagicMock(), manager=mocker.MagicMock()
        )
        parser._is_running = True
        parser.current_page = 1
        mocker.patch.object(parser, "_smart_sleep", return_value=None)
        return parser

    @pytest.mark.parametrize("status", [401, 403, 429])
    def test_detects_http_block(self, parser, status):
        """HTTP 401/403/429 однозначно говорят о блокировке запроса."""
        parser._last_document_status = status
        reason = parser._detect_block_reason()
        assert reason is not None
        assert str(status) in reason

    def test_detects_network_failure(self, parser):
        """Нет ответа при наличии неудачных запросов = проблема с сетью."""
        parser._last_document_status = None
        parser._failed_requests = ["document https://goldapple.ru/ :: net::ERR_NAME_NOT_RESOLVED"]
        reason = parser._detect_block_reason()
        assert reason is not None
        assert "ERR_NAME_NOT_RESOLVED" in reason

    def test_no_false_positives_on_normal_status(self, parser):
        """Успешный ответ 200 не должен считаться блокировкой."""
        parser._last_document_status = 200
        parser._failed_requests = []
        assert parser._detect_block_reason() is None

    def test_scroll_failure_does_not_break_page_load(self, parser, mocker):
        """
        Ошибка скролла не должна обрывать парсинг.

        Именно так выглядел прошлый сбой: страница была занята навигацией,
        page.evaluate() падал с 'Execution context was destroyed' и обрывал
        весь запуск, хотя потеря скролла не критична.
        """
        mock_page = mocker.MagicMock()
        mock_page.goto.return_value = None
        mock_page.wait_for_load_state.return_value = None
        # Карточки не появляются — но блокировки не зафиксировано
        mock_page.locator.return_value.first.wait_for.side_effect = Exception("Timeout 60000ms exceeded")
        mock_page.evaluate.side_effect = Exception(
            "Execution context was destroyed, most likely because of a navigation"
        )
        parser._last_document_status = 200
        # Челлендж тут не проверяется — отключаем ожидание
        mocker.patch.object(parser, "_wait_for_challenge_to_pass", return_value=False)

        result = parser.load_catalog_page(page=mock_page, url="https://goldapple.ru/parfjumerija/novinki")

        # Страница возвращена несмотря на упавший скролл
        assert result == mock_page

    def test_block_raises_clear_stop_message(self, parser, mocker):
        """При явной блокировке парсер должен остановиться с понятным текстом."""
        mock_page = mocker.MagicMock()
        mock_page.goto.return_value = None
        mock_page.wait_for_load_state.return_value = None
        mock_page.locator.return_value.first.wait_for.side_effect = Exception("Timeout 60000ms exceeded")
        mock_page.title.return_value = ""
        mock_page.inner_text.return_value = ""
        parser._last_document_status = 403
        # Челлендж не проходит — проверяем именно сообщение о блокировке
        mocker.patch.object(parser, "_wait_for_challenge_to_pass", return_value=False)

        with pytest.raises(ExceptionStopParser) as exc_info:
            parser.load_catalog_page(page=mock_page, url="https://goldapple.ru/parfjumerija/novinki")

        assert "403" in str(exc_info.value)
        # Скролл не должен был выполняться — до него не дошли
        mock_page.evaluate.assert_not_called()


class TestChallengeWait:
    """Тесты ожидания прохождения антибот-челленджа."""

    @pytest.fixture
    def parser(self, mocker):
        config = mocker.MagicMock()
        parser = GoldenAppleParser(
            config=config, extractor=mocker.MagicMock(), manager=mocker.MagicMock()
        )
        parser._is_running = True
        return parser

    def test_returns_true_when_articles_appear(self, parser, mocker):
        """Если карточки появились — проверка пройдена, ждать дальше не нужно."""
        page = mocker.MagicMock()
        page.locator.return_value.count.return_value = 12
        page.title.return_value = "Золотое Яблоко — Парфюмерия"

        assert parser._wait_for_challenge_to_pass(page, timeout_ms=2000) is True

    def test_waits_until_loading_title_changes(self, parser, mocker):
        """
        Сценарий из лога: title='Loading https://...' и тело-UUID.

        Челлендж должен завершиться сменой заголовка — и мы это ловим.
        """
        page = mocker.MagicMock()
        page.locator.return_value.count.return_value = 0
        # Сначала Loading, затем нормальный заголовок
        page.title.side_effect = ["Loading https://goldapple.ru/parfjumerija", "Золотое Яблоко"]

        mocker.patch.object(parser, "_smart_sleep", side_effect=lambda s: None)

        assert parser._wait_for_challenge_to_pass(page, timeout_ms=5000) is True

    def test_returns_false_on_timeout(self, parser, mocker):
        """Если проверка так и не завершилась — возвращаем False, а не вечный цикл."""
        page = mocker.MagicMock()
        page.locator.return_value.count.return_value = 0
        page.title.return_value = "Loading https://goldapple.ru/parfjumerija"

        mocker.patch.object(parser, "_smart_sleep", side_effect=lambda s: None)

        assert parser._wait_for_challenge_to_pass(page, timeout_ms=50) is False

    def test_respects_cancel(self, parser, mocker):
        """Отмена должна прерывать и ожидание проверки."""
        page = mocker.MagicMock()
        page.locator.return_value.count.return_value = 0
        page.title.return_value = "Loading https://goldapple.ru"
        parser._is_running = False

        with pytest.raises(ExceptionStopParser):
            parser._wait_for_challenge_to_pass(page, timeout_ms=5000)


class TestCountAndGetProductsOnPage:
    @pytest.fixture
    def mock_parser(self, mocker):
        """Фикстура для создания изолированного парсера."""
        config = mocker.MagicMock()
        extractor = mocker.MagicMock()
        manager = mocker.MagicMock()

        parser = GoldenAppleParser(config=config, extractor=extractor, manager=manager)
        parser.current_page = 4  # Задаем номер страницы для проверки логов
        return parser

    def test_get_products_success(self, mock_parser, mocker):
        """1. Успешный сценарий: на странице есть несколько карточек товаров."""
        # 1. Готовим тестовый HTML-код с 3 карточками Золотого Яблока
        fake_html = """
        <html>
            <body>
                <div class="catalog-grid">
                    <article class="product-card">Товар 1</article>
                    <article class="product-card">Товар 2</article>
                    <article class="product-card">Товар 3</article>
                </div>
            </body>
        </html>
        """

        # 2. Создаем мок для страницы Playwright
        mock_page = mocker.MagicMock()
        # Настраиваем, чтобы при вызове page.content() возвращался наш HTML
        mock_page.content.return_value = fake_html

        # 3. Вызываем метод
        cards = mock_parser.count_and_get_products_on_page(page=mock_page)

        # 4. Проверяем результаты
        mock_page.content.assert_called_once()  # Убеждаемся, что метод считал HTML
        assert isinstance(cards, list)  # Результат должен быть списком (ResultSet)
        assert len(cards) == 3  # Карточек должно быть ровно 3
        assert cards[0].text.strip() == "Товар 1"

    def test_get_products_empty_page(self, mock_parser, mocker):
        """2. Сценарий с пустой страницей: теги article отсутствуют."""
        # HTML без карточек товаров (например, страница пуста или сбой выдачи)
        fake_html = "<html><body><div>Товаров не найдено</div></body></html>"

        mock_page = mocker.MagicMock()
        mock_page.content.return_value = fake_html

        cards = mock_parser.count_and_get_products_on_page(page=mock_page)

        # Метод должен вернуть пустой список, без ошибок
        assert len(cards) == 0

    def test_get_products_exception_handled_and_reraised(self, mock_parser, mocker):
        """3. Критический сбой: page.content() выбросил ошибку. Ошибка логируется и пробрасывается вверх."""
        # Мокаем логгер вашего модуля
        mock_logger = mocker.patch("src.parsers.golden_apple_parser.logger")

        mock_page = mocker.MagicMock()
        # Имитируем жесткое падение Playwright (например, Target page closed)
        mock_page.content.side_effect = Exception("Target page closed")

        # Проверяем, что метод делает raise исходного исключения
        with pytest.raises(Exception) as exc_info:
            mock_parser.count_and_get_products_on_page(page=mock_page)

        assert "Target page closed" in str(exc_info.value)

        # Проверяем, что логгер зафиксировал правильный номер страницы текущего парсера (№4)
        log_message = mock_logger.error.call_args[0][0]
        assert "Ошибка. Не удалось определить количество товаров на странице №4" in log_message


class TestRunParsing:
    """Тесты для основного метода run_parsing."""

    @pytest.fixture(autouse=True)
    def mock_stealth(self, mocker):
        """
        Мокаем playwright_stealth для всех тестов класса.

        Мокается именно Stealth().apply_stealth_sync(), потому что в
        playwright_stealth 2.x функции stealth_sync больше нет. Если бы
        оставшийся код импортировал несуществующее имя, тесты бы это поймали.
        """
        mock_stealth_module = mocker.MagicMock()
        mocker.patch.dict("sys.modules", {"playwright_stealth": mock_stealth_module})
        return mock_stealth_module

    def test_stealth_uses_v2_api(self, mocker):
        """
        Проверяет, что вызывается актуальный API playwright_stealth 2.x.

        Регрессия: код делал `from playwright_stealth import stealth_sync`,
        чего в 2.x нет вообще. Ошибка глоталась try/except, и маскировка
        не работала нигде — ни при запуске из исходников, ни в сборке.
        """
        # autouse-фикстура подменяет sys.modules, поэтому реальный пакет нужно
        # импортировать ДО подмены — снимаем фикстуру через прямой sys.modules.
        import importlib

        saved = sys.modules.pop("playwright_stealth", None)
        try:
            real_stealth = importlib.import_module("playwright_stealth")

            # Экспортируется класс Stealth, а функции stealth_sync в 2.x нет
            assert hasattr(real_stealth, "Stealth")
            assert not hasattr(real_stealth, "stealth_sync")

            # Нужный метод есть у реального класса
            assert hasattr(real_stealth.Stealth, "apply_stealth_sync")
        finally:
            if saved is not None:
                sys.modules["playwright_stealth"] = saved

    @pytest.fixture
    def mock_parser(self, mocker):
        """Фикстура для создания парсера с заглушенными зависимостями."""
        config = mocker.MagicMock()
        config.target_url = "https://goldapple.ru"
        config.keyword = "parfjumerija/novinki"

        extractor = mocker.MagicMock()
        manager = mocker.MagicMock()

        parser = GoldenAppleParser(config=config, extractor=extractor, manager=manager)
        parser._is_running = True
        parser.current_page = 1
        parser.empty_pages_count = 0
        return parser

    def test_run_parsing_single_page_success(self, mock_parser, mocker):
        """1. Успешный сценарий: одна страница с товарами, сохранение в БД."""
        # Мокаем sync_playwright
        mock_playwright = mocker.patch("src.parsers.golden_apple_parser.sync_playwright")

        # Создаем моки для Playwright объектов
        mock_p = mocker.MagicMock()
        mock_context = mocker.MagicMock()
        mock_page = mocker.MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch_persistent_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        # Мокаем методы парсера
        mock_parser.load_catalog_page = mocker.MagicMock(return_value=mock_page)
        mock_parser.count_and_get_products_on_page = mocker.MagicMock(return_value=[mocker.MagicMock()])

        # Мокаем extractor
        mock_parser.extractor.extract_data.return_value = [
            {"item_id": "123", "brand": "Brand1", "name": "Product1", "url": "https://goldapple.ru/123"}
        ]

        # Мокаем manager
        mock_parser.manager.check_existing_items_with_pages.return_value = {}
        mock_parser.manager.get_last_page_number.return_value = 1
        mock_parser.manager.save = mocker.MagicMock()

        # Мокаем load_product_detail_page
        mock_parser.load_product_detail_page = mocker.MagicMock(return_value=None)

        # Мокаем _smart_sleep
        mock_parser._smart_sleep = mocker.MagicMock()

        # Запускаем генератор и получаем первый результат
        generator = mock_parser.run_parsing()
        result = next(generator)

        # Проверяем, что был возвращен список товаров
        assert isinstance(result, list)
        assert len(result) == 1

        # Проверяем вызовы методов
        mock_parser.load_catalog_page.assert_called_once()
        mock_parser.extractor.extract_data.assert_called_once()
        mock_parser.manager.check_existing_items_with_pages.assert_called_once()
        mock_parser.manager.save.assert_called_once()

        # Останавливаем парсер для завершения теста
        mock_parser._is_running = False

    def test_run_parsing_empty_pages_stop(self, mock_parser, mocker):
        """2. Сценарий остановки: две пустые страницы подряд."""
        mock_playwright = mocker.patch("src.parsers.golden_apple_parser.sync_playwright")

        mock_p = mocker.MagicMock()
        mock_context = mocker.MagicMock()
        mock_page = mocker.MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch_persistent_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_parser.load_catalog_page = mocker.MagicMock(return_value=mock_page)
        mock_parser.count_and_get_products_on_page = mocker.MagicMock(return_value=[])
        mock_parser.extractor.extract_data.return_value = []
        mock_parser._smart_sleep = mocker.MagicMock()

        # Запускаем генератор
        generator = mock_parser.run_parsing()

        # После двух пустых страниц генератор должен завершиться
        try:
            next(generator)
        except StopIteration:
            pass

        # Проверяем, что счетчик пустых страниц достиг 2 и произошла остановка
        assert mock_parser.empty_pages_count == 2

    def test_run_parsing_user_cancel(self, mock_parser, mocker):
        """3. Сценарий отмены пользователем во время парсинга."""
        mock_playwright = mocker.patch("src.parsers.golden_apple_parser.sync_playwright")

        mock_p = mocker.MagicMock()
        mock_context = mocker.MagicMock()
        mock_page = mocker.MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch_persistent_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        # Имитируем отмену при первой проверке
        mock_parser._is_running = False
        mock_parser._smart_sleep = mocker.MagicMock()

        # Запускаем генератор и ожидаем исключение
        generator = mock_parser.run_parsing()

        with pytest.raises(ExceptionStopParser) as exc_info:
            next(generator)

        assert "Процесс отменен пользователем." in str(exc_info.value)

    def test_run_parsing_duplicates_stop(self, mock_parser, mocker):
        """4. Сценарий остановки при обнаружении всех дубликатов."""
        mock_playwright = mocker.patch("src.parsers.golden_apple_parser.sync_playwright")

        mock_p = mocker.MagicMock()
        mock_context = mocker.MagicMock()
        mock_page = mocker.MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch_persistent_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_parser.load_catalog_page = mocker.MagicMock(return_value=mock_page)
        mock_parser.count_and_get_products_on_page = mocker.MagicMock(return_value=[mocker.MagicMock()])

        # Возвращаем товары, которые уже есть в БД
        mock_parser.extractor.extract_data.return_value = [
            {"item_id": "123", "brand": "Brand1", "name": "Product1", "url": "https://goldapple.ru/123"}
        ]

        # Мокаем manager - все товары уже есть в БД
        mock_parser.manager.check_existing_items_with_pages.return_value = {"123": 1}
        mock_parser.manager.get_last_page_number.return_value = 1
        mock_parser._smart_sleep = mocker.MagicMock()

        # Запускаем генератор
        generator = mock_parser.run_parsing()

        # Должен завершиться без yield (все дубликаты)
        try:
            next(generator)
        except StopIteration:
            pass

        # Проверяем, что страница увеличилась для проверки следующей
        assert mock_parser.current_page == 2

    def test_run_parsing_pagination_loop_detection(self, mock_parser, mocker):
        """5. Сценарий обнаружения зацикливания пагинации."""
        mock_playwright = mocker.patch("src.parsers.golden_apple_parser.sync_playwright")

        mock_p = mocker.MagicMock()
        mock_context = mocker.MagicMock()
        mock_page = mocker.MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch_persistent_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_parser.load_catalog_page = mocker.MagicMock(return_value=mock_page)
        mock_parser.count_and_get_products_on_page = mocker.MagicMock(return_value=[mocker.MagicMock()])

        mock_parser.extractor.extract_data.return_value = [
            {"item_id": "123", "brand": "Brand1", "name": "Product1", "url": "https://goldapple.ru/123"}
        ]

        # Все товары дубликаты
        mock_parser.manager.check_existing_items_with_pages.return_value = {"123": 1}

        # Текущая страница больше максимальной в БД - зацикливание
        mock_parser.current_page = 5
        mock_parser.manager.get_last_page_number.return_value = 3
        mock_parser._smart_sleep = mocker.MagicMock()

        # Запускаем генератор
        generator = mock_parser.run_parsing()

        # Должен завершиться из-за зацикливания
        try:
            next(generator)
        except StopIteration:
            pass

        # Страница не должна увеличиться
        assert mock_parser.current_page == 5

    def test_run_parsing_broken_url_handling(self, mock_parser, mocker):
        """6. Сценарий обработки битого URL товара."""
        mock_playwright = mocker.patch("src.parsers.golden_apple_parser.sync_playwright")

        mock_p = mocker.MagicMock()
        mock_context = mocker.MagicMock()
        mock_page = mocker.MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch_persistent_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_parser.load_catalog_page = mocker.MagicMock(return_value=mock_page)
        mock_parser.count_and_get_products_on_page = mocker.MagicMock(return_value=[mocker.MagicMock()])

        # Товар с пустым URL
        mock_parser.extractor.extract_data.return_value = [
            {"item_id": "123", "brand": "Brand1", "name": "Product1", "url": ""}
        ]

        mock_parser.manager.check_existing_items_with_pages.return_value = {}
        mock_parser.manager.save = mocker.MagicMock()
        mock_parser._smart_sleep = mocker.MagicMock()

        # Запускаем генератор
        generator = mock_parser.run_parsing()
        result = next(generator)

        # Проверяем, что товар сохранен с дефолтными данными
        assert len(result) == 1
        assert result[0]["description"] == "Описание отсутствует"
        assert result[0]["usage"] == "Не указано"
        assert result[0]["country_of_origin"] == "Не указана"
        assert result[0]["page_number"] == 1

        mock_parser.manager.save.assert_called_once()

        # Останавливаем парсер
        mock_parser._is_running = False
