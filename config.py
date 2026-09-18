import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "football_hub.db")

# سیستم امتیازدهی پیش‌فرض (قابل ویرایش توسط ادمین در ربات)
DEFAULT_POINTS = {
    "EXACT_SCORE": 5,
    "CORRECT_OUTCOME": 3,
    "GOAL_DIFFERENCE": 2,
    "WRONG": 0
}

# کدهای معتبر لیگ‌ها در سیستم بدون نیاز به توکن
LEAGUE_CODES = {
    "PL": {"name": "🇬🇧 لیگ برتر انگلیس", "id": "eng.1"},
    "LL": {"name": "🇪🇸 لالیگا اسپانیا", "id": "esp.1"},
    "SA": {"name": "🇮🇹 سری آ ایتالیا", "id": "ita.1"},
    "BL": {"name": "🇩🇪 بوندسلیگا آلمان", "id": "ger.1"},
    "L1": {"name": "🇫🇷 لوشامپیونه فرانسه", "id": "fra.1"},
    "PG": {"name": "🇮🇷 لیگ برتر ایران", "id": "irn.1"}
}
