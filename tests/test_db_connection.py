"""Тесты для работы с БД."""

import sys
import sqlite3
from typing import ClassVar
from pathlib import Path
from src.savers.sqlite_saver import SQLiteSaver
from core.base_classes import BaseDBParsingConfig

# Настройка пути для импортов
root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))


class MockConfig(BaseDBParsingConfig):
    """Тестовая конфигурация для проверки Сейвера."""

    # Указываем Сейверу поле для UPSERT дедупликации
    DEDUP_COLUMN: str = "product_id"

    # Описываем тестовые бизнес-колонки в нативном формате SQLite
    COLUMNS: ClassVar[dict[str, str]] = {
        "product_id": "INTEGER NOT NULL",
        "name": "TEXT NOT NULL",
        "price": "REAL",
        "in_stock": "INTEGER DEFAULT 0",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "session_id": "TEXT NOT NULL",
        "page_number": "INTEGER",
    }

    TABLE_CONSTRAINTS = ()

    @classmethod
    def get_key_column(cls) -> str:
        # Системным первичным ключом остается "id" из SYSTEM_COLUMNS
        return "id"

    @classmethod
    def get_full_schema(cls) -> dict[str, str]:
        """Явно собираем тестовую схему, переопределяя абстрактный метод."""
        return {**cls.SYSTEM_COLUMNS, **MockConfig.COLUMNS}


def test_sqlite_saver_full_flow():
    print("🚀 Запуск теста SQLiteSaver...")

    target_url = "https://test.site.com/products"
    keyword = "mock_test"

    saver = SQLiteSaver()

    # Инициализация: создаст БД, таблицу и проверит схему
    config = MockConfig(target_url, keyword)
    table_name = saver.init_for_config(config)
    print(f"✅ Таблица готова: {table_name}")

    db_path = saver.db_path
    assert db_path.exists(), f"❌ Файл базы данных не создан: {db_path}"
    print(f"✅ Файл БД найден: {db_path}")

    # Запоминаем session_id, который Сейвер сгенерировал автоматически при инициализации
    test_session_id = saver.session_id

    # Тестовые данные (приводим типы к SQLite: in_stock = 1 / 0)
    test_data = [
        {"product_id": 101, "name": "T-Shirt", "price": 19.99, "in_stock": 1},
        {"product_id": 102, "name": "Jeans", "price": 49.50, "in_stock": 0},
    ]

    # Добавляем номер страницы прямо в данные товаров перед сохранением
    for item in test_data:
        item["page_number"] = 1

    # Вызываем save без page_number. Метод возвращает количество записанных строк (int)
    result = saver.save(test_data)
    assert result == 2, f"❌ Ошибка сохранения. Ожидалось 2 строки, записано: {result}"
    print("✅ Данные успешно сохранены")

    # Тест на обновление (UPSERT): меняем имя и цену у product_id 101
    updated_data = [{"product_id": 101, "name": "T-Shirt Pro", "price": 24.99, "in_stock": 1}]

    # Добавляем номер страницы прямо в данные обновляемых товаров
    for item in updated_data:
        item["page_number"] = 2

    # Вызываем save без page_number. UPSERT должен успешно обновить 1 строку
    result_update = saver.save(updated_data)
    assert result_update == 1, f"❌ Ошибка обновления. Ожидалась 1 строка, записано: {result_update}"
    print("✅ Дубликат успешно обновлен (UPSERT сработал)")

    # --- БЛОК ПРОВЕРКИ ---
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()

        # 1. Получаем структуру таблицы
        cursor.execute(f'PRAGMA table_info("{table_name}")')
        columns_info = cursor.fetchall()

        # Извлекаем только имена колонок (второй элемент кортежа)
        col_names = [col[1] for col in columns_info]
        print(f"📋 Фактические колонки в БД: {col_names}")

        # 2. Проверка наличия обязательных колонок (защита от ошибок конфига)
        required_cols = ["product_id", "name", "price", "in_stock", "session_id"]
        missing_cols = [c for c in required_cols if c not in col_names]
        if missing_cols:
            raise ValueError(f"❌ В таблице отсутствуют обязательные колонки: {missing_cols}")

        # 3. Безопасное получение индексов колонок в выборке SELECT *
        try:
            idx_name = col_names.index("name")
            idx_price = col_names.index("price")
            idx_in_stock = col_names.index("in_stock")
            idx_session = col_names.index("session_id")
        except ValueError as e:
            raise ValueError(f"❌ Не удалось найти индекс колонки для проверки: {e}") from e

        # 4. Выбираем обновленные данные для проверки UPSERT
        cursor.execute(f'SELECT * FROM "{table_name}" WHERE product_id = ?', (101,)) # noqa: S608
        row = cursor.fetchone()
        assert row is not None, "❌ Данные не найдены в таблице"

        # 5. Проверки фактических значений в строке
        assert row[idx_name] == "T-Shirt Pro", (
            f"❌ Имя не обновилось. Ожидалось 'T-Shirt Pro', получено: {row[idx_name]}"
        )
        assert abs(row[idx_price] - 24.99) < 0.01, f"❌ Цена не обновилась. Ожидалось 24.99, получено: {row[idx_price]}"

        # В SQLite булевы значения хранятся как 1 (True) и 0 (False)
        assert row[idx_in_stock] == 1, (
            f"❌ Статус in_stock не сохранен корректно. Ожидалось 1, получено: {row[idx_in_stock]}"
        )
        assert row[idx_session] == test_session_id, (
            f"❌ session_id не совпадает. Ожидалось {test_session_id}, получено: {row[idx_session]}"
        )

        print("✅ Все проверки пройдены: данные корректны и обновлены")
    # ---------------------------------------

    print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")


if __name__ == "__main__":
    test_sqlite_saver_full_flow()
