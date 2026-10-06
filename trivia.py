import os
import json
import random
import re

DATA_FILE = os.path.join(os.path.dirname(__file__), "trivia_data.json")

def clean_nickname_options(question, options):
    """پاک‌سازی فلگ‌ها و ایموجی‌ها از گزینه‌های سوالات مربوط به لقب"""
    if "لقب" in question and "چیست" in question:
        def _clean(value):
            value = re.sub(r"[\U0001F1E6-\U0001F1FF]{2}", "", value)
            value = re.sub(r"[\U000E0061-\U000E007A\U000E007F]+", "", value)
            value = value.replace("🏴", "").replace("🏳️", "").replace("🏁", "")
            return value.replace("\ufe0f", "").strip()
        return [_clean(x) for x in options]
    return options

def _load_or_build():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if len(data) >= 100 and all("question" in q and "options" in q for q in data[:20]):
                return data
        except Exception:
            pass
    return []

QUESTION_BANK = _load_or_build()
HARD_QUESTIONS = [q for q in QUESTION_BANK if q.get("difficulty") in ("hard", "very_hard", "expert")]
NORMAL_QUESTIONS = [q for q in QUESTION_BANK if q.get("difficulty") == "normal"]

def get_random_duel_questions(count=3):
    count = max(1, int(count))
    if not QUESTION_BANK:
        raise RuntimeError("trivia_data.json is missing or invalid")
    pool = HARD_QUESTIONS + NORMAL_QUESTIONS
    if len(pool) < count:
        pool = QUESTION_BANK
    return random.sample(pool, min(count, len(pool)))
