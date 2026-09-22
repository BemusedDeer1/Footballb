import aiosqlite
from config import DATABASE_PATH

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # جدول کاربران همراه با ستون‌های جدید XP و آمارهای کامل پروفایل
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                points INTEGER DEFAULT 100,
                xp INTEGER DEFAULT 0,
                duel_wins INTEGER DEFAULT 0,
                total_predictions INTEGER DEFAULT 0,
                correct_results INTEGER DEFAULT 0,
                exact_predictions INTEGER DEFAULT 0,
                season_gold INTEGER DEFAULT 0,
                season_silver INTEGER DEFAULT 0,
                season_bronze INTEGER DEFAULT 0,
                last_daily_date TEXT,
                last_shoot_date TEXT,
                last_wheel_date TEXT,
                penalty_date TEXT,
                penalty_count INTEGER DEFAULT 0,
                last_guess_date TEXT,
                guess_count INTEGER DEFAULT 0,
                total_answers INTEGER DEFAULT 0,
                correct_answers INTEGER DEFAULT 0,
                penalty_wins INTEGER DEFAULT 0,
                guess_wins INTEGER DEFAULT 0
            )
        """)

        # جدول پیش‌بینی مسابقات
        await db.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                match_id TEXT,
                outcome_choice TEXT,
                predicted_home INTEGER DEFAULT 0,
                predicted_away INTEGER DEFAULT 0,
                UNIQUE(user_id, match_id)
            )
        """)

        # جدول استخرهای ۳۰۰ امتیازی ویژه
        await db.execute("""
            CREATE TABLE IF NOT EXISTS special_pool_predictions (
                match_id TEXT,
                user_id INTEGER,
                user_name TEXT,
                choice TEXT,
                settled INTEGER DEFAULT 0,
                PRIMARY KEY (match_id, user_id)
            )
        """)

        # جدول تنظیمات داخلی ربات (مثل گروه زنده و ماه‌شمار سیزن)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await db.commit()
