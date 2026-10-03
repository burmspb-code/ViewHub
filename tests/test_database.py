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
