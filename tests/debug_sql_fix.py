import sqlite3
import os

# Путь к базе данных
db_path = "data/viewhub_fixed.db"
os.makedirs(os.path.dirname(db_path), exist_ok=True)

# ИСПРАВЛЕННЫЙ SQL: PRIMARY KEY перенесен в самый конец, после всех колонок!
sql_content = """
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
)
"""

print(f"🗄 Пробуем создать базу (FIXED): {os.path.abspath(db_path)}")

try:
    # Подключаемся к БД
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Используем стандартный .execute() — теперь он сработает идеально!
        cursor.execute(sql_content)
        conn.commit()

        print("✅ ТАБЛИЦА УСПЕШНО СОЗДАНА через стандартный .execute()!")

        # Проверка структуры (Исправленный вывод)
        cursor.execute("PRAGMA table_info(goldapple_ru_parfjumerija_dlja_detej)")
        cols = cursor.fetchall()

        print(f"\n📋 Найдено колонок в БД: {len(cols)}")
        for c in cols:
            # c[1] — это имя колонки, c[2] — её тип данных
            print(f"   - {c[1]} ({c[2]})")

except Exception as e:
    print(f"❌ ОШИБКА: {e}")
