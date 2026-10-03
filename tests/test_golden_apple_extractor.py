import pytest
from bs4 import BeautifulSoup
from core.base_classes import BaseDBParsingConfig
from src.extractors.golden_apple_extractor import GoldenAppleExtractor

@pytest.fixture
def config_class():
    """Фикстура возвращает сам класс конфигурации как объект."""
    return BaseDBParsingConfig

@pytest.fixture
def extractor():
    """Фикстура для быстрой инициализации экстрактора с изящным конфигом."""
    return GoldenAppleExtractor(config=BaseDBParsingConfig)


def test_golden_apple_init_extractor(config_class):
    """Проверка того, что экстрактор корректно сохраняет переданный конфиг."""
    extrac_data = GoldenAppleExtractor(config=config_class)

    # Проверяем идентичность объекта конфигурации в памяти
    assert extrac_data.config == config_class
    assert extrac_data.config is config_class

def test_extract_deep_data_success(extractor):
    """1. Проверка успешного извлечения всех характеристик при идеальном HTML."""
    html_content = """
    <html>
        <!-- 1. Описание -->
        <div itemprop="description">"Прекрасный унисекс аромат с нотами бергамота."</div>

        <!-- 2. Применение -->
        <div text="Применение">
            <div class="custom_ga-pdp-wysiwyg_style">Распылить на кожу.</div>
        </div>

        <!-- 3. Информация и страна -->
        <div text="Информация и документы">
            <div class="some_ga-pdp-wysiwyg_class">
                <p>Состав: спирт, парфюм</p>
                <p>Страна происхождения: *Франция*</p>
            </div>
        </div>
    </html>
    """

    result = extractor.extract_deep_data(html_content)

    assert result["description"] == "Прекрасный унисекс аромат с нотами бергамота."
    assert result["usage"] == "Распылить на кожу."
    assert result["country_of_origin"] == "Франция"


def test_extract_deep_data_defaults(extractor):
    """2. Проверка возврата дефолтных значений, если блоков нет в HTML."""
    html_content = "<div><p>Какая-то посторонняя страница</p></div>"

    result = extractor.extract_deep_data(html_content)

    assert result["description"] == "Описание отсутствует"
    assert result["usage"] == "Не указано"
    assert result["country_of_origin"] == "Не указана"


def test_extract_deep_data_dirty_country_and_case(extractor):
    """3. Проверка очистки грязных данных в блоке страны (кавычки, регистр, двоеточия)."""
    html_content = """
    <div text="Информация и документы">
        <div class="style_ga-pdp-wysiwyg">
            <!-- Проверяем разный регистр и обилие мусорных символов -->
            <p>СТРАНА ПРОИСХОЖДЕНИЯ : "италия"'</p>
        </div>
    </div>
    """

    result = extractor.extract_deep_data(html_content)
    assert result["country_of_origin"] == "Италия"


def test_extract_deep_data_empty_country_node(extractor):
    """4. Проверка случая, когда фраза 'страна происхождения' есть, но название страны пустое."""
    html_content = """
    <div text="Информация и документы">
        <div class="style_ga-pdp-wysiwyg">
            <p>Страна происхождения:: ** "" </p>
        </div>
    </div>
    """

    result = extractor.extract_deep_data(html_content)
    # Так как после очистки строка пустая, цикл не должен перетереть дефолт
    assert result["country_of_origin"] == "Не указана"


def test_extract_deep_data_partial_tags_missing(extractor):
    """5. Проверка ветвления lambda-функций классов (если класс div не содержит нужной строки)."""
    html_content = """
    <div text="Применение">
        <div class="wrong-class-name">Текст, который не должен быть собран</div>
    </div>
    """

    result = extractor.extract_deep_data(html_content)
    assert result["usage"] == "Не указано"


def test_parse_single_card_happy_path(extractor):
    """1. Идеальный случай: все элементы присутствуют, относительный URL, есть скидка, товар в наличии."""
    html = """
    <div storage-scroll-id="123456">
        <a href="/product/test-aromat">Ссылка</a>
        <span class="product-card-name__brand">Zielinski & Rozen</span>
        <span class="product-card-name__name">Amberwood & Vanilla</span>
        <div class="product-card-vertical__type">Духи концентрированные</div>
        <div class="_ga-price old">4 000 ₽</div>
        <div class="_ga-price">3 000 ₽</div>
        <div class="product-rating__rating-value">4,9</div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = extractor._parse_single_card(soup, "uniseks-aromaty")

    assert result is not None
    assert result["item_id"] == "123456"
    assert result["url"] == "https://goldapple.ru/product/test-aromat/"
    assert result["brand"] == "Zielinski & Rozen"
    assert result["name"] == "Amberwood & Vanilla"
    assert result["product_type"] == "Духи концентрированные"
    assert result["old_price_rub"] == 4000.0
    assert result["current_price_rub"] == 3000.0
    assert result["discount"] == 25.0  # (1 - 3000/4000) * 100
    assert result["in_stock"] == 1
    assert result["rating"] == 4.9


def test_parse_single_card_alternative_id_and_prices(extractor):
    """2. Поиск ID через мета-тег, абсолютный URL, отсутствие скидки, рейтинг через мета-тег."""
    html = """
    <div>
        <meta itemprop="sku" content="777888" />
        <a href="https://external-link.com">Ссылка</a>
        <div class="_ga-price">5 000 ₽</div>
        <div class="_ga-price bnpl">1 250 ₽ х 4</div>
        <meta itemprop="ratingValue" content="4.5" />
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = extractor._parse_single_card(soup, "uniseks-aromaty")

    assert result is not None
    assert result["item_id"] == "777888"
    assert result["url"] == "https://external-link.com"
    assert result["brand"] == "Не указан"
    assert result["name"] == "Без названия"
    assert result["product_type"] == "Нет категории"
    assert result["current_price_rub"] == 5000.0
    assert result["old_price_rub"] == 5000.0  # Перетекло из текущей цены
    assert result["discount"] == 0.0
    assert result["rating"] == 4.5


def test_parse_single_card_banner_returns_none(extractor):
    """3. Если это рекламный баннер в сетке и у него нет никаких ID -> метод должен вернуть None."""
    html = """
    <div class="reklamny-banner">
        <a href="/promo">Купи три по цене двух!</a>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = extractor._parse_single_card(soup, "uniseks-aromaty")

    assert result is None


def test_parse_single_card_out_of_stock_by_status(extractor):
    """4. Товар отсутствует в наличии (проверка по тегу статуса)."""
    html = """
    <div storage-scroll-id="111">
        <div class="_ga-price">1 000 ₽</div>
        <span class="_ga-pdp-status">Ожидается</span>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = extractor._parse_single_card(soup, "uniseks-aromaty")

    assert result["in_stock"] == 0


def test_parse_single_card_out_of_stock_by_text(extractor):
    """5. Товар отсутствует в наличии (проверка по общему тексту карточки)."""
    html = """
    <div storage-scroll-id="222">
        <div class="_ga-price">1 000 ₽</div>
        <p>К сожалению, данного товара сейчас нет в наличии</p>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = extractor._parse_single_card(soup, "uniseks-aromaty")

    assert result["in_stock"] == 0


def test_parse_single_card_rating_value_error(extractor):
    """6. Некорректный формат рейтинга (проверка перехвата ValueError в ValueError исключениях)."""
    html = """
    <div storage-scroll-id="333">
        <div class="_ga-price">1 000 ₽</div>
        <div class="product-rating__rating-value">БИТЫЙ_РЕЙТИНГ</div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = extractor._parse_single_card(soup, "uniseks-aromaty")

    assert result["rating"] == 0.0


def test_parse_single_card_meta_rating_value_error(extractor):
    """7. Некорректный формат рейтинга в мета-тегах."""
    html = """
    <div storage-scroll-id="444">
        <div class="_ga-price">1 000 ₽</div>
        <meta itemprop="ratingValue" content="УЖАСНЫЙ_РЕЙТИНГ" />
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = extractor._parse_single_card(soup, "uniseks-aromaty")

    assert result["rating"] == 0.0


def test_parse_single_card_global_exception(extractor, monkeypatch):
    """8. Глобальный сбой метода (тестирование ветки except Exception)."""
    # Ломаем метод find у soup, чтобы он гарантированно выкинул ошибку
    html = "<div storage-scroll-id='555'></div>"
    soup = BeautifulSoup(html, "html.parser")

    def mock_find(*args, **kwargs):
        raise RuntimeError("Симулированная критическая ошибка DOM")

    monkeypatch.setattr(soup, "find", mock_find)

    result = extractor._parse_single_card(soup, "uniseks-aromaty")
    assert result is None

# Создаем поддельный конфиг, у которого точно есть атрибут keyword со слешами
class FakeConfigWithKeyword(BaseDBParsingConfig):
    keyword = "/parfjumerija/uniseks-aromaty/"

    def __init__(self):
        super().__init__(target_url="https://goldapple.ru", keyword="/parfjumerija/uniseks-aromaty/")

    @classmethod
    def get_full_schema(cls) -> Dict[str, str]:
        """Возвращает пустую схему для тестовых целей."""
        return {}


def test_extract_data_with_config_keyword():
    """1. Проверка очистки слага категории из конфигурации и фильтрации баннеров."""
    # Инициализируем экстрактор с конфигом, содержащим keyword
    extractor = GoldenAppleExtractor(config=FakeConfigWithKeyword())

    # Создаем две карточки: одна валидная, вторая — рекламный баннер без ID
    valid_card = BeautifulSoup(
        '<div storage-scroll-id="999"><div class="_ga-price">1 000 ₽</div></div>',
        "html.parser",
    )
    banner_card = BeautifulSoup(
        '<div class="banner">Реклама косметики</div>', "html.parser"
    )

    raw_content = [valid_card, banner_card]

    # Запускаем пакетный метод
    result = extractor.extract_data(raw_content)

    # Проверяем, что баннер отфильтровался (в списке только 1 элемент вместо 2)
    assert len(result) == 1
    # Проверяем, что слаг категории очистился от ведущих и замыкающих слешей
    assert result[0]["category"] == "parfjumerija/uniseks-aromaty"
    assert result[0]["item_id"] == "999"


def test_extract_data_with_default_category():
    """2. Проверка падения в дефолтный слаг 'Каталог', если у конфига нет keyword."""
    # Используем базовый класс конфигурации, у которого нет атрибута keyword
    extractor = GoldenAppleExtractor(config=BaseDBParsingConfig)

    valid_card = BeautifulSoup(
        '<div storage-scroll-id="777"><div class="_ga-price">500 ₽</div></div>',
        "html.parser",
    )

    result = extractor.extract_data([valid_card])

    assert len(result) == 1
    # Проверяем, что сработала ветка else/default и подставилось слово "Каталог"
    assert result[0]["category"] == "Каталог"
    assert result[0]["item_id"] == "777"


def test_extract_data_empty_input():
    """3. Проверка работы метода с абсолютно пустым списком карточек на входе."""
    extractor = GoldenAppleExtractor(config=BaseDBParsingConfig)

    result = extractor.extract_data([])

    # Должен вернуться пустой массив без падений по ошибкам
    assert isinstance(result, list)
    assert len(result) == 0