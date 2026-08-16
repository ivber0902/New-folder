import asyncio
import time
import json
import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command
from aiohttp import web

# ==================== КОНФИГУРАЦИЯ ====================
TOKEN = "8732492593:AAEisaSSVL1uNIxH4B4mYR9btgN3VfQ5Q3g"
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

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ==================== РАБОТА С ФАЙЛАМИ ====================
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

# ==================== ФУНКЦИИ ДЛЯ РАБОТЫ С API ====================
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
                print(f"⚠️ 503, попытка {attempt+1}/{retries} через {delay}с...")
                time.sleep(delay)
                continue
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except Exception as e:
            print(f"❌ Ошибка (попытка {attempt+1}): {e}")
            if attempt == retries-1:
                raise
            time.sleep(delay)
    return []

def find_positions(applicants, target_code):
    enrolled = []
    informed = []
    for app in applicants:
        code = app.get("code", "")
        if app.get("comment_status") == "К зачислению":
            enrolled.append(code)
        if app.get("has_contract_inform") == "Получено":
            informed.append(code)
    pos_enrolled = enrolled.index(target_code)+1 if target_code in enrolled else None
    pos_informed = informed.index(target_code)+1 if target_code in informed else None
    return pos_enrolled, pos_informed

# ==================== ФОНОВАЯ ЗАДАЧА ====================
async def scheduled_check():
    while True:
        now = time.localtime()
        next_check = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, now.tm_hour + 1, 0, 0, 0, 0, 0))
        sleep_seconds = max(0, next_check - time.time())
        await asyncio.sleep(sleep_seconds)

        try:
            print("🔄 Автоматическая проверка в", time.strftime("%H:%M"))
            applicants = get_applicants()
            if not applicants:
                print("⚠️ Не удалось получить данные")
                continue

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
                        print(f"❌ Не удалось отправить сообщение {user_id}: {e}")
                print("✅ Уведомления разосланы")
            else:
                print("ℹ️ Изменений нет")
        except Exception as e:
            print(f"❌ Ошибка в фоновой проверке: {e}")

# ==================== HTTP-СЕРВЕР ДЛЯ HEALTH CHECKS ====================
async def health_check(request):
    return web.Response(text="OK")

async def start_http_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    print("✅ Health server running on port 10000")
    # Бесконечно ждём, чтобы сервер не завершался
    await asyncio.Event().wait()

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@dp.message(Command("start", "help"))
async def send_welcome(message: Message):
    await message.reply(
        "👋 Привет! Я бот для отслеживания позиции абитуриента в списках СПбПУ.\n"
        "Команды:\n"
        "/check – показать текущую позицию для кода 1679369\n"
        "/subscribe – подписаться на уведомления об изменениях\n"
        "/unsubscribe – отписаться от уведомлений\n"
        "Данные обновляются автоматически каждый час."
    )

@dp.message(Command("check"))
async def check_position(message: Message):
    try:
        await message.answer("⏳ Загружаю данные...")
        applicants = get_applicants()
        if not applicants:
            await message.answer("⚠️ Не удалось получить данные. Попробуйте позже.")
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
        await message.answer("✅ Вы подписались на уведомления об изменениях.")
    else:
        await message.answer("ℹ️ Вы уже подписаны.")

@dp.message(Command("unsubscribe"))
async def unsubscribe(message: Message):
    users = load_users()
    if message.from_user.id in users:
        users.remove(message.from_user.id)
        save_users(users)
        await message.answer("✅ Вы отписались от уведомлений.")
    else:
        await message.answer("ℹ️ Вы не были подписаны.")

# ==================== ЗАПУСК ====================
async def main():
    print("🤖 Бот запущен. Нажми Ctrl+C для остановки.")
    last_state = load_last_state()
    print(f"📊 Последнее состояние: зачисление={last_state.get('enrolled')}, информирование={last_state.get('informed')}")

    asyncio.create_task(scheduled_check())
    asyncio.create_task(start_http_server())

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())