import asyncio
import logging
import os
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.middlewares.logging import LoggingMiddleware

from aiohttp import web
import aiohttp

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN":
    logging.error("❌ BOT_TOKEN is missing or invalid! Please set it in your environment variables.")
    # Exit or handle gracefully - for a bot, we can't continue without a token
    import sys
    sys.exit(1)

WEBHOOK_HOST = os.environ.get("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.environ.get("PORT", 5000))

logging.basicConfig(level=logging.INFO)

bot: Bot = None
dp: Dispatcher = None

# ================== STATES ==================
class Register(StatesGroup):
    name = State()
    location = State()
    phone = State()

# ================== BUTTONS ==================
def toshkent_tumanlari():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        "Yunusobod", "Chilonzor",
        "Mirzo Ulug‘bek", "Yakkasaroy",
        "Shayxontohur", "Olmazor",
        "Sergeli", "Uchtepa",
        "Bektemir", "Mirobod"
    )
    return kb

# ================== HANDLERS ==================
async def start_handler(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("👋 Assalomu alaykum!\n\nIsmingizni kiriting:")
    await Register.name.set()

async def process_name(message: types.Message, state: FSMContext):
    if not message.text.isalpha():
        await message.answer("❌ Ism faqat harflardan iborat bo‘lsin")
        return

    await state.update_data(name=message.text)
    await Register.location.set()

    await message.answer(
        "📍 Toshkent shahrining qaysi tumanida yashaysiz?",
        reply_markup=toshkent_tumanlari()
    )

async def process_location(message: types.Message, state: FSMContext):
    await state.update_data(location=message.text)
    await Register.phone.set()

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("📱 Telefon yuborish", request_contact=True))

    await message.answer(
        "📞 Telefon raqamingizni yuboring:",
        reply_markup=kb
    )

async def process_phone(message: types.Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
    else:
        digits = re.sub(r"\D", "", message.text)
        if len(digits) != 9:
            await message.answer("❌ Raqam noto‘g‘ri")
            return
        phone = "+998" + digits

    data = await state.get_data()

    logging.info({
        "name": data["name"],
        "location": data["location"],
        "phone": phone,
        "user_id": message.from_user.id,
        "time": datetime.now()
    })

    await state.finish()

    await message.answer(
        "✅ Ro‘yxatdan o‘tdingiz!",
        reply_markup=types.ReplyKeyboardRemove()
    )

# ================== WEBHOOK ==================
async def handle_webhook(request):
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return web.Response(text="OK")

# ================== HEALTH CHECK ==================
async def health(request):
    return web.Response(text="OK")

# ================== SELF PING (NO MESSAGE) ==================
async def self_ping():
    await asyncio.sleep(30)  # bot to‘liq ishga tushsin
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                await session.get(WEBHOOK_HOST)
                logging.info("🔁 Self ping OK")
        except Exception as e:
            logging.error(f"PING ERROR: {e}")

        await asyncio.sleep(600)  # 10 minut

# ================== MAIN ==================
async def main():
    global bot, dp

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(bot, storage=MemoryStorage())

    # 🔥 WEBHOOK UCHUN MUHIM
    Bot.set_current(bot)
    Dispatcher.set_current(dp)

    dp.middleware.setup(LoggingMiddleware())

    dp.register_message_handler(start_handler, commands=["start"])
    dp.register_message_handler(process_name, state=Register.name)
    dp.register_message_handler(process_location, state=Register.location)
    dp.register_message_handler(
        process_phone,
        state=Register.phone,
        content_types=["text", "contact"]
    )

    await bot.set_webhook(WEBHOOK_URL)

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_post(WEBHOOK_PATH, handle_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
    await site.start()

    # 🔁 SELF PING ISHGA TUSHADI
    asyncio.create_task(self_ping())

    logging.info("🚀 Bot ishga tushdi (Render FREE)")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
