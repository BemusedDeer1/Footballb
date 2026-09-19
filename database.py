import aiosqlite
import logging
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # جدول کاربران
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                points INTEGER DEFAULT 100,
                exact_predictions INTEGER DEFAULT 0,
                correct_results INTEGER DEFAULT 0,
                total_predictions INTEGER DEFAULT 0,
                duel_wins INTEGER DEFAULT 0
            )
        """)
        
        # جدول پیش‌بینی‌های عادی
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

        # جدول تنظیمات سیستم (مانند شناسه گروه پخش زنده)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # جدول استخر پیش‌بینی ویژه ۳۰۰ امتیازی بازی‌های رئال و بارسا
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
        logger.info("Database initialized successfully with Live & Pool tables!")
