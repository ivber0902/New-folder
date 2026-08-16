import asyncio
import time
import json
import os
import sys
import logging
import signal
import socket
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command
from aiohttp import web

# -------------------- Настройка логирования --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# -------------------- Конфигурация --------------------
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

bot = Bot(token=TOKEN)
dp = Dispatcher()

# -------------------- Работа с файлами --------------------
def load_users():
    logger.info(f"Загрузка пользователей из {USERS_FILE}")
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            data = json.load(f)
            logger.info(f"Загружено {len(data)} пользователей")
            return data
    logger.info("Файл пользователей не найден, создаём пустой список")
    return []

def save_users(users):
    logger.info(f"Сохранение {len(users)} пользователей в {USERS_FILE}")
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)
    logger.info("Пользователи сохранены")

def load_last_state():
    logger.info(f"Загрузка состояния из {STATE_FILE}")
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            logger.info(f"Состояние: {data}")
            return data
    logger.info("Файл состояния не найден, возвращаем пустое")
    return {"enrolled": None, "informed": None}

def save_last_state(enrolled, informed):
    logger.info(f"Сохранение состояния: зачисление={enrolled}, информирование={informed}")
    with open(STATE_FILE, "w") as f:
        json.dump({"enrolled": enrolled, "informed": informed}, f)
    logger.info("Состояние сохранено")

# -------------------- Запросы к API --------------------
def get_applicants(retries=3, delay=5):
    logger.info("Начинаем запрос к API СПбПУ")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://my.spbstu.ru/home/abit/list-applicants/bachelor_competition_lists",
        "X-Requested-With": "XMLHttpRequest"
    }
    for attempt in range(retries):
        try:
            logger.info(f"Попытка {attempt+1}/{retries}")
            response = requests.get(API_URL, params=PARAMS, headers=headers, timeout=15)
            logger.info(f"Ответ: статус {response.status_code}")
            if response.status_code == 503:
                logger.warning(f"503, попытка {attempt+1}/{retries} через {delay}с")
                time.sleep(delay)
                continue
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            logger.info(f"Получено {len(results)} записей")
            return results
        except Exception as e:
            logger.error(f"Ошибка (попытка {attempt+1}): {e}", exc_info=True)
            if attempt == retries-1:
                raise
            time.sleep(delay)
    logger.warning("Не удалось получить данные после всех попыток")
    return []

def find_positions(applicants, target_code):
    logger.info(f"Поиск позиции для кода {target_code} среди {len(applicants)} записей")
    enrolled, informed = [], []
    for app in applicants:
        code = app.get("code", "")
        if app.get("comment_status") == "К зачислению":
            enrolled.append(code)
        if app.get("has_contract_inform") == "Получено":
            informed.append(code)
    pos_enrolled = enrolled.index(target_code)+1 if target_code in enrolled else None
    pos_informed = informed.index(target_code)+1 if target_code in informed else None
    logger.info(f"Позиции: зачисление={pos_enrolled}, информирование={pos_informed}")
    return pos_enrolled, pos_informed

# -------------------- Проверка и уведомления --------------------
async def perform_check():
    logger.info("Запуск perform_check()")
    try:
        logger.info("🔄 Проверка в " + time.strftime("%H:%M"))
        applicants = get_applicants()
        if not applicants:
            logger.warning("⚠️ Нет данных")
            return

        new_enrolled, new_informed = find_positions(applicants, TARGET_CODE)
        last_state = load_last_state()
        old_enrolled = last_state.get("enrolled")
        old_informed = last_state.get("informed")

        if new_enrolled != old_enrolled or new_informed != old_informed:
            logger.info("Обнаружены изменения, сохраняем новое состояние")
            save_last_state(new_enrolled, new_informed)
            msg = (
                f"🔔 **Изменилась позиция абитуриента {TARGET_CODE}!**\n"
                f"• «К зачислению»: было {old_enrolled or '❌'}, стало {new_enrolled or '❌'}\n"
                f"• «Информирование получено»: было {old_informed or '❌'}, стало {new_informed or '❌'}"
            )
            users = load_users()
            logger.info(f"Рассылка уведомлений {len(users)} пользователям")
            for user_id in users:
                try:
                    await bot.send_message(user_id, msg, parse_mode="Markdown")
                    logger.info(f"Уведомление отправлено {user_id}")
                except Exception as e:
                    logger.error(f"Не удалось отправить {user_id}: {e}", exc_info=True)
            logger.info("✅ Уведомления разосланы")
        else:
            logger.info("ℹ️ Изменений нет")
    except Exception as e:
        logger.error(f"❌ Ошибка в perform_check: {e}", exc_info=True)
    logger.info("perform_check() завершён")

async def scheduled_check():
    logger.info("Запуск scheduled_check()")
    while True:
        logger.info("Ожидание 60 минут до следующей проверки")
        await asyncio.sleep(3600)
        logger.info("Пробуждение, запуск проверки")
        await perform_check()

# -------------------- Команды бота --------------------
@dp.message(Command("start", "help"))
async def send_welcome(message: Message):
    logger.info(f"Команда start/help от {message.from_user.id}")
    await message.reply(
        "👋 Привет! Я бот для отслеживания позиции абитуриента.\n"
        "/check – текущая позиция\n"
        "/subscribe – подписаться на уведомления\n"
        "/unsubscribe – отписаться"
    )

@dp.message(Command("check"))
async def check_position(message: Message):
    logger.info(f"Команда check от {message.from_user.id}")
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
            logger.info(f"Пользователь {message.from_user.id} добавлен в список")
    except Exception as e:
        logger.error(f"Ошибка в check: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("subscribe"))
async def subscribe(message: Message):
    logger.info(f"Команда subscribe от {message.from_user.id}")
    users = load_users()
    if message.from_user.id not in users:
        users.append(message.from_user.id)
        save_users(users)
        await message.answer("✅ Вы подписаны.")
    else:
        await message.answer("ℹ️ Вы уже подписаны.")

@dp.message(Command("unsubscribe"))
async def unsubscribe(message: Message):
    logger.info(f"Команда unsubscribe от {message.from_user.id}")
    users = load_users()
    if message.from_user.id in users:
        users.remove(message.from_user.id)
        save_users(users)
        await message.answer("✅ Вы отписаны.")
    else:
        await message.answer("ℹ️ Вы не были подписаны.")

# -------------------- HTTP-сервер для health checks --------------------
async def health_check(request):
    logger.info("Получен health check запрос")
    return web.Response(text="OK")

async def run_http_server():
    logger.info("Запуск HTTP-сервера")
    port = int(os.getenv("PORT", 10000))
    logger.info(f"Порт: {port}")
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    try:
        await runner.setup()
        logger.info("AppRunner настроен")
        site = web.TCPSite(runner, host="0.0.0.0", port=port)
        await site.start()
        logger.info(f"✅ HTTP сервер запущен на порту {port}")
        # Проверяем, что порт действительно слушается
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(("127.0.0.1", port))
            logger.info("Порт успешно прослушивается")
            sock.close()
        except Exception as e:
            logger.error(f"Не удалось подключиться к своему порту: {e}", exc_info=True)
        await asyncio.Event().wait()  # держим сервер активным
    except Exception as e:
        logger.error(f"Ошибка при запуске HTTP-сервера: {e}", exc_info=True)
        raise

# -------------------- Обработка сигналов --------------------
def handle_sigterm(signum, frame):
    logger.info("Получен сигнал SIGTERM, завершаем работу")
    # Здесь можно выполнить сохранение состояния, но мы уже сохраняем при изменениях
    sys.exit(0)

# -------------------- Запуск --------------------
async def main():
    logger.info("=== ЗАПУСК БОТА ===")
    # Регистрируем обработчик SIGTERM
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    last_state = load_last_state()
    logger.info(f"📊 Состояние: зачисление={last_state.get('enrolled')}, информирование={last_state.get('informed')}")

    # Первая проверка при старте
    logger.info("Выполняем первую проверку")
    await perform_check()

    # Запускаем фоновые задачи
    logger.info("Создаём задачи поллинга и периодической проверки")
    asyncio.create_task(dp.start_polling(bot))
    asyncio.create_task(scheduled_check())

    # Запускаем HTTP-сервер (блокирующий)
    logger.info("Запускаем HTTP-сервер")
    await run_http_server()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановка по Ctrl+C")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)