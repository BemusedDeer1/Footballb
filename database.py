import aiosqlite
import logging
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # 1. جدول اصلی کاربران
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                points INTEGER DEFAULT 100,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                duel_wins INTEGER DEFAULT 0,
                penalty_wins INTEGER DEFAULT 0,
                guess_wins INTEGER DEFAULT 0,
                total_predictions INTEGER DEFAULT 0,
                correct_results INTEGER DEFAULT 0,
                exact_predictions INTEGER DEFAULT 0,
                season_gold INTEGER DEFAULT 0,
                season_silver INTEGER DEFAULT 0,
                season_bronze INTEGER DEFAULT 0,
                season_fourth INTEGER DEFAULT 0,
                last_daily_date TEXT DEFAULT '',
                last_shoot_date TEXT DEFAULT '',
                last_wheel_date TEXT DEFAULT '',
                last_guess_date TEXT DEFAULT '',
                guess_count INTEGER DEFAULT 0,
                penalty_date TEXT DEFAULT '',
                penalty_count INTEGER DEFAULT 0,
                profile_xp INTEGER DEFAULT 0,
                profile_level INTEGER DEFAULT 1,
                profile_correct INTEGER DEFAULT 0,
                profile_answered INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. بررسی و اضافه کردن خودکار ستون‌های جاافتاده در کاربران موجود (Safe Migration)
        async with db.execute("PRAGMA table_info(users)") as cur:
            columns = [row[1] for row in await cur.fetchall()]

        required_user_columns = {
            "level": "INTEGER DEFAULT 1",
            "penalty_wins": "INTEGER DEFAULT 0",
            "guess_wins": "INTEGER DEFAULT 0",
            "season_gold": "INTEGER DEFAULT 0",
            "season_silver": "INTEGER DEFAULT 0",
            "season_bronze": "INTEGER DEFAULT 0",
            "season_fourth": "INTEGER DEFAULT 0",
            "profile_xp": "INTEGER DEFAULT 0",
            "profile_level": "INTEGER DEFAULT 1",
            "profile_correct": "INTEGER DEFAULT 0",
            "profile_answered": "INTEGER DEFAULT 0",
            "last_daily_date": "TEXT DEFAULT ''",
            "last_shoot_date": "TEXT DEFAULT ''",
            "last_wheel_date": "TEXT DEFAULT ''",
            "last_guess_date": "TEXT DEFAULT ''",
            "guess_count": "INTEGER DEFAULT 0",
            "penalty_date": "TEXT DEFAULT ''",
            "penalty_count": "INTEGER DEFAULT 0"
        }

        for col_name, col_def in required_user_columns.items():
            if col_name not in columns:
                try:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
                    logger.info(f"Added column {col_name} to users table.")
                except Exception as e:
                    logger.debug(f"Column {col_name} already exists or error: {e}")

        # 3. جدول پیش‌بینی‌های مسابقات روزانه
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

        # 4. جدول استخر ۳۰۰ امتیازی مسابقات ویژه
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

        # 5. جدول تنظیمات سیستمی و ادمین
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # 6. جدول راندهای جک‌پات هفتگی
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

        # 7. جدول فرم‌های ثبت‌شده جک‌پات کاربران
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

        # 8. جدول کارت‌های خریداری‌شده بازیکنان FC
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                player_name TEXT,
                rating INTEGER,
                position TEXT,
                rarity TEXT,
                is_in_lineup INTEGER DEFAULT 0,
                acquired_at TEXT
            )
        """)

        # 9. جدول مارکت و پیشنهادات روزانه نقل‌وانتقالات
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_market (
                user_id INTEGER,
                date_str TEXT,
                offers_json TEXT,
                PRIMARY KEY (user_id, date_str)
            )
        """)

        # 10. جدول ماموریت‌های روزانه (Daily Quests)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_quests (
                user_id INTEGER,
                date_str TEXT,
                penalties_played INTEGER DEFAULT 0,
                card_matches_played INTEGER DEFAULT 0,
                predictions_made INTEGER DEFAULT 0,
                is_claimed INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date_str)
            )
        """)

        # 11. جداول لیگ رفت و برگشت کارت‌های FC
        await db.execute("""
            CREATE TABLE IF NOT EXISTS league_seasons (
                season_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'ACTIVE',
                created_at TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS league_fixtures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id TEXT,
                home_id INTEGER,
                away_id INTEGER,
                home_score INTEGER DEFAULT 0,
                away_score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'PENDING',
                played_date TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS league_standings (
                season_id TEXT,
                user_id INTEGER,
                played INTEGER DEFAULT 0,
                won INTEGER DEFAULT 0,
                drawn INTEGER DEFAULT 0,
                lost INTEGER DEFAULT 0,
                gf INTEGER DEFAULT 0,
                ga INTEGER DEFAULT 0,
                gd INTEGER DEFAULT 0,
                points INTEGER DEFAULT 0,
                PRIMARY KEY (season_id, user_id)
            )
        """)

        await db.commit()
        logger.info("Database initialized and verified successfully.")
