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

def normalize_persian_numbers(text: str) -> str:
    """تبدیل ارقام فارسی و عربی به انگلیسی جهت خواندن صحیح مبالغ شرط‌بندی"""
    if not text:
        return ""
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    for i in range(10):
        text = text.replace(persian_digits[i], str(i)).replace(arabic_digits[i], str(i))
    return text

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

USER_TRANSFER_SELL_DRAFT = {}

PACK_DEFINITIONS = {
    "ucl_super": {
        "title": "🏆 سوپر پک قهرمان UCL (ریتینگ ۹۰+)",
        "min_ovr": 90,
        "weights": {"COMMON": 0, "RARE": 0, "ELITE": 35.0, "ICON": 65.0}
    },
    "ucl_elite": {
        "title": "🥈 اولتیمیت پک نایب‌قهرمان UCL (ریتینگ ۸۶+)",
        "min_ovr": 86,
        "weights": {"COMMON": 0, "RARE": 10.0, "ELITE": 65.0, "ICON": 25.0}
    },
    "league_p1": {
        "title": "🥇 پک طلایی قهرمان لیگ (ریتینگ ۸۶+)",
        "min_ovr": 86,
        "weights": {"COMMON": 0, "RARE": 15.0, "ELITE": 65.0, "ICON": 20.0}
    },
    "league_p2": {
        "title": "🥈 پک نقره‌ای نایب‌قهرمان لیگ (ریتینگ ۸۳+)",
        "min_ovr": 83,
        "weights": {"COMMON": 0, "RARE": 45.0, "ELITE": 50.0, "ICON": 5.0}
    },
    "league_p3": {
        "title": "🥉 پک برنزی لیگ (ریتینگ ۸۰+)",
        "min_ovr": 80,
        "weights": {"COMMON": 20.0, "RARE": 70.0, "ELITE": 10.0, "ICON": 0.0}
    },
    "league_part": {
        "title": "📦 پک مشارکت لیگ (ریتینگ ۷۵+)",
        "min_ovr": 75,
        "weights": {"COMMON": 60.0, "RARE": 38.0, "ELITE": 2.0, "ICON": 0.0}
    }
}

async def add_pack_to_inventory(user_id: int, pack_type: str, count: int = 1, db=None):
    if db:
        await db.execute("""
            INSERT INTO user_inventory_packs (user_id, pack_type, count)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, pack_type) DO UPDATE SET count = count + ?
        """, (user_id, pack_type, count, count))
    else:
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as local_db:
            await local_db.execute("""
                INSERT INTO user_inventory_packs (user_id, pack_type, count)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, pack_type) DO UPDATE SET count = count + ?
            """, (user_id, pack_type, count, count))
            await local_db.commit()

async def get_user_inventory_packs(user_id: int) -> list:
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT pack_type, count FROM user_inventory_packs WHERE user_id = ? AND count > 0", (user_id,)) as cur:
            return await cur.fetchall()

def unpack_inventory_card(pack_type: str):
    cfg = PACK_DEFINITIONS.get(pack_type, PACK_DEFINITIONS["league_part"])
    weights = cfg["weights"]
    min_ovr = cfg.get("min_ovr", 75)
    chosen_rarity = random.choices(list(weights.keys()), weights=list(weights.values()))[0]
    pool = [c for c in FC_CATALOG if c["rarity"] == chosen_rarity and c.get("ovr", 0) >= min_ovr]
    if not pool:
        pool = [c for c in FC_CATALOG if c.get("ovr", 0) >= min_ovr]
    if not pool:
        pool = FC_CATALOG
    return random.choice(pool)

def calculate_exact_market_card_price(card: dict, wealth_mult: float) -> int:
    ovr = card.get("ovr", 75)
    rarity = card.get("rarity", "COMMON")
    base = 120 * (1.15 ** max(0, ovr - 75))
    rarity_factor = {
        "COMMON": 1.0,
        "RARE": 1.25,
        "ELITE": 1.6,
        "ICON": 2.2
    }.get(rarity, 1.0)
    random_fluctuation = random.uniform(0.95, 1.05)
    return max(120, int(base * rarity_factor * wealth_mult * random_fluctuation))

def get_card_min_transfer_price(ovr: int, rarity: str) -> int:
    quick_sell = SELL_PRICES.get(rarity, 50)
    ovr_floor = int(45 * (1.12 ** max(0, ovr - 75)))
    return max(quick_sell * 2, ovr_floor)

async def clean_expired_transfers():
    now_str = get_iran_now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("UPDATE transfer_market SET status = 'EXPIRED' WHERE status = 'ACTIVE' AND expires_at <= ?", (now_str,))
        await db.commit()

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
    "eng.1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 لیگ جزیره انگلیس",
    "esp.1": "🇪🇸 لالیگا اسپانیا",
    "ita.1": "🇮🇹 سری آ ایتالیا",
    "ger.1": "🇩🇪 بوندسلیگا آلمان",
    "fra.1": "🇫🇷 لوشامپیونه فرانسه",
    "uefa.champions": "🏆 لیگ قهرمانان اروپا",
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
        elif hasattr(query_or_bot, "callback_query") and query_or_bot.callback_query:
            await query_or_bot.callback_query.message.edit_text(
                text=text, reply_markup=reply_markup, parse_mode="HTML"
            )
        elif hasattr(query_or_bot, "message") and query_or_bot.message:
            await query_or_bot.message.edit_text(
                text=text, reply_markup=reply_markup, parse_mode="HTML"
            )
        elif hasattr(query_or_bot, "edit_message_text"):
            await query_or_bot.edit_message_text(
                text=text, reply_markup=reply_markup, parse_mode="HTML"
            )
        elif hasattr(query_or_bot, "effective_message") and query_or_bot.effective_message:
            await query_or_bot.effective_message.reply_text(
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
            avg_pts = row[0] if row and row[0] else 500
    mult = 1.0 + max(0.0, (avg_pts - 500) / 800.0)
    return max(1.0, mult)

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
        async with db.execute(
            "SELECT penalties_played, card_matches_played, predictions_made, is_claimed FROM daily_quests WHERE user_id = ? AND date_str = ?",
            (user.id, today_str)
        ) as cur:
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

    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)
    else:
        await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

# --- ADMIN COMMANDS ---

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

async def reset_market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("DELETE FROM daily_market")
        await db.commit()

    await update.effective_message.reply_text("🔄 <b>مارکت روزانه برای تمام کاربران ریست شد!</b>", parse_mode="HTML")

async def finish_league_instantly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شبیه‌سازی یکجای تمام مسابقات باقی‌مانده لیگ جاری و تسویه حساب رسمی"""
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    try:
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
            f"⚡️ <b>شبیه‌سازی سریع کل فصل آغاز شد!</b>\nدر حال محاسبه <b>{len(pending_matches)} مسابقه</b> باقی‌مانده و بستن پرونده لیگ...",
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
    except Exception as e:
        logger.error(f"Error in finish_league_instantly_cmd: {e}", exc_info=True)
        await update.effective_message.reply_text(f"❌ <b>خطا در شبیه‌سازی:</b> <code>{html.escape(str(e))}</code>", parse_mode="HTML")

async def play_league_day_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای ۲ مسابقه روزانه هر تیم در لیگ"""
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    chat_id = update.effective_chat.id

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT season_id FROM league_seasons WHERE status = 'ACTIVE' LIMIT 1") as cur:
            row = await cur.fetchone()
            if not row:
                await update.effective_message.reply_text("⚠️ <b>هیچ لیگی در حال حاضر فعال نیست!</b>", parse_mode="HTML")
                return
            s_id = row[0]

        setting_key = f"last_league_run_{s_id}"
        await db.execute("DELETE FROM bot_settings WHERE key = ?", (setting_key,))
        await db.commit()

    await update.effective_message.reply_text("⚽️ <b>در حال شبیه‌سازی ۲ مسابقه برای هر تیم و محاسبه نتایج...</b>", parse_mode="HTML")
    await simulate_daily_league_task(context, reply_chat_id=chat_id)

async def add_points_to_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return
    if not context.args:
        await update.message.reply_text("⚠️ <b>نحوه استفاده:</b> <code>/all 500</code>", parse_mode="HTML")
        return
    try:
        amount = int(normalize_persian_numbers(context.args[0]))
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً یک عدد معتبر وارد کنید.")
        return

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("UPDATE users SET points = points + ? WHERE user_id != ?", (amount, ESCOBAR_AI_ID))
        await db.commit()
    await update.message.reply_text(f"✅ <b>مبلغ {amount:,} امتیاز به تمام کاربران هدیه داده شد!</b>", parse_mode="HTML")

async def add_points_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return
    if not context.args:
        await update.message.reply_text("⚠️ <b>نحوه استفاده:</b> <code>/add 500</code>", parse_mode="HTML")
        return
    try:
        amount = int(normalize_persian_numbers(context.args[0]))
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
    if str(update.effective_user.id) != str(ADMIN_ID): return
    if os.path.exists(DATABASE_PATH):
        with open(DATABASE_PATH, "rb") as doc:
            await update.message.reply_document(
                document=doc,
                filename=f"backup_{get_iran_now().strftime('%Y%m%d_%H%M')}.db",
                caption="💾 <b>نسخه کامل پشتیبان دیتابیس</b>",
                parse_mode="HTML"
            )

async def restore_db_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_ID): return
    target_msg = update.message.reply_to_message
    if not target_msg or not target_msg.document:
        await update.message.reply_text("⚠️ برای بازگردانی، این دستور را روی فایل دیتابیس ریپلای کن.", parse_mode="HTML")
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
    if str(update.effective_user.id) != str(ADMIN_ID): return
    try:
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("UPDATE users SET points = 100")
            await db.commit()
        await update.message.reply_text("✅ <b>امتیاز تمامی کاربران با موفقیت روی ۱۰۰ ریست شد!</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error resetting points: {e}")

async def set_live_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_ID): return
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
        f"🔥 <b>استخر جایزه ویژه ۵۰۰ امتیازی مسابقه بزرگ!</b> 🎁\n"
        "────────────────────\n"
        f"⚽️ <b>{home_name}</b> 🆚 <b>{away_name}</b>\n"
        f"⏰ ساعت شروع: <code>{time_str}</code> (تهران)\n"
        f"💰 جایزه کل: <b>500 امتیاز</b>\n"
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

# --- PREDICTIONS MONITORING ---

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
            try:
                await context.bot.send_message(chat_id=target_chat_id, text=start_msg, parse_mode="HTML")
            except Exception:
                pass

        is_live = raw_status == "LIVE"
        is_finished = raw_status == "FINISHED"
        if (is_live or is_finished) and h_score is not None and a_score is not None:
            prev_h, prev_a = track["home_score"], track["away_score"]
            if h_score != prev_h or a_score != prev_a:
                track["home_score"], track["away_score"] = h_score, a_score
                goal_msg = f"⚽️🔥 <b>تغییر در نتیجه مسابقه! (گـُــل)</b>\n────────────────────\n▫️ <b>{h_name} [{h_score}] - [{a_score}] {a_name}</b>"
                try:
                    await context.bot.send_message(chat_id=target_chat_id, text=goal_msg, parse_mode="HTML")
                except Exception:
                    pass

        if is_finished and track["last_status"] != "FINISHED":
            track["last_status"] = "FINISHED"
            final_h = h_score if h_score is not None else track["home_score"]
            final_a = a_score if a_score is not None else track["away_score"]
            actual_outcome = "HOME" if final_h > final_a else ("AWAY" if final_a > final_h else "DRAW")

            correct_regular_users = await settle_regular_predictions_for_match(m_id, final_h, final_a)
            winners_text = ""

            if track.get("pool_opened"):
                async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                    async with db.execute(
                        "SELECT user_id, user_name FROM special_pool_predictions WHERE match_id = ? AND choice = ? AND settled = 0",
                        (m_id, actual_outcome)
                    ) as cur:
                        winners = await cur.fetchall()
                    if winners:
                        share = 500 // len(winners)
                        winners_text = f"\n\n🎁 <b>برندگان استخر ۵۰۰ امتیازی (هر نفر +{share} PTS):</b>\n"
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
            try:
                await context.bot.send_message(chat_id=target_chat_id, text=ft_msg, parse_mode="HTML")
            except Exception:
                pass

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
            async with db.execute(
                "SELECT user_id, first_name, points FROM users WHERE user_id != ? ORDER BY points DESC LIMIT 4",
                (ESCOBAR_AI_ID,)
            ) as cur:
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
                    try:
                        await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")
                    except Exception:
                        pass

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
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb.get_main_menu())
    else:
        await update.message.reply_text(text, reply_markup=kb.get_main_menu(), parse_mode="HTML")

async def show_leaderboard_text(requesting_user_id: int = None) -> str:
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute(
            "SELECT user_id, first_name, points, duel_wins FROM users WHERE user_id != ? ORDER BY points DESC, duel_wins DESC",
            (ESCOBAR_AI_ID,)
        ) as cur:
            all_users = await cur.fetchall()

    text = "🏆 <b>جدول رده‌بندی سیزن</b> 🔥\n────────────────────\n\n"
    if not all_users:
        return text + "هنوز کاربری ثبت نشده است.\n────────────────────"

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
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
    else:
        await update.message.reply_text(text, parse_mode="HTML")

async def user_profile_handler(query, target_user=None):
    user = target_user or (query.from_user if hasattr(query, "from_user") else query.effective_user)
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
    else:
        await query.reply_text(text, parse_mode="HTML")

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
        await update.effective_message.reply_text("🧤❌ <b>توپ گل نشد!</b> فردا دوباره شانس داری.", parse_mode="HTML")

async def spin_wheel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT last_wheel_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                msg = f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، امروز گردونه را چرخانده‌اید!"
                if update.callback_query:
                    await safe_edit_message(update.callback_query, msg, reply_markup=kb.get_back_button())
                else:
                    await update.effective_message.reply_text(msg, parse_mode="HTML")
                return
        await db.execute("UPDATE users SET last_wheel_date = ? WHERE user_id = ?", (today_str, user.id))
        await db.commit()

    prizes = [30, 60, 120, 250, 380, 500]
    weights = [35, 30, 18, 11, 4, 2]
    win = random.choices(prizes, weights=weights)[0]

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (win, user.id))
        await db.commit()

    await profile_add_xp(user.id, win // 2)
    msg = f"🎡 <b>گردونه شانس متوقف شد!</b>\n🎉 تبریک به <b>{html.escape(user.first_name)}</b>! برنده <b>+{win} امتیاز</b> و <b>+{win // 2} XP</b> شدید!"

    if update.callback_query:
        await safe_edit_message(update.callback_query, msg, reply_markup=kb.get_back_button())
    else:
        await update.message.reply_text(msg, parse_mode="HTML")

async def guess_timeout_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    game = ACTIVE_GUESS_GAMES.get(chat_id)
    if game and game.get("is_active"):
        game["is_active"] = False
        main_name = game["names"][0]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⌛️ <b>مهلت ۳۰ ثانیه‌ای حدس بازیکن تمام شد!</b>\n👤 ستاره مورد نظر: <b>{main_name}</b> بود.",
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
            f"⌛️ <b>زمان ۱۰ ثانیه‌ای تمام شد!</b> 💀\nبه دلیل عدم پاسخ، مبلغ <b>{stake:,} PTS</b> از حسابتان کسر گردید.",
            reply_markup=None,
            chat_id=game["chat_id"],
            message_id=game["msg_id"]
        )
        ACTIVE_DOUBLE_GAMES.pop(g_id, None)

async def double_or_nothing_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    user = update.effective_user
    await ensure_user(user)

    raw_text = normalize_persian_numbers(update.effective_message.text or "")
    args = context.args

    if not args:
        text_match = re.search(r"\d+", raw_text)
        amount_str = text_match.group(0) if text_match else None
    else:
        amount_str = normalize_persian_numbers(args[0])

    if not amount_str or not amount_str.isdigit():
        await update.effective_message.reply_text("⚠️ <b>نحوه استفاده:</b> <code>/double 100</code> یا نوشتن: <code>دوبل 100</code>", parse_mode="HTML")
        return

    stake = int(amount_str)
    if stake < 10:
        await update.effective_message.reply_text("⚠️ حداقل مبلغ شرط چالش دوبل ۱۰ امتیاز است.")
        return

    today_str = get_iran_now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT points, last_double_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            pts = row[0] if row else 0
            last_date = row[1] if row and len(row) > 1 else ""

        if last_date == today_str:
            await update.effective_message.reply_text(
                f"⛔️ <b>{html.escape(user.first_name)}</b> عزیز، شما امروز چالش دوبل را بازی کرده‌اید!\nاین چالش به دلیل ریسک بالا فقط ۱ بار در روز فعال است.",
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
    if not update.message or not update.message.reply_to_message:
        await update.effective_message.reply_text("🥅 روی پیام حریف ریپلای کنید و بنویسید: <code>پنالتی</code>", parse_mode="HTML")
        return

    challenger, opponent = update.effective_user, update.message.reply_to_message.from_user
    if opponent.is_bot or challenger.id == opponent.id: return

    c_count = await get_penalty_count_db(challenger.id)
    o_count = await get_penalty_count_db(opponent.id)
    if c_count >= 3 or o_count >= 3:
        await update.effective_message.reply_text("⛔️ یکی از طرفین سقف ۳ پنالتی امروز خود را مصرف کرده است!", parse_mode="HTML")
        return

    await ensure_user(challenger)
    await ensure_user(opponent)

    stake = 25
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (challenger.id, opponent.id)) as cur:
            balances = {row[0]: row[1] for row in await cur.fetchall()}

    if balances.get(challenger.id, 0) < stake or balances.get(opponent.id, 0) < stake:
        await update.effective_message.reply_text(f"⛔️ هر دو بازیکن باید حداقل <b>{stake} PTS</b> داشته باشند.", parse_mode="HTML")
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
    sent_msg = await update.effective_message.reply_text(text, reply_markup=p_kb, parse_mode="HTML")
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
                        if target_chat_id:
                            await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")

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
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

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

# --- FC CARDS, LINEUP & TACTICAL AI ---

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
        rarity_weights = {"COMMON": 75, "RARE": 20, "ELITE": 4.5, "ICON": 0.5}
    rarities = list(rarity_weights.keys())
    weights = list(rarity_weights.values())
    chosen_rarity = random.choices(rarities, weights=weights)[0]
    filtered = [c for c in FC_CATALOG if c["rarity"] == chosen_rarity]
    if not filtered:
        filtered = FC_CATALOG
    return random.choice(filtered)

def generate_card_for_pack(pack_type: str):
    """تولید یک بازیکن دقیق بر اساس نوع پک درخواستی کاربر"""
    if pack_type == "buy_pack_gold":
        weights = {"COMMON": 75.0, "RARE": 20.0, "ELITE": 4.5, "ICON": 0.5}
        return generate_random_card_by_rarity(weights)
    elif pack_type == "buy_pack_ultimate":
        pool = [c for c in FC_CATALOG if c.get("ovr", 0) >= 80]
        if not pool:
            pool = [c for c in FC_CATALOG if c.get("rarity") in ["RARE", "ELITE", "ICON"]]
        return random.choice(pool)
    elif pack_type == "buy_pack_super":
        pool = [c for c in FC_CATALOG if c.get("ovr", 0) >= 85]
        if not pool:
            pool = [c for c in FC_CATALOG if c.get("rarity") in ["ELITE", "ICON"]]
        return random.choice(pool)
    return random.choice(FC_CATALOG)

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
        notes.append("🧱 دفاع متراکم تیم ۱ مانع فرار حریف در ضدحملات می‌شود.")
    elif s2 == "PARK_BUS" and s1 == "FAST_COUNTER":
        b2 += 0.07
        notes.append("🧱 دفاع اتوبوسی تیم ۲ جلوی ضدحملات مستقیم حریف را گرفته است.")

    if s1 == "TIKI_TAKA" and s2 == "PARK_BUS":
        b1 += 0.07
        notes.append("🪄 چرخش مداوم توپ تیم ۱ اتوبوس حریف را خسته و باز می‌کند.")
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
    if tac2["depth"] == "DEEP" and tac1["buildup"] == "SHORT":
        b1 += 0.05

    if tac1["risk"] == "ALL_OUT":
        b1 += 0.06
        b2 += 0.04
    if tac2["risk"] == "ALL_OUT":
        b2 += 0.06
        b1 += 0.04

    return b1, b2, notes

async def tactics_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)
    tac = await get_user_tactics(user.id)

    text = (
        f"📋 <b>اتاق آنالیز و تاکتیک هوشمند تیم: {html.escape(user.first_name)}</b>\n"
        "────────────────────\n"
        f"▫️ سبک بازی اصلی: <b>{TACTIC_NAMES.get(tac['style'], tac['style'])}</b>\n"
        f"▫️ عمق خط دفاعی: <b>{TACTIC_NAMES.get(tac['depth'], tac['depth'])}</b>\n"
        f"▫️ نحوه بازیسازی: <b>{TACTIC_NAMES.get(tac['buildup'], tac['buildup'])}</b>\n"
        f"▫️ ریسک هجومی: <b>{TACTIC_NAMES.get(tac['risk'], tac['risk'])}</b>\n"
        "────────────────────\n"
        "🧠 <i>هوش مصنوعی مسابقات در هر بازی تاکتیک شما را با حریف تطبیق داده و برتری ایجاد می‌کند!</i>\n\n"
        "👇 برای تنظیم بخش‌ها انتخاب کنید:"
    )

    kb_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ تغییر سبک بازی (Style)", callback_data="set_tac_step1")],
        [InlineKeyboardButton("2️⃣ عمق خط دفاعی (Depth)", callback_data="set_tac_step2")],
        [InlineKeyboardButton("3️⃣ نحوه بازیسازی (Build-Up)", callback_data="set_tac_step3")],
        [InlineKeyboardButton("4️⃣ ریسک تیمی (Risk)", callback_data="set_tac_step4")],
        [
            InlineKeyboardButton("🛡 مشاهده ترکیب تیم", callback_data="view_lineup"),
            InlineKeyboardButton("‹ بازگشت", callback_data="home")
        ]
    ])

    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)
    else:
        await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

async def evolution_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT points FROM users WHERE user_id = ?", (user.id,)) as cur:
            pts = (await cur.fetchone())[0]

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
        "👑 <b>پروژه‌های ماورایی G.O.A.T:</b>\n"
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
        [
            InlineKeyboardButton("🛡 مشاهده ترکیب تیم", callback_data="view_lineup"),
            InlineKeyboardButton("‹ منوی اصلی", callback_data="home")
        ]
    ]

    kb_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)
    else:
        await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

async def market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT offers_json FROM daily_market WHERE user_id = ? AND date_str = ?", (user.id, today_str)) as cur:
            row = await cur.fetchone()

        mult = await get_wealth_multiplier()
        if row:
            offers = json.loads(row[0])
        else:
            commons = random.sample([c for c in FC_CATALOG if c["rarity"] == "COMMON"], 2)
            rares = random.sample([c for c in FC_CATALOG if c["rarity"] == "RARE"], 3)
            elites = random.sample([c for c in FC_CATALOG if c["rarity"] == "ELITE"], 2)
            icons = random.sample([c for c in FC_CATALOG if c["rarity"] == "ICON"], 1)
            selected = commons + rares + elites + icons
            selected.sort(key=lambda x: x["ovr"])

            offers = []
            for i, c in enumerate(selected):
                price = calculate_exact_market_card_price(c, mult)
                offers.append({"idx": i, "card": c, "price": price, "bought": False})

            await db.execute("INSERT OR REPLACE INTO daily_market (user_id, date_str, offers_json) VALUES (?, ?, ?)", (user.id, today_str, json.dumps(offers, ensure_ascii=False)))
            await db.commit()

        async with db.execute("SELECT points, last_free_pack_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            u_row = await cur.fetchone()
            u_pts = u_row[0] if u_row else 0
            free_pack_date = u_row[1] if u_row and len(u_row) > 1 else ""

    inv_packs = await get_user_inventory_packs(user.id)
    inv_count = sum(cnt for _, cnt in inv_packs)

    text = f"🛒 <b>مارکت نقل‌وانتقالات FC (نرخ‌گذاری صعودی OVR)</b>\n────────────────────\n💰 موجودی شما: <b>{u_pts:,} PTS</b> | شاخص تورم: <code>x{mult:.2f}</code>\n────────────────────\n\n"
    buttons = []
    for o in offers:
        c = o["card"]
        tag = RARITY_COLORS.get(c["rarity"], c["rarity"])
        status = "✅ خریداری شده" if o["bought"] else f"{o['price']:,} PTS"
        text += f"▫️ <b>{c['name']}</b> ({c['pos']}) ➔ <b>{c['ovr']} OVR</b>\n    └ {c.get('nation','')} | {c.get('club','')} | {tag} | <b>{status}</b>\n\n"
        if not o["bought"]:
            buttons.append([InlineKeyboardButton(f"خرید {c['name']} ({c['ovr']}) - {o['price']:,} PTS", callback_data=f"buy_m_{o['idx']}")])

    if inv_count > 0:
        buttons.append([InlineKeyboardButton(f"🎒 انبار پک‌های من ({inv_count} پک موجود)", callback_data="open_inventory_packs")])

    if free_pack_date != today_str:
        buttons.append([InlineKeyboardButton("🎁 باز کردن پک روزانه رایگان (۳ بازیکن)", callback_data="claim_daily_pack")])

    buttons.append([InlineKeyboardButton("🔄 ترنسفر مارکت (خرید و فروش با بازیکنان)", callback_data="open_transfer_market")])
    buttons.append([
        InlineKeyboardButton("📦 گلد پک (500 PTS)", callback_data="buy_pack_gold"),
        InlineKeyboardButton("🔥 اولتیمیت پک (1,500 PTS)", callback_data="buy_pack_ultimate")
    ])
    buttons.append([InlineKeyboardButton("👑 سوپر پک ویژه (4,000 PTS)", callback_data="buy_pack_super")])
    buttons.append([
        InlineKeyboardButton("⚡️🧪 آزمایشگاه اوولوشن (Evolution)", callback_data="open_evolution"),
        InlineKeyboardButton("💰 فروش سریع به ربات", callback_data="open_sell_menu")
    ])
    buttons.append([InlineKeyboardButton("‹ بازگشت", callback_data="home")])

    kb_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)
    else:
        await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

async def sell_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute(
            "SELECT id, player_name, rating, position, rarity, is_in_lineup FROM user_cards WHERE user_id = ? ORDER BY rating DESC",
            (user.id,)
        ) as cur:
            cards = await cur.fetchall()

    if not cards:
        text = "🎴 <b>کارت فعالی برای فروش ندارید!</b>"
        if update.callback_query:
            await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
        else:
            await update.message.reply_text(text, parse_mode="HTML")
        return

    text = "💰 <b>فروشگاه بازخرید کارت‌ها (Quick Sell)</b>\n────────────────────\nوجه فروش فوراً به حسابتان اضافه می‌شود:\n────────────────────\n\n"
    buttons = []
    for cid, name, ovr, pos, rar, in_lineup in cards:
        price = SELL_PRICES.get(rar, 50)
        badge = "🟢 " if in_lineup else ""
        buttons.append([InlineKeyboardButton(f"فروش {badge}{name} ({ovr}) ➔ +{price} PTS", callback_data=f"sell_c_{cid}")])

    buttons.append([InlineKeyboardButton("‹ بازگشت به مارکت", callback_data="view_market")])
    buttons.append([InlineKeyboardButton("‹ منوی اصلی", callback_data="home")])

    kb_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)
    else:
        await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

async def my_cards_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute(
            "SELECT id, player_name, rating, position, rarity, is_in_lineup FROM user_cards WHERE user_id = ? ORDER BY rating DESC",
            (user.id,)
        ) as cur:
            cards = await cur.fetchall()

    if not cards:
        text = "🎴 <b>کلکسیون کارت‌های شما خالی است!</b>\nاز مارکت یا پک روزانه کارت تهیه کنید."
        if update.callback_query:
            await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
        else:
            await update.message.reply_text(text, parse_mode="HTML")
        return

    text = f"🎴 <b>کلکسیون کارت‌های {html.escape(user.first_name)}:</b>\n────────────────────\n\n"
    for cid, name, ovr, pos, rar, in_lineup in cards:
        star = "🟢 [در ترکیب]" if in_lineup else "⚪️"
        c_info = FC_CATALOG_DICT.get(name, {})
        text += f"{star} <b>{name}</b> ({pos}) ➔ <b>{ovr} OVR</b> {c_info.get('nation','')}\n"

    buttons = [
        [InlineKeyboardButton("⚡️ چیدن خودکار قوی‌ترین ترکیب", callback_data="auto_lineup")],
        [InlineKeyboardButton("⚡️🧪 آزمایشگاه اوولوشن (Evolution)", callback_data="open_evolution")],
        [InlineKeyboardButton("💰 فروش کارت‌ها به ربات", callback_data="open_sell_menu")],
        [InlineKeyboardButton("‹ بازگشت", callback_data="home")]
    ]
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

async def lineup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)
    tac = await get_user_tactics(user.id)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT player_name, rating, position FROM user_cards WHERE user_id = ? AND is_in_lineup = 1", (user.id,)) as cur:
            lineup = await cur.fetchall()

    enriched_cards, positions, mids = [], {"GK": None, "DEF": None, "MID1": None, "MID2": None, "FWD": None}, []
    for name, ovr, pos in lineup:
        c_info = FC_CATALOG_DICT.get(name, {"nation": "", "club": "", "rarity": "COMMON", "playstyles": []})
        card_obj = {
            "name": name, "ovr": ovr, "pos": pos,
            "nation": c_info.get("nation"), "club": c_info.get("club"),
            "rarity": c_info.get("rarity"), "playstyles": c_info.get("playstyles", [])
        }
        enriched_cards.append(card_obj)
        if pos == "GK" and not positions["GK"]: positions["GK"] = card_obj
        elif pos == "DEF" and not positions["DEF"]: positions["DEF"] = card_obj
        elif pos == "FWD" and not positions["FWD"]: positions["FWD"] = card_obj
        elif pos == "MID": mids.append(card_obj)

    if len(mids) >= 1: positions["MID1"] = mids[0]
    if len(mids) >= 2: positions["MID2"] = mids[1]

    total_ovr = sum(p["ovr"] for p in positions.values() if p)
    count = sum(1 for p in positions.values() if p)
    avg_ovr = round(total_ovr / count, 1) if count > 0 else 0
    chem = calculate_team_chemistry(enriched_cards) if count == 5 else 0
    chem_boost = round((chem / 100.0) * 6.0, 1)
    effective_ovr = round(avg_ovr + chem_boost, 1)

    def p_line(p):
        if not p: return "<i>[جای خالی - بازیکن آماتور ۴۰]</i>"
        return f"<b>{p['name']}</b> ({p['ovr']}) {p.get('nation', '')}"

    text = (
        f"🛡 <b>ترکیب ۵ نفره تیم: {html.escape(user.first_name)}</b>\n────────────────────\n"
        f"⭐️ <b>قدرت پایه تیمی:</b> <code>{avg_ovr} OVR</code>\n"
        f"⚗️ <b>کمیستری تیم:</b> <code>{chem}%</code> (بوست: <b>+{chem_boost}</b>)\n"
        f"⚡️ <b>قدرت نهایی تیم:</b> <code>{effective_ovr} OVR</code> 🔥\n"
        f"📋 <b>تاکتیک تیمی:</b> <code>{TACTIC_NAMES.get(tac['style'], tac['style'])}</code>\n\n"
        f"🧤 دروازه‌بان (GK): {p_line(positions['GK'])}\n"
        f"🛡 مدافع (DEF): {p_line(positions['DEF'])}\n"
        f"⚡️ هافبک ۱ (MID): {p_line(positions['MID1'])}\n"
        f"⚡️ هافبک ۲ (MID): {p_line(positions['MID2'])}\n"
        f"🎯 مهاجم (FWD): {p_line(positions['FWD'])}\n────────────────────"
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
        [InlineKeyboardButton("⚡️ چیدن خودکار بهترین ترکیب", callback_data="auto_lineup")],
        [
            InlineKeyboardButton("🎴 کل کارت‌ها", callback_data="view_my_cards"),
            InlineKeyboardButton("💰 فروش کارت‌ها", callback_data="open_sell_menu")
        ],
        [InlineKeyboardButton("‹ بازگشت", callback_data="home")]
    ]
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

async def auto_lineup_logic(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("UPDATE user_cards SET is_in_lineup = 0 WHERE user_id = ?", (user_id,))
        for pos, count in [("GK", 1), ("DEF", 1), ("MID", 2), ("FWD", 1)]:
            async with db.execute(
                "SELECT id FROM user_cards WHERE user_id = ? AND position = ? ORDER BY rating DESC LIMIT ?",
                (user_id, pos, count)
            ) as cur:
                ids = [r[0] for r in await cur.fetchall()]
                for cid in ids:
                    await db.execute("UPDATE user_cards SET is_in_lineup = 1 WHERE id = ?", (cid,))
        await db.commit()

async def get_user_team_info(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT player_name, rating, position FROM user_cards WHERE user_id = ? AND is_in_lineup = 1", (user_id,)) as cur:
            cards = await cur.fetchall()

    if len(cards) < 5:
        await auto_lineup_logic(user_id)
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT player_name, rating, position FROM user_cards WHERE user_id = ? AND is_in_lineup = 1", (user_id,)) as cur:
                cards = await cur.fetchall()

    enriched = []
    positions = {"GK": None, "DEF": None, "MID": [], "FWD": None}

    for c in cards:
        c_info = FC_CATALOG_DICT.get(c[0], {"nation": "", "club": "", "rarity": "COMMON", "playstyles": []})
        card_obj = {
            "name": c[0], "ovr": c[1], "pos": c[2],
            "nation": c_info.get("nation"), "club": c_info.get("club"),
            "rarity": c_info.get("rarity"), "playstyles": c_info.get("playstyles", [])
        }
        enriched.append(card_obj)
        if c[2] == "GK" and not positions["GK"]: positions["GK"] = card_obj
        elif c[2] == "DEF" and not positions["DEF"]: positions["DEF"] = card_obj
        elif c[2] == "FWD" and not positions["FWD"]: positions["FWD"] = card_obj
        elif c[2] == "MID" and len(positions["MID"]) < 2: positions["MID"].append(card_obj)

    if not positions["GK"]:
        positions["GK"] = {"name": "دروازه‌بان آماتور", "ovr": 40, "pos": "GK", "nation": "", "club": "", "rarity": "COMMON", "playstyles": []}
        enriched.append(positions["GK"])
    if not positions["DEF"]:
        positions["DEF"] = {"name": "مدافع آماتور", "ovr": 40, "pos": "DEF", "nation": "", "club": "", "rarity": "COMMON", "playstyles": []}
        enriched.append(positions["DEF"])
    if not positions["FWD"]:
        positions["FWD"] = {"name": "مهاجم آماتور", "ovr": 40, "pos": "FWD", "nation": "", "club": "", "rarity": "COMMON", "playstyles": []}
        enriched.append(positions["FWD"])
    while len(positions["MID"]) < 2:
        m_dummy = {"name": f"هافبک آماتور {len(positions['MID'])+1}", "ovr": 40, "pos": "MID", "nation": "", "club": "", "rarity": "COMMON", "playstyles": []}
        positions["MID"].append(m_dummy)
        enriched.append(m_dummy)

    base_ovr = round(sum(c["ovr"] for c in enriched[:5]) / 5.0, 1)
    chem = calculate_team_chemistry(enriched[:5])
    chem_boost = round((chem / 100.0) * 6.0, 1)
    effective_ovr = round(base_ovr + chem_boost, 1)

    fwd_c = positions["FWD"]
    gk_c = positions["GK"]
    def_c = positions["DEF"]
    mids_c = positions["MID"]
    mid_ovr = round(sum(m["ovr"] for m in mids_c) / len(mids_c), 1)

    return {
        "base_ovr": base_ovr, "chem": chem, "eff_ovr": effective_ovr,
        "fwd": fwd_c["name"], "fwd_ovr": fwd_c["ovr"], "fwd_styles": fwd_c.get("playstyles", []),
        "gk": gk_c["name"], "gk_ovr": gk_c["ovr"], "gk_styles": gk_c.get("playstyles", []),
        "def": def_c["name"], "def_ovr": def_c["ovr"], "def_styles": def_c.get("playstyles", []),
        "mid_ovr": mid_ovr, "mids": [m["name"] for m in mids_c],
        "cards": enriched[:5]
    }
    # --- FC 26 MATCH ENGINE ---

def simulate_chained_fc26_attack(att_dict, def_dict, minute_label="", momentum_boost=0.0):
    t_att = att_dict.get("team") if isinstance(att_dict.get("team"), dict) else (att_dict or {})
    t_def = def_dict.get("team") if isinstance(def_dict.get("team"), dict) else (def_dict or {})
    att_name = att_dict.get("name", "تیم ۱")
    def_name = def_dict.get("name", "تیم ۲")

    mid_att = t_att.get("mid_ovr", 78) + (t_att.get("chem", 35) / 25.0) + (momentum_boost * 4.0)
    mid_def = t_def.get("mid_ovr", 78) + (t_def.get("chem", 35) / 25.0)

    creation_rate = 0.65 + ((mid_att - mid_def) * 0.02)
    creation_rate = max(0.30, min(0.92, creation_rate))

    min_lbl = f" (دقیقه {minute_label})" if minute_label else ""
    def_mids = t_def.get("mids") or ["هافبک حریف"]
    att_mids = t_att.get("mids") or [t_att.get("fwd") or "مهاجم"]

    if random.random() > creation_rate:
        def_mid_player = random.choice(def_mids)
        return False, None, None, f"⏱ <b>میانه میدان{min_lbl}:</b> نبرد تن‌به‌تن؛ <b>{def_mid_player}</b> توپ‌گیری کرد و مانع ضدحمله شد.", False, False

    assist_maker = random.choice(att_mids)
    fwd_player = t_att.get("fwd") or "مهاجم"
    def_card = t_def.get("def") or "مدافع"

    if random.random() < 0.04:
        is_red = random.random() < 0.35
        card_text = "کارت قرمز مستقیم و اخراج مدافع! 🟥" if is_red else "کارت زرد داور! 🟨"
        pen_scorer = fwd_player
        return True, pen_scorer, None, f"🚨 <b>خطای پنالتی در محوطه جریمه{min_lbl}!</b>\nتکل <b>{def_card}</b> پنالتی اعلام شد ({card_text}). <b>{pen_scorer}</b> با خونسردی توپ را گل کرد! ⚽️🎯", True, is_red

    def_style_bonus = len(t_def.get("def_styles", [])) * 0.02
    fwd_style_bonus = len(t_att.get("fwd_styles", [])) * 0.025
    gk_style_bonus = len(t_def.get("gk_styles", [])) * 0.02

    def_tackle_chance = 0.28 + ((t_def.get("def_ovr", 78) - t_att.get("fwd_ovr", 78)) * 0.015) + def_style_bonus - (momentum_boost * 0.05)
    def_tackle_chance = max(0.08, min(0.50, def_tackle_chance))

    if random.random() < def_tackle_chance:
        return False, None, None, f"🛡 <b>دفاع مطمئن{min_lbl}:</b> تکل تمیز <b>{def_card}</b> مانع از شوت‌زنی {fwd_player} شد.", False, False

    gk_player = t_def.get("gk") or "دروازه‌بان"
    shot_power = t_att.get("fwd_ovr", 78) + (t_att.get("chem", 35) / 30.0) + (momentum_boost * 5.0)
    gk_power = t_def.get("gk_ovr", 78) + (t_def.get("chem", 35) / 30.0)

    goal_chance = 0.55 + ((shot_power - gk_power) * 0.025) + fwd_style_bonus - gk_style_bonus
    goal_chance = max(0.20, min(0.85, goal_chance))

    roll = random.random()
    if roll < goal_chance:
        scorer = fwd_player if random.random() < 0.72 else assist_maker
        scenarios = [
            f"روی پاس در عمق مهندسی‌شده <b>{assist_maker}</b>، <b>{scorer}</b> توپ را کنج دروازه کاشت! 🚀",
            f"شوت سرکش و غیرقابل مهار <b>{scorer}</b> طاق دروازه {def_name} را فرو ریخت! 💥",
            f"ارسال مواج <b>{assist_maker}</b> و ضربه سر چکشی دیدنی <b>{scorer}</b> به تور چسبید! ⚽️",
            f"مهارت تمام‌کنندگی ناب! <b>{scorer}</b> در موقعیت تک‌به‌تک گلر را فریب داد و گلزنی کرد! 🎯"
        ]
        return True, scorer, assist_maker, f"⚽️🔥 <b>گـُــل برای {att_name}{min_lbl}!</b>\n{random.choice(scenarios)}", True, False
    elif roll < goal_chance + 0.12:
        return False, None, None, f"💥 <b>تیرک دروازه{min_lbl}:</b> شلیک تماشایی <b>{fwd_player}</b> به تیرک دروازه {def_name} برخورد کرد!", True, False
    else:
        saves = [
            f"شیرجه تماشایی <b>{gk_player}</b> مانع از گلزنی قطعی {fwd_player} شد!",
            f"واکنش خیره‌کننده با پا توسط <b>{gk_player}</b> دروازه را در ثانیه آخر نجات داد!",
            f"مهار دوضرب و مطمئن توسط <b>{gk_player}</b> در محوطه شش قدم."
        ]
        return False, None, None, f"🧤 <b>سیو دروازه‌بان{min_lbl}:</b> {random.choice(saves)}", True, False

async def trigger_card_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    if not update.message or not update.message.reply_to_message:
        await update.effective_message.reply_text("⚽️ برای مسابقه کارت‌ها، روی پیام حریف ریپلای کن و بنویس:\n<code>مسابقه کارت</code> یا <code>/cardmatch</code>", parse_mode="HTML")
        return

    p1, p2 = update.effective_user, update.message.reply_to_message.from_user
    if p2.is_bot or p1.id == p2.id: return

    await ensure_user(p1)
    await ensure_user(p2)

    t1, t2 = await get_user_team_info(p1.id), await get_user_team_info(p2.id)

    stake = 100
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (p1.id, p2.id)) as cur:
            balances = {r[0]: r[1] for r in await cur.fetchall()}

    if balances.get(p1.id, 0) < stake or balances.get(p2.id, 0) < stake:
        await update.effective_message.reply_text(f"⛔️ هر دو بازیکن باید حداقل <b>{stake} PTS</b> داشته باشند.", parse_mode="HTML")
        return

    m_id = f"cm_{random.randint(10000, 99999)}"
    ACTIVE_CARD_MATCHES[m_id] = {
        "p1": {"id": p1.id, "name": p1.first_name, "team": t1, "score": 0},
        "p2": {"id": p2.id, "name": p2.first_name, "team": t2, "score": 0},
        "stake": stake, "accepted": False,
        "chat_id": update.effective_chat.id, "msg_id": None
    }

    kb_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚔️ قبول مسابقه کارت‌ها", callback_data=f"ac_cm_{m_id}"),
            InlineKeyboardButton("❌ لغو", callback_data=f"rj_cm_{m_id}")
        ]
    ])
    text = (
        f"🏟 <b>مسابقه بزرگ شبیه‌سازی کارت‌های FC 26!</b> 🔥\n────────────────────\n"
        f"🔵 تیم ۱: <b>{html.escape(p1.first_name)}</b> (⭐️ {t1['eff_ovr']} | ⚗️ {t1['chem']}%)\n"
        f"🔴 تیم ۲: <b>{html.escape(p2.first_name)}</b> (⭐️ {t2['eff_ovr']} | ⚗️ {t2['chem']}%)\n"
        f"💰 مبلغ شرط: <b>{stake} PTS</b> | مدت بازی: <b>۶۰ ثانیه تاکتیکی</b>\n────────────────────\n"
        f"آیا <b>{html.escape(p2.first_name)}</b> این چالش را می‌پذیرد؟"
    )
    sent = await update.effective_message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")
    ACTIVE_CARD_MATCHES[m_id]["msg_id"] = sent.message_id

async def run_live_card_match_simulation(context: ContextTypes.DEFAULT_TYPE, m_id: str):
    m = ACTIVE_CARD_MATCHES.get(m_id)
    if not m: return
    chat_id, msg_id = m["chat_id"], m["msg_id"]
    p1, p2 = m["p1"], m["p2"]

    tac1 = await get_user_tactics(p1["id"])
    tac2 = await get_user_tactics(p2["id"])
    boost1, boost2, tactical_notes = calculate_tactical_clash(tac1, tac2)

    p1_power = (p1["team"]["eff_ovr"] ** 1.3) * (1 + p1["team"]["chem"] / 100.0) * (1.0 + boost1)
    p2_power = (p2["team"]["eff_ovr"] ** 1.3) * (1 + p2["team"]["chem"] / 100.0) * (1.0 + boost2)
    p1_chance_prob = max(0.20, min(0.80, p1_power / (p1_power + p2_power)))

    p1_pos = int(max(35, min(65, p1_chance_prob * 100)))
    p2_pos = 100 - p1_pos

    stats = {
        "p1_shots": 0, "p2_shots": 0,
        "p1_saves": 0, "p2_saves": 0,
        "scorers": [],
        "motm_points": Counter(),
        "red_cards": []
    }
    momentum = {"p1": 0.0, "p2": 0.0}

    def execute_chance(minute_label, extra_boost=0.0):
        attacker, defender = (p1, p2) if random.random() < p1_chance_prob else (p2, p1)
        att_key = "p1" if attacker == p1 else "p2"
        boost = momentum[att_key] + extra_boost

        g, s, a, txt, on_target, red = simulate_chained_fc26_attack(attacker, defender, minute_label, boost)

        if on_target:
            if attacker == p1: stats["p1_shots"] += 1
            else: stats["p2_shots"] += 1
        if g:
            attacker["score"] += 1
            stats["scorers"].append(f"⚽️ {s} ({attacker['name']})")
            stats["motm_points"][s] += 3
            if a: stats["motm_points"][a] += 2
            opp_key = "p2" if att_key == "p1" else "p1"
            momentum[opp_key] += 0.08
            momentum[att_key] = 0.0
        else:
            if on_target:
                if attacker == p1: stats["p2_saves"] += 1
                else: stats["p1_saves"] += 1
        if red:
            stats["red_cards"].append(f"🟥 اخراج مدافع {defender['name']}")
            defender["team"]["def_ovr"] = max(40, defender["team"].get("def_ovr", 75) - 15)
        return txt

    try:
        analysis_line = f"\n📋 <b>آنالیز تاکتیکی هوش مصنوعی:</b>\n{tactical_notes[0]}\n" if tactical_notes else ""

        await asyncio.sleep(15)
        txt_1a = execute_chance("۱۶")
        txt_1b = execute_chance("۲۴")
        t1 = (
            f"⏱ <b>دقیقه ۲۵ مسابقه:</b>\n"
            f"▫️ <b>{p1['name']} [{p1['score']}] - [{p2['score']}] {p2['name']}</b>\n"
            f"{analysis_line}"
            "────────────────────\n"
            f"{txt_1a}\n\n{txt_1b}"
        )
        await safe_edit_message(context.bot, t1, chat_id=chat_id, message_id=msg_id)

        await asyncio.sleep(15)
        txt_2a = execute_chance("۳۵")
        txt_2b = execute_chance("۴۴")
        t2 = (
            f"⏱ <b>پایان نیمه اول (دقیقه ۴۵):</b>\n"
            f"▫️ <b>{p1['name']} [{p1['score']}] - [{p2['score']}] {p2['name']}</b>\n"
            "────────────────────\n"
            f"{txt_2a}\n\n{txt_2b}"
        )
        await safe_edit_message(context.bot, t2, chat_id=chat_id, message_id=msg_id)

        await asyncio.sleep(15)
        txt_3a = execute_chance("۶۲")
        txt_3b = execute_chance("۷۱")
        t3 = (
            f"⏱ <b>دقیقه ۷۰ مسابقه:</b>\n"
            f"▫️ <b>{p1['name']} [{p1['score']}] - [{p2['score']}] {p2['name']}</b>\n"
            "────────────────────\n"
            f"{txt_3a}\n\n{txt_3b}"
        )
        await safe_edit_message(context.bot, t3, chat_id=chat_id, message_id=msg_id)

        await asyncio.sleep(15)
        clutch_boost = 0.12 if abs(p1["score"] - p2["score"]) <= 1 else 0.0
        txt_4a = execute_chance("۸۶", clutch_boost)
        txt_4b = execute_chance("۹۰+۲", clutch_boost)

        motm_player = "نامشخص"
        motm_rating = "8.2"
        if stats["motm_points"]:
            motm_player, best_pts = stats["motm_points"].most_common(1)[0]
            motm_rating = f"{min(9.9, round(7.5 + (best_pts * 0.4), 1))}"
        else:
            motm_player = random.choice(p1["team"]["cards"] + p2["team"]["cards"])["name"]
            motm_rating = "8.0"

        s1, s2, stake = p1["score"], p2["score"], m["stake"]
        res_footer = ""
        winner_id = None

        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            if s1 > s2:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake * 2, p1["id"]))
                winner_id = p1["id"]
                res_footer = f"🏆 <b>پیروز مسابقه: {html.escape(p1['name'])}</b> (+{stake} امتیاز خالص و +100 XP)"
            elif s2 > s1:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake * 2, p2["id"]))
                winner_id = p2["id"]
                res_footer = f"🏆 <b>پیروز مسابقه: {html.escape(p2['name'])}</b> (+{stake} امتیاز خالص و +100 XP)"
            else:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id IN (?, ?)", (stake, p1["id"], p2["id"]))
                res_footer = "🤝 مسابقه با تساوی به پایان رسید! مبلغ شرط به هر دو بازیکن بازگردانده شد."
            await db.commit()

        if winner_id:
            await profile_add_xp(winner_id, 100)

        await record_quest_action(p1["id"], "card_matches")
        await record_quest_action(p2["id"], "card_matches")

        scorers_str = "\n".join(stats["scorers"]) if stats["scorers"] else "بدون گل"
        red_str = f"\n⚠️ رویداد انضباطی: {', '.join(stats['red_cards'])}" if stats["red_cards"] else ""

        t_final = (
            f"🏁 <b>سوت پایان مسابقه کارت‌های FC 26 (Full Time)</b>\n"
            "────────────────────\n"
            f"▫️ نتیجه قطعی: <b>{p1['name']} [{s1}] - [{s2}] {p2['name']}</b>\n\n"
            f"{txt_4a}\n\n{txt_4b}{red_str}\n\n"
            f"⚽️ <b>گلزنان مسابقه:</b>\n{scorers_str}\n\n"
            "📊 <b>آمار رسمی بازی (Match Stats):</b>\n"
            f"▫️ مالکیت توپ: <code>{p1_pos}%</code> ✕ <code>{p2_pos}%</code>\n"
            f"▫️ شوت در چارچوب: <code>{stats['p1_shots']}</code> ✕ <code>{stats['p2_shots']}</code>\n"
            f"▫️ سیو دروازه‌بان: <code>{stats['p1_saves']}</code> ✕ <code>{stats['p2_saves']}</code>\n\n"
            f"🌟 <b>بهترین بازیکن زمین (MOTM):</b>\n"
            f"👤 <b>{motm_player}</b> (⭐️ نمره <code>{motm_rating}/10</code>)\n"
            "────────────────────\n"
            f"{res_footer}"
        )
        await safe_edit_message(context.bot, t_final, chat_id=chat_id, message_id=msg_id)

    except Exception as e:
        logger.error(f"Error in deep card match simulation: {e}")
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id IN (?, ?)", (m["stake"], p1["id"], p2["id"]))
            await db.commit()
        await safe_edit_message(context.bot, "❌ خطایی در جریان شبیه‌سازی مسابقه کارت رخ داد (مبلغ شرط بازگردانده شد).", chat_id=chat_id, message_id=msg_id)
    finally:
        ACTIVE_CARD_MATCHES.pop(m_id, None)

# --- FC LEAGUE ENGINE ---

async def league_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT season_id FROM league_seasons WHERE status = 'ACTIVE' ORDER BY created_at DESC LIMIT 1") as cur:
            row = await cur.fetchone()
            if not row:
                msg = "⏳ <b>در حال حاضر هیچ لیگ فعالی برگزار نمی‌شود.</b>"
                if update.callback_query:
                    await safe_edit_message(update.callback_query, msg, reply_markup=kb.get_back_button())
                else:
                    await update.message.reply_text(msg, parse_mode="HTML")
                return
            s_id = row[0]

        async with db.execute("""
            SELECT u.first_name, s.played, s.won, s.drawn, s.lost, s.gf, s.ga, s.gd, s.points
            FROM league_standings s
            JOIN users u ON s.user_id = u.user_id
            WHERE s.season_id = ?
            ORDER BY s.points DESC, s.gd DESC, s.gf DESC
        """, (s_id,)) as cur:
            table_rows = await cur.fetchall()

    text = "🏆 <b>جدول رده‌بندی لیگ کارت‌های FC 26</b>\n────────────────────\n<pre>"
    text += "#  | Team          | P  | W  | D  | L  | GD | Pts\n---+---------------+----+----+----+----+----+----\n"
    for idx, (name, p, w, d, l, gf, ga, gd, pts) in enumerate(table_rows, 1):
        t_name = name[:13].ljust(13)
        text += f"{idx:<2} | {t_name} | {str(p):<2} | {str(w):<2} | {str(d):<2} | {str(l):<2} | {str(gd):<2} | {str(pts):<3}\n"
    text += "</pre>\n💰 <b>پاداش هر بازی:</b> برد <code>+50 PTS</code> | مساوی <code>+20 PTS</code> | هر گل <code>+5 PTS</code>\n"
    text += "🎁 <b>جوایز نهایی:</b>\n🥇 اول: <b>5,000 PTS + 1000 XP</b>\n🥈 دوم: <b>3,000 PTS + 750 XP</b>\n🥉 سوم: <b>1,500 PTS + 500 XP</b>"

    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
    else:
        await update.message.reply_text(text, parse_mode="HTML")

async def league_on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT season_id FROM league_seasons WHERE status = 'ACTIVE'") as cur:
            if await cur.fetchone():
                await update.message.reply_text("⚠️ یک لیگ هم‌اکنون فعال است! ابتدا با /l_off یا /l_end آن را به پایان برسانید.")
                return

        async with db.execute("""
            SELECT user_id FROM user_cards WHERE is_in_lineup = 1 GROUP BY user_id HAVING COUNT(*) >= 1
        """) as cur:
            eligible = [r[0] for r in await cur.fetchall()]

    if len(eligible) < 3:
        await update.message.reply_text(f"⛔️ تعداد تیم‌های آماده ({len(eligible)}) کمتر از حد نصاب است! حداقل به ۳ تیم نیاز است.")
        return

    season_id = f"L_{get_iran_now().strftime('%Y%m%d_%H%M')}"
    today_str = get_iran_now().strftime("%Y-%m-%d %H:%M")

    fixtures = []
    for h in eligible:
        for a in eligible:
            if h != a:
                fixtures.append((season_id, h, a))

    random.shuffle(fixtures)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("INSERT INTO league_seasons (season_id, status, created_at) VALUES (?, 'ACTIVE', ?)", (season_id, today_str))
        for s_id, h_id, a_id in fixtures:
            await db.execute("INSERT INTO league_fixtures (season_id, home_id, away_id, status) VALUES (?, ?, ?, 'PENDING')", (s_id, h_id, a_id))
        for uid in eligible:
            await db.execute("INSERT INTO league_standings (season_id, user_id) VALUES (?, ?)", (season_id, uid))
        await db.commit()

    total_m = len(fixtures)
    msg = (
        f"🏆🔥 <b>سوت آغاز فصل جدید لیگ کارت‌های FC 26 زده شد!</b>\n────────────────────\n"
        f"👥 تعداد تیم‌های حاضر: <b>{len(eligible)} تیم</b>\n"
        f"🏟 مجموع مسابقات رفت و برگشت: <b>{total_m} مسابقه</b>\n"
        f"⏰ برنامه: <b>روزی ۲ مسابقه برای هر تیم</b>\n"
        f"💰 پاداش هر بازی: <b>برد +50 | مساوی +20 | هر گل +5 PTS</b>\n\n"
        f"🎁 <b>جوایز ویژه پایان فصل:</b>\n"
        f"🥇 قهرمان: <b>۵,۰۰۰ امتیاز + ۱,۰۰۰ XP</b>\n"
        f"🥈 نایب‌قهرمان: <b>۳,۰۰۰ امتیاز + ۷۵۰ XP</b>\n"
        f"🥉 مقام سوم: <b>۱,۵۰۰ امتیاز + ۵۰۰ XP</b>"
    )
    target_chat_id = await get_live_chat_id()
    if target_chat_id:
        await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")
    await update.message.reply_text("✅ لیگ با موفقیت استارت خورد!", parse_mode="HTML")

async def league_off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("UPDATE league_seasons SET status = 'CANCELLED' WHERE status = 'ACTIVE'")
        await db.commit()
    await update.message.reply_text("🔴 لیگ فعال فعلی لغو و متوقف شد.")

async def settle_league_season(context: ContextTypes.DEFAULT_TYPE, db, s_id: str):
    """تسویه حساب نهایی لیگ با جوایز تعیین شده و اهدای پک‌های انبار بدون قفل شدن دیتابیس"""
    async with db.execute("""
        SELECT s.user_id, u.first_name, s.points, s.gd
        FROM league_standings s JOIN users u ON s.user_id = u.user_id
        WHERE s.season_id = ? ORDER BY s.points DESC, s.gd DESC
    """, (s_id,)) as cur:
        final_ranks = await cur.fetchall()

    if final_ranks:
        prizes = {
            0: (5000, 1000, "league_p1"),
            1: (3000, 750, "league_p2"),
            2: (1500, 500, "league_p3")
        }
        summary = "🏁 <b>پایان رسمی فصل لیگ کارت‌های FC 26 و اهدای جوایز + پک‌های انبار!</b>\n────────────────────\n"
        xp_awards = []
        for idx, (uid, name, pts, gd) in enumerate(final_ranks):
            p_pts, p_xp, p_pack = prizes.get(idx, (300, 150, "league_part"))
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (p_pts, uid))
            await add_pack_to_inventory(uid, p_pack, count=1, db=db)
            xp_awards.append((uid, p_xp))
            medal = "🥇" if idx == 0 else ("🥈" if idx == 1 else ("🥉" if idx == 2 else f"#{idx+1}"))
            summary += f"{medal} <b>{html.escape(name)}</b>: {pts} امتیاز (تفاضل {gd:+d}) ➔ 💰 <b>+{p_pts:,} PTS</b> + 📦 <b>{PACK_DEFINITIONS[p_pack]['title']}</b>\n"

        await db.execute("UPDATE league_seasons SET status = 'FINISHED' WHERE season_id = ?", (s_id,))
        await db.commit()

        for uid, p_xp in xp_awards:
            await profile_add_xp(uid, p_xp)

        target_chat_id = await get_live_chat_id()
        if target_chat_id:
            try:
                await context.bot.send_message(chat_id=target_chat_id, text=summary, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error sending settle summary: {e}")

async def simulate_daily_league_task(context: ContextTypes.DEFAULT_TYPE, reply_chat_id: int = None):
    iran_now = get_iran_now()
    today_str = iran_now.strftime("%Y-%m-%d")

    try:
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            async with db.execute("SELECT season_id FROM league_seasons WHERE status = 'ACTIVE' LIMIT 1") as cur:
                row = await cur.fetchone()
                if not row:
                    if reply_chat_id:
                        await context.bot.send_message(chat_id=reply_chat_id, text="⚠️ هیچ لیگی در وضعیت فعال (ACTIVE) پیدا نشد.")
                    return
                s_id = row[0]

            setting_key = f"last_league_run_{s_id}"
            async with db.execute("SELECT value FROM bot_settings WHERE key = ?", (setting_key,)) as cur:
                last_run_row = await cur.fetchone()
                last_run_date = last_run_row[0] if last_run_row else None

            if last_run_date == today_str and not reply_chat_id:
                return

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
            if reply_chat_id:
                await context.bot.send_message(chat_id=reply_chat_id, text="🏁 تمام بازی‌های این فصل انجام شده و فصل به پایان رسید.")
            return

        team_games = Counter()
        selected_matches = []
        remaining = list(pending_matches)

        while True:
            candidates = [f for f in remaining if team_games[f[1]] < 2 and team_games[f[2]] < 2]
            if not candidates:
                break
            candidates.sort(key=lambda f: (team_games[f[1]] + team_games[f[2]]))
            best = candidates[0]
            selected_matches.append(best)
            team_games[best[1]] += 1
            team_games[best[2]] += 1
            remaining.remove(best)

        if not selected_matches:
            if reply_chat_id:
                await context.bot.send_message(chat_id=reply_chat_id, text="⚠️ مسابقه‌ای با شرایط برگزاری روزانه پیدا نشد.")
            return

        all_uids = set()
        for _, h_id, a_id in selected_matches:
            all_uids.add(h_id)
            all_uids.add(a_id)

        teams_data = {}
        tactics_data = {}
        for uid in all_uids:
            teams_data[uid] = await get_user_team_info(uid)
            tactics_data[uid] = await get_user_tactics(uid)

        user_names = {}
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            for uid in all_uids:
                async with db.execute("SELECT first_name FROM users WHERE user_id = ?", (uid,)) as cur:
                    r = await cur.fetchone()
                    user_names[uid] = r[0] if r and r[0] else f"تیم {uid}"

        now_time = iran_now.strftime("%Y-%m-%d %H:%M")
        match_results = []
        match_updates = []

        for f_id, h_id, a_id in selected_matches:
            t1 = teams_data[h_id]
            t2 = teams_data[a_id]
            tac1 = tactics_data[h_id]
            tac2 = tactics_data[a_id]

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

            match_results.append((user_names[h_id], s1, s2, user_names[a_id], reward_h, reward_a))
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

            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (setting_key, today_str))
            await db.commit()

            async with db.execute("""
                SELECT COUNT(*) FROM league_fixtures 
                WHERE season_id = ? AND (status = 'PENDING' OR status IS NULL OR status = '')
            """, (s_id,)) as cur:
                rem_cnt = (await cur.fetchone())[0]
            if rem_cnt == 0:
                await settle_league_season(context, db, s_id)

        report_lines = [
            "🏆⚽️ <b>نتایج مسابقات لیگ کارت‌های FC 26 (۲ مسابقه برای هر تیم):</b>",
            "────────────────────"
        ]
        for h_name, s1, s2, a_name, r_h, r_a in match_results:
            report_lines.append(
                f"▫️ <b>{html.escape(h_name)}</b> (<code>+{r_h}</code>) <b>[{s1}] - [{s2}]</b> (<code>+{r_a}</code>) <b>{html.escape(a_name)}</b>"
            )
        report_lines.append("────────────────────")
        report_lines.append("💰 <i>پاداش‌ها (برد +50، مساوی +20، هر گل +5) واریز شد | جدول: <code>/league</code></i>")
        report_msg = "\n".join(report_lines)

        target_chat_id = await get_live_chat_id()
        if target_chat_id:
            try:
                await context.bot.send_message(chat_id=target_chat_id, text=report_msg, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error sending league results to group: {e}")

        if reply_chat_id and reply_chat_id != target_chat_id:
            try:
                await context.bot.send_message(chat_id=reply_chat_id, text=report_msg, parse_mode="HTML")
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Fatal error in simulate_daily_league_task: {e}", exc_info=True)

# --- TRIVIA DUELS ---

async def trigger_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    if not update.message or not update.message.reply_to_message:
        await update.effective_message.reply_text("⚔️ روی پیام حریف ریپلای کنید و بنویسید: <code>دوئل</code>", parse_mode="HTML")
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
        await update.effective_message.reply_text(f"⛔️ هر دو بازیکن باید حداقل <b>{stake} PTS</b> داشته باشند.", parse_mode="HTML")
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
        [
            InlineKeyboardButton("⚔️ قبول چالش دوئل", callback_data=f"acd_{duel_id}"),
            InlineKeyboardButton("❌ رد چالش", callback_data=f"rjd_{duel_id}")
        ]
    ])
    c_name, o_name = html.escape(challenger.first_name), html.escape(opponent.first_name)
    text = f"⚔️ <b>میدان دوئل اطلاعات عمومی!</b> 🔥\n{c_name} 🆚 {o_name}\nجایزه: <b>+{stake} امتیاز</b> | زمان هر سوال: <b>۱۵ ثانیه</b>\nآیا می‌پذیری؟"
    sent_msg = await update.effective_message.reply_text(text, reply_markup=duel_kb, parse_mode="HTML")
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
    if not update.message or not update.message.reply_to_message:
        await update.effective_message.reply_text("⚔️ برای بتل ۲ به ۲، روی پیام حریف ریپلای کن و بنویس:\n<code>بتل</code>", parse_mode="HTML")
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
        await update.effective_message.reply_text(f"⛔️ هر بازیکن باید حداقل <b>{stake} PTS</b> داشته باشد.", parse_mode="HTML")
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
        [
            InlineKeyboardButton("➕ یار تیم ۱", callback_data=f"bt1_{duel_id}"),
            InlineKeyboardButton("➕ یار تیم ۲", callback_data=f"bt2_{duel_id}")
        ],
        [InlineKeyboardButton("❌ لغو بتل", callback_data=f"r2d_{duel_id}")]
    ])
    text = render_team_duel_lobby(ACTIVE_TEAM_DUELS[duel_id])
    sent = await update.effective_message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")
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
        # ==================== CHAMPIONS LEAGUE (UCL) ENGINE ====================

async def champions_league_status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش وضعیت چمپیونزلیگ با دستور (چمپ)"""
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT season_id, stage, status FROM ucl_tournaments WHERE status = 'ACTIVE' LIMIT 1") as cur:
            row = await cur.fetchone()

        if not row:
            msg = "🏆 <b>در حال حاضر هیچ تورنمنت چمپیونزلیگی فعال نیست!</b>\nبا دستور <code>/cp_on</code> توسط ادمین فعال می‌شود."
            if update.callback_query:
                await safe_edit_message(update.callback_query, msg, reply_markup=kb.get_back_button())
            else:
                await update.message.reply_text(msg, parse_mode="HTML")
            return

        s_id, stage, status = row

        if stage == "GROUP":
            async with db.execute("""
                SELECT g.group_name, u.first_name, g.played, g.won, g.drawn, g.lost, g.gd, g.points
                FROM ucl_group_standings g JOIN users u ON g.user_id = u.user_id
                WHERE g.season_id = ? ORDER BY g.group_name ASC, g.points DESC, g.gd DESC
            """, (s_id,)) as cur:
                all_standings = await cur.fetchall()

            groups = {}
            for g_name, u_name, p, w, d, l, gd, pts in all_standings:
                groups.setdefault(g_name, []).append((u_name, p, w, d, l, gd, pts))

            text = "🏆⭐️ <b>لیگ قهرمانان اروپا (UEFA Champions League)</b>\n────────────────────\n📍 وضعیت: <b>مرحله گروهی</b>\n\n"
            for grp, teams in sorted(groups.items()):
                text += f"🔹 <b>گروه {grp}:</b>\n<pre>"
                text += "# | Team        | P | W | D | L | GD| Pts\n--+-------------+---+---+---+---+---+---\n"
                for idx, (t_name, p, w, d, l, gd, pts) in enumerate(teams, 1):
                    t_str = t_name[:11].ljust(11)
                    text += f"{idx:<1} | {t_str} | {p:<1} | {w:<1} | {d:<1} | {l:<1} |{gd:+2} | {pts:<2}\n"
                text += "</pre>\n"
            text += "✨ <i>۲ تیم برتر هر گروه راهی مرحله حذفی می‌شوند!</i>"
        else:
            async with db.execute("""
                SELECT f.round_name, u1.first_name, f.home_score, f.away_score, u2.first_name, f.status
                FROM ucl_knockout_fixtures f
                JOIN users u1 ON f.home_id = u1.user_id
                JOIN users u2 ON f.away_id = u2.user_id
                WHERE f.season_id = ? ORDER BY f.id ASC
            """, (s_id,)) as cur:
                fixtures = await cur.fetchall()

            text = f"🏆⭐️ <b>مرحله حذفی لیگ قهرمانان اروپا ({stage})</b>\n────────────────────\n\n"
            for r_name, h_name, hs, as_, a_name, f_status in fixtures:
                status_str = f"<b>[{hs} - {as_}]</b> 🏁" if f_status == "FINISHED" else "<b>[Vs]</b> ⏳"
                text += f"▫️ <b>{r_name}:</b>\n    {h_name} {status_str} {a_name}\n\n"

    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
    else:
        await update.message.reply_text(text, parse_mode="HTML")

async def cp_on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT season_id FROM ucl_tournaments WHERE status = 'ACTIVE'") as cur:
            if await cur.fetchone():
                await update.message.reply_text("⚠️ یک دوره چمپیونزلیگ در جریان است! با /cp_off یا /cp_end مدیریت کنید.")
                return

        async with db.execute("SELECT user_id FROM user_cards WHERE is_in_lineup = 1 GROUP BY user_id HAVING COUNT(*) >= 1") as cur:
            eligible = [r[0] for r in await cur.fetchall()]

    if len(eligible) < 4:
        await update.message.reply_text(f"⛔️ تعداد تیم‌ها کافی نیست (حداقل ۴ تیم، موجود: {len(eligible)}).")
        return

    random.shuffle(eligible)
    num_groups = 4 if len(eligible) >= 8 else 2
    groups_dict = {chr(65 + i): [] for i in range(num_groups)}
    for idx, uid in enumerate(eligible):
        groups_dict[chr(65 + (idx % num_groups))].append(uid)

    s_id = f"UCL_{get_iran_now().strftime('%Y%m%d_%H%M')}"
    now_str = get_iran_now().strftime("%Y-%m-%d %H:%M")
    fixtures = []

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("INSERT INTO ucl_tournaments (season_id, stage, status, created_at) VALUES (?, 'GROUP', 'ACTIVE', ?)", (s_id, now_str))
        for grp, uids in groups_dict.items():
            for uid in uids:
                await db.execute("INSERT INTO ucl_group_standings (season_id, group_name, user_id) VALUES (?, ?, ?)", (s_id, grp, uid))
            for h in uids:
                for a in uids:
                    if h != a:
                        fixtures.append((s_id, grp, h, a))

        random.shuffle(fixtures)
        for s_code, grp, h, a in fixtures:
            await db.execute("INSERT INTO ucl_group_fixtures (season_id, group_name, home_id, away_id, status) VALUES (?, ?, ?, ?, 'PENDING')", (s_code, grp, h, a))
        await db.commit()

    msg = (
        f"🏆⭐️🔥 <b>آغاز فصل جدید لیگ قهرمانان اروپا (UCL)!</b>\n"
        "────────────────────\n"
        f"👥 تیم‌های حاضر: <b>{len(eligible)} تیم</b> در <b>{num_groups} گروه</b>\n"
        f"🥇 قهرمان: <b>۲۰,۰۰۰ PTS + ۳ سوپر پک UCL</b>\n"
        f"🥈 نایب‌قهرمان: <b>۱۰,۰۰۰ PTS + ۳ اولتیمیت پک UCL</b>\n"
        f"▫️ هر برد گروهی: <b>+150 PTS</b> | مساوی: <b>+60 PTS</b>\n"
        f"▫️ صعود از گروه: <b>+1,000 PTS</b> | برد حذفی: <b>+2,000 PTS</b>\n"
        "────────────────────\nوضعیت مسابقات با نوشتن کلمه: <b>چمپ</b>"
    )
    target_chat_id = await get_live_chat_id()
    if target_chat_id:
        await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")
    await update.message.reply_text("✅ چمپیونزلیگ آغاز گردید!", parse_mode="HTML")

async def cp_off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("UPDATE ucl_tournaments SET status = 'CANCELLED' WHERE status = 'ACTIVE'")
        await db.commit()
    await update.message.reply_text("🔴 چمپیونزلیگ متوقف و لغو شد.")

async def cp_play_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT season_id, stage FROM ucl_tournaments WHERE status = 'ACTIVE' LIMIT 1") as cur:
            row = await cur.fetchone()
        if not row:
            await update.message.reply_text("⚠️ هیچ تورنمنت چمپیونزلیگ فعالی پیدا نشد!")
            return
        s_id, stage = row

    if stage == "GROUP":
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT id, group_name, home_id, away_id FROM ucl_group_fixtures WHERE season_id = ? AND status = 'PENDING' LIMIT 4", (s_id,)) as cur:
                matches = await cur.fetchall()

        if not matches:
            await update.message.reply_text("🏁 مسابقات گروهی تمام شده، دستور /cp_end را ارسال کنید.")
            return

        report = ["⭐️⚽️ <b>نتایج دور مسابقات گروهی چمپیونزلیگ:</b>\n────────────────────"]
        for f_id, grp, h_id, a_id in matches:
            t1, t2 = await get_user_team_info(h_id), await get_user_team_info(a_id)
            p1_prob = max(0.20, min(0.80, (t1["eff_ovr"]**1.3) / ((t1["eff_ovr"]**1.3) + (t2["eff_ovr"]**1.3))))
            s1, s2 = 0, 0
            for _ in range(random.randint(5, 7)):
                if random.random() < p1_prob: s1 += 1
                else: s2 += 1

            w1, d1, l1, pts1 = (1, 0, 0, 3) if s1 > s2 else ((0, 1, 0, 1) if s1 == s2 else (0, 0, 1, 0))
            w2, d2, l2, pts2 = (1, 0, 0, 3) if s2 > s1 else ((0, 1, 0, 1) if s1 == s2 else (0, 0, 1, 0))
            rew_h = 150 if s1 > s2 else (60 if s1 == s2 else 0)
            rew_a = 150 if s2 > s1 else (60 if s1 == s2 else 0)

            async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                await db.execute("UPDATE ucl_group_fixtures SET home_score = ?, away_score = ?, status = 'FINISHED' WHERE id = ?", (s1, s2, f_id))
                await db.execute("UPDATE ucl_group_standings SET played = played + 1, won = won + ?, drawn = drawn + ?, lost = lost + ?, gf = gf + ?, ga = ga + ?, gd = gd + ?, points = points + ? WHERE season_id = ? AND user_id = ?", (w1, d1, l1, s1, s2, s1 - s2, pts1, s_id, h_id))
                await db.execute("UPDATE ucl_group_standings SET played = played + 1, won = won + ?, drawn = drawn + ?, lost = lost + ?, gf = gf + ?, ga = ga + ?, gd = gd + ?, points = points + ? WHERE season_id = ? AND user_id = ?", (w2, d2, l2, s2, s1, s2 - s1, pts2, s_id, a_id))
                if rew_h: await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (rew_h, h_id))
                if rew_a: await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (rew_a, a_id))
                await db.commit()
                async with db.execute("SELECT first_name FROM users WHERE user_id = ?", (h_id,)) as cur: h_name = (await cur.fetchone())[0]
                async with db.execute("SELECT first_name FROM users WHERE user_id = ?", (a_id,)) as cur: a_name = (await cur.fetchone())[0]
            report.append(f"▫️ گروه {grp}: <b>{h_name}</b> [{s1} - {s2}] <b>{a_name}</b>")

        target_chat_id = await get_live_chat_id() or update.effective_chat.id
        await context.bot.send_message(chat_id=target_chat_id, text="\n".join(report), parse_mode="HTML")
    else:
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT id, round_name, home_id, away_id FROM ucl_knockout_fixtures WHERE season_id = ? AND status = 'PENDING'", (s_id,)) as cur:
                fixtures = await cur.fetchall()

        if not fixtures:
            await update.message.reply_text("🏁 مسابقات این مرحله برگزار شده است. با /cp_end مرحله را تعیین تکلیف کنید.")
            return

        report = ["🔥⭐️ <b>نتایج مسابقات حذفی لیگ قهرمانان:</b>\n────────────────────"]
        for f_id, r_name, h_id, a_id in fixtures:
            t1, t2 = await get_user_team_info(h_id), await get_user_team_info(a_id)
            p1_prob = max(0.20, min(0.80, (t1["eff_ovr"]**1.3) / ((t1["eff_ovr"]**1.3) + (t2["eff_ovr"]**1.3))))
            s1, s2 = 0, 0
            for _ in range(random.randint(6, 8)):
                if random.random() < p1_prob: s1 += 1
                else: s2 += 1
            if s1 == s2:
                if random.random() < 0.5: s1 += 1
                else: s2 += 1

            win_id = h_id if s1 > s2 else a_id
            async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                await db.execute("UPDATE ucl_knockout_fixtures SET home_score = ?, away_score = ?, winner_id = ?, status = 'FINISHED' WHERE id = ?", (s1, s2, win_id, f_id))
                await db.execute("UPDATE users SET points = points + 2000 WHERE user_id = ?", (win_id,))
                await db.commit()
                async with db.execute("SELECT first_name FROM users WHERE user_id = ?", (h_id,)) as cur: h_name = (await cur.fetchone())[0]
                async with db.execute("SELECT first_name FROM users WHERE user_id = ?", (a_id,)) as cur: a_name = (await cur.fetchone())[0]
            report.append(f"▫️ <b>{r_name}:</b> {h_name} [{s1} - {s2}] {a_name} ➔ برنده: <b>{h_name if win_id == h_id else a_name}</b> (+2,000 PTS)")

        target_chat_id = await get_live_chat_id() or update.effective_chat.id
        await context.bot.send_message(chat_id=target_chat_id, text="\n".join(report), parse_mode="HTML")

async def cp_end_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT season_id, stage FROM ucl_tournaments WHERE status = 'ACTIVE' LIMIT 1") as cur:
            row = await cur.fetchone()
        if not row: return
        s_id, stage = row

    if stage == "GROUP":
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT group_name, user_id FROM ucl_group_standings WHERE season_id = ? ORDER BY group_name ASC, points DESC, gd DESC", (s_id,)) as cur:
                rows = await cur.fetchall()

        groups = {}
        for grp, uid in rows:
            groups.setdefault(grp, []).append(uid)

        qualified = []
        for grp, uids in groups.items():
            top2 = uids[:2]
            qualified.extend(top2)
            for q_id in top2:
                async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                    await db.execute("UPDATE users SET points = points + 1000 WHERE user_id = ?", (q_id,))
                    await db.commit()

        next_stage = "SEMIFINAL" if len(qualified) == 4 else ("FINAL" if len(qualified) == 2 else "KNOCKOUT")
        r_name = "نیمه‌نهایی" if next_stage == "SEMIFINAL" else ("فینال بزرگ" if next_stage == "FINAL" else "حذفی")
        random.shuffle(qualified)

        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("UPDATE ucl_tournaments SET stage = ? WHERE season_id = ?", (next_stage, s_id))
            for i in range(0, len(qualified), 2):
                if i + 1 < len(qualified):
                    await db.execute("INSERT INTO ucl_knockout_fixtures (season_id, round_name, home_id, away_id, status) VALUES (?, ?, ?, ?, 'PENDING')", (s_id, r_name, qualified[i], qualified[i+1]))
            await db.commit()

        target_chat_id = await get_live_chat_id() or update.effective_chat.id
        await context.bot.send_message(chat_id=target_chat_id, text=f"🏁 <b>مرحله گروهی UCL بسته شد!</b>\nپاداش صعود (+1,000 PTS) واریز شد.\nقرعه‌کشی مرحله <b>{r_name}</b> انجام شد.", parse_mode="HTML")

    elif stage in ["KNOCKOUT", "SEMIFINAL"]:
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT winner_id FROM ucl_knockout_fixtures WHERE season_id = ? AND status = 'FINISHED'", (s_id,)) as cur:
                winners = [r[0] for r in await cur.fetchall()]

        if len(winners) == 2:
            async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                await db.execute("UPDATE ucl_tournaments SET stage = 'FINAL' WHERE season_id = ?", (s_id,))
                await db.execute("INSERT INTO ucl_knockout_fixtures (season_id, round_name, home_id, away_id, status) VALUES (?, 'فینال بزرگ', ?, ?, 'PENDING')", (s_id, winners[0], winners[1]))
                await db.commit()
            target_chat_id = await get_live_chat_id() or update.effective_chat.id
            await context.bot.send_message(chat_id=target_chat_id, text="🔥 <b>فینالیست‌های لیگ قهرمانان مشخص شدند!</b> با /cp_play فینال را اجرا کنید.", parse_mode="HTML")

    elif stage == "FINAL":
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT home_id, away_id, winner_id FROM ucl_knockout_fixtures WHERE season_id = ? AND round_name LIKE '%فینال%' AND status = 'FINISHED'", (s_id,)) as cur:
                fin_row = await cur.fetchone()
        if not fin_row: return
        h_id, a_id, champ_id = fin_row
        runner_id = a_id if champ_id == h_id else h_id

        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("UPDATE users SET points = points + 20000 WHERE user_id = ?", (champ_id,))
            await db.execute("UPDATE users SET points = points + 10000 WHERE user_id = ?", (runner_id,))
            await db.execute("UPDATE ucl_tournaments SET status = 'FINISHED' WHERE season_id = ?", (s_id,))
            await db.commit()
            async with db.execute("SELECT first_name FROM users WHERE user_id = ?", (champ_id,)) as cur: champ_name = (await cur.fetchone())[0]
            async with db.execute("SELECT first_name FROM users WHERE user_id = ?", (runner_id,)) as cur: runner_name = (await cur.fetchone())[0]

        await add_pack_to_inventory(champ_id, "ucl_super", count=3)
        await add_pack_to_inventory(runner_id, "ucl_elite", count=3)

        msg = (
            f"👑🏆⭐️ <b>پایان رسمی لیگ قهرمانان اروپا و اهدای جوایز!</b>\n────────────────────\n"
            f"🥇 <b>قهرمان: {html.escape(champ_name)}</b> ➔ 💰 <b>+20,000 PTS</b> + 🎁 <b>۳ سوپر پک UCL</b>\n"
            f"🥈 <b>نایب‌قهرمان: {html.escape(runner_name)}</b> ➔ 💰 <b>+10,000 PTS</b> + 🎁 <b>۳ اولتیمیت پک UCL</b>\n"
            "────────────────────\n🎒 <i>پک‌ها در انبار مارکت کاربران ذخیره شد و در هر زمان قابل بازگشایی هستند!</i>"
        )
        target_chat_id = await get_live_chat_id() or update.effective_chat.id
        await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")

# ==================== ترنسفر مارکت ====================

async def transfer_market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await clean_expired_transfers()
    user = update.effective_user
    await ensure_user(user)

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("""
            SELECT tm.id, tm.seller_id, u.first_name, tm.player_name, tm.rating, tm.position, tm.rarity, tm.price
            FROM transfer_market tm JOIN users u ON tm.seller_id = u.user_id
            WHERE tm.status = 'ACTIVE' ORDER BY tm.created_at DESC
        """) as cur:
            listings = await cur.fetchall()
        async with db.execute("SELECT points FROM users WHERE user_id = ?", (user.id,)) as cur:
            user_pts = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM transfer_market WHERE seller_id = ? AND status = 'EXPIRED'", (user.id,)) as cur:
            expired_count = (await cur.fetchone())[0]

    text = f"🔄 <b>ترنسفر مارکت P2P</b>\n────────────────────\n💰 موجودی: <b>{user_pts:,} PTS</b> | مالیات: <b>۵٪</b> | اعتبار: <b>۲۴ ساعت</b>\n────────────────────\n"
    buttons = []
    if expired_count > 0:
        buttons.append([InlineKeyboardButton(f"📥 دریافت کارت‌های منقضی ({expired_count})", callback_data="tm_reclaim_all")])

    if not listings:
        text += "▫️ در حال حاضر بازیکنی لیست نشده است."
    else:
        for t_id, s_id, s_name, name, ovr, pos, rar, price in listings[:8]:
            tag = RARITY_COLORS.get(rar, rar)
            badge = " [شما]" if s_id == user.id else f" ({s_name[:10]})"
            text += f"▫️ <b>{name}</b> ({pos}) ➔ <b>{ovr} OVR</b> {tag}{badge}\n    └ 💰 {price:,} PTS\n\n"
            if s_id == user.id:
                buttons.append([InlineKeyboardButton(f"❌ لغو {name} ({ovr})", callback_data=f"tm_cancel_{t_id}")])
            else:
                buttons.append([InlineKeyboardButton(f"🛒 خرید {name} ({ovr}) - {price:,} PTS", callback_data=f"tm_buy_{t_id}")])

    buttons.append([InlineKeyboardButton("➕ فروش بازیکن در ترنسفر", callback_data="tm_open_sell"), InlineKeyboardButton("‹ بازگشت", callback_data="home")])
    kb_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)
    else:
        await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

# --- CALLBACK ROUTER ---

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query: return
    data = query.data
    user = query.from_user
    uid = user.id
    await ensure_user(user)

    if data == "home":
        await query.answer()
        await start(update, context)
    elif data == "open_transfer_market":
        await query.answer()
        await transfer_market_cmd(update, context)
    elif data == "open_inventory_packs":
        await query.answer()
        packs = await get_user_inventory_packs(uid)
        if not packs:
            await query.answer("انبار پک‌های شما خالی است!", show_alert=True)
            return
        text = "🎒 <b>انبار پک‌های اهدایی لیگ و UCL شما:</b>\n────────────────────\n"
        buttons = []
        for p_type, cnt in packs:
            cfg = PACK_DEFINITIONS.get(p_type, PACK_DEFINITIONS["league_part"])
            text += f"▫️ <b>{cfg['title']}</b>: <code>{cnt} عدد</code> موجود\n"
            buttons.append([InlineKeyboardButton(f"🎁 باز کردن {cfg['title']}", callback_data=f"open_pack_{p_type}")])
        buttons.append([InlineKeyboardButton("‹ بازگشت به مارکت", callback_data="view_market")])
        await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(buttons))
    elif data.startswith("open_pack_"):
        p_type = data.replace("open_pack_", "")
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT count FROM user_inventory_packs WHERE user_id = ? AND pack_type = ?", (uid, p_type)) as cur:
                row = await cur.fetchone()
            if not row or row[0] <= 0:
                await query.answer("این پک در انبار موجود نیست!", show_alert=True)
                return
            await db.execute("UPDATE user_inventory_packs SET count = count - 1 WHERE user_id = ? AND pack_type = ?", (uid, p_type))
            c = unpack_inventory_card(p_type)
            today_str = get_iran_now().strftime("%Y-%m-%d")
            await db.execute("INSERT INTO user_cards (user_id, player_name, rating, position, rarity, acquired_at) VALUES (?, ?, ?, ?, ?, ?)", (uid, c["name"], c["ovr"], c["pos"], c["rarity"], today_str))
            await db.commit()
        await profile_add_xp(uid, 60)
        tag = RARITY_COLORS.get(c["rarity"], c["rarity"])
        res_txt = f"🎉 <b>کارت جدید شما:</b>\n⭐️ <b>{c['name']}</b> ({c['pos']}) ➔ <b>{c['ovr']} OVR</b>\n    └ {tag}\nبه کلکسیون اضافه شد!"
        await safe_edit_message(query, res_txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎒 انبار پک‌ها", callback_data="open_inventory_packs")], [InlineKeyboardButton("🛡 ترکیب تیم", callback_data="view_lineup")]]))
    elif data == "tm_open_sell":
        await query.answer()
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT id, player_name, rating, position, rarity FROM user_cards WHERE user_id = ? AND is_in_lineup = 0 ORDER BY rating DESC", (uid,)) as cur:
                cards = await cur.fetchall()
        if not cards:
            await query.answer("کارت مازادی برای فروش ندارید!", show_alert=True)
            return
        buttons = []
        for cid, name, ovr, pos, rar in cards[:10]:
            min_p = get_card_min_transfer_price(ovr, rar)
            buttons.append([InlineKeyboardButton(f"{name} ({ovr}) - کف: {min_p:,}", callback_data=f"tm_sellcard_{cid}")])
        buttons.append([InlineKeyboardButton("‹ انصراف", callback_data="open_transfer_market")])
        await safe_edit_message(query, "📋 بازیکن مورد نظر را برای فروش انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data.startswith("tm_sellcard_"):
        cid = int(data.replace("tm_sellcard_", ""))
        USER_TRANSFER_SELL_DRAFT[uid] = cid
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT player_name, rating, rarity FROM user_cards WHERE id = ?", (cid,)) as cur:
                p_name, ovr, rar = await cur.fetchone()
        min_p = get_card_min_transfer_price(ovr, rar)
        await safe_edit_message(query, f"💰 فروش {p_name} ({ovr} OVR)\nکف قیمت مجاز: <b>{min_p:,} PTS</b>\nقیمت پیشنهادی را در چت تایپ کن (مثلا: 2000):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("‹ انصراف", callback_data="open_transfer_market")]]))
    elif data.startswith("tm_buy_"):
        t_id = int(data.replace("tm_buy_", ""))
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT seller_id, player_name, rating, position, rarity, price FROM transfer_market WHERE id = ? AND status = 'ACTIVE'", (t_id,)) as cur:
                row = await cur.fetchone()
            if not row or row[0] == uid:
                await query.answer("خرید غیرمجاز یا کارت نامعتبر است!", show_alert=True)
                return
            s_id, p_name, ovr, pos, rar, price = row
            async with db.execute("SELECT points FROM users WHERE user_id = ?", (uid,)) as cur:
                buyer_pts = (await cur.fetchone())[0]
            if buyer_pts < price:
                await query.answer("موجودی ناکافی!", show_alert=True)
                return
            tax = int(price * 0.05)
            await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (price, uid))
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (price - tax, s_id))
            await db.execute("UPDATE transfer_market SET status = 'SOLD' WHERE id = ?", (t_id,))
            today_str = get_iran_now().strftime("%Y-%m-%d")
            await db.execute("INSERT INTO user_cards (user_id, player_name, rating, position, rarity, acquired_at) VALUES (?, ?, ?, ?, ?, ?)", (uid, p_name, ovr, pos, rar, today_str))
            await db.commit()
        await query.answer("✅ کارت با موفقیت خریداری شد!", show_alert=True)
        await transfer_market_cmd(update, context)
    elif data.startswith("tm_cancel_"):
        t_id = int(data.replace("tm_cancel_", ""))
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT seller_id, player_name, rating, position, rarity FROM transfer_market WHERE id = ? AND status = 'ACTIVE'", (t_id,)) as cur:
                row = await cur.fetchone()
            if row and row[0] == uid:
                _, p_name, ovr, pos, rar = row
                await db.execute("UPDATE transfer_market SET status = 'CANCELLED' WHERE id = ?", (t_id,))
                today_str = get_iran_now().strftime("%Y-%m-%d")
                await db.execute("INSERT INTO user_cards (user_id, player_name, rating, position, rarity, acquired_at) VALUES (?, ?, ?, ?, ?, ?)", (uid, p_name, ovr, pos, rar, today_str))
                await db.commit()
        await transfer_market_cmd(update, context)
    elif data == "tm_reclaim_all":
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT id, player_name, rating, position, rarity FROM transfer_market WHERE seller_id = ? AND status = 'EXPIRED'", (uid,)) as cur:
                expired = await cur.fetchall()
            today_str = get_iran_now().strftime("%Y-%m-%d")
            for tid, p_name, ovr, pos, rar in expired:
                await db.execute("UPDATE transfer_market SET status = 'RECLAIMED' WHERE id = ?", (tid,))
                await db.execute("INSERT INTO user_cards (user_id, player_name, rating, position, rarity, acquired_at) VALUES (?, ?, ?, ?, ?, ?)", (uid, p_name, ovr, pos, rar, today_str))
            await db.commit()
        await query.answer(f"✅ تعداد {len(expired)} کارت به ترکیب بازگردانده شد.")
        await transfer_market_cmd(update, context)
    elif data == "view_market":
        await query.answer()
        await market_cmd(update, context)
    elif data == "open_sell_menu":
        await query.answer()
        await sell_menu_cmd(update, context)
    elif data == "view_my_cards":
        await query.answer()
        await my_cards_cmd(update, context)
    elif data == "view_lineup":
        await query.answer()
        await lineup_cmd(update, context)
    elif data == "auto_lineup":
        await auto_lineup_logic(uid)
        await query.answer("⚡️ ترکیب به طور خودکار چیده شد!")
        await lineup_cmd(update, context)
    elif data == "claim_daily_pack":
        await query.answer()
        await daily_pack_cmd(update, context)
    elif data == "claim_quests":
        today_str = get_iran_now().strftime("%Y-%m-%d")
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute(
                "SELECT penalties_played, card_matches_played, predictions_made, is_claimed FROM daily_quests WHERE user_id = ? AND date_str = ?",
                (uid, today_str)
            ) as cur:
                row = await cur.fetchone()
            if row and (row[0] >= 2 and row[1] >= 1 and row[2] >= 1) and not row[3]:
                await db.execute("UPDATE daily_quests SET is_claimed = 1 WHERE user_id = ? AND date_str = ?", (uid, today_str))
                await db.execute("UPDATE users SET points = points + 120 WHERE user_id = ?", (uid,))
                await db.commit()
                await profile_add_xp(uid, 50)
                await query.answer("🎉 پاداش ۱۲۰ امتیازی و ۵۰ XP با موفقیت واریز شد!", show_alert=True)
                await quests_cmd(update, context)
            else:
                await query.answer("هنوز تمام ماموریت‌ها کامل نشده یا قبلاً دریافت کرده‌اید!", show_alert=True)

    elif data.startswith("buy_m_"):
        idx = int(data.replace("buy_m_", ""))
        today_str = get_iran_now().strftime("%Y-%m-%d")
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT offers_json FROM daily_market WHERE user_id = ? AND date_str = ?", (uid, today_str)) as cur:
                r = await cur.fetchone()
                if not r:
                    await query.answer("مارکت منقضی شده!", show_alert=True)
                    return
                offers = json.loads(r[0])

            if idx >= len(offers) or offers[idx]["bought"]:
                await query.answer("این کارت قبلاً خریداری شده است!", show_alert=True)
                return

            item = offers[idx]
            price = item["price"]
            c = item["card"]

            async with db.execute("SELECT points FROM users WHERE user_id = ?", (uid,)) as cur:
                pts = (await cur.fetchone())[0]

            if pts < price:
                await query.answer(f"موجودی کافی نیست! قیمت: {price:,} PTS", show_alert=True)
                return

            item["bought"] = True
            await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (price, uid))
            await db.execute(
                "INSERT INTO user_cards (user_id, player_name, rating, position, rarity, acquired_at) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, c["name"], c["ovr"], c["pos"], c["rarity"], today_str)
            )
            await db.execute(
                "UPDATE daily_market SET offers_json = ? WHERE user_id = ? AND date_str = ?",
                (json.dumps(offers, ensure_ascii=False), uid, today_str)
            )
            await db.commit()

        await profile_add_xp(uid, 40)
        await query.answer(f"✅ کارت {c['name']} با موفقیت خریداری شد!")
        await market_cmd(update, context)

    # --- خرید پک‌ها: اصلاح شده برای دادن دقیقا ۱ کارت و شرایط ریتینگ خواسته شده ---
    elif data in ["buy_pack_gold", "buy_pack_ultimate", "buy_pack_super"]:
        pack_cfg = {
            "buy_pack_gold": {"price": 500, "name": "📦 گلد پک"},
            "buy_pack_ultimate": {"price": 1500, "name": "🔥 اولتیمیت پک (بالای ۸۰)"},
            "buy_pack_super": {"price": 4000, "name": "👑 سوپر پک ویژه (بالای ۸۵)"}
        }[data]

        cost = pack_cfg["price"]
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT points FROM users WHERE user_id = ?", (uid,)) as cur:
                user_pts = (await cur.fetchone())[0]

            if user_pts < cost:
                await query.answer("موجودی شما کافی نیست!", show_alert=True)
                return

            # طبق خواسته: دقیقا ۱ بازیکن به کاربر داده می‌شود
            c = generate_card_for_pack(data)
            today_str = get_iran_now().strftime("%Y-%m-%d")

            await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (cost, uid))
            await db.execute(
                "INSERT INTO user_cards (user_id, player_name, rating, position, rarity, acquired_at) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, c["name"], c["ovr"], c["pos"], c["rarity"], today_str)
            )
            await db.commit()

        await profile_add_xp(uid, 50)
        rarity_label = RARITY_COLORS.get(c["rarity"], c["rarity"])
        card_desc = f"⭐ <b>{c['name']}</b> ({c['pos']}) ➔ <b>{c['ovr']} OVR</b>\n    └ {c.get('nation','')} | {c.get('club','')} | {rarity_label}"

        msg = (
            f"🎉 <b>{pack_cfg['name']} باز شد!</b>\n────────────────────\n"
            f"{card_desc}\n"
            f"────────────────────\nمبلغ {cost:,} PTS کسر شد و بازیکن به کلکسیون شما اضافه گردید!"
        )
        await safe_edit_message(query, msg, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 بازگشت به مارکت", callback_data="view_market")],
            [InlineKeyboardButton("🛡 مشاهده ترکیب", callback_data="view_lineup")]
        ]))

    elif data.startswith("sell_c_"):
        cid = int(data.replace("sell_c_", ""))
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT player_name, rarity, is_in_lineup FROM user_cards WHERE id = ? AND user_id = ?", (cid, uid)) as cur:
                row = await cur.fetchone()
            if not row:
                await query.answer("کارت پیدا نشد!", show_alert=True)
                return
            name, rar, in_lineup = row
            price = SELL_PRICES.get(rar, 50)
            await db.execute("DELETE FROM user_cards WHERE id = ?", (cid,))
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (price, uid))
            await db.commit()

        await query.answer(f"💰 کارت {name} به قیمت +{price} PTS فروخته شد!")
        await sell_menu_cmd(update, context)

    elif data.startswith("ac_cm_"):
        m_id = data.replace("ac_cm_", "")
        m = ACTIVE_CARD_MATCHES.get(m_id)
        if not m:
            await query.answer("مسابقه منقضی شده است!", show_alert=True)
            return
        if uid != m["p2"]["id"]:
            await query.answer("تنها حریف به چالش کشیده شده می‌تواند بپذیرد!", show_alert=True)
            return
        if m.get("accepted"):
            await query.answer()
            return
        m["accepted"] = True
        stake = m["stake"]
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("UPDATE users SET points = points - ? WHERE user_id IN (?, ?)", (stake, m["p1"]["id"], m["p2"]["id"]))
            await db.commit()
        await query.answer("⚔️ مسابقه آغاز شد!")
        asyncio.create_task(run_live_card_match_simulation(context, m_id))

    elif data.startswith("rj_cm_"):
        m_id = data.replace("rj_cm_", "")
        m = ACTIVE_CARD_MATCHES.get(m_id)
        if m and (uid in [m["p1"]["id"], m["p2"]["id"]]):
            ACTIVE_CARD_MATCHES.pop(m_id, None)
            await query.answer()
            await safe_edit_message(query, "❌ مسابقه کارت‌ها لغو گردید.")
        else:
            await query.answer()

    elif data.startswith("acp_"):
        p_id = data.replace("acp_", "")
        shot_data = ACTIVE_SHOOTOUTS.get(p_id)
        if not shot_data:
            await query.answer("چالش پنالتی منقضی شده است!", show_alert=True)
            return
        if uid != shot_data["p2"]["id"]:
            await query.answer("فقط حریف می‌تواند بپذیرد!", show_alert=True)
            return
        if shot_data.get("accepted"):
            await query.answer()
            return
        shot_data["accepted"] = True
        stake = shot_data["stake"]
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("UPDATE users SET points = points - ? WHERE user_id IN (?, ?)", (stake, shot_data["p1"]["id"], shot_data["p2"]["id"]))
            await db.commit()
        await increment_penalty_count_db(shot_data["p1"]["id"])
        await increment_penalty_count_db(shot_data["p2"]["id"])
        await query.answer("🧤 پنالتی پذیرفته شد!")

        p1_name = html.escape(shot_data["p1"]["name"])
        text = f"🥅 <b>نوبت ضربه پنالتی {p1_name}!</b> ⚽️\nجهت شوت زدن روی دکمه زیر کلیک کنید:"
        kb_shot = InlineKeyboardMarkup([[InlineKeyboardButton("⚽️ شلیک ضربه پنالتی", callback_data=f"shoot_pen_{p_id}")]])
        await safe_edit_message(query, text, reply_markup=kb_shot)

    elif data.startswith("rjp_"):
        p_id = data.replace("rjp_", "")
        shot_data = ACTIVE_SHOOTOUTS.get(p_id)
        if shot_data and (uid in [shot_data["p1"]["id"], shot_data["p2"]["id"]]):
            ACTIVE_SHOOTOUTS.pop(p_id, None)
            await query.answer()
            await safe_edit_message(query, "❌ دوئل پنالتی لغو شد.")
        else:
            await query.answer()

    elif data.startswith("shoot_pen_"):
        p_id = data.replace("shoot_pen_", "")
        shot_data = ACTIVE_SHOOTOUTS.get(p_id)
        if not shot_data:
            await query.answer("پنالتی منقضی شده!", show_alert=True)
            return
        turn_id = shot_data["current_turn"]
        if uid != turn_id:
            await query.answer("نوبت شما نیست!", show_alert=True)
            return
        await query.answer()
        dice_roll = random.randint(1, 6)
        is_goal = dice_roll in [3, 4, 5]
        shooter_key = "p1" if uid == shot_data["p1"]["id"] else "p2"
        shot_data[shooter_key]["shot"] = is_goal

        if shooter_key == "p1":
            shot_data["current_turn"] = shot_data["p2"]["id"]
            p2_name = html.escape(shot_data["p2"]["name"])
            g_txt = "⚽️ گل شد!" if is_goal else "🧤 مهار شد / به اوت رفت!"
            text = (
                f"نتیجه ضربه {html.escape(shot_data['p1']['name'])}: <b>{g_txt}</b>\n\n"
                f"🥅 اکنون نوبت ضربه پنالتی <b>{p2_name}</b> است!"
            )
            kb_shot = InlineKeyboardMarkup([[InlineKeyboardButton("⚽️ شلیک ضربه پنالتی", callback_data=f"shoot_pen_{p_id}")]])
            await safe_edit_message(query, text, reply_markup=kb_shot)
        else:
            g1 = shot_data["p1"]["shot"]
            g2 = shot_data["p2"]["shot"]
            stake = shot_data["stake"]
            p1_name = html.escape(shot_data["p1"]["name"])
            p2_name = html.escape(shot_data["p2"]["name"])
            p1_id = shot_data["p1"]["id"]
            p2_id = shot_data["p2"]["id"]

            t1 = "⚽️ گل" if g1 else "❌ از دست رفت"
            t2 = "⚽️ گل" if g2 else "❌ از دست رفت"

            if g1 and not g2:
                async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake * 2, p1_id))
                    await db.commit()
                await profile_record_penalty_win(p1_id)
                res = f"🏆 <b>پیروز دوئل پنالتی: {p1_name}</b> (+{stake} PTS)"
            elif g2 and not g1:
                async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake * 2, p2_id))
                    await db.commit()
                await profile_record_penalty_win(p2_id)
                res = f"🏆 <b>پیروز دوئل پنالتی: {p2_name}</b> (+{stake} PTS)"
            else:
                async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                    await db.execute("UPDATE users SET points = points + ? WHERE user_id IN (?, ?)", (stake, p1_id, p2_id))
                    await db.commit()
                res = "🤝 هر دو پنالتی مشابه ثبت شد؛ مساوی و برگشت امتیازات!"

            final_text = (
                f"🏁 <b>نتیجه نهایی ضربات پنالتی:</b>\n"
                f"▫️ {p1_name}: {t1}\n"
                f"▫️ {p2_name}: {t2}\n\n"
                f"{res}"
            )
            ACTIVE_SHOOTOUTS.pop(p_id, None)
            await safe_edit_message(query, final_text)

    elif data.startswith("ans_dbl_"):
        parts = data.split("_")
        g_id, opt_idx = f"{parts[2]}_{parts[3]}", int(parts[4])
        game = ACTIVE_DOUBLE_GAMES.get(g_id)
        if not game or not game.get("is_active"):
            await query.answer("این چالش منقضی شده است!", show_alert=True)
            return
        if uid != game["user_id"]:
            await query.answer("این چالش برای شما نیست!", show_alert=True)
            return

        game["is_active"] = False
        cancel_timer(context, f"timer_dbl_{g_id}")
        selected_opt = game["options"][opt_idx]
        is_correct = (selected_opt == game["correct"])
        stake = game["stake"]

        if is_correct:
            win_amount = stake * 2
            async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (win_amount, uid))
                await db.commit()
            await profile_add_xp(uid, 80)
            msg = f"🔥🎉 <b>پاسخ کاملاً صحیح!</b>\nپاسخ درست: <b>{game['correct']}</b>\n💰 سود شما: <b>+{stake:,} PTS</b> خالص و <b>+80 XP</b>!"
        else:
            msg = f"💀❌ <b>پاسخ اشتباه!</b>\nگزینه درست: <b>{game['correct']}</b> بود.\nمبلغ <b>{stake:,} PTS</b> از دست رفت!"

        ACTIVE_DOUBLE_GAMES.pop(g_id, None)
        await safe_edit_message(query, msg, reply_markup=None)

    elif data.startswith("acd_"):
        duel_id = data.replace("acd_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if not duel:
            await query.answer("دوئل منقضی شده است!", show_alert=True)
            return
        if uid != duel["opponent"]["id"]:
            await query.answer("تنها حریف می‌تواند دوئل را قبول کند!", show_alert=True)
            return
        if duel.get("accepted"):
            await query.answer()
            return
        duel["accepted"] = True
        stake = duel["stake"]
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            await db.execute("UPDATE users SET points = points - ? WHERE user_id IN (?, ?)", (stake, duel["challenger"]["id"], duel["opponent"]["id"]))
            await db.commit()
        await query.answer("⚔️ دوئل آغاز شد!")
        await proceed_duel(context, duel_id)

    elif data.startswith("rjd_"):
        duel_id = data.replace("rjd_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if duel and (uid in [duel["challenger"]["id"], duel["opponent"]["id"]]):
            ACTIVE_DUELS.pop(duel_id, None)
            await query.answer()
            await safe_edit_message(query, "❌ چالش دوئل لغو شد.")
        else:
            await query.answer()

    elif data.startswith("pool_"):
        parts = data.split("_")
        m_id, choice = parts[1], parts[2]
        user = query.from_user
        await ensure_user(user)

        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT id FROM special_pool_predictions WHERE user_id = ? AND match_id = ?", (uid, m_id)) as cur:
                if await cur.fetchone():
                    await query.answer("شما قبلاً در استخر این مسابقه شرکت کرده‌اید!", show_alert=True)
                    return
            await db.execute(
                "INSERT INTO special_pool_predictions (user_id, user_name, match_id, choice, settled) VALUES (?, ?, ?, ?, 0)",
                (uid, user.first_name, m_id, choice)
            )
            await db.commit()

        await query.answer("✅ پیش‌بینی شما در استخر ۵۰۰ امتیازی ثبت شد!", show_alert=True)
        m_data = MATCH_CACHE.get(m_id)
        if m_data:
            async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
                async with db.execute("SELECT user_name, choice FROM special_pool_predictions WHERE match_id = ?", (m_id,)) as cur:
                    participants = [(r[0], r[1]) for r in await cur.fetchall()]
            new_text = await generate_pool_message_text(m_data, participants)
            await safe_edit_message(query, new_text, reply_markup=query.message.reply_markup)

    elif data.startswith("pred_"):
        parts = data.split("_")
        m_id, choice = parts[1], parts[2]
        m_data = MATCH_CACHE.get(m_id)
        if not is_match_still_open_for_prediction(m_data):
            await query.answer("مهلت پیش‌بینی این بازی به پایان رسیده است!", show_alert=True)
            return

        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT id FROM predictions WHERE user_id = ? AND match_id = ?", (uid, m_id)) as cur:
                if await cur.fetchone():
                    await query.answer("شما قبلاً این بازی را پیش‌بینی کرده‌اید!", show_alert=True)
                    return
            await db.execute(
                "INSERT INTO predictions (user_id, match_id, outcome_choice, settled) VALUES (?, ?, ?, 0)",
                (uid, m_id, choice)
            )
            await db.execute("UPDATE users SET points = points + 10 WHERE user_id = ?", (uid,))
            await db.commit()

        await record_quest_action(uid, "predictions")
        await profile_add_xp(uid, 15)
        choice_label = "برد میزبان" if choice == "HOME" else ("تساوی" if choice == "DRAW" else "برد میهمان")
        await query.answer(f"✅ پیش‌بینی شما ({choice_label}) ثبت شد (+10 PTS)!", show_alert=True)

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
        text = f"⚙️ <b>انتخاب بازیکن برای پست {pos} (حداکثر {limit} بازیکن):</b>"

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
                        await query.answer("⚠️ این بازیکن قبلاً در خط هافبک است!", show_alert=True)
                        return
                    if len(active_mids) >= 2:
                        await db.execute("UPDATE user_cards SET is_in_lineup = 0 WHERE id = ?", (active_mids[0][0],))
                    await db.execute("UPDATE user_cards SET is_in_lineup = 1 WHERE id = ?", (cid,))
                    await db.commit()
                    await query.answer(f"✅ {p_name} به هافبک اضافه شد!")
                query.data = "manual_pos_MID"
                await callback_router(update, context)

    # --- تاکتیک‌ها ---
    elif data == "open_tactics":
        await query.answer()
        await tactics_menu_cmd(update, context)

    elif data == "set_tac_step1":
        await query.answer()
        kb_s = InlineKeyboardMarkup([
            [InlineKeyboardButton("🪄 تیکی‌تاکا و مالکیت توپ", callback_data="save_tac_style_TIKI_TAKA")],
            [InlineKeyboardButton("⚡️ گگن‌پرسینگ (پرس وحشتناک)", callback_data="save_tac_style_GEGENPRESS")],
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
            [InlineKeyboardButton("🔵 دفاع عقب‌کشیده و عمیق", callback_data="save_tac_depth_DEEP")],
            [InlineKeyboardButton("‹ بازگشت به تاکتیک", callback_data="open_tactics")]
        ])
        await safe_edit_message(query, "🛡 <b>ارتفاع و عمق استقرار مدافعان:</b>", reply_markup=kb_d)

    elif data == "set_tac_step3":
        await query.answer()
        kb_b = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 پاس‌های تک‌ضرب و کوتاه", callback_data="save_tac_buildup_SHORT")],
            [InlineKeyboardButton("✈️ پاس‌های بلند و ارسال قطری", callback_data="save_tac_buildup_LONG")],
            [InlineKeyboardButton("‹ بازگشت به تاکتیک", callback_data="open_tactics")]
        ])
        await safe_edit_message(query, "📐 <b>نحوه انتقال توپ به حمله:</b>", reply_markup=kb_b)

    elif data == "set_tac_step4":
        await query.answer()
        kb_r = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔥 انتحاری و هجوم همه‌جانبه", callback_data="save_tac_risk_ALL_OUT")],
            [InlineKeyboardButton("⚖️ منظم و ریسک کنترل‌شده", callback_data="save_tac_risk_BALANCED")],
            [InlineKeyboardButton("‹ بازگشت به تاکتیک", callback_data="open_tactics")]
        ])
        await safe_edit_message(query, "⚖️ <b>سطح ریسک بازیکنان در مسابقه:</b>", reply_markup=kb_r)

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
            text += "🎴 قربانی‌های لازم: <b>۲ کارت ICON + ۳ کارت ELITE مازاد</b>\n"
        else:
            text += f"🎴 قربانی‌های لازم: <b>{plan['sac_count']} کارت {plan['sac_rarity']} مازاد</b>\n"

        text += "────────────────────\n👇 بازیکن مورد نظر را برای شروع ارتقا انتخاب کنید:\n"

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
            f"💰 هزینه: <b>{plan['cost']:,} PTS</b> (موجودی: {user_pts:,})\n"
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
    elif data == "spin_wheel":
        await query.answer()
        await spin_wheel_cmd(update, context)
    elif data == "jackpot_hub":
        await query.answer()
        await jackpot_cmd(update, context)

# --- GROUP TEXT MESSAGE HANDLER ---

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.text: return
    raw_text = update.effective_message.text.strip()
    msg = normalize_persian_numbers(raw_text).lower()
    chat_id = update.effective_chat.id
    user = update.effective_user
    uid = user.id if user else None

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
            await update.effective_message.reply_text(f"🎉🔥 <b>پاسخ صحیح!</b> 👤 {game['names'][0]} | 🏆 برنده: <b>{html.escape(winner.first_name)}</b> (+{reward} PTS)", parse_mode="HTML")
            return

    # ثبت قیمت ترنسفر مارکت
    if uid in USER_TRANSFER_SELL_DRAFT and msg.isdigit():
        price = int(msg)
        cid = USER_TRANSFER_SELL_DRAFT.pop(uid)
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute("SELECT player_name, rating, position, rarity FROM user_cards WHERE id = ? AND user_id = ?", (cid, uid)) as cur:
                card = await cur.fetchone()
            if card:
                p_name, ovr, pos, rar = card
                min_p = get_card_min_transfer_price(ovr, rar)
                if price < min_p:
                    await update.effective_message.reply_text(f"⛔️ حداقل قیمت قانونی: <b>{min_p:,} PTS</b> است!", parse_mode="HTML")
                    return
                now = get_iran_now()
                exp = now + timedelta(hours=24)
                await db.execute("DELETE FROM user_cards WHERE id = ?", (cid,))
                await db.execute("""
                    INSERT INTO transfer_market (seller_id, player_name, rating, position, rarity, price, expires_at, created_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
                """, (uid, p_name, ovr, pos, rar, price, exp.strftime("%Y-%m-%d %H:%M"), now.strftime("%Y-%m-%d %H:%M")))
                await db.commit()
                await update.effective_message.reply_text(f"✅ کارت <b>{p_name} ({ovr})</b> با موفقیت به قیمت <b>{price:,} PTS</b> در ترنسفر مارکت قرار گرفت (مهلت ۲۴ ساعت).", parse_mode="HTML")
                return

    # پاسخ به کلمات کلیدی چمپ و ترنسفر
    if msg in ["چمپ", "champions", "چمپیونزلیگ", "ucl"]:
        await champions_league_status_cmd(update, context)
        return
    elif msg in ["ترنسفر", "transfer", "ترانسفر"]:
        await transfer_market_cmd(update, context)
        return

    if msg in ["اطلاعات", "info", "پروفایل", "stats"] or msg.startswith(("/info", "اطلاعات")):
        target_user = update.effective_user
        if update.effective_message.reply_to_message: target_user = update.effective_message.reply_to_message.from_user
        await user_profile_handler(update.effective_message, target_user=target_user)
        return

    # شناسایی قطعی و هوشمند کلمات و عبارات کلیدی
    if re.match(r"^\s*(?:دوبل|دابل|قمار|ریسک|double)\s+(\d+)\s*$", msg):
        await double_or_nothing_cmd(update, context)
    elif msg in ["مسابقه کارت", "مسابقه کارتها", "کارت مچ", "کارت بازی", "cardmatch", "کارت"]:
        await trigger_card_match(update, context)
    elif msg in ["دوئل", "duel", "چالش"]:
        await trigger_duel(update, context)
    elif msg in ["بتل", "battle"]:
        await trigger_team_duel(update, context)
    elif msg in ["پنالتی", "پنالتی کشی", "penalty"]:
        await trigger_penalty_shootout(update, context)
    elif msg in ["تاکتیک", "tactic", "tactics", "استراتژی"]:
        await tactics_menu_cmd(update, context)
    elif msg in ["ارتقا", "ارتقاء", "evo", "upgrade", "اوولوشن"]:
        await evolution_menu_cmd(update, context)
    elif msg in ["پک روزانه", "پک رایگان", "dailypack"]:
        await daily_pack_cmd(update, context)
    elif msg in ["مارکت", "market", "فروشگاه"]:
        await market_cmd(update, context)
    elif msg in ["فروش", "فروش کارت", "sell"]:
        await sell_menu_cmd(update, context)
    elif msg in ["کارتها", "کارت های من", "کارتهای من", "mycards"]:
        await my_cards_cmd(update, context)
    elif msg in ["ترکیب", "لاین اپ", "lineup", "تیم من"]:
        await lineup_cmd(update, context)
    elif msg in ["ماموریت", "ماموریتها", "ماموریت ها", "quests"]:
        await quests_cmd(update, context)
    elif msg in ["لیگ", "جدول لیگ", "league"]:
        await league_cmd(update, context)
    elif msg in ["شوت", "گل", "shoot"]:
        await daily_shoot_cmd(update, context)
    elif msg in ["جایزه", "روزانه", "daily"]:
        await daily_reward_cmd(update, context)
    elif msg in ["حدس", "حدس بازیکن", "guess"]:
        await start_guess_game(update, context)
    elif msg in ["گردونه", "گردونه شانس", "wheel"]:
        await spin_wheel_cmd(update, context)
    elif msg in ["جکپات", "جک‌پات", "jackpot"]:
        await jackpot_cmd(update, context)
    elif msg in ["شروع", "منو", "menu"]:
        await start(update, context)
    elif msg in ["جدول", "رنکینگ", "امتیازات", "ranking", "top"]:
        await leaderboard_cmd(update, context)

# --- APPLICATION INITIALIZATION ---

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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transfer_market (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER,
                player_name TEXT,
                rating INTEGER,
                position TEXT,
                rarity TEXT,
                price INTEGER,
                expires_at TEXT,
                created_at TEXT,
                status TEXT DEFAULT 'ACTIVE'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_inventory_packs (
                user_id INTEGER,
                pack_type TEXT,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, pack_type)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ucl_tournaments (
                season_id TEXT PRIMARY KEY,
                stage TEXT,
                status TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ucl_group_standings (
                season_id TEXT,
                group_name TEXT,
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ucl_group_fixtures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id TEXT,
                group_name TEXT,
                home_id INTEGER,
                away_id INTEGER,
                home_score INTEGER,
                away_score INTEGER,
                status TEXT DEFAULT 'PENDING'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ucl_knockout_fixtures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id TEXT,
                round_name TEXT,
                home_id INTEGER,
                away_id INTEGER,
                home_score INTEGER,
                away_score INTEGER,
                winner_id INTEGER,
                status TEXT DEFAULT 'PENDING'
            )
        """)
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
    app.add_handler(CommandHandler(["ranking", "leaderboard"], leaderboard_cmd))
    app.add_handler(CommandHandler("duel", trigger_duel))
    app.add_handler(CommandHandler("battle", trigger_team_duel))
    app.add_handler(CommandHandler("penalty", trigger_penalty_shootout))
    app.add_handler(CommandHandler(["cardmatch", "card_match"], trigger_card_match))
    app.add_handler(CommandHandler("market", market_cmd))
    app.add_handler(CommandHandler("sell", sell_menu_cmd))
    app.add_handler(CommandHandler("pack", lambda u, c: market_cmd(u, c)))
    app.add_handler(CommandHandler("dailypack", daily_pack_cmd))
    app.add_handler(CommandHandler("mycards", my_cards_cmd))
    app.add_handler(CommandHandler("lineup", lineup_cmd))
    app.add_handler(CommandHandler(["tactic", "tactics"], tactics_menu_cmd))
    app.add_handler(CommandHandler(["evo", "evolution", "upgrade"], evolution_menu_cmd))
    app.add_handler(CommandHandler("quests", quests_cmd))
    app.add_handler(CommandHandler(["double", "risk"], double_or_nothing_cmd))
    app.add_handler(CommandHandler("league", league_cmd))
    app.add_handler(CommandHandler("l_on", league_on_cmd))
    app.add_handler(CommandHandler("l_off", league_off_cmd))
    app.add_handler(CommandHandler(["pl", "Pl", "run_league"], play_league_day_cmd))
    app.add_handler(CommandHandler(["l_end", "L_end"], finish_league_instantly_cmd))
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
    app.add_handler(CommandHandler("cp_on", cp_on_cmd))
    app.add_handler(CommandHandler("cp_off", cp_off_cmd))
    app.add_handler(CommandHandler("cp_play", cp_play_cmd))
    app.add_handler(CommandHandler("cp_end", cp_end_cmd))
    app.add_handler(CommandHandler(["champions", "ucl"], champions_league_status_cmd))
    app.add_handler(CommandHandler("transfer", transfer_market_cmd))
    app.add_handler(CommandHandler("info", lambda u, c: handle_group_messages(u, c)))

    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_messages))

    logger.info("Football Hub Bot running smoothly!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
