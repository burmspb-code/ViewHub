"""Тесты подключения парсера Цитадели."""

import pytest

from src.core.base_classes import BaseParser
from src.extractors.citadel_extractor import CitadelExtractor
from src.my_exceptions.exceptions import ExceptionStopParser
from src.parsers.citadel_parser import CitadelParser
from src.parsers_config.citadel_config import CitadelConfig
from src.service_modules import parsing_service

CARD_HTML = """
<html>
  <div class="product-list">
    <a href="/catalog/zamki/">Замки</a>
    <div class="product-card">
      <div class="product-card-info">
        <div class="product-title">
          <a href="/catalog/navesnye/zamok-apeks/" title="Замок навесной PD-21  Апекс">
            Замок навесной PD-21 Апекс
          </a>
        </div>
        <div class="product-brand-info"><div class="title">Бренд</div></div>
        <div class="available-block much green_status"><span>В наличии</span></div>
        <div class="text">Описание первого товара.</div>
      </div>
      <div class="price">1 290,50 ₽</div>
    </div>
    <div class="product-card">
      <div class="product-card-info">
        <div class="product-title">
          <a href="/catalog/petli/petlya-bulat/" title="Петля Булат ПН-103">
            Петля Булат ПН-103
          </a>
        </div>
        <div class="product-brand-info"><div class="title">Бренд</div></div>
        <div class="available-block much orange_status"><span>Много</span></div>
        <div class="text">Описание второго товара.</div>
      </div>
    </div>
  </div>
</html>
"""

DETAIL_HTML = """
<html>
  <div class="product-brand-part">
    <span>Арт.:</span>
    <button class="number-copy"><span id="number-field">24043</span></button>
  </div>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "Product",
    "name": "Замок навесной PD-21",
    "sku": "24043",
    "brand": {"@type": "Brand", "name": "АПЕКС"}
  }
  </script>
</html>
"""

DETAIL_HTML_LABEL_ONLY = """
<html>
  <div class="product-brand-part">Арт.: 777</div>
  <div class="product-brand-info"><div class="title">Бренд</div></div>
</html>
"""


@pytest.fixture
def config():
    """Конфиг Цитадели с реальным базовым URL."""
    instance = CitadelConfig()
    instance.target_url = "https://citadel2000.ru/"
    instance.keyword = "замок"
    return instance


@pytest.fixture
def extractor(config):
    return CitadelExtractor(config)


def test_config_schema_contains_all_sections():
    """Схема таблицы = системные колонки + бизнес-колонки."""
    schema = CitadelConfig.get_full_schema()

    assert set(schema) == set(CitadelConfig.SYSTEM_COLUMNS) | set(CitadelConfig.BUSINESS_COLUMNS)
    assert CitadelConfig.DEDUP_COLUMN in schema
    for column in ("code", "brand", "availability", "description", "current_price", "url"):
        assert column in schema


def test_extractor_keys_match_config_schema(extractor):
    """Сейвер берёт значения по ключам схемы — они обязаны совпадать."""
    items = extractor.extract_data(CARD_HTML)

    assert items
    assert set(items[0]) == set(CitadelConfig.BUSINESS_COLUMNS)


def test_extract_data_parses_product_cards(extractor):
    """Из карточек достаются все поля, ссылки категорий игнорируются."""
    items = extractor.extract_data(CARD_HTML)

    assert len(items) == 2
    first = items[0]
    assert first["item_id"] == "zamok-apeks"
    assert first["name"] == "Замок навесной PD-21 Апекс"
    assert first["url"] == "https://citadel2000.ru/catalog/navesnye/zamok-apeks/"
    # Кода в выдаче нет, а «Бренд» — подпись-заглушка: оба поля заполнит проход по карточке.
    assert first["code"] == ""
    assert first["brand"] == ""
    assert first["availability"] == "В наличии"
    assert first["description"] == "Описание первого товара."
    assert first["current_price"] == 1290.5

    second = items[1]
    assert second["availability"] == "Много"
    assert second["current_price"] is None
    assert all("catalog/zamki/" not in item["url"] for item in items)


def test_extract_detail_data_reads_code_and_brand(extractor):
    """Код берётся из number, бренд — из JSON-LD товара."""
    result = extractor.extract_detail_data(DETAIL_HTML)

    assert result == {"code": "24043", "brand": "АПЕКС"}


def test_extract_detail_data_strips_article_prefix(extractor):
    """Подпись «Арт.:» убирается, если сайт отдаёт её вместе с кодом."""
    result = extractor.extract_detail_data(DETAIL_HTML_LABEL_ONLY)

    assert result == {"code": "777", "brand": ""}


def test_extract_detail_data_ignores_brand_placeholder(extractor):
    """Заглушка «Бренд» не должна попадать в БД как название бренда."""
    assert extractor.extract_detail_data("<div class='product-brand-info'><div class='title'>Бренд</div></div>") == {
        "code": "",
        "brand": "",
    }


def test_extract_data_skips_duplicates(extractor):
    """Повторный вызов не возвращает уже виденные товары."""
    assert len(extractor.extract_data(CARD_HTML)) == 2
    assert extractor.extract_data(CARD_HTML) == []

    extractor.clear_seen()
    assert len(extractor.extract_data(CARD_HTML)) == 2


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("В наличии", "В наличии"),
        ("Много", "Много"),
        ("Ожидается поставка", "Ожидается поставка"),
        ("Нет в наличии", "Нет в наличии"),
        ("", "Неизвестно"),
    ],
)
def test_availability_mapping(text, expected):
    assert CitadelExtractor._parse_availability(text) == expected


def test_extract_data_on_empty_page(extractor):
    """Пустая страница — нормальное окончание выдачи, а не ошибка."""
    assert extractor.extract_data("<html><div>Ничего не найдено</div></html>") == []


def test_build_url(config, extractor):
    """URL поиска и пагинации совпадают с разметкой сайта."""
    parser = CitadelParser(config=config, extractor=extractor, manager=None)

    assert parser._build_url() == "https://citadel2000.ru/catalog/?q=%D0%B7%D0%B0%D0%BC%D0%BE%D0%BA"
    assert parser._build_url(3).endswith("&PAGEN_2=3")


def test_cancel_triggers_hook(config, extractor):
    """BaseParser.cancel() вызывает хук _on_cancel, флаг отмены виден парсеру."""
    parser = CitadelParser(config=config, extractor=extractor, manager=None)

    assert isinstance(parser, BaseParser)
    parser.cancel()

    assert parser._is_running is False
    assert parser._cancel_requested is True


def test_run_parsing_saves_items_and_closes_browser(config, extractor, mocker):
    """Парсер обогащает карточки, пишет их поштучно и закрывает ресурсы Playwright."""
    manager = mocker.MagicMock()
    parser = CitadelParser(config=config, extractor=extractor, manager=manager)

    listing_page = mocker.MagicMock()
    listing_page.content.return_value = CARD_HTML
    listing_page.is_closed.return_value = True

    detail_pages = []
    for html in (DETAIL_HTML, DETAIL_HTML_LABEL_ONLY):
        detail_page = mocker.MagicMock()
        detail_page.content.return_value = html
        detail_page.is_closed.return_value = False
        detail_pages.append(detail_page)

    context = mocker.MagicMock()
    context.new_page.side_effect = [listing_page, *detail_pages]
    browser = mocker.MagicMock()
    browser.new_context.return_value = context
    playwright = mocker.MagicMock()
    playwright.chromium.launch.return_value = browser
    playwright_context = mocker.MagicMock()
    playwright_context.__enter__.return_value = playwright

    # Playwright останавливается при выходе из with — ресурсы должны быть
    # закрыты к этому моменту, иначе в логе появится "Event loop is closed".
    def on_playwright_exit(*args):
        assert parser._page is None
        assert parser._browser is None
        return False

    playwright_context.__exit__.side_effect = on_playwright_exit
    mocker.patch("src.parsers.citadel_parser.sync_playwright", return_value=playwright_context)

    chunks = list(parser.run_parsing())

    assert len(chunks) == 1
    first, second = chunks[0]
    assert first["code"] == "24043"
    assert first["brand"] == "АПЕКС"
    assert second["code"] == "777"
    assert second["brand"] == ""
    assert manager.save.call_count == 2
    assert manager.save.call_args_list[0].args[0] == [first]
    assert manager.save.call_args_list[1].args[0] == [second]
    # Страница 1 с товарами + две пустые страницы — штатное завершение.
    assert listing_page.goto.call_count == 3
    assert all(detail_page.goto.call_count == 1 for detail_page in detail_pages)
    assert all(detail_page.close.call_count == 1 for detail_page in detail_pages)
    assert browser.close.call_count == 1
    assert parser._browser is None
    assert parser._page is None
    assert parser._detail_page is None


def test_enrich_item_keeps_listing_data_on_error(config, extractor, mocker):
    """Битая карточка не теряет данные выдачи и всё равно закрывается."""
    parser = CitadelParser(config=config, extractor=extractor, manager=mocker.MagicMock())
    item = {"url": "https://citadel2000.ru/catalog/broken/", "code": "", "brand": ""}

    detail_page = mocker.MagicMock()
    detail_page.goto.side_effect = RuntimeError("страница недоступна")
    detail_page.is_closed.return_value = False
    context = mocker.MagicMock()
    context.new_page.return_value = detail_page
    parser._context = context

    parser._enrich_item(item)

    assert item["code"] == ""
    assert item["brand"] == ""
    detail_page.close.assert_called_once()
    assert parser._detail_page is None


def test_cancel_before_start_closes_browser(config, extractor, mocker):
    """Отмена до старта прерывает цикл и всё равно закрывает браузер."""
    parser = CitadelParser(config=config, extractor=extractor, manager=mocker.MagicMock())
    parser.cancel()

    browser = mocker.MagicMock()
    playwright = mocker.MagicMock()
    playwright.chromium.launch.return_value = browser
    playwright_context = mocker.MagicMock()
    playwright_context.__enter__.return_value = playwright
    mocker.patch("src.parsers.citadel_parser.sync_playwright", return_value=playwright_context)

    with pytest.raises(ExceptionStopParser):
        list(parser.run_parsing())

    browser.close.assert_called_once()
    assert parser._cancel_requested is False


def test_prepare_parsing_citadel_wires_dependencies(mocker):
    """Сборка в service_modules создаёт конфиг, экстрактор, менеджер и парсер."""
    obj = mocker.MagicMock()
    manager = mocker.MagicMock()
    parser = mocker.MagicMock()

    config_class = mocker.patch.object(parsing_service, "CitadelConfig")
    mocker.patch.object(parsing_service, "DatabaseManager", return_value=manager)
    mocker.patch.object(parsing_service, "CitadelExtractor")
    mocker.patch.object(parsing_service, "CitadelParser", return_value=parser)

    parsing_service.prepare_parsing_citadel(obj)

    assert obj.manager is manager
    assert obj.parser is parser
    config_class.assert_called_once_with()
    parsing_service.CitadelExtractor.assert_called_once()
    parsing_service.CitadelParser.assert_called_once()
