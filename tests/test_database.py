import pytest
import sqlite3

from src.database.sqlite_manager import DatabaseManager
from src.parsers_config.golden_apple_config import GoldenAppleConfig


@pytest.fixture
def db_manager(tmp_path):
    # tmp_path автоматически создаст уникальную временную папку на диске
    test_db_file = tmp_path / "test_data.db"

    class MockDataBaseManager(DatabaseManager):
        def _make_table_name(self, config) -> str:
            """Возвращаем фиксированное имя для проверки"""
            return "goldapple_ru_parfjumerija_novinki"

    return MockDataBaseManager(db_path=test_db_file)


@pytest.fixture
def config_db():
    """Формирует объект конфигурации с нужными атрибутами."""
    # Возвращаем реальный конфигурационный объект
    return GoldenAppleConfig


@pytest.fixture
def system_shema():
    """Формирует конфигурацию системных полей таблицы"""
    return {
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "session_id": "TEXT NOT NULL",
    }


@pytest.fixture
def business_shema():
    """Формирует кофигурацию полей бизнес-логики"""
    return {
        "item_id": "TEXT NOT NULL",
        "category": "TEXT",
        "brand": "TEXT",
        "name": "TEXT NOT NULL",
        "product_type": "TEXT",
        "old_price_rub": "REAL",
        "current_price_rub": "REAL",
        "discount": "REAL",
        "in_stock": "INTEGER DEFAULT 0",
        "rating": "REAL",
        "url": "TEXT",
        "catalog_page_url": "TEXT",
        "description": "TEXT",
        "usage": "TEXT",
        "country_of_origin": "TEXT",
        "page_number": "INTEGER",
    }


@pytest.fixture
def create_table_sql():
    return """CREATE TABLE IF NOT EXISTS goldapple_ru_parfjumerija_novinki (
        item_id TEXT NOT NULL,
        category TEXT,
        brand TEXT,
        name TEXT NOT NULL,
        product_type TEXT,
        old_price_rub REAL,
        current_price_rub REAL,
        discount REAL,
        in_stock INTEGER DEFAULT 0,
        rating REAL,
        url TEXT,
        catalog_page_url TEXT,
        description TEXT,
        usage TEXT,
        country_of_origin TEXT,
        page_number INTEGER
);"""


def test_connect(db_manager):
    """Проверяет, что соединение с БД установлено"""
    assert db_manager._connect() is not None


def test_skipped_tracks_failures_separately_from_real_data(db_manager, config_db):
    """
    Сбой парсера и пустое описание на сайте должны быть различимы.

    Товар с незагруженной карточкой попадает и в основную таблицу (с заглушкой
    "Описание отсутствует"), и в таблицу учёта сбоев. Товар, у которого сайт
    просто не публикует описание, в учёт не попадает — иначе список
    «незаполненных» оказался бы бесполезным.
    """
    db_manager.init_for_config(config_db)

    assert db_manager.save([{"item_id": "99000037750", "name": "Chanel", "description": "Описание отсутствует"}]) == 1
    assert db_manager.save_skipped([{"item_id": "99000037750", "reason": "карточка не загрузилась"}]) == 1

    skipped = db_manager.get_skipped()

    assert len(skipped) == 1
    assert skipped[0]["item_id"] == "99000037750"
    assert skipped[0]["reason"] == "карточка не загрузилась"
    assert skipped[0]["attempts"] == 1


def test_skipped_repeat_failure_increments_attempts(db_manager, config_db):
    """Повторный сбой того же товара не плодит дубли, а растёт счётчик попыток."""
    db_manager.init_for_config(config_db)

    db_manager.save_skipped([{"item_id": "1", "reason": "таймаут"}])
    db_manager.save_skipped([{"item_id": "1", "reason": "таймаут, HTTP 503"}])
    db_manager.save_skipped([{"item_id": "2", "reason": "битая ссылка"}])

    skipped = {row["item_id"]: row for row in db_manager.get_skipped()}

    assert set(skipped) == {"1", "2"}
    assert skipped["1"]["attempts"] == 2
    assert skipped["1"]["reason"] == "таймаут, HTTP 503"
    assert skipped["2"]["attempts"] == 1


def test_skipped_table_absent_returns_empty_list(db_manager, config_db):
    """До первого сбоя таблицы учёта нет — чтение не должно падать."""
    db_manager.init_for_config(config_db)

    assert db_manager.get_skipped() == []


def test_skipped_ignores_rows_without_item_id(db_manager, config_db):
    """Товар без артикула в учёт не пишется: по нему нельзя ничего найти."""
    db_manager.init_for_config(config_db)

    assert db_manager.save_skipped([{"item_id": "", "reason": "мусор"}, {"item_id": None}]) == 0
    assert db_manager.get_skipped() == []


def test_skipped_stores_url_for_manual_review(db_manager, config_db):
    """URL обязателен: по нему пользователь откроет карточку вручную."""
    db_manager.init_for_config(config_db)

    db_manager.save_skipped(
        [
            {
                "item_id": "99000037750",
                "url": "https://goldapple.ru/catalog/parfjumerija/uniseks-aromaty-chanel-99000037750/",
                "brand": "Chanel",
                "name": "Coco Mademoiselle",
                "page_number": 3,
                "reason": "карточка не загрузилась",
            }
        ]
    )

    row = db_manager.get_skipped()[0]

    assert row["url"].endswith("99000037750/")
    assert row["brand"] == "Chanel"
    assert row["page_number"] == 3


def test_skipped_table_name_is_suffixed_and_fits_sqlite_limit(db_manager, config_db):
    """Имя таблицы учёта не должно превышать лимит SQLite в 63 символа."""
    db_manager.init_for_config(config_db)

    name = db_manager.skipped_table_name()

    assert name.endswith("_skipped")
    assert len(name) <= DatabaseManager.MAX_IDENTIFIER_LENGTH


def test_clear_skipped_empties_accounting(db_manager, config_db):
    """Очистка сбрасывает учёт, но не трогает основную таблицу товаров."""
    db_manager.init_for_config(config_db)
    db_manager.save([{"item_id": "1", "name": "A"}])
    db_manager.save_skipped([{"item_id": "1", "reason": "таймаут"}])

    db_manager.clear_skipped()

    assert db_manager.get_skipped() == []


def test_make_table_name(db_manager, config_db):
    """Проверяет, что имя таблицы формируется корректно"""
    result = db_manager._make_table_name(config_db)

    # Проверяем финальную строчку
    assert result == "goldapple_ru_parfjumerija_novinki"


def test_golden_apple_config_structure():
    """Проверяет базовую структуру конфигурации и типы данных."""
    # Проверка, что DEDUP_COLUMN указывает на существующую бизнес-колонку
    assert GoldenAppleConfig.DEDUP_COLUMN in GoldenAppleConfig.BUSINESS_COLUMNS
    assert GoldenAppleConfig.DEDUP_COLUMN == "item_id"

    # Проверка типов основных полей
    assert isinstance(GoldenAppleConfig.BUSINESS_COLUMNS, dict)
    assert GoldenAppleConfig.BUSINESS_COLUMNS["item_id"] == "TEXT NOT NULL"
    assert GoldenAppleConfig.BUSINESS_COLUMNS["in_stock"] == "INTEGER DEFAULT 0"


def test_get_full_schema_merging(system_shema, business_shema):
    """Проверяет правильность объединения системных и бизнес-колонок."""
    full_schema = GoldenAppleConfig.get_full_schema()

    # Проверяем правльность распаковки полей таблицы
    assert full_schema == {**system_shema, **business_shema}

    # Схема должна содержать ключи из обоих словарей
    for sys_col in GoldenAppleConfig.SYSTEM_COLUMNS:
        assert sys_col in full_schema
        assert full_schema[sys_col] == GoldenAppleConfig.SYSTEM_COLUMNS[sys_col]

    for bus_col in GoldenAppleConfig.BUSINESS_COLUMNS:
        assert bus_col in full_schema
        assert full_schema[bus_col] == GoldenAppleConfig.BUSINESS_COLUMNS[bus_col]

    # Общий размер должен быть равен сумме длин без пересечений
    expected_len = len(GoldenAppleConfig.SYSTEM_COLUMNS) + len(GoldenAppleConfig.BUSINESS_COLUMNS)
    assert len(full_schema) == expected_len


def test_build_create_sql_executes_successfully(db_manager, config_db):
    """
    Архитектурный тест: проверяет, что генерируемый SQL-запрос
    валиден для SQLite и создает таблицу с правильной структурой.
    """
    # 1. Генерируем SQL динамически на основе РЕАЛЬНОГО конфигуратора
    sql_request = db_manager._build_create_sql(config_db)

    # 2. Создаем чистую БД в оперативной памяти для проверки синтаксиса
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()

    # Если синтаксис SQL нарушен (кавычки, запятые), код упадет прямо здесь
    cursor.execute(sql_request)

    # 3. Извлекаем информацию о созданной таблице из внутренностей SQLite
    table_name = db_manager._make_table_name(config_db)
    cursor.execute(f"PRAGMA table_info('{table_name}');")
    columns_in_db = cursor.fetchall()

    # Структура ответа PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
    db_column_names = [col[1] for col in columns_in_db]

    # 4. Проверяем, что все бизнес-колонки из конфигуратора физически создались в БД
    expected_schema = config_db.get_full_schema()
    for expected_col in expected_schema.keys():
        assert expected_col in db_column_names, f"Колонка {expected_col} не была создана в БД!"

    conn.close()
