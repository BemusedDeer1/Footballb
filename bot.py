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

def get_user_badge(points: int) -> str:
    if points >= 250:
        return "💎"
    elif points >= 180:
        return "🥇"
    elif points >= 120:
        return "🥈"
    else:
        return "🥉"

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

MATCH_CACHE = {}
ACTIVE_DUELS = {}
ACTIVE_SHOOTOUTS = {}
USER_LAST_SHOT = {}
USER_LAST_DAILY = {}
USER_DAILY_PENALTIES = {}
TRACKED_LIVE_MATCHES = {}

def get_penalty_count_today(user_id: int) -> int:
    today_str = get_iran_now().strftime("%Y-%m-%d")
    data = USER_DAILY_PENALTIES.get(user_id)
    if not data or data["date"] != today_str:
        return 0
    return data["count"]

def increment_penalty_count_today(user_id: int):
    today_str = get_iran_now().strftime("%Y-%m-%d")
    data = USER_DAILY_PENALTIES.get(user_id)
    if not data or data["date"] != today_str:
        USER_DAILY_PENALTIES[user_id] = {"date": today_str, "count": 1}
    else:
        data["count"] += 1

async def get_live_chat_id():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = 'live_chat_id'") as cur:
            row = await cur.fetchone()
            if row and row[0]:
                return int(row[0])
    return None

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
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass
        else:
            logger.warning(f"Edit warning: {e}")
    except Exception as e:
        logger.error(f"Unexpected edit error: {e}")

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
                VALUES (?, ?, ?, 150)
            """, (ESCOBAR_AI_ID, "Escobar AI 🤖", "escobar_ai"))
            await db.commit()
    except Exception as e:
        logger.error(f"Error in ensure_escobar_ai: {e}")

async def set_live_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in ["group", "supergroup"]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('live_chat_id', ?)", (str(chat.id),))
            await db.commit()
        await update.message.reply_text(
            f"✅ <b>این گروه با موفقیت به عنوان ورزشگاه پخش زنده مسابقات رئال مادرید و بارسلونا تنظیم شد!</b> 🏟🔥\n"
            "از این پس دقیقاً ۱۵ دقیقه قبل بازی‌ها استخر ۳۰۰ امتیازی و در جریان بازی گزارش لحظه‌ای ارسال می‌شود.",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("⚠️ این دستور را باید در گروه یا سوپرگروه مورد نظر ارسال کنید.")

# -------------------------------------------------------------
# موتور گزارشگر زنده و استخر ۳۰۰ امتیازی با زمان‌بندی دقیق ۱۵ دقیقه
# -------------------------------------------------------------
async def monitor_real_barca_live_job(context: ContextTypes.DEFAULT_TYPE):
    target_chat_id = await get_live_chat_id()
    if not target_chat_id:
        return

    today_str = get_iran_now().strftime("%Y%m%d")
    matches = await provider.get_matches(today_str, league_code="esp.1")
    ucl_matches = await provider.get_matches(today_str, league_code="uefa.champions")
    matches.extend(ucl_matches)

    utc_now = datetime.now(timezone.utc)

    for m in matches:
        h_name = m.get("home_team", "")
        a_name = m.get("away_team", "")

        is_barca = ("Barcelona" in h_name or "Barcelona" in a_name or "بارسلونا" in h_name or "بارسلونا" in a_name)
        is_real = ("Real Madrid" in h_name or "Real Madrid" in a_name or "رئال مادرید" in h_name or "رئال مادرید" in a_name)

        if not (is_barca or is_real):
            continue

        m_id = m["id"]
        status = m.get("status", "UPCOMING")
        h_score = m.get("home_score")
        a_score = m.get("away_score")

        track = TRACKED_LIVE_MATCHES.get(m_id)
        if not track:
            track = {
                "last_status": status,
                "home_score": h_score if h_score is not None else 0,
                "away_score": a_score if a_score is not None else 0,
                "pool_opened": False
            }
            TRACKED_LIVE_MATCHES[m_id] = track

        # محاسبه فاصله زمانی دقیق تا شروع بازی بر حسب دقیقه
        match_date_str = m.get("date")
        minutes_to_start = 9999
        if match_date_str:
            try:
                dt_match = datetime.fromisoformat(match_date_str.replace("Z", "+00:00"))
                diff_sec = (dt_match - utc_now).total_seconds()
                minutes_to_start = int(diff_sec // 60)
            except Exception:
                minutes_to_start = 9999

        # ۱. باز کردن استخر ۳۰۰ امتیازی فقط زمانی که دقیقاً بین ۰ تا ۱۵ دقیقه به شروع بازی مانده باشد
        if status == "UPCOMING" and not track["pool_opened"] and (0 <= minutes_to_start <= 15):
            track["pool_opened"] = True
            time_str = format_iran_time(match_date_str)
            pool_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"⚪️ برد {h_name[:10]}", callback_data=f"pool_{m_id}_HOME"),
                    InlineKeyboardButton("🤝 مساوی", callback_data=f"pool_{m_id}_DRAW"),
                    InlineKeyboardButton(f"🔴 برد {a_name[:10]}", callback_data=f"pool_{m_id}_AWAY")
                ]
            ])
            pool_text = (
                f"🚨🔥 <b>۱۵ دقیقه تا آغاز نبرد حساس! پیش‌بینی ویژه استخر ۳۰۰ امتیازی</b> 🏆\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"⚽️ <b>{h_name}</b> 🆚 <b>{a_name}</b>\n"
                f"⏰ شروع بازی: <code>{time_str}</code> (به وقت تهران)\n"
                "💰 <b>استخر جایزه: ۳۰۰ امتیاز</b> 🪙\n"
                "⚡️ جایزه ۳۰۰ امتیازی بین تمام کسانی که برنده را درست حدس بزنند مساوی تقسیم خواهد شد!\n"
                "⏱ مهلت ثبت: تا سوت شروع بازی!\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "👇 پیش‌بینی خود را با دکمه‌های زیر ثبت کنید:"
            )
            try:
                await context.bot.send_message(chat_id=target_chat_id, text=pool_text, reply_markup=pool_kb, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error sending pool alert: {e}")

        # ۲. سوت شروع بازی
        if status == "LIVE" and track["last_status"] == "UPCOMING":
            track["last_status"] = "LIVE"
            start_msg = (
                f"📢 <b>سوت آغاز بازی به صدا درآمد!</b> 🔥⚽️\n"
                f"▫️ <b>{h_name}</b> 🆚 <b>{a_name}</b>\n"
                "دکمه‌های پیش‌بینی قفل شدند! گزارش لحظه‌ای بازی آغاز شد."
            )
            await context.bot.send_message(chat_id=target_chat_id, text=start_msg, parse_mode="HTML")

        # ۳. ثبت و اعلام گل‌ها با متن حماسی
        if status == "LIVE" and h_score is not None and a_score is not None:
            if h_score > track["home_score"]:
                track["home_score"] = h_score
                goal_team = h_name
                hype = "توووووپ توی دروازهههههه! گلللل برای " if ("Barcelona" in h_name or "Real" in h_name) else "گللللل برای "
                goal_msg = (
                    f"⚽️🔥 <b>{hype}{goal_team}!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚪️ <b>{h_name}</b> [{h_score}] - [{a_score}] <b>{a_name}</b> 🔴\n"
                    "شور و هیجان در استادیوم به اوج رسید!"
                )
                await context.bot.send_message(chat_id=target_chat_id, text=goal_msg, parse_mode="HTML")

            elif a_score > track["away_score"]:
                track["away_score"] = a_score
                goal_team = a_name
                hype = "توووووپ توی دروازهههههه! گلللل برای " if ("Barcelona" in a_name or "Real" in a_name) else "گللللل برای "
                goal_msg = (
                    f"⚽️🔥 <b>{hype}{goal_team}!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚪️ <b>{h_name}</b> [{h_score}] - [{a_score}] <b>{a_name}</b> 🔴\n"
                    "شور و هیجان در استادیوم به اوج رسید!"
                )
                await context.bot.send_message(chat_id=target_chat_id, text=goal_msg, parse_mode="HTML")

        # ۴. سوت پایان بازی و تقسیم استخر ۳۰۰ امتیازی
        if status == "FINISHED" and track["last_status"] != "FINISHED":
            track["last_status"] = "FINISHED"
            final_h = h_score if h_score is not None else 0
            final_a = a_score if a_score is not None else 0
            actual_outcome = "HOME" if final_h > final_a else ("AWAY" if final_a > final_h else "DRAW")

            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute("SELECT user_id, user_name FROM special_pool_predictions WHERE match_id = ? AND choice = ?", (m_id, actual_outcome)) as cur:
                    winners = await cur.fetchall()

                winners_text = ""
                if winners:
                    share = 300 // len(winners)
                    winners_text = f"\n\n🎁 <b>برندگان استخر ۳۰۰ امتیازی (هر نفر +{share} امتیاز):</b>\n"
                    for w_id, w_name in winners:
                        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (share, w_id))
                        winners_text += f"▫️ <b>{html.escape(w_name)}</b> (+{share} PTS)\n"
                else:
                    winners_text = "\n\nهیچ کاربری برنده نهایی را درست حدس نزد!"

                await db.execute("UPDATE special_pool_predictions SET settled = 1 WHERE match_id = ?", (m_id,))
                await db.commit()

            ft_msg = (
                f"🏁 <b>سوت پایان مسابقه به صدا درآمد!</b> 🏆\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"⚪️ <b>{h_name}</b> {final_h} - {final_a} <b>{a_name}</b> 🔴\n"
                f"نتیجه قطعی بازی ثبت شد.{winners_text}"
            )
            await context.bot.send_message(chat_id=target_chat_id, text=ft_msg, parse_mode="HTML")

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
                        try:
                            await context.bot.send_message(
                                chat_id=ref_id,
                                text=f"🎉 دوست شما <b>{html.escape(user.first_name)}</b> با لینک شما به ربات پیوست!\n💰 <b>+30 امتیاز پاداش</b> دریافت کردید.",
                                parse_mode="HTML"
                            )
                        except Exception:
                            pass

    safe_name = html.escape(user.first_name)
    text = (
        f"⚽ <b>FOOTBALL HUB</b> | <i>PRO EDITION</i> ✨\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"سلام <b>{safe_name}</b> عزیز، خوش اومدی به هاب فوتبالی! 🔥\n\n"
        "⚡️ نتایج زنده و گزارش حماسی مسابقات رئال و بارسا\n"
        "🎯 پیش‌بینی بازی‌ها با استخر <b>۳۰۰ امتیازی ویژه</b>\n"
        "⚔️ دوئل اطلاعات عمومی و <b>پنالتی تک‌ضرب (۲ بار در روز)</b> در گروه!\n"
        "🎁 پاداش روزانه و شوت‌های سرعتی\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <b>یک بخش را جهت شروع انتخاب کنید:</b>"
    )
    try:
        if update.callback_query:
            await safe_edit_message(update.callback_query, text, reply_markup=kb.get_main_menu())
        else:
            await update.message.reply_text(text, reply_markup=kb.get_main_menu(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error sending start message: {e}")

async def show_leaderboard_text():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT first_name, points, duel_wins FROM users ORDER BY points DESC, duel_wins DESC") as cur:
            all_users = await cur.fetchall()

    text = "🏆 <b>جدول رنکینگ و رقابت اعضا</b> 🔥\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    if not all_users:
        text += "▫️ هنوز کاربری ثبت نشده است.\n"
    else:
        for idx, u in enumerate(all_users, 1):
            name, pts, wins = u[0], max(0, u[1]), u[2]
            badge = get_user_badge(pts)
            pos = "🥇" if idx == 1 else ("🥈" if idx == 2 else ("🥉" if idx == 3 else f"<b>{idx:02d}.</b>"))
            safe_name = html.escape(str(name))
            text += f"{pos} {badge} <b>{safe_name}</b>\n   └ ⚡️ <code>{pts} PTS</code>  ▫️  ⚔️ <code>{wins} برد</code>\n"
    text += "\n━━━━━━━━━━━━━━━━━━━━"
    return text

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await show_leaderboard_text()
    await update.message.reply_text(text, parse_mode="HTML")

async def daily_reward_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)
    now = datetime.utcnow()
    last = USER_LAST_DAILY.get(user.id)

    if last and (now - last) < timedelta(hours=24):
        rem = timedelta(hours=24) - (now - last)
        h = int(rem.total_seconds() // 3600)
        m = int((rem.total_seconds() % 3600) // 60)
        await update.message.reply_text(
            f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، شما امروز جایزه‌تان را دریافت کرده‌اید!\n"
            f"⏱ نوبت بعدی: <b>{h} ساعت و {m} دقیقه</b> دیگر.",
            parse_mode="HTML"
        )
        return

    reward = 20
    USER_LAST_DAILY[user.id] = now
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, user.id))
        await db.commit()

    await update.message.reply_text(
        f"🎁 <b>پاداش روزانه با موفقیت واریز شد!</b>\n"
        f"👤 کاربر: <b>{html.escape(user.first_name)}</b>\n"
        f"💰 <b>+{reward} امتیاز</b> دریافت کردید! فردا هم سر بزنید.",
        parse_mode="HTML"
    )

async def daily_shoot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    now = datetime.utcnow()
    last_shot = USER_LAST_SHOT.get(user.id)

    if last_shot and (now - last_shot) < timedelta(hours=24):
        remaining = timedelta(hours=24) - (now - last_shot)
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        await update.message.reply_text(
            f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، شما شوت روزانه خود را زده‌اید!\n"
            f"⏱ فرصت بعدی شما: <b>{hours} ساعت و {minutes} دقیقه</b> دیگر.",
            parse_mode="HTML"
        )
        return

    msg = await update.message.reply_dice(emoji="⚽")
    dice_val = msg.dice.value
    USER_LAST_SHOT[user.id] = now

    await asyncio.sleep(2.5)

    if dice_val in [3, 4, 5]:
        reward = 15
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, user.id))
            await db.commit()

        await update.message.reply_text(
            f"⚽️🔥 <b>گـُـل شدددد! عجب شوتی!</b>\n"
            f"👤 بازیکن: <b>{html.escape(user.first_name)}</b>\n"
            f"💰 پاداش: <b>+{reward} امتیاز</b> به حساب شما اضافه شد! 🎉",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"🧤❌ <b>حیف شد! توپ گل نشد!</b> (برخورد به تیرک یا مهار گلر)\n"
            f"👤 بازیکن: <b>{html.escape(user.first_name)}</b>\n"
            "فردا دوباره شانس خودت رو امتحان کن! 😉",
            parse_mode="HTML"
        )

# -------------------------------------------------------------
# پنالتی تک‌ضرب با سقف ۲ بار در روز
# -------------------------------------------------------------
async def trigger_penalty_shootout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "🥅 <b>نحوه پنالتی‌کشی:</b>\nروی پیام دوستت در گروه ریپلای کن و بنویس: <code>پنالتی</code> یا <code>/penalty</code>",
            parse_mode="HTML"
        )
        return

    challenger = update.effective_user
    opponent = update.message.reply_to_message.from_user

    if opponent.is_bot:
        await update.message.reply_text("🤖 نمی‌تونی با ربات پنالتی بزنی!")
        return

    if challenger.id == opponent.id:
        await update.message.reply_text("⚠️ نمی‌تونی با خودت پنالتی بزنی!")
        return

    c_count = get_penalty_count_today(challenger.id)
    if c_count >= 2:
        await update.message.reply_text(
            f"⛔️ <b>{html.escape(challenger.first_name)}</b> عزیز، شما سقف مجاز ۲ پنالتی در روز خود را استفاده کرده‌اید!\n"
            "فردا دوباره می‌توانید پنالتی بزنید.",
            parse_mode="HTML"
        )
        return

    o_count = get_penalty_count_today(opponent.id)
    if o_count >= 2:
        await update.message.reply_text(
            f"⛔️ حریف شما <b>{html.escape(opponent.first_name)}</b> امروز ۲ پنالتی خود را بازی کرده و فرصت امروزش تمام شده است!",
            parse_mode="HTML"
        )
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
        [InlineKeyboardButton("🧤 قبول چالش پنالتی تک‌ضرب", callback_data=f"acp_{p_id}"),
         InlineKeyboardButton("❌ انصراف", callback_data=f"rjp_{p_id}")]
    ])

    c_name = html.escape(challenger.first_name)
    o_name = html.escape(opponent.first_name)

    text = (
        "🥅 <b>دوئل تک‌ضرب پنالتی (مرگ ناگهانی)!</b> ⚽️\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 شوت‌زن اول: <b>{c_name}</b> (پنالتی امروز: {c_count + 1}/2)\n"
        f"👤 شوت‌زن دوم: <b>{o_name}</b> (پنالتی امروز: {o_count + 1}/2)\n"
        "💰 شرط مسابقه: <b>25 امتیاز</b> 🪙\n"
        "⚡️ در صورت تساوی، ضربات تا تعیین برنده ادامه پیدا می‌کند!\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
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
        f"🥅 <b>راند طلایی شماره {shootout['round']}:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>{html.escape(p1['name'])}</b>: {p1_status}\n"
        f"👤 <b>{html.escape(p2['name'])}</b>: {p2_status}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 نوبت شوت زدن: <b>{html.escape(cur_shooter)}</b>\n"
        "روی دکمه زیر کلیک کن تا ضربه‌ات را بزنی! 👇"
    )
    return text

async def execute_penalty_kick(query, context, p_id):
    shootout = ACTIVE_SHOOTOUTS.get(p_id)
    if not shootout:
        await query.answer("مسابقه منقضی شده است.", show_alert=True)
        return

    user_id = query.from_user.id
    if user_id != shootout["current_turn"]:
        await query.answer("⛔ نوبت شما نیست! اجازه دهید حریف شوت بزند.", show_alert=True)
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
        kick_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚽️ نوبت توئه! پنالتی رو بزن", callback_data=f"shoot_pen_{p_id}")]])
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kick_kb, parse_mode="HTML")
    else:
        shootout["p2"]["shot"] = icon
        p1_goal = (shootout["p1"]["shot"] == "⚽️ گل شد!")
        p2_goal = (shootout["p2"]["shot"] == "⚽️ گل شد!")

        p1_name = html.escape(shootout["p1"]["name"])
        p2_name = html.escape(shootout["p2"]["name"])
        stake = shootout["stake"]

        if p1_goal and not p2_goal:
            increment_penalty_count_today(shootout["p1"]["id"])
            increment_penalty_count_today(shootout["p2"]["id"])

            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, shootout["p1"]["id"]))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, shootout["p2"]["id"]))
                await db.commit()

            del ACTIVE_SHOOTOUTS[p_id]
            res = (
                "🏁 <b>پایان دوئل پنالتی!</b> 🏆\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 {p1_name}: ⚽️ گل زد\n"
                f"👤 {p2_name}: ❌ گل نکرد\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🎉 <b>تبریک به {p1_name}! برنده {stake} امتیاز شد!</b> 🔥"
            )
            await context.bot.send_message(chat_id=chat_id, text=res, parse_mode="HTML")

        elif p2_goal and not p1_goal:
            increment_penalty_count_today(shootout["p1"]["id"])
            increment_penalty_count_today(shootout["p2"]["id"])

            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, shootout["p2"]["id"]))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, shootout["p1"]["id"]))
                await db.commit()

            del ACTIVE_SHOOTOUTS[p_id]
            res = (
                "🏁 <b>پایان دوئل پنالتی!</b> 🏆\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 {p1_name}: ❌ گل نکرد\n"
                f"👤 {p2_name}: ⚽️ گل زد\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🎉 <b>تبریک به {p2_name}! برنده {stake} امتیاز شد!</b> 🔥"
            )
            await context.bot.send_message(chat_id=chat_id, text=res, parse_mode="HTML")

        else:
            shootout["round"] += 1
            shootout["p1"]["shot"] = None
            shootout["p2"]["shot"] = None
            shootout["current_turn"] = shootout["p1"]["id"]

            draw_msg = (
                f"🤝 <b>هردو مساوی شدند! بازی وارد راند طلایی {shootout['round']} شد!</b> 🔥\n"
                "ضربات تک‌به‌تک ادامه دارد تا برنده نهایی مشخص شود..."
            )
            await context.bot.send_message(chat_id=chat_id, text=draw_msg, parse_mode="HTML")

            text = render_shootout_board(shootout)
            kick_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚽️ زدن ضربه مرگ ناگهانی!", callback_data=f"shoot_pen_{p_id}")]])
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kick_kb, parse_mode="HTML")

# -------------------------------------------------------------
# دوئل اطلاعات عمومی
# -------------------------------------------------------------
async def trigger_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚔️ <b>نحوه شروع دوئل:</b>\nروی پیام حریفت ریپلای کن و بنویس: <code>دوئل</code> یا <code>/duel</code> 🎯",
            parse_mode="HTML"
        )
        return

    challenger = update.effective_user
    opponent = update.message.reply_to_message.from_user

    if opponent.is_bot:
        await update.message.reply_text("🤖 نمی‌تونی با ربات دوئل کنی!")
        return

    if challenger.id == opponent.id:
        await update.message.reply_text("⚠️ نمی‌تونی با خودت دوئل کنی!")
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
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 چلنجر: <b>{c_name}</b>\n"
        f"🎯 هماورد: <b>{o_name}</b>\n"
        "💰 جایزه رقابت: <b>+25 امتیاز</b> 🪙\n"
        "⏱ زمان هر سوال: <b>15 ثانیه</b> ⏳\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"آیا <b>{o_name}</b> چالش رو می‌پذیره؟"
    )
    sent_msg = await update.message.reply_text(text, reply_markup=duel_kb, parse_mode="HTML")
    ACTIVE_DUELS[duel_id]["message_id"] = sent_msg.message_id

def render_duel_question_text(duel, q_data, q_idx):
    c_name = html.escape(duel["challenger"]["name"])
    o_name = html.escape(duel["opponent"]["name"])
    c_id = duel["challenger"]["id"]
    o_id = duel["opponent"]["id"]

    c_status = "✅ پاسخ داد" if c_id in duel["answered"] else "⏳ در حال فکر کردن..."
    o_status = "✅ پاسخ داد" if o_id in duel["answered"] else "⏳ در حال فکر کردن..."
    safe_q = html.escape(q_data['question'])

    text = (
        f"❓ <b>سوال {q_idx + 1} از 3:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{safe_q}</b>\n\n"
        "⏱ مهلت پاسخ: <b>15 ثانیه</b> ⏳\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
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
            "🏁 <b>پایان دوئل اطلاعات عمومی فوتبال!</b> 🏆\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 {c_name}: <code>{c_score}/3</code> پاسخ درست\n"
            f"👤 {o_name}: <code>{o_score}/3</code> پاسخ درست\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
        )

        async with aiosqlite.connect(DATABASE_PATH) as db:
            if c_score > o_score:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, c_id))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, o_id))
                res_text += f"🎉 <b>تبریک به {c_name}! برنده {stake} امتیاز شد!</b> 🔥"
            elif o_score > c_score:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, o_id))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, c_id))
                res_text += f"🎉 <b>تبریک به {o_name}! برنده {stake} امتیاز شد!</b> 🔥"
            else:
                res_text += "🤝 <b>نتیجه مساوی شد! هیچ امتیازی کسر نگردید.</b>"
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

# -------------------------------------------------------------
# Callback Router
# -------------------------------------------------------------
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    iran_now = get_iran_now()

    if data == "home":
        await start(update, context)

    elif data == "claim_daily":
        update.effective_user = query.from_user
        update.message = query.message
        await daily_reward_cmd(update, context)

    elif data == "invite_friends":
        bot_info = await context.bot.get_me()
        user_id = query.from_user.id
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        text = (
            "👥 <b>سیستم دعوت از دوستان و کسب امتیاز رایگان:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 لینک اختصاصی شما:\n<code>{ref_link}</code>\n\n"
            "به ازای هر دوستی که با لینک شما عضو ربات شود:\n"
            "💰 <b>30 امتیاز به شما</b> و <b>20 امتیاز به دوستتان</b> هدیه داده می‌شود!"
        )
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data == "duel_help":
        text = (
            "⚔️ <b>راهنمای بازی‌ها و کسب امتیاز:</b> ⚽️\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ <b>پیش‌بینی ویژه استخر ۳۰۰ امتیازی:</b> دقیقاً ۱۵ دقیقه قبل بازی‌های رئال و بارسا!\n"
            "2️⃣ <b>دوئل اطلاعات عمومی:</b> ریپلای روی دوستت و نوشتن <code>دوئل</code> یا <code>/duel</code>\n"
            "3️⃣ <b>پنالتی تک‌ضرب:</b> ریپلای روی دوستت و نوشتن <code>پنالتی</code> (سقف ۲ بار در روز برای هر نفر)\n"
            "4️⃣ <b>شوت سرعتی:</b> فرستادن کلمه <code>شوت</code> هر ۲۴ ساعت با شانس ۱۵ امتیاز!\n"
            "5️⃣ <b>جایزه روزانه:</b> فرستادن کلمه <code>جایزه</code> هر ۲۴ ساعت با ۲۰ امتیاز قطعی!"
        )
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data.startswith("pool_"):
        parts = data.split("_")
        match_id = parts[1]
        choice = parts[2]
        user = query.from_user

        choice_label = "برد میزبان" if choice == "HOME" else ("مساوی" if choice == "DRAW" else "برد میهمان")

        async with aiosqlite.connect(DATABASE_PATH) as db:
            try:
                await db.execute("""
                    INSERT INTO special_pool_predictions (match_id, user_id, user_name, choice)
                    VALUES (?, ?, ?, ?)
                """, (match_id, user.id, user.first_name, choice))
                await db.commit()
                await query.answer("✅ پیش‌بینی شما با موفقیت ثبت شد!", show_alert=False)

                # ارسال پیام در گروه که شخص در پیش‌بینی شرکت کرد
                safe_name = html.escape(user.first_name)
                alert_text = (
                    f"🎯 <b>{safe_name}</b> در پیش‌بینی ویژه استخر ۳۰۰ امتیازی شرکت کرد!\n"
                    f"▫️ انتخاب: <b>{choice_label}</b>"
                )
                await query.message.reply_text(alert_text, parse_mode="HTML")
            except Exception:
                await query.answer("⚠️ شما قبلاً در استخر پیش‌بینی این مسابقه شرکت کرده‌اید!", show_alert=True)

    elif data.startswith("acp_"):
        p_id = data.replace("acp_", "")
        shootout = ACTIVE_SHOOTOUTS.get(p_id)
        if not shootout:
            await query.answer("⚠️ این چالش منقضی شده است.", show_alert=True)
            return

        if query.from_user.id != shootout["p2"]["id"]:
            await query.answer("⛔ فقط حریف دعوت‌شده می‌تواند چالش را قبول کند!", show_alert=True)
            return

        if get_penalty_count_today(query.from_user.id) >= 2:
            await query.answer("⛔ شما امروز سقف ۲ پنالتی خود را بازی کرده‌اید!", show_alert=True)
            return

        text = render_shootout_board(shootout)
        kick_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚽️ زدن ضربه پنالتی!", callback_data=f"shoot_pen_{p_id}")]])
        await safe_edit_message(query, text, reply_markup=kick_kb)

    elif data.startswith("rjp_"):
        p_id = data.replace("rjp_", "")
        shootout = ACTIVE_SHOOTOUTS.get(p_id)
        if shootout and query.from_user.id in [shootout["p1"]["id"], shootout["p2"]["id"]]:
            del ACTIVE_SHOOTOUTS[p_id]
            await safe_edit_message(query, "❌ رقابت پنالتی‌کشی لغو گردید.")

    elif data.startswith("shoot_pen_"):
        p_id = data.replace("shoot_pen_", "")
        await execute_penalty_kick(query, context, p_id)

    elif data.startswith("acd_"):
        duel_id = data.replace("acd_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if not duel:
            await query.answer("⚠️ این دوئل منقضی شده است.", show_alert=True)
            return

        if query.from_user.id != duel["opponent"]["id"]:
            await query.answer("⛔ فقط حریف دعوت‌شده می‌تواند چالش را قبول کند!", show_alert=True)
            return

        await proceed_duel(context, duel_id)

    elif data.startswith("rjd_"):
        duel_id = data.replace("rjd_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if duel and query.from_user.id in [duel["opponent"]["id"], duel["challenger"]["id"]]:
            del ACTIVE_DUELS[duel_id]
            await safe_edit_message(query, "❌ رقابت دوئل لغو گردید.")

    elif data.startswith("ad_"):
        parts = data.split("_")
        duel_id = parts[1]
        chosen_idx = int(parts[2])
        duel = ACTIVE_DUELS.get(duel_id)

        if not duel:
            await query.answer("⚠️ این دوئل به پایان رسیده است.", show_alert=True)
            return

        user_id = query.from_user.id
        if user_id not in [duel["challenger"]["id"], duel["opponent"]["id"]]:
            await query.answer("⛔ شما بازیکن این مسابقه نیستید!", show_alert=True)
            return

        if user_id in duel["answered"]:
            await query.answer("⚠️ شما قبلاً پاسخ خود را ثبت کرده‌اید!", show_alert=True)
            return

        curr_q = duel["questions"][duel["current_q"]]
        is_correct = (chosen_idx == curr_q["correct_idx"])
        duel["answered"][user_id] = is_correct

        if is_correct:
            if user_id == duel["challenger"]["id"]:
                duel["challenger"]["score"] += 1
            else:
                duel["opponent"]["score"] += 1
            await query.answer("✅ پاسخ درست ثبت شد!")
        else:
            await query.answer("❌ پاسخ اشتباه ثبت شد!")

        q_text = render_duel_question_text(duel, curr_q, duel["current_q"])
        await safe_edit_message(query, q_text, reply_markup=query.message.reply_markup)

        if len(duel["answered"]) >= 2:
            current_jobs = context.job_queue.get_jobs_by_name(f"duel_timer_{duel_id}_{duel['current_q']}")
            for j in current_jobs:
                j.schedule_removal()

            await asyncio.sleep(1)
            duel["current_q"] += 1
            await proceed_duel(context, duel_id)

    elif data == "select_matches_today":
        await safe_edit_message(
            query,
            "🔥 <b>مسابقات امروز (به وقت تهران):</b>\n━━━━━━━━━━━━━━━━━━━━\n👇 لیگ مورد نظر را انتخاب کنید:",
            reply_markup=kb.get_matches_leagues_keyboard("today")
        )

    elif data == "select_matches_tomorrow":
        await safe_edit_message(
            query,
            "📅 <b>مسابقات فردا (به وقت تهران):</b>\n━━━━━━━━━━━━━━━━━━━━\n👇 لیگ مورد نظر را انتخاب کنید:",
            reply_markup=kb.get_matches_leagues_keyboard("tmrw")
        )

    elif data == "select_standings_league":
        await safe_edit_message(
            query,
            "🏆 <b>مشاهده جداول معتبر فوتبال:</b>\n━━━━━━━━━━━━━━━━━━━━\n👇 جدول کدام لیگ را می‌خواهید؟",
            reply_markup=kb.get_standings_leagues_keyboard()
        )

    elif data.startswith("today_") or data.startswith("tmrw_"):
        is_today = data.startswith("today_")
        league_code = data.replace("today_", "").replace("tmrw_", "")
        target_date = iran_now if is_today else iran_now + timedelta(days=1)
        date_str = target_date.strftime("%Y%m%d")

        matches = []
        if league_code == "all":
            for l_id in ["eng.1", "esp.1", "ita.1", "ger.1"]:
                m_list = await provider.get_matches(date_str, league_code=l_id)
                matches.extend(m_list[:2])
        else:
            matches = await provider.get_matches(date_str, league_code=league_code)

        league_title = LEAGUE_TITLES.get(league_code, "فوتبال")
        day_title = "امروز" if is_today else "فردا"

        if not matches:
            await safe_edit_message(query, f"⏳ برای {league_title} در تاریخ {day_title} مسابقه‌ای ثبت نشده است.", reply_markup=kb.get_back_button())
            return

        text = f"🔥 <b>برنامه مسابقات {league_title} ({day_title}):</b>\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        for m in matches[:8]:
            match_time = format_iran_time(m.get("date"))
            if m['status'] == "LIVE":
                status_badge = "🔴 <b>LIVE (در حال بازی)</b>"
            elif m['status'] == "FINISHED":
                status_badge = "🏁 <b>FT (پایان مسابقه)</b>"
            else:
                status_badge = f"⏰ ساعت: <code>{match_time}</code>"

            score = f"\n⚽️ نتیجه: <b>{m['home_score']} - {m['away_score']}</b>" if m['home_score'] is not None else ""
            h_team = html.escape(str(m['home_team']))
            a_team = html.escape(str(m['away_team']))
            venue = html.escape(str(m['venue']))

            text += (
                f"⚪️ <b>{h_team}</b> 🆚 <b>{a_team}</b> 🔴\n"
                f"وضعیت: {status_badge}{score}\n"
                f"🏟 استادیوم: <code>{venue}</code>\n"
                "────────────────────\n"
            )
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data.startswith("table_"):
        league_code = data.replace("table_", "")
        league_title = LEAGUE_TITLES.get(league_code, "League")
        standings = await provider.get_standings(league_code)
        
        if not standings:
            await safe_edit_message(query, f"⏳ جدول {league_title} در دسترس نیست.", reply_markup=kb.get_back_button())
            return
            
        text = f"🏆 <b>{league_title} Standings (Top 10)</b>\n\n"
        text += "<pre>"
        text += "#  | Team          | P  | Pts\n"
        text += "---+---------------+----+----\n"
        for idx, s in enumerate(standings, 1):
            t_name = s['team'][:13]
            text += f"{idx:<2} | {t_name:<13} | {s['p']:<2} | {s['pts']:<3}\n"
        text += "</pre>"
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data == "predictions_hub":
        today_str = iran_now.strftime("%Y%m%d")
        tmrw_str = (iran_now + timedelta(days=1)).strftime("%Y%m%d")

        candidate_matches = []
        for l_code in ["eng.1", "esp.1", "ita.1", "ger.1"]:
            candidate_matches.extend(await provider.get_matches(today_str, league_code=l_code))
            candidate_matches.extend(await provider.get_matches(tmrw_str, league_code=l_code))

        upcoming_matches = [m for m in candidate_matches if m.get("status") == "UPCOMING"]

        if not upcoming_matches:
            await safe_edit_message(query, "⏳ در حال حاضر مسابقه شروع‌نشده‌ای برای پیش‌بینی موجود نیست.", reply_markup=kb.get_back_button())
            return

        for m in upcoming_matches:
            MATCH_CACHE[m["id"]] = m
            await record_ai_prediction_if_needed(m["id"])

        text = (
            "🎯 <b>تالار پیش‌بینی مسابقات آینده:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💰 <b>+10 امتیاز قطعی</b> به محض ثبت پیش‌بینی!\n"
            "🎁 <b>+10 امتیاز</b> برای حدس برنده درست\n"
            "🔥 <b>+15 امتیاز</b> برای حدس نتیجه دقیق\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "یکی از مسابقات زیر را انتخاب فرمایید:"
        )
        await safe_edit_message(query, text, reply_markup=kb.get_upcoming_matches_keyboard(upcoming_matches))

    elif data.startswith("select_pred_"):
        match_id = data.replace("select_pred_", "")
        m = MATCH_CACHE.get(match_id)
        if not m:
            await safe_edit_message(query, "⚠️ مهلت پیش‌بینی این مسابقه به پایان رسیده است.", reply_markup=kb.get_back_button())
            return

        match_time = format_iran_time(m.get("date"))
        h_team = html.escape(str(m['home_team']))
        a_team = html.escape(str(m['away_team']))
        league = html.escape(str(m['league']))
        
        text = (
            "🎯 <b>فرم پیش‌بینی مسابقه:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 {league}\n"
            f"⚪️ <b>{h_team}</b> 🆚 <b>{a_team}</b> 🔴\n"
            f"⏰ شروع: <code>{match_time}</code> (به وقت تهران)\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "پیش‌بینی شما برای نتیجه مسابقه چیست؟"
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
                await safe_edit_message(
                    query,
                    "✅ <b>پیش‌بینی شما با موفقیت قفل و ثبت شد!</b> 🔥\n"
                    "💰 <b>+10 امتیاز مشارکت در پیش‌بینی</b> به حساب شما اضافه شد!\n"
                    "در صورت حدس درست برنده، ۱۰ امتیاز دیگر نیز پس از بازی دریافت خواهید کرد.",
                    reply_markup=kb.get_back_button()
                )
            except Exception:
                await safe_edit_message(query, "⚠️ پیش‌بینی شما برای این مسابقه قبلاً ثبت شده است.", reply_markup=kb.get_back_button())

    elif data == "user_profile":
        user_id = query.from_user.id
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT points, exact_predictions, correct_results, total_predictions, duel_wins FROM users WHERE user_id = ?", (user_id,)) as cur:
                u = await cur.fetchone()

        if u:
            pts, exact, correct, total, dw = max(0, u[0]), u[1], u[2], u[3], u[4]
            badge = get_user_badge(pts)
            safe_name = html.escape(str(query.from_user.first_name))
            p_today = get_penalty_count_today(user_id)
            text = (
                f"👤 <b>کارت رسمی بازیکن | {safe_name}</b> ✨\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🌟 سطح بازیکن: {badge} <b>Level PRO</b>\n"
                f"💰 موجودی امتیاز: <code>{pts} PTS</code>\n"
                f"🥅 پنالتی‌های بازی‌شده امروز: <code>{p_today}/2</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"⚔️ پیروزی در دوئل‌ها: <code>{dw} برد</code>\n"
                f"🎯 پیش‌بینی‌های ثبت‌شده: <code>{total}</code>\n"
                f"🏅 حدس درست برنده: <code>{correct}</code>\n"
                f"🔥 حدس دقیق نتیجه: <code>{exact}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━"
            )
            await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data == "leaderboard_hub":
        text = await show_leaderboard_text()
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

# هندلر پیام‌های متنی در گروه
async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.strip() if update.message and update.message.text else ""
    if not msg:
        return

    if msg in ["شروع", "منو", "فوتبال"]:
        await start(update, context)
    elif msg in ["جدول", "رنکینگ", "امتیازات"]:
        await leaderboard_cmd(update, context)
    elif msg in ["دوئل", "duel", "چالش"]:
        await trigger_duel(update, context)
    elif msg in ["پنالتی", "پنالتی کشی", "penalty"]:
        await trigger_penalty_shootout(update, context)
    elif msg in ["شوت", "گل", "shoot"]:
        await daily_shoot_cmd(update, context)
    elif msg in ["جایزه", "روزانه", "daily"]:
        await daily_reward_cmd(update, context)
    elif msg in ["پیشبینی", "پیش بینی"]:
        await update.message.reply_text("🎯 جهت ثبت پیش‌بینی مسابقات و دریافت ۱۰ امتیاز قطعی، دستور /start را لمس کنید.", parse_mode="HTML")
    elif msg in ["بازیها", "بازی ها"]:
        iran_now = get_iran_now()
        matches = await provider.get_matches(iran_now.strftime("%Y%m%d"), league_code="eng.1")
        if matches:
            t = "🔥 <b>مسابقات منتخب امروز (به وقت تهران):</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for m in matches[:4]:
                tm = format_iran_time(m.get("date"))
                h_team = html.escape(str(m['home_team']))
                a_team = html.escape(str(m['away_team']))
                t += f"▫️ <b>{h_team}</b> 🆚 <b>{a_team}</b> (⏰ <code>{tm}</code>)\n"
            await update.message.reply_text(t, parse_mode="HTML")
        else:
            await update.message.reply_text("⏳ مسابقه‌ای برای امروز یافت نشد.")

async def post_init(application: Application):
    await init_db()
    await ensure_escobar_ai()
    # مانیتورینگ مسابقات زنده رئال و بارسا و استخر ۳۰۰ امتیازی هر ۶۰ ثانیه
    application.job_queue.run_repeating(monitor_real_barca_live_job, interval=60, first=10)

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
    app.add_handler(CommandHandler("set_live", set_live_group))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_messages))

    logger.info("Bot fully online with accurate 15-min Live Pool & Public Alerts!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
