import logging
import asyncio
import threading
import re
import os
import json
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.utils import exceptions
from flask import Flask, request
import aiohttp
import gspread
from google.oauth2.service_account import Credentials
from google.auth.exceptions import GoogleAuthError

# ======================= CONFIG =======================
import os
import json

# credentials.json ni avtomatik yaratish
def setup_credentials():
    """credentials.json ni sozlash"""
    creds_file = "credentials.json"
    
    # Agar fayl bo'lsa, ishlat
    if os.path.exists(creds_file):
        logging.info(f"✅ {creds_file} topildi")
        return True
    
    # Environment variable dan yaratish
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    if creds_json:
        try:
            with open(creds_file, 'w') as f:
                f.write(creds_json)
            logging.info(f"✅ {creds_file} environment variable dan yaratildi")
            return True
        except Exception as e:
            logging.error(f"❌ {creds_file} yaratishda xatolik: {e}")
            return False
    
    logging.error(f"❌ {creds_file} topilmadi va GOOGLE_CREDENTIALS ham yo'q")
    return False

# credentials.json ni sozlash
if not setup_credentials():
    logging.warning("⚠️ credentials.json sozlanmadi, Google Sheets ishlamaydi")

from data import BOT_TOKEN, ADMINS, SPREADSHEET_NAME, CREDENTIALS_FILE, HEADER_COLOR, SUCCESS_COLOR
from buttons import toshkent_tumanlari  # Toshkent tumanlari uchun reply keyboard

API_TOKEN = BOT_TOKEN

logging.basicConfig(level=logging.INFO)

# ======================= GOOGLE SHEETS SETUP =======================
class GoogleSheetsManager:
    def __init__(self):
        self.sheet = None
        self.connected = False
        self.connect()
    
    def connect(self):
        """Google Sheets ga ulanish"""
        try:
            # Scope larni aniqlash
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive.file',
                'https://www.googleapis.com/auth/drive'
            ]
            
            # Credentials faylini tekshirish
            if not os.path.exists(CREDENTIALS_FILE):
                logging.error(f"❌ Credentials fayli topilmadi: {CREDENTIALS_FILE}")
                return False
            
            # Autentifikatsiya
            creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
            client = gspread.authorize(creds)
            
            # Spreadsheet ni ochish yoki yaratish
            try:
                self.sheet = client.open(SPREADSHEET_NAME)
            except gspread.SpreadsheetNotFound:
                # Yangi spreadsheet yaratish
                self.sheet = client.create(SPREADSHEET_NAME)
                # Foydalanish uchun ochish
                self.sheet.share('', perm_type='anyone', role='writer')
                logging.info(f"✅ Yangi spreadsheet yaratildi: {SPREADSHEET_NAME}")
            
            # Worksheet ni tekshirish yoki yaratish
            try:
                self.worksheet = self.sheet.get_worksheet(0)
            except:
                self.worksheet = self.sheet.add_worksheet(title="Foydalanuvchilar", rows=1000, cols=20)
            
            # Agar bo'sh bo'lsa, headerlar qo'shish
            if not self.worksheet.get('A1'):
                headers = [
                    ['№', 'Ism', 'Tuman', 'Telefon', 'User ID', 'To\'liq Ism', 
                     'Username', 'Ro\'yxatdan o\'tgan sana', 'Vaqt', 'Status']
                ]
                self.worksheet.update('A1:J1', headers)
                # Headerlarga format berish
                self.worksheet.format('A1:J1', {
                    "backgroundColor": {"red": 0.29, "green": 0.53, "blue": 0.91},
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    "horizontalAlignment": "CENTER"
                })
                logging.info("✅ Google Sheets headerlar qo'shildi")
            
            self.connected = True
            logging.info("✅ Google Sheets ga muvaffaqiyatli ulandı")
            return True
            
        except GoogleAuthError as e:
            logging.error(f"❌ Google autentifikatsiya xatosi: {e}")
            return False
        except Exception as e:
            logging.error(f"❌ Google Sheets ga ulanishda xatolik: {e}")
            return False
    
    def add_user(self, user_data):
        """Yangi foydalanuvchini Google Sheets ga qo'shish"""
        if not self.connected:
            logging.error("❌ Google Sheets ga ulanmagan!")
            return False
        
        try:
            # Oxirgi qatorni topish
            all_values = self.worksheet.get_all_values()
            next_row = len(all_values) + 1
            
            # Ma'lumotlarni tayyorlash
            row_data = [
                next_row - 1,  # № (header hisobga olinmagan)
                user_data['name'],
                user_data['location'],
                user_data['phone'],
                user_data['user_id'],
                user_data['full_name'],
                user_data['username'],
                datetime.now().strftime('%Y-%m-%d'),
                datetime.now().strftime('%H:%M:%S'),
                "✅ Ro'yxatdan o'tgan"
            ]
            
            # Ma'lumotlarni yozish
            self.worksheet.update(f'A{next_row}:J{next_row}', [row_data])
            
            # Muvaffaqiyatli qatorga format berish
            self.worksheet.format(f'A{next_row}:J{next_row}', {
                "backgroundColor": {"red": 0.58, "green": 0.77, "blue": 0.49},
                "textFormat": {"bold": False}
            })
            
            logging.info(f"✅ Foydalanuvchi Google Sheets ga qo'shildi: {user_data['name']}")
            return True
            
        except Exception as e:
            logging.error(f"❌ Google Sheets ga yozishda xatolik: {e}")
            return False

# Google Sheets managerini yaratish
gs_manager = GoogleSheetsManager()

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
    # Adminlar uchun alohida xabar
    if message.from_user.id in ADMINS:
        # Admin state ni tozalash
        current_state = await dp.current_state(user=message.from_user.id).get_state()
        if current_state:
            await dp.current_state(user=message.from_user.id).finish()
        
        await message.reply(
            f"👋 <b>Xush kelibsiz, Admin!</b>\n\n"
            f"🤖 <b>Admin panel:</b>\n"
            f"📊 /stats - Statistika ko'rish\n"
            f"📁 /export - Google Sheets havolasi\n"
            f"👥 /users - Foydalanuvchilar ro'yxati\n\n"
            f"📝 <i>Agar ro'yxatdan o'tmoqchi bo'lsangiz, ismingizni kiriting:</i>",
            parse_mode="HTML"
        )
    else:
        # Oddiy foydalanuvchilar uchun
        await message.reply(
            f"Assalomu Alaykum, <b>{message.from_user.full_name}</b> 😊\n"
            "Autizm haqidagi qo'llanmani olish uchun 3 qadam qoldi 🤩 \n\n<b>1-qadam:</b>\n"
            "Ismingizni kiriting:",
            parse_mode="HTML"
        )
    
    # State ni to'g'ri o'rnatish
    await Register.name.set()

@dp.message_handler(state=Register.name)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name.replace(" ", "").isalpha() or len(name) < 2:
        await message.reply("❌ Iltimos, to'g'ri ism kiriting (faqat harflardan iborat bo'lsin)")
        return
    await state.update_data(name=name)
    await Register.location.set()
    await message.reply(
        "📍 Toshkent shahrining qaysi tumanida yashaysiz?",
        reply_markup=toshkent_tumanlari
    )

@dp.message_handler(state=Register.location)
async def process_location(message: types.Message, state: FSMContext):
    location = message.text
    await state.update_data(location=location)
    await Register.phone.set()
    
    contact_button = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    contact_button.add(types.KeyboardButton("📱 Telefon raqamini yuborish", request_contact=True))
    contact_button.add(types.KeyboardButton("✏️ Raqamni qo'lda kiritish"))
    
    await message.reply(
        "✅ <b>2-qadam:</b>\n\n"
        "Telefon raqamingizni kiriting:\n\n"
        "📱 <i>Telefon raqamini yuborish</i> tugmasini bosing yoki\n"
        "📝 <i>Raqamni qo'lda kiritish</i> tugmasini bosib, raqamingizni kiriting\n\n"
        "Namuna: <code>901234567</code>",
        parse_mode="HTML",
        reply_markup=contact_button
    )

@dp.message_handler(content_types=['contact', 'text'], state=Register.phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = ""
    if message.contact:
        phone = message.contact.phone_number
        # Ozbekiston raqamini formatlash
        if phone.startswith('+'):
            phone = phone
        elif phone.startswith('998'):
            phone = f"+{phone}"
        else:
            phone = f"+998{phone[-9:]}"
    else:
        phone_text = message.text
        
        if phone_text == "✏️ Raqamni qo'lda kiritish":
            await message.reply(
                "📝 Telefon raqamingizni kiriting:\n"
                "Namuna: <code>901234567</code> yoki <code>+998901234567</code>",
                parse_mode="HTML",
                reply_markup=types.ReplyKeyboardRemove()
            )
            return
        
        # Raqamni tozalash va formatlash
        phone_digits = re.sub(r'\D', '', phone_text)
        
        if len(phone_digits) == 9:
            phone = f"+998{phone_digits}"
        elif len(phone_digits) == 12 and phone_digits.startswith('998'):
            phone = f"+{phone_digits}"
        elif len(phone_digits) == 13 and phone_digits.startswith('998'):
            phone = f"+{phone_digits}"
        elif len(phone_digits) == 10 and phone_digits.startswith('8'):
            phone = f"+7{phone_digits[1:]}"
        elif phone_text.startswith('+'):
            phone = phone_text
        else:
            await message.reply(
                "❌ Noto'g'ri telefon raqami formati!\n\n"
                "✅ Qabul qilinadigan formatlar:\n"
                "• <code>901234567</code>\n"
                "• <code>+998901234567</code>\n"
                "• <code>998901234567</code>",
                parse_mode="HTML"
            )
            return
    
    data = await state.get_data()
    user_name = data.get('name')
    location = data.get('location')
    
    # User data for Google Sheets
    user_data = {
        "name": user_name,
        "location": location,
        "phone": phone,
        "user_id": message.from_user.id,
        "full_name": message.from_user.full_name,
        "username": message.from_user.username if message.from_user.username else '',
    }

    # Google Sheets ga yozish
    gs_success = gs_manager.add_user(user_data)
    
    # Admin xabari
    admin_message = (
        f"🎯 <b>Yangi ro'yxatdan o'tish:</b>\n\n"
        f"👤 <b>Ism:</b> {user_name}\n"
        f"📍 <b>Tuman:</b> {location}\n"
        f"📱 <b>Telefon:</b> {phone}\n"
        f"🆔 <b>User ID:</b> {message.from_user.id}\n"
        f"📛 <b>To'liq ism:</b> {message.from_user.full_name}\n"
        f"👤 <b>Username:</b> @{message.from_user.username if message.from_user.username else 'yoq'}\n"
        f"📅 <b>Vaqt:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📊 <b>Google Sheets:</b> {'✅ Saqlandi' if gs_success else '❌ Saqlanmadi'}\n\n"
        f"#yangi_royhat"
    )
    
    if not gs_success:
        admin_message += "\n\n⚠️ <b>Google Sheets ga saqlanmadi!</b>"
    
    # Adminlarga xabar yuborish
    if ADMINS:
        for admin_id in ADMINS:
            try:
                await bot.send_message(admin_id, admin_message, parse_mode="HTML")
            except exceptions.TelegramAPIError as e:
                logging.error(f"Admin {admin_id} ga xabar yuborishda xatolik: {e}")
    
    await state.finish()
    
    # Foydalanuvchiga javob
    success_message = "✅ Siz muvaffaqiyatli ro'yxatdan o'tdingiz!\n\n"
    if not gs_success:
        success_message += "⚠️ <i>Ma'lumotlaringiz saqlanmadi. Admin bilan bog'laning.</i>\n\n"
    
    success_message += "📚 Marhamat, autizm haqidagi maxsus qo'llanma:"
    
    # PDF faylni yuborish
    try:
        await message.reply(success_message, parse_mode="HTML")
        await message.reply_document(
            document=open("Autizm.pdf", "rb"),
            caption="",
            parse_mode="HTML"
        )
    except FileNotFoundError:
        await message.reply(
            f"{success_message}\n\n❌ Qo'llanma fayli hozirda mavjud emas.",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"PDF yuborishda xatolik: {e}")
        await message.reply(
            f"{success_message}\n\n❌ Qo'llanmani olishda texnik muammo yuz berdi.",
            parse_mode="HTML"
        )

# ======================= ADMIN KOMANDALARI =======================
@dp.message_handler(commands=['admin'], user_id=ADMINS)
async def admin_panel(message: types.Message):
    """Admin panel"""
    await message.reply(
        f"👋 <b>Xush kelibsiz, Admin!</b>\n\n"
        f"🤖 <b>Admin panel:</b>\n"
        f"📊 /stats - Statistika ko'rish\n"
        f"📁 /export - Google Sheets havolasi\n"
        f"👥 /users - Foydalanuvchilar ro'yxati\n"
        f"🔄 /restart - Botni qayta ishga tushirish\n\n"
        f"📈 <b>Bot holati:</b>\n"
        f"• Google Sheets: {'✅ Ulangan' if gs_manager.connected else '❌ Ulanmagan'}\n"
        f"• Adminlar soni: {len(ADMINS)}\n"
        f"• Bot ishlayapti: ✅",
        parse_mode="HTML"
    )

@dp.message_handler(commands=['stats'], user_id=ADMINS)
async def get_stats(message: types.Message):
    """Statistika olish"""
    try:
        if not gs_manager.connected:
            await message.reply("❌ Google Sheets ga ulanmagan!")
            return
        
        all_values = gs_manager.worksheet.get_all_values()
        total_users = len(all_values) - 1  # Header hisobga olinmagan
        
        if total_users == 0:
            await message.reply("📊 <b>Statistika:</b>\n\n❌ Hali hech qanday foydalanuvchi ro'yxatdan o'tmagan.", parse_mode="HTML")
            return
        
        # Tumanlar bo'yicha statistik
        locations = {}
        for row in all_values[1:]:  # Headerdan keyingi qatorlar
            if len(row) > 2 and row[2]:  # Tuman ustuni
                tuman = row[2]
                locations[tuman] = locations.get(tuman, 0) + 1
        
        # Xabar tayyorlash
        stats_message = f"📊 <b>Statistika:</b>\n\n"
        stats_message += f"👥 <b>Jami ro'yxatdan o'tganlar:</b> {total_users} ta\n\n"
        
        if locations:
            stats_message += f"📍 <b>Tumanlar bo'yicha:</b>\n"
            for tuman, count in sorted(locations.items(), key=lambda x: x[1], reverse=True):
                stats_message += f"  • {tuman}: {count} ta\n"
        
        # Oxirgi 3 ro'yxatdan o'tgan
        stats_message += f"\n⏰ <b>Oxirgi 3 ta ro'yxatdan o'tgan:</b>\n"
        last_3 = all_values[-3:] if len(all_values) > 3 else all_values[1:]
        for i, row in enumerate(last_3, 1):
            if len(row) > 1:
                stats_message += f"  {i}. {row[1]} - {row[2]} - {row[3]}\n"
        
        await message.reply(stats_message, parse_mode="HTML")
        
    except Exception as e:
        logging.error(f"Statistika olishda xatolik: {e}")
        await message.reply(f"❌ Statistika olishda xatolik: {str(e)}")

@dp.message_handler(commands=['users'], user_id=ADMINS)
async def get_users(message: types.Message):
    """Foydalanuvchilar ro'yxati"""
    try:
        if not gs_manager.connected:
            await message.reply("❌ Google Sheets ga ulanmagan!")
            return
        
        all_values = gs_manager.worksheet.get_all_values()
        if len(all_values) <= 1:
            await message.reply("📋 <b>Foydalanuvchilar ro'yxati:</b>\n\n❌ Hali hech qanday foydalanuvchi ro'yxatdan o'tmagan.", parse_mode="HTML")
            return
        
        users_list = "📋 <b>Oxirgi 10 ta foydalanuvchi:</b>\n\n"
        start_idx = max(1, len(all_values) - 10)  # Oxirgi 10 tasi
        
        for i, row in enumerate(all_values[start_idx:], start_idx):
            if len(row) > 3:
                users_list += f"<b>{row[0]}.</b> {row[1]} - {row[2]}\n"
                users_list += f"   📱 {row[3]}\n"
                users_list += f"   📅 {row[7]} {row[8]}\n"
                users_list += "   ────────\n"
        
        users_list += f"\n<b>Jami:</b> {len(all_values)-1} ta foydalanuvchi"
        
        await message.reply(users_list, parse_mode="HTML")
        
    except Exception as e:
        logging.error(f"Foydalanuvchilar ro'yxatini olishda xatolik: {e}")
        await message.reply(f"❌ Foydalanuvchilar ro'yxatini olishda xatolik: {str(e)}")

@dp.message_handler(commands=['export'], user_id=ADMINS)
async def export_data(message: types.Message):
    """Ma'lumotlarni export qilish"""
    try:
        if not gs_manager.connected:
            await message.reply("❌ Google Sheets ga ulanmagan!")
            return
        
        # Google Sheets havolasini olish
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{gs_manager.sheet.id}"
        
        await message.reply(
            f"📊 <b>Ma'lumotlar Google Sheets da:</b>\n\n"
            f"🔗 <a href='{spreadsheet_url}'>Havolani ochish</a>\n\n"
            f"📋 Foydalanuvchilar ro'yxati ushbu havolada saqlanmoqda.",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logging.error(f"Exportda xatolik: {e}")
        await message.reply(f"❌ Export qilishda xatolik: {str(e)}")

# ======================= QOLGAN HANDLERS =======================
@dp.message_handler(commands=['cancel'], state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.reply("⚠️ Hozir hech qanday amal bajarilmagan.")
        return
    
    await state.finish()
    await message.reply(
        "❌ Ro'yxatdan o'tish bekor qilindi.\n\n"
        "Qaytadan boshlash uchun /start ni bosing.",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message_handler(commands=['restart'])
async def restart_handler(message: types.Message):
    await send_welcome(message)

@dp.message_handler(state='*')
async def handle_all_messages(message: types.Message):
    current_state = await dp.current_state().get_state()
    if current_state:
        await message.reply(
            "❌ Iltimos, kerakli amalni bajaring.\n"
            "Davom etish uchun kerakli ma'lumotni kiriting yoki\n"
            "Bekor qilish uchun /cancel ni bosing.",
            reply_markup=types.ReplyKeyboardRemove()
        )

# ======================= FLASK SERVER =======================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot ishlayapti!"

@app.route('/health')
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.route('/sheet')
def sheet_link():
    if gs_manager.connected:
        return f"""
        <h1>Google Sheets</h1>
        <p>Spreadsheet ID: {gs_manager.sheet.id}</p>
        <p><a href="https://docs.google.com/spreadsheets/d/{gs_manager.sheet.id}" target="_blank">
        Havolani ochish</a></p>
        """
    return "Google Sheets ga ulanmagan"

# Webhook endpoint
@app.route('/webhook', methods=['POST'])
async def webhook():
    """Telegram webhook"""
    if request.method == 'POST':
        try:
            update = types.Update(**request.json)
            await dp.process_update(update)
            return 'OK'
        except Exception as e:
            logging.error(f"Webhook xatosi: {e}")
            return 'Error', 500
    return 'Method not allowed', 405

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

# =================== INTERNAL PING ===================
async def keep_alive_ping():
    url = os.environ.get("RENDER_EXTERNAL_URL", "http://127.0.0.1:5000")
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}/health") as resp:
                    if resp.status == 200:
                        logging.info(f"✅ Ping muvaffaqiyatli: {resp.status}")
                    else:
                        logging.warning(f"⚠️ Ping javobi: {resp.status}")
        except Exception as e:
            logging.error(f"❌ Ping xatoligi: {e}")
        await asyncio.sleep(300)

# =================== BOT START ===================
async def start_bot():
    asyncio.create_task(keep_alive_ping())
    
    # Agar RENDER environment bo'lsa, webhook ishlat
    if os.environ.get('RENDER'):
        # Webhook URL ni aniqlash
        service_name = os.environ.get('RENDER_SERVICE_NAME', 'rs-bot-6b9r')
        webhook_url = f"https://{service_name}.onrender.com/webhook"
        
        # Eski webhook ni tozalash
        await bot.delete_webhook()
        await asyncio.sleep(1)
        
        # Yangi webhook ni o'rnatish
        await bot.set_webhook(webhook_url)
        logging.info(f"✅ Webhook o'rnatildi: {webhook_url}")
        
        # Flask server ishlashini kuting
        return
    else:
        # Localda polling ishlat
        logging.info("🤖 Local polling rejimida ishlayapti...")
        await dp.start_polling()

# =================== MAIN ===================
if __name__ == "__main__":
    logging.info("🤖 Bot ishga tushmoqda...")
    
    # Google Sheets ulanishini tekshirish
    if not gs_manager.connected:
        logging.warning("⚠️ Google Sheets ga ulanmagan! Ma'lumotlar faqat Telegramda saqlanadi.")
    
    # Flask server
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Aiogram bot
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(start_bot())
    except KeyboardInterrupt:
        logging.info("📴 Bot to'xtatilmoqda...")
    except Exception as e:
        logging.error(f"❌ Botda xatolik: {e}")
    finally:
        logging.info("✅ Bot to'xtatildi")
