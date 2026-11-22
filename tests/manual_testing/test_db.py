"""Тест создания БД."""

import sqlite3
from pathlib import Path

# Путь к базе
db_path = Path("../data", "viewhub_test.db")
db_path.parent.mkdir(parents=True, exist_ok=True)

# SQL запрос
sql = """
CREATE TABLE IF NOT EXISTS "goldapple_ru_parfjumerija_dlja_detej" (
    "item_id" TEXT NOT NULL,
    "category" TEXT,
    "brand" TEXT,
    "name" TEXT NOT NULL,
    "product_type" TEXT,
    "old_price_rub" REAL,
    "current_price_rub" REAL,
    "discount" REAL,
    "in_stock" INTEGER,
    "rating" REAL,
    "url" TEXT,
    "catalog_page_url" TEXT,
    "description" TEXT,
    "usage" TEXT,
    "country_of_origin" TEXT,
    "created_at" TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "page_number" INTEGER,
    "session_id" TEXT NOT NULL,
    PRIMARY KEY (item_id)
)
"""

conn = None
print(f"🗄 Создаю базу в: {db_path.absolute()}")
print("📜 Выполняю SQL напрямую...")

try:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(sql)
    conn.commit()
    print("✅ УСПЕХ! Таблица создана напрямую через sqlite3.")

    # Проверка: выведем структуру
    cursor = conn.execute("PRAGMA table_info(goldapple_ru_parfjumerija_dlja_detej)")
    print("\n📋 Структура таблицы:")
    for row in cursor.fetchall():
        print(row)

except Exception as e:
    print(f"❌ КРИТИЧЕСКАЯ ОШИБКА ПРИ ПРЯМОМ ЗАПУСКЕ: {e}")
    raise
finally:
    conn.close()
