import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMINS = [int(admin_id) for admin_id in os.getenv("ADMINS", "").split(",") if admin_id]

SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "RAHIMOV SCHOOL")
CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")

HEADER_COLOR = {"red": 0.29, "green": 0.53, "blue": 0.91}
SUCCESS_COLOR = {"red": 0.58, "green": 0.77, "blue": 0.49}
