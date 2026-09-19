import os
import threading
import logging
import random
import asyncio
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

# مینی سرور پایداری
class SimpleHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Football Hub Engine is Online! 200 OK")

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHealthServer)
    logger.info(f"Health server on port {port}")
    server.serve_forever()

LEAGUE_TITLES = {
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ita.1": "Serie A",
    "ger.1": "Bundesliga",
    "fra.1": "Ligue 1",
    "all": "Top European Matches"
}

MATCH_CACHE = {}
ACTIVE_DUELS = {}

async def safe_edit_message(query_or_bot, text, reply_markup=None, chat_id=None, message_id=None):
    """ویرایش کاملاً امن پیام بدون کرش"""
    try:
        if chat_id and message_id:
            await query_or_bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup
            )
        else:
            await query_or_bot.message.edit_text(
                text=text,
                reply_markup=reply_markup
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

async def record_ai_prediction_if_needed(match_id: str):
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT id FROM predictions WHERE user_id = ? AND match_id = ?", (ESCOBAR_AI_ID, match_id)) as cur:
                if await cur.fetchone():
                    return
            ai_choice = random.choice(["HOME", "DRAW", "AWAY"])
            await db.execute("""
                INSERT INTO predictions (user_id, match_id, outcome_choice, predicted_home, predicted_away)
                VALUES (?, ?, ?, 0, 0)
            """, (ESCOBAR_AI_ID, match_id, ai_choice))
            await db.execute("UPDATE users SET total_predictions = total_predictions + 1 WHERE user_id = ?", (ESCOBAR_AI_ID,))
            await db.commit()
    except Exception as e:
        logger.error(f"Error in record_ai_prediction: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    text = (
        f"⚽ FOOTBALL HUB | PRO EDITION\n"
        "────────────────────────────\n"
        f"درود {user.first_name}، به مرکز هوشمند فوتبال خوش آمدید.\n\n"
        "▫️ نتایج زنده و برنامه مسابقات معتبر\n"
        "▫️ پیش‌بینی مسابقات و رقابت با Escobar AI\n"
        "▫️ دوئل اطلاعات عمومی فوتبال در گروه‌ها\n"
        "────────────────────────────\n"
        "یک بخش را جهت شروع انتخاب کنید:"
    )
    try:
        if update.callback_query:
            await safe_edit_message(update.callback_query, text, reply_markup=kb.get_main_menu())
        else:
            await update.message.reply_text(text, reply_markup=kb.get_main_menu())
    except Exception as e:
        logger.error(f"Error sending start message: {e}")

async def show_leaderboard_text():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT first_name, points, duel_wins FROM users ORDER BY points DESC, duel_wins DESC") as cur:
            all_users = await cur.fetchall()

    text = "🎖 رتبه‌بندی قهرمانان فوتبال هاب\n"
    text += "────────────────────────────\n\n"
    if not all_users:
        text += "▫️ هنوز کاربری ثبت نشده است.\n"
    else:
        for idx, u in enumerate(all_users, 1):
            name, pts, wins = u[0], u[1], u[2]
            badge = get_user_badge(pts)
            pos = "🥇" if idx == 1 else ("🥈" if idx == 2 else ("🥉" if idx == 3 else f"{idx:02d}"))
            text += f"{pos} {badge} {name}\n   └ ⚡ {pts} PTS  ▫️  ⚔️ {wins} W\n"
    text += "\n────────────────────────────"
    return text

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await show_leaderboard_text()
    await update.message.reply_text(text)

# دوئل اطلاعات عمومی
async def trigger_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚔️ نحوه شروع دوئل:\nروی پیام حریفتان ریپلای کرده و دستور 'دوئل' یا /duel را بفرستید."
        )
        return

    challenger = update.effective_user
    opponent = update.message.reply_to_message.from_user

    if opponent.is_bot:
        await update.message.reply_text("🤖 امکان دوئل با ربات وجود ندارد.")
        return

    if challenger.id == opponent.id:
        await update.message.reply_text("⚠️ امکان مسابقه با خودتان وجود ندارد.")
        return

    await ensure_user(challenger)
    await ensure_user(opponent)

    duel_id = f"{challenger.id}_{opponent.id}_{int(datetime.utcnow().timestamp())}"
    ACTIVE_DUELS[duel_id] = {
        "challenger": {"id": challenger.id, "name": challenger.first_name, "score": 0},
        "opponent": {"id": opponent.id, "name": opponent.first_name, "score": 0},
        "questions": get_random_duel_questions(3),
        "current_q": 0,
        "stake": 25,
        "answered": {},
        "timer_task": None,
        "chat_id": update.effective_chat.id,
        "message_id": None
    }

    duel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ پذیرش چالش", callback_data=f"accept_duel_{duel_id}"),
         InlineKeyboardButton("✕ انصراف", callback_data=f"reject_duel_{duel_id}")]
    ])

    text = (
        "⚔️ میدان دوئل اطلاعات عمومی فوتبال\n"
        "────────────────────────────\n"
        f"▫️ چلنجر: {challenger.first_name}\n"
        f"▫️ هماورد: {opponent.first_name}\n"
        f"▫️ جایزه رقابت: +25 PTS\n"
        f"▫️ زمان هر سوال: 15 ثانیه\n"
        "────────────────────────────\n"
        f"آیا {opponent.first_name} چالش را می‌پذیرد؟"
    )
    sent_msg = await update.message.reply_text(text, reply_markup=duel_kb)
    ACTIVE_DUELS[duel_id]["message_id"] = sent_msg.message_id

def render_duel_question_text(duel, q_data, q_idx):
    c_name = duel["challenger"]["name"]
    o_name = duel["opponent"]["name"]
    c_id = duel["challenger"]["id"]
    o_id = duel["opponent"]["id"]

    c_status = "✅ ثبت شد" if c_id in duel["answered"] else "⏳ در حال بررسی..."
    o_status = "✅ ثبت شد" if o_id in duel["answered"] else "⏳ در حال بررسی..."

    text = (
        f"❓ سوال {q_idx + 1} از 3\n"
        "────────────────────────────\n"
        f"📌 {q_data['question']}\n\n"
        f"⏱ مهلت پاسخگویی: 15 ثانیه\n"
        "────────────────────────────\n"
        f"▫️ {c_name}: {c_status}\n"
        f"▫️ {o_name}: {o_status}\n"
    )
    return text

async def question_timeout_worker(bot, duel_id: str, q_idx: int):
    await asyncio.sleep(15)
    duel = ACTIVE_DUELS.get(duel_id)
    if duel and duel["current_q"] == q_idx:
        duel["current_q"] += 1
        await proceed_duel(bot, duel_id)

async def proceed_duel(bot, duel_id):
    duel = ACTIVE_DUELS.get(duel_id)
    if not duel:
        return

    if duel["timer_task"] and not duel["timer_task"].done():
        duel["timer_task"].cancel()

    q_idx = duel["current_q"]
    chat_id = duel["chat_id"]
    msg_id = duel["message_id"]

    if q_idx >= len(duel["questions"]):
        c_score = duel["challenger"]["score"]
        o_score = duel["opponent"]["score"]
        stake = duel["stake"]

        c_id, c_name = duel["challenger"]["id"], duel["challenger"]["name"]
        o_id, o_name = duel["opponent"]["id"], duel["opponent"]["name"]

        res_text = (
            "🏁 پایان دوئل اطلاعات عمومی\n"
            "────────────────────────────\n"
            f"▫️ {c_name}: {c_score}/3 امتیاز\n"
            f"▫️ {o_name}: {o_score}/3 امتیاز\n"
            "────────────────────────────\n"
        )

        async with aiosqlite.connect(DATABASE_PATH) as db:
            if c_score > o_score:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, c_id))
                await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (stake, o_id))
                res_text += f"🏆 پیروز مسابقه: {c_name} (+{stake} PTS)"
            elif o_score > c_score:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, o_id))
                await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (stake, c_id))
                res_text += f"🏆 پیروز مسابقه: {o_name} (+{stake} PTS)"
            else:
                res_text += "🤝 نتیجه مساوی شد و تغییری در امتیازات صورت نگرفت."
            await db.commit()

        del ACTIVE_DUELS[duel_id]
        await safe_edit_message(bot, res_text, chat_id=chat_id, message_id=msg_id)
        return

    q_data = duel["questions"][q_idx]
    duel["answered"] = {}

    buttons = []
    for opt_idx, opt_text in enumerate(q_data["options"]):
        buttons.append([InlineKeyboardButton(f"▫️ {opt_text}", callback_data=f"ans_duel_{duel_id}_{opt_idx}")])

    text = render_duel_question_text(duel, q_data, q_idx)
    await safe_edit_message(bot, text, reply_markup=InlineKeyboardMarkup(buttons), chat_id=chat_id, message_id=msg_id)

    loop = asyncio.get_event_loop()
    duel["timer_task"] = loop.create_task(question_timeout_worker(bot, duel_id, q_idx))

# Router
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    iran_now = get_iran_now()

    if data == "home":
        await start(update, context)

    elif data == "duel_help":
        text = (
            "⚔️ راهنمای دوئل دونفره در گروه:\n"
            "────────────────────────────\n"
            "1. در گروه روی پیام شخص مورد نظر ریپلای بزنید.\n"
            "2. کلمه 'دوئل' یا دستور /duel را بفرستید.\n"
            "3. یک رقابت اطلاعات عمومی ۳ سوالی آغاز می‌شود.\n"
            "4. برنده رقابت 25 امتیاز به همراه نشان کاربری دریافت می‌کند!"
        )
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data.startswith("accept_duel_"):
        duel_id = data.replace("accept_duel_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if not duel:
            await query.answer("این مسابقه منقضی شده است.", show_alert=True)
            return

        if query.from_user.id != duel["opponent"]["id"]:
            await query.answer("تنها هماورد دعوت‌شده مجاز به پذیرش چالش است.", show_alert=True)
            return

        await proceed_duel(context.bot, duel_id)

    elif data.startswith("reject_duel_"):
        duel_id = data.replace("reject_duel_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if duel and query.from_user.id in [duel["opponent"]["id"], duel["challenger"]["id"]]:
            del ACTIVE_DUELS[duel_id]
            await safe_edit_message(query, "✕ رقابت لغو گردید.")

    elif data.startswith("ans_duel_"):
        parts = data.split("_")
        duel_id = parts[2]
        chosen_idx = int(parts[3])
        duel = ACTIVE_DUELS.get(duel_id)

        if not duel:
            await query.answer("این مسابقه به پایان رسیده است.", show_alert=True)
            return

        user_id = query.from_user.id
        if user_id not in [duel["challenger"]["id"], duel["opponent"]["id"]]:
            await query.answer("شما در این رقابت حضور ندارید.", show_alert=True)
            return

        if user_id in duel["answered"]:
            await query.answer("پاسخ شما پیش‌تر ثبت گردیده است.", show_alert=True)
            return

        curr_q = duel["questions"][duel["current_q"]]
        is_correct = (chosen_idx == curr_q["correct_idx"])
        duel["answered"][user_id] = is_correct

        if is_correct:
            if user_id == duel["challenger"]["id"]:
                duel["challenger"]["score"] += 1
            else:
                duel["opponent"]["score"] += 1
            await query.answer("✅ پاسخ صحیح ثبت شد.")
        else:
            await query.answer("❌ پاسخ ثبت شد.")

        q_text = render_duel_question_text(duel, curr_q, duel["current_q"])
        await safe_edit_message(query, q_text, reply_markup=query.message.reply_markup)

        if len(duel["answered"]) >= 2:
            await asyncio.sleep(1)
            duel["current_q"] += 1
            await proceed_duel(context.bot, duel_id)

    elif data == "select_matches_today":
        await safe_edit_message(
            query,
            "⚡ مسابقات امروز (به وقت تهران)\n────────────────────────────\nلیگ مورد نظر را انتخاب فرمایید:",
            reply_markup=kb.get_matches_leagues_keyboard("today")
        )

    elif data == "select_matches_tomorrow":
        await safe_edit_message(
            query,
            "📅 مسابقات فردا (به وقت تهران)\n────────────────────────────\nلیگ مورد نظر را انتخاب فرمایید:",
            reply_markup=kb.get_matches_leagues_keyboard("tmrw")
        )

    elif data == "select_standings_league":
        await safe_edit_message(
            query,
            "🏆 جداول رده‌بندی لیگ‌های معتبر\n────────────────────────────\nلیگ مورد نظر را انتخاب فرمایید:",
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

        league_title = LEAGUE_TITLES.get(league_code, "Football")
        day_title = "امروز" if is_today else "فردا"

        if not matches:
            await safe_edit_message(query, f"⏳ در تاریخ {day_title} برای {league_title} مسابقه‌ای ثبت نشده است.", reply_markup=kb.get_back_button())
            return

        text = f"⚡ برنامه مسابقات {league_title} ({day_title})\n"
        text += "────────────────────────────\n\n"
        for m in matches[:8]:
            match_time = format_iran_time(m.get("date"))
            if m['status'] == "LIVE":
                status_badge = "🔴 در جریان"
            elif m['status'] == "FINISHED":
                status_badge = "🏁 پایان یافته"
            else:
                status_badge = f"⏰ {match_time}"

            score = f" [{m['home_score']} - {m['away_score']}]" if m['home_score'] is not None else ""
            text += (
                f"▫️ {m['home_team']} ✕ {m['away_team']}\n"
                f"   └ وضعیت: {status_badge}{score}\n"
                f"   └ ورزشگاه: {m['venue']}\n\n"
            )
        text += "────────────────────────────"
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data.startswith("table_"):
        league_code = data.replace("table_", "")
        league_title = LEAGUE_TITLES.get(league_code, "League")
        standings = await provider.get_standings(league_code)
        
        if not standings:
            await safe_edit_message(query, f"⏳ جدول {league_title} در دسترس نیست.", reply_markup=kb.get_back_button())
            return
            
        text = f"🏆 {league_title} Standings\n\n"
        text += "POS  TEAM           P   PTS\n"
        text += "───────────────────────────\n"
        for idx, s in enumerate(standings, 1):
            t_name = s['team'][:13]
            text += f"{idx:02d}   {t_name:<13}  {s['p']:<2}  {s['pts']:<3}\n"
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
            await safe_edit_message(query, "⏳ مسابقه پیش‌رویی در حال حاضر جهت پیش‌بینی یافت نشد.", reply_markup=kb.get_back_button())
            return

        for m in upcoming_matches:
            MATCH_CACHE[m["id"]] = m
            await record_ai_prediction_if_needed(m["id"])

        text = (
            "🎯 تالار پیش‌بینی مسابقات آینده\n"
            "────────────────────────────\n"
            "یکی از مسابقات زیر را جهت پیش‌بینی انتخاب کنید:\n"
            "(Escobar AI همگام با شما پیش‌بینی ثبت می‌کند)\n"
            "────────────────────────────"
        )
        await safe_edit_message(query, text, reply_markup=kb.get_upcoming_matches_keyboard(upcoming_matches))

    elif data.startswith("select_pred_"):
        match_id = data.replace("select_pred_", "")
        m = MATCH_CACHE.get(match_id)
        if not m:
            await safe_edit_message(query, "⚠️ زمان پیش‌بینی این مسابقه به پایان رسیده است.", reply_markup=kb.get_back_button())
            return

        match_time = format_iran_time(m.get("date"))
        text = (
            f"🎯 فرم پیش‌بینی مسابقه\n"
            "────────────────────────────\n"
            f"🏆 {m['league']}\n"
            f"▫️ {m['home_team']} ✕ {m['away_team']}\n"
            f"⏰ زمان مسابقه: {match_time} (به وقت تهران)\n"
            "────────────────────────────\n"
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
                await db.execute("UPDATE users SET total_predictions = total_predictions + 1 WHERE user_id = ?", (user_id,))
                await db.commit()
                await safe_edit_message(query, "✅ پیش‌بینی شما با موفقیت قفل و ثبت شد.", reply_markup=kb.get_back_button())
            except Exception:
                await safe_edit_message(query, "⚠️ پیش‌بینی شما برای این مسابقه قبلاً ثبت شده است.", reply_markup=kb.get_back_button())

    elif data == "user_profile":
        user_id = query.from_user.id
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT points, exact_predictions, correct_results, total_predictions, duel_wins FROM users WHERE user_id = ?", (user_id,)) as cur:
                u = await cur.fetchone()

        if u:
            pts, exact, correct, total, dw = u
            badge = get_user_badge(pts)
            text = (
                f"👤 کارت رسمی بازیکنی\n"
                "────────────────────────────\n"
                f"▫️ بازیکن: {query.from_user.first_name}\n"
                f"▫️ نشان کاربری: {badge} Level PRO\n"
                f"▫️ موجودی امتیاز: {pts} PTS\n"
                "────────────────────────────\n"
                f"▫️ پیروزی در دوئل‌ها: {dw} برد\n"
                f"▫️ کل پیش‌بینی‌ها: {total}\n"
                f"▫️ حدس دقیق نتیجه: {exact}\n"
                "────────────────────────────"
            )
            await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data == "leaderboard_hub":
        text = await show_leaderboard_text()
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

# Group Messages
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
    elif msg in ["پیشبینی", "پیش بینی"]:
        await update.message.reply_text("🎯 جهت ثبت پیش‌بینی و رقابت با Escobar AI، از دستور /start استفاده فرمایید.")
    elif msg in ["بازیها", "بازی ها"]:
        iran_now = get_iran_now()
        matches = await provider.get_matches(iran_now.strftime("%Y%m%d"), league_code="eng.1")
        if matches:
            t = "⚡ مسابقات منتخب امروز (به وقت تهران):\n────────────────────────────\n\n"
            for m in matches[:4]:
                tm = format_iran_time(m.get("date"))
                t += f"▫️ {m['home_team']} ✕ {m['away_team']} ({tm})\n"
            await update.message.reply_text(t)
        else:
            await update.message.reply_text("⏳ مسابقه‌ای برای امروز یافت نشد.")

async def post_init(application: Application):
    await init_db()
    await ensure_escobar_ai()

def main():
    t = threading.Thread(target=start_health_server, daemon=True)
    t.start()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ranking", leaderboard_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CommandHandler("duel", trigger_duel))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_messages))

    logger.info("Bot fully online with crash-proof telegram handlers!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
