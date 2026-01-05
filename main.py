import logging
import asyncio
import threading
import re
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.utils import exceptions
from flask import Flask
import aiohttp

# ======================= CONFIG =======================
from data import BOT_TOKEN, ADMINS  # sizning token va adminlar ro'yxati
from buttons import toshkent_tumanlari  # Toshkent tumanlari uchun reply keyboard

API_TOKEN = BOT_TOKEN

logging.basicConfig(level=logging.INFO)

# ======================= STATES =======================
class Register(StatesGroup):
    name = State()
    location = State()
    phone = State()

# ======================= BOT SETUP =======================
storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=storage)

# ======================= HANDLERS =======================
@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    await Register.name.set()
    await message.reply(
        f"Assalomu Alaykum, <b>{message.from_user.full_name} 😊</b>!\n"
        "Bizning Rahimov School botiga xush kelibsiz! 👏\n"
        "<i>Autizm haqidagi qo'llanmani olish 3 qadam qoldi. 1-qadam: ismingizni yozing:</i>\n\n"
        "Ismingizni kiriting:",
        parse_mode="HTML"
    )

@dp.message_handler(state=Register.name)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name.replace(" ", "").isalpha() or len(name) < 2:
        await message.reply("❌ Iltimos, to'g'ri ism kiriting (faqat harflardan iborat bo'lsin)")
        return
    await state.update_data(name=name)
    await Register.location.set()
    await message.reply(
        "Toshkent shahrining qaysi tumanida yashaysiz?",
        reply_markup=toshkent_tumanlari
    )

@dp.message_handler(state=Register.location)
async def process_location(message: types.Message, state: FSMContext):
    location = message.text
    await state.update_data(location=location)
    await Register.phone.set()
    
    contact_button = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    contact_button.add(types.KeyboardButton("📱 Telefon raqamini yuborish", request_contact=True))
    contact_button.add(types.KeyboardButton("Raqamni qo'lda kiritish"))
    
    await message.reply(
        "2-qadam: Telefon raqamingizni kiriting:\n\n"
        "📱 Telefon raqamini yuborish tugmasini bosing yoki\n"
        "Namuna: +998901234567 yoki 901234567",
        reply_markup=contact_button
    )

@dp.message_handler(content_types=['contact', 'text'], state=Register.phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = ""
    if message.contact:
        phone = message.contact.phone_number
    else:
        phone = message.text
        if phone == "Raqamni qo'lda kiritish":
            await message.reply(
                "Telefon raqamingizni kiriting:\nNamuna: +998901234567 yoki 901234567",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return
        phone_digits = re.sub(r'\D', '', phone)
        if len(phone_digits) == 9:
            phone = f"+998{phone_digits}"
        elif len(phone_digits) == 12 and phone_digits.startswith('998'):
            phone = f"+{phone_digits}"
        elif len(phone_digits) == 13 and phone.startswith('+'):
            phone = f"+{phone_digits}"
        elif len(phone_digits) == 10 and phone_digits.startswith('8'):
            phone = f"+7{phone_digits[1:]}"
        else:
            await message.reply(
                "❌ Noto'g'ri telefon raqami formati!\n"
                "✅ Qabul qilinadigan formatlar:\n"
                "• 901234567\n"
                "• +998901234567\n"
                "• 998901234567"
            )
            return
    
    data = await state.get_data()
    user_name = data.get('name')
    location = data.get('location')

    admin_message = (
        f"🎯 <b>Qaytadan ro'yxatdan o'tish:</b>\n\n"
        f"👤 <b>Ism:</b> {user_name}\n"
        f"📍 <b>Tuman:</b> {location}\n"
        f"📱 <b>Telefon:</b> {phone}\n"
        f"🆔 <b>User ID:</b> {message.from_user.id}\n"
        f"📛 <b>To'liq ism:</b> {message.from_user.full_name}\n"
        f"📅 <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"#yangi_royhat"
    )
    
    if ADMINS:
        for admin_id in ADMINS:
            try:
                await bot.send_message(admin_id, admin_message, parse_mode="HTML")
            except exceptions.TelegramAPIError as e:
                logging.error(f"Admin {admin_id} ga xabar yuborishda xatolik: {e}")
    
    await state.finish()
    await message.reply_document(
        document=open("Autizm.pdf", "rb"),
        caption="Siz muvaffaqiyatli ro'yxatdan o'tdingiz. Marhamat, autizm haqidagi maxsus qo'llanma: \n"
    )

@dp.message_handler(commands=['cancel'], state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.finish()
    await message.reply(
        "❌ Ro'yhatdan o'tish bekor qilindi.\nQaytadan boshlash uchun /start ni bosing.",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message_handler(state='*')
async def handle_all_messages(message: types.Message):
    await message.reply(
        "❌ Iltimos, kerakli amalni bajaring.\nYordam olish uchun /help ni bosing.\nQayta boshlash uchun /restart ni bosing."
    )

# ======================= FLASK SERVER =======================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot ishlayapti!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# =================== INTERNAL PING ===================
async def keep_alive_ping():
    url = os.environ.get("RENDER_EXTERNAL_URL", "http://127.0.0.1:5000")
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    logging.info(f"Ping: {resp.status}")
        except Exception as e:
            logging.error(f"Ping xatoligi: {e}")
        await asyncio.sleep(600)  # 10 daqiqa

# =================== BOT START ===================
async def start_bot():
    asyncio.create_task(keep_alive_ping())  # pingni ishga tushirish
    await dp.start_polling()  # aiogram 2.25.1 da skip_updates default True

# =================== MAIN ===================
if __name__ == "__main__":
    # Flask server
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # Aiogram bot
    loop = asyncio.get_event_loop()
    loop.create_task(start_bot())
    loop.run_forever()
