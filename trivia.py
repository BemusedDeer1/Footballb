import os
import json
import random
import re

DATA_FILE = os.path.join(os.path.dirname(__file__), "trivia_data.json")

# الگوهای سوالات اسکریپتی مبهم که بیش از یک گزینه صحیح دارند
AMBIGUOUS_PATTERNS = (
    "در پست «مربی»",
    "با نقش «مربی»",
    "کدام بازیکن در پست «مهاجم نوک» بازی کرده است؟",
    "کدام گزینه بازیکنی با پست «دروازه‌بان» را نشان می‌دهد؟",
    "کدام بازیکن در پست «هافبک مرکزی» بازی کرده است؟",
    "کدام بازیکن در پست «هافبک دفاعی» بازی کرده است؟",
)

def clean_nickname_options(question, options):
    """پاک‌سازی فلگ‌ها و ایموجی‌ها از گزینه‌های سوالات مربوط به لقب"""
    if "لقب" in question and ("چیست" in question or "شناخته می‌شود" in question):
        def _clean(value):
            value = re.sub(r"[\U0001F1E6-\U0001F1FF]{2}", "", value)
            value = re.sub(r"[\U000E0061-\U000E007A\U000E007F]+", "", value)
            value = value.replace("🏴", "").replace("🏳️", "").replace("🏁", "")
            return value.replace("\ufe0f", "").strip()
        return [_clean(x) for x in options]
    return options

def _is_valid_question(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    q_text = item.get("question", "")
    opts = item.get("options", [])
    c_idx = item.get("correct_idx")
    if not q_text or not isinstance(opts, list) or len(opts) != 4:
        return False
    if not isinstance(c_idx, int) or not (0 <= c_idx < 4):
        return False
    if any(pat in q_text for pat in AMBIGUOUS_PATTERNS):
        return False
    return True

def _load_or_build():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            cleaned_data = []
            for q in raw_data:
                if _is_valid_question(q):
                    q["options"] = clean_nickname_options(q["question"], q["options"])
                    cleaned_data.append(q)
            if len(cleaned_data) >= 50:
                return cleaned_data
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
    selected = random.sample(pool, min(count, len(pool)))
    # بازگرداندن کپی مستقل همراه با بر زدن گزینه‌ها برای جلوگیری از حفظ کردن جای گزینه
    final_questions = []
    for q in selected:
        opts = list(q["options"])
        correct_answer = opts[q["correct_idx"]]
        random.shuffle(opts)
        final_questions.append({
            "question": q["question"],
            "options": opts,
            "correct_idx": opts.index(correct_answer),
            "difficulty": q.get("difficulty", "normal"),
            "category": q.get("category", "دانستنی")
        })
    return final_questions
