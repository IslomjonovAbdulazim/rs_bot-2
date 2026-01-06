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
from flask import Flask, request, jsonify
import aiohttp
import gspread
from google.oauth2.service_account import Credentials
from google.auth.exceptions import GoogleAuthError

# ======================= CONFIG IMPORT =======================
from data import BOT_TOKEN, ADMINS, SPREADSHEET_NAME, CREDENTIALS_FILE, HEADER_COLOR, SUCCESS_COLOR
from buttons import toshkent_tumanlari, phone_keyboard, cancel_keyboard

# ======================= LOGGING =======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ======================= GOOGLE SHEETS SETUP =======================
class GoogleSheetsManager:
    def __init__(self):
        self.sheet = None
        self.worksheet = None
        self.connected = False
        self.spreadsheet_id = None
        
    def connect(self):
        """Google Sheets ga ulanish"""
        try:
            # Avval credentials ni yaratish
            if not os.path.exists(CREDENTIALS_FILE):
                logger.info("📝 Credentials fayli topilmadi, yaratilmoqda...")
                if not setup_google_credentials():
                    logger.error("❌ Credentials yaratib bo'lmadi")
                    return False
            
            logger.info(f"📂 Credentials fayli: {CREDENTIALS_FILE}")
            
            # Service account email ni o'qish
            try:
                with open(CREDENTIALS_FILE, 'r') as f:
                    creds_data = json.load(f)
                    service_email = creds_data.get('client_email', 'Noma\'lum')
                    logger.info(f"📧 Service Account: {service_email}")
            except Exception as e:
                logger.error(f"❌ Credentials faylini o'qishda xatolik: {e}")
                return False
            
            # Scope larni aniqlash
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            # Autentifikatsiya
            logger.info("🔑 Google ga autentifikatsiya qilinmoqda...")
            creds = Credentials.from_service_account_file(
                CREDENTIALS_FILE, 
                scopes=scope
            )
            
            # Client yaratish
            client = gspread.authorize(creds)
            logger.info("✅ Google Sheets client yaratildi")
            
            # Spreadsheet ni ochish yoki yaratish
            try:
                self.sheet = client.open(SPREADSHEET_NAME)
                logger.info(f"✅ Spreadsheet topildi: {SPREADSHEET_NAME}")
            except gspread.SpreadsheetNotFound:
                logger.info(f"📄 Spreadsheet topilmadi, yangisini yaratmoqda...")
                try:
                    self.sheet = client.create(SPREADSHEET_NAME)
                    self.spreadsheet_id = self.sheet.id
                    
                    # Service account ga edit ruxsati berish
                    self.sheet.share(service_email, perm_type='user', role='writer')
                    
                    # Hammaga read-only ruxsati (ixtiyoriy)
                    # self.sheet.share('', perm_type='anyone', role='reader')
                    
                    logger.info(f"✅ Yangi spreadsheet yaratildi: {SPREADSHEET_NAME}")
                    logger.info(f"🔗 URL: https://docs.google.com/spreadsheets/d/{self.sheet.id}")
                except Exception as e:
                    logger.error(f"❌ Spreadsheet yaratishda xatolik: {e}")
                    return False
            except Exception as e:
                logger.error(f"❌ Spreadsheet ochishda xatolik: {e}")
                return False
            
            # Worksheet ni tekshirish yoki yaratish
            try:
                self.worksheet = self.sheet.get_worksheet(0)
                if self.worksheet is None:
                    raise Exception("Worksheet topilmadi")
                logger.info(f"✅ Worksheet topildi: {self.worksheet.title}")
            except:
                try:
                    self.worksheet = self.sheet.add_worksheet(
                        title="Foydalanuvchilar", 
                        rows=1000, 
                        cols=20
                    )
                    logger.info("✅ Worksheet yaratildi")
                except Exception as e:
                    logger.error(f"❌ Worksheet yaratishda xatolik: {e}")
                    return False
            
            # Headerlarni qo'shish (agar bo'sh bo'lsa)
            if not self.worksheet.get('A1'):
                headers = [
                    ['№', 'Ism', 'Tuman', 'Telefon', 'User ID', 'To\'liq Ism', 
                     'Username', 'Ro\'yxatdan o\'tgan sana', 'Vaqt', 'Status']
                ]
                self.worksheet.update('A1:J1', headers)
                
                # Format berish
                self.worksheet.format('A1:J1', {
                    "backgroundColor": HEADER_COLOR,
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    "horizontalAlignment": "CENTER"
                })
                logger.info("✅ Headerlar qo'shildi")
            
            self.connected = True
            self.spreadsheet_id = self.sheet.id
            logger.info("✅ Google Sheets ga muvaffaqiyatli ulandi")
            logger.info(f"📊 Jami qatorlar: {len(self.worksheet.get_all_values())}")
            return True
            
        except GoogleAuthError as e:
            logger.error(f"❌ Google autentifikatsiya xatosi: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Google Sheets ga ulanishda xatolik: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def add_user(self, user_data):
        """Yangi foydalanuvchini Google Sheets ga qo'shish"""
        if not self.connected:
            logger.error("❌ Google Sheets ga ulanmagan!")
            return False
        
        try:
            # Oxirgi qatorni topish
            all_values = self.worksheet.get_all_values()
            next_row = len(all_values) + 1
            
            # Ma'lumotlarni tayyorlash
            now = datetime.now()
            row_data = [
                next_row - 1,  # № (header hisobga olinmagan)
                user_data['name'],
                user_data['location'],
                user_data['phone'],
                user_data['user_id'],
                user_data['full_name'],
                user_data['username'],
                now.strftime('%Y-%m-%d'),
                now.strftime('%H:%M:%S'),
                "✅ Ro'yxatdan o'tgan"
            ]
            
            # Ma'lumotlarni yozish
            self.worksheet.update(f'A{next_row}:J{next_row}', [row_data])
            
            # Muvaffaqiyatli qatorga format berish
            self.worksheet.format(f'A{next_row}:J{next_row}', {
                "backgroundColor": SUCCESS_COLOR,
                "textFormat": {"bold": False}
            })
            
            logger.info(f"✅ Foydalanuvchi Google Sheets ga qo'shildi: {user_data['name']}")
            logger.info(f"📊 Yangi jami: {len(self.worksheet.get_all_values())} qator")
            return True
            
        except Exception as e:
            logger.error(f"❌ Google Sheets ga yozishda xatolik: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def get_stats(self):
        """Statistika olish"""
        if not self.connected:
            return None
        
        try:
            all_values = self.worksheet.get_all_values()
            total_users = len(all_values) - 1  # Header hisobga olinmagan
            
            # Tumanlar bo'yicha statistik
            locations = {}
            for row in all_values[1:]:  # Headerdan keyingi qatorlar
                if len(row) > 2 and row[2]:  # Tuman ustuni
                    tuman = row[2]
                    locations[tuman] = locations.get(tuman, 0) + 1
            
            return {
                'total_users': total_users,
                'locations': locations,
                'last_3': all_values[-3:] if len(all_values) > 3 else all_values[1:]
            }
        except Exception as e:
            logger.error(f"❌ Statistika olishda xatolik: {e}")
            return None

# Google Sheets managerini yaratish
gs_manager = GoogleSheetsManager()

# ======================= STATES =======================
class Register(StatesGroup):
    name = State()
    location = State()
    phone = State()

# ======================= BOT SETUP =======================
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN topilmadi! Environment variable ni tekshiring.")
    exit(1)

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=storage)

# ======================= HANDLERS =======================
@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message, state: FSMContext):
    # Avvalgi state ni tozalash
    current_state = await state.get_state()
    if current_state:
        await state.finish()
    
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    
    # Adminlar uchun alohida xabar
    if user_id in ADMINS:
        await message.reply(
            f"👋 <b>Xush kelibsiz, Admin!</b>\n\n"
            f"🤖 <b>Admin panel:</b>\n"
            f"📊 /stats - Statistika ko'rish\n"
            f"📁 /export - Google Sheets havolasi\n"
            f"👥 /users - Foydalanuvchilar ro'yxati\n"
            f"🔄 /restart - Botni qayta ishga tushirish\n\n"
            f"📝 <i>Agar ro'yxatdan o'tmoqchi bo'lsangiz, ismingizni kiriting:</i>",
            parse_mode="HTML"
        )
    else:
        # Oddiy foydalanuvchilar uchun
        await message.reply(
            f"Assalomu Alaykum, <b>{user_name}</b> 😊\n"
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
    # Tuman to'g'riligini tekshirish (ixtiyoriy)
    valid_tumanlar = ["Olmazor", "Bektemir", "Mirzo Ulug'bek", "Sergeli",
                     "Yashnobod", "Chilonzor", "Yunusobod", "Shayxontohur",
                     "Uchtepa", "Yakkasaroy", "Mirobod"]
    
    if location not in valid_tumanlar:
        await message.reply("❌ Iltimos, ro'yxatdan tuman tanlang", reply_markup=toshkent_tumanlari)
        return
    
    await state.update_data(location=location)
    await Register.phone.set()
    
    await message.reply(
        "✅ <b>2-qadam:</b>\n\n"
        "Telefon raqamingizni kiriting:\n\n"
        "📱 <i>Telefon raqamini yuborish</i> tugmasini bosing yoki\n"
        "📝 <i>Raqamni qo'lda kiritish</i> tugmasini bosib, raqamingizni kiriting\n\n"
        "Namuna: <code>901234567</code>",
        parse_mode="HTML",
        reply_markup=phone_keyboard
    )

@dp.message_handler(content_types=['contact', 'text'], state=Register.phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = ""
    
    if message.contact:
        # Kontakt orqali
        phone = message.contact.phone_number
        # Ozbekiston raqamini formatlash
        if phone.startswith('+'):
            phone = phone
        elif phone.startswith('998'):
            phone = f"+{phone}"
        else:
            phone = f"+998{phone[-9:]}"
    else:
        # Matn orqali
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
        elif phone_text.startswith('+998') and len(phone_text) == 13:
            phone = phone_text
        else:
            await message.reply(
                "❌ Noto'g'ri telefon raqami formati!\n\n"
                "✅ Qabul qilinadigan formatlar:\n"
                "• <code>901234567</code>\n"
                "• <code>+998901234567</code>\n"
                "• <code>998901234567</code>\n\n"
                "Iltimos, qaytadan kiriting:",
                parse_mode="HTML"
            )
            return
    
    # Ma'lumotlarni olish
    data = await state.get_data()
    user_name = data.get('name', '')
    location = data.get('location', '')
    
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
    
    # Adminlarga xabar yuborish
    if ADMINS:
        for admin_id in ADMINS:
            try:
                await bot.send_message(admin_id, admin_message, parse_mode="HTML")
            except exceptions.TelegramAPIError as e:
                logger.error(f"Admin {admin_id} ga xabar yuborishda xatolik: {e}")
    
    # State ni tozalash
    await state.finish()
    
    # Foydalanuvchiga javob
    success_message = "✅ <b>Tabriklaymiz!</b>\nSiz muvaffaqiyatli ro'yxatdan o'tdingiz! 🎉\n\n"
    if not gs_success:
        success_message += "⚠️ <i>Ma'lumotlaringiz Google Sheets ga saqlanmadi. Admin bilan bog'laning.</i>\n\n"
    
    success_message += "📚 Marhamat, autizm haqidagi maxsus qo'llanma:"
    
    # PDF faylni yuborish
    try:
        await message.reply(success_message, parse_mode="HTML", reply_markup=types.ReplyKeyboardRemove())
        await message.reply_document(
            document=open("Autizm.pdf", "rb"),
            caption="",
            parse_mode="HTML"
        )
    except FileNotFoundError:
        await message.reply(
            f"{success_message}\n\n❌ Qo'llanma fayli hozirda mavjud emas. Admin bilan bog'laning.",
            parse_mode="HTML",
            reply_markup=types.ReplyKeyboardRemove()
        )
    except Exception as e:
        logger.error(f"PDF yuborishda xatolik: {e}")
        await message.reply(
            f"{success_message}\n\n❌ Qo'llanmani olishda texnik muammo yuz berdi. Admin bilan bog'laning.",
            parse_mode="HTML",
            reply_markup=types.ReplyKeyboardRemove()
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
        stats = gs_manager.get_stats()
        
        if not stats:
            await message.reply("❌ Statistika olishda xatolik yoki Google Sheets ulanmagan!", parse_mode="HTML")
            return
        
        total_users = stats['total_users']
        locations = stats['locations']
        
        if total_users == 0:
            await message.reply("📊 <b>Statistika:</b>\n\n❌ Hali hech qanday foydalanuvchi ro'yxatdan o'tmagan.", parse_mode="HTML")
            return
        
        # Xabar tayyorlash
        stats_message = f"📊 <b>Statistika:</b>\n\n"
        stats_message += f"👥 <b>Jami ro'yxatdan o'tganlar:</b> {total_users} ta\n\n"
        
        if locations:
            stats_message += f"📍 <b>Tumanlar bo'yicha:</b>\n"
            for tuman, count in sorted(locations.items(), key=lambda x: x[1], reverse=True):
                stats_message += f"  • {tuman}: {count} ta\n"
        
        # Oxirgi 3 ro'yxatdan o'tgan
        stats_message += f"\n⏰ <b>Oxirgi 3 ta ro'yxatdan o'tgan:</b>\n"
        last_3 = stats['last_3']
        for i, row in enumerate(last_3, 1):
            if len(row) > 1:
                stats_message += f"  {i}. {row[1]} - {row[2]} - {row[3]}\n"
        
        await message.reply(stats_message, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Statistika olishda xatolik: {e}")
        await message.reply(f"❌ Statistika olishda xatolik: {str(e)}")

@dp.message_handler(commands=['users'], user_id=ADMINS)
async def get_users(message: types.Message):
    """Foydalanuvchilar ro'yxati"""
    try:
        if not gs_manager.connected:
            await message.reply("❌ Google Sheets ga ulanmagan!", parse_mode="HTML")
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
                if len(row) > 7:
                    users_list += f"   📅 {row[7]} {row[8] if len(row) > 8 else ''}\n"
                users_list += "   ────────\n"
        
        users_list += f"\n<b>Jami:</b> {len(all_values)-1} ta foydalanuvchi"
        
        await message.reply(users_list, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Foydalanuvchilar ro'yxatini olishda xatolik: {e}")
        await message.reply(f"❌ Foydalanuvchilar ro'yxatini olishda xatolik: {str(e)}", parse_mode="HTML")

@dp.message_handler(commands=['export'], user_id=ADMINS)
async def export_data(message: types.Message):
    """Ma'lumotlarni export qilish"""
    try:
        if not gs_manager.connected:
            await message.reply("❌ Google Sheets ga ulanmagan!", parse_mode="HTML")
            return
        
        # Google Sheets havolasini olish
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{gs_manager.spreadsheet_id}"
        
        await message.reply(
            f"📊 <b>Ma'lumotlar Google Sheets da:</b>\n\n"
            f"🔗 <a href='{spreadsheet_url}'>Havolani ochish</a>\n\n"
            f"📋 Foydalanuvchilar ro'yxati ushbu havolada saqlanmoqda.\n"
            f"📊 Jami: {len(gs_manager.worksheet.get_all_values())-1} ta foydalanuvchi",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Exportda xatolik: {e}")
        await message.reply(f"❌ Export qilishda xatolik: {str(e)}", parse_mode="HTML")

# ======================= QOLGAN HANDLERS =======================
@dp.message_handler(commands=['cancel'], state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.reply("⚠️ Hozir hech qanday amal bajarilmagan.", parse_mode="HTML")
        return
    
    await state.finish()
    await message.reply(
        "❌ Ro'yxatdan o'tish bekor qilindi.\n\n"
        "Qaytadan boshlash uchun /start ni bosing.",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="HTML"
    )

@dp.message_handler(commands=['restart'])
async def restart_handler(message: types.Message, state: FSMContext):
    await state.finish()
    await send_welcome(message, state)

@dp.message_handler(state='*')
async def handle_all_messages(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        await message.reply(
            "❌ Iltimos, kerakli amalni bajaring.\n"
            "Davom etish uchun kerakli ma'lumotni kiriting yoki\n"
            "Bekor qilish uchun /cancel ni bosing.",
            reply_markup=cancel_keyboard,
            parse_mode="HTML"
        )
    else:
        await message.reply(
            "🤖 Botga xush kelibsiz!\n"
            "Ro'yxatdan o'tish uchun /start ni bosing.",
            parse_mode="HTML"
        )

# ======================= FLASK SERVER =======================
app = Flask(__name__)

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Autizm Bot</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            .status { color: green; font-weight: bold; }
            .error { color: red; }
        </style>
    </head>
    <body>
        <h1>🤖 Autizm Bot</h1>
        <p class="status">✅ Bot ishlayapti!</p>
        <p>Google Sheets: <span class="{'status' if gs_manager.connected else 'error'}">
            {'✅ Ulangan' if gs_manager.connected else '❌ Ulanmagan'}
        </span></p>
        <p><a href="/health">Health Check</a> | <a href="/sheet">Google Sheets</a></p>
        <p>Telegram: @autizm_qollanma_bot</p>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "google_sheets": gs_manager.connected,
        "bot": "running"
    })

@app.route('/sheet')
def sheet_link():
    if gs_manager.connected and gs_manager.spreadsheet_id:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Google Sheets</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .link {{ 
                    display: inline-block; 
                    padding: 15px 30px; 
                    background: #1a73e8; 
                    color: white; 
                    text-decoration: none; 
                    border-radius: 5px; 
                    font-size: 18px;
                }}
                .link:hover {{ background: #0d62d9; }}
            </style>
        </head>
        <body>
            <h1>📊 Google Sheets</h1>
            <p>Bot ma'lumotlari saqlanadigan spreadsheet</p>
            <a href="https://docs.google.com/spreadsheets/d/{gs_manager.spreadsheet_id}" 
               target="_blank" class="link">📂 Spreadsheetni ochish</a>
            <p style="margin-top: 30px;">
                <a href="/">← Ortga</a>
            </p>
        </body>
        </html>
        """
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Google Sheets</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            .error { color: red; }
        </style>
    </head>
    <body>
        <h1>📊 Google Sheets</h1>
        <p class="error">❌ Google Sheets ga ulanmagan!</p>
        <p><a href="/">← Ortga</a></p>
    </body>
    </html>
    """

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
            logger.error(f"Webhook xatosi: {e}")
            return 'Error', 500
    return 'Method not allowed', 405

def run_flask():
    """Flask server ishga tushirish"""
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# =================== KEEP ALIVE PING ===================
async def keep_alive_ping():
    """Botni faol ushlab turish uchun ping"""
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        logger.info("⚠️ RENDER_EXTERNAL_URL topilmadi, ping o'chirildi")
        return
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}/health") as resp:
                    if resp.status == 200:
                        logger.debug(f"✅ Ping muvaffaqiyatli: {resp.status}")
                    else:
                        logger.warning(f"⚠️ Ping javobi: {resp.status}")
        except Exception as e:
            logger.error(f"❌ Ping xatoligi: {e}")
        await asyncio.sleep(300)  # 5 daqiqa

# =================== BOT START ===================
async def start_bot():
    """Botni ishga tushirish"""
    logger.info("🤖 Bot ishga tushmoqda...")
    
    # Google Sheets ulanishini tekshirish
    if not gs_manager.connect():
        logger.warning("⚠️ Google Sheets ga ulanmagan! Ma'lumotlar faqat Telegramda saqlanadi.")
    else:
        logger.info("✅ Google Sheets ga muvaffaqiyatli ulandi")
    
    # Environment variables tekshirish
    logger.info(f"🔧 Environment tekshiruv:")
    logger.info(f"   • BOT_TOKEN: {'✅' if BOT_TOKEN else '❌'}")
    logger.info(f"   • ADMINS: {len(ADMINS)} ta")
    logger.info(f"   • GOOGLE_CREDENTIALS: {'✅' if os.environ.get('GOOGLE_CREDENTIALS') else '❌'}")
    logger.info(f"   • SPREADSHEET_NAME: {SPREADSHEET_NAME}")
    
    # Agar RENDER environment bo'lsa, webhook ishlat
    if os.environ.get('RENDER'):
        service_name = os.environ.get('RENDER_SERVICE_NAME')
        webhook_url = f"https://{service_name}.onrender.com/webhook"
        
        # Eski webhook ni tozalash
        await bot.delete_webhook()
        await asyncio.sleep(1)
        
        # Yangi webhook ni o'rnatish
        await bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook o'rnatildi: {webhook_url}")
        
        # Keep alive ping
        asyncio.create_task(keep_alive_ping())
    else:
        # Localda polling ishlat
        logger.info("🔧 Local polling rejimida ishlayapti...")
        await bot.delete_webhook()
        await dp.start_polling()

# =================== MAIN ===================
def main():
    """Asosiy dastur"""
    try:
        # Flask server thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info("✅ Flask server ishga tushdi")
        
        # Botni ishga tushirish
        asyncio.run(start_bot())
        
    except KeyboardInterrupt:
        logger.info("📴 Bot to'xtatilmoqda...")
    except Exception as e:
        logger.error(f"❌ Botda xatolik: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("✅ Bot to'xtatildi")

if __name__ == "__main__":
    main()
