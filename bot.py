import asyncio
import time
import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command

# ==================== КОНФИГУРАЦИЯ ====================
# Токен бота (можно вынести в переменную окружения для безопасности)
TOKEN = "8732492593:AAEisaSSVL1uNIxH4B4mYR9btgN3VfQ5Q3g"

# Если вы хотите использовать переменную окружения (рекомендуется для облачных сервисов),
# раскомментируйте следующую строку и закомментируйте верхнюю:
# TOKEN = os.getenv("BOT_TOKEN", "8732492593:AAEisaSSVL1uNIxH4B4mYR9btgN3VfQ5Q3g")

# API СПбПУ (доступен из любой страны)
API_URL = "https://my.spbstu.ru/home/get-abit-list"
PARAMS = {
    "filter_1": "2",      # очная
    "filter_2": "2",      # контракт
    "filter_3": "652",    # 09.03.04 Программная инженерия
    "education_level": "bachelor_competition_lists"
}
TARGET_CODE = "1679369"   # код абитуриента, который ищем

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ==================== ФУНКЦИИ ДЛЯ РАБОТЫ С API ====================
def get_applicants(retries=3, delay=5):
    """
    Запрашивает данные с API СПбПУ.
    При ошибках делает до retries повторных попыток с паузой delay секунд.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://my.spbstu.ru/home/abit/list-applicants/bachelor_competition_lists",
        "X-Requested-With": "XMLHttpRequest"
    }

    for attempt in range(retries):
        try:
            response = requests.get(API_URL, params=PARAMS, headers=headers, timeout=15)
            if response.status_code == 503:
                print(f"⚠️ 503 Service Unavailable, попытка {attempt+1}/{retries} через {delay}с...")
                time.sleep(delay)
                continue
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"❌ Ошибка запроса (попытка {attempt+1}): {e}")
            if attempt == retries - 1:
                raise
            time.sleep(delay)
    return []

def find_positions(applicants, target_code):
    """
    Возвращает позицию абитуриента с target_code среди двух групп:
       1) comment_status == "К зачислению"
       2) has_contract_inform == "Получено"
    Возвращает кортеж (pos_enrolled, pos_informed).
    """
    enrolled = []
    informed = []

    for app in applicants:
        code = app.get("code", "")
        comment = app.get("comment_status", "")
        inform = app.get("has_contract_inform", "")

        if comment == "К зачислению":
            enrolled.append(code)
        if inform == "Получено":
            informed.append(code)

    pos_enrolled = enrolled.index(target_code) + 1 if target_code in enrolled else None
    pos_informed = informed.index(target_code) + 1 if target_code in informed else None
    return pos_enrolled, pos_informed

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@dp.message(Command("start", "help"))
async def send_welcome(message: Message):
    await message.reply(
        "👋 Привет! Я бот для проверки позиции абитуриента в списках СПбПУ.\n"
        "Отправь команду /check – я покажу место для кода 1679369.\n"
        "Данные берутся с сайта my.spbstu.ru (очная, контракт, 09.03.04)."
    )

@dp.message(Command("check"))
async def check_position(message: Message):
    try:
        await message.answer("⏳ Загружаю данные...")
        applicants = get_applicants()
        if not applicants:
            await message.answer("⚠️ Не удалось получить данные. Попробуй позже.")
            return

        pos_enrolled, pos_informed = find_positions(applicants, TARGET_CODE)

        reply = (
            f"🔍 Результаты для кода **{TARGET_CODE}**:\n"
            f"• Место среди абитуриентов со статусом **«К зачислению»**: "
            f"{pos_enrolled if pos_enrolled is not None else '❌ не найден'}\n"
            f"• Место среди абитуриентов с информированием **«Получено»**: "
            f"{pos_informed if pos_informed is not None else '❌ не найден'}"
        )
        await message.answer(reply, parse_mode="Markdown")

    except Exception as e:
        await message.answer(f"❌ Произошла ошибка:\n`{e}`\nПопробуйте через минуту.", parse_mode="Markdown")

# ==================== ЗАПУСК БОТА ====================
async def main():
    print("🤖 Бот запущен. Нажми Ctrl+C для остановки.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())