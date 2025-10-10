import os
import re
import tempfile
from typing import Optional, Dict, Any, List
import requests
from openpyxl import load_workbook
from openpyxl.cell import Cell

from config import LESSON_TIMES, GROUP_CODES


class ExcelParser:
    def __init__(self):
        self.temp_files: List[str] = []

    def download_excel(self, url: str) -> Optional[str]:
        try:
            if url.startswith('http'):
                response = requests.get(url, timeout=30)
                response.raise_for_status()

                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
                temp_file.write(response.content)
                temp_file.close()

                self.temp_files.append(temp_file.name)
                return temp_file.name
            else:
                # Для локальных файлов - создаем копию
                if os.path.exists(url):
                    import shutil  # ← импорт внутри метода
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
                    shutil.copy2(url, temp_file.name)  # ← правильный отступ
                    self.temp_files.append(temp_file.name)
                    return temp_file.name
                return None
        except Exception as e:
            print(f"❌ Ошибка загрузки: {e}")
            return None

    def cleanup_temp_files(self) -> None:
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception as e:
                print(f"⚠️ Не удалось удалить временный файл: {e}")
        self.temp_files.clear()

    @staticmethod
    def get_cell_color_type(cell: Cell) -> str:
        try:
            if cell.fill.start_color and cell.fill.start_color.index == 9:
                return "distant"  # Единственная цветная ячейка
            return "normal"
        except (AttributeError, TypeError, ValueError):
            return "normal"

    @staticmethod
    def is_valid_group_name(group_name: str) -> bool:
        """Проверяет, является ли текст названием группы"""
        text = str(group_name).strip()

        # Пропускаем пустые
        if not text:
            return False

        # Пропускаем очевидные не-группы
        if any(word in text.lower() for word in ['расписание', 'занятий', 'семестр', 'учебный', 'год', '№']):
            return False

        # Группы обычно содержат буквы и цифры, короткие
        if len(text) > 15:
            return False

        # Должны быть и буквы и цифры
        has_letters = any(c.isalpha() for c in text)
        has_digits = any(c.isdigit() for c in text)

        return has_letters and has_digits

    @staticmethod
    def is_group_in_course(group_name: str, course: str) -> bool:
        """Проверяет, принадлежит ли группа к курсу по буквенному коду"""
        group_codes = GROUP_CODES.get(course, [])
        group_name_str = str(group_name).upper().strip()

        # Ищем любой из кодов групп в названии
        for code in group_codes:
            if code.upper() in group_name_str:
                return True
        return False

    def find_groups_in_excel(self, excel_content: str, course: str) -> List[str]:
        try:
            print(f"🔍 Ищу группы для курса: {course}")
            excel_path = self.download_excel(excel_content)
            if not excel_path:
                return []

            wb = load_workbook(excel_path)
            ws = wb.active

            groups = []
            # Ищем в строке 6 (с колонки 4, после "№")
            for col in range(4, ws.max_column + 1):
                cell_value = ws.cell(row=6, column=col).value
                if cell_value:
                    group_name = str(cell_value).strip()
                    print(f"🎯 Строка 6, колонка {col}: '{group_name}'")

                    if group_name and group_name != "№":
                        is_valid = self.is_valid_group_name(group_name)
                        in_course = self.is_group_in_course(group_name, course)
                        print(f"   ✅ Валидна: {is_valid}, В курсе: {in_course}")

                        if is_valid and in_course:
                            groups.append(group_name)
                            print(f"   🎯 ДОБАВЛЕНА ГРУППА: {group_name}")

            print(f"📋 Итоговый список групп: {groups}")
            wb.close()
            return groups

        except Exception as e:
            print(f"❌ Ошибка поиска групп: {e}")
            return []
        finally:
            if excel_content.startswith('http'):
                self.cleanup_temp_files()

    def get_group_schedule(self, excel_content: str, group_name: str) -> Optional[Dict[str, Any]]:
        try:
            total_lessons = 0
            distant_lessons = 0
            self_study_lessons = 0
            normal_lessons = 0
            current_day = "Понедельник"
            excel_path = self.download_excel(excel_content)
            if not excel_path:
                return None

            wb = load_workbook(excel_path)
            ws = wb.active

            # Ищем группу в строке 6
            group_col = None
            for col in range(4, ws.max_column + 1):  # с колонки D
                cell_value = ws.cell(row=6, column=col).value
                if cell_value and group_name.upper() in str(cell_value).upper():
                    group_col = col
                    print(f"✅ Найдена группа '{group_name}' в колонке {col}")
                    break

            if not group_col:
                return None

            schedule = {}
            _current_day = "Понедельник"

            # Парсим начиная со строки 7
            for row in range(7, ws.max_row + 1):
                day_cell = ws.cell(row=row, column=1)  # ячейка дня
                time_cell = ws.cell(row=row, column=2)  # ячейка времени
                lesson_num_cell = ws.cell(row=row, column=3)  # ячейка номера пары
                lesson_cell = ws.cell(row=row, column=group_col)  # ячейка предмета

                # Обновляем текущий день
                if day_cell.value and str(day_cell.value).strip():
                    current_day = str(day_cell.value).strip().split()[0]  # "Среда 8 октября" → "Среда"

                if not lesson_num_cell.value:
                    continue

                try:
                    lesson_num = int(lesson_num_cell.value)
                except (ValueError, TypeError):
                    continue

                color_type = self.get_cell_color_type(lesson_cell)  # передаем ячейку для цвета

                # Обновляем счетчики
                if lesson_cell.value and str(lesson_cell.value).strip():
                    total_lessons += 1
                    if color_type == "distant":
                        distant_lessons += 1
                    elif color_type == "self_study":
                        self_study_lessons += 1
                    else:
                        normal_lessons += 1

                if lesson_cell.value and str(lesson_cell.value).strip():
                    lesson_text = str(lesson_cell.value).strip()
                    parsed = self.parse_lesson_text(lesson_text)

                    print(f"📝 Строка {row}: '{lesson_text}' → {parsed}")  # отладка

                    # Форматируем текст
                    if color_type == "distant":
                        subject_text = f"💻 {parsed['subject']} (дистант)"
                    elif color_type == "self_study":
                        subject_text = f"📚 {parsed['subject']} (самостоятельная)"
                    else:
                        subject_text = parsed['subject']

                    # Получаем время
                    lesson_time = str(time_cell.value).strip() if time_cell.value else self.get_lesson_time(lesson_num)

                    schedule[lesson_num] = {
                        "day": current_day,
                        "time": lesson_time,
                        "subject": subject_text,
                        "teacher": parsed["teacher"],
                        "room": parsed["room"],
                        "color_type": color_type,
                        "subgroup": parsed.get("subgroup", "")
                    }
                else:
                    lesson_time = str(time_cell.value).strip() if time_cell.value else self.get_lesson_time(lesson_num)
                    schedule[lesson_num] = {
                        "day": current_day,
                        "time": lesson_time,
                        "subject": "❌ Нет пары",
                        "teacher": "",
                        "room": "",
                        "color_type": "normal",
                        "subgroup": ""
                    }

            wb.close()

            # Создаем статистику
            stats_data = {
                "total": total_lessons,
                "distant": distant_lessons,
                "self_study": self_study_lessons,
                "normal": normal_lessons
            }

            print(f"📊 Расписание собрано: {len(schedule)} пар")

            return {
                "schedule": schedule,
                "stats": stats_data
            }

        except Exception as e:
            print(f"❌ Ошибка парсинга расписания: {e}")
            return None
        finally:
            if excel_content.startswith('http'):
                self.cleanup_temp_files()

    @staticmethod
    def parse_lesson_text(lesson_text: str) -> Dict[str, str]:
        """Финальный улучшенный парсер"""
        text = str(lesson_text).strip()

        if not text:
            return {"subject": "❌ Нет пары", "teacher": "", "room": "", "subgroup": ""}

        # Обработка специальных занятий
        special_lessons = {
            'разговор о важном': '💬 Занятие "Разговор о важном"'
        }

        text_lower = text.lower()
        for pattern, replacement in special_lessons.items():
            if pattern in text_lower:
                return {
                    "subject": replacement,
                    "teacher": "Внеурочное",
                    "room": "?",
                    "subgroup": ""
                }

        # Очищаем текст
        text = ' '.join(text.split())
        print(f"🔍 Начало парсинга: '{text}'")

        # 1. Сначала ищем подгруппы
        subgroup = ""
        subgroup_patterns = [
            r'(\d\s?и\s?\d\s?[п]?од?гр?)',
            r'(\d\s?[п]?од?гр?)',
        ]

        for pattern in subgroup_patterns:
            subgroup_match = re.search(pattern, text, re.IGNORECASE)
            if subgroup_match:
                subgroup = subgroup_match.group(1)
                subgroup = re.sub(r'(\d)([а-я])', r'\1 \2', subgroup)
                subgroup = re.sub(r'(\d)(и)(\d)', r'\1 \2 \3', subgroup)
                subgroup = re.sub(r'\s+', ' ', subgroup).strip()
                text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
                break

        print(f"📌 Подгруппа: '{subgroup}'")

        # 2. Ищем аудитории
        rooms = []
        room_pattern = r'\b(\d{2,4}[A-ZА-Я]?)\b'
        room_matches = re.findall(room_pattern, text)

        for room_match in room_matches:
            if 2 <= len(room_match) <= 5:
                rooms.append(room_match)
                text = re.sub(r'\b' + re.escape(room_match) + r'\b', ' ', text).strip()

        print(f"📍 Аудитории: {rooms}")

        # 3. Специальные помещения
        special_rooms = ['зал', 'библиотека', 'чит', 'актовый', 'спортзал', 'стадион']
        for room_word in special_rooms:
            if room_word in text.lower():
                rooms.append(room_word.capitalize())
                text = re.sub(room_word, ' ', text, flags=re.IGNORECASE).strip()

        # 4. Список известных преподавателей (расширенный)
        known_teachers = [
            'Шпейт', 'Таран', 'Морозова', 'Соколова', 'Олешкевич', 'Догадин',
            'Денисов', 'Зыкова', 'Лобанов', 'Коротков', 'Бухатиева', 'Коврижных',
            'Гоголева', 'Губич'  # ← ДОБАВЛЕНЫ НОВЫЕ ПРЕПОДАВАТЕЛИ
        ]

        # 5. Ищем ТОЛЬКО известных преподавателей
        teachers = []
        words = text.split()

        for word in words:
            word_clean = re.sub(r'[^А-Яа-я]', '', word)

            # Ищем только известных преподавателей
            if word_clean in known_teachers:
                teachers.append(word_clean)
                text = text.replace(word, ' ', 1).strip()

        print(f"👨‍🏫 Преподаватели: {teachers}")

        # 6. Собираем оставшийся текст - это предмет
        subject = ' '.join(text.split()).strip()

        # Очистка предмета
        subject = re.sub(r'^[,\s\-–—()]+|[,\s\-–—()]+$', '', subject)
        subject = re.sub(r'\s+', ' ', subject)

        # 7. Формируем результат
        final_subject = subject if subject else "?"
        final_teacher = ", ".join(teachers) if teachers else ""
        final_room = ", ".join(rooms) if rooms else ""

        print(f"🎯 Результат: subject='{final_subject}', teacher='{final_teacher}', "
              f"room='{final_room}', subgroup='{subgroup}'")

        return {
            "subject": final_subject,
            "teacher": final_teacher,
            "room": final_room,
            "subgroup": subgroup
        }

    @staticmethod
    def _parse_single_subject(text: str, subgroup: str = "") -> Dict[str, str]:
        """Парсит один предмет с преподавателем и аудиторией"""
        if not text:
            return {"subject": "?", "teacher": "", "room": "", "subgroup": subgroup}

        # Ищем аудиторию (цифры 2-4 знака с возможной буквой в конце)
        room = "?"
        room_pattern = r'(\d{2,4}[A-ZА-Я]?\b)'
        room_match = re.search(room_pattern, text)
        if room_match:
            room = room_match.group(1)
            text = re.sub(room_pattern, '', text).strip()

        # Ищем специальные помещения
        special_rooms = ['зал', 'библиотека', 'чит', 'актовый', 'спортзал', 'стадион']
        for room_word in special_rooms:
            if room_word in text.lower():
                room = room_word.capitalize()
                text = re.sub(room_word, '', text, flags=re.IGNORECASE).strip()
                break

        # Ищем преподавателя (слова с заглавной буквы, состоящие из букв)
        teacher = ""
        words = text.split()
        teacher_words = []
        remaining_words = []

        for word in words:
            if (len(word) > 2 and
                    word[0].isupper() and
                    word.isalpha() and
                    word.lower() not in ['зал', 'библиотека', 'чит', 'актовый', 'пдгр', 'подгр'] and
                    not any(special_room in word.lower() for special_room in special_rooms)):
                teacher_words.append(word)
            else:
                remaining_words.append(word)

        if teacher_words:
            teacher = " ".join(teacher_words)
            # Убираем преподавателя из текста
            text = ' '.join(remaining_words).strip()

        # Оставшийся текст - это предмет
        subject = text.strip()

        # Очистка от лишних символов
        subject = re.sub(r'^[,\s-]+|[,\s-]+$', '', subject)

        return {
            "subject": subject if subject else "?",
            "teacher": teacher,
            "room": room,
            "subgroup": subgroup
        }

    @staticmethod
    def get_lesson_time(lesson_num: int) -> str:
        return LESSON_TIMES.get(lesson_num, "?")
