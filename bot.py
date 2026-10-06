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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ESCOBAR_AI_ID = 999999999
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))
LRM = "\u200E"

# بارگذاری دیتای غنی بازیکنان برای چالش حدس از فایل JSON
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

# ساختارهای داده در حافظه
ACTIVE_GUESS_GAMES = {}  # chat_id -> game_data
MATCH_CACHE = {}         # match_id -> match_dict
ACTIVE_DUELS = {}        # duel_id -> duel_dict
ACTIVE_TEAM_DUELS = {}   # duel_id -> team_duel_dict
ACTIVE_SHOOTOUTS = {}    # shootout_id -> shootout_dict
CHEAT_MODE_USERS = set() # admin user_ids with cheat on
TRACKED_LIVE_MATCHES = {}
USER_JACKPOT_DRAFTS = {} # user_id -> {"round_id": ..., "picks": {}}

LEAGUE_TITLES = {
    "eng.1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 لیگ برتر انگلیس",
    "esp.1": "🇪🇸 لالیگا اسپانیا",
    "ita.1": "🇮🇹 سری آ ایتالیا",
    "ger.1": "🇩🇪 بوندسلیگا آلمان",
    "fra.1": "🇫🇷 لوشامپیونه فرانسه",
    "uefa.champions": "🏆 لیگ قهرمانان اروپا",
    "fifa.friendly": "🌍 بازی‌های ملی و فیفادی",
    "uefa.nations": "🇪🇺 لیگ ملت‌های اروپا",
    "fifa.worldq.afc": "🌏 انتخابی جام جهانی (آسیا)",
    "fifa.worldq.uefa": "🏆 انتخابی جام جهانی (اروپا)",
    "irn.1": "🇮🇷 لیگ برتر ایران",
    "all": "🌐 گلچین معتبرترین مسابقات"
}

BANTER_TEXTS = {
    "real": [
        "⚪️ باختین کهکشانی‌های پوشالی! حتی دروازه‌بانتونم دیگه رو نداره تو صورت هوادار نگاه کنه!",
        "⚪️ ادعای پادشاهی اروپا داشتین ولی باختین، سکوت کنید لااقل!",
        "⚪️ دوباره باختین؟ وقتی می‌بازید ناله نکنید و گردن داور نندازید!"
    ],
    "barca": [
        "🔴🔵 مسخره‌ترین نمایش ممکن! حتی تیم نونهالان هم از این خط دفاع بهتر بازی می‌کنه!",
        "🔴🔵 دوباره تحقیر شدین؟ بارسا فقط ساخته شده واسه کامبک خوردن و اشک ریختن!",
        "🔴🔵 این باختتونم مثل همیشه مایه آبروریزی بود؛ حداقل تا هفته بعد یه جا قایم شین!"
    ],
    "atletico": [
        "🔴⚪️ باختین اتوبوس‌سوارها! این همه دفاع اتوبوسی آخرش به همین باخت ختم شد؟",
        "🔴⚪️ سیمئونه خودش هم دیگه از این سبک خسته‌کننده خجالت می‌کشه!"
    ],
    "liverpool": [
        "🔴 باختین مدعی‌ها! این لیگه نه جام‌های شانسکی؛ باختین و رفتین پی کارتون!",
        "🔴 دوباره باختین؟ آنفیلد شده کاروانسرا، روح کلوپ هم از این بازیتون خجالت می‌کشه!"
    ],
    "united": [
        "🔴 باختین ارواح سرگردان! اولدترافورد دیگه تئاتر رویاها نیست، قبرستان آرزوهاست!",
        "🔴 دوباره باختین؟ یونایتد فقط برای تفریح و میم شدن رقبا تو اینترنت ساخته شده!"
    ]
}

def get_iran_now():
    return datetime.now(IRAN_TZ)

def format_iran_time(dt_str: str) -> str:
    if not dt_str:
        return "نامشخص"
    try:
        clean_time = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_time)
        dt_iran = dt.astimezone(IRAN_TZ)
        return dt_iran.strftime("%H:%M")
    except Exception:
        return "نامشخص"

# سیستم ۱۲ رنک متنوع و لوکس فوتبالی
TIERS = [
    (0, "🔰", "Academy"),
    (100, "🥉", "Bronze Striker"),
    (250, "🥈", "Silver Playmaker"),
    (500, "🥇", "Gold Champion"),
    (800, "💎", "Diamond Maestro"),
    (1200, "🔮", "Elite Master"),
    (1700, "👑", "Grandmaster"),
    (2300, "⚡️", "Galactico"),
    (3000, "🏆", "Champions Icon"),
    (4000, "🌟", "Ballon d'Or Legend"),
    (5500, "🐐", "The G.O.A.T"),
    (7500, "🌌", "Football Immortal")
]

def get_user_tier(points: int):
    pts = max(0, int(points or 0))
    current_icon, current_name = TIERS[0][1], TIERS[0][2]
    for min_pts, icon, name in TIERS:
        if pts >= min_pts:
            current_icon, current_name = icon, name
        else:
            break
    return current_icon, current_name

def xp_for_next_level(level: int) -> int:
    return int(100 + (level - 1) * 60)

def calculate_level(xp: int):
    xp = max(0, int(xp or 0))
    lvl = 1
    rem = xp
    while rem >= xp_for_next_level(lvl) and lvl < 100:
        rem -= xp_for_next_level(lvl)
        lvl += 1
    needed = xp_for_next_level(lvl)
    pct = min(100, int((rem / needed) * 100)) if needed else 100
    return lvl, rem, needed, pct

def render_xp_bar(percent: int, width: int = 10) -> str:
    filled = max(0, min(width, round((percent / 100) * width)))
    empty = width - filled
    return f"{'▰' * filled}{'▱' * empty} {percent}%"

async def profile_add_xp(user_id: int, amount: int):
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET duel_wins = duel_wins + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
    await profile_add_xp(user_id, 120)

async def profile_record_penalty_win(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET penalty_wins = penalty_wins + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
    await profile_add_xp(user_id, 100)

async def profile_record_guess_win(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET guess_wins = guess_wins + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
    await profile_add_xp(user_id, 80)

def format_bidi_name(name: str) -> str:
    cleaned = (name or "بازیکن").strip()
    return f"{LRM}{html.escape(cleaned)}{LRM}"

# وب‌سرور داخلی برای زنده نگه داشتن بات در سرورهای ابری
class SimpleHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Football Hub Online! 200 OK")

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.getenv("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), SimpleHealthServer)
        logger.info(f"Health check server active on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Health server failed: {e}")

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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = 'live_chat_id'") as cur:
            row = await cur.fetchone()
            if row and row[0]:
                return int(row[0])
    return None

async def is_action_allowed_in_chat(update: Update) -> bool:
    chat = update.effective_chat
    if not chat or chat.type == "private":
        return True
    target_chat_id = await get_live_chat_id()
    if not target_chat_id or chat.id == target_chat_id:
        return True
    await update.effective_message.reply_text(
        "⛔️ <b>بخش‌های مسابقاتی و امتیازی فقط در گروه اختصاصی ربات فعال است!</b>\n"
        "▫️ سایر بخش‌ها از جمله جدول‌ها، مسابقات و نتایج برای همه باز است.",
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
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
                INSERT OR IGNORE INTO users (user_id, first_name, username, points)
                VALUES (?, ?, ?, 100)
            """, (user.id, user.first_name, user.username or ""))
            await db.execute("""
                UPDATE users SET first_name = ?, username = ? WHERE user_id = ?
            """, (user.first_name, user.username or "", user.id))
            await db.commit()
    except Exception as e:
        logger.error(f"Error in ensure_user: {e}")

async def ensure_escobar_ai():
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
                INSERT OR IGNORE INTO users (user_id, first_name, username, points)
                VALUES (?, ?, ?, 100)
            """, (ESCOBAR_AI_ID, "Escobar AI 🤖", "escobar_ai"))
            await db.commit()
    except Exception as e:
        logger.error(f"Error in ensure_escobar_ai: {e}")

async def get_penalty_count_db(user_id: int) -> int:
    today_str = get_iran_now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT penalty_date, penalty_count FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                return row[1] or 0
    return 0

async def increment_penalty_count_db(user_id: int):
    today_str = get_iran_now().strftime("%Y-%m-%d")
    cur_count = await get_penalty_count_db(user_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE users SET penalty_date = ?, penalty_count = ? WHERE user_id = ?
        """, (today_str, cur_count + 1, user_id))
        await db.commit()

async def get_guess_count_db(user_id: int) -> int:
    today_str = get_iran_now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT last_guess_date, guess_count FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                return row[1] or 0
    return 0

async def increment_guess_count_db(user_id: int):
    today_str = get_iran_now().strftime("%Y-%m-%d")
    cur_count = await get_guess_count_db(user_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE users SET last_guess_date = ?, guess_count = ? WHERE user_id = ?
        """, (today_str, cur_count + 1, user_id))
        await db.commit()

# دستورات ادمین با احراز هویت امن
async def reset_points_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID):
        await update.message.reply_text("⛔️ دسترسی غیرمجاز!")
        return
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE users SET points = 100")
            await db.commit()
        await update.message.reply_text("✅ <b>امتیاز تمامی کاربران با موفقیت روی ۱۰۰ ریست شد!</b>\nافتخارات و مدال‌ها حفظ شدند.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error resetting points: {e}")

async def set_live_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # بررسی امنیتی دسترسی ادمین
    if str(user.id) != str(ADMIN_ID):
        await update.message.reply_text("⛔️ این دستور فقط برای مالک و ادمین اصلی ربات مجاز است.")
        return

    chat = update.effective_chat
    if chat.type in ["group", "supergroup"]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('live_chat_id', ?)", (str(chat.id),))
            await db.commit()
        await update.message.reply_text(
            f"✅ <b>این گروه به عنوان گروه اختصاصی مسابقات و گزارش زنده ثبت شد!</b> 🏟🔥\n"
            f"شناسه اختصاصی: <code>{chat.id}</code>\n"
            "رویدادها، استخرها، جک‌پات و کل‌کل‌ها در همین گروه فعال شد.",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("⚠️ این دستور باید در گروه ارسال شود.")

async def generate_pool_message_text(match, participants):
    home_name = match.get("home_team", "میزبان")
    away_name = match.get("away_team", "میهمان")
    time_str = format_iran_time(match.get("date"))

    text = (
        f"🔥 <b>استخر جایزه ویژه ۳۰۰ امتیازی مسابقه بزرگ!</b> 🎁\n"
        "────────────────────\n"
        f"⚽️ <b>{home_name}</b> 🆚 <b>{away_name}</b>\n"
        f"⏰ ساعت شروع: <code>{time_str}</code> (تهران)\n"
        f"💰 جایزه کل: <b>300 امتیاز</b> (تقسیم عادلانه بین برندگان)\n"
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

# پایش زنده مسابقات، استخرها و بازی‌های فیفادی
async def monitor_live_matches_and_banter(context: ContextTypes.DEFAULT_TYPE):
    target_chat_id = await get_live_chat_id()
    if not target_chat_id:
        return

    iran_now = get_iran_now()
    today_str = iran_now.strftime("%Y%m%d")

    matches = []
    # بررسی لیگ‌های معتبر باشگاهی و ملی در فیفادی
    for l_code in ACTIVE_MONITOR_LEAGUES:
        try:
            m_list = await provider.get_matches(today_str, league_code=l_code)
            if m_list:
                matches.extend(m_list)
        except Exception as e:
            logger.debug(f"Monitor error for {l_code}: {e}")

    unique_matches = {m["id"]: m for m in matches}
    utc_now = datetime.now(timezone.utc)

    for m_id, m in unique_matches.items():
        h_name = str(m.get("home_team", ""))
        a_name = str(m.get("away_team", ""))

        home_tracked = identify_tracked_team(h_name)
        away_tracked = identify_tracked_team(a_name)

        # اگر بازی تیم‌های بزرگ باشگاهی یا بازی تیم ملی ایران باشد، پایش ویژه می‌شود
        is_iran_match = "ایران" in h_name or "ایران" in a_name
        if not home_tracked and not away_tracked and not is_iran_match:
            continue

        MATCH_CACHE[m_id] = m
        raw_status = str(m.get("status", "UPCOMING")).upper()

        try:
            h_score = int(m.get("home_score")) if m.get("home_score") is not None else None
            a_score = int(m.get("away_score")) if m.get("away_score") is not None else None
        except Exception:
            h_score, a_score = None, None

        track = TRACKED_LIVE_MATCHES.get(m_id)
        if not track:
            track = {
                "last_status": raw_status,
                "home_score": h_score if h_score is not None else 0,
                "away_score": a_score if a_score is not None else 0,
                "started_announced": False,
                "ht_announced": False,
                "second_half_announced": False,
                "pool_opened": False,
                "pool_msg_id": None,
                "banter_sent": False
            }
            TRACKED_LIVE_MATCHES[m_id] = track

        match_date_str = m.get("date")
        minutes_to_start = 9999
        if match_date_str:
            try:
                dt_match = datetime.fromisoformat(match_date_str.replace("Z", "+00:00"))
                minutes_to_start = (dt_match - utc_now).total_seconds() / 60
            except Exception:
                pass

        # باز کردن استخر ۳۰۰ امتیازی ۴۵ دقیقه قبل از بازی
        if 0 < minutes_to_start <= 45 and not track.get("pool_opened") and raw_status == "UPCOMING":
            track["pool_opened"] = True
            pool_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"⚪️ برد {h_name[:12]}", callback_data=f"pool_{m_id}_HOME"),
                    InlineKeyboardButton("🤝 تساوی", callback_data=f"pool_{m_id}_DRAW"),
                    InlineKeyboardButton(f"🔴 برد {a_name[:12]}", callback_data=f"pool_{m_id}_AWAY")
                ]
            ])
            msg_text = await generate_pool_message_text(m, [])
            try:
                sent = await context.bot.send_message(
                    chat_id=target_chat_id,
                    text=msg_text,
                    reply_markup=pool_kb,
                    parse_mode="HTML"
                )
                track["pool_msg_id"] = sent.message_id
            except Exception as e:
                logger.error(f"Error opening pool: {e}")

        # شروع مسابقه
        if raw_status == "LIVE" and not track.get("started_announced"):
            track["started_announced"] = True
            time_str = format_iran_time(m.get("date"))
            start_msg = (
                f"🚨 <b>سوت آغاز مسابقه حساس!</b> ⚽️\n"
                "────────────────────\n"
                f"🏟 <b>{h_name}</b> 🆚 <b>{a_name}</b>\n"
                f"⏰ شروع: <code>{time_str}</code> (تهران)\n"
                "▫️ استخر پیش‌بینی بسته شد. گزارش زنده آغاز گردید."
            )
            try:
                await context.bot.send_message(chat_id=target_chat_id, text=start_msg, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error sending start match: {e}")

        # تغییر نتیجه و ثبت گل
        is_live = raw_status == "LIVE"
        is_finished = raw_status == "FINISHED"
        if (is_live or is_finished) and h_score is not None and a_score is not None:
            prev_h = track["home_score"]
            prev_a = track["away_score"]
            if h_score != prev_h or a_score != prev_a:
                track["home_score"] = h_score
                track["away_score"] = a_score
                goal_msg = (
                    f"⚽️🔥 <b>تغییر در نتیجه مسابقه! (گـُــل)</b>\n"
                    "────────────────────\n"
                    f"▫️ <b>{h_name} [{h_score}] - [{a_score}] {a_name}</b>\n"
                    f"⏱ وضعیت: {raw_status}"
                )
                try:
                    await context.bot.send_message(chat_id=target_chat_id, text=goal_msg, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Error sending goal: {e}")

        # پایان بازی و تسویه استخر
        if is_finished and track["last_status"] != "FINISHED":
            track["last_status"] = "FINISHED"
            final_h = h_score if h_score is not None else track["home_score"]
            final_a = a_score if a_score is not None else track["away_score"]
            actual_outcome = "HOME" if final_h > final_a else ("AWAY" if final_a > final_h else "DRAW")

            winners_text = ""
            if track.get("pool_opened"):
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    async with db.execute("SELECT user_id, user_name FROM special_pool_predictions WHERE match_id = ? AND choice = ?", (m_id, actual_outcome)) as cur:
                        winners = await cur.fetchall()

                    if winners:
                        share = 300 // len(winners)
                        winners_text = f"\n\n🎁 <b>برندگان استخر ۳۰۰ امتیازی (هر نفر +{share} PTS):</b>\n"
                        for w_id, w_name in winners:
                            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (share, w_id))
                            winners_text += f"▫️ <b>{html.escape(w_name)}</b>\n"
                    else:
                        winners_text = "\n\n▫️ هیچ کاربری برنده نهایی را درست حدس نزد!"

                    await db.execute("UPDATE special_pool_predictions SET settled = 1 WHERE match_id = ?", (m_id,))
                    await db.commit()

            ft_msg = (
                f"🏁 <b>سوت پایان مسابقه (Full Time)</b>\n"
                "────────────────────\n"
                f"نتیجه قطعی: <b>{h_name} [{final_h}] - [{final_a}] {a_name}</b>{winners_text}"
            )
            try:
                await context.bot.send_message(chat_id=target_chat_id, text=ft_msg, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error sending FT: {e}")

            # کل‌کل خودکار برای باخت تیم‌های بزرگ
            if not track.get("banter_sent") and final_h != final_a:
                loser_key = None
                if final_h < final_a and home_tracked:
                    loser_key = home_tracked
                elif final_a < final_h and away_tracked:
                    loser_key = away_tracked

                if loser_key and loser_key in BANTER_TEXTS:
                    track["banter_sent"] = True
                    banter_msg = random.choice(BANTER_TEXTS[loser_key])
                    await asyncio.sleep(2)
                    try:
                        await context.bot.send_message(
                            chat_id=target_chat_id,
                            text=f"📢 <b>پیام ویژه کل‌کل هواداری:</b>\n{banter_msg}",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.error(f"Error sending banter: {e}")

# تسویه سیزن ماهانه و ثبت ۴ رتبه برتر
async def check_and_settle_monthly_season(context: ContextTypes.DEFAULT_TYPE):
    iran_now = get_iran_now()
    cur_month_str = iran_now.strftime("%Y-%m")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = 'last_settled_month'") as cur:
            row = await cur.fetchone()
            last_settled = row[0] if row else None

        if not last_settled:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('last_settled_month', ?)", (cur_month_str,))
            await db.commit()
            return

        if cur_month_str != last_settled:
            logger.info(f"Settling season for previous month: {last_settled}")
            async with db.execute("""
                SELECT user_id, first_name, points FROM users
                WHERE user_id != ? ORDER BY points DESC LIMIT 4
            """, (ESCOBAR_AI_ID,)) as cur:
                top4 = await cur.fetchall()

            if top4 and len(top4) >= 1:
                # ثبت مدال‌ها برای ۴ رتبه اول
                p1 = top4[0]
                await db.execute("UPDATE users SET season_gold = season_gold + 1 WHERE user_id = ?", (p1[0],))
                
                p2 = top4[1] if len(top4) >= 2 else None
                if p2:
                    await db.execute("UPDATE users SET season_silver = season_silver + 1 WHERE user_id = ?", (p2[0],))
                
                p3 = top4[2] if len(top4) >= 3 else None
                if p3:
                    await db.execute("UPDATE users SET season_bronze = season_bronze + 1 WHERE user_id = ?", (p3[0],))
                
                p4 = top4[3] if len(top4) >= 4 else None
                if p4:
                    await db.execute("UPDATE users SET season_fourth = season_fourth + 1 WHERE user_id = ?", (p4[0],))

                target_chat_id = await get_live_chat_id()
                if target_chat_id:
                    msg = (
                        f"🏆🔥 <b>پایان رسمی رقابت‌های این سیزن!</b> 🏁\n"
                        "────────────────────\n"
                        "👑 <b>تالار قهرمانان و برندگان مدال ماه:</b>\n\n"
                        f"🥇 قهرمان سیزن (رتبه ۱): <b>{html.escape(p1[1])}</b> (مدال طلا 🥇)\n"
                    )
                    if p2:
                        msg += f"🥈 نایب قهرمان (رتبه ۲): <b>{html.escape(p2[1])}</b> (مدال نقره 🥈)\n"
                    if p3:
                        msg += f"🥉 مقام سوم (رتبه ۳): <b>{html.escape(p3[1])}</b> (مدال برنز 🥉)\n"
                    if p4:
                        msg += f"🎖 مقام چهارم (رتبه ۴): <b>{html.escape(p4[1])}</b> (دیپلم افتخار 🎖)\n"

                    msg += (
                        "\n⚡️ مدال‌ها و رتبه‌های این ۴ ستاره در حساب کاربری‌شان جاودانه شد!\n"
                        "🔄 <b>امتیازات برای سیزن جدید همگی روی ۱۰۰ ریست شدند!</b>\n"
                        "رقابت برای قهرمانی سیزن جدید آغاز شد! 🔥"
                    )
                    try:
                        await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")
                    except Exception as e:
                        logger.error(f"Error sending season announcement: {e}")

                await db.execute("""
                    UPDATE users SET
                        points = 100,
                        duel_wins = 0,
                        penalty_wins = 0,
                        guess_wins = 0
                """)
                await db.execute("UPDATE bot_settings SET value = ? WHERE key = 'last_settled_month'", (cur_month_str,))
                await db.commit()

# دستور استارت و منوی اصلی
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT points, profile_level, profile_xp FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            pts = row[0] if row else 100
            lvl = row[1] if row and row[1] else 1
            xp = row[2] if row and row[2] else 0

    icon, tier = get_user_tier(pts)
    safe_name = html.escape(user.first_name)
    _, _, _, pct = calculate_level(xp)
    xp_bar = render_xp_bar(pct, width=8)

    text = (
        f"⚽️ <b>FOOTBALL HUB | پلتفرم هوشمند فوتبال</b>\n"
        f"────────────────────\n"
        f"👤 کاربر: <b>{safe_name}</b>\n"
        f"💰 موجودی: <code>{pts} PTS</code>  ▫️  سطح: {icon} <b>{tier}</b>\n"
        f"🎖 لول: <b>Level {lvl}</b> ({xp_bar})\n"
        f"────────────────────\n"
        f"به معتبرترین هاب فوتبالی تلگرام خوش آمدید! نتایج زنده، پیش‌بینی مسابقات بزرگ، جک‌پات کمبو، دوئل‌های اطلاعات عمومی و جوایز روزانه در اختیار شماست.\n\n"
        f"👇 لطفاً یکی از بخش‌های زیر را انتخاب کنید:"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb.get_main_menu())
    else:
        await update.message.reply_text(text, reply_markup=kb.get_main_menu(), parse_mode="HTML")

# نمایش لیدربورد با کنترل سقف کاراکتر
async def show_leaderboard_text(requesting_user_id: int = None) -> str:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # انتخاب حداکثر ۱۵ نفر برتر جهت جلوگیری از خطای سقف ۴۰۹۶ کاراکتر تلگرام
        async with db.execute("""
            SELECT user_id, first_name, points, duel_wins FROM users
            WHERE user_id != ? ORDER BY points DESC, duel_wins DESC LIMIT 15
        """, (ESCOBAR_AI_ID,)) as cur:
            top_list = await cur.fetchall()

    text = "🏆 <b>جدول رده‌بندی سیزن فوتبال هاب</b> 🔥\n"
    text += "────────────────────\n\n"

    if not top_list:
        text += "▫️ هنوز رکوردی ثبت نشده است.\n"
        text += "────────────────────"
        return text

    user_in_top = False
    for idx, u in enumerate(top_list, 1):
        uid, name, pts, wins = u[0], u[1], max(0, u[2]), u[3]
        if requesting_user_id and uid == requesting_user_id:
            user_in_top = True
        icon, tier = get_user_tier(pts)
        display_name = format_bidi_name(name)

        if idx == 1:
            rank_prefix = "🥇 👑"
        elif idx == 2:
            rank_prefix = "🥈 👑"
        elif idx == 3:
            rank_prefix = "🥉 👑"
        else:
            rank_prefix = f"<code>{idx:02d}.</code>"

        text += f"{rank_prefix} <b>{display_name}</b>\n"
        text += f"    └ 💰 <code>{pts} PTS</code> ▫️ رنک: {icon} {tier} ▫️ برد: <code>{wins}</code>\n\n"

    text += "────────────────────\n"
    # اگر کاربر در تاپ ۱۵ نبود، جایگاه اختصاصی او را در انتها اضافه کن
    if requesting_user_id and not user_in_top:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("""
                SELECT COUNT(*) + 1 FROM users WHERE points > (SELECT points FROM users WHERE user_id = ?)
            """, (requesting_user_id,)) as cur:
                rank_row = await cur.fetchone()
                user_rank = rank_row[0] if rank_row else "—"

            async with db.execute("SELECT points FROM users WHERE user_id = ?", (requesting_user_id,)) as cur:
                pts_row = await cur.fetchone()
                user_pts = pts_row[0] if pts_row else 0

        text += f"📍 رتبه شما: <b>#{user_rank}</b>  |  موجودی: <code>{user_pts} PTS</code>\n"

    return text

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    text = await show_leaderboard_text(user_id)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
    else:
        await update.message.reply_text(text, parse_mode="HTML")

# پروفایل کاربر با جزئیات کامل و افتخارات ۴ گانه
async def user_profile_handler(query, target_user=None):
    user = target_user or query.from_user
    user_id = user.id
    await ensure_user(user)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("""
            SELECT points, profile_xp, profile_level, profile_correct, profile_answered,
                   duel_wins, penalty_wins, guess_wins, jackpot_wins,
                   season_gold, season_silver, season_bronze, season_fourth
            FROM users WHERE user_id = ?
        """, (user_id,)) as cur:
            row = await cur.fetchone()

    if not row:
        return

    pts, xp, level, correct, answered, d_wins, p_wins, g_wins, jk_wins, gold, silver, bronze, fourth = row
    pts = max(0, pts or 0)
    level, cur_xp, needed_xp, pct = calculate_level(xp or 0)
    accuracy = round((correct / answered) * 100) if answered else 0
    icon, tier = get_user_tier(pts)
    safe_name = html.escape(user.first_name)
    bar = render_xp_bar(pct, width=10)

    # ساخت متن افتخارات فصلی
    season_text = ""
    medals_count = (gold or 0) + (silver or 0) + (bronze or 0) + (fourth or 0)
    if medals_count > 0:
        if gold:
            season_text += f"🥇 <b>{gold} بار</b> قهرمانی سیزن (رتبه ۱)\n"
        if silver:
            season_text += f"🥈 <b>{silver} بار</b> نایب قهرمانی سیزن (رتبه ۲)\n"
        if bronze:
            season_text += f"🥉 <b>{bronze} بار</b> مقام سومی سیزن (رتبه ۳)\n"
        if fourth:
            season_text += f"🎖 <b>{fourth} بار</b> مقام چهارمی سیزن (رتبه ۴)\n"
    else:
        season_text = "▫️ هنوز مدالی در پایان سیزن‌ها ثبت نشده است.\n"

    text = (
        f"┏ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ┓\n"
        f"     👤 <b>کارت شناسایی بازیکن</b>\n"
        f"┗ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ━ ┛\n"
        f"⚽️ نام: <b>{safe_name}</b>\n"
        f"🆔 شناسه: <code>{user_id}</code>\n"
        f"🏆 رنکینگ: {icon} <b>{tier}</b>\n"
        f"💰 موجودی سکه: <code>{pts} PTS</code>\n"
        f"────────────────────\n"
        f"🎖 <b>پیشرفت سطح و تجربه:</b>\n"
        f"⭐ سطح: <b>Level {level}</b>\n"
        f"📈 پیشرفت: <code>{bar}</code> ({cur_xp}/{needed_xp} XP)\n"
        f"────────────────────\n"
        f"🏆 <b>تالار افتخارات فصلی (سیزن):</b>\n"
        f"{season_text}"
        f"────────────────────\n"
        f"📊 <b>کارنامه و آمار مینی‌گیم‌ها:</b>\n"
        f"⚔️ بردهای دوئل و بتل: <b>{d_wins or 0}</b>\n"
        f"🥅 بردهای ضربات پنالتی: <b>{p_wins or 0}</b>\n"
        f"🕵️ بردهای چالش حدس بازیکن: <b>{g_wins or 0}</b>\n"
        f"🎰 بردهای جک‌پات کمبو: <b>{jk_wins or 0}</b>\n"
        f"🎯 دقت در اطلاعات عمومی: <b>{accuracy}%</b> ({correct or 0}/{answered or 0})"
    )
    if hasattr(query, "message"):
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())
    else:
        await query.reply_text(text, parse_mode="HTML")

# جوایز روزانه، شوت و گردونه شانس
async def daily_reward_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update):
        return

    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT last_daily_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                await update.effective_message.reply_text(
                    f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، پاداش روزانه امروز خود را دریافت کرده‌اید!\nامشب بعد از ساعت ۱۲ (۰۰:۰۰) پاداش فردا فعال خواهد شد.",
                    parse_mode="HTML"
                )
                return

        reward = 25
        await db.execute("UPDATE users SET points = points + ?, last_daily_date = ? WHERE user_id = ?", (reward, today_str, user.id))
        await db.commit()

    await profile_add_xp(user.id, 20)
    await update.effective_message.reply_text(
        f"🎁 <b>پاداش روزانه با موفقیت واریز شد!</b>\n"
        f"💰 <b>+{reward} امتیاز</b> و <b>+20 XP</b> به حساب شما اضافه شد.",
        parse_mode="HTML"
    )

async def daily_shoot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update):
        return

    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT last_shoot_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                await update.effective_message.reply_text(
                    f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، شوت روزانه امروز خود را زده‌اید!\nامشب بعد از ساعت ۱۲ شانس شوت فردا فعال خواهد شد.",
                    parse_mode="HTML"
                )
                return

        await db.execute("UPDATE users SET last_shoot_date = ? WHERE user_id = ?", (today_str, user.id))
        await db.commit()

    msg = await update.effective_message.reply_dice(emoji="⚽")
    dice_val = msg.dice.value

    await asyncio.sleep(2.5)

    if dice_val in [3, 4, 5]:
        reward = 20
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, user.id))
            await db.commit()
        await profile_add_xp(user.id, 25)

        await update.effective_message.reply_text(
            f"⚽️🔥 <b>گـُـل شد! ضربه غیرقابل مهار!</b>\n"
            f"💰 پاداش: <b>+{reward} امتیاز</b> و <b>+25 XP</b> دریافت کردید.",
            parse_mode="HTML"
        )
    else:
        await update.effective_message.reply_text(
            "🧤❌ <b>توپ گل نشد!</b> (مهار دیدنی دروازه‌بان یا برخورد به تیرک)\nامشب بعد از ساعت ۱۲ دوباره شانس داری.",
            parse_mode="HTML"
        )

async def spin_wheel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update):
        return

    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT last_wheel_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                await update.effective_message.reply_text(
                    f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، امروز گردونه را چرخانده‌اید!\nامشب بعد از ساعت ۱۲ شانس مجدد فعال خواهد شد.",
                    parse_mode="HTML"
                )
                return

        await db.execute("UPDATE users SET last_wheel_date = ? WHERE user_id = ?", (today_str, user.id))
        await db.commit()

    prizes = [10, 15, 25, 40, 60, 100, 0]
    weights = [30, 25, 20, 12, 8, 3, 2]
    win = random.choices(prizes, weights=weights)[0]

    async with aiosqlite.connect(DATABASE_PATH) as db:
        if win > 0:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (win, user.id))
            await db.commit()

    if win > 0:
        await profile_add_xp(user.id, win)
        msg = f"🎡 <b>گردونه شانس متوقف شد!</b>\n🎉 تبریک <b>{html.escape(user.first_name)}</b>، شما برنده <b>+{win} امتیاز</b> شدید!"
    else:
        msg = f"🎡 <b>گردونه شانس متوقف شد!</b>\n❌ این‌بار پوچ بود! امشب بعد از ساعت ۱۲ دوباره شانس‌ات را امتحان کن."

    if update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode="HTML")
    else:
        await update.effective_message.reply_text(msg, parse_mode="HTML")

# سیستم حدس بازیکن با متغیر مستقل به ازای هر گروه
async def guess_timeout_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    game = ACTIVE_GUESS_GAMES.get(chat_id)
    if game and game.get("is_active"):
        game["is_active"] = False
        main_name = game["names"][0]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⌛️ <b>مهلت ۳۰ ثانیه‌ای حدس بازیکن به پایان رسید!</b>\n"
                 f"👤 ستاره مورد نظر پرونده: <b>{main_name}</b> بود.",
            parse_mode="HTML"
        )

async def start_guess_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update):
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    await ensure_user(user)

    g_count = await get_guess_count_db(user.id)
    if g_count >= 3:
        await update.effective_message.reply_text(
            f"⛔️ <b>{html.escape(user.first_name)}</b> عزیز، شما سقف ۳ بار حدس بازیکن امروز خود را مصرف کرده‌اید!\n"
            "امشب بعد از ساعت ۱۲ سهمیه ۳تایی جدید شما باز خواهد شد.",
            parse_mode="HTML"
        )
        return

    game = ACTIVE_GUESS_GAMES.get(chat_id)
    if game and game.get("is_active"):
        challenger_name = html.escape(game.get("challenger_name", "کاربر"))
        await update.effective_message.reply_text(
            f"⚠️ یک پرونده هم‌اکنون برای <b>{challenger_name}</b> در این گروه در جریان است!\n"
            "لطفاً تا پایان مهلت ۳۰ ثانیه‌ای شکیبا باشید.",
            parse_mode="HTML"
        )
        return

    await increment_guess_count_db(user.id)
    current_attempt = g_count + 1

    p = get_next_guess_player()
    career_str = "\n".join([f"  {idx}. {club}" for idx, club in enumerate(p['career'], 1)])

    ACTIVE_GUESS_GAMES[chat_id] = {
        "names": [n.lower() for n in p["names"]],
        "reward": 15,
        "chat_id": chat_id,
        "challenger_id": user.id,
        "challenger_name": user.first_name,
        "is_active": True
    }

    text = (
        "🕵️‍♂️ <b>پرونده اطلاعاتی: ستاره فوتبال را شناسایی کنید!</b>\n"
        "────────────────────\n"
        f"🎯 بازیکن چالش: <b>{html.escape(user.first_name)}</b> (فرصت {current_attempt} از ۳)\n"
        f"⏱ مهلت پاسخ: <b>۳۰ ثانیه</b> ⏳\n"
        f"🌍 <b>ملیت:</b> {p['nation']}\n"
        f"📌 <b>پست تخصصی:</b> {p['pos']}\n\n"
        f"🏟 <b>مسیر باشگاهی:</b>\n{career_str}\n\n"
        f"⭐️ <b>سرنخ کلیدی:</b>\n{p['clue']}\n"
        "────────────────────\n"
        "💰 پاداش پاسخ صحیح: <b>+15 امتیاز</b> | <b>+80 XP</b>\n"
        "👇 نام بازیکن را در چت ارسال کنید:"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")
    context.job_queue.run_once(
        guess_timeout_job, 30,
        data={"chat_id": chat_id, "user_id": user.id},
        name=f"guess_timer_{chat_id}"
    )

# سیستم جک‌پات کمبو کاملاً فعال و کاربردی (۵ مسابقه)
async def get_or_create_jackpot_round():
    now_str = get_iran_now().strftime("%Y-%m-%d")
    round_id = f"JK_{now_str}"

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT round_id, title, matches_json, pool_amount FROM jackpot_rounds WHERE round_id = ?", (round_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "round_id": row[0],
                    "title": row[1],
                    "matches": json.loads(row[2]),
                    "pool_amount": row[3]
                }

    # جمع‌آوری مسابقات برای جک‌پات از کش یا بازی‌های روز
    sample_fixtures = [
        {"id": "jk1", "home": "رئال مادرید", "away": "بارسلونا", "league": "🇪🇸 لالیگا"},
        {"id": "jk2", "home": "منچسترسیتی", "away": "آرسنال", "league": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 لیگ جزیره"},
        {"id": "jk3", "home": "تیم ملی ایران", "away": "ازبکستان", "league": "🌏 انتخابی جام جهانی"},
        {"id": "jk4", "home": "فرانسه", "away": "ایتالیا", "league": "🇪🇺 لیگ ملت‌های اروپا"},
        {"id": "jk5", "home": "بایرن مونیخ", "away": "دورتموند", "league": "🇩🇪 بوندسلیگا"}
    ]

    # اگر بازی‌های زنده در کش بود، از آن‌ها استفاده کن
    if len(MATCH_CACHE) >= 5:
        cached_matches = list(MATCH_CACHE.values())[:5]
        sample_fixtures = [
            {"id": m["id"], "home": m["home_team"], "away": m["away_team"], "league": m.get("league", "فوتبال")}
            for m in cached_matches
        ]

    title = f"جک‌پات کمبو ۵ مسابقه بزرگ ({now_str})"
    pool_amount = 500

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO jackpot_rounds (round_id, title, matches_json, pool_amount, is_active, is_settled, created_at)
            VALUES (?, ?, ?, ?, 1, 0, ?)
        """, (round_id, title, json.dumps(sample_fixtures, ensure_ascii=False), pool_amount, now_str))
        await db.commit()

    return {
        "round_id": round_id,
        "title": title,
        "matches": sample_fixtures,
        "pool_amount": pool_amount
    }

async def jackpot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    round_data = await get_or_create_jackpot_round()
    round_id = round_data["round_id"]
    matches = round_data["matches"]
    pool = round_data["pool_amount"]

    # بررسی اینکه آیا کاربر قبلاً فرم ثبت کرده است
    user_combo = None
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT predictions_json, status FROM jackpot_combos WHERE user_id = ? AND round_id = ?", (user.id, round_id)) as cur:
            row = await cur.fetchone()
            if row:
                user_combo = json.loads(row[0])

    matches_text = ""
    for idx, m in enumerate(matches, 1):
        user_pick = ""
        if user_combo:
            p_val = user_combo.get(str(idx - 1), "—")
            p_label = "برد میزبان" if p_val == "HOME" else ("تساوی" if p_val == "DRAW" else ("برد میهمان" if p_val == "AWAY" else "—"))
            user_pick = f" ➔ انتخاب شما: <b>{p_label}</b>"
        matches_text += f"{idx}. <b>{m['home']}</b> 🆚 <b>{m['away']}</b> ({m['league']}){user_pick}\n"

    status_footer = ""
    buttons = []
    if user_combo:
        status_footer = "\n✅ <b>فرم جک‌پات شما برای این راند با موفقیت ثبت شده است!</b>"
        buttons.append([InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")])
    else:
        status_footer = "\n👇 برای شروع ثبت پیش‌بینی کمبو روی دکمه زیر کلیک کنید:"
        buttons.append([InlineKeyboardButton("📝 ثبت فرم کمبو ۵تایی (رایگان)", callback_data=f"jk_start_{round_id}")])
        buttons.append([InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")])

    text = (
        f"🎰 <b>جک‌پات کمبو طلایی فوتبال هاب (Jackpot Combo)</b>\n"
        f"────────────────────\n"
        f"💰 استخر جایزه بزرگ: <b>{pool} PTS</b> 🪙\n"
        f"▫️ شرط برنده شدن: پیش‌بینی دقیق نتیجه هر ۵ مسابقه\n"
        f"▫️ جایزه تسلیحاتی: ۴ از ۵ صحیح = <b>+50 PTS</b>\n"
        f"────────────────────\n"
        f"📋 <b>مسابقات راند جاری:</b>\n\n"
        f"{matches_text}"
        f"{status_footer}"
    )

    reply_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

# پنالتی تک‌ضرب با محافظت از موجودی و عدم تولید امتیاز جعلی
async def trigger_penalty_shootout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "🥅 <b>نحوه شروع پنالتی:</b>\nروی پیام حریف ریپلای کنید و بنویسید: <code>پنالتی</code> یا <code>/penalty</code>",
            parse_mode="HTML"
        )
        return

    challenger = update.effective_user
    opponent = update.message.reply_to_message.from_user

    if opponent.is_bot or challenger.id == opponent.id:
        await update.message.reply_text("⚠️ امکان مسابقه با این کاربر وجود ندارد.")
        return

    c_count = await get_penalty_count_db(challenger.id)
    if c_count >= 3:
        await update.message.reply_text(
            f"⛔️ <b>{html.escape(challenger.first_name)}</b> عزیز، شما سقف مجاز ۳ پنالتی در روز خود را مصرف کرده‌اید!",
            parse_mode="HTML"
        )
        return

    o_count = await get_penalty_count_db(opponent.id)
    if o_count >= 3:
        await update.message.reply_text(
            f"⛔️ حریف شما <b>{html.escape(opponent.first_name)}</b> امروز ۳ پنالتی خود را بازی کرده است!",
            parse_mode="HTML"
        )
        return

    await ensure_user(challenger)
    await ensure_user(opponent)

    stake = 15
    # بررسی و قفل موجودی هر دو طرف برای جلوگیری از باگ تولید امتیاز
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (challenger.id, opponent.id)) as cur:
            balances = {row[0]: row[1] for row in await cur.fetchall()}

    c_pts = balances.get(challenger.id, 0)
    o_pts = balances.get(opponent.id, 0)

    if c_pts < stake:
        await update.message.reply_text(f"⛔️ شما برای پنالتی حداقل <b>{stake} PTS</b> نیاز دارید.\nموجودی: <code>{c_pts} PTS</code>", parse_mode="HTML")
        return
    if o_pts < stake:
        await update.message.reply_text(f"⛔️ حریف شما <b>{html.escape(opponent.first_name)}</b> حداقل <b>{stake} PTS</b> موجودی ندارد.", parse_mode="HTML")
        return

    p_id = f"pen_{random.randint(10000, 99999)}"
    ACTIVE_SHOOTOUTS[p_id] = {
        "p1": {"id": challenger.id, "name": challenger.first_name, "shot": None},
        "p2": {"id": opponent.id, "name": opponent.first_name, "shot": None},
        "current_turn": challenger.id,
        "round": 1,
        "stake": stake,
        "chat_id": update.effective_chat.id,
        "message_id": None
    }

    p_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧤 قبول چالش پنالتی", callback_data=f"acp_{p_id}"),
         InlineKeyboardButton("❌ انصراف", callback_data=f"rjp_{p_id}")]
    ])

    c_name = html.escape(challenger.first_name)
    o_name = html.escape(opponent.first_name)

    text = (
        "🥅 <b>دوئل تک‌ضرب پنالتی (مرگ ناگهانی)!</b> ⚽️\n"
        "────────────────────\n"
        f"👤 شوت‌زن اول: <b>{c_name}</b> ({c_count + 1}/3)\n"
        f"👤 شوت‌زن دوم: <b>{o_name}</b> ({o_count + 1}/3)\n"
        f"💰 مبلغ شرط: <b>{stake} PTS</b> (مجموع جایزه: <b>{stake * 2} PTS</b>)\n"
        "────────────────────\n"
        f"آیا <b>{o_name}</b> چالش پنالتی را می‌پذیرد؟"
    )
    sent_msg = await update.message.reply_text(text, reply_markup=p_kb, parse_mode="HTML")
    ACTIVE_SHOOTOUTS[p_id]["message_id"] = sent_msg.message_id

def render_shootout_board(shootout_id: str, shooter_name: str, shot_number: int):
    text = (
        "🥅 <b>نوبت ضربه پنالتی!</b> ⚽️\n"
        "────────────────────\n"
        f"👤 زننده ضربه: <b>{html.escape(shooter_name)}</b> (شوت شماره {shot_number})\n"
        "گوشه شوت خود را انتخاب کنید:\n"
        "  [بالا چپ ↖️]  [مرکز طاق ⬆️]  [بالا راست ↗️]\n"
        "  [پایین چپ ↙️]   [مرکز زمینی ⬇️]   [پایین راست ↘️]"
    )
    buttons = [
        [
            InlineKeyboardButton("↖️ بالا چپ", callback_data=f"sht_{shootout_id}_TL"),
            InlineKeyboardButton("⬆️ مرکز طاق", callback_data=f"sht_{shootout_id}_TC"),
            InlineKeyboardButton("↗️ بالا راست", callback_data=f"sht_{shootout_id}_TR")
        ],
        [
            InlineKeyboardButton("↙️ پایین چپ", callback_data=f"sht_{shootout_id}_BL"),
            InlineKeyboardButton("⬇️ زمینی مرکز", callback_data=f"sht_{shootout_id}_BC"),
            InlineKeyboardButton("↘️ پایین راست", callback_data=f"sht_{shootout_id}_BR")
        ]
    ]
    return text, InlineKeyboardMarkup(buttons)

async def execute_penalty_kick(context: ContextTypes.DEFAULT_TYPE, shootout_id: str, choice: str):
    shootout = ACTIVE_SHOOTOUTS.get(shootout_id)
    if not shootout:
        return

    chat_id = shootout["chat_id"]
    msg_id = shootout["message_id"]
    stake = shootout["stake"]

    goalkeeper_dives = ["TL", "TC", "TR", "BL", "BC", "BR"]
    gk_dive = random.choice(goalkeeper_dives)
    is_goal = choice != gk_dive

    pos_names = {
        "TL": "گوشه بالا چپ", "TC": "مرکز طاق دروازه", "TR": "گوشه بالا راست",
        "BL": "زاویه پایین چپ", "BC": "مرکز زمینی", "BR": "زاویه پایین راست"
    }

    if shootout["p1"]["shot"] is None:
        shootout["p1"]["shot"] = is_goal
        p1_name = shootout["p1"]["name"]
        p2_name = shootout["p2"]["name"]
        status_text = f"⚽️ <b>گـُــل شد!</b> ({pos_names[choice]})" if is_goal else f"🧤❌ <b>مهار شد!</b> (شیرجه دروازه‌بان به {pos_names[gk_dive]})"

        mid_text = (
            f"👤 شوت <b>{html.escape(p1_name)}</b>: {status_text}\n"
            "────────────────────\n"
            f"اکنون نوبت شوت <b>{html.escape(p2_name)}</b> است..."
        )
        shootout["current_turn"] = shootout["p2"]["id"]
        t, k = render_shootout_board(shootout_id, p2_name, 2)
        await safe_edit_message(context.bot, f"{mid_text}\n\n{t}", reply_markup=k, chat_id=chat_id, message_id=msg_id)
        return

    # شوت دوم و تسویه شرط‌بندی امن (Escrow)
    shootout["p2"]["shot"] = is_goal
    p1_goal = shootout["p1"]["shot"]
    p2_goal = shootout["p2"]["shot"]
    p1_name = shootout["p1"]["name"]
    p2_name = shootout["p2"]["name"]
    p1_id = shootout["p1"]["id"]
    p2_id = shootout["p2"]["id"]

    res_h = "⚽️ گل" if p1_goal else "❌ مهار"
    res_a = "⚽️ گل" if p2_goal else "❌ مهار"

    summary = (
        "🏁 <b>نتیجه نهایی پنالتی تک‌ضرب:</b>\n"
        "────────────────────\n"
        f"▫️ <b>{html.escape(p1_name)}</b>: {res_h}\n"
        f"▫️ <b>{html.escape(p2_name)}</b>: {res_a}\n"
        "────────────────────\n"
    )

    async with aiosqlite.connect(DATABASE_PATH) as db:
        if p1_goal and not p2_goal:
            # کسر از بازنده و پرداخت به برنده
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, p1_id))
            await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, p2_id))
            await db.commit()
            await profile_record_penalty_win(p1_id)
            summary += f"🎉 تبریک! <b>{html.escape(p1_name)}</b> برنده <b>+{stake} امتیاز</b> شد!"
        elif p2_goal and not p1_goal:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, p2_id))
            await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, p1_id))
            await db.commit()
            await profile_record_penalty_win(p2_id)
            summary += f"🎉 تبریک! <b>{html.escape(p2_name)}</b> برنده <b>+{stake} امتیاز</b> شد!"
        else:
            summary += "🤝 هر دو پنالتی مشابه شد (تساوی)! هیچ امتیازی کسر نگردید."

    del ACTIVE_SHOOTOUTS[shootout_id]
    await safe_edit_message(context.bot, summary, chat_id=chat_id, message_id=msg_id)

# دوئل ۱ به ۱ اطلاعات عمومی با بانک ۸۰۹۰ سوالی
async def trigger_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚔️ روی پیام حریف ریپلای کنید و بنویسید: <code>دوئل</code> یا <code>/duel</code>", parse_mode="HTML")
        return

    challenger = update.effective_user
    opponent = update.message.reply_to_message.from_user

    if opponent.is_bot or challenger.id == opponent.id:
        await update.message.reply_text("⚠️ امکان دوئل با این کاربر نیست.")
        return

    await ensure_user(challenger)
    await ensure_user(opponent)

    stake = 25
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (challenger.id, opponent.id)) as cur:
            balances = {row[0]: row[1] for row in await cur.fetchall()}

    c_pts = balances.get(challenger.id, 0)
    o_pts = balances.get(opponent.id, 0)

    if c_pts < stake:
        await update.message.reply_text(f"⛔️ شما برای دوئل حداقل <b>{stake} PTS</b> لازم دارید.\nموجودی: <code>{c_pts} PTS</code>", parse_mode="HTML")
        return
    if o_pts < stake:
        await update.message.reply_text(f"⛔️ <b>{html.escape(opponent.first_name)}</b> برای دوئل حداقل <b>{stake} PTS</b> لازم دارد.", parse_mode="HTML")
        return

    duel_id = f"dl_{random.randint(10000, 99999)}"
    ACTIVE_DUELS[duel_id] = {
        "challenger": {"id": challenger.id, "name": challenger.first_name, "score": 0},
        "opponent": {"id": opponent.id, "name": opponent.first_name, "score": 0},
        "questions": get_random_duel_questions(3),
        "current_q": 0,
        "stake": stake,
        "answered": {},
        "chat_id": update.effective_chat.id,
        "message_id": None
    }

    duel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ قبول چالش دوئل", callback_data=f"acd_{duel_id}"),
         InlineKeyboardButton("❌ رد چالش", callback_data=f"rjd_{duel_id}")]
    ])

    c_name = html.escape(challenger.first_name)
    o_name = html.escape(opponent.first_name)

    text = (
        "⚔️ <b>میدان دوئل اطلاعات عمومی فوتبال!</b> 🔥\n"
        "────────────────────\n"
        f"👤 چلنجر: <b>{c_name}</b>  ▫️  هماورد: <b>{o_name}</b>\n"
        f"💰 جایزه رقابت: <b>+{stake} امتیاز</b> 🪙\n"
        "⏱ زمان هر سوال: <b>15 ثانیه</b> ⏳\n"
        "────────────────────\n"
        f"آیا <b>{o_name}</b> چالش را می‌پذیرد؟"
    )
    sent_msg = await update.message.reply_text(text, reply_markup=duel_kb, parse_mode="HTML")
    ACTIVE_DUELS[duel_id]["message_id"] = sent_msg.message_id

def render_duel_question_text(duel, q_data, q_idx):
    c_name = html.escape(duel["challenger"]["name"])
    o_name = html.escape(duel["opponent"]["name"])
    c_score = duel["challenger"]["score"]
    o_score = duel["opponent"]["score"]

    return (
        f"⚔️ <b>دوئل اطلاعات عمومی (سوال {q_idx + 1} از ۳)</b>\n"
        "────────────────────\n"
        f"▫️ <b>{c_name}</b>: <code>{c_score}</code> امتیاز\n"
        f"▫️ <b>{o_name}</b>: <code>{o_score}</code> امتیاز\n"
        "────────────────────\n"
        f"❓ <b>{q_data['question']}</b>\n\n"
        "⏱ مهلت پاسخ: <b>۱۵ ثانیه</b>"
    )

async def question_timeout_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    duel_id = job_data["duel_id"]
    q_idx = job_data["q_idx"]
    duel = ACTIVE_DUELS.get(duel_id)
    if duel and duel["current_q"] == q_idx:
        duel["current_q"] += 1
        await proceed_duel(context, duel_id)

async def proceed_duel(context: ContextTypes.DEFAULT_TYPE, duel_id: str):
    duel = ACTIVE_DUELS.get(duel_id)
    if not duel:
        return

    chat_id = duel["chat_id"]
    msg_id = duel["message_id"]
    q_idx = duel["current_q"]

    if q_idx >= len(duel["questions"]):
        c_score = duel["challenger"]["score"]
        o_score = duel["opponent"]["score"]
        c_name = html.escape(duel["challenger"]["name"])
        o_name = html.escape(duel["opponent"]["name"])
        c_id = duel["challenger"]["id"]
        o_id = duel["opponent"]["id"]
        stake = duel["stake"]

        res_text = (
            "🏁 <b>پایان دوئل اطلاعات عمومی!</b>\n"
            "────────────────────\n"
            f"▫️ <b>{c_name}</b>: {c_score} پاسخ درست\n"
            f"▫️ <b>{o_name}</b>: {o_score} پاسخ درست\n"
            "────────────────────\n"
        )

        async with aiosqlite.connect(DATABASE_PATH) as db:
            if c_score > o_score:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, c_id))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, o_id))
                res_text += f"🎉 تبریک به <b>{c_name}</b>! برنده <b>+{stake} امتیاز</b> شد."
                await profile_record_duel_win(c_id)
            elif o_score > c_score:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, o_id))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, c_id))
                res_text += f"🎉 تبریک به <b>{o_name}</b>! برنده <b>+{stake} امتیاز</b> شد."
                await profile_record_duel_win(o_id)
            else:
                res_text += "🤝 رقابت مساوی شد! هیچ امتیازی کسر نگردید."
            await db.commit()

        del ACTIVE_DUELS[duel_id]
        await safe_edit_message(context.bot, res_text, chat_id=chat_id, message_id=msg_id)
        return

    q_data = duel["questions"][q_idx]
    duel["answered"] = {}

    buttons = []
    for opt_idx, opt_text in enumerate(q_data["options"]):
        buttons.append([InlineKeyboardButton(f"🔘 {opt_text}", callback_data=f"ad_{duel_id}_{opt_idx}")])

    text = render_duel_question_text(duel, q_data, q_idx)
    await safe_edit_message(context.bot, text, reply_markup=InlineKeyboardMarkup(buttons), chat_id=chat_id, message_id=msg_id)

    context.job_queue.run_once(
        question_timeout_job,
        15,
        data={"duel_id": duel_id, "q_idx": q_idx},
        name=f"duel_timer_{duel_id}_{q_idx}"
    )

# بتل ۲ به ۲ تیمی
async def trigger_team_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚔️ برای شروع بتل ۲ به ۲، روی پیام حریف ریپلای کن و بنویس:\n"
            "<code>بتل</code> یا <code>/battle</code>", parse_mode="HTML"
        )
        return
    challenger = update.effective_user
    opponent = update.message.reply_to_message.from_user
    if opponent.is_bot or challenger.id == opponent.id:
        await update.message.reply_text("⚠️ امکان بتل با این کاربر نیست.")
        return
    await ensure_user(challenger)
    await ensure_user(opponent)
    stake = 30
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (challenger.id, opponent.id)) as cur:
            balances = {int(uid): int(pts or 0) for uid, pts in await cur.fetchall()}
    if balances.get(challenger.id, 0) < stake or balances.get(opponent.id, 0) < stake:
        await update.message.reply_text(f"⛔️ هر بازیکن برای شروع بتل باید حداقل <b>{stake} PTS</b> داشته باشد.", parse_mode="HTML")
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
    text = render_team_duel_lobby(ACTIVE_TEAM_DUELS[duel_id])
    kb_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ یار تیم ۱", callback_data=f"bt1_{duel_id}"),
         InlineKeyboardButton("➕ یار تیم ۲", callback_data=f"bt2_{duel_id}")],
        [InlineKeyboardButton("❌ لغو بتل", callback_data=f"r2d_{duel_id}")]
    ])
    sent = await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")
    ACTIVE_TEAM_DUELS[duel_id]["message_id"] = sent.message_id

def render_team_duel_lobby(duel):
    def player_line(team):
        lines = []
        for idx in range(2):
            if idx < len(team):
                lines.append(f"<b>{html.escape(team[idx]['name'])}</b>")
            else:
                lines.append("<i>[در انتظار پیوستن یار...]</i>")
        return " & ".join(lines)

    return (
        "⚔️ <b>لابی نبرد ۲ به ۲ تیمی (بتل)!</b> 🔥\n"
        "────────────────────\n"
        f"🔵 <b>تیم ۱:</b> {player_line(duel['team1'])}\n"
        f"🔴 <b>تیم ۲:</b> {player_line(duel['team2'])}\n"
        "────────────────────\n"
        f"💰 ورودی هر نفر: <b>{duel['stake']} PTS</b> | جایزه تیم برنده: <b>+{duel['stake']} PTS</b> به هر نفر\n"
        "⏱ زمان هر سوال: <b>۱۵ ثانیه</b>\n\n"
        "👇 برای عضویت در هر تیم روی دکمه‌های زیر بزنید:"
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
    duel_id = job_data["duel_id"]
    q_idx = job_data["q_idx"]
    duel = ACTIVE_TEAM_DUELS.get(duel_id)
    if duel and duel["current_q"] == q_idx and not duel.get("finished"):
        duel["current_q"] += 1
        await proceed_team_duel(context, duel_id)

async def finish_team_duel(context: ContextTypes.DEFAULT_TYPE, duel_id: str):
    duel = ACTIVE_TEAM_DUELS.get(duel_id)
    if not duel or duel.get("finished"):
        return
    duel["finished"] = True
    chat_id = duel["chat_id"]
    msg_id = duel["message_id"]
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

    async with aiosqlite.connect(DATABASE_PATH) as db:
        if t1_score > t2_score:
            text += f"🎉 تبریک! <b>تیم ۱</b> پیروز شد و هر بازیکن <b>+{stake} امتیاز</b> پاداش گرفت!"
            for p in duel["team1"]:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, p["id"]))
                await profile_record_duel_win(p["id"])
            for p in duel["team2"]:
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, p["id"]))
        elif t2_score > t1_score:
            text += f"🎉 تبریک! <b>تیم ۲</b> پیروز شد و هر بازیکن <b>+{stake} امتیاز</b> پاداش گرفت!"
            for p in duel["team2"]:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, p["id"]))
                await profile_record_duel_win(p["id"])
            for p in duel["team1"]:
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, p["id"]))
        else:
            text += "🤝 رقابت دو تیم مساوی شد! هیچ امتیازی کسر نگردید."
        await db.commit()

    del ACTIVE_TEAM_DUELS[duel_id]
    await safe_edit_message(context.bot, text, chat_id=chat_id, message_id=msg_id)

async def proceed_team_duel(context: ContextTypes.DEFAULT_TYPE, duel_id: str):
    duel = ACTIVE_TEAM_DUELS.get(duel_id)
    if not duel or duel.get("finished"):
        return
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

    context.job_queue.run_once(
        team_duel_timeout_job, 15,
        data={"duel_id": duel_id, "q_idx": q_idx},
        name=f"team_duel_timer_{duel_id}_{q_idx}"
    )

# تالار مسابقات و پیش‌بینی
async def predictions_hub_handler(query):
    iran_now = get_iran_now()
    dates = [iran_now.strftime("%Y%m%d"), (iran_now + timedelta(days=1)).strftime("%Y%m%d")]

    candidate_matches = []
    for d in dates:
        for l_code in ACTIVE_MONITOR_LEAGUES:
            try:
                m_list = await provider.get_matches(d, league_code=l_code)
                for m in m_list:
                    MATCH_CACHE[m["id"]] = m
                    if m.get("status") == "UPCOMING":
                        candidate_matches.append(m)
            except Exception:
                pass

    seen = set()
    upcoming_list = []
    for m in candidate_matches:
        if m["id"] not in seen:
            seen.add(m["id"])
            upcoming_list.append(m)

    if not upcoming_list:
        await safe_edit_message(query, "⏳ <b>در حال حاضر مسابقه شروع‌نشده‌ای برای پیش‌بینی ثبت نشده است.</b>\nبه زودی با بارگذاری بازی‌های جدید فعال خواهد شد.", reply_markup=kb.get_back_button())
        return

    text = (
        "🎯 <b>تالار پیش‌بینی مسابقات فوتبال</b>\n"
        "────────────────────\n"
        "مسابقه مورد نظر خود را جهت ثبت نتیجه انتخاب کنید:\n"
        "💰 پاداش شرکت در هر مسابقه: <b>+10 امتیاز هدیه</b>\n"
        "────────────────────"
    )
    await safe_edit_message(query, text, reply_markup=kb.get_upcoming_matches_keyboard(upcoming_list))

# حالت تقلب ادمین (حفظ‌شده طبق درخواست کاربر)
async def cheat_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if chat is None or chat.type != "private":
        return

    if str(user.id) != str(ADMIN_ID):
        await update.effective_message.reply_text("⛔️ این قابلیت فقط برای مالک ربات فعال است.")
        return

    command = (update.effective_message.text or "").split()[0].split("@")[0].lower()

    if command == "/ch_on":
        CHEAT_MODE_USERS.add(user.id)
        await update.effective_message.reply_text(
            "🟢 <b>Ch Mode فعال شد.</b>\n\n"
            "در دوئل و بتل ۲ به ۲، هر گزینه‌ای که انتخاب کنی به عنوان پاسخ درست ثبت می‌شود.\n"
            "برای برگشت به حالت عادی: <code>/Ch_off</code>",
            parse_mode="HTML"
        )
    elif command == "/ch_off":
        CHEAT_MODE_USERS.discard(user.id)
        await update.effective_message.reply_text(
            "🔴 <b>Ch Mode غیرفعال شد.</b>\n\n"
            "دوئل و بتل دوباره پاسخ واقعی را بررسی می‌کنند.",
            parse_mode="HTML"
        )

# مسیریاب کلیک‌های اینلاین (Callback Router)
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "home":
        await start(update, context)

    elif data == "spin_wheel":
        await spin_wheel_cmd(update, context)

    elif data == "jackpot_hub":
        await jackpot_cmd(update, context)

    # شروع پیش‌بینی جک‌پات کمبو ۵ مسابقه
    elif data.startswith("jk_start_"):
        round_id = data.replace("jk_start_", "")
        round_data = await get_or_create_jackpot_round()
        matches = round_data["matches"]
        USER_JACKPOT_DRAFTS[query.from_user.id] = {"round_id": round_id, "picks": {}}
        
        # نمایش اولین بازی
        m = matches[0]
        text = (
            f"🎰 <b>جک‌پات کمبو (مسابقه ۱ از ۵):</b>\n"
            f"────────────────────\n"
            f"⚽️ <b>{m['home']}</b> 🆚 <b>{m['away']}</b> ({m['league']})\n\n"
            f"نتیجه این مسابقه را پیش‌بینی کنید:"
        )
        await safe_edit_message(query, text, reply_markup=kb.get_jackpot_match_keyboard(round_id, 0, 5))

    elif data.startswith("jk_pick_"):
        parts = data.split("_")
        round_id = parts[2]
        match_idx = int(parts[3])
        pick = parts[4]
        user_id = query.from_user.id

        draft = USER_JACKPOT_DRAFTS.get(user_id)
        if not draft or draft.get("round_id") != round_id:
            draft = {"round_id": round_id, "picks": {}}
            USER_JACKPOT_DRAFTS[user_id] = draft

        draft["picks"][str(match_idx)] = pick
        next_idx = match_idx + 1

        round_data = await get_or_create_jackpot_round()
        matches = round_data["matches"]

        if next_idx < len(matches):
            m = matches[next_idx]
            text = (
                f"🎰 <b>جک‌پات کمبو (مسابقه {next_idx + 1} از ۵):</b>\n"
                f"────────────────────\n"
                f"⚽️ <b>{m['home']}</b> 🆚 <b>{m['away']}</b> ({m['league']})\n\n"
                f"نتیجه این مسابقه را پیش‌بینی کنید:"
            )
            await safe_edit_message(query, text, reply_markup=kb.get_jackpot_match_keyboard(round_id, next_idx, len(matches)))
        else:
            # پایان ثبت هر ۵ مسابقه و ذخیره در دیتابیس
            picks_json = json.dumps(draft["picks"], ensure_ascii=False)
            now_str = get_iran_now().strftime("%Y-%m-%d %H:%M")
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO jackpot_combos (user_id, user_name, round_id, predictions_json, status, created_at)
                    VALUES (?, ?, ?, ?, 'PENDING', ?)
                """, (user_id, query.from_user.first_name, round_id, picks_json, now_str))
                await db.commit()

            await profile_add_xp(user_id, 30)

            # رسید فرم ثبت‌شده
            receipt = ""
            for idx, m in enumerate(matches):
                p_val = draft["picks"].get(str(idx), "—")
                p_label = "برد میزبان" if p_val == "HOME" else ("تساوی" if p_val == "DRAW" else "برد میهمان")
                receipt += f"▫️ {m['home']} ✕ {m['away']}: <b>{p_label}</b>\n"

            text = (
                "🎉 <b>فرم جک‌پات کمبو با موفقیت صادر شد!</b> 🎟\n"
                "────────────────────\n"
                f"{receipt}"
                "────────────────────\n"
                "💰 پاداش ثبت فرم: <b>+30 XP</b>\n"
                "🏆 در صورت حدس هر ۵ مسابقه، استخر ۵۰۰ امتیازی به حساب شما واریز خواهد شد!",
            )
            USER_JACKPOT_DRAFTS.pop(user_id, None)
            await safe_edit_message(query, "".join(text), reply_markup=kb.get_back_button("jackpot_hub"))

    elif data == "predictions_hub":
        await predictions_hub_handler(query)

    elif data.startswith("select_pred_"):
        match_id = data.replace("select_pred_", "")
        m = MATCH_CACHE.get(match_id)
        if not m:
            await query.answer("اطلاعات این مسابقه منقضی شده است.", show_alert=True)
            return
        time_str = format_iran_time(m.get("date"))
        text = (
            f"🎯 <b>فرم ثبت پیش‌بینی مسابقه:</b>\n"
            f"────────────────────\n"
            f"⚽️ <b>{m['home_team']}</b> 🆚 <b>{m['away_team']}</b>\n"
            f"⏰ شروع: <code>{time_str}</code> (تهران)\n"
            f"────────────────────\n"
            f"پیش‌بینی خود از نتیجه نهایی را انتخاب کنید:"
        )
        await safe_edit_message(query, text, reply_markup=kb.get_prediction_keyboard(m['id']))

    elif data.startswith("pred_out_"):
        parts = data.split("_")
        match_id, choice = parts[2], parts[3]
        user_id = query.from_user.id
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            try:
                await db.execute("""
                    INSERT INTO predictions (user_id, match_id, outcome_choice, predicted_home, predicted_away)
                    VALUES (?, ?, ?, 0, 0)
                """, (user_id, match_id, choice))
                await db.execute("UPDATE users SET points = points + 10, total_predictions = total_predictions + 1 WHERE user_id = ?", (user_id,))
                await db.commit()
                await profile_add_xp(user_id, 20)
                await safe_edit_message(query, "✅ <b>پیش‌بینی شما با موفقیت ثبت شد! (+10 امتیاز و +20 XP هدیه)</b>", reply_markup=kb.get_back_button())
            except Exception:
                await safe_edit_message(query, "⚠️ شما قبلاً این بازی را پیش‌بینی کرده‌اید.", reply_markup=kb.get_back_button())

    elif data.startswith("pool_"):
        parts = data.split("_")
        match_id = parts[1]
        choice = parts[2]
        user = query.from_user

        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
                INSERT INTO special_pool_predictions (match_id, user_id, user_name, choice)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(match_id, user_id) DO UPDATE SET choice = excluded.choice, user_name = excluded.user_name
            """, (match_id, user.id, user.first_name, choice))
            await db.commit()

            async with db.execute("SELECT user_name, choice FROM special_pool_predictions WHERE match_id = ?", (match_id,)) as cur:
                participants = await cur.fetchall()

        await query.answer("✅ انتخاب شما در استخر ثبت شد!", show_alert=False)
        m = MATCH_CACHE.get(match_id, {"home_team": "میزبان", "away_team": "میهمان", "date": None})
        new_text = await generate_pool_message_text(m, participants)
        await safe_edit_message(query, new_text, reply_markup=query.message.reply_markup)

    elif data == "select_matches_today":
        await safe_edit_message(query, "🔥 <b>لیگ یا تورنمنت مسابقات امروز را انتخاب کنید:</b>", reply_markup=kb.get_matches_leagues_keyboard("today"))

    elif data == "select_matches_tomorrow":
        await safe_edit_message(query, "📅 <b>لیگ یا تورنمنت مسابقات فردا را انتخاب کنید:</b>", reply_markup=kb.get_matches_leagues_keyboard("tmrw"))

    elif data == "select_standings_league":
        await safe_edit_message(query, "🏆 <b>جدول رده‌بندی لیگ مورد نظر را انتخاب کنید:</b>", reply_markup=kb.get_standings_leagues_keyboard())

    elif data.startswith("today_") or data.startswith("tmrw_"):
        is_today = data.startswith("today_")
        league_code = data.split("_")[1]
        target_date = get_iran_now() if is_today else (get_iran_now() + timedelta(days=1))
        date_str = target_date.strftime("%Y%m%d")

        matches = await provider.get_matches(date_str, league_code=league_code)
        title = LEAGUE_TITLES.get(league_code, "مسابقات فوتبال")
        day_label = "امروز" if is_today else "فردا"

        if not matches:
            await safe_edit_message(
                query,
                f"⏳ مسابقه‌ای برای <b>{title}</b> در تاریخ {day_label} یافت نشد.\nممکن است در تعطیلات لیگ یا فیفادی باشیم.",
                reply_markup=kb.get_back_button()
            )
            return

        text = f"⚽️ <b>برنامه مسابقات {title} ({day_label}):</b>\n────────────────────\n\n"
        for m in matches[:10]:
            MATCH_CACHE[m["id"]] = m
            time_str = format_iran_time(m.get("date"))
            status = m.get("status", "UPCOMING")
            if status in ["LIVE", "IN_PLAY", "1H", "2H", "HT"]:
                badge = f"🔴 زنده [{m['home_score']} - {m['away_score']}]"
            elif status in ["FINISHED", "FT", "POST"]:
                badge = f"🏁 پایان [{m['home_score']} - {m['away_score']}]"
            else:
                badge = f"⏰ <code>{time_str}</code>"

            text += f"▫️ <b>{m['home_team']}</b> 🆚 <b>{m['away_team']}</b>\n    └ {badge}  •  {m.get('venue', 'ورزشگاه')}\n\n"

        text += "────────────────────"
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data.startswith("table_"):
        league_code = data.replace("table_", "")
        standings = await provider.get_standings(league_code)
        title = LEAGUE_TITLES.get(league_code, "جدول رده‌بندی")

        if not standings:
            await safe_edit_message(query, f"⏳ جدول رده‌بندی برای <b>{title}</b> در دسترس نیست.", reply_markup=kb.get_back_button())
            return

        text = f"🏆 <b>جدول زنده {title}:</b>\n────────────────────\n"
        text += "<code>رتبه | تیم            | بازی | برد | مساوی | باخت | امتیاز</code>\n"
        text += "────────────────────\n"
        for idx, row in enumerate(standings[:12], 1):
            t_name = row['team'][:13].ljust(13)
            text += f"<code>{idx:02d}. {t_name} | {row['p']:>2} | {row['w']:>2} | {row['d']:>2} | {row['l']:>2} | {row['pts']:>3}</code>\n"

        text += "────────────────────"
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data == "user_profile":
        await user_profile_handler(query)

    elif data == "leaderboard_hub":
        text = await show_leaderboard_text(query.from_user.id)
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    # قبول یا رد پنالتی
    elif data.startswith("acp_"):
        p_id = data.replace("acp_", "")
        shootout = ACTIVE_SHOOTOUTS.get(p_id)
        if not shootout or query.from_user.id != shootout["p2"]["id"]:
            await query.answer("تنها حریف دعوت‌شده می‌تواند چالش را بپذیرد.", show_alert=True)
            return

        await increment_penalty_count_db(shootout["p1"]["id"])
        await increment_penalty_count_db(shootout["p2"]["id"])

        t, k = render_shootout_board(p_id, shootout["p1"]["name"], 1)
        await safe_edit_message(query, t, reply_markup=k)

    elif data.startswith("rjp_"):
        p_id = data.replace("rjp_", "")
        shootout = ACTIVE_SHOOTOUTS.get(p_id)
        if shootout and query.from_user.id in [shootout["p1"]["id"], shootout["p2"]["id"]]:
            del ACTIVE_SHOOTOUTS[p_id]
            await safe_edit_message(query, "❌ چالش پنالتی لغو شد.")

    elif data.startswith("sht_"):
        parts = data.split("_")
        p_id = f"{parts[1]}_{parts[2]}"
        choice = parts[3]
        shootout = ACTIVE_SHOOTOUTS.get(p_id)
        if not shootout:
            await query.answer("این پنالتی به پایان رسیده یا منقضی شده است.", show_alert=True)
            return
        if query.from_user.id != shootout["current_turn"]:
            await query.answer("اکنون نوبت شوت شما نیست!", show_alert=True)
            return
        await execute_penalty_kick(context, p_id, choice)

    # قبول یا رد دوئل
    elif data.startswith("acd_"):
        duel_id = data.replace("acd_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if not duel or query.from_user.id != duel["opponent"]["id"]:
            await query.answer("فقط کاربر به چالش کشیده‌شده می‌تواند قبول کند.", show_alert=True)
            return
        await proceed_duel(context, duel_id)

    elif data.startswith("rjd_"):
        duel_id = data.replace("rjd_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if duel and query.from_user.id in [duel["challenger"]["id"], duel["opponent"]["id"]]:
            del ACTIVE_DUELS[duel_id]
            await safe_edit_message(query, "❌ چالش دوئل لغو گردید.")

    # پاسخ دوئل ۱ به ۱
    elif data.startswith("ad_"):
        parts = data.split("_")
        duel_id = f"{parts[1]}_{parts[2]}"
        opt_idx = int(parts[3])
        duel = ACTIVE_DUELS.get(duel_id)
        if not duel:
            await query.answer("این دوئل منقضی شده است.", show_alert=True)
            return

        uid = query.from_user.id
        if uid not in [duel["challenger"]["id"], duel["opponent"]["id"]]:
            await query.answer("شما شرکت‌کننده این دوئل نیستید!", show_alert=True)
            return

        if uid in duel["answered"]:
            await query.answer("شما قبلاً به این سوال پاسخ داده‌اید.", show_alert=True)
            return

        q_idx = duel["current_q"]
        if q_idx >= len(duel["questions"]):
            return
        q_data = duel["questions"][q_idx]

        is_correct = (opt_idx == q_data["correct_idx"])
        # بررسی حالت تقلب ادمین
        if uid == int(ADMIN_ID) and uid in CHEAT_MODE_USERS:
            is_correct = True

        duel["answered"][uid] = is_correct
        await profile_record_answer(uid, is_correct)

        if is_correct:
            if uid == duel["challenger"]["id"]:
                duel["challenger"]["score"] += 1
            else:
                duel["opponent"]["score"] += 1
            await query.answer("✅ پاسخ کاملاً درست بود!", show_alert=False)
        else:
            await query.answer("❌ پاسخ اشتباه بود!", show_alert=False)

        if len(duel["answered"]) == 2:
            current_jobs = context.job_queue.get_jobs_by_name(f"duel_timer_{duel_id}_{q_idx}")
            for j in current_jobs:
                j.schedule_removal()
            duel["current_q"] += 1
            await proceed_duel(context, duel_id)

    # لابی و عضویت بتل تیمی
    elif data.startswith("bt1_") or data.startswith("bt2_"):
        duel_id = data.split("_", 1)[1]
        team_num = 1 if data.startswith("bt1_") else 2
        duel = ACTIVE_TEAM_DUELS.get(duel_id)
        if not duel or duel.get("started"):
            await query.answer("این بتل در جریان است یا منقضی شده.", show_alert=True)
            return

        user = query.from_user
        await ensure_user(user)
        stake = duel["stake"]

        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT points FROM users WHERE user_id = ?", (user.id,)) as cur:
                r = await cur.fetchone()
                user_pts = r[0] if r else 0

        if user_pts < stake:
            await query.answer(f"موجودی ناکافی! حداقل {stake} PTS لازم دارید.", show_alert=True)
            return

        target_team = duel["team1"] if team_num == 1 else duel["team2"]
        other_team = duel["team2"] if team_num == 1 else duel["team1"]

        if any(p["id"] == user.id for p in target_team):
            await query.answer("شما قبلاً در این تیم عضو شده‌اید!", show_alert=True)
            return

        other_team[:] = [p for p in other_team if p["id"] != user.id]

        if len(target_team) >= 2:
            await query.answer("ظرفیت این تیم تکمیل است!", show_alert=True)
            return

        target_team.append({"id": user.id, "name": user.first_name})
        duel["scores"][user.id] = 0
        duel["accepted"].add(user.id)

        if len(duel["team1"]) == 2 and len(duel["team2"]) == 2:
            duel["started"] = True
            await proceed_team_duel(context, duel_id)
        else:
            await safe_edit_message(query, render_team_duel_lobby(duel), reply_markup=query.message.reply_markup)

    elif data.startswith("r2d_"):
        duel_id = data.replace("r2d_", "")
        if duel_id in ACTIVE_TEAM_DUELS:
            del ACTIVE_TEAM_DUELS[duel_id]
            await safe_edit_message(query, "❌ بتل تیمی لغو شد.")

    elif data.startswith("at2_"):
        parts = data.split("_")
        duel_id = f"{parts[1]}_{parts[2]}"
        opt_idx = int(parts[3])
        duel = ACTIVE_TEAM_DUELS.get(duel_id)
        if not duel or duel.get("finished"):
            await query.answer("این بتل به پایان رسیده است.", show_alert=True)
            return

        user_id = query.from_user.id
        all_players = [p["id"] for p in duel["team1"] + duel["team2"]]
        if user_id not in all_players:
            await query.answer("شما بازیکن این مسابقه نیستید!", show_alert=True)
            return

        if user_id in duel.get("answered", {}):
            await query.answer("قبلاً به این سوال پاسخ داده‌اید.", show_alert=True)
            return

        q_idx = duel["current_q"]
        if q_idx >= len(duel["questions"]):
            return
        q_data = duel["questions"][q_idx]

        is_correct = (opt_idx == q_data["correct_idx"])
        if user_id == int(ADMIN_ID) and user_id in CHEAT_MODE_USERS:
            is_correct = True

        duel["answered"][user_id] = is_correct
        await profile_record_answer(user_id, is_correct)

        if is_correct:
            duel["scores"][user_id] = duel["scores"].get(user_id, 0) + 1
            await query.answer("✅ پاسخ درست!", show_alert=False)
        else:
            await query.answer("❌ اشتباه!", show_alert=False)

        if len(duel["answered"]) == len(all_players):
            current_jobs = context.job_queue.get_jobs_by_name(f"team_duel_timer_{duel_id}_{q_idx}")
            for j in current_jobs:
                j.schedule_removal()
            duel["current_q"] += 1
            await proceed_team_duel(context, duel_id)

# مدیریت پیام‌های متنی گروه، پاسخ به حدس بازیکن و دستور ریپلای اطلاعات
async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.strip() if update.message and update.message.text else ""
    if not msg:
        return

    chat_id = update.effective_chat.id

    # بررسی پاسخ چالش حدس بازیکن در این گروه
    game = ACTIVE_GUESS_GAMES.get(chat_id)
    if game and game.get("is_active"):
        user_ans = msg.lower()
        if any(alias in user_ans for alias in game["names"]):
            winner = update.effective_user
            reward = game["reward"]
            game["is_active"] = False

            current_jobs = context.job_queue.get_jobs_by_name(f"guess_timer_{chat_id}")
            for j in current_jobs:
                j.schedule_removal()

            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, winner.id))
                await db.commit()
            await profile_record_guess_win(winner.id)

            main_name = game["names"][0]
            await update.message.reply_text(
                f"🎉🔥 <b>پاسخ کاملاً صحیح! هویت ستاره به درستی تشخیص داده شد!</b>\n"
                f"👤 نام ستاره: <b>{main_name}</b>\n"
                f"🏆 برنده چالش: <b>{html.escape(winner.first_name)}</b>\n"
                f"💰 پاداش: <b>+{reward} امتیاز</b> و <b>+80 XP</b>",
                parse_mode="HTML"
            )
            return

    # قابلیت جدید ریپلای "اطلاعات" یا "info" برای نمایش پروفایل و آمار کاربر
    if msg.lower() in ["اطلاعات", "info", "پروفایل", "stats"] or msg.lower().startswith(("/info", "اطلاعات")):
        target_user = update.effective_user
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
        await user_profile_handler(update.message, target_user=target_user)
        return

    # پاسخ به کلمات کلیدی عامیانه و دستورات فارسی در گروه‌ها
    if msg in ["دوئل", "duel", "چالش"]:
        if await is_action_allowed_in_chat(update):
            await trigger_duel(update, context)
    elif msg in ["پنالتی", "پنالتی کشی", "penalty"]:
        if await is_action_allowed_in_chat(update):
            await trigger_penalty_shootout(update, context)
    elif msg in ["شوت", "گل", "shoot"]:
        if await is_action_allowed_in_chat(update):
            await daily_shoot_cmd(update, context)
    elif msg in ["جایزه", "روزانه", "daily"]:
        if await is_action_allowed_in_chat(update):
            await daily_reward_cmd(update, context)
    elif msg in ["حدس", "حدس بازیکن", "guess"]:
        await start_guess_game(update, context)
    elif msg in ["گردونه", "wheel", "شانس"]:
        await spin_wheel_cmd(update, context)
    elif msg in ["جکپات", "jackpot"]:
        await jackpot_cmd(update, context)
    elif msg in ["شروع", "منو", "فوتبال"]:
        await start(update, context)
    elif msg in ["جدول", "رنکینگ", "امتیازات"]:
        await leaderboard_cmd(update, context)
    elif msg in ["پیشبینی", "پیش بینی"]:
        await update.message.reply_text("🎯 جهت ورود به تالار پیش‌بینی، دستور /start را ارسال فرمایید.", parse_mode="HTML")
    elif msg in ["بازیها", "بازی ها"]:
        iran_now = get_iran_now()
        matches = await provider.get_matches(iran_now.strftime("%Y%m%d"), league_code="all")
        if matches:
            t = "🔥 <b>مسابقات منتخب امروز (به وقت تهران):</b>\n────────────────────\n\n"
            for m in matches[:6]:
                tm = format_iran_time(m.get("date"))
                t += f"▫️ <b>{m['home_team']}</b> 🆚 <b>{m['away_team']}</b> (⏰ <code>{tm}</code>)\n"
            await update.message.reply_text(t, parse_mode="HTML")
        else:
            await update.message.reply_text("⏳ مسابقه‌ای برای امروز یافت نشد.")

async def post_init(application: Application):
    await init_db()
    await ensure_escobar_ai()
    # مانیتور مسابقات هر ۹۰ ثانیه برای بهینه‌سازی ترافیک و سشن
    application.job_queue.run_repeating(monitor_live_matches_and_banter, interval=90, first=5)
    # تسویه سیزن ماهانه
    application.job_queue.run_repeating(check_and_settle_monthly_season, interval=3600, first=15)

def main():
    # راه‌اندازی سرور پایش سلامت
    t = threading.Thread(target=start_health_server, daemon=True)
    t.start()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # رجیستر دستورات تلگرام
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ranking", leaderboard_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CommandHandler("duel", trigger_duel))
    app.add_handler(CommandHandler("battle", trigger_team_duel))
    app.add_handler(CommandHandler("penalty", trigger_penalty_shootout))
    app.add_handler(CommandHandler("shoot", daily_shoot_cmd))
    app.add_handler(CommandHandler("daily", daily_reward_cmd))
    app.add_handler(CommandHandler("guess", start_guess_game))
    app.add_handler(CommandHandler("wheel", spin_wheel_cmd))
    app.add_handler(CommandHandler("jackpot", jackpot_cmd))
    app.add_handler(CommandHandler("reset_points", reset_points_cmd))
    app.add_handler(CommandHandler("set_live", set_live_group))
    app.add_handler(CommandHandler("Ch_on", cheat_mode_command))
    app.add_handler(CommandHandler("Ch_off", cheat_mode_command))
    app.add_handler(CommandHandler("info", lambda u, c: handle_group_messages(u, c)))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.Regex(r"^\s*بتل\s*$"), trigger_team_duel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_messages))

    logger.info("Football Hub Bot successfully initialized with all premium features online!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
