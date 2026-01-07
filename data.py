import os
import json
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMINS = [int(admin_id) for admin_id in os.getenv("ADMINS", "").split(",") if admin_id]

SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "RAHIMOV SCHOOL")

# 🔐 CREDENTIALS HANDLE
GOOGLE_JSON_STR = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
if GOOGLE_JSON_STR:
    try:
        GOOGLE_CREDENTIALS = json.loads(GOOGLE_JSON_STR)
        CREDENTIALS_FILE = None # Dictionary ishlatiladi
    except Exception as e:
        print(f"❌ JSON PARSE ERROR: {e}")
        CREDENTIALS_FILE = "credentials.json"
else:
    CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    GOOGLE_CREDENTIALS = None

# 💡 PRO TIP: Agar env variable ichida JSON bo'lsa, uni faylga vaqtinchalik saqlash mumkin
# Lekin Render uchun eng yaxshi yo'l "Secret Files" dan foydalanishdir.

HEADER_COLOR = {"red": 0.29, "green": 0.53, "blue": 0.91}
SUCCESS_COLOR = {"red": 0.58, "green": 0.77, "blue": 0.49}
