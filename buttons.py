from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

toshkent_tumanlari = ReplyKeyboardMarkup(
    resize_keyboard=True,
    row_width=2
)

tumanlar = [
    "Bektemir",
    "Chilonzor",
    "Hamza (Yashnobod)",
    "Mirobod",
    "Mirzo Ulug‘bek",
    "Olmazor",
    "Sergeli",
    "Shayxontohur",
    "Uchtepa",
    "Yakkasaroy",
    "Yunusobod",
    "Yashnobod"
]

toshkent_tumanlari.add(
    *[KeyboardButton(text=tuman) for tuman in tumanlar]
)
