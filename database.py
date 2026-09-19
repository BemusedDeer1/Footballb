import aiosqlite
from config import DATABASE_PATH
import os

async def init_db():
    # اطمینان از وجود پوشه data
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # جدول کاربران با ۱۰۰ امتیاز پیش‌فرض
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
                streak INTEGER DEFAULT 0,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # جدول پیش‌بینی‌ها
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
        await db.commit()
