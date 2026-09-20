import os
import threading
import logging
import random
import asyncio
import html
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
import aiosqlite

from config import BOT_TOKEN, ADMIN_ID, DATABASE_PATH
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

def get_iran_now():
    return datetime.now(IRAN_TZ)

def format_iran_time(utc_date_str):
    if not utc_date_str:
        return "--:--"
    try:
        clean_str = utc_date_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(clean_str)
        dt_iran = dt_utc.astimezone(IRAN_TZ)
        return dt_iran.strftime("%H:%M")
    except Exception:
        return "20:00"

def get_user_tier(points: int) -> str:
    if points >= 300:
        return "💎 Legend"
    elif points >= 200:
        return "🥇 Master"
    elif points >= 130:
        return "🥈 Pro"
    else:
        return "🥉 Rookie"

class SimpleHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Football Hub Live Engine Online! 200 OK")

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHealthServer)
    logger.info(f"Health server on port {port}")
    server.serve_forever()

LEAGUE_TITLES = {
    "eng.1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",
    "esp.1": "🇪🇸 La Liga",
    "ita.1": "🇮🇹 Serie A",
    "ger.1": "🇩🇪 Bundesliga",
    "fra.1": "🇫🇷 Ligue 1",
    "all": "🌍 Top European Matches"
}

# بانک بزرگ و جامع بازیکنان برای چالش حدس با ساختار شیک
RAW_GUESS_PLAYERS = [
    {
        "nation": "آرژانتین 🇦🇷",
        "pos": "وینگر راست / مهاجم کاذب",
        "career": ["بارسلونا 🇪🇸", "پاری‌سن‌ژرمن 🇫🇷", "اینتر میامی 🇺🇸"],
        "clue": "۸ توپ طلا، قهرمان جام جهانی قطر و اسطوره ابدی لئو 🐐",
        "names": ["مسی", "لیونل مسی", "messi"]
    },
    {
        "nation": "پرتغال 🇵🇹",
        "pos": "مهاجم نوک / وینگر چپ",
        "career": ["اسپورتینگ لیسبون 🇵🇹", "منچستریونایتد 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "رئال مادرید 🇪🇸", "یوونتوس 🇮🇹", "النصر 🇸🇦"],
        "clue": "آقای گل تاریخ فوتبال با پیراهن افسانه‌ای شماره ۷ CR7 🔥",
        "names": ["رونالدو", "کریستیانو رونالدو", "کریس رونالدو", "ronaldo", "cr7"]
    },
    {
        "nation": "نروژ 🇳🇴",
        "pos": "مهاجم نوک قاتل",
        "career": ["سالزبورگ 🇦🇹", "دورتموند 🇩🇪", "منچسترسیتی 🏴󠁧󠁢󠁥󠁮󠁧󠁿"],
        "clue": "ملقب به سایبورگ و ترمیناتور، شکننده تمام رکوردهای گلزنی لیگ جزیره 🤖",
        "names": ["هالند", "ارلینگ هالند", "haaland"]
    },
    {
        "nation": "اسپانیا 🇪🇸",
        "pos": "وینگر راست تکنیکی",
        "career": ["لاماسیا 🇪🇸", "بارسلونا 🇪🇸"],
        "clue": "پدیده ۱۷ ساله با براکت ارتودنسی و درخشش خیره‌کننده در یورو ۲۰۲۴ ⚡️",
        "names": ["یامال", "لامین یامال", "yamal"]
    },
    {
        "nation": "فرانسه 🇫🇷",
        "pos": "وینگر چپ / مهاجم",
        "career": ["موناکو 🇫🇷", "پاری‌سن‌ژرمن 🇫🇷", "رئال مادرید 🇪🇸"],
        "clue": "هت‌تریک در فینال جام جهانی و سرعت سرسام‌آور ملقب به لاکپشت نینجا 🐢",
        "names": ["امباپه", "کیلیان امباپه", "mbappe"]
    },
    {
        "nation": "انگلیس 🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "pos": "هافبک هجومی باکس‌تو‌باکس",
        "career": ["بیرمنگام 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "دورتموند 🇩🇪", "رئال مادرید 🇪🇸"],
        "clue": "پسر طلایی سانتیاگو برنابئو با شادی گل باز کردن دست‌ها 🙌",
        "names": ["بلینگام", "جود بلینگام", "bellingham"]
    },
    {
        "nation": "مصر 🇪🇬",
        "pos": "وینگر راست سرعتی",
        "career": ["بازل 🇨🇭", "چلسی 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "فیورنتینا 🇮🇹", "رم 🇮🇹", "لیورپول 🏴󠁧󠁢󠁥󠁮󠁧󠁿"],
        "clue": "فرعون آنفیلد و یکی از برترین گلزنان تاریخ لیگ برتر انگلیس 👑",
        "names": ["صلاح", "محمد صلاح", "salah"]
    },
    {
        "nation": "برزیل 🇧🇷",
        "pos": "وینگر چپ",
        "career": ["فلامینگو 🇧🇷", "رئال مادرید 🇪🇸"],
        "clue": "زننده گل قهرمانی در ۲ فینال چمپیونزلیگ با تکنیک رقص سامبا 🕺",
        "names": ["وینیسیوس", "وینی", "vinicius", "vini"]
    },
    {
        "nation": "لهستان 🇵🇱",
        "pos": "مهاجم هدف کلاسیک",
        "career": ["لخ پوزنان 🇵🇱", "دورتموند 🇩🇪", "بایرن مونیخ 🇩🇪", "بارسلونا 🇪🇸"],
        "clue": "ثبت رکورد افسانه‌ای ۴۱ گل در یک فصل بوندسلیگا 🎯",
        "names": ["لواندوفسکی", "لوا", "lewandowski"]
    },
    {
        "nation": "کرواسی 🇭🇷",
        "pos": "هافبک میانی بازی‌ساز",
        "career": ["دینامو زاگرب 🇭🇷", "تاتنهام 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "رئال مادرید 🇪🇸"],
        "clue": "برنده توپ طلای ۲۰۱۸ با پاس‌های بیرون پای استثنایی 🪄",
        "names": ["مودریچ", "لوکا مودریچ", "modric"]
    },
    {
        "nation": "بلژیک 🇧🇪",
        "pos": "مهندس و هافبک طراح",
        "career": ["خنک 🇧🇪", "چلسی 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "ولفسبورگ 🇩🇪", "منچسترسیتی 🏴󠁧󠁢󠁥󠁮󠁧󠁿"],
        "clue": "سلطان پاس گل دنیا با دید ۳۶۰ درجه در تیم پپ گواردیولا 📐",
        "names": ["دی بروینه", "کوین دی بروینه", "دیبروینه", "de bruyne"]
    },
    {
        "nation": "آلمان 🇩🇪",
        "pos": "هافبک هجومی / وینگر",
        "career": ["چلسی 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "بایرن مونیخ 🇩🇪"],
        "clue": "دریبل‌زن‌ترین جواهر ژرمن‌ها با لقب بامبی 🦌",
        "names": ["موسیالا", "جمال موسیالا", "musiala"]
    },
    {
        "nation": "اروگوئه 🇺🇾",
        "pos": "موتور خستگی‌ناپذیر میانه میدان",
        "career": ["پنیارول 🇺🇾", "دپورتیوو لاکرونیا 🇪🇸", "رئال مادرید 🇪🇸"],
        "clue": "معروف به شاهین (ال هاکون) با شوت‌های موشکی و ریه‌های بی‌پایان 🦅",
        "names": ["والورده", "فدریکو والورده", "valverde"]
    },
    {
        "nation": "اسپانیا 🇪🇸",
        "pos": "مغز متفکر میانه زمین",
        "career": ["لاس پالماس 🇪🇸", "بارسلونا 🇪🇸"],
        "clue": "پسر طلایی کاتالونیا با سبک بازی چشم‌نواز مشابه اینیستا 🎩",
        "names": ["پدری", "pedri"]
    },
    {
        "nation": "برزیل 🇧🇷",
        "pos": "وینگر فانتزی",
        "career": ["سانتوس 🇧🇷", "بارسلونا 🇪🇸", "پاری‌سن‌ژرمن 🇫🇷", "الهلال 🇸🇦"],
        "clue": "گران‌ترین انتقال تاریخ فوتبال (۲۲۲ میلیون یورو) و پادشاه تکنیک خیابانی 🤙",
        "names": ["نیمار", "neymar"]
    }
]

GUESS_DECK = []

def get_next_guess_player():
    global GUESS_DECK
    if not GUESS_DECK:
        GUESS_DECK = RAW_GUESS_PLAYERS[:]
        random.shuffle(GUESS_DECK)
    return GUESS_DECK.pop()

ACTIVE_GUESS_GAME = None
MATCH_CACHE = {}
ACTIVE_DUELS = {}
ACTIVE_SHOOTOUTS = {}
TRACKED_LIVE_MATCHES = {}

# -------------------------------------------------------------
# توابع خواندن و نوشتن دائمی در دیتابیس (بدون پریدن در ری‌دیپلو)
# -------------------------------------------------------------
async def get_live_chat_id():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = 'live_chat_id'") as cur:
            row = await cur.fetchone()
            if row and row[0]:
                return int(row[0])
    return None

async def is_action_allowed_in_chat(update: Update) -> bool:
    chat = update.effective_chat
    if chat.type == "private":
        return True
    target_chat_id = await get_live_chat_id()
    if not target_chat_id or chat.id == target_chat_id:
        return True
    await update.effective_message.reply_text(
        "⛔️ <b>بخش‌های مسابقاتی و امتیازی فقط در گروه اصلی فعال است!</b>\n"
        "▫️ سایر بخش‌ها از جمله جداول رده‌بندی، مسابقات و نتایج برای همه در دسترس است.",
        parse_mode="HTML"
    )
    return False

async def safe_edit_message(query_or_bot, text, reply_markup=None, chat_id=None, message_id=None):
    try:
        if chat_id and message_id:
            await query_or_bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        else:
            await query_or_bot.message.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
    except Exception:
        pass

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

async def remove_unwanted_users():
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("DELETE FROM users WHERE first_name LIKE '%ՏᎻᎪΝͲᏆᎪ%' OR first_name LIKE '%شنتیا%'")
            await db.commit()
    except Exception as e:
        logger.error(f"Error removing user: {e}")

# تابع مدیریت پنالتی‌های روزانه در دیتابیس
async def get_penalty_count_db(user_id: int) -> int:
    today_str = get_iran_now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT penalty_date, penalty_count FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                return row[1]
    return 0

async def increment_penalty_count_db(user_id: int):
    today_str = get_iran_now().strftime("%Y-%m-%d")
    cur_count = await get_penalty_count_db(user_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE users SET penalty_date = ?, penalty_count = ? WHERE user_id = ?
        """, (today_str, cur_count + 1, user_id))
        await db.commit()

async def reset_points_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID):
        await update.message.reply_text("⛔️ دسترسی غیرمجاز! فقط ادمین اصلی می‌تواند این دستور را اجرا کند.")
        return
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE users SET points = 100")
            await db.commit()
        await update.message.reply_text("✅ <b>امتیاز تمامی کاربران با موفقیت روی ۱۰۰ ریست شد!</b>\nبردها بدون تغییر باقی ماندند.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error resetting points: {e}")
        await update.message.reply_text("❌ خطا در اجرای ریست امتیازات.")

async def set_live_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in ["group", "supergroup"]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('live_chat_id', ?)", (str(chat.id),))
            await db.commit()
        await update.message.reply_text(
            f"✅ <b>این گروه با موفقیت به عنوان گروه اختصاصی مسابقات و گزارش زنده ثبت شد!</b> 🏟🔥\n"
            f"شناسه گروه: <code>{chat.id}</code>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("⚠️ این دستور باید در گروه ارسال شود.")

async def record_ai_prediction_if_needed(match_id: str):
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT id FROM predictions WHERE user_id = ? AND match_id = ?", (ESCOBAR_AI_ID, match_id)) as cur:
                if await cur.fetchone():
                    return
            ai_choice = random.choices(["HOME", "DRAW", "AWAY"], weights=[45, 25, 30])[0]
            await db.execute("""
                INSERT INTO predictions (user_id, match_id, outcome_choice, predicted_home, predicted_away)
                VALUES (?, ?, ?, 0, 0)
            """, (ESCOBAR_AI_ID, match_id, ai_choice))
            await db.execute("UPDATE users SET points = points + 10, total_predictions = total_predictions + 1 WHERE user_id = ?", (ESCOBAR_AI_ID,))
            await db.commit()
    except Exception as e:
        logger.error(f"Error in record_ai_prediction: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    if context.args and len(context.args) > 0:
        referrer_id_str = context.args[0]
        if referrer_id_str.isdigit() and int(referrer_id_str) != user.id:
            ref_id = int(referrer_id_str)
            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute("SELECT points FROM users WHERE user_id = ?", (ref_id,)) as cur:
                    if await cur.fetchone():
                        await db.execute("UPDATE users SET points = points + 30 WHERE user_id = ?", (ref_id,))
                        await db.execute("UPDATE users SET points = points + 20 WHERE user_id = ?", (user.id,))
                        await db.commit()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT points FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            pts = row[0] if row else 100

    tier = get_user_tier(pts)
    safe_name = html.escape(user.first_name)

    text = (
        f"⚽️ <b>FOOTBALL HUB</b>\n"
        f"────────────────────\n"
        f"👤 بازیکن: <b>{safe_name}</b>\n"
        f"⚡️ موجودی: <code>{pts} PTS</code>  ▫️  سطح: <b>{tier}</b>\n"
        f"────────────────────\n"
        f"جهت دسترسی به بخش‌های ربات از منوی زیر استفاده کنید:"
    )

    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb.get_main_menu())
    else:
        await update.message.reply_text(text, reply_markup=kb.get_main_menu(), parse_mode="HTML")

async def show_leaderboard_text():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT first_name, points, duel_wins FROM users ORDER BY points DESC, duel_wins DESC") as cur:
            all_users = await cur.fetchall()

    text = "🏆 <b>جدول رده‌بندی کاربران</b>\n"
    text += "────────────────────\n\n"
    if not all_users:
        text += "هنوز کاربری ثبت نشده است.\n"
    else:
        for idx, u in enumerate(all_users, 1):
            name, pts, wins = u[0], max(0, u[1]), u[2]
            rank_badge = "🥇" if idx == 1 else ("🥈" if idx == 2 else ("🥉" if idx == 3 else f"{idx:02d}."))
            safe_name = html.escape(str(name))
            tier = get_user_tier(pts)

            text += f"{rank_badge} <b>{safe_name}</b>  <i>({tier})</i>\n"
            text += f"    ⚡️ <code>{pts} PTS</code>  ▫️  ⚔️ <code>{wins} برد</code>\n\n"
    text += "────────────────────"
    return text

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await show_leaderboard_text()
    await update.message.reply_text(text, parse_mode="HTML")

# جایزه روزانه کاملاً ثبت‌شده در دیتابیس
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
                    f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، پاداش روزانه امروز خود را دریافت کرده‌اید!\nفردا برای پاداش جدید سر بزنید.",
                    parse_mode="HTML"
                )
                return

        reward = 20
        await db.execute("UPDATE users SET points = points + ?, last_daily_date = ? WHERE user_id = ?", (reward, today_str, user.id))
        await db.commit()

    await update.effective_message.reply_text(
        f"🎁 <b>پاداش روزانه با موفقیت واریز شد!</b>\n"
        f"💰 <b>+{reward} امتیاز</b> به حساب شما اضافه شد.",
        parse_mode="HTML"
    )

# شوت روزانه کاملاً ثبت‌شده در دیتابیس
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
                    f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، شوت روزانه امروز خود را زده‌اید!\nفردا دوباره شانس‌ات را امتحان کن.",
                    parse_mode="HTML"
                )
                return

        await db.execute("UPDATE users SET last_shoot_date = ? WHERE user_id = ?", (today_str, user.id))
        await db.commit()

    msg = await update.effective_message.reply_dice(emoji="⚽")
    dice_val = msg.dice.value

    await asyncio.sleep(2.5)

    if dice_val in [3, 4, 5]:
        reward = 15
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, user.id))
            await db.commit()

        await update.effective_message.reply_text(
            f"⚽️🔥 <b>گـُـل شد! ضربه مهارنشدنی!</b>\n"
            f"💰 پاداش: <b>+{reward} امتیاز</b> دریافت کردید.",
            parse_mode="HTML"
        )
    else:
        await update.effective_message.reply_text(
            "🧤❌ <b>توپ گل نشد!</b> (برخورد به تیرک یا مهار سنگربان)\nفردا دوباره امتحان کن.",
            parse_mode="HTML"
        )

# گردونه شانس کاملاً ثبت‌شده در دیتابیس
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
                    f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، امروز گردونه را چرخانده‌اید!\nفردا برای شانس بعدی سر بزنید.",
                    parse_mode="HTML"
                )
                return

        await db.execute("UPDATE users SET last_wheel_date = ? WHERE user_id = ?", (today_str, user.id))
        await db.commit()

    prizes = [10, 15, 20, 25, 40, 50, 0]
    weights = [30, 25, 20, 12, 8, 3, 2]
    win = random.choices(prizes, weights=weights)[0]

    async with aiosqlite.connect(DATABASE_PATH) as db:
        if win > 0:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (win, user.id))
            await db.commit()

    if win > 0:
        msg = f"🎡 <b>گردونه متوقف شد!</b>\n🎉 تبریک <b>{html.escape(user.first_name)}</b>، شما برنده <b>+{win} امتیاز</b> شدید!"
    else:
        msg = f"🎡 <b>گردونه متوقف شد!</b>\n❌ این‌بار پوچ بود! فردا دوباره شانس‌ات را امتحان کن."

    await update.effective_message.reply_text(msg, parse_mode="HTML")

# مینی‌گیم شیک و بدون به‌هم‌ریختگی حدس بازیکن با سقف ۱ بار در روز
async def start_guess_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update):
        return

    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT last_guess_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                await update.effective_message.reply_text(
                    f"⛔️ <b>{html.escape(user.first_name)}</b> عزیز، شما امروز سهمیه ۱ حدس بازیکن خود را استفاده کرده‌اید!\nفردا دوباره چالش را امتحان کنید.",
                    parse_mode="HTML"
                )
                return

    global ACTIVE_GUESS_GAME
    if ACTIVE_GUESS_GAME and ACTIVE_GUESS_GAME.get("is_active"):
        await update.effective_message.reply_text("⚠️ یک مسابقه حدس بازیکن در جریان است! ابتدا پاسخ آن را ارسال کنید.")
        return

    p = get_next_guess_player()

    career_str = "\n".join([f"  {idx}. {club}" for idx, club in enumerate(p['career'], 1)])

    ACTIVE_GUESS_GAME = {
        "names": p["names"],
        "reward": 25,
        "chat_id": update.effective_chat.id,
        "is_active": True
    }

    text = (
        "🕵️‍♂️ <b>پرونده اطلاعاتی: ستاره فوتبال را شناسایی کنید!</b>\n"
        "────────────────────\n"
        f"🌍 <b>ملیت:</b> {p['nation']}\n"
        f"📌 <b>پست:</b> {p['pos']}\n\n"
        f"🏟 <b>مسیر باشگاهی:</b>\n{career_str}\n\n"
        f"⭐️ <b>سرنخ ویژه:</b>\n{p['clue']}\n"
        "────────────────────\n"
        "💰 جایزه: <b>+25 امتیاز</b>\n"
        "⚡️ اولین نفری که نام بازیکن را ارسال کند برنده است!"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def jackpot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎰 <b>پیش‌بینی زنجیره‌ای جک‌پات (Jackpot Combo)</b>\n"
        "────────────────────\n"
        "💰 استخر جایزه طلایی: <b>500 امتیاز</b> 🪙\n"
        "▫️ شرط برنده شدن: پیش‌بینی صحیح هر ۵ مسابقه منتخب هفته\n"
        "▫️ در صورت عدم برنده، جایزه به استخر مسابقه بعد منتقل می‌شود.\n\n"
        "⚠️ فرم جدید جک‌پات در روزهای مسابقات بزرگ فعال خواهد شد!"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
    else:
        await update.message.reply_text(text, parse_mode="HTML")

# پنالتی تک‌ضرب با سقف ۲ بار در روز ذخیره‌شده در دیتابیس
async def trigger_penalty_shootout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "🥅 <b>نحوه شروع پنالتی:</b>\nروی پیام حریف در گروه ریپلای کنید و بنویسید: <code>پنالتی</code> یا <code>/penalty</code>",
            parse_mode="HTML"
        )
        return

    challenger = update.effective_user
    opponent = update.message.reply_to_message.from_user

    if opponent.is_bot or challenger.id == opponent.id:
        await update.message.reply_text("⚠️ امکان مسابقه با این کاربر وجود ندارد.")
        return

    c_count = await get_penalty_count_db(challenger.id)
    if c_count >= 2:
        await update.message.reply_text(f"⛔️ <b>{html.escape(challenger.first_name)}</b> عزیز، شما سقف مجاز ۲ پنالتی در روز خود را مصرف کرده‌اید!", parse_mode="HTML")
        return

    o_count = await get_penalty_count_db(opponent.id)
    if o_count >= 2:
        await update.message.reply_text(f"⛔️ حریف شما <b>{html.escape(opponent.first_name)}</b> امروز ۲ پنالتی خود را بازی کرده است!", parse_mode="HTML")
        return

    await ensure_user(challenger)
    await ensure_user(opponent)

    p_id = str(random.randint(10000, 99999))
    ACTIVE_SHOOTOUTS[p_id] = {
        "p1": {"id": challenger.id, "name": challenger.first_name, "shot": None},
        "p2": {"id": opponent.id, "name": opponent.first_name, "shot": None},
        "current_turn": challenger.id,
        "round": 1,
        "stake": 25,
        "chat_id": update.effective_chat.id,
        "message_id": None
    }

    p_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧤 قبول پنالتی تک‌ضرب", callback_data=f"acp_{p_id}"),
         InlineKeyboardButton("❌ انصراف", callback_data=f"rjp_{p_id}")]
    ])

    c_name = html.escape(challenger.first_name)
    o_name = html.escape(opponent.first_name)

    text = (
        "🥅 <b>دوئل تک‌ضرب پنالتی (مرگ ناگهانی)!</b> ⚽️\n"
        "────────────────────\n"
        f"👤 شوت‌زن اول: <b>{c_name}</b> ({c_count + 1}/2)\n"
        f"👤 شوت‌زن دوم: <b>{o_name}</b> ({o_count + 1}/2)\n"
        "💰 شرط مسابقه: <b>25 امتیاز</b> 🪙\n"
        "────────────────────\n"
        f"آیا <b>{o_name}</b> چالش را می‌پذیرد؟"
    )
    sent_msg = await update.message.reply_text(text, reply_markup=p_kb, parse_mode="HTML")
    ACTIVE_SHOOTOUTS[p_id]["message_id"] = sent_msg.message_id

def render_shootout_board(shootout):
    p1 = shootout["p1"]
    p2 = shootout["p2"]
    p1_status = p1["shot"] if p1["shot"] else "⏳ در انتظار شوت..."
    p2_status = p2["shot"] if p2["shot"] else "⏳ در انتظار شوت..."
    cur_shooter = p1["name"] if shootout["current_turn"] == p1["id"] else p2["name"]

    text = (
        f"🥅 <b>راند طلایی {shootout['round']}:</b>\n"
        "────────────────────\n"
        f"👤 <b>{html.escape(p1['name'])}</b>: {p1_status}\n"
        f"👤 <b>{html.escape(p2['name'])}</b>: {p2_status}\n"
        "────────────────────\n"
        f"👉 نوبت ضربه: <b>{html.escape(cur_shooter)}</b>"
    )
    return text

async def execute_penalty_kick(query, context, p_id):
    shootout = ACTIVE_SHOOTOUTS.get(p_id)
    if not shootout:
        await query.answer("مسابقه منقضی شده است.", show_alert=True)
        return

    user_id = query.from_user.id
    if user_id != shootout["current_turn"]:
        await query.answer("⛔ نوبت شما نیست!", show_alert=True)
        return

    chat_id = shootout["chat_id"]
    dice_msg = await context.bot.send_dice(chat_id=chat_id, emoji="⚽")
    val = dice_msg.dice.value

    await asyncio.sleep(2.5)
    is_goal = (val in [3, 4, 5])
    icon = "⚽️ گل شد!" if is_goal else "❌ مهار شد!"

    if user_id == shootout["p1"]["id"]:
        shootout["p1"]["shot"] = icon
        shootout["current_turn"] = shootout["p2"]["id"]
        text = render_shootout_board(shootout)
        kick_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚽️ نوبت توئه! ضربه رو بزن", callback_data=f"shoot_pen_{p_id}")]])
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kick_kb, parse_mode="HTML")
    else:
        shootout["p2"]["shot"] = icon
        p1_goal = (shootout["p1"]["shot"] == "⚽️ گل شد!")
        p2_goal = (shootout["p2"]["shot"] == "⚽️ گل شد!")

        p1_name = html.escape(shootout["p1"]["name"])
        p2_name = html.escape(shootout["p2"]["name"])
        stake = shootout["stake"]

        if p1_goal and not p2_goal:
            await increment_penalty_count_db(shootout["p1"]["id"])
            await increment_penalty_count_db(shootout["p2"]["id"])
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, shootout["p1"]["id"]))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, shootout["p2"]["id"]))
                await db.commit()
            del ACTIVE_SHOOTOUTS[p_id]
            await context.bot.send_message(chat_id=chat_id, text=f"🏁 <b>پایان مسابقه!</b>\n🎉 تبریک به <b>{p1_name}</b>! برنده <b>{stake} امتیاز</b> شد.", parse_mode="HTML")

        elif p2_goal and not p1_goal:
            await increment_penalty_count_db(shootout["p1"]["id"])
            await increment_penalty_count_db(shootout["p2"]["id"])
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, shootout["p2"]["id"]))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, shootout["p1"]["id"]))
                await db.commit()
            del ACTIVE_SHOOTOUTS[p_id]
            await context.bot.send_message(chat_id=chat_id, text=f"🏁 <b>پایان مسابقه!</b>\n🎉 تبریک به <b>{p2_name}</b>! برنده <b>{stake} امتیاز</b> شد.", parse_mode="HTML")

        else:
            shootout["round"] += 1
            shootout["p1"]["shot"] = None
            shootout["p2"]["shot"] = None
            shootout["current_turn"] = shootout["p1"]["id"]
            await context.bot.send_message(chat_id=chat_id, text=f"🤝 <b>مساوی! راند طلایی {shootout['round']} آغاز شد.</b>", parse_mode="HTML")
            text = render_shootout_board(shootout)
            kick_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚽️ ضربه مرگ ناگهانی!", callback_data=f"shoot_pen_{p_id}")]])
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kick_kb, parse_mode="HTML")

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

    duel_id = str(random.randint(10000, 99999))
    ACTIVE_DUELS[duel_id] = {
        "challenger": {"id": challenger.id, "name": challenger.first_name, "score": 0},
        "opponent": {"id": opponent.id, "name": opponent.first_name, "score": 0},
        "questions": get_random_duel_questions(3),
        "current_q": 0,
        "stake": 25,
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
        "💰 جایزه رقابت: <b>+25 امتیاز</b> 🪙\n"
        "⏱ زمان هر سوال: <b>15 ثانیه</b> ⏳\n"
        "────────────────────\n"
        f"آیا <b>{o_name}</b> چالش را می‌پذیرد؟"
    )
    sent_msg = await update.message.reply_text(text, reply_markup=duel_kb, parse_mode="HTML")
    ACTIVE_DUELS[duel_id]["message_id"] = sent_msg.message_id

def render_duel_question_text(duel, q_data, q_idx):
    c_name = html.escape(duel["challenger"]["name"])
    o_name = html.escape(duel["opponent"]["name"])
    c_id = duel["challenger"]["id"]
    o_id = duel["opponent"]["id"]

    c_status = "✅ ثبت کرد" if c_id in duel["answered"] else "⏳ در حال پاسخ..."
    o_status = "✅ ثبت کرد" if o_id in duel["answered"] else "⏳ در حال پاسخ..."

    text = (
        f"❓ <b>سوال {q_idx + 1} از 3:</b>\n"
        "────────────────────\n"
        f"📌 <b>{html.escape(q_data['question'])}</b>\n\n"
        "⏱ مهلت پاسخ: <b>15 ثانیه</b>\n"
        "────────────────────\n"
        f"👤 {c_name}: {c_status}\n"
        f"👤 {o_name}: {o_status}\n"
    )
    return text

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

    q_idx = duel["current_q"]
    chat_id = duel["chat_id"]
    msg_id = duel["message_id"]

    if q_idx >= len(duel["questions"]):
        c_score = duel["challenger"]["score"]
        o_score = duel["opponent"]["score"]
        stake = duel["stake"]

        c_id, c_name = duel["challenger"]["id"], html.escape(duel["challenger"]["name"])
        o_id, o_name = duel["opponent"]["id"], html.escape(duel["opponent"]["name"])

        res_text = (
            "🏁 <b>پایان دوئل اطلاعات عمومی!</b>\n"
            "────────────────────\n"
            f"👤 {c_name}: <code>{c_score}/3</code>\n"
            f"👤 {o_name}: <code>{o_score}/3</code>\n"
            "────────────────────\n"
        )

        async with aiosqlite.connect(DATABASE_PATH) as db:
            if c_score > o_score:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, c_id))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, o_id))
                res_text += f"🎉 تبریک به <b>{c_name}</b>! برنده {stake} امتیاز شد."
            elif o_score > c_score:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, o_id))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, c_id))
                res_text += f"🎉 تبریک به <b>{o_name}</b>! برنده {stake} امتیاز شد."
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

async def predictions_hub_handler(query):
    iran_now = get_iran_now()
    dates = [iran_now.strftime("%Y%m%d"), (iran_now + timedelta(days=1)).strftime("%Y%m%d")]

    candidate_matches = []
    for d in dates:
        for l_code in ["eng.1", "esp.1", "ita.1", "ger.1", "uefa.champions"]:
            m_list = await provider.get_matches(d, league_code=l_code)
            candidate_matches.extend(m_list)

    upcoming_matches = [
        m for m in candidate_matches
        if str(m.get("status", "")).upper() not in ["LIVE", "FINISHED", "FT", "IN_PLAY", "HT"]
        and m.get("home_score") is None
    ]

    unique_dict = {}
    for m in upcoming_matches:
        unique_dict[m["id"]] = m
    upcoming_list = list(unique_dict.values())

    if not upcoming_list:
        await safe_edit_message(query, "⏳ در حال حاضر مسابقه‌ای آماده پیش‌بینی نیست.", reply_markup=kb.get_back_button())
        return

    for m in upcoming_list:
        MATCH_CACHE[m["id"]] = m
        await record_ai_prediction_if_needed(m["id"])

    text = (
        "🎯 <b>انتخاب مسابقه جهت ثبت پیش‌بینی:</b>\n"
        "────────────────────\n"
        "▫️ ثبت پیش‌بینی: <b>+10 امتیاز قطعی</b>\n"
        "▫️ حدس برنده درست: <b>+10 امتیاز</b> | نتیجه دقیق: <b>+15 امتیاز</b>\n"
        "🤖 <i>Escobar AI نیز در این مسابقات شرکت می‌کند!</i>\n"
        "────────────────────"
    )
    await safe_edit_message(query, text, reply_markup=kb.get_upcoming_matches_keyboard(upcoming_list))

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "home":
        await start(update, context)

    elif data == "spin_wheel":
        update.effective_user = query.from_user
        update.effective_message = query.message
        await spin_wheel_cmd(update, context)

    elif data == "jackpot_hub":
        await jackpot_cmd(update, context)

    elif data == "predictions_hub":
        await predictions_hub_handler(query)

    elif data.startswith("select_pred_"):
        match_id = data.replace("select_pred_", "")
        m = MATCH_CACHE.get(match_id)
        if not m:
            await safe_edit_message(query, "⚠️ مهلت ثبت پیش‌بینی منقضی شده است.", reply_markup=kb.get_back_button())
            return

        time_str = format_iran_time(m.get("date"))
        text = (
            f"🎯 <b>فرم ثبت پیش‌بینی:</b>\n"
            f"────────────────────\n"
            f"⚽️ <b>{m['home_team']}</b> 🆚 <b>{m['away_team']}</b>\n"
            f"⏰ ساعت شروع: <code>{time_str}</code> (تهران)\n"
            f"────────────────────\n"
            f"نتیجه را انتخاب کنید:"
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
                await safe_edit_message(query, "✅ <b>پیش‌بینی شما ثبت شد! (+10 امتیاز هدیه شرکت)</b>", reply_markup=kb.get_back_button())
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

        await query.answer("✅ پیش‌بینی شما ثبت و لیست آپدیت شد!", show_alert=False)

        m = MATCH_CACHE.get(match_id)
        if not m:
            m = {"home_team": "میزبان", "away_team": "میهمان", "date": None}

        h_name = m.get("home_team", "")
        a_name = m.get("away_team", "")
        time_str = format_iran_time(m.get("date"))

        new_text = (
            f"🚨🔥 <b>۱۵ دقیقه تا آغاز نبرد حساس! پیش‌بینی ویژه استخر ۳۰۰ امتیازی</b> 🏆\n"
            "────────────────────\n"
            f"⚽️ <b>{h_name}</b> 🆚 <b>{a_name}</b>\n"
            f"⏰ شروع بازی: <code>{time_str}</code> (به وقت تهران)\n"
            "💰 <b>استخر جایزه: ۳۰۰ امتیاز</b> 🪙\n"
            "⚡️ جایزه ۳۰۰ امتیازی بین حدس‌های درست تقسیم می‌شود!\n"
            "⏱ مهلت ثبت: تا سوت شروع بازی!\n"
            "────────────────────\n"
        )
        if participants:
            new_text += f"👥 <b>شرکت‌کنندگان تا این لحظه ({len(participants)} نفر):</b>\n"
            for uname, ch in participants:
                choice_label = f"برد {h_name[:10]}" if ch == "HOME" else ("مساوی" if ch == "DRAW" else f"برد {a_name[:10]}")
                new_text += f"▫️ <b>{html.escape(uname)}</b>: <i>{choice_label}</i>\n"
        else:
            new_text += "▫️ هنوز کسی در استخر پیش‌بینی ثبت نکرده است!\n"

        new_text += "\n👇 <b>پیش‌بینی خود را با دکمه‌های زیر ثبت کنید:</b>"
        await safe_edit_message(query, new_text, reply_markup=query.message.reply_markup)

    elif data == "select_matches_today":
        await safe_edit_message(query, "🔥 <b>لیگ مورد نظر برای مسابقات امروز را انتخاب کنید:</b>", reply_markup=kb.get_matches_leagues_keyboard("today"))

    elif data == "select_matches_tomorrow":
        await safe_edit_message(query, "📅 <b>لیگ مورد نظر برای مسابقات فردا را انتخاب کنید:</b>", reply_markup=kb.get_matches_leagues_keyboard("tmrw"))

    elif data == "select_standings_league":
        await safe_edit_message(query, "🏆 <b>جدول رده‌بندی کدام لیگ را می‌خواهید؟</b>", reply_markup=kb.get_standings_leagues_keyboard())

    elif data.startswith("today_") or data.startswith("tmrw_"):
        is_today = data.startswith("today_")
        league_code = data.replace("today_", "").replace("tmrw_", "")
        iran_now = get_iran_now()
        target_date = iran_now if is_today else iran_now + timedelta(days=1)
        matches = await provider.get_matches(target_date.strftime("%Y%m%d"), league_code="eng.1" if league_code == "all" else league_code)

        if not matches:
            await safe_edit_message(query, "مسابقه‌ای یافت نشد.", reply_markup=kb.get_back_button())
            return

        text = f"🔥 <b>مسابقات ({('امروز' if is_today else 'فردا')}):</b>\n────────────────────\n\n"
        for m in matches[:6]:
            time_str = format_iran_time(m.get("date"))
            score = f"[{m['home_score']} - {m['away_score']}]" if m.get("home_score") is not None else f"(⏰ {time_str})"
            text += f"▫️ <b>{m['home_team']}</b> 🆚 <b>{m['away_team']}</b>  <code>{score}</code>\n"
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data.startswith("table_"):
        league_code = data.replace("table_", "")
        standings = await provider.get_standings(league_code)
        if not standings:
            await safe_edit_message(query, "جدول در دسترس نیست.", reply_markup=kb.get_back_button())
            return
        text = "🏆 <b>جدول رده‌بندی</b>\n<pre>"
        text += "#  | Team          | P  | Pts\n---+---------------+----+----\n"
        for idx, s in enumerate(standings[:10], 1):
            text += f"{idx:<2} | {s['team'][:13]:<13} | {s['p']:<2} | {s['pts']:<3}\n"
        text += "</pre>"
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data == "user_profile":
        user_id = query.from_user.id
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT points, exact_predictions, correct_results, total_predictions, duel_wins FROM users WHERE user_id = ?", (user_id,)) as cur:
                u = await cur.fetchone()

        pts, exact, correct, total, dw = (u[0], u[1], u[2], u[3], u[4]) if u else (100, 0, 0, 0, 0)
        tier = get_user_tier(pts)
        safe_name = html.escape(query.from_user.first_name)
        p_today = await get_penalty_count_db(user_id)
        text = (
            f"👤 <b>پروفایل بازیکن: {safe_name}</b>\n"
            f"────────────────────\n"
            f"🌟 رتبه: <b>{tier}</b>\n"
            f"⚡️ موجودی امتیاز: <code>{pts} PTS</code>\n"
            f"🥅 پنالتی‌های بازی‌شده امروز: <code>{p_today}/2</code>\n"
            f"⚔️ بردهای دوئل: <code>{dw}</code>\n"
            f"🎯 کل پیش‌بینی‌ها: <code>{total}</code> (برنده: {correct} | دقیق: {exact})\n"
            f"────────────────────"
        )
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data == "leaderboard_hub":
        text = await show_leaderboard_text()
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data.startswith("acp_"):
        p_id = data.replace("acp_", "")
        shootout = ACTIVE_SHOOTOUTS.get(p_id)
        if not shootout or query.from_user.id != shootout["p2"]["id"]:
            await query.answer("خطا یا عدم دسترسی به مسابقه!", show_alert=True)
            return
        text = render_shootout_board(shootout)
        kick_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚽️ زدن ضربه پنالتی!", callback_data=f"shoot_pen_{p_id}")]])
        await safe_edit_message(query, text, reply_markup=kick_kb)

    elif data.startswith("rjp_"):
        p_id = data.replace("rjp_", "")
        shootout = ACTIVE_SHOOTOUTS.get(p_id)
        if shootout and query.from_user.id in [shootout["p1"]["id"], shootout["p2"]["id"]]:
            del ACTIVE_SHOOTOUTS[p_id]
            await safe_edit_message(query, "❌ مسابقه پنالتی لغو شد.")

    elif data.startswith("shoot_pen_"):
        p_id = data.replace("shoot_pen_", "")
        await execute_penalty_kick(query, context, p_id)

    elif data.startswith("acd_"):
        duel_id = data.replace("acd_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if not duel or query.from_user.id != duel["opponent"]["id"]:
            await query.answer("خطا یا عدم دسترسی به دوئل!", show_alert=True)
            return
        await proceed_duel(context, duel_id)

    elif data.startswith("rjd_"):
        duel_id = data.replace("rjd_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if duel and query.from_user.id in [duel["opponent"]["id"], duel["challenger"]["id"]]:
            del ACTIVE_DUELS[duel_id]
            await safe_edit_message(query, "❌ دوئل لغو شد.")

    elif data.startswith("ad_"):
        parts = data.split("_")
        duel_id = parts[1]
        chosen_idx = int(parts[2])
        duel = ACTIVE_DUELS.get(duel_id)

        if not duel:
            await query.answer("این دوئل تمام شده است.", show_alert=True)
            return

        user_id = query.from_user.id
        if user_id not in [duel["challenger"]["id"], duel["opponent"]["id"]] or user_id in duel["answered"]:
            await query.answer("پاسخ قبلاً ثبت شده یا شما شرکت‌کننده نیستید!", show_alert=True)
            return

        curr_q = duel["questions"][duel["current_q"]]
        is_correct = (chosen_idx == curr_q["correct_idx"])
        duel["answered"][user_id] = is_correct

        if is_correct:
            if user_id == duel["challenger"]["id"]:
                duel["challenger"]["score"] += 1
            else:
                duel["opponent"]["score"] += 1

        q_text = render_duel_question_text(duel, curr_q, duel["current_q"])
        await safe_edit_message(query, q_text, reply_markup=query.message.reply_markup)

        if len(duel["answered"]) >= 2:
            current_jobs = context.job_queue.get_jobs_by_name(f"duel_timer_{duel_id}_{duel['current_q']}")
            for j in current_jobs:
                j.schedule_removal()
            await asyncio.sleep(1)
            duel["current_q"] += 1
            await proceed_duel(context, duel_id)

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.strip() if update.message and update.message.text else ""
    if not msg:
        return

    # بررسی پاسخ مینی‌گیم حدس بازیکن
    global ACTIVE_GUESS_GAME
    if ACTIVE_GUESS_GAME and ACTIVE_GUESS_GAME.get("is_active") and ACTIVE_GUESS_GAME["chat_id"] == update.effective_chat.id:
        user_ans = msg.lower()
        if any(alias in user_ans for alias in ACTIVE_GUESS_GAME["names"]):
            winner = update.effective_user
            today_str = get_iran_now().strftime("%Y-%m-%d")

            # ثبت تاریخ حدس موفق برای برنده
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("""
                    UPDATE users SET points = points + ?, last_guess_date = ? WHERE user_id = ?
                """, (ACTIVE_GUESS_GAME["reward"], today_str, winner.id))
                await db.commit()
            
            reward = ACTIVE_GUESS_GAME["reward"]
            await update.message.reply_text(
                f"🎉🔥 <b>پاسخ کاملاً صحیح! تبریک به {html.escape(winner.first_name)}!</b>\n"
                f"💰 پاداش: <b>+{reward} امتیاز</b> دریافت کردید.",
                parse_mode="HTML"
            )
            ACTIVE_GUESS_GAME["is_active"] = False
            return

    if msg in ["دوئل", "duel", "چالش"]:
        await trigger_duel(update, context)
    elif msg in ["پنالتی", "پنالتی کشی", "penalty"]:
        await trigger_penalty_shootout(update, context)
    elif msg in ["شوت", "گل", "shoot"]:
        await daily_shoot_cmd(update, context)
    elif msg in ["جایزه", "روزانه", "daily"]:
        await daily_reward_cmd(update, context)
    elif msg in ["حدس", "حدس بازیکن", "guess"]:
        await start_guess_game(update, context)
    elif msg in ["گردونه", "wheel", "شانس"]:
        await spin_wheel_cmd(update, context)
    elif msg in ["جکپات", "jackpot"]:
        await jackpot_cmd(update, context)
    elif msg in ["شروع", "منو"]:
        await start(update, context)
    elif msg in ["جدول", "رنکینگ"]:
        await leaderboard_cmd(update, context)
    elif msg in ["پیشبینی", "پیش بینی"]:
        await update.message.reply_text("🎯 جهت ورود به تالار پیش‌بینی، دستور /start را ارسال کنید.", parse_mode="HTML")

async def post_init(application: Application):
    await init_db()
    await ensure_escobar_ai()
    await remove_unwanted_users()

def main():
    t = threading.Thread(target=start_health_server, daemon=True)
    t.start()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ranking", leaderboard_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CommandHandler("duel", trigger_duel))
    app.add_handler(CommandHandler("penalty", trigger_penalty_shootout))
    app.add_handler(CommandHandler("shoot", daily_shoot_cmd))
    app.add_handler(CommandHandler("daily", daily_reward_cmd))
    app.add_handler(CommandHandler("guess", start_guess_game))
    app.add_handler(CommandHandler("wheel", spin_wheel_cmd))
    app.add_handler(CommandHandler("jackpot", jackpot_cmd))
    app.add_handler(CommandHandler("reset_points", reset_points_cmd))
    app.add_handler(CommandHandler("set_live", set_live_group))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_messages))

    logger.info("Bot running with persistent daily activities and clean guess format!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
