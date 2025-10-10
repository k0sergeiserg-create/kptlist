import shutil
import os
from datetime import datetime


def update_schedule_files():
    # Создаем backup старого файла
    backup_dir = "backup"
    os.makedirs(backup_dir, exist_ok=True)

    files_to_update = [
        "data/schedule_1course.xlsx",
        "data/schedule_2course.xlsx",
        "data/schedule_3course.xlsx",
        "data/schedule_4course.xlsx"
    ]

    for file_path in files_to_update:
        if os.path.exists(file_path):
            # Создаем backup с timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{backup_dir}/{os.path.basename(file_path)}_{timestamp}.backup"
            shutil.copy2(file_path, backup_name)

            # Заменяем файл (Windows разрешает замену используемых файлов)
            new_file = f"new_{file_path}"
            if os.path.exists(new_file):
                os.replace(new_file, file_path)
                print(f"✅ Обновлен: {file_path}")

    print("🔄 Файлы расписания обновлены!")


if __name__ == "__main__":
    update_schedule_files()
