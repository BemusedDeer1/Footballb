import aiosqlite
import json
from config import DATABASE_PATH

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # جدول کاربران
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                points INTEGER DEFAULT 0,
                exact_predictions INTEGER DEFAULT 0,
                correct_results INTEGER DEFAULT 0,
                total_predictions INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                favorite_teams TEXT DEFAULT '[]',
                notifications_enabled INTEGER DEFAULT 1,
                is_banned INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # جدول مسابقات جهت کش و مدیریت وضعیت
        await db.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                match_id TEXT PRIMARY KEY,
                league_id TEXT,
                home_team TEXT,
                away_team TEXT,
                kickoff TIMESTAMP,
                status TEXT, -- 'UPCOMING', 'LIVE', 'FINISHED'
                home_score INTEGER,
                away_score INTEGER,
                is_featured INTEGER DEFAULT 0,
                is_scored INTEGER DEFAULT 0
            )
        """)

        # جدول پیش‌بینی‌ها
        await db.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                match_id TEXT,
                predicted_home INTEGER,
                predicted_away INTEGER,
                outcome_choice TEXT, -- 'HOME', 'DRAW', 'AWAY'
                points_earned INTEGER DEFAULT 0,
                status TEXT DEFAULT 'PENDING', -- 'PENDING', 'CALCULATED'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, match_id)
            )
        """)

        # جدول لیگ‌های خصوصی دوستان
        await db.execute("""
            CREATE TABLE IF NOT EXISTS private_leagues (
                league_code TEXT PRIMARY KEY,
                league_name TEXT,
                owner_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS private_league_members (
                league_code TEXT,
                user_id INTEGER,
                PRIMARY KEY (league_code, user_id)
            )
        """)

        # جدول دستاوردها (Achievements)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_achievements (
                user_id INTEGER,
                badge_key TEXT,
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, badge_key)
            )
        """)

        await db.commit()
