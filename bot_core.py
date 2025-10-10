import logging
import asyncio
from typing import Dict, Any

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
        self.parser = ExcelParser()
        self.user_manager = UserManager()
        self.temp_data: Dict[int, Dict[str, Any]] = {}
        self.notification_task = None

    async def start_notification_system(self, application: Application) -> None:
        """Запускает систему периодических уведомлений"""
        if self.notification_task is None or self.notification_task.done():
            self.notification_task = asyncio.create_task(
                self._notification_loop(application)
            )
            logging.info("🔔 Система уведомлений запущена")

    async def _notification_loop(self, application: Application) -> None:
        """Цикл проверки обновлений расписания"""
        while True:
            try:
                await asyncio.sleep(3600)  # Проверка каждые 60 минут
                await self._check_schedule_updates(application)
            except Exception as e:
                logging.error(f"❌ Ошибка в системе уведомлений: {e}")
                await asyncio.sleep(300)  # Пауза 5 минут при ошибке

    async def _check_schedule_updates(self, application: Application) -> None:
        """Проверяет обновления расписания и отправляет уведомления"""
        try:
            users_data = self.user_manager.load_all_users()
            if not users_data:
                return

            updates_found = False
            for user_id_str, user_data in users_data.items():
                user_id = int(user_id_str)
                course = user_data.get("course")
                group = user_data.get("group")

                if course and group:
                    should_update = self.user_manager.should_update_schedule(user_id, course)
                    if should_update:
                        updates_found = True
                        # Обновляем время в базе
                        self.user_manager.save_user_choice(user_id, course, group)

                        # Отправляем уведомление пользователю
                        try:
                            await application.bot.send_message(
                                chat_id=user_id,
                                text=f"🔄 **Обновление расписания!**\n\n"
                                     f"Для группы *{group}* доступно новое расписание\.\n"
                                     f"Используй кнопку *📅 Получить расписание* для просмотра\.",
                                parse_mode='MarkdownV2'
                            )
                            logging.info(f"📢 Отправлено уведомление пользователю {user_id}")
                        except Exception as e:
                            logging.warning(f"⚠️ Не удалось отправить уведомление пользователю {user_id}: {e}")

            if updates_found:
                logging.info("🔔 Уведомления об обновлениях отправлены")

        except Exception as e:
            logging.error(f"❌ Ошибка при проверке обновлений: {e}")

    @staticmethod
    def get_courses_keyboard() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup([
            [KeyboardButton("1 курс"), KeyboardButton("2 курс")],
            [KeyboardButton("3 курс"), KeyboardButton("4 курс")]
        ], resize_keyboard=True)

    @staticmethod
    def get_groups_keyboard(groups: list) -> ReplyKeyboardMarkup:
        keyboard = []
        for i in range(0, len(groups), 3):
            keyboard.append([KeyboardButton(group) for group in groups[i:i + 3]])
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    @staticmethod
    def get_main_keyboard() -> ReplyKeyboardMarkup:
        keyboard = [
            [KeyboardButton("📅 Получить расписание")],
            [KeyboardButton("🔄 Сменить группу")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        saved_choice = self.user_manager.get_user_choice(user_id)

        print(f"🔍 START: user_id={user_id}, saved_choice={saved_choice}")

        # Запускаем систему уведомлений при первом старте
        if not hasattr(context.application, 'notification_system_started'):
            await self.start_notification_system(context.application)
            context.application.notification_system_started = True

        if saved_choice:
            should_update = self.user_manager.should_update_schedule(user_id, saved_choice["course"])
            print(f"🔄 Проверка обновления: {should_update}")

            if should_update:
                print("🎯 ОБНОВЛЕНИЕ НАЙДЕНО! Сохраняем новую версию...")
                self.user_manager.save_user_choice(user_id, saved_choice["course"], saved_choice["group"])
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
            await update.message.reply_text(
                "🎓 Бот расписания Политеха\n\nВыбери свой курс:",
                reply_markup=self.get_courses_keyboard()
            )

    async def handle_course_selection(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        course = update.message.text
        user_id = update.effective_user.id

        await update.message.reply_text("🔍 Сканирую расписание...")

        excel_url = EXCEL_URLS.get(course)
        if not excel_url:
            await update.message.reply_text("❌ Файл расписания не найден")
            return

        groups = self.parser.find_groups_in_excel(excel_url, course)

        if not groups:
            await update.message.reply_text("❌ Группы не найдены в расписании")
            return

        self.temp_data[user_id] = {
            "course": course,
            "excel_url": excel_url,
            "available_groups": groups
        }

        await update.message.reply_text(
            f"✅ Найдено {len(groups)} групп\nВыбери свою группу:",
            reply_markup=self.get_groups_keyboard(groups)
        )

    async def handle_group_selection(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        group = update.message.text
        user_id = update.effective_user.id

        temp_data = self.temp_data.get(user_id)
        if not temp_data:
            await update.message.reply_text("❌ Ошибка. Начни с /start")
            return

        self.user_manager.save_user_choice(user_id, temp_data["course"], group)
        del self.temp_data[user_id]

        await update.message.reply_text(
            f"✅ Группа {group} сохранена!\nТеперь ты можешь получать расписание:",
            reply_markup=self.get_main_keyboard()
        )

    async def handle_get_schedule(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        user_choice = self.user_manager.get_user_choice(user_id)

        if not user_choice:
            await update.message.reply_text("❌ Сначала выбери группу через /start")
            return

        course = user_choice["course"]
        group = user_choice["group"]
        excel_url = EXCEL_URLS.get(course)

        await update.message.reply_text(f"🔍 Ищу расписание {group}...")

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

    async def handle_change_group(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        # Очищаем старый выбор
        self.user_manager.save_user_choice(user_id, "", "")
        await update.message.reply_text("Выбери новый курс:", reply_markup=self.get_courses_keyboard())

    @staticmethod
    def format_schedule(result_data, group_name):
        print(f"🔧 format_schedule вызван с: {type(result_data)}")

        schedule = result_data.get("schedule", {})
        stats = result_data.get("stats", {})

        print(f"📊 Расписание keys: {list(schedule.keys())}")

        if not schedule or not isinstance(schedule, dict):
            return "❌ Расписание не найдено или повреждено"

        text = f"📅 Расписание {group_name}:\n\n"

        days_schedule = {}
        for lesson_num, lesson in schedule.items():
            if not isinstance(lesson_num, int):
                continue

            day = lesson['day']
            if day not in days_schedule:
                days_schedule[day] = []
            days_schedule[day].append((lesson_num, lesson))

        for day, lessons_in_day in days_schedule.items():
            text += f"- {day.upper()}:-\n"

            for lesson_num, lesson in sorted(lessons_in_day, key=lambda x: x[0]):
                time = lesson['time']
                subject = lesson['subject']

                if lesson.get('subgroup') and lesson['subgroup'] != "?":
                    full_subject = f"{subject} ({lesson['subgroup']})"
                else:
                    full_subject = subject

                text += f"- {lesson_num}. {time} - {full_subject}\n"

                if lesson['teacher'] and lesson['teacher'] != "?" and "нет пары" not in subject.lower():
                    text += f"   👨‍🏫 {lesson['teacher']}\n"

                if lesson['room'] and lesson['room'] != "?" and "нет пары" not in subject.lower():
                    text += f"  🚪 {lesson['room']}\n"

        if stats:
            text += "---\n"
            text += f"📊 **Статистика:**\n"
            text += f"• Всего пар: {stats.get('total', 0)}\n"
            text += f"• Очных: {stats.get('normal', 0)}\n"
            text += f"• Дистанционных: {stats.get('distant', 0)}\n"
            text += f"• Самостоятельных: {stats.get('self_study', 0)}\n\n"

        text += "**Условные обозначения:**\n"
        text += "💻 - Дистанционное занятие\n"
        text += "📚 - Самостоятельная работа\n"
        text += "🏫 - Очное занятие\n"
        text += "❌ - Нет пары\n"

        return text


def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "ВАШ_ТОКЕН_ОТ_BOTFATHER":
        logging.error("❌ BOT_TOKEN не установлен! Добавьте его в переменные окружения")
        return

    bot = ScheduleBot()
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(MessageHandler(filters.Text(["1 курс", "2 курс", "3 курс", "4 курс"]),
                                           bot.handle_course_selection))
    application.add_handler(MessageHandler(filters.Text(["📅 Получить расписание"]), bot.handle_get_schedule))
    application.add_handler(MessageHandler(filters.Text(["🔄 Сменить группу"]), bot.handle_change_group))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_group_selection))

    logging.info("🤖 Бот запускается...")
    application.run_polling()


if __name__ == "__main__":
    main()
