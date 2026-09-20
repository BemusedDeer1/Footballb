import aiosqlite
import logging
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # جدول اصلی کاربران به همراه ردیاب‌های فعالیت‌های روزانه و ویترین مدال‌های سیزن
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                points INTEGER DEFAULT 100,
                exact_predictions INTEGER DEFAULT 0,
                correct_results INTEGER DEFAULT 0,
                total_predictions INTEGER DEFAULT 0,
                duel_wins INTEGER DEFAULT 0,
                last_daily_date TEXT DEFAULT '',
                last_shoot_date TEXT DEFAULT '',
                last_wheel_date TEXT DEFAULT '',
                last_guess_date TEXT DEFAULT '',
                penalty_date TEXT DEFAULT '',
                penalty_count INTEGER DEFAULT 0,
                season_gold INTEGER DEFAULT 0,
                season_silver INTEGER DEFAULT 0,
                season_bronze INTEGER DEFAULT 0
            )
        """)

        # افزودن خودکار ستون‌های جدید در صورت وجود دیتابیس قبلی
        cols_to_add = [
            ("last_daily_date", "TEXT DEFAULT ''"),
            ("last_shoot_date", "TEXT DEFAULT ''"),
            ("last_wheel_date", "TEXT DEFAULT ''"),
            ("last_guess_date", "TEXT DEFAULT ''"),
            ("penalty_date", "TEXT DEFAULT ''"),
            ("penalty_count", "INTEGER DEFAULT 0"),
            ("season_gold", "INTEGER DEFAULT 0"),
            ("season_silver", "INTEGER DEFAULT 0"),
            ("season_bronze", "INTEGER DEFAULT 0")
        ]
        for col_name, col_type in cols_to_add:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

        # جدول تنظیمات سیستم و گزارش زنده
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # جدول پیش‌بینی‌های عمومی مسابقات
        await db.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                match_id TEXT,
                outcome_choice TEXT,
                predicted_home INTEGER DEFAULT 0,
                predicted_away INTEGER DEFAULT 0,
                status TEXT DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, match_id)
            )
        """)

        # جدول استخر ویژه ۳۰۰ امتیازی مسابقات رئال و بارسا
        await db.execute("""
            CREATE TABLE IF NOT EXISTS special_pool_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT,
                user_id INTEGER,
                user_name TEXT,
                choice TEXT,
                settled INTEGER DEFAULT 0,
                UNIQUE(match_id, user_id)
            )
        """)

        await db.commit()
        logger.info("Database initialized successfully with Season Trophy Cabinet and Persistent Trackers!")
