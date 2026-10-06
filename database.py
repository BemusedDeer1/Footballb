import aiosqlite
from config import DATABASE_PATH

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # جدول اصلی کاربران به همراه تمام آمارهای پروفایل، سیزن و مینی‌گیم‌ها
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                points INTEGER DEFAULT 100,
                profile_xp INTEGER DEFAULT 0,
                profile_level INTEGER DEFAULT 1,
                duel_wins INTEGER DEFAULT 0,
                total_predictions INTEGER DEFAULT 0,
                correct_results INTEGER DEFAULT 0,
                exact_predictions INTEGER DEFAULT 0,
                season_gold INTEGER DEFAULT 0,
                season_silver INTEGER DEFAULT 0,
                season_bronze INTEGER DEFAULT 0,
                season_fourth INTEGER DEFAULT 0,
                last_daily_date TEXT,
                last_shoot_date TEXT,
                last_wheel_date TEXT,
                penalty_date TEXT,
                penalty_count INTEGER DEFAULT 0,
                last_guess_date TEXT,
                guess_count INTEGER DEFAULT 0,
                profile_answered INTEGER DEFAULT 0,
                profile_correct INTEGER DEFAULT 0,
                penalty_wins INTEGER DEFAULT 0,
                guess_wins INTEGER DEFAULT 0,
                jackpot_wins INTEGER DEFAULT 0
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
                settled INTEGER DEFAULT 0,
                won INTEGER DEFAULT 0,
                UNIQUE(user_id, match_id)
            )
        """)

        # جدول استخرهای ویژه ۳۰۰ امتیازی مسابقات زنده
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

        # جدول ثبت فرم‌های جک‌پات کمبو ۵ مسابقه‌ای
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jackpot_combos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name TEXT,
                round_id TEXT,
                predictions_json TEXT,
                status TEXT DEFAULT 'PENDING',
                correct_count INTEGER DEFAULT 0,
                created_at TEXT,
                UNIQUE(user_id, round_id)
            )
        """)

        # جدول راندهای فعال جک‌پات کمبو
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jackpot_rounds (
                round_id TEXT PRIMARY KEY,
                title TEXT,
                matches_json TEXT,
                pool_amount INTEGER DEFAULT 500,
                is_active INTEGER DEFAULT 1,
                is_settled INTEGER DEFAULT 0,
                created_at TEXT,
                settled_at TEXT
            )
        """)

        # جدول تنظیمات داخلی ربات
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # مایگریشن خودکار برای دیتابیس‌های قدیمی بدون از دست رفتن دیتا
        columns_to_ensure = {
            "profile_xp": "INTEGER DEFAULT 0",
            "profile_level": "INTEGER DEFAULT 1",
            "profile_correct": "INTEGER DEFAULT 0",
            "profile_answered": "INTEGER DEFAULT 0",
            "penalty_wins": "INTEGER DEFAULT 0",
            "guess_wins": "INTEGER DEFAULT 0",
            "jackpot_wins": "INTEGER DEFAULT 0",
            "season_gold": "INTEGER DEFAULT 0",
            "season_silver": "INTEGER DEFAULT 0",
            "season_bronze": "INTEGER DEFAULT 0",
            "season_fourth": "INTEGER DEFAULT 0",
        }

        async with db.execute("PRAGMA table_info(users)") as cur:
            existing_cols = {row[1] for row in await cur.fetchall()}

        for col_name, col_def in columns_to_ensure.items():
            if col_name not in existing_cols:
                try:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
                except Exception:
                    pass

        await db.commit()
