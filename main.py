import logging
import asyncio
import os
import json
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import exceptions

from aiohttp import web
import aiohttp

import gspread
from google.oauth2.service_account import Credentials
from google.auth.exceptions import GoogleAuthError

# ================= CONFIG =================
from data import BOT_TOKEN, ADMINS, SPREADSHEET_NAME, CREDENTIALS_FILE
from buttons import toshkent_tumanlari

API_TOKEN = BOT_TOKEN

WEBHOOK_HOST = os.environ.get("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = f"/webhook/{API_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.environ.get("PORT", 5000))

logging.basicConfig(level=logging.INFO)

bot = None
dp = None
gs_manager = None

# ================= GOOGLE SHEETS =================
class GoogleSheetsManager:
    def __init__(self):
        self.sheet = None
        self.worksheet = None
        self.connected = False
        self.connect()

    def connect(self):
        try:
            scope = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]

            creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
            if creds_json:
                creds = Credentials.from_service_account_info(
                    json.loads(creds_json), scopes=scope
                )
            else:
                creds = Credentials.from_service_account_file(
                    CREDENTIALS_FILE, scopes=scope
                )

            client = gspread.authorize(creds)

            try:
                self.sheet = client.open(SPREADSHEET_NAME)
            except gspread.SpreadsheetNotFound:
                self.sheet = client.create(SPREADSHEET_NAME)

            self.worksheet = self.sheet.sheet1

            if not self.worksheet.get("A1"):
                self.worksheet.update("A1:J1", [[
                    "№", "Ism", "Tuman", "Telefon", "User ID",
                    "Full name", "Username", "Sana", "Vaqt", "Status"
                ]])

            self.connected = True
            logging.info("✅ Google Sheets ulandi")

        except Exception as e:
            logging.error(f"❌ Google Sheets xato: {e}")

    def add_user(self, user):
        if not self.connected:
            return False

        rows = self.worksheet.get_all_values()
        index = len(rows)

        self.worksheet.append_row([
            index,
            user["name"],
            user["location"],
            user["phone"],
            user["user_id"],
            user["full_name"],
            user["username"],
            datetime.now().strftime("%Y-%m-%d"),
            datetime.now().strftime("%H:%M:%S"),
            "OK"
        ])
        return True

# ================= STATES =================
class Register(StatesGroup):
    name = State()
    location = State()
    phone = State()

# ================= HANDLERS =================
async def start_handler(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        "👋 Assalomu alaykum!\n\n"
        "Ismingizni kiriting:"
    )
    await Register.name.set()

async def process_name(message: types.Message, state: FSMContext):
    if not message.text.isalpha():
        await message.answer("❌ Iltimos, faqat harflardan iborat ism kiriting")
        return

    await state.update_data(name=message.text)
    await Register.location.set()

    await message.answer(
        "📍 Toshkent shahrining qaysi tumanida yashaysiz?",
        reply_markup=toshkent_tumanlari
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
            await message.answer("❌ Noto‘g‘ri raqam")
            return
        phone = "+998" + digits

    data = await state.get_data()

    user_data = {
        "name": data["name"],
        "location": data["location"],
        "phone": phone,
        "user_id": message.from_user.id,
        "full_name": message.from_user.full_name,
        "username": message.from_user.username or ""
    }

    gs_manager.add_user(user_data)

    await state.finish()

    await message.answer(
        "✅ Ro‘yxatdan o‘tdingiz!\n\n"
        "📘 Qo‘llanma:",
        reply_markup=types.ReplyKeyboardRemove()
    )

    await message.answer_document(
        open("Autizm.pdf", "rb")
    )

# ================= WEBHOOK =================
async def handle_webhook(request):
    data = await request.json()
    update = types.Update(**data)
    await dp.process_update(update)
    return web.Response(text="OK")

# ================= MAIN =================
async def main():
    global bot, dp, gs_manager

    bot = Bot(API_TOKEN)
    dp = Dispatcher(bot, storage=MemoryStorage())

    # 🔥 MUHIM QATORLAR
    Bot.set_current(bot)
    Dispatcher.set_current(dp)

    dp.middleware.setup(LoggingMiddleware())

    gs_manager = GoogleSheetsManager()

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
    app.router.add_post(WEBHOOK_PATH, handle_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
    await site.start()

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
