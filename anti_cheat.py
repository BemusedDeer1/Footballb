from datetime import datetime
import aiosqlite
from config import DATABASE_PATH, DEFAULT_POINTS

async def is_prediction_allowed(user_id: int, match_time_iso: str, match_id: str) -> bool:
    """جلوگیری از ثبت پیش‌بینی بعد از سوت شروع یا پیش‌بینی تکراری"""
    # بررسی زمان مسابقه
    try:
        clean_time = match_time_iso.replace("Z", "+00:00")
        kickoff = datetime.fromisoformat(clean_time)
        if datetime.utcnow() >= kickoff.replace(tzinfo=None):
            return False
    except Exception:
        pass

    # بررسی سابقه پیش‌بینی در دیتابیس
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT id FROM predictions WHERE user_id = ? AND match_id = ?", (user_id, match_id)) as cur:
            row = await cur.fetchone()
            return row is None

async def calculate_points(home_real: int, away_real: int, home_pred: int, away_pred: int, outcome_choice: str) -> int:
    """محاسبه غیرتکراری بر اساس قوانین تعیین‌شده"""
    real_outcome = "DRAW"
    if home_real > away_real:
        real_outcome = "HOME"
    elif away_real > home_real:
        real_outcome = "AWAY"

    # نتیجه دقیق
    if home_real == home_pred and away_real == away_pred:
        return DEFAULT_POINTS["EXACT_SCORE"]

    # تفاضل گل مساوی
    if (home_real - away_real) == (home_pred - away_pred) and real_outcome == outcome_choice:
        return DEFAULT_POINTS["GOAL_DIFFERENCE"]

    # برنده یا مساوی درست
    if real_outcome == outcome_choice:
        return DEFAULT_POINTS["CORRECT_OUTCOME"]

    return DEFAULT_POINTS["WRONG"]
  
