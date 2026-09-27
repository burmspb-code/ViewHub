import json
import shutil
from pathlib import Path
from typing import Any, Dict, List


from core.base_classes import BaseSaver


class JSONSaver(BaseSaver):
    """Сейвер для формата JSON с транзакционным бэкапом текущего состояния."""

    def __init__(self, file_name: str):
        # Вызываем конструктор базового класса для фиксации self.file_name
        super().__init__(file_name)
        # Привязываем пути строго к экземпляру класса
        self.file_path = (Path.cwd() / self.file_name).with_suffix(".json")
        self.backup_path = (Path.cwd() / self.file_name).with_suffix(".json.bak")
        self.is_file_init = False

    def save(self, data: List[Dict[str, Any]]) -> bool:
        if not data:
            return False

        # --- ТРАНЗАКЦИОННАЯ ЗАЩИТА: Бэкап перед каждым изменением файла ---
        if self.file_path.exists():
            try:
                # Если прошлый временный кэш остался на диске — удаляем его
                self.backup_path.unlink(missing_ok=True)
                # Копируем текущее стабильное состояние файла в бэкап
                shutil.copy2(self.file_path, self.backup_path)

                # Если это самый первый чанк НОВОЙ сессии парсинга — очищаем старый файл
                if not self.is_file_init:
                    self.file_path.unlink()
            except PermissionError as e:
                raise IOError(
                    f"❌ Не удалось сделать бэкап файла {self.file_name}. "
                    f"Убедитесь, что файл не заблокирован другими программами!"
                ) from e

        try:
            existing_data = []

            # Если файл существует и мы находимся внутри текущей сессии (флаг True),
            # считываем из него ранее накопленные в этой сессии чанки
            if self.file_path.exists() and self.file_path.stat().st_size > 0:
                with open(self.file_path, mode="r", encoding="utf-8") as f:
                    try:
                        existing_data = json.load(f)
                    except json.JSONDecodeError:
                        existing_data = []
            else:
                # Если файла на диске нет (или мы только что стерли его при старте сессии),
                # инициализируем его как пустой массив
                existing_data = []

            # Объединяем старый массив текущей сессии с новой порцией (чанком)
            existing_data.extend(data)

            # Записываем обновленный массив целиком
            with open(self.file_path, mode="w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)

            # --- УСПЕХ: Чанк успешно записан на диск, временный бэкап больше не нужен ---
            self.backup_path.unlink(missing_ok=True)
            self.is_file_init = True
            return True

        except Exception as e:
            # --- ОТКАТ: Запись упала, мгновенно восстанавливаем файл из бэкапа ---
            if self.backup_path.exists():
                # Удаляем поврежденный при записи файл
                self.file_path.unlink(missing_ok=True)
                # Восстанавливаем точную копию файла, сделанную прямо перед этим чанком
                shutil.copy2(self.backup_path, self.file_path)
                self.backup_path.unlink(missing_ok=True)

            raise IOError(f"Ошибка записи JSON (данные восстановлены до состояния перед чанком):\n{e}") from e
