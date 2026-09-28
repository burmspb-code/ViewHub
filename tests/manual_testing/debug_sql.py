"""Тест создания БД."""

import sqlite3
import os

# Путь к базе (скопируй тот, который реально используется в проекте)
db_path = "../data/viewhub.db"

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
    PRIMARY KEY ("item_id")
);
"""

print(f"🗄 Пробуем создать базу: {os.path.abspath(db_path)}")
print("📜 SQL строка (длина):", len(sql))

try:
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        print("✅ ТАБЛИЦА УСПЕШНО СОЗДАНА!")
except Exception as e:
    print(f"❌ ОШИБКА: {e}")
    # Выведем первые 200 символов SQL, чтобы убедиться, что он не изменился
    print("🔍 Первые 200 символов SQL:", sql[:200])

