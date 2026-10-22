import os
import re
import html
import random
import logging
import asyncio
import threading
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from collections import Counter

import aiosqlite
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)

from config import BOT_TOKEN, ADMIN_ID, DATABASE_PATH, DEFAULT_POINTS, LEAGUE_CODES, ACTIVE_MONITOR_LEAGUES
from database import init_db
from football_provider import provider
import keyboards as kb
from trivia import get_random_duel_questions
from fc_catalog import FC_CATALOG, FC_CATALOG_DICT, RARITY_COLORS, SELL_PRICES

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ESCOBAR_AI_ID = 999999999
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))
LRM = "\u200E"

# بانک سوالات چالش دوبل یا پوچ
HARDCORE_QUIZ_POOL = [
    {
        "question": "در فینال جام جهانی ۱۹۵۴ (معجزه برن)، زننده گل برتری دقیقه ۸۴ آلمان غربی چه کسی بود؟",
        "options": ["هلموت ران", "فریتز والتر", "ماکس مورلوک", "اووه زلر"],
        "correct": "هلموت ران"
    },
    {
        "question": "کدام دروازه‌بان در ضربات پنالتی فینال جام باشگاه‌های اروپا ۱۹۸۶ هر ۴ پنالتی بارسلونا را مهار کرد؟",
        "options": ["هلموت دوکادام", "استوان استویانوویچ", "پیتر اشمایکل", "سیلوینو"],
        "correct": "هلموت دوکادام"
    },
    {
        "question": "اولین بازیکنی که در تاریخ جام‌های جهانی کارت قرمز دریافت کرد چه کسی بود؟",
        "options": ["کارلوس کازلی", "کارلوس کاستیلیو", "روبن توریبیو", "آنتونیو راتین"],
        "correct": "کارلوس کازلی"
    },
    {
        "question": "کدام باشگاه رکورددار طولانی‌ترین روند شکست‌ناپذیری متوالی در تاریخ لیگ‌های اروپایی (۱۰۴ بازی) است؟",
        "options": ["استوا بخارست", "سلتیک", "بنفیکا", "آژاکس"],
        "correct": "استوا بخارست"
    },
    {
        "question": "کدام کشور اولین دوره جام ملت‌های آسیا در سال ۱۹۵۶ را فتح کرد؟",
        "options": ["کره جنوبی", "اسرائیل", "ایران", "هنگ کنگ"],
        "correct": "کره جنوبی"
    },
    {
        "question": "در فینال جام جهانی ۱۹۳۸، مجموعاً چند گل بین ایتالیا و مجارستان رد و بدل شد؟",
        "options": ["۶ گل", "۴ گل", "۵ گل", "۷ گل"],
        "correct": "۶ گل"
    },
    {
        "question": "کدام بازیکن در سه جام جهانی مختلف (۱۹۵۸، ۱۹۶۲، ۱۹۷۰) برای برزیل گلزنی کرد به جز پله؟",
        "options": ["واوا", "گارینشا", "ماریو زاگالو", "دیدی"],
        "correct": "واوا"
    },
    {
        "question": "در فینال لیگ قهرمانان ۱۹۹۹، چه کسی در دقیقه ۹۱ گل اول منچستریونایتد به بایرن مونیخ را زد؟",
        "options": ["تدی شرینگهام", "اوله گونار سولشایر", "پل اسکولز", "دوایت یورک"],
        "correct": "تدی شرینگهام"
    },
    {
        "question": "آقای گل جام جهانی ۱۹۹۴ که در یک بازی ۵ گل به کامرون زد چه کسی بود؟",
        "options": ["اولگ سالنکو", "هریستو استویچکوف", "روماریو", "یورگن کلینزمن"],
        "correct": "اولگ سالنکو"
    },
    {
        "question": "در فینال جام جهانی ۱۹۶۶، کمک‌داوری که گل بحث‌برانگیز انگلیس به آلمان را تایید کرد اهل کدام کشور بود؟",
        "options": ["شوروی (آذربایجان)", "سوئیس", "یوگسلاوی", "مصر"],
        "correct": "شوروی (آذربایجان)"
    },
    {
        "question": "اولین برنده توپ طلای غیراروپایی تاریخ فرانس فوتبال در سال ۱۹۹۵ چه کسی بود؟",
        "options": ["ژرژ وه‌آ", "روماریو", "رونالدو نازاریو", "عبدی پله"],
        "correct": "ژرژ وه‌آ"
    },
    {
        "question": "حریف ناتینگهام فارست در فینال جام باشگاه‌های اروپا ۱۹۷۹ که ۱-۰ مغلوب شد کدام تیم بود؟",
        "options": ["مالمو سوئد", "هامبورگ", "کلن", "آژاکس"],
        "correct": "مالمو سوئد"
    },
    {
        "question": "زننده تک گل پیروزی‌بخش فینال یورو ۲۰۰۴ برای تیم ملی یونان مقابل پرتغال چه کسی بود؟",
        "options": ["آنجلوس چاریستیاس", "تئودوروس زاگوراکیس", "گیورگوس کاراگونیس", "دیمیتریس پاپادوپولوس"],
        "correct": "آنجلوس چاریستیاس"
    },
    {
        "question": "در جام جهانی ۱۹۸۶، مارادونا گل قرن را با عبور از کدام دروازه‌بان انگلیس به ثمر رساند؟",
        "options": ["پیتر شیلتون", "دیوید سیمن", "گوردون بنکس", "ری کلمنس"],
        "correct": "پیتر شیلتون"
    },
    {
        "question": "کدام تیم ملی در فینال یورو ۱۹۹۲ مقابل دانمارک شگفتی‌ساز شکست خورد؟",
        "options": ["آلمان", "هلند", "سوئد", "فرانسه"],
        "correct": "آلمان"
    }
]

GUESS_PLAYERS_FILE = os.path.join(os.path.dirname(__file__), "guess_players.json")
try:
    with open(GUESS_PLAYERS_FILE, "r", encoding="utf-8") as f:
        RAW_GUESS_PLAYERS = json.load(f)
except Exception as e:
    logger.error(f"Error loading guess_players.json: {e}")
    RAW_GUESS_PLAYERS = []

GUESS_DECK = []

def refill_guess_deck():
    global GUESS_DECK
    GUESS_DECK = RAW_GUESS_PLAYERS.copy()
    random.shuffle(GUESS_DECK)

def get_next_guess_player():
    global GUESS_DECK
    if not GUESS_DECK:
        refill_guess_deck()
    if not GUESS_DECK:
        return {
            "names": ["مسی", "messi"],
            "nation": "آرژانتین 🇦🇷",
            "pos": "مهاجم کاذب",
            "career": ["بارسلونا 🇪🇸", "اینتر میامی 🇺🇸"],
            "clue": "⭐ برنده ۸ توپ طلا"
        }
    return GUESS_DECK.pop()

ACTIVE_GUESS_GAMES = {}
MATCH_CACHE = {}
ACTIVE_DUELS = {}
ACTIVE_TEAM_DUELS = {}
ACTIVE_SHOOTOUTS = {}
ACTIVE_CARD_MATCHES = {}
ACTIVE_DOUBLE_GAMES = {}
CHEAT_MODE_USERS = set()
TRACKED_LIVE_MATCHES = {}
USER_JACKPOT_DRAFTS = {}
ACTIVE_ASYNCIO_TIMERS = {}

# --- قوانین و پلن‌های تخصصی سیستم اوولوشن (EVOLUTION PLANS) ---
EVO_PLANS = {
    "academy": {
        "title": "🧬 جهش آکادمی (Future Prodigy)",
        "desc": "ارتقای پدیده‌های جوان و بازیکنان معمولی به سطح گلد ریر",
        "boost": 5, "max_input_ovr": 80, "rarities": ["COMMON"],
        "cost": 1200, "sac_rarity": "COMMON", "sac_count": 3
    },
    "rare_boost": {
        "title": "💎 کیمیاگری کهکشانی (Galactico Blueprint)",
        "desc": "ارتقای ستاره‌های گلد ریر به رده بازیکنان نخبه الیت",
        "boost": 3, "min_input_ovr": 81, "max_input_ovr": 85, "rarities": ["RARE"],
        "cost": 2500, "sac_rarity": "RARE", "sac_count": 2
    },
    "elite_push": {
        "title": "⚡️ تولد اسطوره (Legendary Metamorphosis)",
        "desc": "تبدیل سوپراستارهای الیت به تالار افتخارات آیکان",
        "boost": 3, "min_input_ovr": 86, "max_input_ovr": 89, "rarities": ["ELITE"],
        "cost": 5000, "sac_rarity": "ELITE", "sac_count": 2
    },
    "icon_titan": {
        "title": "👑 تایتان نامیرا (Immortal Titan)",
        "desc": "تقویت سنگین اسطوره‌ها و آیکان‌های تاریخ (تا سقف ۹۶)",
        "boost": 2, "min_input_ovr": 90, "max_input_ovr": 94, "rarities": ["ICON"],
        "cost": 8500, "sac_rarity": "ICON", "sac_count": 1
    },
    "messi_99": {
        "title": "🐐🇦🇷 لا پولگا جاودانه (La Pulga Immortal)",
        "desc": "آزاد کردن پتانسیل ماورایی لیونل مسی و جهش به ۹۹ OVR",
        "target_name": "لیونل مسی", "fixed_ovr": 99,
        "cost": 18000, "sac_icon": 2, "sac_elite": 3
    },
    "cr7_99": {
        "title": "🐐🇵🇹 فرمانده ماورایی (El Comandante Prime)",
        "desc": "آزاد کردن نسخه اوج و بی‌مرگ کریستیانو رونالدو و جهش به ۹۹ OVR",
        "target_name": "کریستیانو رونالدو", "fixed_ovr": 99,
        "cost": 18000, "sac_icon": 2, "sac_elite": 3
    }
}

def schedule_timer(context, callback_coro, delay_seconds, data, name=None):
    if getattr(context, 'job_queue', None):
        if name:
            cancel_timer(context, name)
        return context.job_queue.run_once(callback_coro, delay_seconds, data=data, name=name)

    async def _timer_runner():
        try:
            await asyncio.sleep(delay_seconds)
            class SimpleJob:
                def __init__(self, d): self.data = d
            class SimpleContext:
                def __init__(self, c, d):
                    self.bot = c.bot
                    self.application = getattr(c, 'application', None)
                    self.job_queue = None
                    self.job = SimpleJob(d)
            await callback_coro(SimpleContext(context, data))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f'Error in timer {name}: {e}')
        finally:
            if name: ACTIVE_ASYNCIO_TIMERS.pop(name, None)

    if name:
        cancel_timer(context, name)
    task = asyncio.create_task(_timer_runner())
    if name:
        ACTIVE_ASYNCIO_TIMERS[name] = task
    return task

def cancel_timer(context, name):
    if getattr(context, 'job_queue', None):
        for j in context.job_queue.get_jobs_by_name(name):
            j.schedule_removal()
    if name in ACTIVE_ASYNCIO_TIMERS:
        task = ACTIVE_ASYNCIO_TIMERS.pop(name, None)
        if task and not task.done():
            task.cancel()

async def run_repeating_task(coro_fn, app, interval_sec, initial_delay_sec=5):
    class SimpleContext:
        def __init__(self, application):
            self.bot = application.bot
            self.application = application
            self.job_queue = None

    await asyncio.sleep(initial_delay_sec)
    ctx = SimpleContext(app)
    while True:
        try:
            await coro_fn(ctx)
        except Exception as e:
            logger.error(f'Error in background task {coro_fn.__name__}: {e}')
        await asyncio.sleep(interval_sec)

LEAGUE_TITLES = {
    "eng.1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",
    "esp.1": "🇪🇸 La Liga",
    "ita.1": "🇮🇹 Serie A",
    "ger.1": "🇩🇪 Bundesliga",
    "fra.1": "🇫🇷 Ligue 1",
    "uefa.champions": "🏆 Champions League",
    "fifa.friendly": "🌍 مسابقات ملی و فیفادی",
    "uefa.nations": "🇪🇺 لیگ ملت‌های اروپا",
    "fifa.worldq.afc": "🌏 انتخابی جام جهانی (آسیا)",
    "fifa.worldq.uefa": "🏆 انتخابی جام جهانی (اروپا)",
    "irn.1": "🇮🇷 لیگ برتر ایران",
    "all": "🌐 گلچین مسابقات معتبر"
}

def get_iran_now():
    return datetime.now(IRAN_TZ)

def format_iran_time(dt_str: str) -> str:
    if not dt_str: return "نامشخص"
    try:
        clean_time = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_time)
        dt_iran = dt.astimezone(IRAN_TZ)
        return dt_iran.strftime("%H:%M")
    except Exception:
        return "نامشخص"

def is_match_still_open_for_prediction(match_dict: dict) -> bool:
    if not match_dict:
        return False
    status = str(match_dict.get("status", "UPCOMING")).upper()
    if status != "UPCOMING":
        return False
    dt_str = match_dict.get("date")
    if dt_str:
        try:
            clean_time = dt_str.replace("Z", "+00:00")
            kickoff = datetime.fromisoformat(clean_time)
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= kickoff:
                return False
        except Exception:
            pass
    return True

def get_user_tier(points: int) -> tuple[str, str]:
    pts = max(0, int(points or 0))
    if pts >= 3000: return "🌌", "Football Immortal"
    elif pts >= 2200: return "🐐", "G.O.A.T"
    elif pts >= 1600: return "⚡️", "Galactico"
    elif pts >= 1100: return "👑", "Ballon d'Or"
    elif pts >= 800: return "💎", "Legend"
    elif pts >= 550: return "🔮", "World Class"
    elif pts >= 350: return "🎖", "Captain"
    elif pts >= 200: return "🌟", "First Team"
    elif pts >= 100: return "⚡️", "Semi-Pro"
    else: return "🔰", "Academy"

def xp_for_next_level(level: int) -> int:
    return 100 + max(0, level - 1) * 25

def calculate_level(xp: int):
    level = 1
    remaining = max(0, int(xp or 0))
    while remaining >= xp_for_next_level(level):
        remaining -= xp_for_next_level(level)
        level += 1
        if level >= 1000: break
    needed = xp_for_next_level(level)
    percent = int((remaining / needed) * 100) if needed else 100
    return level, remaining, needed, percent

def render_xp_bar(percent: int, width: int = 10) -> str:
    percent = max(0, min(100, percent))
    filled = round(percent / 100 * width)
    return "█" * filled + "░" * (width - filled)

async def profile_add_xp(user_id: int, amount: int):
    if amount <= 0: return
    try:
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT profile_xp FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                cur_xp = row[0] if row and row[0] is not None else 0
            new_xp = cur_xp + amount
            lvl, _, _, _ = calculate_level(new_xp)
            await db.execute("UPDATE users SET profile_xp = ?, profile_level = ? WHERE user_id = ?", (new_xp, lvl, user_id))
            await db.commit()
    except Exception as e:
        logger.error(f"Error adding XP: {e}")

async def profile_record_answer(user_id: int, is_correct: bool):
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        if is_correct:
            await db.execute("""
                UPDATE users SET profile_answered = profile_answered + 1, profile_correct = profile_correct + 1
                WHERE user_id = ?
            """, (user_id,))
        else:
            await db.execute("UPDATE users SET profile_answered = profile_answered + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
    await profile_add_xp(user_id, 15 if is_correct else 3)

async def profile_record_duel_win(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("UPDATE users SET duel_wins = duel_wins + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
    await profile_add_xp(user_id, 120)

async def profile_record_penalty_win(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("UPDATE users SET penalty_wins = penalty_wins + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
    await profile_add_xp(user_id, 100)

async def profile_record_guess_win(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("UPDATE users SET guess_wins = guess_wins + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
    await profile_add_xp(user_id, 80)

def format_bidi_name(name: str) -> str:
    cleaned = (name or "بازیکن").strip()
    return f"{LRM}{html.escape(cleaned)}{LRM}"

class SimpleHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Football Hub Online! 200 OK")

    def log_message(self, format, *args): return

def start_health_server():
    port = int(os.getenv("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), SimpleHealthServer)
        logger.info(f"Health server on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Health server error: {e}")

def identify_tracked_team(team_name: str):
    name = (team_name or "").lower()
    if any(x in name for x in ["real madrid", "رئال مادرید", "madrid"]) and "atletico" not in name and "اتلتیکو" not in name:
        return "real"
    if any(x in name for x in ["barcelona", "بارسلونا", "barca"]):
        return "barca"
    if any(x in name for x in ["atletico", "اتلتیکو", "atlético"]):
        return "atletico"
    if any(x in name for x in ["liverpool", "لیورپول"]):
        return "liverpool"
    if any(x in name for x in ["manchester united", "man utd", "منچستر یونایتد", "یونایتد"]):
        return "united"
    return None

async def get_live_chat_id():
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = 'live_chat_id'") as cur:
            row = await cur.fetchone()
            if row and row[0]: return int(row[0])
    return None

async def is_action_allowed_in_chat(update: Update) -> bool:
    chat = update.effective_chat
    if not chat or chat.type == "private": return True
    target_chat_id = await get_live_chat_id()
    if not target_chat_id or chat.id == target_chat_id: return True
    await update.effective_message.reply_text(
        "⛔️ <b>بخش‌های مسابقاتی و امتیازی فقط در گروه اختصاصی ربات فعال است!</b>",
        parse_mode="HTML"
    )
    return False

async def safe_edit_message(query_or_bot, text, reply_markup=None, chat_id=None, message_id=None):
    try:
        if chat_id is not None and message_id is not None:
            await query_or_bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text,
                reply_markup=reply_markup, parse_mode="HTML"
            )
        else:
            await query_or_bot.message.edit_text(
                text=text, reply_markup=reply_markup, parse_mode="HTML"
            )
        return True
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.warning(f"Bad request in safe_edit_message: {e}")
        return False
    except Exception as e:
        logger.debug(f"Edit warning: {e}")
        return False

async def ensure_user(user):
    try:
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("""
                INSERT OR IGNORE INTO users (user_id, first_name, username, points, xp)
                VALUES (?, ?, ?, 100, 0)
            """, (user.id, user.first_name, user.username or ""))
            await db.execute("""
                UPDATE users SET first_name = ?, username = ? WHERE user_id = ?
            """, (user.first_name, user.username or "", user.id))
            await db.commit()
    except Exception as e:
        logger.error(f"Error in ensure_user: {e}")

async def ensure_escobar_ai():
    try:
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("""
                INSERT OR IGNORE INTO users (user_id, first_name, username, points, xp)
                VALUES (?, ?, ?, 100, 0)
            """, (ESCOBAR_AI_ID, "Escobar AI 🤖", "escobar_ai"))
            await db.commit()
    except Exception as e:
        logger.error(f"Error in ensure_escobar_ai: {e}")

async def get_wealth_multiplier():
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT AVG(points) FROM users WHERE user_id != ?", (ESCOBAR_AI_ID,)) as cur:
            row = await cur.fetchone()
            avg_pts = row[0] if row and row[0] else 200
    mult = 1.0 + max(0.0, (avg_pts - 300) / 1000.0)
    return min(2.5, mult)

async def get_penalty_count_db(user_id: int) -> int:
    today_str = get_iran_now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT penalty_date, penalty_count FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str: return row[1] or 0
    return 0

async def increment_penalty_count_db(user_id: int):
    today_str = get_iran_now().strftime("%Y-%m-%d")
    cur_count = await get_penalty_count_db(user_id)
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("""
            UPDATE users SET penalty_date = ?, penalty_count = ? WHERE user_id = ?
        """, (today_str, cur_count + 1, user_id))
        await db.commit()
    await record_quest_action(user_id, "penalties")

async def get_guess_count_db(user_id: int) -> int:
    today_str = get_iran_now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT last_guess_date, guess_count FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str: return row[1] or 0
    return 0

async def increment_guess_count_db(user_id: int):
    today_str = get_iran_now().strftime("%Y-%m-%d")
    cur_count = await get_guess_count_db(user_id)
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("""
            UPDATE users SET last_guess_date = ?, guess_count = ? WHERE user_id = ?
        """, (today_str, cur_count + 1, user_id))
        await db.commit()

# --- DAILY QUESTS ENGINE ---

async def record_quest_action(user_id: int, action_type: str):
    today_str = get_iran_now().strftime("%Y-%m-%d")
    col = ""
    if action_type == "penalties": col = "penalties_played"
    elif action_type == "card_matches": col = "card_matches_played"
    elif action_type == "predictions": col = "predictions_made"
    if not col: return

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute(f"""
            INSERT INTO daily_quests (user_id, date_str, {col})
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, date_str) DO UPDATE SET {col} = {col} + 1
        """, (user_id, today_str))
        await db.commit()

async def quests_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT penalties_played, card_matches_played, predictions_made, is_claimed FROM daily_quests WHERE user_id = ? AND date_str = ?", (user.id, today_str)) as cur:
            row = await cur.fetchone()

    p_count = row[0] if row else 0
    c_count = row[1] if row else 0
    pr_count = row[2] if row else 0
    claimed = row[3] if row else 0

    q1_done = p_count >= 2
    q2_done = c_count >= 1
    q3_done = pr_count >= 1
    all_done = q1_done and q2_done and q3_done

    q1_icon = "✅" if q1_done else f"⏳ ({min(p_count, 2)}/2)"
    q2_icon = "✅" if q2_done else f"⏳ ({min(c_count, 1)}/1)"
    q3_icon = "✅" if q3_done else f"⏳ ({min(pr_count, 1)}/1)"

    text = (
        f"🎯 <b>ماموریت‌های روزانه (Daily Quests)</b>\n"
        "────────────────────\n"
        f"1️⃣ انجام ۲ پنالتی: {q1_icon}\n"
        f"2️⃣ انجام ۱ مسابقه کارت: {q2_icon}\n"
        f"3️⃣ ثبت ۱ پیش‌بینی مسابقه: {q3_icon}\n"
        "────────────────────\n"
        f"🎁 <b>پاداش تکمیل کل ماموریت‌ها: +120 PTS و +50 XP</b>\n\n"
    )

    buttons = []
    if all_done:
        if claimed:
            text += "🎉 <i>شما پاداش امروز را دریافت کرده‌اید!</i>"
        else:
            buttons.append([InlineKeyboardButton("🎁 دریافت جایزه ۱۲۰ امتیازی", callback_data="claim_quests")])
    else:
        text += "⚡️ <i>با کامل کردن هر ۳ ماموریت، دکمه دریافت پاداش فعال می‌شود.</i>"

    buttons.append([InlineKeyboardButton("‹ بازگشت", callback_data="home")])
    kb_markup = InlineKeyboardMarkup(buttons)

    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)
    else: await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

# --- ADMIN ECONOMIC CONTROLS ---

async def halve_points_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("""
            UPDATE users 
            SET points = MAX(10, CAST(points / 2 AS INTEGER)) 
            WHERE user_id != ?
        """, (ESCOBAR_AI_ID,))
        await db.commit()

    await update.effective_message.reply_text(
        "📉 <b>شوک اقتصادی اعمال شد!</b>\nموجودی تمام کاربران به نصف کاهش یافت (با کف ۱۰ امتیاز).",
        parse_mode="HTML"
    )

    target_chat_id = await get_live_chat_id()
    if target_chat_id:
        msg = (
            "🏦📉 <b>اصلاحیه مالی و کنترل نقدینگی بازی!</b>\n"
            "────────────────────\n"
            "جهت ایجاد تعادل در بازار، موجودی حساب‌ها ۵۰٪ تعدیل شد. اکنون شکار کارت‌ها رقابتی‌تر خواهد بود!"
        )
        try: await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")
        except Exception: pass

async def reset_market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("DELETE FROM daily_market")
        await db.commit()

    await update.effective_message.reply_text("🔄 <b>مارکت روزانه برای تمام کاربران ریست شد!</b>", parse_mode="HTML")

async def finish_league_instantly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شبیه‌سازی یکجای تمام مسابقات باقی‌مانده لیگ جاری و اعلام قهرمان با دستور /l_end"""
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    chat_id = update.effective_chat.id

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        async with db.execute("SELECT season_id FROM league_seasons WHERE status = 'ACTIVE' LIMIT 1") as cur:
            row = await cur.fetchone()
            if not row:
                await update.effective_message.reply_text("⚠️ هیچ لیگی در وضعیت فعال (ACTIVE) پیدا نشد.", parse_mode="HTML")
                return
            s_id = row[0]

        async with db.execute("""
            SELECT id, home_id, away_id 
            FROM league_fixtures 
            WHERE season_id = ? AND (status = 'PENDING' OR status IS NULL OR status = '')
            ORDER BY id ASC
        """, (s_id,)) as cur:
            pending_matches = await cur.fetchall()

    if not pending_matches:
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await settle_league_season(context, db, s_id)
        await update.effective_message.reply_text("🏁 تمام بازی‌ها قبلاً انجام شده بود؛ فصل تسویه گردید.", parse_mode="HTML")
        return

    await update.effective_message.reply_text(
        f"⚡️ <b>شبیه‌سازی سریع کل فصل آغاز شد!</b>\nدر حال محاسبه <b>{len(pending_matches)} مسابقه</b> باقی‌مانده و بستن فوری پرونده لیگ...",
        parse_mode="HTML"
    )

    all_uids = {uid for _, h, a in pending_matches for uid in (h, a)}
    teams_data = {uid: await get_user_team_info(uid) for uid in all_uids}
    tactics_data = {uid: await get_user_tactics(uid) for uid in all_uids}

    now_time = get_iran_now().strftime("%Y-%m-%d %H:%M")
    match_updates = []

    for f_id, h_id, a_id in pending_matches:
        t1, t2 = teams_data[h_id], teams_data[a_id]
        tac1, tac2 = tactics_data[h_id], tactics_data[a_id]
        b1, b2, _ = calculate_tactical_clash(tac1, tac2)

        p1_power = (t1["eff_ovr"] ** 1.3) * (1 + t1["chem"] / 100.0) * (1.0 + b1)
        p2_power = (t2["eff_ovr"] ** 1.3) * (1 + t2["chem"] / 100.0) * (1.0 + b2)
        p1_chance_prob = max(0.20, min(0.80, p1_power / (p1_power + p2_power)))

        s1, s2 = 0, 0
        for _ in range(random.randint(6, 8)):
            if random.random() < p1_chance_prob:
                if simulate_chained_fc26_attack({"name": "میزبان", "team": t1}, {"name": "میهمان", "team": t2}, "")[0]:
                    s1 += 1
            else:
                if simulate_chained_fc26_attack({"name": "میهمان", "team": t2}, {"name": "میزبان", "team": t1}, "")[0]:
                    s2 += 1

        reward_h = (50 if s1 > s2 else (20 if s1 == s2 else 0)) + (s1 * 5)
        reward_a = (50 if s2 > s1 else (20 if s1 == s2 else 0)) + (s2 * 5)
        match_updates.append((f_id, h_id, a_id, s1, s2, reward_h, reward_a))

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        for f_id, h_id, a_id, s1, s2, reward_h, reward_a in match_updates:
            await db.execute("""
                UPDATE league_fixtures 
                SET home_score = ?, away_score = ?, status = 'FINISHED', played_date = ? 
                WHERE id = ?
            """, (s1, s2, now_time, f_id))

            w1, d1, l1, pts1 = (1, 0, 0, 3) if s1 > s2 else ((0, 1, 0, 1) if s1 == s2 else (0, 0, 1, 0))
            w2, d2, l2, pts2 = (1, 0, 0, 3) if s2 > s1 else ((0, 1, 0, 1) if s1 == s2 else (0, 0, 1, 0))

            await db.execute("""
                UPDATE league_standings 
                SET played = played + 1, won = won + ?, drawn = drawn + ?, lost = lost + ?,
                    gf = gf + ?, ga = ga + ?, gd = gd + ?, points = points + ? 
                WHERE season_id = ? AND user_id = ?
            """, (w1, d1, l1, s1, s2, s1 - s2, pts1, s_id, h_id))

            await db.execute("""
                UPDATE league_standings 
                SET played = played + 1, won = won + ?, drawn = drawn + ?, lost = lost + ?,
                    gf = gf + ?, ga = ga + ?, gd = gd + ?, points = points + ? 
                WHERE season_id = ? AND user_id = ?
            """, (w2, d2, l2, s2, s1, s2 - s1, pts2, s_id, a_id))

            if reward_h > 0:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward_h, h_id))
            if reward_a > 0:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward_a, a_id))

        await db.commit()
        await settle_league_season(context, db, s_id)

    await update.effective_message.reply_text(
        f"✅ <b>تمام {len(pending_matches)} مسابقه با موفقیت شبیه‌سازی و پرونده لیگ بسته شد!</b>",
        parse_mode="HTML"
    )

async def play_league_day_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای دستی و فوری ۲ مسابقه روزانه هر تیم در لیگ با دستور /pl"""
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    chat_id = update.effective_chat.id

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        async with db.execute("SELECT season_id FROM league_seasons WHERE status = 'ACTIVE' LIMIT 1") as cur:
            row = await cur.fetchone()
            if not row:
                await update.effective_message.reply_text(
                    "⚠️ <b>هیچ لیگی در حال حاضر فعال نیست!</b>\nابتدا با دستور <code>/l_on</code> لیگ جدید را آغاز کن.",
                    parse_mode="HTML"
                )
                return
            s_id = row[0]

        setting_key = f"last_league_run_{s_id}"
        await db.execute("DELETE FROM bot_settings WHERE key = ?", (setting_key,))
        await db.commit()

    await update.effective_message.reply_text(
        "⚽️ <b>سوت مسابقات لیگ زده شد!</b>\nدر حال شبیه‌سازی ۲ مسابقه برای هر تیم و محاسبه نتایج...",
        parse_mode="HTML"
    )
    await simulate_daily_league_task(context, reply_chat_id=chat_id)

async def add_points_to_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    if not context.args:
        await update.message.reply_text("⚠️ <b>نحوه استفاده:</b> <code>/all 500</code>", parse_mode="HTML")
        return

    try: amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً یک عدد معتبر وارد کنید.")
        return

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("UPDATE users SET points = points + ? WHERE user_id != ?", (amount, ESCOBAR_AI_ID))
        await db.commit()

    await update.message.reply_text(f"✅ <b>مبلغ {amount:,} امتیاز به تمام کاربران هدیه داده شد!</b>", parse_mode="HTML")

    target_chat_id = await get_live_chat_id()
    if target_chat_id:
        msg = f"🎉🎁 <b>هدیه همگانی از طرف مدیریت!</b>\nمبلغ <b>{amount:,} امتیاز</b> به حساب تمام کاربران واریز شد! 💰🔥"
        try: await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")
        except Exception: pass

async def add_points_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    if not context.args:
        await update.message.reply_text("⚠️ <b>نحوه استفاده:</b> <code>/add 500</code>", parse_mode="HTML")
        return

    try: amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً یک عدد معتبر وارد کنید.")
        return

    target_id, target_name = user.id, user.first_name
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_u = update.message.reply_to_message.from_user
        target_id, target_name = target_u.id, target_u.first_name
        await ensure_user(target_u)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, target_id))
        await db.commit()

    await update.message.reply_text(f"✅ <b>مبلغ {amount:,} امتیاز به {html.escape(target_name)} اضافه شد!</b>", parse_mode="HTML")

async def backup_db_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != str(ADMIN_ID): return
    if os.path.exists(DATABASE_PATH):
        with open(DATABASE_PATH, "rb") as doc:
            await update.message.reply_document(
                document=doc,
                filename=f"backup_{get_iran_now().strftime('%Y%m%d_%H%M')}.db",
                caption="💾 <b>نسخه کامل پشتیبان دیتابیس</b>\nجهت بازگردانی روی هاست جدید ریپلای کنید: <code>/restore</code>",
                parse_mode="HTML"
            )
    else:
        await update.message.reply_text("⚠️ فایل دیتابیس یافت نشد.")

async def restore_db_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != str(ADMIN_ID): return
    target_msg = update.message.reply_to_message
    if not target_msg or not target_msg.document:
        await update.message.reply_text("⚠️ برای بازگردانی، این دستور را روی فایل دیتابیس ریپلای کن:\n<code>/restore</code>", parse_mode="HTML")
        return

    try:
        doc = target_msg.document
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(DATABASE_PATH)
        await update.message.reply_text("✅ <b>دیتابیس با موفقیت جایگزین شد!</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error restoring DB: {e}")
        await update.message.reply_text(f"❌ خطا در بازگردانی فایل: {e}")

async def reset_points_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return
    try:
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("UPDATE users SET points = 100")
            await db.commit()
        await update.message.reply_text("✅ <b>امتیاز تمامی کاربران با موفقیت روی ۱۰۰ ریست شد!</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error resetting points: {e}")

async def set_live_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return
    chat = update.effective_chat
    if chat.type in ["group", "supergroup"]:
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('live_chat_id', ?)", (str(chat.id),))
            await db.commit()
        await update.message.reply_text(f"✅ <b>این گروه به عنوان گروه اختصاصی ثبت شد!</b> شناسه: <code>{chat.id}</code>", parse_mode="HTML")

async def generate_pool_message_text(match, participants):
    home_name = match.get("home_team", "میزبان")
    away_name = match.get("away_team", "میهمان")
    time_str = format_iran_time(match.get("date"))

    text = (
        f"🔥 <b>استخر جایزه ویژه ۳۰۰ امتیازی مسابقه بزرگ!</b> 🎁\n"
        "────────────────────\n"
        f"⚽️ <b>{home_name}</b> 🆚 <b>{away_name}</b>\n"
        f"⏰ ساعت شروع: <code>{time_str}</code> (تهران)\n"
        f"💰 جایزه کل: <b>300 امتیاز</b>\n"
        "────────────────────\n"
        "👥 <b>لیست شرکت‌کنندگان:</b>\n"
    )
    home_pickers = [p[0] for p in participants if p[1] == "HOME"]
    draw_pickers = [p[0] for p in participants if p[1] == "DRAW"]
    away_pickers = [p[0] for p in participants if p[1] == "AWAY"]

    h_str = ", ".join([html.escape(n) for n in home_pickers[:5]]) if home_pickers else "هیچ‌کس"
    d_str = ", ".join([html.escape(n) for n in draw_pickers[:5]]) if draw_pickers else "هیچ‌کس"
    a_str = ", ".join([html.escape(n) for n in away_pickers[:5]]) if away_pickers else "هیچ‌کس"

    text += f"▫️ برد {home_name} ({len(home_pickers)} نفر): <i>{h_str}</i>\n"
    text += f"▫️ تساوی ({len(draw_pickers)} نفر): <i>{d_str}</i>\n"
    text += f"▫️ برد {away_name} ({len(away_pickers)} نفر): <i>{a_str}</i>\n"
    text += "\n👇 <b>پیش‌بینی خود را انتخاب کنید:</b>"
    return text
# --- MONITORING LIVE MATCHES & REWARDING REGULAR PREDICTIONS ---

async def settle_regular_predictions_for_match(m_id: str, final_h: int, final_a: int) -> list[str]:
    actual_outcome = "HOME" if final_h > final_a else ("AWAY" if final_a > final_h else "DRAW")
    correct_regular_users = []

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("""
            SELECT p.user_id, u.first_name 
            FROM predictions p JOIN users u ON p.user_id = u.user_id
            WHERE p.match_id = ? AND p.outcome_choice = ? AND p.settled = 0
        """, (m_id, actual_outcome)) as cur:
            reg_winners = await cur.fetchall()

        for r_uid, r_name in reg_winners:
            await db.execute(
                "UPDATE users SET points = points + 40, correct_predictions = correct_predictions + 1 WHERE user_id = ?",
                (r_uid,)
            )
            correct_regular_users.append(r_name)

        await db.execute("UPDATE predictions SET settled = 1 WHERE match_id = ?", (m_id,))
        await db.commit()

    for r_uid, _ in reg_winners:
        await profile_add_xp(r_uid, 30)

    return correct_regular_users

async def monitor_live_matches_and_banter(context: ContextTypes.DEFAULT_TYPE):
    target_chat_id = await get_live_chat_id()
    iran_now = get_iran_now()
    today_str = iran_now.strftime("%Y%m%d")

    matches = []
    for l_code in ACTIVE_MONITOR_LEAGUES:
        try:
            m_list = await provider.get_matches(today_str, league_code=l_code)
            if m_list: matches.extend(m_list)
        except Exception:
            pass

    unique_matches = {str(m["id"]): m for m in matches}
    utc_now = datetime.now(timezone.utc)

    for m_id, m in unique_matches.items():
        MATCH_CACHE[m_id] = m
        raw_status = str(m.get("status", "UPCOMING")).upper()
        try:
            h_score = int(m.get("home_score")) if m.get("home_score") is not None else None
            a_score = int(m.get("away_score")) if m.get("away_score") is not None else None
        except Exception:
            h_score, a_score = None, None

        h_name, a_name = str(m.get("home_team", "")), str(m.get("away_team", ""))
        home_tracked, away_tracked = identify_tracked_team(h_name), identify_tracked_team(a_name)
        is_iran_match = "ایران" in h_name or "ایران" in a_name

        if not home_tracked and not away_tracked and not is_iran_match:
            if raw_status == "FINISHED" and h_score is not None and a_score is not None:
                await settle_regular_predictions_for_match(m_id, h_score, a_score)
            continue

        if not target_chat_id:
            continue

        track = TRACKED_LIVE_MATCHES.get(m_id)
        if not track:
            track = {
                "last_status": raw_status,
                "home_score": h_score if h_score is not None else 0,
                "away_score": a_score if a_score is not None else 0,
                "started_announced": False, "pool_opened": False, "pool_msg_id": None, "banter_sent": False
            }
            TRACKED_LIVE_MATCHES[m_id] = track

        match_date_str = m.get("date")
        minutes_to_start = 9999
        if match_date_str:
            try:
                dt_match = datetime.fromisoformat(match_date_str.replace("Z", "+00:00"))
                if dt_match.tzinfo is None:
                    dt_match = dt_match.replace(tzinfo=timezone.utc)
                minutes_to_start = (dt_match - utc_now).total_seconds() / 60
            except Exception:
                pass

        if 0 < minutes_to_start <= 45 and not track.get("pool_opened") and raw_status == "UPCOMING":
            track["pool_opened"] = True
            pool_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"⚪️ برد {h_name[:12]}", callback_data=f"pool_{m_id}_HOME"),
                 InlineKeyboardButton("🤝 تساوی", callback_data=f"pool_{m_id}_DRAW"),
                 InlineKeyboardButton(f"🔴 برد {a_name[:12]}", callback_data=f"pool_{m_id}_AWAY")]
            ])
            msg_text = await generate_pool_message_text(m, [])
            try:
                sent = await context.bot.send_message(chat_id=target_chat_id, text=msg_text, reply_markup=pool_kb, parse_mode="HTML")
                track["pool_msg_id"] = sent.message_id
            except Exception:
                pass

        if raw_status == "LIVE" and not track.get("started_announced"):
            track["started_announced"] = True
            time_str = format_iran_time(m.get("date"))
            start_msg = (
                f"🚨 <b>سوت آغاز مسابقه حساس!</b> ⚽️\n────────────────────\n"
                f"🏟 <b>{h_name}</b> 🆚 <b>{a_name}</b>\n⏰ شروع: <code>{time_str}</code> (تهران)\n"
                "▫️ استخر پیش‌بینی بسته شد. گزارش زنده آغاز گردید."
            )
            try: await context.bot.send_message(chat_id=target_chat_id, text=start_msg, parse_mode="HTML")
            except Exception: pass

        is_live = raw_status == "LIVE"
        is_finished = raw_status == "FINISHED"
        if (is_live or is_finished) and h_score is not None and a_score is not None:
            prev_h, prev_a = track["home_score"], track["away_score"]
            if h_score != prev_h or a_score != prev_a:
                track["home_score"], track["away_score"] = h_score, a_score
                goal_msg = f"⚽️🔥 <b>تغییر در نتیجه مسابقه! (گـُــل)</b>\n────────────────────\n▫️ <b>{h_name} [{h_score}] - [{a_score}] {a_name}</b>"
                try: await context.bot.send_message(chat_id=target_chat_id, text=goal_msg, parse_mode="HTML")
                except Exception: pass

        if is_finished and track["last_status"] != "FINISHED":
            track["last_status"] = "FINISHED"
            final_h = h_score if h_score is not None else track["home_score"]
            final_a = a_score if a_score is not None else track["away_score"]
            actual_outcome = "HOME" if final_h > final_a else ("AWAY" if final_a > final_h else "DRAW")

            correct_regular_users = await settle_regular_predictions_for_match(m_id, final_h, final_a)
            winners_text = ""

            if track.get("pool_opened"):
                async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                    async with db.execute("SELECT user_id, user_name FROM special_pool_predictions WHERE match_id = ? AND choice = ? AND settled = 0", (m_id, actual_outcome)) as cur:
                        winners = await cur.fetchall()
                    if winners:
                        share = 300 // len(winners)
                        winners_text = f"\n\n🎁 <b>برندگان استخر ۳۰۰ امتیازی (هر نفر +{share} PTS):</b>\n"
                        for w_id, w_name in winners:
                            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (share, w_id))
                            winners_text += f"▫️ <b>{html.escape(w_name)}</b>\n"
                    else:
                        winners_text = "\n\n▫️ در استخر ویژه کسی برنده نشد."
                    await db.execute("UPDATE special_pool_predictions SET settled = 1 WHERE match_id = ?", (m_id,))
                    await db.commit()

            reg_text = ""
            if correct_regular_users:
                names_str = ", ".join([f"<b>{html.escape(n)}</b>" for n in correct_regular_users[:6]])
                reg_text = f"\n\n🎯 <b>برندگان پیش‌بینی مسابقه (+40 PTS):</b>\n{names_str}"

            ft_msg = (
                f"🏁 <b>سوت پایان مسابقه (Full Time)</b>\n────────────────────\n"
                f"نتیجه قطعی: <b>{h_name} [{final_h}] - [{final_a}] {a_name}</b>"
                f"{reg_text}{winners_text}"
            )
            try: await context.bot.send_message(chat_id=target_chat_id, text=ft_msg, parse_mode="HTML")
            except Exception: pass

async def check_and_settle_monthly_season(context: ContextTypes.DEFAULT_TYPE):
    iran_now = get_iran_now()
    cur_month_str = iran_now.strftime("%Y-%m")

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = 'last_settled_month'") as cur:
            row = await cur.fetchone()
            last_settled = row[0] if row else None

        if not last_settled:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('last_settled_month', ?)", (cur_month_str,))
            await db.commit()
            return

        if cur_month_str != last_settled:
            async with db.execute("SELECT user_id, first_name, points FROM users WHERE user_id != ? ORDER BY points DESC LIMIT 4", (ESCOBAR_AI_ID,)) as cur:
                top4 = await cur.fetchall()

            if top4 and len(top4) >= 1:
                p1 = top4[0]
                await db.execute("UPDATE users SET season_gold = season_gold + 1 WHERE user_id = ?", (p1[0],))
                p2 = top4[1] if len(top4) >= 2 else None
                if p2: await db.execute("UPDATE users SET season_silver = season_silver + 1 WHERE user_id = ?", (p2[0],))
                p3 = top4[2] if len(top4) >= 3 else None
                if p3: await db.execute("UPDATE users SET season_bronze = season_bronze + 1 WHERE user_id = ?", (p3[0],))
                p4 = top4[3] if len(top4) >= 4 else None
                if p4: await db.execute("UPDATE users SET season_fourth = season_fourth + 1 WHERE user_id = ?", (p4[0],))

                target_chat_id = await get_live_chat_id()
                if target_chat_id:
                    msg = (
                        f"🏆 <b>پایان رسمی رقابت‌های این سیزن!</b> 🔥\n────────────────────\n"
                        f"🥇 قهرمان سیزن: <b>{html.escape(p1[1])}</b>\n"
                    )
                    if p2: msg += f"🥈 نایب قهرمان: <b>{html.escape(p2[1])}</b>\n"
                    if p3: msg += f"🥉 مقام سوم: <b>{html.escape(p3[1])}</b>\n"
                    msg += "\n🔄 <b>امتیازات سیزن روی ۱۰۰ ریست شدند. کارت‌ها و لول محفوظ است!</b>"
                    try: await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")
                    except Exception: pass

                await db.execute("UPDATE users SET points = 100, duel_wins = 0, penalty_wins = 0, guess_wins = 0")
                await db.execute("UPDATE bot_settings SET value = ? WHERE key = 'last_settled_month'", (cur_month_str,))
                await db.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT points, profile_level, profile_xp FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            pts = row[0] if row else 100
            lvl = row[1] if row and row[1] else 1
            xp = row[2] if row and row[2] else 0

    icon, tier = get_user_tier(pts)
    safe_name = html.escape(user.first_name)
    _, _, _, pct = calculate_level(xp)
    bar = render_xp_bar(pct, width=10)

    text = (
        f"⚽ <b>{safe_name}</b>\n\n"
        f"🏆 <b>{tier}</b>\n"
        f"<b>LVL {lvl}</b>\n"
        f"{bar} <code>{pct}%</code>\n\n"
        f"💰 <b>{pts:,} PTS</b>\n"
        f"────────────────────\n"
        f"به هاب هوشمند فوتبال خوش آمدید!\n"
        f"یکی از بخش‌های زیر را انتخاب کنید:"
    )
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb.get_main_menu())
    else: await update.message.reply_text(text, reply_markup=kb.get_main_menu(), parse_mode="HTML")

async def show_leaderboard_text(requesting_user_id: int = None) -> str:
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT user_id, first_name, points, duel_wins FROM users WHERE user_id != ? ORDER BY points DESC, duel_wins DESC", (ESCOBAR_AI_ID,)) as cur:
            all_users = await cur.fetchall()

    text = "🏆 <b>جدول رده‌بندی سیزن</b> 🔥\n────────────────────\n\n"
    if not all_users: return text + "هنوز کاربری ثبت نشده است.\n────────────────────"

    top_list, remaining_list = all_users[:15], all_users[15:25]
    for idx, u in enumerate(top_list, 1):
        name, pts, wins = u[1], max(0, u[2]), u[3]
        _, tier = get_user_tier(pts)
        display_name = format_bidi_name(name)
        rank_prefix = "🥇 👑" if idx == 1 else ("🥈 👑" if idx == 2 else ("🥉 👑" if idx == 3 else f"<code>{idx:02d}.</code>"))
        text += f"{rank_prefix} <b>{display_name}</b> ({tier})\n    └ 💰 <code>{pts} PTS</code>  ▫️  ⚔️ <code>{wins}</code>\n\n"

    if remaining_list:
        text += "────────────────────\n\n"
        for idx, u in enumerate(remaining_list, 16):
            name, pts, wins = u[1], max(0, u[2]), u[3]
            _, tier = get_user_tier(pts)
            display_name = format_bidi_name(name)
            text += f"<code>{idx:02d}.</code> <b>{display_name}</b> ({tier})\n    └ 💰 <code>{pts} PTS</code>  ▫️  ⚔️ <code>{wins}</code>\n\n"

    if requesting_user_id:
        for idx, u in enumerate(all_users, 1):
            if u[0] == requesting_user_id and idx > 25:
                pts = max(0, u[2])
                _, tier = get_user_tier(pts)
                text += f"────────────────────\n👤 <b>رتبه شخصی شما:</b> <code>#{idx}</code> ({tier} - <code>{pts} PTS</code>)\n"
                break

    text += "────────────────────"
    return text

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    text = await show_leaderboard_text(user_id)
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
    else: await update.message.reply_text(text, parse_mode="HTML")

async def user_profile_handler(query, target_user=None):
    user = target_user or query.from_user
    user_id = user.id
    await ensure_user(user)

    team_info = await get_user_team_info(user_id)
    team_ovr = team_info["eff_ovr"] if team_info else 0
    team_chem = team_info["chem"] if team_info else 0

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("""
            SELECT points, profile_xp, profile_level, profile_correct, profile_answered,
                   duel_wins, penalty_wins, guess_wins,
                   season_gold, season_silver, season_bronze, season_fourth
            FROM users WHERE user_id = ?
        """, (user_id,)) as cur:
            row = await cur.fetchone()

        async with db.execute("SELECT COUNT(*) FROM user_cards WHERE user_id = ? AND is_in_lineup = 1", (user_id,)) as cur:
            lineup_count = (await cur.fetchone())[0]

    if not row: return
    pts, xp, level, correct, answered, d_wins, p_wins, g_wins, gold, silver, bronze, fourth = row
    pts = max(0, pts or 0)
    level, cur_xp, needed_xp, percent = calculate_level(xp or 0)
    accuracy = round((correct / answered) * 100) if answered else 0
    _, tier = get_user_tier(pts)
    safe_name = html.escape(user.first_name)
    bar = render_xp_bar(percent, width=10)

    medals_lines = []
    if gold: medals_lines.append(f"🥇 {gold} بار رتبه اول")
    if silver: medals_lines.append(f"🥈 {silver} بار رتبه دوم")
    if bronze: medals_lines.append(f"🥉 {bronze} بار رتبه سوم")
    if fourth: medals_lines.append(f"🎖 {fourth} بار رتبه چهارم")

    medals_text = "\n\n🏆 <b>افتخارات سیزن:</b>\n" + "  •  ".join(medals_lines) if medals_lines else ""

    text = (
        f"⚽ <b>{safe_name}</b>\n\n"
        f"🏆 <b>{tier}</b>\n"
        f"<b>LVL {level}</b>\n"
        f"{bar} <code>{percent}%</code>\n\n"
        f"💰 <b>{pts:,} PTS</b>\n"
        f"🛡 <b>قدرت نهایی تیم:</b> <code>{team_ovr} OVR</code> ({lineup_count}/5)\n"
        f"⚗️ <b>کمیستری تیم:</b> <code>{team_chem}%</code>\n"
        f"⚔️ <b>{d_wins or 0}</b> Wins\n"
        f"🧠 <b>{accuracy}%</b> Accuracy\n"
        f"🥅 <b>{p_wins or 0}</b> Penalty Wins\n"
        f"🕵️ <b>{g_wins or 0}</b> Guess Wins"
        f"{medals_text}"
    )

    if hasattr(query, "message") and query.message:
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())
    else: await query.reply_text(text, parse_mode="HTML")

async def daily_reward_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT last_daily_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                await update.effective_message.reply_text(f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، پاداش امروز را دریافت کرده‌اید!", parse_mode="HTML")
                return

        reward = 35
        await db.execute("UPDATE users SET points = points + ?, last_daily_date = ? WHERE user_id = ?", (reward, today_str, user.id))
        await db.commit()

    await profile_add_xp(user.id, 25)
    await update.effective_message.reply_text(f"🎁 <b>پاداش ورود روزانه واریز شد!</b>\n💰 <b>+{reward} امتیاز</b> دریافت کردید.", parse_mode="HTML")

async def daily_pack_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT last_free_pack_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                msg = f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، شما پک روزانه امروز خود را باز کرده‌اید! فردا دوباره سر بزنید."
                if update.callback_query:
                    await update.callback_query.answer("⏳ پک روزانه امروز را قبلاً دریافت کرده‌اید!", show_alert=True)
                else:
                    await update.effective_message.reply_text(msg, parse_mode="HTML")
                return

        daily_weights = {"COMMON": 82.0, "RARE": 16.0, "ELITE": 1.8, "ICON": 0.2}
        pulled_cards = [generate_random_card_by_rarity(daily_weights) for _ in range(3)]

        await db.execute("UPDATE users SET last_free_pack_date = ? WHERE user_id = ?", (today_str, user.id))
        for c in pulled_cards:
            await db.execute(
                "INSERT INTO user_cards (user_id, player_name, rating, position, rarity, acquired_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user.id, c["name"], c["ovr"], c["pos"], c["rarity"], today_str)
            )
        await db.commit()

    await profile_add_xp(user.id, 30)

    cards_lines = []
    for idx, c in enumerate(pulled_cards, 1):
        rarity_label = RARITY_COLORS.get(c["rarity"], c["rarity"])
        cards_lines.append(
            f"{idx}️⃣ <b>{c['name']}</b> ({c['pos']}) ➔ <b>{c['ovr']} OVR</b>\n"
            f"    └ {c.get('nation', '')} | {c.get('club', '')} | {rarity_label}"
        )

    pack_text = (
        f"🎁📦 <b>پک روزانه رایگان {html.escape(user.first_name)} باز شد!</b>\n"
        "────────────────────\n"
        + "\n\n".join(cards_lines) +
        "\n────────────────────\n"
        "✨ هر ۳ بازیکن به کلکسیون کارت‌های شما اضافه شدند! (+30 XP)"
    )

    if update.callback_query:
        await update.callback_query.message.reply_text(pack_text, parse_mode="HTML")
    else:
        await update.effective_message.reply_text(pack_text, parse_mode="HTML")

async def daily_shoot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT last_shoot_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                await update.effective_message.reply_text(f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، شوت امروز را زده‌اید!", parse_mode="HTML")
                return
        await db.execute("UPDATE users SET last_shoot_date = ? WHERE user_id = ?", (today_str, user.id))
        await db.commit()

    msg = await update.effective_message.reply_dice(emoji="⚽")
    dice_val = msg.dice.value
    await asyncio.sleep(2.5)

    if dice_val in [3, 4, 5]:
        reward = 30
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, user.id))
            await db.commit()
        await profile_add_xp(user.id, 25)
        await update.effective_message.reply_text(f"⚽️🔥 <b>گـُـل شد! ضربه مهارنشدنی!</b>\n💰 پاداش: <b>+{reward} امتیاز</b> دریافت کردید.", parse_mode="HTML")
    else:
        await update.effective_message.reply_text("🧤❌ <b>توپ گل نشد!</b> امشب بعد از ساعت ۱۲ دوباره شانس داری.", parse_mode="HTML")

async def spin_wheel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT last_wheel_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                await update.effective_message.reply_text(f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، امروز گردونه را چرخانده‌اید!", parse_mode="HTML")
                return
        await db.execute("UPDATE users SET last_wheel_date = ? WHERE user_id = ?", (today_str, user.id))
        await db.commit()

    prizes = [0, 30, 60, 120, 250, 380, 500]
    weights = [15, 30, 25, 16, 10, 3, 1]
    win = random.choices(prizes, weights=weights)[0]

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        if win > 0:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (win, user.id))
            await db.commit()

    if win == 500:
        msg = f"🎰🔥 <b>جـک‌پـات تـاریـخـی گـردونـه!</b>\n🎉 تبریک ویژه به <b>{html.escape(user.first_name)}</b>! برنده خوش‌شانس <b>+۵۰۰ امتیاز</b> شدید!"
    elif win > 0:
        await profile_add_xp(user.id, win // 2)
        msg = f"🎡 <b>گردونه شانس متوقف شد!</b>\n🎉 تبریک، برنده <b>+{win} امتیاز</b> شدید!"
    else:
        msg = "🎡 <b>گردونه شانس متوقف شد!</b>\n❌ این بار پوچ شد! امشب بعد از ساعت ۱۲ دوباره شانس‌ات را امتحان کن."

    if update.callback_query: await update.callback_query.message.reply_text(msg, parse_mode="HTML")
    else: await update.effective_message.reply_text(msg, parse_mode="HTML")

async def guess_timeout_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    game = ACTIVE_GUESS_GAMES.get(chat_id)
    if game and game.get("is_active"):
        game["is_active"] = False
        main_name = game["names"][0]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⌛️ <b>مهلت ۳۰ ثانیه‌ای حدس بازیکن تمام شد!</b>\n👤 ستاره مورد نظر پرونده: <b>{main_name}</b> بود.",
            parse_mode="HTML"
        )

async def start_guess_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    chat_id, user = update.effective_chat.id, update.effective_user
    await ensure_user(user)

    g_count = await get_guess_count_db(user.id)
    if g_count >= 3:
        await update.effective_message.reply_text(f"⛔️ <b>{html.escape(user.first_name)}</b> عزیز، سقف ۳ حدس امروز را مصرف کرده‌اید!", parse_mode="HTML")
        return

    game = ACTIVE_GUESS_GAMES.get(chat_id)
    if game and game.get("is_active"):
        await update.effective_message.reply_text("⚠️ یک پرونده هم‌اکنون در این گروه در جریان است!", parse_mode="HTML")
        return

    await increment_guess_count_db(user.id)
    current_attempt = g_count + 1
    p = get_next_guess_player()
    career_str = "\n".join([f"  {idx}. {club}" for idx, club in enumerate(p['career'], 1)])

    ACTIVE_GUESS_GAMES[chat_id] = {
        "names": [n.lower().strip() for n in p["names"]],
        "reward": 20, "chat_id": chat_id,
        "challenger_id": user.id, "challenger_name": user.first_name, "is_active": True
    }

    text = (
        "🕵️‍♂️ <b>پرونده اطلاعاتی: ستاره فوتبال را شناسایی کنید!</b>\n────────────────────\n"
        f"🎯 بازیکن چالش: <b>{html.escape(user.first_name)}</b> ({current_attempt}/3)\n"
        f"⏱ مهلت پاسخ: <b>۳۰ ثانیه</b> ⏳\n"
        f"🌍 <b>ملیت:</b> {p['nation']}\n📌 <b>پست تخصصی:</b> {p['pos']}\n\n"
        f"🏟 <b>مسیر باشگاهی:</b>\n{career_str}\n\n⭐️ <b>سرنخ:</b>\n{p['clue']}\n────────────────────\n"
        "💰 پاداش پاسخ صحیح: <b>+20 امتیاز</b> | <b>+80 XP</b>\n👇 نام بازیکن را در چت ارسال کنید:"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")
    schedule_timer(context, guess_timeout_job, 30, data={"chat_id": chat_id, "user_id": user.id}, name=f"guess_timer_{chat_id}")

# --- DOUBLE OR NOTHING ---

async def double_timeout_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    g_id = job_data["g_id"]
    game = ACTIVE_DOUBLE_GAMES.get(g_id)
    if game and game.get("is_active"):
        game["is_active"] = False
        stake = game["stake"]
        await safe_edit_message(
            context.bot,
            f"⌛️ <b>زمان ۱۰ ثانیه‌ای تمام شد!</b> 💀\nبه دلیل عدم پاسخ در مهلت مقرر، شرط شما سوخت و مبلغ <b>{stake:,} PTS</b> از حسابتان کسر گردید.",
            reply_markup=None,
            chat_id=game["chat_id"],
            message_id=game["msg_id"]
        )
        ACTIVE_DOUBLE_GAMES.pop(g_id, None)

async def double_or_nothing_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    user = update.effective_user
    await ensure_user(user)

    args = context.args
    if not args:
        text_match = re.search(r"\d+", update.effective_message.text or "")
        amount_str = text_match.group(0) if text_match else None
    else:
        amount_str = args[0]

    if not amount_str or not amount_str.isdigit():
        await update.effective_message.reply_text("⚠️ <b>نحوه استفاده:</b> <code>/double 100</code> یا نوشتن: <code>دوبل 100</code>", parse_mode="HTML")
        return

    stake = int(amount_str)
    if stake < 10:
        await update.effective_message.reply_text("⚠️ حداقل مبلغ شرط چالش دوبرابر ۱۰ امتیاز است.")
        return

    today_str = get_iran_now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT points, last_double_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            pts = row[0] if row else 0
            last_date = row[1] if row and len(row) > 1 else ""

        if last_date == today_str:
            await update.effective_message.reply_text(
                f"⛔️ <b>{html.escape(user.first_name)}</b> عزیز، شما امروز چالش مرگبار دوبرابر را بازی کرده‌اید!\nاین چالش به دلیل ریسک بالا فقط ۱ بار در روز فعال است.",
                parse_mode="HTML"
            )
            return

        if pts < stake:
            await update.effective_message.reply_text(f"⛔️ موجودی ناکافی! شما <b>{pts:,} PTS</b> دارید اما شرط <b>{stake:,} PTS</b> بسته‌اید.", parse_mode="HTML")
            return

        await db.execute("UPDATE users SET points = points - ?, last_double_date = ? WHERE user_id = ?", (stake, today_str, user.id))
        await db.commit()

    q_data = random.choice(HARDCORE_QUIZ_POOL)
    opts = list(q_data["options"])
    random.shuffle(opts)

    g_id = f"dbl_{random.randint(10000, 99999)}"
    ACTIVE_DOUBLE_GAMES[g_id] = {
        "user_id": user.id,
        "stake": stake,
        "correct": q_data["correct"],
        "options": opts,
        "is_active": True,
        "chat_id": update.effective_chat.id,
        "msg_id": None
    }

    buttons = [[InlineKeyboardButton(f"🔘 {opt}", callback_data=f"ans_dbl_{g_id}_{idx}")] for idx, opt in enumerate(opts)]

    text = (
        "🔥 <b>چالش مرگبار دوبرابر یا پوچ (Double or Nothing)!</b> 💀\n"
        "────────────────────\n"
        f"👤 بازیکن: <b>{html.escape(user.first_name)}</b>\n"
        f"💰 مبلغ شرط: <b>{stake:,} PTS</b> (برد: +{stake:,} | باخت: -{stake:,})\n"
        "⏱ <b>مهلت پاسخ: فقط ۱۰ ثانیه!</b> ⏳\n"
        "────────────────────\n"
        f"❓ <b>{q_data['question']}</b>"
    )
    sent = await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    ACTIVE_DOUBLE_GAMES[g_id]["msg_id"] = sent.message_id

    schedule_timer(context, double_timeout_job, 10, data={"g_id": g_id}, name=f"timer_dbl_{g_id}")

# --- SUDDEN DEATH PENALTY ---

async def trigger_penalty_shootout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("🥅 روی پیام حریف ریپلای کنید و بنویسید: <code>پنالتی</code>", parse_mode="HTML")
        return

    challenger, opponent = update.effective_user, update.message.reply_to_message.from_user
    if opponent.is_bot or challenger.id == opponent.id: return

    c_count = await get_penalty_count_db(challenger.id)
    o_count = await get_penalty_count_db(opponent.id)
    if c_count >= 3 or o_count >= 3:
        await update.message.reply_text("⛔️ یکی از طرفین سقف ۳ پنالتی امروز خود را مصرف کرده است!", parse_mode="HTML")
        return

    await ensure_user(challenger)
    await ensure_user(opponent)

    stake = 25
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (challenger.id, opponent.id)) as cur:
            balances = {row[0]: row[1] for row in await cur.fetchall()}

    if balances.get(challenger.id, 0) < stake or balances.get(opponent.id, 0) < stake:
        await update.message.reply_text(f"⛔️ هر دو بازیکن باید حداقل <b>{stake} PTS</b> داشته باشند.", parse_mode="HTML")
        return

    p_id = f"pen_{random.randint(10000, 99999)}"
    ACTIVE_SHOOTOUTS[p_id] = {
        "p1": {"id": challenger.id, "name": challenger.first_name, "shot": None},
        "p2": {"id": opponent.id, "name": opponent.first_name, "shot": None},
        "current_turn": challenger.id, "round": 1, "stake": stake,
        "accepted": False,
        "chat_id": update.effective_chat.id, "message_id": None
    }

    p_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧤 قبول پنالتی", callback_data=f"acp_{p_id}"),
         InlineKeyboardButton("❌ لغو", callback_data=f"rjp_{p_id}")]
    ])
    text = (
        f"🥅 <b>دوئل پنالتی مرگ ناگهانی (با تاس فوتبالی)!</b> ⚽️\n"
        f"{html.escape(challenger.first_name)} 🆚 {html.escape(opponent.first_name)}\n"
        f"💰 شرط: <b>{stake} PTS</b>\nآیا می‌پذیری؟"
    )
    sent_msg = await update.message.reply_text(text, reply_markup=p_kb, parse_mode="HTML")
    ACTIVE_SHOOTOUTS[p_id]["message_id"] = sent_msg.message_id

# --- WEEKLY JACKPOT ---

async def get_or_create_jackpot_round():
    iran_now = get_iran_now()
    week_id = f"JKW{iran_now.strftime('%U%Y')}"

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT round_id, title, matches_json, pool_amount, is_active FROM jackpot_rounds WHERE round_id = ?", (week_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "round_id": row[0],
                    "title": row[1] or "جک‌پات طلایی هفته",
                    "matches": json.loads(row[2]),
                    "pool_amount": row[3] or 500,
                    "is_open": bool(row[4])
                }

    candidates = []
    for day in range(7):
        d_str = (iran_now + timedelta(days=day)).strftime("%Y%m%d")
        for l_code in ["eng.1", "esp.1", "ita.1", "uefa.champions", "irn.1"]:
            try:
                m_list = await provider.get_matches(d_str, league_code=l_code)
                for m in m_list:
                    if m.get("status") == "UPCOMING":
                        if not any(c["id"] == str(m["id"]) for c in candidates):
                            candidates.append({
                                "id": str(m["id"]),
                                "home": m["home_team"],
                                "away": m["away_team"],
                                "date": m.get("date"),
                                "league_code": l_code
                            })
                    if len(candidates) >= 5: break
            except Exception: continue
            if len(candidates) >= 5: break
        if len(candidates) >= 5: break

    if len(candidates) < 5:
        tmrw = iran_now + timedelta(days=1)
        tmrw_iso = tmrw.replace(hour=21, minute=0).astimezone(timezone.utc).isoformat()
        day_after_iso = (iran_now + timedelta(days=2)).replace(hour=22, minute=30).astimezone(timezone.utc).isoformat()
        sample_pool = [
            {"id": "fut_1", "home": "رئال مادرید", "away": "بارسلونا", "date": tmrw_iso},
            {"id": "fut_2", "home": "منچسترسیتی", "away": "لیورپول", "date": tmrw_iso},
            {"id": "fut_3", "home": "تیم ملی ایران", "away": "کره جنوبی", "date": tmrw_iso},
            {"id": "fut_4", "home": "فرانسه", "away": "ایتالیا", "date": day_after_iso},
            {"id": "fut_5", "home": "بایرن مونیخ", "away": "دورتموند", "date": day_after_iso}
        ]
        needed = 5 - len(candidates)
        candidates.extend(sample_pool[:needed])

    selected_5 = candidates[:5]
    now_str = iran_now.strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("""
            INSERT OR REPLACE INTO jackpot_rounds (round_id, title, matches_json, pool_amount, is_active, is_settled, created_at)
            VALUES (?, ?, ?, 500, 1, 0, ?)
        """, (week_id, "جک‌پات طلایی هفته", json.dumps(selected_5, ensure_ascii=False), now_str))
        await db.commit()

    return {"round_id": week_id, "title": "جک‌پات طلایی هفته", "matches": selected_5, "pool_amount": 500, "is_open": True}

async def settle_jackpot_task(context: ContextTypes.DEFAULT_TYPE):
    try:
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT round_id, matches_json, pool_amount FROM jackpot_rounds WHERE is_settled = 0 AND is_active = 1") as cur:
                rounds = await cur.fetchall()

        for r_id, m_json, pool in rounds:
            matches = json.loads(m_json)
            results = {}
            all_finished = True

            for idx, m in enumerate(matches):
                m_id = str(m["id"])
                m_data = MATCH_CACHE.get(m_id)
                if not m_data and m.get("date") and m.get("league_code"):
                    try:
                        dt = datetime.fromisoformat(m["date"].replace("Z", "+00:00"))
                        fetched = await provider.get_matches(dt.strftime("%Y%m%d"), league_code=m["league_code"])
                        for fm in fetched:
                            MATCH_CACHE[str(fm["id"])] = fm
                        m_data = MATCH_CACHE.get(m_id)
                    except Exception:
                        pass

                if not m_data or m_data.get("status") not in ["FINISHED", "FT", "POST"]:
                    all_finished = False
                    break
                h = int(m_data.get("home_score", 0))
                a = int(m_data.get("away_score", 0))
                results[str(idx)] = "HOME" if h > a else ("AWAY" if a > h else "DRAW")

            if all_finished and len(results) == 5:
                async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                    async with db.execute("SELECT user_id, predictions_json, user_name FROM jackpot_combos WHERE round_id = ?", (r_id,)) as cur:
                        entries = await cur.fetchall()

                    winners = []
                    for uid, p_json, name in entries:
                        u_preds = json.loads(p_json)
                        if all(u_preds.get(k) == results.get(k) for k in results):
                            winners.append((uid, name))

                    if winners:
                        prize = pool // len(winners)
                        for w_id, _ in winners:
                            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (prize, w_id))
                        msg = f"🎰 <b>جک‌پات هفته تسویه شد!</b>\n🏆 برندگان ۵ از ۵:\n" + "\n".join([f"👤 {html.escape(w[1])} (+{prize} PTS)" for w in winners])
                        target_chat_id = await get_live_chat_id()
                        if target_chat_id: await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")

                    await db.execute("UPDATE jackpot_rounds SET is_settled = 1, is_active = 0 WHERE round_id = ?", (r_id,))
                    await db.commit()
    except Exception as e:
        logger.error(f"Error in settle_jackpot_task: {e}")

async def jackpot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    round_data = await get_or_create_jackpot_round()
    round_id, matches, pool, is_open = round_data["round_id"], round_data["matches"], round_data.get("pool_amount", 500), round_data.get("is_open", True)

    user_combo = None
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT predictions_json FROM jackpot_combos WHERE user_id = ? AND round_id = ?", (user.id, round_id)) as cur:
            row = await cur.fetchone()
            if row: user_combo = json.loads(row[0])

    matches_text = ""
    for idx, m in enumerate(matches, 1):
        user_pick = ""
        if user_combo:
            p_val = user_combo.get(str(idx - 1), "—")
            p_label = "برد ۱" if p_val == "HOME" else ("تساوی X" if p_val == "DRAW" else ("برد ۲" if p_val == "AWAY" else "—"))
            user_pick = f"  ➔  <b>{p_label}</b>"
        time_display = format_iran_time(m.get("date"))
        matches_text += f"{idx}. <b>{m['home']}</b> 🆚 <b>{m['away']}</b> ({time_display}){user_pick}\n"

    buttons = []
    if user_combo:
        status_footer = "\n✅ <b>فرم جک‌پات شما برای این راند با موفقیت ثبت شده است!</b>"
        buttons.append([InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")])
    elif not is_open:
        status_footer = "\n⚠️ <b>مسابقات این راند آغاز شده و مهلت ثبت به پایان رسیده است.</b>"
        buttons.append([InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")])
    else:
        status_footer = "\n👇 برای شروع ثبت پیش‌بینی روی دکمه زیر کلیک کنید:"
        buttons.append([InlineKeyboardButton("📝 ثبت پیش‌بینی (۵ بازی)", callback_data=f"jk_start_{round_id}")])
        buttons.append([InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")])

    text = f"🎰 <b>{round_data.get('title')}</b>\n────────────────────\n💰 استخر جایزه: <b>{pool:,} PTS</b>\n────────────────────\n📋 <b>مسابقات:</b>\n\n{matches_text}{status_footer}"
    reply_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=reply_markup)
    else: await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

# --- PREDICTIONS HUB ---

async def predictions_hub_handler(query):
    iran_now = get_iran_now()
    dates = [iran_now.strftime("%Y%m%d"), (iran_now + timedelta(days=1)).strftime("%Y%m%d")]
    candidate_matches = []
    for d in dates:
        for l_code in ACTIVE_MONITOR_LEAGUES:
            try:
                m_list = await provider.get_matches(d, league_code=l_code)
                for m in m_list:
                    MATCH_CACHE[str(m["id"])] = m
                    if is_match_still_open_for_prediction(m):
                        candidate_matches.append(m)
            except Exception: pass

    seen, upcoming_list = set(), []
    for m in candidate_matches:
        if str(m["id"]) not in seen:
            seen.add(str(m["id"]))
            upcoming_list.append(m)

    if not upcoming_list:
        await safe_edit_message(query, "⏳ مسابقه شروع‌نشده‌ای در دسترس نیست.", reply_markup=kb.get_back_button())
        return

    text = "🎯 <b>تالار پیش‌بینی مسابقات فوتبال</b>\n────────────────────\nمسابقه مورد نظر خود را جهت ثبت پیش‌بینی انتخاب کنید:\n💰 پاداش ثبت: <b>+10 امتیاز</b> | جایزه حدس درست: <b>+40 امتیاز</b>\n────────────────────"
    await safe_edit_message(query, text, reply_markup=kb.get_upcoming_matches_keyboard(upcoming_list))
# --- FC CARDS, LINEUP, TACTICAL AI & EVOLUTION ENGINE ---

def calculate_team_chemistry(cards):
    if len(cards) < 5: return 0
    chem = 35
    icons = sum(1 for c in cards if c.get("rarity") == "ICON")
    chem += icons * 15

    nations = [c.get("nation") for c in cards if c.get("nation") and c.get("rarity") != "ICON"]
    for _, count in Counter(nations).items():
        if count >= 2: chem += (count - 1) * 18

    clubs = [c.get("club") for c in cards if c.get("club") and c.get("rarity") != "ICON"]
    for _, count in Counter(clubs).items():
        if count >= 2: chem += (count - 1) * 22

    return min(100, max(0, chem))

def generate_random_card_by_rarity(rarity_weights=None):
    if not rarity_weights:
        rarity_weights = {"COMMON": 60, "RARE": 32, "ELITE": 7, "ICON": 1}
    rarities = list(rarity_weights.keys())
    weights = list(rarity_weights.values())
    chosen_rarity = random.choices(rarities, weights=weights)[0]
    filtered = [c for c in FC_CATALOG if c["rarity"] == chosen_rarity]
    return random.choice(filtered)

TACTIC_NAMES = {
    "TIKI_TAKA": "🪄 تیکی‌تاکا و مالکیت توپ",
    "GEGENPRESS": "⚡️ گگن‌پرسینگ (پرس وحشتناک)",
    "FAST_COUNTER": "🚀 ضدحمله سرعتی و برق‌آسا",
    "PARK_BUS": "🧱 اتوبوسی و دفاع متمرکز",
    "HIGH_LINE": "🔴 دفاع بالا (تله آفساید)",
    "BALANCED": "🟡 دفاع متعادل و متوازن",
    "DEEP": "🔵 دفاع عمیق در محوطه",
    "SHORT": "🎯 پاس‌های کوتاه و تک‌ضرب",
    "LONG": "✈️ پاس‌های بلند و قطری",
    "ALL_OUT": "🔥 انتحاری و هجوم همه‌جانبه"
}

async def get_user_tactics(user_id: int) -> dict:
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT style, depth, buildup, risk FROM user_tactics WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return {"style": row[0], "depth": row[1], "buildup": row[2], "risk": row[3]}
    return {"style": "TIKI_TAKA", "depth": "BALANCED", "buildup": "SHORT", "risk": "BALANCED"}

def calculate_tactical_clash(tac1: dict, tac2: dict):
    b1, b2 = 0.0, 0.0
    notes = []

    s1, s2 = tac1["style"], tac2["style"]
    if s1 == "GEGENPRESS" and s2 == "TIKI_TAKA":
        b1 += 0.08
        notes.append("⚡️ پرس سنگین تیم ۱ خطوط بازیسازی تیکی‌تاکای تیم ۲ را مختل کرده است!")
    elif s2 == "GEGENPRESS" and s1 == "TIKI_TAKA":
        b2 += 0.08
        notes.append("⚡️ پرس شدید تیم ۲ کار را برای تیکی‌تاکای تیم ۱ دشوار کرده است!")

    if s1 == "FAST_COUNTER" and s2 == "GEGENPRESS":
        b1 += 0.09
        notes.append("🚀 تیم ۱ از فضای پشت خط پرس حریف با ضدحملات سریع استفاده می‌کند!")
    elif s2 == "FAST_COUNTER" and s1 == "GEGENPRESS":
        b2 += 0.09
        notes.append("🚀 تیم ۲ از خلأ ناشی از پرس حریف برای ضدحملات برق‌آسا سود می‌برد!")

    if s1 == "PARK_BUS" and s2 == "FAST_COUNTER":
        b1 += 0.07
        notes.append("🧱 دفاع متراکم و اتوبوسی تیم ۱ اجازه فرار در ضدحملات را به حریف نمی‌دهد.")
    elif s2 == "PARK_BUS" and s1 == "FAST_COUNTER":
        b2 += 0.07
        notes.append("🧱 اتوبوس تیم ۲ جلوی ضدحملات مستقیم حریف دیوار کشیده است.")

    if s1 == "TIKI_TAKA" and s2 == "PARK_BUS":
        b1 += 0.07
        notes.append("🪄 چرخش مداوم توپ و پاس‌های ریز تیم ۱ اتوبوس حریف را خسته و باز می‌کند.")
    elif s2 == "TIKI_TAKA" and s1 == "PARK_BUS":
        b2 += 0.07
        notes.append("🪄 پاس‌کاری تیکی‌تاکای تیم ۲ دفاع فشرده تیم ۱ را دور می‌زند.")

    if tac1["depth"] == "HIGH_LINE" and tac2["buildup"] == "LONG":
        b2 += 0.08
        notes.append("⚠️ خط دفاعی بسیار بالای تیم ۱ روی پاس‌های بلند هوایی حریف کاملاً جا ماند!")
    if tac2["depth"] == "HIGH_LINE" and tac1["buildup"] == "LONG":
        b1 += 0.08
        notes.append("⚠️ تیم ۱ با ارسال پاس‌های قطری از بالا بودن خط دفاعی حریف بهره می‌برد!")

    if tac1["depth"] == "DEEP" and tac2["buildup"] == "SHORT":
        b2 += 0.05
        notes.append("🎯 تیم ۲ به راحتی پشت محوطه تیم ۱ خیمه زده و شوت‌زنی می‌کند.")
    if tac2["depth"] == "DEEP" and tac1["buildup"] == "SHORT":
        b1 += 0.05
        notes.append("🎯 تیم ۱ با پاس‌های تک‌ضرب اطراف محوطه جریمه حریف فرصت‌سازی می‌کند.")

    if tac1["risk"] == "ALL_OUT":
        b1 += 0.06
        b2 += 0.04
    if tac2["risk"] == "ALL_OUT":
        b2 += 0.06
        b1 += 0.04

    return b1, b2, notes

async def tactics_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)[span_5](start_span)[span_5](end_span)
    tac = await get_user_tactics(user.id)

    text = (
        f"📋 <b>اتاق آنالیز و تاکتیک هوشمند تیم: {html.escape(user.first_name)}</b>\n"
        "────────────────────\n"
        f"▫️ سبک بازی اصلی: <b>{TACTIC_NAMES.get(tac['style'], tac['style'])}</b>\n"
        f"▫️ عمق خط دفاعی: <b>{TACTIC_NAMES.get(tac['depth'], tac['depth'])}</b>\n"
        f"▫️ نحوه بازیسازی: <b>{TACTIC_NAMES.get(tac['buildup'], tac['buildup'])}</b>\n"
        f"▫️ ریسک هجومی: <b>{TACTIC_NAMES.get(tac['risk'], tac['risk'])}</b>\n"
        "────────────────────\n"
        "🧠 <i>هوش مصنوعی مسابقات در هر بازی تاکتیک شما را با حریف تطبیق داده و برتری‌های میدانی ایجاد می‌کند!</i>\n\n"
        "👇 برای تنظیم بخش‌ها انتخاب کنید:"
    )

    kb_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ تغییر سبک بازی (Style)", callback_data="set_tac_step1")],
        [InlineKeyboardButton("2️⃣ عمق خط دفاعی (Depth)", callback_data="set_tac_step2")],
        [InlineKeyboardButton("3️⃣ نحوه بازیسازی (Build-Up)", callback_data="set_tac_step3")],
        [InlineKeyboardButton("4️⃣ ریسک تیمی (Risk)", callback_data="set_tac_step4")],
        [InlineKeyboardButton("🛡 مشاهده ترکیب تیم", callback_data="view_lineup"),[span_6](start_span)[span_6](end_span)
         InlineKeyboardButton("‹ بازگشت", callback_data="home")][span_7](start_span)[span_7](end_span)
    ])

    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)[span_8](start_span)[span_8](end_span)
    else:
        await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

async def evolution_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)[span_9](start_span)[span_9](end_span)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_10](start_span)[span_10](end_span)
        async with db.execute("SELECT points FROM users WHERE user_id = ?", (user.id,)) as cur:[span_11](start_span)[span_11](end_span)
            pts = (await cur.fetchone())[0][span_12](start_span)[span_12](end_span)

    text = (
        f"⚡️🧪 <b>مرکز اوولوشن تخصصی FC (Evolution Hub)</b>\n"
        "────────────────────\n"
        f"💰 موجودی شما: <b>{pts:,} PTS</b>\n"
        "────────────────────\n"
        "یک مسیر ارتقا را برای تیم خود انتخاب کنید:\n\n"
        "1️⃣ <b>جهش آکادمی (+5 OVR):</b> مخصوص کارت‌های معمولی\n"
        "2️⃣ <b>کیمیاگری کهکشانی (+3 OVR):</b> مخصوص کارت‌های گلد ریر\n"
        "3️⃣ <b>تولد اسطوره (+3 OVR):</b> تبدیل الیت به آیکان\n"
        "4️⃣ <b>تایتان نامیرا (+2 OVR):</b> تقویت آیکان‌ها تا سقف ۹۶\n\n"
        "👑 <b>پروژه‌های ماورایی G.O.A.T (فوق‌العاده گران):</b>\n"
        "▫️ <b>مسی ۹۹ OVR:</b> نیازمند ۱۸ هزار امتیاز + ۲ آیکان + ۳ الیت\n"
        "▫️ <b>رونالدو ۹۹ OVR:</b> نیازمند ۱۸ هزار امتیاز + ۲ آیکان + ۳ الیت\n"
    )

    buttons = [
        [InlineKeyboardButton("1️⃣ جهش آکادمی (1,200 PTS)", callback_data="evo_cat_academy")],
        [InlineKeyboardButton("2️⃣ کیمیاگری کهکشانی (2,500 PTS)", callback_data="evo_cat_rare_boost")],
        [InlineKeyboardButton("3️⃣ تولد اسطوره (5,000 PTS)", callback_data="evo_cat_elite_push")],
        [InlineKeyboardButton("4️⃣ تایتان نامیرا (8,500 PTS)", callback_data="evo_cat_icon_titan")],
        [
            InlineKeyboardButton("🐐 مسی ۹۹ OVR", callback_data="evo_cat_messi_99"),
            InlineKeyboardButton("🐐 رونالدو ۹۹ OVR", callback_data="evo_cat_cr7_99")
        ],
        [InlineKeyboardButton("🛡 مشاهده ترکیب تیم", callback_data="view_lineup"),[span_13](start_span)[span_13](end_span)
         InlineKeyboardButton("‹ منوی اصلی", callback_data="home")][span_14](start_span)[span_14](end_span)
    ]

    kb_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)[span_15](start_span)[span_15](end_span)
    else:
        await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

async def market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)[span_16](start_span)[span_16](end_span)
    today_str = get_iran_now().strftime("%Y-%m-%d")[span_17](start_span)[span_17](end_span)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_18](start_span)[span_18](end_span)
        async with db.execute("SELECT offers_json FROM daily_market WHERE user_id = ? AND date_str = ?", (user.id, today_str)) as cur:[span_19](start_span)[span_19](end_span)
            row = await cur.fetchone()[span_20](start_span)[span_20](end_span)

        if row: offers = json.loads(row[0])[span_21](start_span)[span_21](end_span)
        else:
            mult = await get_wealth_multiplier()[span_22](start_span)[span_22](end_span)
            commons = random.sample([c for c in FC_CATALOG if c["rarity"] == "COMMON"], 2)[span_23](start_span)[span_23](end_span)
            rares = random.sample([c for c in FC_CATALOG if c["rarity"] == "RARE"], 3)[span_24](start_span)[span_24](end_span)
            elites = random.sample([c for c in FC_CATALOG if c["rarity"] == "ELITE"], 2)[span_25](start_span)[span_25](end_span)
            icons = random.sample([c for c in FC_CATALOG if c["rarity"] == "ICON"], 1)[span_26](start_span)[span_26](end_span)
            selected = commons + rares + elites + icons[span_27](start_span)[span_27](end_span)
            random.shuffle(selected)[span_28](start_span)[span_28](end_span)

            offers = [][span_29](start_span)[span_29](end_span)
            for i, c in enumerate(selected):[span_30](start_span)[span_30](end_span)
                if c["rarity"] == "COMMON": base_price = random.randint(120, 180)[span_31](start_span)[span_31](end_span)
                elif c["rarity"] == "RARE": base_price = random.randint(400, 580)[span_32](start_span)[span_32](end_span)
                elif c["rarity"] == "ELITE": base_price = random.randint(1250, 1650)[span_33](start_span)[span_33](end_span)
                else: base_price = random.randint(3400, 4500)[span_34](start_span)[span_34](end_span)

                dyn_price = int(base_price * mult)[span_35](start_span)[span_35](end_span)
                offers.append({"idx": i, "card": c, "price": dyn_price, "bought": False})[span_36](start_span)[span_36](end_span)

            await db.execute("INSERT OR REPLACE INTO daily_market (user_id, date_str, offers_json) VALUES (?, ?, ?)",[span_37](start_span)[span_37](end_span)
                             (user.id, today_str, json.dumps(offers, ensure_ascii=False)))[span_38](start_span)[span_38](end_span)
            await db.commit()[span_39](start_span)[span_39](end_span)

        async with db.execute("SELECT points, last_free_pack_date FROM users WHERE user_id = ?", (user.id,)) as cur:[span_40](start_span)[span_40](end_span)
            u_row = await cur.fetchone()[span_41](start_span)[span_41](end_span)
            u_pts = u_row[0] if u_row else 0[span_42](start_span)[span_42](end_span)
            free_pack_date = u_row[1] if u_row and len(u_row) > 1 else "[span_43](start_span)"[span_43](end_span)

    text = f"🛒 <b>مارکت نقل‌وانتقالات FC (قیمت‌های متعادل بازار)</b>\n────────────────────\n💰 موجودی شما: <b>{u_pts:,} PTS</b>\n────────────────────\n\n[span_44](start_span)"[span_44](end_span)
    buttons = [][span_45](start_span)[span_45](end_span)
    for o in offers:[span_46](start_span)[span_46](end_span)
        c = o["card"][span_47](start_span)[span_47](end_span)
        tag = RARITY_COLORS.get(c["rarity"], c["rarity"])[span_48](start_span)[span_48](end_span)
        status = "✅ خریداری شده" if o["bought"] else f"{o['price']:,} PTS[span_49](start_span)"[span_49](end_span)
        text += f"▫️ <b>{c['name']}</b> ({c['pos']}) ➔ <b>{c['ovr']} OVR</b>\n    └ {c.get('nation','')} | {c.get('club','')} | {tag} | <b>{status}</b>\n\n[span_50](start_span)"[span_50](end_span)
        if not o["bought"]:[span_51](start_span)[span_51](end_span)
            buttons.append([InlineKeyboardButton(f"خرید {c['name']} ({c['ovr']}) - {o['price']:,} PTS", callback_data=f"buy_m_{o['idx']}")])[span_52](start_span)[span_52](end_span)

    if free_pack_date != today_str:[span_53](start_span)[span_53](end_span)
        buttons.append([InlineKeyboardButton("🎁 باز کردن پک روزانه رایگان (۳ بازیکن)", callback_data="claim_daily_pack")])[span_54](start_span)[span_54](end_span)

    buttons.append([
        InlineKeyboardButton("📦 گلد پک (500 PTS)", callback_data="buy_pack_gold"),
        InlineKeyboardButton("🔥 اولتیمیت پک (1,500 PTS)", callback_data="buy_pack_ultimate")
    ])
    buttons.append([
        InlineKeyboardButton("👑 سوپر پک ویژه (4,000 PTS)", callback_data="buy_pack_super")
    ])
    buttons.append([
        InlineKeyboardButton("⚡️🧪 آزمایشگاه اوولوشن (Evolution)", callback_data="open_evolution"),
        InlineKeyboardButton("💰 فروش کارت‌ها", callback_data="open_sell_menu")[span_55](start_span)[span_55](end_span)
    ])
    buttons.append([InlineKeyboardButton("‹ بازگشت", callback_data="home")])[span_56](start_span)[span_56](end_span)

    kb_markup = InlineKeyboardMarkup(buttons)[span_57](start_span)[span_57](end_span)
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)[span_58](start_span)[span_58](end_span)
    else: await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")[span_59](start_span)[span_59](end_span)

async def sell_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)[span_60](start_span)[span_60](end_span)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_61](start_span)[span_61](end_span)
        async with db.execute("SELECT id, player_name, rating, position, rarity, is_in_lineup FROM user_cards WHERE user_id = ? ORDER BY rating DESC", (user.id,)) as cur:[span_62](start_span)[span_62](end_span)
            cards = await cur.fetchall()[span_63](start_span)[span_63](end_span)

    if not cards:[span_64](start_span)[span_64](end_span)
        text = "🎴 <b>کارت فعالی برای فروش ندارید!</b>[span_65](start_span)"[span_65](end_span)
        if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())[span_66](start_span)[span_66](end_span)
        else: await update.message.reply_text(text, parse_mode="HTML")[span_67](start_span)[span_67](end_span)
        return[span_68](start_span)[span_68](end_span)

    text = "💰 <b>فروشگاه بازخرید کارت‌ها (Quick Sell)</b>\n────────────────────\nوجه فروش فوراً به حسابتان اضافه می‌شود:\n────────────────────\n\n[span_69](start_span)"[span_69](end_span)
    buttons = [][span_70](start_span)[span_70](end_span)
    for cid, name, ovr, pos, rar, in_lineup in cards:[span_71](start_span)[span_71](end_span)
        price = SELL_PRICES.get(rar, 50)[span_72](start_span)[span_72](end_span)
        badge = "🟢 " if in_lineup else "[span_73](start_span)"[span_73](end_span)
        buttons.append([InlineKeyboardButton(f"فروش {badge}{name} ({ovr}) ➔ +{price} PTS", callback_data=f"sell_c_{cid}")])[span_74](start_span)[span_74](end_span)

    buttons.append([InlineKeyboardButton("‹ بازگشت به مارکت", callback_data="view_market")])[span_75](start_span)[span_75](end_span)
    buttons.append([InlineKeyboardButton("‹ منوی اصلی", callback_data="home")])[span_76](start_span)[span_76](end_span)

    kb_markup = InlineKeyboardMarkup(buttons)[span_77](start_span)[span_77](end_span)
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)[span_78](start_span)[span_78](end_span)
    else: await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")[span_79](start_span)[span_79](end_span)

async def my_cards_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)[span_80](start_span)[span_80](end_span)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_81](start_span)[span_81](end_span)
        async with db.execute("SELECT id, player_name, rating, position, rarity, is_in_lineup FROM user_cards WHERE user_id = ? ORDER BY rating DESC", (user.id,)) as cur:[span_82](start_span)[span_82](end_span)
            cards = await cur.fetchall()[span_83](start_span)[span_83](end_span)

    if not cards:[span_84](start_span)[span_84](end_span)
        text = "🎴 <b>کلکسیون کارت‌های شما خالی است!</b>\nاز مارکت یا پک روزانه کارت تهیه کنید.[span_85](start_span)"[span_85](end_span)
        if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())[span_86](start_span)[span_86](end_span)
        else: await update.message.reply_text(text, parse_mode="HTML")[span_87](start_span)[span_87](end_span)
        return[span_88](start_span)[span_88](end_span)

    text = f"🎴 <b>کلکسیون کارت‌های {html.escape(user.first_name)}:</b>\n────────────────────\n\n[span_89](start_span)"[span_89](end_span)
    for cid, name, ovr, pos, rar, in_lineup in cards:[span_90](start_span)[span_90](end_span)
        star = "🟢 [در ترکیب]" if in_lineup else "⚪️[span_91](start_span)"[span_91](end_span)
        c_info = FC_CATALOG_DICT.get(name, {})[span_92](start_span)[span_92](end_span)
        text += f"{star} <b>{name}</b> ({pos}) ➔ <b>{ovr} OVR</b> {c_info.get('nation','')}\n[span_93](start_span)"[span_93](end_span)

    buttons = [
        [InlineKeyboardButton("⚡️ چیدن خودکار قوی‌ترین ترکیب", callback_data="auto_lineup")],[span_94](start_span)[span_94](end_span)
        [InlineKeyboardButton("⚡️🧪 آزمایشگاه اوولوشن (Evolution)", callback_data="open_evolution")],
        [InlineKeyboardButton("💰 فروش کارت‌ها به ربات", callback_data="open_sell_menu")],[span_95](start_span)[span_95](end_span)
        [InlineKeyboardButton("‹ بازگشت", callback_data="home")][span_96](start_span)[span_96](end_span)
    ]
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=InlineKeyboardMarkup(buttons))[span_97](start_span)[span_97](end_span)
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")[span_98](start_span)[span_98](end_span)

async def lineup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)[span_99](start_span)[span_99](end_span)
    tac = await get_user_tactics(user.id)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_100](start_span)[span_100](end_span)
        async with db.execute("SELECT player_name, rating, position FROM user_cards WHERE user_id = ? AND is_in_lineup = 1", (user.id,)) as cur:[span_101](start_span)[span_101](end_span)
            lineup = await cur.fetchall()[span_102](start_span)[span_102](end_span)

    enriched_cards, positions, mids = [], {"GK": None, "DEF": None, "MID1": None, "MID2": None, "FWD": None}, [][span_103](start_span)[span_103](end_span)
    for name, ovr, pos in lineup:[span_104](start_span)[span_104](end_span)
        c_info = FC_CATALOG_DICT.get(name, {"nation": "", "club": "", "rarity": "COMMON", "playstyles": []})[span_105](start_span)[span_105](end_span)
        card_obj = {"name": name, "ovr": ovr, "pos": pos, "nation": c_info.get("nation"), "club": c_info.get("club"), "rarity": c_info.get("rarity"), "playstyles": c_info.get("playstyles", [])}[span_106](start_span)[span_106](end_span)
        enriched_cards.append(card_obj)[span_107](start_span)[span_107](end_span)
        if pos == "GK" and not positions["GK"]: positions["GK"] = card_obj[span_108](start_span)[span_108](end_span)
        elif pos == "DEF" and not positions["DEF"]: positions["DEF"] = card_obj[span_109](start_span)[span_109](end_span)
        elif pos == "FWD" and not positions["FWD"]: positions["FWD"] = card_obj[span_110](start_span)[span_110](end_span)
        elif pos == "MID": mids.append(card_obj)[span_111](start_span)[span_111](end_span)

    if len(mids) >= 1: positions["MID1"] = mids[0][span_112](start_span)[span_112](end_span)
    if len(mids) >= 2: positions["MID2"] = mids[1][span_113](start_span)[span_113](end_span)

    total_ovr = sum(p["ovr"] for p in positions.values() if p)[span_114](start_span)[span_114](end_span)
    count = sum(1 for p in positions.values() if p)[span_115](start_span)[span_115](end_span)
    avg_ovr = round(total_ovr / count, 1) if count > 0 else 0[span_116](start_span)[span_116](end_span)
    chem = calculate_team_chemistry(enriched_cards) if count == 5 else 0[span_117](start_span)[span_117](end_span)
    chem_boost = round((chem / 100.0) * 6.0, 1)[span_118](start_span)[span_118](end_span)
    effective_ovr = round(avg_ovr + chem_boost, 1)[span_119](start_span)[span_119](end_span)

    def p_line(p):
        if not p: return "<i>[جای خالی - بازیکن آماتور ۴۰]</i>[span_120](start_span)"[span_120](end_span)
        return f"<b>{p['name']}</b> ({p['ovr']}) {p.get('nation', '')}[span_121](start_span)"[span_121](end_span)

    text = (
        f"🛡 <b>ترکیب ۵ نفره تیم: {html.escape(user.first_name)}</b>\n────────────────────\n[span_122](start_span)"[span_122](end_span)
        f"⭐️ <b>قدرت پایه تیمی:</b> <code>{avg_ovr} OVR</code>\n[span_123](start_span)"[span_123](end_span)
        f"⚗️ <b>کمیستری تیم:</b> <code>{chem}%</code> (بوست: <b>+{chem_boost}</b>)\n[span_124](start_span)"[span_124](end_span)
        f"⚡️ <b>قدرت نهایی تیم:</b> <code>{effective_ovr} OVR</code> 🔥\n[span_125](start_span)"[span_125](end_span)
        f"📋 <b>تاکتیک تیمی:</b> <code>{TACTIC_NAMES.get(tac['style'], tac['style'])}</code>\n\n"
        f"🧤 دروازه‌بان (GK): {p_line(positions['GK'])}\n[span_126](start_span)"[span_126](end_span)
        f"🛡 مدافع (DEF): {p_line(positions['DEF'])}\n[span_127](start_span)"[span_127](end_span)
        f"⚡️ هافبک ۱ (MID): {p_line(positions['MID1'])}\n[span_128](start_span)"[span_128](end_span)
        f"⚡️ هافبک ۲ (MID): {p_line(positions['MID2'])}\n[span_129](start_span)"[span_129](end_span)
        f"🎯 مهاجم (FWD): {p_line(positions['FWD'])}\n────────────────────[span_130](start_span)"[span_130](end_span)
    )

    buttons = [
        [
            InlineKeyboardButton("🧤 تغییر GK", callback_data="manual_pos_GK"),
            InlineKeyboardButton("🛡 تغییر DEF", callback_data="manual_pos_DEF")
        ],
        [
            InlineKeyboardButton("⚡️ تغییر MID", callback_data="manual_pos_MID"),
            InlineKeyboardButton("🎯 تغییر FWD", callback_data="manual_pos_FWD")
        ],
        [InlineKeyboardButton("📋 تنظیم تاکتیک هوشمند تیم", callback_data="open_tactics")],
        [InlineKeyboardButton("⚡️ چیدن خودکار بهترین ترکیب", callback_data="auto_lineup")],[span_131](start_span)[span_131](end_span)
        [
            InlineKeyboardButton("🎴 کل کارت‌ها", callback_data="view_my_cards"),[span_132](start_span)[span_132](end_span)
            InlineKeyboardButton("💰 فروش کارت‌ها", callback_data="open_sell_menu")[span_133](start_span)[span_133](end_span)
        ],
        [InlineKeyboardButton("‹ بازگشت", callback_data="home")][span_134](start_span)[span_134](end_span)
    ]
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=InlineKeyboardMarkup(buttons))[span_135](start_span)[span_135](end_span)
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")[span_136](start_span)[span_136](end_span)

async def auto_lineup_logic(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_137](start_span)[span_137](end_span)
        await db.execute("UPDATE user_cards SET is_in_lineup = 0 WHERE user_id = ?", (user_id,))[span_138](start_span)[span_138](end_span)
        for pos, count in [("GK", 1), ("DEF", 1), ("MID", 2), ("FWD", 1)]:[span_139](start_span)[span_139](end_span)
            async with db.execute("SELECT id FROM user_cards WHERE user_id = ? AND position = ? ORDER BY rating DESC LIMIT ?", (user_id, pos, count)) as cur:[span_140](start_span)[span_140](end_span)
                ids = [r[0] for r in await cur.fetchall()][span_141](start_span)[span_141](end_span)
                for cid in ids: await db.execute("UPDATE user_cards SET is_in_lineup = 1 WHERE id = ?", (cid,))[span_142](start_span)[span_142](end_span)
        await db.commit()[span_143](start_span)[span_143](end_span)

async def get_user_team_info(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_144](start_span)[span_144](end_span)
        async with db.execute("SELECT player_name, rating, position FROM user_cards WHERE user_id = ? AND is_in_lineup = 1", (user_id,)) as cur:[span_145](start_span)[span_145](end_span)
            cards = await cur.fetchall()[span_146](start_span)[span_146](end_span)

    if len(cards) < 5:[span_147](start_span)[span_147](end_span)
        await auto_lineup_logic(user_id)[span_148](start_span)[span_148](end_span)
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_149](start_span)[span_149](end_span)
            async with db.execute("SELECT player_name, rating, position FROM user_cards WHERE user_id = ? AND is_in_lineup = 1", (user_id,)) as cur:[span_150](start_span)[span_150](end_span)
                cards = await cur.fetchall()[span_151](start_span)[span_151](end_span)

    enriched = [][span_152](start_span)[span_152](end_span)
    positions = {"GK": None, "DEF": None, "MID": [], "FWD": None}[span_153](start_span)[span_153](end_span)

    for c in cards:[span_154](start_span)[span_154](end_span)
        c_info = FC_CATALOG_DICT.get(c[0], {"nation": "", "club": "", "rarity": "COMMON", "playstyles": []})[span_155](start_span)[span_155](end_span)
        card_obj = {"name": c[0], "ovr": c[1], "pos": c[2], "nation": c_info.get("nation"), "club": c_info.get("club"), "rarity": c_info.get("rarity"), "playstyles": c_info.get("playstyles", [])}[span_156](start_span)[span_156](end_span)
        enriched.append(card_obj)[span_157](start_span)[span_157](end_span)
        if c[2] == "GK" and not positions["GK"]: positions["GK"] = card_obj[span_158](start_span)[span_158](end_span)
        elif c[2] == "DEF" and not positions["DEF"]: positions["DEF"] = card_obj[span_159](start_span)[span_159](end_span)
        elif c[2] == "FWD" and not positions["FWD"]: positions["FWD"] = card_obj[span_160](start_span)[span_160](end_span)
        elif c[2] == "MID" and len(positions["MID"]) < 2: positions["MID"].append(card_obj)[span_161](start_span)[span_161](end_span)

    if not positions["GK"]:[span_162](start_span)[span_162](end_span)
        positions["GK"] = {"name": "دروازه‌بان آماتور", "ovr": 40, "pos": "GK", "nation": "", "club": "", "rarity": "COMMON", "playstyles": []}[span_163](start_span)[span_163](end_span)
        enriched.append(positions["GK"])[span_164](start_span)[span_164](end_span)
    if not positions["DEF"]:[span_165](start_span)[span_165](end_span)
        positions["DEF"] = {"name": "مدافع آماتور", "ovr": 40, "pos": "DEF", "nation": "", "club": "", "rarity": "COMMON", "playstyles": []}[span_166](start_span)[span_166](end_span)
        enriched.append(positions["DEF"])[span_167](start_span)[span_167](end_span)
    if not positions["FWD"]:[span_168](start_span)[span_168](end_span)
        positions["FWD"] = {"name": "مهاجم آماتور", "ovr": 40, "pos": "FWD", "nation": "", "club": "", "rarity": "COMMON", "playstyles": []}[span_169](start_span)[span_169](end_span)
        enriched.append(positions["FWD"])[span_170](start_span)[span_170](end_span)
    while len(positions["MID"]) < 2:[span_171](start_span)[span_171](end_span)
        m_dummy = {"name": f"هافبک آماتور {len(positions['MID'])+1}", "ovr": 40, "pos": "MID", "nation": "", "club": "", "rarity": "COMMON", "playstyles": []}[span_172](start_span)[span_172](end_span)
        positions["MID"].append(m_dummy)[span_173](start_span)[span_173](end_span)
        enriched.append(m_dummy)[span_174](start_span)[span_174](end_span)

    base_ovr = round(sum(c["ovr"] for c in enriched[:5]) / 5.0, 1)[span_175](start_span)[span_175](end_span)
    chem = calculate_team_chemistry(enriched[:5])[span_176](start_span)[span_176](end_span)
    chem_boost = round((chem / 100.0) * 6.0, 1)[span_177](start_span)[span_177](end_span)
    effective_ovr = round(base_ovr + chem_boost, 1)[span_178](start_span)[span_178](end_span)

    fwd_c = positions["FWD"][span_179](start_span)[span_179](end_span)
    gk_c = positions["GK"][span_180](start_span)[span_180](end_span)
    def_c = positions["DEF"][span_181](start_span)[span_181](end_span)
    mids_c = positions["MID"][span_182](start_span)[span_182](end_span)
    mid_ovr = round(sum(m["ovr"] for m in mids_c) / len(mids_c), 1)[span_183](start_span)[span_183](end_span)

    return {
        "base_ovr": base_ovr, "chem": chem, "eff_ovr": effective_ovr,
        "fwd": fwd_c["name"], "fwd_ovr": fwd_c["ovr"], "fwd_styles": fwd_c.get("playstyles", []),
        "gk": gk_c["name"], "gk_ovr": gk_c["ovr"], "gk_styles": gk_c.get("playstyles", []),
        "def": def_c["name"], "def_ovr": def_c["ovr"], "def_styles": def_c.get("playstyles", []),
        "mid_ovr": mid_ovr, "mids": [m["name"] for m in mids_c],
        "cards": enriched[:5]
    }

# --- DEEP FC 26 DYNAMIC CHANCES MATCH ENGINE ---

def simulate_chained_fc26_attack(att_dict, def_dict, minute_label="", momentum_boost=0.0):
    t_att = att_dict.get("team") if isinstance(att_dict.get("team"), dict) else (att_dict or {})[span_184](start_span)[span_184](end_span)
    t_def = def_dict.get("team") if isinstance(def_dict.get("team"), dict) else (def_dict or {})[span_185](start_span)[span_185](end_span)
    att_name = att_dict.get("name", "تیم ۱")[span_186](start_span)[span_186](end_span)
    def_name = def_dict.get("name", "تیم ۲")[span_187](start_span)[span_187](end_span)

    mid_att = t_att.get("mid_ovr", 78) + (t_att.get("chem", 35) / 25.0) + (momentum_boost * 4.0)[span_188](start_span)[span_188](end_span)
    mid_def = t_def.get("mid_ovr", 78) + (t_def.get("chem", 35) / 25.0)[span_189](start_span)[span_189](end_span)

    creation_rate = 0.65 + ((mid_att - mid_def) * 0.02)[span_190](start_span)[span_190](end_span)
    creation_rate = max(0.30, min(0.92, creation_rate))[span_191](start_span)[span_191](end_span)

    min_lbl = f" (دقیقه {minute_label})" if minute_label else "[span_192](start_span)"[span_192](end_span)

    def_mids = t_def.get("mids") or ["هافبک حریف"][span_193](start_span)[span_193](end_span)
    att_mids = t_att.get("mids") or [t_att.get("fwd") or "مهاجم"][span_194](start_span)[span_194](end_span)

    if random.random() > creation_rate:[span_195](start_span)[span_195](end_span)
        def_mid_player = random.choice(def_mids)[span_196](start_span)[span_196](end_span)
        return False, None, None, f"⏱ <b>میانه میدان{min_lbl}:</b> نبرد تن‌به‌تن؛ <b>{def_mid_player}</b> توپ‌گیری کرد و مانع ضدحمله شد.", False, False[span_197](start_span)[span_197](end_span)

    assist_maker = random.choice(att_mids)[span_198](start_span)[span_198](end_span)
    fwd_player = t_att.get("fwd") or "مهاجم[span_199](start_span)"[span_199](end_span)
    def_card = t_def.get("def") or "مدافع[span_200](start_span)"[span_200](end_span)

    if random.random() < 0.04:[span_201](start_span)[span_201](end_span)
        is_red = random.random() < 0.35[span_202](start_span)[span_202](end_span)
        card_text = "کارت قرمز مستقیم و اخراج مدافع! 🟥" if is_red else "کارت زرد داور! 🟨[span_203](start_span)"[span_203](end_span)
        pen_scorer = fwd_player[span_204](start_span)[span_204](end_span)
        return True, pen_scorer, None, f"🚨 <b>خطای پنالتی در محوطه جریمه{min_lbl}!</b>\nتکل خشن <b>{def_card}</b> پنالتی اعلام شد ({card_text}). <b>{pen_scorer}</b> با خونسردی توپ را به تور دوخت! ⚽️🎯", True, is_red[span_205](start_span)[span_205](end_span)

    def_style_bonus = len(t_def.get("def_styles", [])) * 0.02[span_206](start_span)[span_206](end_span)
    fwd_style_bonus = len(t_att.get("fwd_styles", [])) * 0.025[span_207](start_span)[span_207](end_span)
    gk_style_bonus = len(t_def.get("gk_styles", [])) * 0.02[span_208](start_span)[span_208](end_span)

    def_tackle_chance = 0.28 + ((t_def.get("def_ovr", 78) - t_att.get("fwd_ovr", 78)) * 0.015) + def_style_bonus - (momentum_boost * 0.05)[span_209](start_span)[span_209](end_span)
    def_tackle_chance = max(0.08, min(0.50, def_tackle_chance))[span_210](start_span)[span_210](end_span)

    if random.random() < def_tackle_chance:[span_211](start_span)[span_211](end_span)
        return False, None, None, f"🛡 <b>دفاع مطمئن{min_lbl}:</b> تکل تمیز و به‌موقع <b>{def_card}</b> مانع از شوت‌زنی {fwd_player} شد.", False, False[span_212](start_span)[span_212](end_span)

    gk_player = t_def.get("gk") or "دروازه‌بان[span_213](start_span)"[span_213](end_span)
    shot_power = t_att.get("fwd_ovr", 78) + (t_att.get("chem", 35) / 30.0) + (momentum_boost * 5.0)[span_214](start_span)[span_214](end_span)
    gk_power = t_def.get("gk_ovr", 78) + (t_def.get("chem", 35) / 30.0)[span_215](start_span)[span_215](end_span)

    goal_chance = 0.55 + ((shot_power - gk_power) * 0.025) + fwd_style_bonus - gk_style_bonus[span_216](start_span)[span_216](end_span)
    goal_chance = max(0.20, min(0.85, goal_chance))[span_217](start_span)[span_217](end_span)

    roll = random.random()[span_218](start_span)[span_218](end_span)
    if roll < goal_chance:[span_219](start_span)[span_219](end_span)
        scorer = fwd_player if random.random() < 0.72 else assist_maker[span_220](start_span)[span_220](end_span)
        scenarios = [
            f"روی پاس در عمق مهندسی‌شده <b>{assist_maker}</b>، <b>{scorer}</b> توپ را کنج دروازه کاشت! 🚀",[span_221](start_span)[span_221](end_span)
            f"شوت سرکش و غیرقابل مهار <b>{scorer}</b> طاق دروازه {def_name} را فرو ریخت! 💥",[span_222](start_span)[span_222](end_span)
            f"ارسال مواج <b>{assist_maker}</b> و ضربه سر چکشی دیدنی <b>{scorer}</b> به تور چسبید! ⚽️",[span_223](start_span)[span_223](end_span)
            f"مهارت تمام‌کنندگی ناب! <b>{scorer}</b> در تک‌به‌تک گلر را فریب داد و گلزنی کرد! 🎯[span_224](start_span)"[span_224](end_span)
        ]
        return True, scorer, assist_maker, f"⚽️🔥 <b>گـُــل برای {att_name}{min_lbl}!</b>\n{random.choice(scenarios)}", True, False[span_225](start_span)[span_225](end_span)
    elif roll < goal_chance + 0.12:[span_226](start_span)[span_226](end_span)
        return False, None, None, f"💥 <b>تیرک دروازه{min_lbl}:</b> شلیک مرگبار <b>{fwd_player}</b> به تیرک افقی دروازه {def_name} برخورد کرد و برگشت!", True, False[span_227](start_span)[span_227](end_span)
    else:
        saves = [
            f"شیرجه تماشایی <b>{gk_player}</b> مانع از گلزنی قطعی {fwd_player} شد!",[span_228](start_span)[span_228](end_span)
            f"واکنش خیره‌کننده با پا توسط <b>{gk_player}</b> دروازه را در ثانیه آخر نجات داد!",[span_229](start_span)[span_229](end_span)
            f"مهار دوضرب و مطمئن توسط <b>{gk_player}</b> در محوطه شش قدم.[span_230](start_span)"[span_230](end_span)
        ]
        return False, None, None, f"🧤 <b>سیو دروازه‌بان{min_lbl}:</b> {random.choice(saves)}", True, False[span_231](start_span)[span_231](end_span)

async def trigger_card_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return[span_232](start_span)[span_232](end_span)
    if not update.message.reply_to_message:[span_233](start_span)[span_233](end_span)
        await update.message.reply_text("⚽️ برای مسابقه کارت‌ها، روی پیام حریف ریپلای کن و بنویس:\n<code>مسابقه کارت</code> یا <code>/cardmatch</code>", parse_mode="HTML")[span_234](start_span)[span_234](end_span)
        return[span_235](start_span)[span_235](end_span)

    p1, p2 = update.effective_user, update.message.reply_to_message.from_user[span_236](start_span)[span_236](end_span)
    if p2.is_bot or p1.id == p2.id: return[span_237](start_span)[span_237](end_span)

    await ensure_user(p1)[span_238](start_span)[span_238](end_span)
    await ensure_user(p2)[span_239](start_span)[span_239](end_span)

    t1, t2 = await get_user_team_info(p1.id), await get_user_team_info(p2.id)[span_240](start_span)[span_240](end_span)

    stake = 100[span_241](start_span)[span_241](end_span)
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_242](start_span)[span_242](end_span)
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (p1.id, p2.id)) as cur:[span_243](start_span)[span_243](end_span)
            balances = {r[0]: r[1] for r in await cur.fetchall()}[span_244](start_span)[span_244](end_span)

    if balances.get(p1.id, 0) < stake or balances.get(p2.id, 0) < stake:[span_245](start_span)[span_245](end_span)
        await update.message.reply_text(f"⛔️ هر دو بازیکن باید حداقل <b>{stake} PTS</b> داشته باشند.", parse_mode="HTML")[span_246](start_span)[span_246](end_span)
        return[span_247](start_span)[span_247](end_span)

    m_id = f"cm_{random.randint(10000, 99999)}[span_248](start_span)"[span_248](end_span)
    ACTIVE_CARD_MATCHES[m_id] = {
        "p1": {"id": p1.id, "name": p1.first_name, "team": t1, "score": 0},
        "p2": {"id": p2.id, "name": p2.first_name, "team": t2, "score": 0},
        "stake": stake, "accepted": False,
        "chat_id": update.effective_chat.id, "msg_id": None
    }[span_249](start_span)[span_249](end_span)

    kb_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ قبول مسابقه کارت‌ها", callback_data=f"ac_cm_{m_id}"),
         InlineKeyboardButton("❌ لغو", callback_data=f"rj_cm_{m_id}")]
    ])[span_250](start_span)[span_250](end_span)
    text = (
        f"🏟 <b>مسابقه بزرگ شبیه‌سازی کارت‌های FC 26!</b> 🔥\n────────────────────\n[span_251](start_span)"[span_251](end_span)
        f"🔵 تیم ۱: <b>{html.escape(p1.first_name)}</b> (⭐️ {t1['eff_ovr']} | ⚗️ {t1['chem']}%)\n[span_252](start_span)"[span_252](end_span)
        f"🔴 تیم ۲: <b>{html.escape(p2.first_name)}</b> (⭐️ {t2['eff_ovr']} | ⚗️ {t2['chem']}%)\n[span_253](start_span)"[span_253](end_span)
        f"💰 مبلغ شرط: <b>{stake} PTS</b> | مدت بازی: <b>۶۰ ثانیه تاکتیکی</b>\n────────────────────\n[span_254](start_span)"[span_254](end_span)
        f"آیا <b>{html.escape(p2.first_name)}</b> این چالش را می‌پذیرد؟[span_255](start_span)"[span_255](end_span)
    )
    sent = await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")[span_256](start_span)[span_256](end_span)
    ACTIVE_CARD_MATCHES[m_id]["msg_id"] = sent.message_id[span_257](start_span)[span_257](end_span)

async def run_live_card_match_simulation(context: ContextTypes.DEFAULT_TYPE, m_id: str):
    m = ACTIVE_CARD_MATCHES.get(m_id)[span_258](start_span)[span_258](end_span)
    if not m: return[span_259](start_span)[span_259](end_span)
    chat_id, msg_id = m["chat_id"], m["msg_id"][span_260](start_span)[span_260](end_span)
    p1, p2 = m["p1"], m["p2"][span_261](start_span)[span_261](end_span)

    tac1 = await get_user_tactics(p1["id"])
    tac2 = await get_user_tactics(p2["id"])
    boost1, boost2, tactical_notes = calculate_tactical_clash(tac1, tac2)

    p1_power = (p1["team"]["eff_ovr"] ** 1.3) * (1 + p1["team"]["chem"] / 100.0) * (1.0 + boost1)
    p2_power = (p2["team"]["eff_ovr"] ** 1.3) * (1 + p2["team"]["chem"] / 100.0) * (1.0 + boost2)
    p1_chance_prob = max(0.20, min(0.80, p1_power / (p1_power + p2_power)))

    p1_pos = int(max(35, min(65, p1_chance_prob * 100)))[span_262](start_span)[span_262](end_span)
    p2_pos = 100 - p1_pos[span_263](start_span)[span_263](end_span)

    stats = {
        "p1_shots": 0, "p2_shots": 0,
        "p1_saves": 0, "p2_saves": 0,
        "scorers": [],
        "motm_points": Counter(),
        "red_cards": []
    }[span_264](start_span)[span_264](end_span)
    momentum = {"p1": 0.0, "p2": 0.0}[span_265](start_span)[span_265](end_span)

    def execute_chance(minute_label, extra_boost=0.0):
        attacker, defender = (p1, p2) if random.random() < p1_chance_prob else (p2, p1)[span_266](start_span)[span_266](end_span)
        att_key = "p1" if attacker == p1 else "p2[span_267](start_span)"[span_267](end_span)
        boost = momentum[att_key] + extra_boost[span_268](start_span)[span_268](end_span)

        g, s, a, txt, on_target, red = simulate_chained_fc26_attack(attacker, defender, minute_label, boost)[span_269](start_span)[span_269](end_span)

        if on_target:[span_270](start_span)[span_270](end_span)
            if attacker == p1: stats["p1_shots"] += 1[span_271](start_span)[span_271](end_span)
            else: stats["p2_shots"] += 1[span_272](start_span)[span_272](end_span)
        if g:[span_273](start_span)[span_273](end_span)
            attacker["score"] += 1[span_274](start_span)[span_274](end_span)
            stats["scorers"].append(f"⚽️ {s} ({attacker['name']})")[span_275](start_span)[span_275](end_span)
            stats["motm_points"][s] += 3[span_276](start_span)[span_276](end_span)
            if a: stats["motm_points"][a] += 2[span_277](start_span)[span_277](end_span)
            opp_key = "p2" if att_key == "p1" else "p1[span_278](start_span)"[span_278](end_span)
            momentum[opp_key] += 0.08[span_279](start_span)[span_279](end_span)
            momentum[att_key] = 0.0[span_280](start_span)[span_280](end_span)
        else:
            if on_target:[span_281](start_span)[span_281](end_span)
                if attacker == p1: stats["p2_saves"] += 1[span_282](start_span)[span_282](end_span)
                else: stats["p1_saves"] += 1[span_283](start_span)[span_283](end_span)
        if red:[span_284](start_span)[span_284](end_span)
            stats["red_cards"].append(f"🟥 اخراج مدافع {defender['name']}")[span_285](start_span)[span_285](end_span)
            defender["team"]["def_ovr"] = max(40, defender["team"].get("def_ovr", 75) - 15)[span_286](start_span)[span_286](end_span)
        return txt[span_287](start_span)[span_287](end_span)

    try:
        analysis_line = f"\n📋 <b>آنالیز تاکتیکی هوش مصنوعی:</b>\n{tactical_notes[0]}\n" if tactical_notes else ""

        await asyncio.sleep(15)[span_288](start_span)[span_288](end_span)
        txt_1a = execute_chance("۱۶")[span_289](start_span)[span_289](end_span)
        txt_1b = execute_chance("۲۴")[span_290](start_span)[span_290](end_span)
        t1 = (
            f"⏱ <b>دقیقه ۲۵ مسابقه:</b>\n[span_291](start_span)"[span_291](end_span)
            f"▫️ <b>{p1['name']} [{p1['score']}] - [{p2['score']}] {p2['name']}</b>\n[span_292](start_span)"[span_292](end_span)
            f"{analysis_line}"
            "────────────────────\n[span_293](start_span)"[span_293](end_span)
            f"{txt_1a}\n\n{txt_1b}[span_294](start_span)"[span_294](end_span)
        )
        await safe_edit_message(context.bot, t1, chat_id=chat_id, message_id=msg_id)[span_295](start_span)[span_295](end_span)

        await asyncio.sleep(15)[span_296](start_span)[span_296](end_span)
        txt_2a = execute_chance("۳۵")[span_297](start_span)[span_297](end_span)
        txt_2b = execute_chance("۴۴")[span_298](start_span)[span_298](end_span)
        t2 = (
            f"⏱ <b>پایان نیمه اول (دقیقه ۴۵):</b>\n[span_299](start_span)"[span_299](end_span)
            f"▫️ <b>{p1['name']} [{p1['score']}] - [{p2['score']}] {p2['name']}</b>\n[span_300](start_span)"[span_300](end_span)
            "────────────────────\n[span_301](start_span)"[span_301](end_span)
            f"{txt_2a}\n\n{txt_2b}[span_302](start_span)"[span_302](end_span)
        )
        await safe_edit_message(context.bot, t2, chat_id=chat_id, message_id=msg_id)[span_303](start_span)[span_303](end_span)

        await asyncio.sleep(15)[span_304](start_span)[span_304](end_span)
        txt_3a = execute_chance("۶۲")[span_305](start_span)[span_305](end_span)
        txt_3b = execute_chance("۷۱")[span_306](start_span)[span_306](end_span)
        t3 = (
            f"⏱ <b>دقیقه ۷۰ مسابقه:</b>\n[span_307](start_span)"[span_307](end_span)
            f"▫️ <b>{p1['name']} [{p1['score']}] - [{p2['score']}] {p2['name']}</b>\n[span_308](start_span)"[span_308](end_span)
            "────────────────────\n[span_309](start_span)"[span_309](end_span)
            f"{txt_3a}\n\n{txt_3b}[span_310](start_span)"[span_310](end_span)
        )
        await safe_edit_message(context.bot, t3, chat_id=chat_id, message_id=msg_id)[span_311](start_span)[span_311](end_span)

        await asyncio.sleep(15)[span_312](start_span)[span_312](end_span)
        clutch_boost = 0.12 if abs(p1["score"] - p2["score"]) <= 1 else 0.0[span_313](start_span)[span_313](end_span)
        txt_4a = execute_chance("۸۶", clutch_boost)[span_314](start_span)[span_314](end_span)
        txt_4b = execute_chance("۹۰+۲", clutch_boost)[span_315](start_span)[span_315](end_span)

        motm_player = "نامشخص[span_316](start_span)"[span_316](end_span)
        motm_rating = "8.2[span_317](start_span)"[span_317](end_span)
        if stats["motm_points"]:[span_318](start_span)[span_318](end_span)
            motm_player, best_pts = stats["motm_points"].most_common(1)[0][span_319](start_span)[span_319](end_span)
            motm_rating = f"{min(9.9, round(7.5 + (best_pts * 0.4), 1))}[span_320](start_span)"[span_320](end_span)
        else:
            motm_player = random.choice(p1["team"]["cards"] + p2["team"]["cards"])["name"][span_321](start_span)[span_321](end_span)
            motm_rating = "8.0[span_322](start_span)"[span_322](end_span)

        s1, s2, stake = p1["score"], p2["score"], m["stake"][span_323](start_span)[span_323](end_span)
        res_footer = "[span_324](start_span)"[span_324](end_span)
        winner_id = None[span_325](start_span)[span_325](end_span)

        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_326](start_span)[span_326](end_span)
            if s1 > s2:[span_327](start_span)[span_327](end_span)
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake * 2, p1["id"]))[span_328](start_span)[span_328](end_span)
                winner_id = p1["id"][span_329](start_span)[span_329](end_span)
                res_footer = f"🏆 <b>پیروز مسابقه: {html.escape(p1['name'])}</b> (+{stake} امتیاز خالص و +100 XP)[span_330](start_span)"[span_330](end_span)
            elif s2 > s1:[span_331](start_span)[span_331](end_span)
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake * 2, p2["id"]))[span_332](start_span)[span_332](end_span)
                winner_id = p2["id"][span_333](start_span)[span_333](end_span)
                res_footer = f"🏆 <b>پیروز مسابقه: {html.escape(p2['name'])}</b> (+{stake} امتیاز خالص و +100 XP)[span_334](start_span)"[span_334](end_span)
            else:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id IN (?, ?)", (stake, p1["id"], p2["id"]))[span_335](start_span)[span_335](end_span)
                res_footer = "🤝 مسابقه با تساوی به پایان رسید! مبلغ شرط به هر دو بازیکن بازگردانده شد.[span_336](start_span)"[span_336](end_span)
            await db.commit()[span_337](start_span)[span_337](end_span)

        if winner_id:[span_338](start_span)[span_338](end_span)
            await profile_add_xp(winner_id, 100)[span_339](start_span)[span_339](end_span)

        await record_quest_action(p1["id"], "card_matches")[span_340](start_span)[span_340](end_span)
        await record_quest_action(p2["id"], "card_matches")[span_341](start_span)[span_341](end_span)

        scorers_str = "\n".join(stats["scorers"]) if stats["scorers"] else "بدون گل[span_342](start_span)"[span_342](end_span)
        red_str = f"\n⚠️ رویداد انضباطی: {', '.join(stats['red_cards'])}" if stats["red_cards"] else "[span_343](start_span)"[span_343](end_span)

        t_final = (
            f"🏁 <b>سوت پایان مسابقه کارت‌های FC 26 (Full Time)</b>\n[span_344](start_span)"[span_344](end_span)
            "────────────────────\n[span_345](start_span)"[span_345](end_span)
            f"▫️ نتیجه قطعی: <b>{p1['name']} [{s1}] - [{s2}] {p2['name']}</b>\n\n[span_346](start_span)"[span_346](end_span)
            f"{txt_4a}\n\n{txt_4b}{red_str}\n\n[span_347](start_span)"[span_347](end_span)
            f"⚽️ <b>گلزنان مسابقه:</b>\n{scorers_str}\n\n[span_348](start_span)"[span_348](end_span)
            "📊 <b>آمار رسمی بازی (Match Stats):</b>\n[span_349](start_span)"[span_349](end_span)
            f"▫️ مالکیت توپ: <code>{p1_pos}%</code> ✕ <code>{p2_pos}%</code>\n[span_350](start_span)"[span_350](end_span)
            f"▫️ شوت در چارچوب: <code>{stats['p1_shots']}</code> ✕ <code>{stats['p2_shots']}</code>\n[span_351](start_span)"[span_351](end_span)
            f"▫️ سیو دروازه‌بان: <code>{stats['p1_saves']}</code> ✕ <code>{stats['p2_saves']}</code>\n\n[span_352](start_span)"[span_352](end_span)
            f"🌟 <b>بهترین بازیکن زمین (MOTM):</b>\n[span_353](start_span)"[span_353](end_span)
            f"👤 <b>{motm_player}</b> (⭐️ نمره <code>{motm_rating}/10</code>)\n[span_354](start_span)"[span_354](end_span)
            "────────────────────\n[span_355](start_span)"[span_355](end_span)
            f"{res_footer}[span_356](start_span)"[span_356](end_span)
        )
        await safe_edit_message(context.bot, t_final, chat_id=chat_id, message_id=msg_id)[span_357](start_span)[span_357](end_span)

    except Exception as e:[span_358](start_span)[span_358](end_span)
        logger.error(f"Error in deep card match simulation: {e}")[span_359](start_span)[span_359](end_span)
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_360](start_span)[span_360](end_span)
            await db.execute("UPDATE users SET points = points + ? WHERE user_id IN (?, ?)", (m["stake"], p1["id"], p2["id"]))[span_361](start_span)[span_361](end_span)
            await db.commit()[span_362](start_span)[span_362](end_span)
        await safe_edit_message(context.bot, "❌ خطایی در جریان شبیه‌سازی مسابقه کارت رخ داد (مبلغ شرط بازگردانده شد).", chat_id=chat_id, message_id=msg_id)[span_363](start_span)[span_363](end_span)
    finally:
        ACTIVE_CARD_MATCHES.pop(m_id, None)[span_364](start_span)[span_364](end_span)

# --- FC CARDS LEAGUE ENGINE ---

async def league_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_365](start_span)[span_365](end_span)
        async with db.execute("SELECT season_id FROM league_seasons WHERE status = 'ACTIVE' ORDER BY created_at DESC LIMIT 1") as cur:[span_366](start_span)[span_366](end_span)
            row = await cur.fetchone()[span_367](start_span)[span_367](end_span)
            if not row:[span_368](start_span)[span_368](end_span)
                msg = "⏳ <b>در حال حاضر هیچ لیگ فعالی برگزار نمی‌شود.</b>[span_369](start_span)"[span_369](end_span)
                if update.callback_query: await safe_edit_message(update.callback_query, msg, reply_markup=kb.get_back_button())[span_370](start_span)[span_370](end_span)
                else: await update.message.reply_text(msg, parse_mode="HTML")[span_371](start_span)[span_371](end_span)
                return[span_372](start_span)[span_372](end_span)
            s_id = row[0][span_373](start_span)[span_373](end_span)

        async with db.execute("""
            SELECT u.first_name, s.played, s.won, s.drawn, s.lost, s.gf, s.ga, s.gd, s.points
            FROM league_standings s
            JOIN users u ON s.user_id = u.user_id
            WHERE s.season_id = ?
            ORDER BY s.points DESC, s.gd DESC, s.gf DESC
        """, (s_id,)) as cur:[span_374](start_span)[span_374](end_span)
            table_rows = await cur.fetchall()[span_375](start_span)[span_375](end_span)

    text = f"🏆 <b>جدول رده‌بندی لیگ کارت‌های FC 26</b>\n────────────────────\n<pre>[span_376](start_span)"[span_376](end_span)
    text += "#  | Team          | P  | W  | D  | L  | GD | Pts\n---+---------------+----+----+----+----+----+----\n[span_377](start_span)"[span_377](end_span)
    for idx, (name, p, w, d, l, gf, ga, gd, pts) in enumerate(table_rows, 1):[span_378](start_span)[span_378](end_span)
        t_name = name[:13].ljust(13)[span_379](start_span)[span_379](end_span)
        text += f"{idx:<2} | {t_name} | {str(p):<2} | {str(w):<2} | {str(d):<2} | {str(l):<2} | {str(gd):<2} | {str(pts):<3}\n[span_380](start_span)"[span_380](end_span)
    text += "</pre>\n💰 <b>پاداش هر بازی:</b> برد <code>+50 PTS</code> | مساوی <code>+20 PTS</code> | هر گل <code>+5 PTS</code>\n<i>(شبیه‌سازی روزانه ۲ مسابقه یا اتمام یکجای سیزن با <code>/l_end</code>)</i>[span_381](start_span)"[span_381](end_span)

    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())[span_382](start_span)[span_382](end_span)
    else: await update.message.reply_text(text, parse_mode="HTML")[span_383](start_span)[span_383](end_span)

async def league_on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user[span_384](start_span)[span_384](end_span)
    if str(user.id) != str(ADMIN_ID): return[span_385](start_span)[span_385](end_span)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_386](start_span)[span_386](end_span)
        async with db.execute("SELECT season_id FROM league_seasons WHERE status = 'ACTIVE'") as cur:[span_387](start_span)[span_387](end_span)
            if await cur.fetchone():[span_388](start_span)[span_388](end_span)
                await update.message.reply_text("⚠️ یک لیگ هم‌اکنون فعال است! ابتدا با /l_off یا /l_end آن را به پایان برسانید.")[span_389](start_span)[span_389](end_span)
                return[span_390](start_span)[span_390](end_span)

        async with db.execute("""
            SELECT user_id FROM user_cards WHERE is_in_lineup = 1 GROUP BY user_id HAVING COUNT(*) >= 1
        """) as cur:[span_391](start_span)[span_391](end_span)
            eligible = [r[0] for r in await cur.fetchall()][span_392](start_span)[span_392](end_span)

    if len(eligible) < 3:[span_393](start_span)[span_393](end_span)
        await update.message.reply_text(f"⛔️ تعداد تیم‌های آماده ({len(eligible)}) کمتر از حد نصاب است! حداقل به ۳ تیم نیاز است.")[span_394](start_span)[span_394](end_span)
        return[span_395](start_span)[span_395](end_span)

    season_id = f"L_{get_iran_now().strftime('%Y%m%d_%H%M')}[span_396](start_span)"[span_396](end_span)
    today_str = get_iran_now().strftime("%Y-%m-%d %H:%M")[span_397](start_span)[span_397](end_span)

    fixtures = [][span_398](start_span)[span_398](end_span)
    for h in eligible:[span_399](start_span)[span_399](end_span)
        for a in eligible:[span_400](start_span)[span_400](end_span)
            if h != a: fixtures.append((season_id, h, a))[span_401](start_span)[span_401](end_span)

    random.shuffle(fixtures)[span_402](start_span)[span_402](end_span)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_403](start_span)[span_403](end_span)
        await db.execute("INSERT INTO league_seasons (season_id, status, created_at) VALUES (?, 'ACTIVE', ?)", (season_id, today_str))[span_404](start_span)[span_404](end_span)
        for s_id, h_id, a_id in fixtures:[span_405](start_span)[span_405](end_span)
            await db.execute("INSERT INTO league_fixtures (season_id, home_id, away_id, status) VALUES (?, ?, ?, 'PENDING')", (s_id, h_id, a_id))[span_406](start_span)[span_406](end_span)
        for uid in eligible:[span_407](start_span)[span_407](end_span)
            await db.execute("INSERT INTO league_standings (season_id, user_id) VALUES (?, ?)", (season_id, uid))[span_408](start_span)[span_408](end_span)
        await db.commit()[span_409](start_span)[span_409](end_span)

    total_m = len(fixtures)[span_410](start_span)[span_410](end_span)
    msg = (
        f"🏆🔥 <b>سوت آغاز فصل جدید لیگ کارت‌های FC 26 زده شد!</b>\n────────────────────\n[span_411](start_span)"[span_411](end_span)
        f"👥 تعداد تیم‌های حاضر: <b>{len(eligible)} تیم</b>\n[span_412](start_span)"[span_412](end_span)
        f"🏟 مجموع مسابقات رفت و برگشت: <b>{total_m} مسابقه</b>\n[span_413](start_span)"[span_413](end_span)
        f"⏰ برنامه: <b>روزی ۲ مسابقه برای هر تیم بعد از ساعت ۱۲ شب</b>\n[span_414](start_span)"[span_414](end_span)
        f"💰 پاداش هر بازی: <b>برد +50 | مساوی +20 | هر گل +5 PTS</b>\n\n[span_415](start_span)"[span_415](end_span)
        f"🥇 قهرمان: ۲,۵۰۰ PTS | 🥈 نایب‌قهرمان: ۱,۲۰۰ PTS | 🥉 سوم: ۶۰۰ PTS[span_416](start_span)"[span_416](end_span)
    )
    target_chat_id = await get_live_chat_id()[span_417](start_span)[span_417](end_span)
    if target_chat_id: await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")[span_418](start_span)[span_418](end_span)
    await update.message.reply_text("✅ لیگ با موفقیت استارت خورد!", parse_mode="HTML")[span_419](start_span)[span_419](end_span)

async def league_off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user[span_420](start_span)[span_420](end_span)
    if str(user.id) != str(ADMIN_ID): return[span_421](start_span)[span_421](end_span)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_422](start_span)[span_422](end_span)
        await db.execute("UPDATE league_seasons SET status = 'CANCELLED' WHERE status = 'ACTIVE'")[span_423](start_span)[span_423](end_span)
        await db.commit()[span_424](start_span)[span_424](end_span)
    await update.message.reply_text("🔴 لیگ فعال فعلی لغو و متوقف شد.")[span_425](start_span)[span_425](end_span)

async def settle_league_season(context: ContextTypes.DEFAULT_TYPE, db, s_id: str):
    async with db.execute("""
        SELECT s.user_id, u.first_name, s.points, s.gd
        FROM league_standings s JOIN users u ON s.user_id = u.user_id
        WHERE s.season_id = ? ORDER BY s.points DESC, s.gd DESC
    """, (s_id,)) as cur:[span_426](start_span)[span_426](end_span)
        final_ranks = await cur.fetchall()[span_427](start_span)[span_427](end_span)

    if final_ranks:[span_428](start_span)[span_428](end_span)
        prizes = {0: (2500, 600), 1: (1200, 350), 2: (600, 200)}[span_429](start_span)[span_429](end_span)
        summary = "🏁 <b>پایان رسمی فصل لیگ کارت‌های FC 26!</b>\n────────────────────\n[span_430](start_span)"[span_430](end_span)
        xp_awards = [][span_431](start_span)[span_431](end_span)
        for idx, (uid, name, pts, gd) in enumerate(final_ranks):[span_432](start_span)[span_432](end_span)
            p_pts, p_xp = prizes.get(idx, (150, 50))[span_433](start_span)[span_433](end_span)
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (p_pts, uid))[span_434](start_span)[span_434](end_span)
            xp_awards.append((uid, p_xp))[span_435](start_span)[span_435](end_span)
            medal = "🥇" if idx == 0 else ("🥈" if idx == 1 else ("🥉" if idx == 2 else f"#{idx+1}"))[span_436](start_span)[span_436](end_span)
            summary += f"{medal} <b>{html.escape(name)}</b>: {pts} امتیاز جدول (+{p_pts:,} PTS جایزه)\n[span_437](start_span)"[span_437](end_span)

        await db.execute("UPDATE league_seasons SET status = 'FINISHED' WHERE season_id = ?", (s_id,))[span_438](start_span)[span_438](end_span)
        await db.commit()[span_439](start_span)[span_439](end_span)

        for uid, p_xp in xp_awards:[span_440](start_span)[span_440](end_span)
            await profile_add_xp(uid, p_xp)[span_441](start_span)[span_441](end_span)

        target_chat_id = await get_live_chat_id()[span_442](start_span)[span_442](end_span)
        if target_chat_id:[span_443](start_span)[span_443](end_span)
            try:[span_444](start_span)[span_444](end_span)
                await context.bot.send_message(chat_id=target_chat_id, text=summary, parse_mode="HTML")[span_445](start_span)[span_445](end_span)
            except Exception: pass[span_446](start_span)[span_446](end_span)

async def simulate_daily_league_task(context: ContextTypes.DEFAULT_TYPE, reply_chat_id: int = None):
    iran_now = get_iran_now()[span_447](start_span)[span_447](end_span)
    today_str = iran_now.strftime("%Y-%m-%d")[span_448](start_span)[span_448](end_span)

    try:[span_449](start_span)[span_449](end_span)
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_450](start_span)[span_450](end_span)
            await db.execute("PRAGMA journal_mode=WAL;")[span_451](start_span)[span_451](end_span)
            async with db.execute("SELECT season_id FROM league_seasons WHERE status = 'ACTIVE' LIMIT 1") as cur:[span_452](start_span)[span_452](end_span)
                row = await cur.fetchone()[span_453](start_span)[span_453](end_span)
                if not row:[span_454](start_span)[span_454](end_span)
                    if reply_chat_id:[span_455](start_span)[span_455](end_span)
                        await context.bot.send_message(chat_id=reply_chat_id, text="⚠️ هیچ لیگی در وضعیت فعال (ACTIVE) پیدا نشد.")[span_456](start_span)[span_456](end_span)
                    return[span_457](start_span)[span_457](end_span)
                s_id = row[0][span_458](start_span)[span_458](end_span)

            setting_key = f"last_league_run_{s_id}[span_459](start_span)"[span_459](end_span)
            async with db.execute("SELECT value FROM bot_settings WHERE key = ?", (setting_key,)) as cur:[span_460](start_span)[span_460](end_span)
                last_run_row = await cur.fetchone()[span_461](start_span)[span_461](end_span)
                last_run_date = last_run_row[0] if last_run_row else None[span_462](start_span)[span_462](end_span)

            if last_run_date == today_str and not reply_chat_id:[span_463](start_span)[span_463](end_span)
                return[span_464](start_span)[span_464](end_span)

            async with db.execute("""
                SELECT id, home_id, away_id 
                FROM league_fixtures 
                WHERE season_id = ? AND (status = 'PENDING' OR status IS NULL OR status = '')
                ORDER BY id ASC
            """, (s_id,)) as cur:[span_465](start_span)[span_465](end_span)
                pending_matches = await cur.fetchall()[span_466](start_span)[span_466](end_span)

        if not pending_matches:[span_467](start_span)[span_467](end_span)
            async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_468](start_span)[span_468](end_span)
                await settle_league_season(context, db, s_id)[span_469](start_span)[span_469](end_span)
            if reply_chat_id:[span_470](start_span)[span_470](end_span)
                await context.bot.send_message(chat_id=reply_chat_id, text="🏁 تمام بازی‌های این فصل قبلاً انجام شده و لیگ پایان یافته است.")[span_471](start_span)[span_471](end_span)
            return[span_472](start_span)[span_472](end_span)

        team_games = Counter()[span_473](start_span)[span_473](end_span)
        selected_matches = [][span_474](start_span)[span_474](end_span)
        remaining = list(pending_matches)[span_475](start_span)[span_475](end_span)

        while True:[span_476](start_span)[span_476](end_span)
            candidates = [f for f in remaining if team_games[f[1]] < 2 and team_games[f[2]] < 2][span_477](start_span)[span_477](end_span)
            if not candidates: break[span_478](start_span)[span_478](end_span)
            candidates.sort(key=lambda f: (team_games[f[1]] + team_games[f[2]]))[span_479](start_span)[span_479](end_span)
            best = candidates[0][span_480](start_span)[span_480](end_span)
            selected_matches.append(best)[span_481](start_span)[span_481](end_span)
            team_games[best[1]] += 1[span_482](start_span)[span_482](end_span)
            team_games[best[2]] += 1[span_483](start_span)[span_483](end_span)
            remaining.remove(best)[span_484](start_span)[span_484](end_span)

        if not selected_matches:[span_485](start_span)[span_485](end_span)
            if reply_chat_id:[span_486](start_span)[span_486](end_span)
                await context.bot.send_message(chat_id=reply_chat_id, text="⚠️ مسابقه‌ای با شرایط برگزاری روزانه پیدا نشد.")[span_487](start_span)[span_487](end_span)
            return[span_488](start_span)[span_488](end_span)

        all_uids = set()[span_489](start_span)[span_489](end_span)
        for _, h_id, a_id in selected_matches:[span_490](start_span)[span_490](end_span)
            all_uids.add(h_id)[span_491](start_span)[span_491](end_span)
            all_uids.add(a_id)[span_492](start_span)[span_492](end_span)

        teams_data = {}[span_493](start_span)[span_493](end_span)
        tactics_data = {}
        for uid in all_uids:[span_494](start_span)[span_494](end_span)
            teams_data[uid] = await get_user_team_info(uid)[span_495](start_span)[span_495](end_span)
            tactics_data[uid] = await get_user_tactics(uid)

        user_names = {}[span_496](start_span)[span_496](end_span)
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_497](start_span)[span_497](end_span)
            for uid in all_uids:[span_498](start_span)[span_498](end_span)
                async with db.execute("SELECT first_name FROM users WHERE user_id = ?", (uid,)) as cur:[span_499](start_span)[span_499](end_span)
                    r = await cur.fetchone()[span_500](start_span)[span_500](end_span)
                    user_names[uid] = r[0] if r and r[0] else f"تیم {uid}[span_501](start_span)"[span_501](end_span)

        now_time = iran_now.strftime("%Y-%m-%d %H:%M")[span_502](start_span)[span_502](end_span)
        match_results = [][span_503](start_span)[span_503](end_span)
        match_updates = [][span_504](start_span)[span_504](end_span)

        for f_id, h_id, a_id in selected_matches:[span_505](start_span)[span_505](end_span)
            t1 = teams_data[h_id][span_506](start_span)[span_506](end_span)
            t2 = teams_data[a_id][span_507](start_span)[span_507](end_span)
            tac1 = tactics_data[h_id]
            tac2 = tactics_data[a_id]

            b1, b2, _ = calculate_tactical_clash(tac1, tac2)

            p1_power = (t1["eff_ovr"] ** 1.3) * (1 + t1["chem"] / 100.0) * (1.0 + b1)
            p2_power = (t2["eff_ovr"] ** 1.3) * (1 + t2["chem"] / 100.0) * (1.0 + b2)
            p1_chance_prob = max(0.20, min(0.80, p1_power / (p1_power + p2_power)))

            s1, s2 = 0, 0[span_508](start_span)[span_508](end_span)
            for _ in range(random.randint(6, 8)):[span_509](start_span)[span_509](end_span)
                if random.random() < p1_chance_prob:[span_510](start_span)[span_510](end_span)
                    if simulate_chained_fc26_attack({"name": "میزبان", "team": t1}, {"name": "میهمان", "team": t2}, "")[0]:[span_511](start_span)[span_511](end_span)
                        s1 += 1[span_512](start_span)[span_512](end_span)
                else:
                    if simulate_chained_fc26_attack({"name": "میهمان", "team": t2}, {"name": "میزبان", "team": t1}, "")[0]:[span_513](start_span)[span_513](end_span)
                        s2 += 1[span_514](start_span)[span_514](end_span)

            reward_h = (50 if s1 > s2 else (20 if s1 == s2 else 0)) + (s1 * 5)[span_515](start_span)[span_515](end_span)
            reward_a = (50 if s2 > s1 else (20 if s1 == s2 else 0)) + (s2 * 5)[span_516](start_span)[span_516](end_span)

            match_results.append((user_names[h_id], s1, s2, user_names[a_id], reward_h, reward_a))[span_517](start_span)[span_517](end_span)
            match_updates.append((f_id, h_id, a_id, s1, s2, reward_h, reward_a))[span_518](start_span)[span_518](end_span)

        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:[span_519](start_span)[span_519](end_span)
            await db.execute("PRAGMA journal_mode=WAL;")[span_520](start_span)[span_520](end_span)
            for f_id, h_id, a_id, s1, s2, reward_h, reward_a in match_updates:[span_521](start_span)[span_521](end_span)
                await db.execute("""
                    UPDATE league_fixtures 
                    SET home_score = ?, away_score = ?, status = 'FINISHED', played_date = ? 
                    WHERE id = ?
                """, (s1, s2, now_time, f_id))[span_522](start_span)[span_522](end_span)

                w1, d1, l1, pts1 = (1, 0, 0, 3) if s1 > s2 else ((0, 1, 0, 1) if s1 == s2 else (0, 0, 1, 0))[span_523](start_span)[span_523](end_span)
                w2, d2, l2, pts2 = (1, 0, 0, 3) if s2 > s1 else ((0, 1, 0, 1) if s1 == s2 else (0, 0, 1, 0))[span_524](start_span)[span_524](end_span)

                await db.execute("""
                    UPDATE league_standings 
                    SET played = played + 1, won = won + ?, drawn = drawn + ?, lost = lost + ?,
                        gf = gf + ?, ga = ga + ?, gd = gd + ?, points = points + ? 
                    WHERE season_id = ? AND user_id = ?
                """, (w1, d1, l1, s1, s2, s1 - s2, pts1, s_id, h_id))[span_525](start_span)[span_525](end_span)

                await db.execute("""
                    UPDATE league_standings 
                    SET played = played + 1, won = won + ?, drawn = drawn + ?, lost = lost + ?,
                        gf = gf + ?, ga = ga + ?, gd = gd + ?, points = points + ? 
                    WHERE season_id = ? AND user_id = ?
                """, (w2, d2, l2, s2, s1, s2 - s1, pts2, s_id, a_id))[span_526](start_span)[span_526](end_span)

                if reward_h > 0:[span_527](start_span)[span_527](end_span)
                    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward_h, h_id))[span_528](start_span)[span_528](end_span)
                if reward_a > 0:[span_529](start_span)[span_529](end_span)
                    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward_a, a_id))[span_530](start_span)[span_530](end_span)

            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (setting_key, today_str))[span_531](start_span)[span_531](end_span)
            await db.commit()[span_532](start_span)[span_532](end_span)

            async with db.execute("""
                SELECT COUNT(*) FROM league_fixtures 
                WHERE season_id = ? AND (status = 'PENDING' OR status IS NULL OR status = '')
            """, (s_id,)) as cur:[span_533](start_span)[span_533](end_span)
                rem_cnt = (await cur.fetchone())[0][span_534](start_span)[span_534](end_span)
            if rem_cnt == 0:[span_535](start_span)[span_535](end_span)
                await settle_league_season(context, db, s_id)[span_536](start_span)[span_536](end_span)

        report_lines = [
            "🏆⚽️ <b>نتایج مسابقات لیگ کارت‌های FC 26 (۲ مسابقه برای هر تیم):</b>",[span_537](start_span)[span_537](end_span)
            "────────────────────[span_538](start_span)"[span_538](end_span)
        ]
        for h_name, s1, s2, a_name, r_h, r_a in match_results:[span_539](start_span)[span_539](end_span)
            report_lines.append(
                f"▫️ <b>{html.escape(h_name)}</b> (<code>+{r_h}</code>) <b>[{s1}] - [{s2}]</b> (<code>+{r_a}</code>) <b>{html.escape(a_name)}</b>[span_540](start_span)"[span_540](end_span)
            )
        report_lines.append("────────────────────")[span_541](start_span)[span_541](end_span)
        report_lines.append("💰 <i>پاداش‌ها (برد +50، مساوی +20، هر گل +5) واریز شد | جدول: <code>/league</code></i>")[span_542](start_span)[span_542](end_span)
        report_msg = "\n".join(report_lines)[span_543](start_span)[span_543](end_span)

        target_chat_id = await get_live_chat_id()[span_544](start_span)[span_544](end_span)
        if target_chat_id:[span_545](start_span)[span_545](end_span)
            try:[span_546](start_span)[span_546](end_span)
                await context.bot.send_message(chat_id=target_chat_id, text=report_msg, parse_mode="HTML")[span_547](start_span)[span_547](end_span)
            except Exception as e:[span_548](start_span)[span_548](end_span)
                logger.error(f"Error sending league results to group: {e}")[span_549](start_span)[span_549](end_span)

        if reply_chat_id and reply_chat_id != target_chat_id:[span_550](start_span)[span_550](end_span)
            try:[span_551](start_span)[span_551](end_span)
                await context.bot.send_message(chat_id=reply_chat_id, text=report_msg, parse_mode="HTML")[span_552](start_span)[span_552](end_span)
            except Exception:[span_553](start_span)[span_553](end_span)
                pass[span_554](start_span)[span_554](end_span)

    except Exception as e:[span_555](start_span)[span_555](end_span)
        logger.error(f"Fatal error in simulate_daily_league_task: {e}", exc_info=True)[span_556](start_span)[span_556](end_span)
        if reply_chat_id:[span_557](start_span)[span_557](end_span)
            await context.bot.send_message(chat_id=reply_chat_id, text=f"❌ خطا در پردازش لیگ:\n<code>{html.escape(str(e))}</code>", parse_mode="HTML")[span_558](start_span)[span_558](end_span)
# --- TRIVIA DUELS ---

async def trigger_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚔️ روی پیام حریف ریپلای کنید و بنویسید: <code>دوئل</code>", parse_mode="HTML")
        return

    challenger, opponent = update.effective_user, update.message.reply_to_message.from_user
    if opponent.is_bot or challenger.id == opponent.id: return
    await ensure_user(challenger)
    await ensure_user(opponent)

    stake = 25
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (challenger.id, opponent.id)) as cur:
            balances = {row[0]: row[1] for row in await cur.fetchall()}

    if balances.get(challenger.id, 0) < stake or balances.get(opponent.id, 0) < stake:
        await update.message.reply_text(f"⛔️ هر دو بازیکن باید حداقل <b>{stake} PTS</b> داشته باشند.", parse_mode="HTML")
        return

    duel_id = f"dl_{random.randint(10000, 99999)}"
    ACTIVE_DUELS[duel_id] = {
        "challenger": {"id": challenger.id, "name": challenger.first_name, "score": 0},
        "opponent": {"id": opponent.id, "name": opponent.first_name, "score": 0},
        "questions": get_random_duel_questions(3),
        "current_q": 0, "stake": stake, "answered": {},
        "accepted": False,
        "chat_id": update.effective_chat.id, "message_id": None
    }

    duel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ قبول چالش دوئل", callback_data=f"acd_{duel_id}"),
         InlineKeyboardButton("❌ رد چالش", callback_data=f"rjd_{duel_id}")]
    ])
    c_name, o_name = html.escape(challenger.first_name), html.escape(opponent.first_name)
    text = f"⚔️ <b>میدان دوئل اطلاعات عمومی!</b> 🔥\n{c_name} 🆚 {o_name}\nجایزه: <b>+{stake} امتیاز</b> | زمان هر سوال: <b>۱۵ ثانیه</b>\nآیا می‌پذیری؟"
    sent_msg = await update.message.reply_text(text, reply_markup=duel_kb, parse_mode="HTML")
    ACTIVE_DUELS[duel_id]["message_id"] = sent_msg.message_id

def render_duel_question_text(duel, q_data, q_idx):
    c_name, o_name = html.escape(duel["challenger"]["name"]), html.escape(duel["opponent"]["name"])
    c_status = "✅" if duel["challenger"]["id"] in duel.get("answered", {}) else "⏳"
    o_status = "✅" if duel["opponent"]["id"] in duel.get("answered", {}) else "⏳"

    return (
        f"❓ <b>سوال {q_idx + 1} از ۳:</b>\n────────────────────\n"
        f"📌 <b>{q_data['question']}</b>\n\n⏱ مهلت پاسخ: <b>۱۵ ثانیه</b>\n────────────────────\n"
        f"👤 {c_name}: {c_status}  |  👤 {o_name}: {o_status}"
    )

async def question_timeout_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    duel_id, q_idx = job_data["duel_id"], job_data["q_idx"]
    duel = ACTIVE_DUELS.get(duel_id)
    if duel and duel.get("current_q") == q_idx:
        duel["current_q"] += 1
        await proceed_duel(context, duel_id)

async def proceed_duel(context: ContextTypes.DEFAULT_TYPE, duel_id: str):
    duel = ACTIVE_DUELS.get(duel_id)
    if not duel: return
    chat_id, msg_id = duel["chat_id"], duel["message_id"]
    q_idx = duel["current_q"]

    if q_idx >= len(duel["questions"]):
        try:
            c_score, o_score = duel["challenger"]["score"], duel["opponent"]["score"]
            c_name, o_name = html.escape(duel["challenger"]["name"]), html.escape(duel["opponent"]["name"])
            c_id, o_id, stake = duel["challenger"]["id"], duel["opponent"]["id"], duel["stake"]

            res_text = (
                "🏁 <b>پایان مسابقه دوئل اطلاعات عمومی!</b>\n────────────────────\n"
                f"👤 {c_name}: <code>{c_score}/3</code>\n"
                f"👤 {o_name}: <code>{o_score}/3</code>\n────────────────────\n"
            )

            winner_id = None
            async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                if c_score > o_score:
                    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake * 2, c_id))
                    res_text += f"🎉 تبریک به <b>{c_name}</b>! برنده <b>+{stake} امتیاز</b> خالص شد."
                    winner_id = c_id
                elif o_score > c_score:
                    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake * 2, o_id))
                    res_text += f"🎉 تبریک به <b>{o_name}</b>! برنده <b>+{stake} امتیاز</b> خالص شد."
                    winner_id = o_id
                else:
                    await db.execute("UPDATE users SET points = points + ? WHERE user_id IN (?, ?)", (stake, c_id, o_id))
                    res_text += "🤝 رقابت مساوی شد! مبلغ شرط به هر دو بازیکن بازگردانده شد."
                await db.commit()

            if winner_id:
                await profile_record_duel_win(winner_id)

            await safe_edit_message(context.bot, res_text, reply_markup=None, chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.error(f"Error finalizing duel: {e}")
        finally:
            ACTIVE_DUELS.pop(duel_id, None)
        return

    q_data = duel["questions"][q_idx]
    duel["answered"] = {}
    buttons = [[InlineKeyboardButton(f"🔘 {opt}", callback_data=f"ad_{duel_id}_{opt_idx}")] for opt_idx, opt in enumerate(q_data["options"])]
    text = render_duel_question_text(duel, q_data, q_idx)
    await safe_edit_message(context.bot, text, reply_markup=InlineKeyboardMarkup(buttons), chat_id=chat_id, message_id=msg_id)
    schedule_timer(context, question_timeout_job, 15, data={"duel_id": duel_id, "q_idx": q_idx}, name=f"duel_timer_{duel_id}_{q_idx}")

async def trigger_team_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚔️ برای بتل ۲ به ۲، روی پیام حریف ریپلای کن و بنویس:\n<code>بتل</code>", parse_mode="HTML")
        return

    challenger, opponent = update.effective_user, update.message.reply_to_message.from_user
    if opponent.is_bot or challenger.id == opponent.id: return
    await ensure_user(challenger)
    await ensure_user(opponent)
    stake = 30

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (challenger.id, opponent.id)) as cur:
            balances = {int(uid): int(pts or 0) for uid, pts in await cur.fetchall()}

    if balances.get(challenger.id, 0) < stake or balances.get(opponent.id, 0) < stake:
        await update.message.reply_text(f"⛔️ هر بازیکن باید حداقل <b>{stake} PTS</b> داشته باشد.", parse_mode="HTML")
        return

    duel_id = f"tm_{random.randint(10000, 99999)}"
    ACTIVE_TEAM_DUELS[duel_id] = {
        "team1": [{"id": challenger.id, "name": challenger.first_name}],
        "team2": [{"id": opponent.id, "name": opponent.first_name}],
        "questions": get_random_duel_questions(3),
        "current_q": 0, "stake": stake, "answered": {},
        "scores": {challenger.id: 0, opponent.id: 0},
        "accepted": {challenger.id, opponent.id},
        "chat_id": update.effective_chat.id, "message_id": None,
        "started": False, "finished": False,
    }
    kb_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ یار تیم ۱", callback_data=f"bt1_{duel_id}"),
         InlineKeyboardButton("➕ یار تیم ۲", callback_data=f"bt2_{duel_id}")],
        [InlineKeyboardButton("❌ لغو بتل", callback_data=f"r2d_{duel_id}")]
    ])
    text = render_team_duel_lobby(ACTIVE_TEAM_DUELS[duel_id])
    sent = await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")
    ACTIVE_TEAM_DUELS[duel_id]["message_id"] = sent.message_id

def render_team_duel_lobby(duel):
    def player_line(team):
        lines = []
        for idx in range(2):
            if idx < len(team): lines.append(f"<b>{html.escape(team[idx]['name'])}</b>")
            else: lines.append("<i>[در انتظار یار...]</i>")
        return " & ".join(lines)

    return (
        "⚔️ <b>لابی نبرد ۲ به ۲ تیمی (بتل)!</b> 🔥\n"
        "────────────────────\n"
        f"🔵 <b>تیم ۱:</b> {player_line(duel['team1'])}\n"
        f"🔴 <b>تیم ۲:</b> {player_line(duel['team2'])}\n"
        "────────────────────\n"
        f"💰 ورودی هر نفر: <b>{duel['stake']} PTS</b> | جایزه تیم برنده: <b>+{duel['stake']} PTS</b>\n"
        "⏱ زمان هر سوال: <b>۱۵ ثانیه</b>\n\n"
        "👇 برای عضویت روی دکمه‌های زیر بزنید:"
    )

def render_team_duel_question_text(duel, q_data, q_idx):
    def player_status(team):
        parts = []
        for p in team:
            name = html.escape(p["name"])
            sc = duel["scores"].get(p["id"], 0)
            ans = "✅" if p["id"] in duel.get("answered", {}) else "⏳"
            parts.append(f"{name}: <code>{sc}</code> {ans}")
        return " | ".join(parts)

    return (
        f"⚔️ <b>بتل ۲ به ۲ تیمی (سوال {q_idx + 1} از ۳)</b>\n"
        "────────────────────\n"
        f"🔵 تیم ۱: {player_status(duel['team1'])}\n"
        f"🔴 تیم ۲: {player_status(duel['team2'])}\n"
        "────────────────────\n"
        f"❓ <b>{q_data['question']}</b>\n\n"
        "⏱ مهلت پاسخ: <b>۱۵ ثانیه</b>"
    )

async def team_duel_timeout_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    duel_id, q_idx = job_data["duel_id"], job_data["q_idx"]
    duel = ACTIVE_TEAM_DUELS.get(duel_id)
    if duel and duel["current_q"] == q_idx and not duel.get("finished"):
        duel["current_q"] += 1
        await proceed_team_duel(context, duel_id)

async def finish_team_duel(context: ContextTypes.DEFAULT_TYPE, duel_id: str):
    duel = ACTIVE_TEAM_DUELS.get(duel_id)
    if not duel or duel.get("finished"): return
    duel["finished"] = True
    chat_id, msg_id = duel["chat_id"], duel["message_id"]
    stake = duel["stake"]

    t1_score = sum(duel["scores"].get(p["id"], 0) for p in duel["team1"])
    t2_score = sum(duel["scores"].get(p["id"], 0) for p in duel["team2"])
    t1_names = " & ".join(f"<b>{html.escape(p['name'])}</b>" for p in duel["team1"])
    t2_names = " & ".join(f"<b>{html.escape(p['name'])}</b>" for p in duel["team2"])

    text = (
        "🏁 <b>پایان رقابت نبرد ۲ به ۲ تیمی!</b>\n"
        "────────────────────\n"
        f"🔵 تیم ۱ ({t1_names}): <b>{t1_score} امتیاز</b>\n"
        f"🔴 تیم ۲ ({t2_names}): <b>{t2_score} امتیاز</b>\n"
        "────────────────────\n"
    )

    winning_team = []
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        if t1_score > t2_score:
            text += f"🎉 تبریک! <b>تیم ۱</b> پیروز شد و هر بازیکن <b>+{stake} امتیاز</b> خالص پاداش گرفت!"
            for p in duel["team1"]:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake * 2, p["id"]))
            winning_team = duel["team1"]
        elif t2_score > t1_score:
            text += f"🎉 تبریک! <b>تیم ۲</b> پیروز شد و هر بازیکن <b>+{stake} امتیاز</b> خالص پاداش گرفت!"
            for p in duel["team2"]:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake * 2, p["id"]))
            winning_team = duel["team2"]
        else:
            text += "🤝 رقابت دو تیم مساوی شد! مبلغ شرط به هر ۴ بازیکن بازگردانده شد."
            for p in duel["team1"] + duel["team2"]:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, p["id"]))
        await db.commit()

    for p in winning_team:
        await profile_record_duel_win(p["id"])

    ACTIVE_TEAM_DUELS.pop(duel_id, None)
    await safe_edit_message(context.bot, text, chat_id=chat_id, message_id=msg_id)

async def proceed_team_duel(context: ContextTypes.DEFAULT_TYPE, duel_id: str):
    duel = ACTIVE_TEAM_DUELS.get(duel_id)
    if not duel or duel.get("finished"): return
    q_idx = duel["current_q"]
    if q_idx >= len(duel["questions"]):
        await finish_team_duel(context, duel_id)
        return

    duel["answered"] = {}
    q_data = duel["questions"][q_idx]
    buttons = []
    for opt_idx, opt_text in enumerate(q_data["options"]):
        buttons.append([InlineKeyboardButton(f"🔘 {opt_text}", callback_data=f"at2_{duel_id}_{opt_idx}")])

    text = render_team_duel_question_text(duel, q_data, q_idx)
    await safe_edit_message(context.bot, text, reply_markup=InlineKeyboardMarkup(buttons), chat_id=duel["chat_id"], message_id=duel["message_id"])
    schedule_timer(context, team_duel_timeout_job, 15, data={"duel_id": duel_id, "q_idx": q_idx}, name=f"team_duel_timer_{duel_id}_{q_idx}")

async def cheat_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, chat = update.effective_user, update.effective_chat
    if chat is None or chat.type != "private" or str(user.id) != str(ADMIN_ID): return

    command = (update.effective_message.text or "").split()[0].split("@")[0].lower()
    if command == "/ch_on":
        CHEAT_MODE_USERS.add(user.id)
        await update.effective_message.reply_text("🟢 <b>Ch Mode اختصاصی فعال شد.</b> پاسخ‌ها درست ثبت می‌شوند.", parse_mode="HTML")
    elif command == "/ch_off":
        CHEAT_MODE_USERS.discard(user.id)
        await update.effective_message.reply_text("🔴 <b>Ch Mode غیرفعال شد.</b>", parse_mode="HTML")

# --- CALLBACK ROUTER CONTINUED ---

    elif data.startswith("ad_"):
        parts = data.split("_")
        duel_id, opt_idx = f"{parts[1]}_{parts[2]}", int(parts[3])
        duel = ACTIVE_DUELS.get(duel_id)
        if not duel or uid not in [duel["challenger"]["id"], duel["opponent"]["id"]] or uid in duel["answered"]:
            await query.answer()
            return

        await query.answer()
        q_idx = duel["current_q"]
        if q_idx >= len(duel["questions"]): return
        q_data = duel["questions"][q_idx]

        is_correct = (opt_idx == q_data["correct_idx"])
        if uid == int(ADMIN_ID) and uid in CHEAT_MODE_USERS: is_correct = True

        duel["answered"][uid] = is_correct
        await profile_record_answer(uid, is_correct)
        if is_correct:
            if uid == duel["challenger"]["id"]: duel["challenger"]["score"] += 1
            else: duel["opponent"]["score"] += 1

        if len(duel["answered"]) == 2:
            cancel_timer(context, f"duel_timer_{duel_id}_{q_idx}")
            duel["current_q"] += 1
            await proceed_duel(context, duel_id)
        else:
            await safe_edit_message(
                context.bot,
                render_duel_question_text(duel, q_data, q_idx),
                reply_markup=query.message.reply_markup,
                chat_id=duel["chat_id"],
                message_id=duel["message_id"]
            )

    elif data.startswith("bt1_") or data.startswith("bt2_"):
        duel_id = data.split("_", 1)[1]
        team_num = 1 if data.startswith("bt1_") else 2
        duel = ACTIVE_TEAM_DUELS.get(duel_id)
        if not duel or duel.get("started"):
            await query.answer()
            return

        user = query.from_user
        await ensure_user(user)
        stake = duel["stake"]

        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT points FROM users WHERE user_id = ?", (user.id,)) as cur:
                r = await cur.fetchone()
                u_pts = r[0] if r else 0

        if u_pts < stake:
            await query.answer(f"⛔️ برای ورود به این بتل حداقل به {stake} PTS نیاز دارید!", show_alert=True)
            return

        target_team = duel["team1"] if team_num == 1 else duel["team2"]
        other_team = duel["team2"] if team_num == 1 else duel["team1"]

        if any(p["id"] == user.id for p in target_team):
            await query.answer("شما هم‌اکنون در این تیم حضور دارید!")
            return
        if len(target_team) >= 2:
            await query.answer("ظرفیت این تیم تکمیل است!", show_alert=True)
            return

        other_team[:] = [p for p in other_team if p["id"] != user.id]
        target_team.append({"id": user.id, "name": user.first_name})
        duel["scores"][user.id] = 0
        duel["accepted"].add(user.id)

        if len(duel["team1"]) == 2 and len(duel["team2"]) == 2:
            all_pids = [p["id"] for p in duel["team1"] + duel["team2"]]
            async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?, ?, ?)", tuple(all_pids)) as cur:
                    bals = {row[0]: row[1] for row in await cur.fetchall()}
                if any(bals.get(pid, 0) < stake for pid in all_pids):
                    await query.answer("موجودی یکی از بازیکنان کمتر از مبلغ ورودی شده است!", show_alert=True)
                    return
                await db.execute("UPDATE users SET points = points - ? WHERE user_id IN (?, ?, ?, ?)", (stake, *all_pids))
                await db.commit()

            duel["started"] = True
            await query.answer("🔥 تیم‌ها تکمیل شد! بتل آغاز می‌شود...")
            await proceed_team_duel(context, duel_id)
        else:
            await query.answer("✅ به تیم ملحق شدید!")
            await safe_edit_message(query, render_team_duel_lobby(duel), reply_markup=query.message.reply_markup)

    elif data.startswith("r2d_"):
        duel_id = data.replace("r2d_", "")
        duel = ACTIVE_TEAM_DUELS.get(duel_id)
        if duel and not duel.get("started"):
            del ACTIVE_TEAM_DUELS[duel_id]
            await query.answer()
            await safe_edit_message(query, "❌ بتل تیمی لغو شد.")
        else:
            await query.answer("امکان لغو بتل پس از شروع وجود ندارد!", show_alert=True)

    elif data.startswith("at2_"):
        parts = data.split("_")
        duel_id, opt_idx = f"{parts[1]}_{parts[2]}", int(parts[3])
        duel = ACTIVE_TEAM_DUELS.get(duel_id)
        if not duel or duel.get("finished"):
            await query.answer()
            return

        all_players = [p["id"] for p in duel["team1"] + duel["team2"]]
        if uid not in all_players or uid in duel.get("answered", {}):
            await query.answer()
            return

        await query.answer()
        q_idx = duel["current_q"]
        if q_idx >= len(duel["questions"]): return
        q_data = duel["questions"][q_idx]

        is_correct = (opt_idx == q_data["correct_idx"])
        if uid == int(ADMIN_ID) and uid in CHEAT_MODE_USERS: is_correct = True

        duel["answered"][uid] = is_correct
        await profile_record_answer(uid, is_correct)
        if is_correct: duel["scores"][uid] = duel["scores"].get(uid, 0) + 1

        if len(duel["answered"]) == len(all_players):
            cancel_timer(context, f"team_duel_timer_{duel_id}_{q_idx}")
            duel["current_q"] += 1
            await proceed_team_duel(context, duel_id)
        else:
            await safe_edit_message(
                context.bot,
                render_team_duel_question_text(duel, q_data, q_idx),
                reply_markup=query.message.reply_markup,
                chat_id=duel["chat_id"],
                message_id=duel["message_id"]
            )

    # --- MANUAL LINEUP CONTROLS ---
    elif data.startswith("manual_pos_"):
        pos = data.replace("manual_pos_", "")
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("""
                SELECT id, player_name, rating, is_in_lineup 
                FROM user_cards 
                WHERE user_id = ? AND position = ? 
                ORDER BY is_in_lineup DESC, rating DESC
            """, (uid, pos)) as cur:
                cards = await cur.fetchall()

        if not cards:
            await query.answer(f"⚠️ شما هیچ کارتی در پست {pos} ندارید!", show_alert=True)
            return

        await query.answer()
        limit = 2 if pos == "MID" else 1
        text = f"⚙️ <b>انتخاب بازیکن برای پست {pos} (حداکثر {limit} بازیکن):</b>\nکلیک کنید تا بازیکن وارد یا خارج شود:"

        buttons = []
        seen = set()
        for cid, name, ovr, in_lineup in cards:
            if not in_lineup and name in seen:
                continue
            seen.add(name)
            c_info = FC_CATALOG_DICT.get(name, {})
            status = "🟢 [در ترکیب]" if in_lineup else "⚪️"
            buttons.append([InlineKeyboardButton(f"{status} {name} ({ovr}) {c_info.get('nation','')}", callback_data=f"setcard_{pos}_{cid}")])

        buttons.append([InlineKeyboardButton("‹ بازگشت به ترکیب", callback_data="view_lineup")])
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("setcard_"):
        _, pos, cid_str = data.split("_")
        cid = int(cid_str)
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT player_name, is_in_lineup FROM user_cards WHERE id = ? AND user_id = ?", (cid, uid)) as cur:
                row = await cur.fetchone()
            if not row:
                await query.answer("کارت یافت نشد!", show_alert=True)
                return
            p_name, in_lineup = row

            if pos != "MID":
                await db.execute("UPDATE user_cards SET is_in_lineup = 0 WHERE user_id = ? AND position = ?", (uid, pos))
                await db.execute("UPDATE user_cards SET is_in_lineup = 1 WHERE id = ?", (cid,))
                await db.commit()
                await query.answer(f"✅ {p_name} فیکس شد!")
                await lineup_cmd(update, context)
            else:
                if in_lineup:
                    await db.execute("UPDATE user_cards SET is_in_lineup = 0 WHERE id = ?", (cid,))
                    await db.commit()
                    await query.answer(f"🔻 {p_name} از ترکیب خارج شد.")
                else:
                    async with db.execute("SELECT id, player_name FROM user_cards WHERE user_id = ? AND position = 'MID' AND is_in_lineup = 1", (uid,)) as cur:
                        active_mids = await cur.fetchall()
                    if any(m[1] == p_name for m in active_mids):
                        await query.answer("⚠️ این بازیکن قبلاً در خط هافبک قرار گرفته است!", show_alert=True)
                        return
                    if len(active_mids) >= 2:
                        await db.execute("UPDATE user_cards SET is_in_lineup = 0 WHERE id = ?", (active_mids[0][0],))
                    await db.execute("UPDATE user_cards SET is_in_lineup = 1 WHERE id = ?", (cid,))
                    await db.commit()
                    await query.answer(f"✅ {p_name} به هافبک اضافه شد!")
                query.data = "manual_pos_MID"
                await callback_router(update, context)

    # --- TACTICAL AI CONFIGURATION CONTROLS ---
    elif data == "open_tactics":
        await query.answer()
        await tactics_menu_cmd(update, context)

    elif data == "set_tac_step1":
        await query.answer()
        kb_s = InlineKeyboardMarkup([
            [InlineKeyboardButton("🪄 تیکی‌تاکا و مالکیت توپ", callback_data="save_tac_style_TIKI_TAKA")],
            [InlineKeyboardButton("⚡️ گگن‌پرسینگ (پرس در زمین حریف)", callback_data="save_tac_style_GEGENPRESS")],
            [InlineKeyboardButton("🚀 ضدحملات برق‌آسا و سریع", callback_data="save_tac_style_FAST_COUNTER")],
            [InlineKeyboardButton("🧱 دفاع اتوبوسی متمرکز", callback_data="save_tac_style_PARK_BUS")],
            [InlineKeyboardButton("‹ بازگشت به تاکتیک", callback_data="open_tactics")]
        ])
        await safe_edit_message(query, "🎯 <b>سبک کلی بازی تیم خود را مشخص کنید:</b>", reply_markup=kb_s)

    elif data == "set_tac_step2":
        await query.answer()
        kb_d = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 دفاع بالا (تله آفساید - هجومی)", callback_data="save_tac_depth_HIGH_LINE")],
            [InlineKeyboardButton("🟡 خط دفاعی متعادل", callback_data="save_tac_depth_BALANCED")],
            [InlineKeyboardButton("🔵 دفاع عقب‌کشیده و عمیق (بستن فضا)", callback_data="save_tac_depth_DEEP")],
            [InlineKeyboardButton("‹ بازگشت به تاکتیک", callback_data="open_tactics")]
        ])
        await safe_edit_message(query, "🛡 <b>ارتفاع و عمق استقرار مدافعان در زمین:</b>", reply_markup=kb_d)

    elif data == "set_tac_step3":
        await query.answer()
        kb_b = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 پاس‌های تک‌ضرب و کوتاه", callback_data="save_tac_buildup_SHORT")],
            [InlineKeyboardButton("✈️ پاس‌های بلند و ارسال قطری", callback_data="save_tac_buildup_LONG")],
            [InlineKeyboardButton("‹ بازگشت به تاکتیک", callback_data="open_tactics")]
        ])
        await safe_edit_message(query, "📐 <b>نحوه انتقال توپ از دفاع به خط حمله:</b>", reply_markup=kb_b)

    elif data == "set_tac_step4":
        await query.answer()
        kb_r = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔥 انتحاری و هجوم همه‌جانبه", callback_data="save_tac_risk_ALL_OUT")],
            [InlineKeyboardButton("⚖️ منظم و ریسک کنترل‌شده", callback_data="save_tac_risk_BALANCED")],
            [InlineKeyboardButton("‹ بازگشت به تاکتیک", callback_data="open_tactics")]
        ])
        await safe_edit_message(query, "⚖️ <b>سطح ریسک بازیکنان در دقایق مختلف مسابقه:</b>", reply_markup=kb_r)

    elif data.startswith("save_tac_"):
        parts = data.split("_")
        field, val = parts[2], parts[3]
        now_str = get_iran_now().strftime("%Y-%m-%d %H:%M")

        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("""
                INSERT INTO user_tactics (user_id, style, depth, buildup, risk, updated_at)
                VALUES (?, 'TIKI_TAKA', 'BALANCED', 'SHORT', 'BALANCED', ?)
                ON CONFLICT(user_id) DO NOTHING
            """, (uid, now_str))
            await db.execute(f"UPDATE user_tactics SET {field} = ?, updated_at = ? WHERE user_id = ?", (val, now_str, uid))
            await db.commit()

        await query.answer("✅ استراتژی ذخیره شد!")
        await tactics_menu_cmd(update, context)

    # --- ADVANCED EVOLUTION CONTROLS ---
    elif data == "open_evolution":
        await query.answer()
        await evolution_menu_cmd(update, context)

    elif data.startswith("evo_cat_"):
        plan_key = data.replace("evo_cat_", "")
        plan = EVO_PLANS.get(plan_key)
        if not plan:
            await query.answer("پلن نامعتبر است!", show_alert=True)
            return

        await query.answer()
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            if "fixed_ovr" in plan:
                async with db.execute("""
                    SELECT id, player_name, rating, position, rarity, is_in_lineup 
                    FROM user_cards 
                    WHERE user_id = ? AND player_name = ? AND rating < 99
                """, (uid, plan["target_name"])) as cur:
                    eligible_cards = await cur.fetchall()
            else:
                min_ovr = plan.get("min_input_ovr", 0)
                max_ovr = plan.get("max_input_ovr", 99)
                r_placeholders = ",".join(f"'{r}'" for r in plan["rarities"])
                query_sql = f"""
                    SELECT id, player_name, rating, position, rarity, is_in_lineup 
                    FROM user_cards 
                    WHERE user_id = ? AND rating >= {min_ovr} AND rating <= {max_ovr} 
                      AND rarity IN ({r_placeholders})
                    ORDER BY rating DESC
                """
                async with db.execute(query_sql, (uid,)) as cur:
                    eligible_cards = await cur.fetchall()

        text = (
            f"⚡️ <b>{plan['title']}</b>\n"
            "────────────────────\n"
            f"📝 {plan['desc']}\n"
            f"💰 هزینه: <b>{plan['cost']:,} PTS</b>\n"
        )
        if "fixed_ovr" in plan:
            text += f"🎴 قربانی‌های لازم: <b>۲ کارت ICON + ۳ کارت ELITE مازاد</b>\n"
        else:
            text += f"🎴 قربانی‌های لازم: <b>{plan['sac_count']} کارت {plan['sac_rarity']} مازاد</b>\n"

        text += "────────────────────\n👇 بازیکن مورد نظر خود را جهت شروع ارتقا انتخاب کنید:\n"

        buttons = []
        if not eligible_cards:
            text += "\n⚠️ <i>شما در حال حاضر کارت واجد شرایطی برای این پلن ندارید!</i>"
        else:
            for cid, name, ovr, pos, rar, in_lineup in eligible_cards[:12]:
                next_ovr = plan.get("fixed_ovr", ovr + plan.get("boost", 2))
                badge = "🟢 " if in_lineup else "⚪️ "
                buttons.append([InlineKeyboardButton(
                    f"{badge}{name} ({ovr} ➔ {next_ovr} OVR)",
                    callback_data=f"evo_req_{plan_key}_{cid}"
                )])

        buttons.append([InlineKeyboardButton("‹ بازگشت به پلن‌ها", callback_data="open_evolution")])
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("evo_req_"):
        parts = data.split("_")
        plan_key, cid = f"{parts[2]}_{parts[3]}" if len(parts) == 5 else parts[2], int(parts[-1])
        plan = EVO_PLANS.get(plan_key)
        if not plan: return

        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT player_name, rating, position, rarity FROM user_cards WHERE id = ? AND user_id = ?", (cid, uid)) as cur:
                target_card = await cur.fetchone()

            async with db.execute("SELECT points FROM users WHERE user_id = ?", (uid,)) as cur:
                user_pts = (await cur.fetchone())[0]

            if "fixed_ovr" in plan:
                async with db.execute("SELECT COUNT(*) FROM user_cards WHERE user_id = ? AND is_in_lineup = 0 AND rarity = 'ICON' AND id != ?", (uid, cid)) as cur:
                    free_icons = (await cur.fetchone())[0]
                async with db.execute("SELECT COUNT(*) FROM user_cards WHERE user_id = ? AND is_in_lineup = 0 AND rarity = 'ELITE' AND id != ?", (uid, cid)) as cur:
                    free_elites = (await cur.fetchone())[0]
                has_fodder = (free_icons >= 2 and free_elites >= 3)
                fodder_status = f"▫️ آیکان مازاد: <b>{free_icons}/2</b> | الیت مازاد: <b>{free_elites}/3</b>"
            else:
                sac_r = plan["sac_rarity"]
                req_cnt = plan["sac_count"]
                async with db.execute("SELECT COUNT(*) FROM user_cards WHERE user_id = ? AND is_in_lineup = 0 AND rarity = ? AND id != ?", (uid, sac_r, cid)) as cur:
                    free_cnt = (await cur.fetchone())[0]
                has_fodder = (free_cnt >= req_cnt)
                fodder_status = f"▫️ کارت‌های {sac_r} مازاد: <b>{free_cnt}/{req_cnt}</b>"

        if not target_card:
            await query.answer("کارت یافت نشد!", show_alert=True)
            return

        name, ovr, pos, rar = target_card
        next_ovr = plan.get("fixed_ovr", min(96, ovr + plan.get("boost", 2)))

        text = (
            f"📋 <b>تایید نهایی اوولوشن: {plan['title']}</b>\n"
            "────────────────────\n"
            f"👤 ستاره انتخابی: <b>{name}</b> ({pos})\n"
            f"📊 ریتینگ فعلی: <b>{ovr} OVR</b> ➔ ریتینگ نهایی: <b>{next_ovr} OVR</b> 🔥\n"
            "────────────────────\n"
            f"💰 هزینه عملیات: <b>{plan['cost']:,} PTS</b> (موجودی شما: {user_pts:,})\n"
            f"🎴 وضعیت کارت‌های قربانی:\n{fodder_status}\n"
            "────────────────────\n"
        )

        buttons = []
        if user_pts < plan["cost"]:
            text += "❌ <b>موجودی امتیاز شما کافی نیست!</b>"
        elif not has_fodder:
            text += "❌ <b>کارت‌های مازاد کافی برای قربانی کردن ندارید!</b>\n<i>(توجه: کارت‌های حاضر در ترکیب اصلی نمی‌توانند قربانی شوند)</i>"
        else:
            text += "✅ <b>همه شرایط مهیا است. آیا عملیات اجرا شود؟</b>"
            buttons.append([InlineKeyboardButton("🔥 تایید و اجرای ارتقا", callback_data=f"evo_run_{plan_key}_{cid}")])

        buttons.append([InlineKeyboardButton("‹ بازگشت به لیست", callback_data=f"evo_cat_{plan_key}")])
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("evo_run_"):
        parts = data.split("_")
        plan_key, cid = f"{parts[2]}_{parts[3]}" if len(parts) == 5 else parts[2], int(parts[-1])
        plan = EVO_PLANS.get(plan_key)
        if not plan: return

        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT player_name, rating, rarity FROM user_cards WHERE id = ? AND user_id = ?", (cid, uid)) as cur:
                card_row = await cur.fetchone()

            async with db.execute("SELECT points FROM users WHERE user_id = ?", (uid,)) as cur:
                user_pts = (await cur.fetchone())[0]

            if not card_row or user_pts < plan["cost"]:
                await query.answer("موجودی یا کارت معتبر نیست!", show_alert=True)
                return

            p_name, cur_ovr, cur_rar = card_row
            burn_ids = []

            if "fixed_ovr" in plan:
                async with db.execute("SELECT id FROM user_cards WHERE user_id = ? AND is_in_lineup = 0 AND rarity = 'ICON' AND id != ? LIMIT 2", (uid, cid)) as cur:
                    icons = [r[0] for r in await cur.fetchall()]
                async with db.execute("SELECT id FROM user_cards WHERE user_id = ? AND is_in_lineup = 0 AND rarity = 'ELITE' AND id != ? LIMIT 3", (uid, cid)) as cur:
                    elites = [r[0] for r in await cur.fetchall()]
                if len(icons) < 2 or len(elites) < 3:
                    await query.answer("کارت‌های قربانی کافی نیست!", show_alert=True)
                    return
                burn_ids = icons + elites
                new_ovr = 99
                new_rar = "ICON"
            else:
                sac_r = plan["sac_rarity"]
                req_cnt = plan["sac_count"]
                async with db.execute("SELECT id FROM user_cards WHERE user_id = ? AND is_in_lineup = 0 AND rarity = ? AND id != ? ORDER BY rating ASC LIMIT ?", (uid, sac_r, cid, req_cnt)) as cur:
                    burn_ids = [r[0] for r in await cur.fetchall()]
                if len(burn_ids) < req_cnt:
                    await query.answer("کارت‌های مازاد کافی نیست!", show_alert=True)
                    return
                new_ovr = min(96, cur_ovr + plan["boost"])
                new_rar = "ICON" if plan_key == "elite_push" else cur_rar

            await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (plan["cost"], uid))
            for b_id in burn_ids:
                await db.execute("DELETE FROM user_cards WHERE id = ?", (b_id,))
            await db.execute("UPDATE user_cards SET rating = ?, rarity = ? WHERE id = ?", (new_ovr, new_rar, cid))
            await db.commit()

        await profile_add_xp(uid, 350 if new_ovr == 99 else 150)
        await query.answer("✨ اوولوشن با موفقیت ثبت شد!", show_alert=True)

        if new_ovr == 99:
            succ_msg = (
                f"👑🐐 <b>تولد کارت فوق‌افسانه‌ای ۹۹ جاودانه!</b> 🔥\n"
                "────────────────────\n"
                f"👤 <b>{p_name}</b> به ریتینگ فرازمینی <b>99 OVR</b> رسید!\n"
                f"▫️ ۲ کارت آیکان و ۳ کارت الیت سوزانده شدند و {plan['cost']:,} PTS کسر گردید.\n"
                "🏆 این کارت اکنون قوی‌ترین مهره بازی در کل لیگ است!"
            )
            target_chat_id = await get_live_chat_id()
            if target_chat_id:
                try:
                    announce = f"🚨🔥 <b>شاهکار تاریخی در لیگ!</b>\nکاربر <b>{html.escape(query.from_user.first_name)}</b> موفق شد کارت <b>{p_name}</b> را به <b>99 OVR</b> ارتقا دهد! 👑🐐"
                    await context.bot.send_message(chat_id=target_chat_id, text=announce, parse_mode="HTML")
                except Exception: pass
        else:
            succ_msg = (
                f"🎉⚡️ <b>اوولوشن با موفقیت اجرا شد!</b>\n"
                "────────────────────\n"
                f"👤 بازیکن: <b>{p_name}</b>\n"
                f"⭐️ ریتینگ جدید: <b>{new_ovr} OVR</b>\n"
                f"▫️ کارت‌های قربانی مصرف شدند و مبلغ {plan['cost']:,} PTS کسر گردید."
            )

        await safe_edit_message(query, succ_msg, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧪 ارتقای دیگر", callback_data="open_evolution")],
            [InlineKeyboardButton("🛡 مشاهده ترکیب تیم", callback_data="view_lineup")],
            [InlineKeyboardButton("‹ منوی اصلی", callback_data="home")]
        ]))

    elif data == "user_profile":
        await query.answer()
        await user_profile_handler(query)
    elif data == "leaderboard_hub":
        await query.answer()
        await safe_edit_message(query, await show_leaderboard_text(uid), reply_markup=kb.get_back_button())

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.strip() if update.message and update.message.text else ""
    if not msg: return
    chat_id = update.effective_chat.id

    game = ACTIVE_GUESS_GAMES.get(chat_id)
    if game and game.get("is_active"):
        user_ans = msg.lower().strip()
        is_matched = any(
            user_ans == alias or re.search(rf"(?:^|\s){re.escape(alias)}(?:$|\s)", user_ans)
            for alias in game["names"]
        )
        if is_matched:
            winner = update.effective_user
            await ensure_user(winner)
            reward = game["reward"]
            game["is_active"] = False
            cancel_timer(context, f"guess_timer_{chat_id}")
            async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, winner.id))
                await db.commit()
            await profile_record_guess_win(winner.id)
            await update.message.reply_text(f"🎉🔥 <b>پاسخ صحیح!</b> 👤 {game['names'][0]} | 🏆 برنده: <b>{html.escape(winner.first_name)}</b> (+{reward} PTS)", parse_mode="HTML")
            return

    if msg.lower() in ["اطلاعات", "info", "پروفایل", "stats"] or msg.lower().startswith(("/info", "اطلاعات")):
        target_user = update.effective_user
        if update.message.reply_to_message: target_user = update.message.reply_to_message.from_user
        await user_profile_handler(update.message, target_user=target_user)
        return

    if re.match(r"^\s*(?:دوبل|قمار|ریسک)\s+(\d+)\s*$", msg):
        await double_or_nothing_cmd(update, context)
    elif msg in ["تاکتیک", "tactic", "tactics", "استراتژی"]: await tactics_menu_cmd(update, context)
    elif msg in ["ارتقا", "ارتقاء", "evo", "upgrade", "اوولوشن"]: await evolution_menu_cmd(update, context)
    elif msg in ["پک روزانه", "پک رایگان", "dailypack"]: await daily_pack_cmd(update, context)
    elif msg in ["دوئل", "duel", "چالش"]: await trigger_duel(update, context)
    elif msg in ["پنالتی", "پنالتی کشی", "penalty"]: await trigger_penalty_shootout(update, context)
    elif msg in ["مسابقه کارت", "کارت مچ", "cardmatch", "کارت"]: await trigger_card_match(update, context)
    elif msg in ["مارکت", "market", "خرید کارت"]: await market_cmd(update, context)
    elif msg in ["فروش", "فروش کارت", "sell"]: await sell_menu_cmd(update, context)
    elif msg in ["کارتها", "کارتهای من", "mycards"]: await my_cards_cmd(update, context)
    elif msg in ["ترکیب", "لاین اپ", "lineup"]: await lineup_cmd(update, context)
    elif msg in ["ماموریت", "ماموریتها", "ماموریت ها", "quests"]: await quests_cmd(update, context)
    elif msg in ["لیگ", "جدول لیگ", "league"]: await league_cmd(update, context)
    elif msg in ["شوت", "گل", "shoot"]: await daily_shoot_cmd(update, context)
    elif msg in ["جایزه", "روزانه", "daily"]: await daily_reward_cmd(update, context)
    elif msg in ["حدس", "حدس بازیکن", "guess"]: await start_guess_game(update, context)
    elif msg in ["گردونه", "wheel", "شانس"]: await spin_wheel_cmd(update, context)
    elif msg in ["جکپات", "jackpot"]: await jackpot_cmd(update, context)
    elif msg in ["شروع", "منو", "فوتبال"]: await start(update, context)
    elif msg in ["جدول", "رنکینگ", "امتیازات"]: await leaderboard_cmd(update, context)

async def post_init(application: Application):
    await init_db()
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA busy_timeout=30000;")
        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_double_date TEXT DEFAULT ''")
            await db.commit()
        except Exception: pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_free_pack_date TEXT DEFAULT ''")
            await db.commit()
        except Exception: pass
        try:
            await db.execute("ALTER TABLE predictions ADD COLUMN settled INTEGER DEFAULT 0")
            await db.commit()
        except Exception: pass
        try:
            await db.execute("ALTER TABLE league_fixtures ADD COLUMN status TEXT DEFAULT 'PENDING'")
            await db.commit()
        except Exception: pass
        try:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_tactics (
                    user_id INTEGER PRIMARY KEY,
                    style TEXT DEFAULT 'TIKI_TAKA',
                    depth TEXT DEFAULT 'BALANCED',
                    buildup TEXT DEFAULT 'SHORT',
                    risk TEXT DEFAULT 'BALANCED',
                    updated_at TEXT
                )
            """)
            await db.commit()
        except Exception: pass

    await ensure_escobar_ai()
    if getattr(application, "job_queue", None):
        application.job_queue.run_repeating(monitor_live_matches_and_banter, interval=90, first=5)
        application.job_queue.run_repeating(check_and_settle_monthly_season, interval=3600, first=15)
        application.job_queue.run_repeating(settle_jackpot_task, interval=7200, first=60)
        application.job_queue.run_repeating(simulate_daily_league_task, interval=300, first=10)
        logger.info("PTB JobQueue is active.")
    else:
        logger.warning("PTB JobQueue is None. Falling back to native asyncio background tasks.")
        asyncio.create_task(run_repeating_task(monitor_live_matches_and_banter, application, 90, 5))
        asyncio.create_task(run_repeating_task(check_and_settle_monthly_season, application, 3600, 15))
        asyncio.create_task(run_repeating_task(settle_jackpot_task, application, 7200, 60))
        asyncio.create_task(run_repeating_task(simulate_daily_league_task, application, 300, 10))

def main():
    threading.Thread(target=start_health_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ranking", leaderboard_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CommandHandler("duel", trigger_duel))
    app.add_handler(CommandHandler("battle", trigger_team_duel))
    app.add_handler(CommandHandler("penalty", trigger_penalty_shootout))
    app.add_handler(CommandHandler("cardmatch", trigger_card_match))
    app.add_handler(CommandHandler("market", market_cmd))
    app.add_handler(CommandHandler("sell", sell_menu_cmd))
    app.add_handler(CommandHandler("pack", lambda u, c: market_cmd(u, c)))
    app.add_handler(CommandHandler("dailypack", daily_pack_cmd))
    app.add_handler(CommandHandler("mycards", my_cards_cmd))
    app.add_handler(CommandHandler("lineup", lineup_cmd))
    app.add_handler(CommandHandler("tactic", tactics_menu_cmd))
    app.add_handler(CommandHandler("tactics", tactics_menu_cmd))
    app.add_handler(CommandHandler(["evo", "evolution", "upgrade"], evolution_menu_cmd))
    app.add_handler(CommandHandler("quests", quests_cmd))
    app.add_handler(CommandHandler("double", double_or_nothing_cmd))
    app.add_handler(CommandHandler("risk", double_or_nothing_cmd))
    app.add_handler(CommandHandler("league", league_cmd))
    app.add_handler(CommandHandler("l_on", league_on_cmd))
    app.add_handler(CommandHandler("l_off", league_off_cmd))
    app.add_handler(CommandHandler(["pl", "Pl"], play_league_day_cmd))
    app.add_handler(CommandHandler(["l_end", "L_end"], finish_league_instantly_cmd))
    app.add_handler(CommandHandler("run_league", play_league_day_cmd))
    app.add_handler(CommandHandler("shoot", daily_shoot_cmd))
    app.add_handler(CommandHandler("daily", daily_reward_cmd))
    app.add_handler(CommandHandler("guess", start_guess_game))
    app.add_handler(CommandHandler("wheel", spin_wheel_cmd))
    app.add_handler(CommandHandler("jackpot", jackpot_cmd))
    app.add_handler(CommandHandler("add", add_points_cmd))
    app.add_handler(CommandHandler("all", add_points_to_all_cmd))
    app.add_handler(CommandHandler("backup", backup_db_cmd))
    app.add_handler(CommandHandler("restore", restore_db_cmd))
    app.add_handler(CommandHandler("reset_points", reset_points_cmd))
    app.add_handler(CommandHandler("set_live", set_live_group))
    app.add_handler(CommandHandler("ch_on", cheat_mode_command))
    app.add_handler(CommandHandler("ch_off", cheat_mode_command))
    app.add_handler(CommandHandler(["nesf", "Nesf"], halve_points_cmd))
    app.add_handler(CommandHandler(["mr", "Mr"], reset_market_cmd))
    app.add_handler(CommandHandler("info", lambda u, c: handle_group_messages(u, c)))

    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.Regex(r"^\s*بتل\s*$"), trigger_team_duel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_messages))

    logger.info("Football Hub Bot running smoothly!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
