from pathlib import Path
from typing import Any, Dict, List, Set

import sqlite3

from parent_base_classes import BaseConfig, BaseSaver


class SqliteSaver(BaseSaver):
    """Сохраняет записи в SQLite-базу со схемой из конфигуратора."""

    def __init__(self, config: BaseConfig, db_dir: str = "data") -> None:
        super().__init__(config.file_name)
        self.config = config

        # 1. Папка для базы (SQLite не создаёт промежуточные директории сам)
        Path(db_dir).mkdir(parents=True, exist_ok=True)

        # 2. Имя базы из file_name конфига, например, "golden_apple" → data/golden_apple.db
        db_path = Path(db_dir) / f"{Path(config.file_name).stem}.db"

        # 3. Подключение (файл создаётся автоматически) + WAL для устойчивости
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")

        # 4. Таблица строится из конфига — схема зашита в GoldenAppleConfig
        cols_sql = ",\n                ".join(
            f"{name} {sql_type}" for name, sql_type in config.COLUMNS.items()
        )
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS items (
                {cols_sql},
                UNIQUE ({config.KEY_COLUMN})
            )
        """)
        self.conn.commit()

    def save(self, data: List[Dict[str, Any]]) -> bool:
        """Сохраняет чанк записей. Дубли по KEY_COLUMN молча пропускаются."""
        if not data:
            return True
        columns = list(self.config.COLUMNS)
        placeholders = ", ".join("?" * len(columns))
        rows = [tuple(item.get(col) for col in columns) for item in data]
        with self.conn:
            self.conn.executemany(
                f"INSERT OR IGNORE INTO items ({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                rows,
            )
        return True

    def done_urls(self) -> Set[str]:
        """URL-ы страниц, по которым уже есть записи, — фундамент resume."""
        url_col = self.config.PAGE_URL_COLUMN
        return {
            row[0]
            for row in self.conn.execute(f"SELECT DISTINCT {url_col} FROM items")
        }

    def close(self) -> None:
        """Явно закрывает соединение (вызывать при завершении работы воркера)."""
        self.conn.close()
