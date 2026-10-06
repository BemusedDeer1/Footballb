import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "football_hub.db")

# سیستم امتیازدهی پیش‌فرض
DEFAULT_POINTS = {
    "EXACT_SCORE": 5,
    "CORRECT_OUTCOME": 3,
    "GOAL_DIFFERENCE": 2,
    "PARTICIPATION": 10,
    "WRONG": 0
}

# کدهای معتبر لیگ‌ها و تورنمنت‌های ملی و باشگاهی
LEAGUE_CODES = {
    "PL": {"name": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 لیگ برتر انگلیس", "id": "eng.1"},
    "LL": {"name": "🇪🇸 لالیگا اسپانیا", "id": "esp.1"},
    "SA": {"name": "🇮🇹 سری آ ایتالیا", "id": "ita.1"},
    "BL": {"name": "🇩🇪 بوندسلیگا آلمان", "id": "ger.1"},
    "L1": {"name": "🇫🇷 لوشامپیونه فرانسه", "id": "fra.1"},
    "UCL": {"name": "🏆 لیگ قهرمانان اروپا", "id": "uefa.champions"},
    "PG": {"name": "🇮🇷 لیگ برتر ایران", "id": "irn.1"},
    "INT": {"name": "🌍 بازی‌های ملی و فیفادی", "id": "fifa.friendly"},
    "NL": {"name": "🇪🇺 لیگ ملت‌های اروپا", "id": "uefa.nations"},
    "WCQ_ASIA": {"name": "🌏 انتخابی جام جهانی (آسیا)", "id": "fifa.worldq.afc"},
    "WCQ_EUR": {"name": "🏆 انتخابی جام جهانی (اروپا)", "id": "fifa.worldq.uefa"}
}

# لیست لیگ‌های فعال برای پایش زنده و پیش‌بینی
ACTIVE_MONITOR_LEAGUES = [
    "esp.1",
    "eng.1",
    "uefa.champions",
    "fifa.friendly",
    "uefa.nations",
    "fifa.worldq.afc",
    "fifa.worldq.uefa"
]
