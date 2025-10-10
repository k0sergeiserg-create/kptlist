import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8379351448:AAHNlTGiWWzMjgN9_4BsPwkKnNuDgzBpQr8")
GROUP_CODES = {
    "1 курс": ["ИС", "МД", "Э", "ЛС", "СТ", "МЭ", "ТД", "МС", "БП"],
    "2 курс": ["ИС", "МД", "Э", "ЛС", "СТ", "МЭ", "ТД", "МС", "БП"],
    "3 курс": ["ИС", "МД", "Э", "ЛС", "СТ", "МЭ", "ТД", "МС", "БП"],
    "4 курс": ["ИС", "МД", "Э", "ЛС", "СТ", "МЭ", "ТД", "МС", "БП"]
}
EXCEL_URLS = {
    "1 курс": "C:/TelegrammBOT KPT LIST/Data/Расписание 1 семестр 2025 год 1 курсы.xlsx",
    "2 курс": "C:/TelegrammBOT KPT LIST/Data/Расписание 1 семестр 2025 год 1-2 курсы.xlsx",
    "3 курс": "C:/TelegrammBOT KPT LIST/Data/Расписание 1 семестр 2025 год 2-3 курсы.xlsx",
    "4 курс": "C:/TelegrammBOT KPT LIST/Data/Расписание 1 семестр 2025 год 3-4 курсы.xlsx"
}

LESSON_TIMES = {
    1: "8:00-9:30", 2: "9:40-11:10", 3: "11:20-12:50",
    4: "13:30-15:00", 5: "15:10-16:40", 6: "16:50-18:20"
}
# Цвета для дистанта и самостоятельной работы
DISTANT_COLOR_HEX = "FFE26B0A"
SELF_STUDY_COLOR_HEX = "FFC5D9F1"
DISTANT_COLOR_VARIANTS = ["FFE26B0A", "FFFFC000"]
