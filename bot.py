import asyncio
import time
import json
import os
import logging
import sys
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command

# -------------------- Настройка логирования --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# -------------------- Конфигурация --------------------
TOKEN = os.getenv("BOT_TOKEN", "8732492593:AAEisaSSVL1uNIxH4B4mYR9btgN3VfQ5Q3g")
API_URL = "https://my.spbstu.ru/home/get-abit-list"
PARAMS = {
    "filter_1": "2",
    "filter_2": "2",
    "filter_3": "652",
    "education_level": "bachelor_competition_lists"
}
TARGET_CODE = "1679369"

USERS_FILE = "users.json"
STATE_FILE = "last_state.json"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# -------------------- Работа с файлами --------------------
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return []

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

def load_last_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"enrolled": None, "informed": None}

def save_last_state(enrolled, informed):
    with open(STATE_FILE, "w") as f:
        json.dump({"enrolled": enrolled, "informed": informed}, f)

# -------------------- Запросы к API --------------------
def get_applicants(retries=3, delay=5):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://my.spbstu.ru/home/abit/list-applicants/bachelor_competition_lists",
        "X-Requested-With": "XMLHttpRequest"
    }
    for attempt in range(retries):
        try:
            response = requests.get(API_URL, params=PARAMS, headers=headers, timeout=15)
            if response.status_code == 503:
                logger.warning(f"503, попытка {attempt+1}/{retries} через {delay}с")
                time.sleep(delay)
                continue
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except Exception as e:
            logger.error(f"Ошибка (попытка {attempt+1}): {e}")
            if attempt == retries-1:
                raise
            time.sleep(delay)
    return []

def find_positions(applicants, target_code):
    enrolled, informed = [], []
    for app in applicants:
        code = app.get("code", "")
        if app.get("comment_status") == "К зачислению":
            enrolled.append(code)
        if app.get("has_contract_inform") == "Получено":
            informed.append(code)
    pos_enrolled = enrolled.index(target_code)+1 if target_code in enrolled else None
    pos_informed = informed.index(target_code)+1 if target_code in informed else None
    return pos_enrolled, pos_informed

# -------------------- Проверка и уведомления --------------------
async def perform_check():
    logger.info("🔄 Проверка в " + time.strftime("%H:%M"))
    try:
        applicants = get_applicants()
        if not applicants:
            logger.warning("Нет данных")
            return

        new_enrolled, new_informed = find_positions(applicants, TARGET_CODE)
        last_state = load_last_state()
        old_enrolled = last_state.get("enrolled")
        old_informed = last_state.get("informed")

        if new_enrolled != old_enrolled or new_informed != old_informed:
            save_last_state(new_enrolled, new_informed)
            msg = (
                f"🔔 **Изменилась позиция абитуриента {TARGET_CODE}!**\n"
                f"• «К зачислению»: было {old_enrolled or '❌'}, стало {new_enrolled or '❌'}\n"
                f"• «Информирование получено»: было {old_informed or '❌'}, стало {new_informed or '❌'}"
            )
            users = load_users()
            for user_id in users:
                try:
                    await bot.send_message(user_id, msg, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"Не удалось отправить {user_id}: {e}")
            logger.info("Уведомления разосланы")
        else:
            logger.info("Изменений нет")
    except Exception as e:
        logger.error(f"Ошибка в perform_check: {e}", exc_info=True)

async def scheduled_check():
    while True:
        await asyncio.sleep(3600)  # 60 минут
        await perform_check()

# -------------------- Команды бота --------------------
@dp.message(Command("start", "help"))
async def send_welcome(message: Message):
    await message.reply(
        "👋 Привет! Я бот для отслеживания позиции абитуриента.\n"
        "/check – текущая позиция\n"
        "/subscribe – подписаться на уведомления\n"
        "/unsubscribe – отписаться"
    )

@dp.message(Command("check"))
async def check_position(message: Message):
    try:
        await message.answer("⏳ Загружаю данные...")
        applicants = get_applicants()
        if not applicants:
            await message.answer("⚠️ Нет данных. Попробуйте позже.")
            return
        pos_enrolled, pos_informed = find_positions(applicants, TARGET_CODE)
        reply = (
            f"🔍 Результаты для кода **{TARGET_CODE}**:\n"
            f"• «К зачислению»: {pos_enrolled if pos_enrolled is not None else '❌ не найден'}\n"
            f"• «Информирование получено»: {pos_informed if pos_informed is not None else '❌ не найден'}"
        )
        await message.answer(reply, parse_mode="Markdown")
        users = load_users()
        if message.from_user.id not in users:
            users.append(message.from_user.id)
            save_users(users)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("subscribe"))
async def subscribe(message: Message):
    users = load_users()
    if message.from_user.id not in users:
        users.append(message.from_user.id)
        save_users(users)
        await message.answer("✅ Вы подписаны.")
    else:
        await message.answer("ℹ️ Вы уже подписаны.")

@dp.message(Command("unsubscribe"))
async def unsubscribe(message: Message):
    users = load_users()
    if message.from_user.id in users:
        users.remove(message.from_user.id)
        save_users(users)
        await message.answer("✅ Вы отписаны.")
    else:
        await message.answer("ℹ️ Вы не были подписаны.")

# -------------------- Запуск --------------------
async def main():
    logger.info("🤖 Бот запущен.")
    last_state = load_last_state()
    logger.info(f"Состояние: зачисление={last_state.get('enrolled')}, информирование={last_state.get('informed')}")

    # Первая проверка при старте
    await perform_check()

    # Запускаем фоновую проверку
    asyncio.create_task(scheduled_check())

    # Запускаем поллинг
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановка по Ctrl+C")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)