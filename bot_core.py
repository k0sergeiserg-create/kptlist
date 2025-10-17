import logging

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config import BOT_TOKEN, EXCEL_URLS
from exel_parser import ExcelParser
from user_manager import UserManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class ScheduleBot:
    def __init__(self):
        logging.info("✅ Инициализация ScheduleBot...")

        # Менеджер пользователей (хранит выбор группы/курса/базы)
        self.user_manager = UserManager()

        # Парсер Excel-файлов для расписания
        self.parser = ExcelParser()

        # Временные данные для выбора курса/группы
        self.temp_data = {}

    # 🔥 NEW: выбор базы (9/11)
    @staticmethod
    def get_base_keyboard() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup([
            [KeyboardButton("🧑‍🏫 9 классов"), KeyboardButton("🎓 11 классов")]
        ], resize_keyboard=True)

    def get_courses_keyboard(self, with_back=False):
        # Берём временные данные текущего пользователя
        # (эта функция вызывается только после того, как base уже выбран)
        # user_id в неё не передаётся
        base = None
        if self.temp_data:
            # Берём первый user_id из словаря (так как эта клавиатура всегда строится для активного пользователя)
            any_user = next(iter(self.temp_data))
            base = self.temp_data[any_user].get("base", "9")

        if base == "11":
            buttons = ["1 курс", "2 курс", "3 курс"]
        else:
            buttons = ["1 курс", "2 курс", "3 курс", "4 курс"]

        if with_back:
            buttons.append("⬅️ Вернуться")

        return ReplyKeyboardMarkup([[b] for b in buttons], resize_keyboard=True)

    @staticmethod
    def get_groups_keyboard(groups: list, with_back: bool = True) -> ReplyKeyboardMarkup:
        keyboard = []

        # Гарантируем, что groups — список строк
        groups = [str(g) for g in groups]

        for i in range(0, len(groups), 3):
            keyboard.append([KeyboardButton(group) for group in groups[i:i + 3]])
        if with_back:
            keyboard.append([KeyboardButton("⬅️ Вернуться")])
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    @staticmethod
    def get_main_keyboard() -> ReplyKeyboardMarkup:
        keyboard = [
            [KeyboardButton("📅 Получить расписание")],
            [KeyboardButton("🔄 Сменить группу")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # 🔄 MODIFIED: /start теперь спрашивает базу при отсутствии сохранённых данных
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        saved_choice = self.user_manager.get_user_choice(user_id)

        print(f"🔍 START: user_id={user_id}, saved_choice={saved_choice}")

        if saved_choice and saved_choice.get("course") and saved_choice.get("group") and saved_choice.get("base"):
            # проверяем время обновления файла, но учитываем, что для базы 11 реальные файлы могут быть на курс +1
            excel_course = self._compute_excel_course(saved_choice["course"], saved_choice["base"])
            should_update = self.user_manager.should_update_schedule(user_id, excel_course)
            print(f"🔄 Проверка обновления: {should_update} (excel_course={excel_course})")

            if should_update:
                print("🎯 ОБНОВЛЕНИЕ НАЙДЕНО! Сохраняем новую версию...")
                # Сохраняем заново текущее значение (обновим file_update_time)
                self.user_manager.save_user_choice(user_id, saved_choice["course"], saved_choice["group"],
                                                   saved_choice["base"])
                await update.message.reply_text(
                    f"🔄 **Обновление расписания!**\n"
                    f"Твоя группа: {saved_choice['group']}\n"
                    f"Загружено новое расписание!\n\n"
                    f"Используй кнопки ниже:",
                    reply_markup=self.get_main_keyboard(),
                    parse_mode='Markdown'
                )
                return

            await update.message.reply_text(
                f"👋 С возвращением!\nТвоя группа: {saved_choice['group']}\nИспользуй кнопки ниже:",
                reply_markup=self.get_main_keyboard()
            )
        else:
            # 🔥 NEW: просим выбрать базу (9/11)
            await update.message.reply_text(
                "🎓 Бот расписания Политеха\n\nВыбери свою базу обучения:",
                reply_markup=self.get_base_keyboard()
            )

    # 🔥 NEW: Обработка выбора базы (9/11)
    async def handle_base_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = update.message.text
        user_id = update.effective_user.id

        base = None
        if text.startswith("🧑‍🏫") or "9" in text:
            base = "9"
        elif text.startswith("🎓") or "11" in text:
            base = "11"

        if not base:
            await update.message.reply_text("❌ Неверный выбор. Выбери базу обучения:",
                                            reply_markup=self.get_base_keyboard())
            return

        # сохраняем в temp_data, дальше после выбора курса/группы запишем в UserManager
        self.temp_data[user_id] = {"base": base}
        await update.message.reply_text(f"Вы выбрали базу: {base}. Теперь выбери курс:",
                                        reply_markup=self.get_courses_keyboard(with_back=True   ))

    # 🔄 MODIFIED: при выборе курса учитываем базу и выбираем файл excel корректно (для базы 11 используем курс+1)
    async def handle_course_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        course_text = update.message.text  # Например "2 курс"

        # Назад → возвращаемся к выбору базы
        if course_text == "⬅️ Вернуться":
            self.temp_data[user_id] = {}
            await update.message.reply_text("Выбери базу обучения:", reply_markup=self.get_base_keyboard())
            return

        # Определяем курс (число)
        try:
            course_num = int(course_text.split()[0])  # 2
        except Exception:
            await update.message.reply_text("❌ Неверный курс. Выбери ещё раз.",
                                            reply_markup=self.get_courses_keyboard())
            return

        # Получаем базу
        base = self.temp_data.get(user_id, {}).get("base", "9")

        # Выбираем Excel-файл
        if base == "11":
            excel_course_num = min(course_num + 1, 4)
        else:
            excel_course_num = course_num

        excel_course_key = f"{excel_course_num} курс"
        excel_url = EXCEL_URLS.get(excel_course_key)

        if not excel_url:
            await update.message.reply_text("❌ Файл расписания не найден для выбранного курса")
            return

        # Получаем группы
        groups = self.parser.find_groups_in_excel(excel_url, excel_course_key)
        if not groups:
            await update.message.reply_text("❌ Группы не найдены в расписании")
            return

        # Фильтрация по базе
        if base == "11":
            filtered_groups = [str(g) for g in groups if str(g).lower().endswith("с")]
        else:
            filtered_groups = [str(g) for g in groups if not str(g).lower().endswith("с")]

        if not filtered_groups:
            await update.message.reply_text("❌ После фильтрации по базе группы не найдены. Попробуй другую базу/курс.",
                                            reply_markup=self.get_courses_keyboard(with_back=True))
            return

        # Сохраняем
        self.temp_data[user_id] = {
            "base": base,
            "course": course_num,  # строго INT
            "excel_course_key": excel_course_key,
            "excel_url": excel_url,
            "available_groups": filtered_groups
        }

        # Выводим
        await update.message.reply_text(
            "Теперь выбери свою группу:",
            reply_markup=self.get_groups_keyboard(filtered_groups)
        )

        # 🔄 MODIFIED: выбор группы — сохраняем base + course + group (для поиска в excel сохраняем group как в файле)

    async def handle_group_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        group = update.message.text

        # Назад → возвращаемся к выбору курса
        if group == "⬅️ Вернуться":
            temp = self.temp_data.get(user_id, {})
            base = temp.get("base", "9")
            await update.message.reply_text("Выбери курс:", reply_markup=self.get_courses_keyboard(with_back=True))
            return

        temp = self.temp_data.get(user_id)
        if not temp:
            await update.message.reply_text("❌ Ошибка. Начни с /start")
            return

        base = temp.get("base", "9")
        course = temp.get("course")
        excel_course_key = self._compute_excel_course(course, base)

        self.user_manager.save_user_choice(user_id, str(course), group, base)
        if user_id in self.temp_data:
            del self.temp_data[user_id]

        await update.message.reply_text(
            f"✅ Группа {group} сохранена!\nТеперь ты можешь получать расписание:",
            reply_markup=self.get_main_keyboard()
        )

    async def handle_get_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        user_choice = self.user_manager.get_user_choice(user_id)

        if not user_choice:
            await update.message.reply_text("❌ Сначала выбери группу через /start")
            return

        course = user_choice["course"]
        group = user_choice["group"]
        base = user_choice.get("base", "9")

        excel_course_key = self._compute_excel_course(course, base)
        excel_url = EXCEL_URLS.get(excel_course_key)

        await update.message.reply_text(f"🔍 Ищу расписание {group}... ")

        result_data = self.parser.get_group_schedule(excel_url, group)

        if result_data and isinstance(result_data, dict) and "schedule" in result_data:
            formatted = self.format_schedule(result_data, group)
            if len(formatted) > 4096:
                parts = [formatted[i:i + 4096] for i in range(0, len(formatted), 4096)]
                for part in parts:
                    await update.message.reply_text(part)
            else:
                await update.message.reply_text(formatted)
        else:
            await update.message.reply_text(f"❌ Не удалось загрузить расписание для {group}")

    async def handle_change_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id

        # Удаляем только выбор курса и группы, но оставляем базу (если была)
        prev_base = self.user_manager.get_user_choice(user_id).get("base", "")

        if prev_base:
            # Если база уже была выбрана ранее — сразу ведём на выбор курса
            self.temp_data[user_id] = {"base": prev_base}
            await update.message.reply_text("Выбери курс:", reply_markup=self.get_courses_keyboard(with_back=True))
        else:
            # Если база не выбрана — возвращаем на выбор базы
            self.user_manager.save_user_choice(user_id, "", "", "")
            await update.message.reply_text("Выбери базу обучения:", reply_markup=self.get_base_keyboard())


    def format_schedule(self, data: dict, group: str) -> str:
        schedule = data.get("schedule", {})
        stats = data.get("stats", {})

        if not schedule:
            return f"❌ Нет расписания для {group}"

        days_order = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
        result = [f"📅 Расписание для группы -{group}-:\n"]

        # Сначала разбиваем по дням
        day_blocks = {}
        for lesson_num, info in schedule.items():
            day = info["day"]
            if day not in day_blocks:
                day_blocks[day] = []
            day_blocks[day].append((lesson_num, info))

        # Формируем вывод по порядку дней
        for day in days_order:
            if day in day_blocks:
                result.append(f" - {day}: -\n")
                for lesson_num, info in sorted(day_blocks[day]):
                    subj = info["subject"]
                    time = info["time"]
                    room = info["room"]
                    teacher = info["teacher"]
                    subgroup = f" | Подгруппа: {info['subgroup']}" if info["subgroup"] else ""

                    result.append(f"{lesson_num}️. {time} — {subj} \n👨‍🏫 {teacher} | 🚪 {room}{subgroup}\n")

        # Добавим статистику
        result.append(
            f"📊 -Статистика: \n"
            f"Всего лент: {stats.get('total', 0)} \n"
            f"Очных лент: {stats.get('normal', 0)} \n"
            f"Дистанционных лент: {stats.get('distant', 0)}"
        )

        return "\n".join(result)

        # 🔥 NEW: Помощник — вычисляет, какой ключ EXCEL_URLS использовать

    def _compute_excel_course(self, course, base):
        """
        Получает правильный ключ Excel для выбранной базы.
        course — может быть int или str ('2' или '2 курс')
        base — '9' или '11'
        """
        # Приводим курс к int
        try:
            course_num = int(str(course).split()[0])
        except:
            course_num = 1

        # Если база 11 → курс + 1
        if base == "11":
            course_num = min(course_num + 1, 4)

        # Возвращаем ключ в нужном формате
        return f"{course_num} курс"


def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "ВАШ_ТОКЕН_ОТ_BOTFATHER":
        logging.error("❌ BOT_TOKEN не установлен! Добавьте его в config.py")
        return

    bot = ScheduleBot()
    application = Application.builder().token(BOT_TOKEN).build()

    # Подключаем handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(MessageHandler(filters.Text(["🧑‍🏫 9 классов", "🎓 11 классов"]), bot.handle_base_selection))
    application.add_handler(MessageHandler(filters.Text(["1 курс", "2 курс", "3 курс", "4 курс", "⬅️ Вернуться"]),
                                           bot.handle_course_selection))
    application.add_handler(MessageHandler(filters.Text(["📅 Получить расписание"]), bot.handle_get_schedule))
    application.add_handler(MessageHandler(filters.Text(["🔄 Сменить группу"]), bot.handle_change_group))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_group_selection))

    logging.info("🤖 Бот запускается...")
    application.run_polling()


if __name__ == "__main__":
    main()