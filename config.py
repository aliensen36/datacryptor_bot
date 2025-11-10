import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_LITE = os.getenv('DB_LITE')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения")

if not DB_LITE:
    raise ValueError("DB_LITE не найден в переменных окружения")