import json
import os
import time
from typing import Optional, Dict, Any


class UserManager:
    def __init__(self):
        self.users_file = "users_data.json"

    def get_file_update_time(self, course):  # ← УБРАТЬ @staticmethod
        """Получает время изменения файла"""
        from config import EXCEL_URLS
        file_path = EXCEL_URLS.get(course)
        if file_path and os.path.exists(file_path):
            return os.path.getmtime(file_path)
        return 0

    def save_user_choice(self, user_id: int, course: str, group: str) -> None:
        users_data = self.load_all_users()
        users_data[str(user_id)] = {
            "course": course,
            "group": group,
            "last_update_time": time.time(),
            "file_update_time": self.get_file_update_time(course)
        }

        with open(self.users_file, 'w', encoding='utf-8') as f:
            json.dump(users_data, f, ensure_ascii=False, indent=2)

    def get_user_choice(self, user_id: int) -> Optional[Dict[str, Any]]:
        users_data = self.load_all_users()
        return users_data.get(str(user_id))

    def should_update_schedule(self, user_id, course):
        """Проверяет нужно ли обновить расписание"""
        user_data = self.get_user_choice(user_id)
        if not user_data:
            return True

        user_time = user_data.get("file_update_time", 0)
        file_time = self.get_file_update_time(course)

        print(f"📊 Сравнение времени: user={user_time}, file={file_time}, update={file_time > user_time}")
        return file_time > user_time

    def load_all_users(self) -> Dict[str, Any]:
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
