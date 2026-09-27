import sys
import uuid
import sqlite3
from typing import ClassVar
from pathlib import Path
from src.savers.sqlite_saver import SQLiteSaver
from core.base_classes import BaseConfig

# Настройка пути для импортов
root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))


class MockConfig(BaseConfig):
    target_url = "https://test.site.com/products"
    keyword = "mock_test"

    COLUMNS: ClassVar[dict[str, type | str]] = {
        "product_id": int,  # Авто превратится в INTEGER
        "name": str,  # Авто превратится в TEXT
        "price": float,  # Авто превратится в REAL
        "in_stock": bool,  # Авто превратится в INTEGER
        # Для служебных полей можно оставить явные строки, если нужны спец. ограничения
        "created_at": "DATETIME NOT NULL",
        "session_id": "TEXT NOT NULL",
        "page_number": int,
    }


    # PRIMARY KEY теперь можно вынести в TABLE_CONSTRAINTS или оставить в get_key_column
    TABLE_CONSTRAINTS = ("PRIMARY KEY (product_id)",)


    @classmethod
    def get_key_column(cls) -> str:
        # Явно возвращаем имя ключевой колонки
        return "product_id"


def test_sqlite_saver_full_flow():
    print("🚀 Запуск теста SQLiteSaver...")

    saver = SQLiteSaver()
    test_session_id = str(uuid.uuid4())[:12]

    # Инициализация: создаст БД, таблицу и проверит схему
    config = MockConfig()
    table_name = saver.init_for_config(config, session_id=test_session_id)
    print(f"✅ Таблица готова: {table_name}")

    db_path = saver.db_path
    assert db_path.exists(), f"❌ Файл базы данных не создан: {db_path}"
    print(f"✅ Файл БД найден: {db_path}")

    # Тестовые данные (без служебных полей - они добавятся автоматически)
    test_data = [
        {"product_id": 101, "name": "T-Shirt", "price": 19.99, "in_stock": True},
        {"product_id": 102, "name": "Jeans", "price": 49.50, "in_stock": False},
    ]

    result = saver.save(test_data, page_number=1)
    assert result is True, "❌ Ошибка при сохранении данных"
    print("✅ Данные успешно сохранены")

    # Тест на обновление (UPSERT): меняем имя и цену у product_id 101
    updated_data = [{"product_id": 101, "name": "T-Shirt Pro", "price": 24.99, "in_stock": True}]

    result_update = saver.save(updated_data, page_number=2)
    assert result_update is True, "❌ Ошибка при обновлении дубликата"
    print("✅ Дубликат успешно обновлен (UPSERT сработал)")

    # --- БЛОК ПРОВЕРКИ (ИСПРАВЛЕННЫЙ) ---
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

        # 3. Безопасное получение индексов (если вдруг колонка исчезнет, тут будет понятная ошибка)
        try:
            idx_name = col_names.index("name")
            idx_price = col_names.index("price")
            idx_in_stock = col_names.index("in_stock")
            idx_session = col_names.index("session_id")
            # idx_product_id = col_names.index("product_id")
        except ValueError as e:
            raise ValueError(f"❌ Не удалось найти индекс колонки для проверки: {e}") from e

        # 4. Выбираем данные
        cursor.execute(f'SELECT * FROM "{table_name}" WHERE product_id = ?', (101,)) # noqa: S608
        row = cursor.fetchone()
        assert row is not None, "❌ Данные не найдены в таблице"

        # 5. Проверки значений
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
