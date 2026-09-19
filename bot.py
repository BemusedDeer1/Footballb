import os
import threading
import logging
import random
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# سرور پایدار
class SimpleHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Football Hub Premium Engine is Online! 200 OK")

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

async def ensure_user(user):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, first_name, username, points)
            VALUES (?, ?, ?, 100)
            ON CONFLICT(user_id) DO UPDATE SET first_name=?, username=?
        """, (user.id, user.first_name, user.username, user.first_name, user.username))
        await db.commit()

async def ensure_escobar_ai():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, first_name, username, points)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET first_name=?
        """, (ESCOBAR_AI_ID, "Escobar AI 🤖", "escobar_ai", 150, "Escobar AI 🤖"))
        await db.commit()

async def record_ai_prediction_if_needed(match_id: str):
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    text = (
        f"⚽ **FOOTBALL HUB** | `PRO EDITION`\n"
        "─" * 28 + "\n"
        f"درود **{user.first_name}**، به مرکز حرفه‌ای فوتبال خوش آمدید.\n\n"
        "▫️ نتایج زنده و برنامه مسابقات معتبر جهان\n"
        "▫️ رقابت پیش‌بینی و هماوردی با `Escobar AI`\n"
        "▫️ دوئل اطلاعات عمومی فوتبال در گروه‌ها\n"
        "─" * 28 + "\n"
        "یک بخش را جهت شروع انتخاب کنید:"
    )
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=kb.get_main_menu(), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=kb.get_main_menu(), parse_mode="Markdown")

async def show_leaderboard_text():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT first_name, points, duel_wins FROM users ORDER BY points DESC, duel_wins DESC") as cur:
            all_users = await cur.fetchall()

    text = "🎖 **رتبه‌بندی قهرمانان فوتبال هاب**\n"
    text += "─" * 28 + "\n\n"
    if not all_users:
        text += "▫️ هنوز کاربری ثبت نشده است."
    else:
        for idx, u in enumerate(all_users, 1):
            name, pts, wins = u[0], u[1], u[2]
            badge = get_user_badge(pts)
            pos = "🥇" if idx == 1 else ("🥈" if idx == 2 else ("🥉" if idx == 3 else f"`{idx:02d}`"))
            text += f"{pos} {badge} **{name}**\n   └ ⚡ `{pts} PTS`  ▫️  ⚔️ `{wins} W`\n"
    text += "\n" + "─" * 28
    return text

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await show_leaderboard_text()
    await update.message.reply_text(text, parse_mode="Markdown")

# دوئل اطلاعات عمومی
async def trigger_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚔️ **نحوه شروع دوئل:**\n"
            "روی پیام حریفتان ریپلای کرده و دستور `دوئل` یا `/duel` را بفرستید.",
            parse_mode="Markdown"
        )
        return

    challenger = update.effective_user
    opponent = update.message.reply_to_message.from_user

    if opponent.is_bot:
        await update.message.reply_text("🤖 رقابت با ربات در بخش دوئل مجاز نیست.")
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
        "⚔️ **میدان دوئل اطلاعات عمومی فوتبال**\n"
        "─" * 28 + "\n"
        f"▫️ چلنجر: **{challenger.first_name}**\n"
        f"▫️ هماورد: **{opponent.first_name}**\n"
        f"▫️ جایزه رقابت: `+25 PTS`\n"
        f"▫️ زمان هر سوال: `15 ثانیه`\n"
        "─" * 28 + "\n"
        f"آیا **{opponent.first_name}** چالش را می‌پذیرد؟"
    )
    sent_msg = await update.message.reply_text(text, reply_markup=duel_kb, parse_mode="Markdown")
    ACTIVE_DUELS[duel_id]["message_id"] = sent_msg.message_id

def render_duel_question_text(duel, q_data, q_idx):
    c_name = duel["challenger"]["name"]
    o_name = duel["opponent"]["name"]
    c_id = duel["challenger"]["id"]
    o_id = duel["opponent"]["id"]

    c_status = "✅ ثبت شد" if c_id in duel["answered"] else "⏳ در حال بررسی..."
    o_status = "✅ ثبت شد" if o_id in duel["answered"] else "⏳ در حال بررسی..."

    text = (
        f"❓ **سوال `{q_idx + 1}` از `3`**\n"
        "─" * 28 + "\n"
        f"📌 **{q_data['question']}**\n\n"
        f"⏱ مهلت پاسخگویی: `15 ثانیه`\n"
        "─" * 28 + "\n"
        f"▫️ {c_name}: {c_status}\n"
        f"▫️ {o_name}: {o_status}\n"
    )
    return text

async def question_timeout_worker(context: ContextTypes.DEFAULT_TYPE, duel_id: str, q_idx: int):
    await asyncio.sleep(15)
    duel = ACTIVE_DUELS.get(duel_id)
    if duel and duel["current_q"] == q_idx:
        duel["current_q"] += 1
        await proceed_duel(context.bot, duel_id)

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
            "🏁 **پایان دوئل اطلاعات عمومی**\n"
            "─" * 28 + "\n"
            f"▫️ {c_name}: `{c_score}/3` امتیاز\n"
            f"▫️ {o_name}: `{o_score}/3` امتیاز\n"
            "─" * 28 + "\n"
        )

        async with aiosqlite.connect(DATABASE_PATH) as db:
            if c_score > o_score:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, c_id))
                await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (stake, o_id))
                res_text += f"🏆 پیروز مسابقه: **{c_name}** (`+{stake} PTS`)"
            elif o_score > c_score:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, o_id))
                await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (stake, c_id))
                res_text += f"🏆 پیروز مسابقه: **{o_name}** (`+{stake} PTS`)"
            else:
                res_text += "🤝 نتیجه مساوی شد و تغییری در امتیازات صورت نگرفت."
            await db.commit()

        del ACTIVE_DUELS[duel_id]
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=res_text, parse_mode="Markdown")
        except Exception:
            pass
        return

    q_data = duel["questions"][q_idx]
    duel["answered"] = {}

    buttons = []
    for opt_idx, opt_text in enumerate(q_data["options"]):
        buttons.append([InlineKeyboardButton(f"▫️ {opt_text}", callback_data=f"ans_duel_{duel_id}_{opt_idx}")])

    text = render_duel_question_text(duel, q_data, q_idx)

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
    except Exception:
        pass

    loop = asyncio.get_event_loop()
    duel["timer_task"] = loop.create_task(question_timeout_worker(None, duel_id, q_idx))

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    iran_now = get_iran_now()

    if data == "home":
        await query.answer()
        await start(update, context)

    elif data == "duel_help":
        await query.answer()
        text = (
            "⚔️ **راهنمای دوئل دونفره در گروه:**\n"
            "─" * 28 + "\n"
            "1. در گروه روی پیام شخص مورد نظر ریپلای بزنید.\n"
            "2. کلمه `دوئل` یا دستور `/duel` را بنویسید.\n"
            "3. یک مسابقه اطلاعات عمومی ۳ سوالی با تایمر ۱۵ ثانیه‌ای شروع می‌شود.\n"
            "4. برنده رقابت `25 امتیاز` به همراه نشان ویژه دریافت می‌کند!"
        )
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data.startswith("accept_duel_"):
        duel_id = data.replace("accept_duel_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if not duel:
            await query.answer("این مسابقه منقضی شده است.", show_alert=True)
            return

        if query.from_user.id != duel["opponent"]["id"]:
            await query.answer("تنها هماورد دعوت‌شده مجاز به پذیرش چالش است.", show_alert=True)
            return

        await query.answer("دوئل آغاز شد!")
        await proceed_duel(context.bot, duel_id)

    elif data.startswith("reject_duel_"):
        duel_id = data.replace("reject_duel_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if duel and query.from_user.id in [duel["opponent"]["id"], duel["challenger"]["id"]]:
            del ACTIVE_DUELS[duel_id]
            await query.answer("دوئل لغو شد.")
            await query.message.edit_text("✕ رقابت لغو گردید.")

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
        try:
            await query.message.edit_text(q_text, reply_markup=query.message.reply_markup, parse_mode="Markdown")
        except Exception:
            pass

        if len(duel["answered"]) >= 2:
            await asyncio.sleep(1)
            duel["current_q"] += 1
            await proceed_duel(context.bot, duel_id)

    elif data == "select_matches_today":
        await query.answer()
        await query.message.edit_text(
            "⚡ **مسابقات امروز (به وقت تهران)**\n─" + "─" * 26 + "\nلیگ مورد نظر را انتخاب فرمایید:",
            reply_markup=kb.get_matches_leagues_keyboard("today"),
            parse_mode="Markdown"
        )

    elif data == "select_matches_tomorrow":
        await query.answer()
        await query.message.edit_text(
            "📅 **مسابقات فردا (به وقت تهران)**\n─" + "─" * 26 + "\nلیگ مورد نظر را انتخاب فرمایید:",
            reply_markup=kb.get_matches_leagues_keyboard("tmrw"),
            parse_mode="Markdown"
        )

    elif data == "select_standings_league":
        await query.answer()
        await query.message.edit_text(
            "🏆 **جداول رده‌بندی لیگ‌های معتبر**\n─" + "─" * 26 + "\nلیگ مورد نظر را انتخاب فرمایید:",
            reply_markup=kb.get_standings_leagues_keyboard(),
            parse_mode="Markdown"
        )

    elif data.startswith("today_") or data.startswith("tmrw_"):
        await query.answer()
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
            await query.message.edit_text(
                f"⏳ در تاریخ {day_title} برای {league_title} مسابقه‌ای ثبت نشده است.",
                reply_markup=kb.get_back_button()
            )
            return

        text = f"⚡ **برنامه مسابقات {league_title}** | `{day_title}`\n"
        text += "─" * 28 + "\n\n"
        for m in matches[:8]:
            match_time = format_iran_time(m.get("date"))
            if m['status'] == "LIVE":
                status_badge = "🔴 `در جریان`"
            elif m['status'] == "FINISHED":
                status_badge = "🏁 `پایان یافته`"
            else:
                status_badge = f"⏰ `{match_time}`"

            score = f" `{m['home_score']} - {m['away_score']}`" if m['home_score'] is not None else ""
            
            text += (
                f"▫️ **{m['home_team']}** ✕ **{m['away_team']}**\n"
                f"   └ وضعیت: {status_badge}{score}\n"
                f"   └ ورزشگاه: `{m['venue']}`\n\n"
            )
        text += "─" * 28
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data.startswith("table_"):
        await query.answer()
        league_code = data.replace("table_", "")
        league_title = LEAGUE_TITLES.get(league_code, "League")
        standings = await provider.get_standings(league_code)
        
        if not standings:
            await query.message.edit_text(f"⏳ جدول {league_title} در دسترس نیست.", reply_markup=kb.get_back_button())
            return
            
        text = f"🏆 **{league_title} Standings**\n"
        text += "```text\n"
        text += "POS  TEAM           P   PTS\n"
        text += "───────────────────────────\n"
        for idx, s in enumerate(standings, 1):
            t_name = s['team'][:13]
            text += f"{idx:02d}   {t_name:<13}  {s['p']:<2}  {s['pts']:<3}\n"
        text += "```"
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data == "predictions_hub":
        await query.answer()
        today_str = iran_now.strftime("%Y%m%d")
        tmrw_str = (iran_now + timedelta(days=1)).strftime("%Y%m%d")

        candidate_matches = []
        for l_code in ["eng.1", "esp.1", "ita.1", "ger.1"]:
            candidate_matches.extend(await provider.get_matches(today_str, league_code=l_code))
            candidate_matches.extend(await provider.get_matches(tmrw_str, league_code=l_code))

        upcoming_matches = [m for m in candidate_matches if m.get("status") == "UPCOMING"]

        if not upcoming_matches:
            await query.message.edit_text("⏳ مسابقه پیش‌رویی در حال حاضر جهت پیش‌بینی یافت نشد.", reply_markup=kb.get_back_button())
            return

        for m in upcoming_matches:
            MATCH_CACHE[m["id"]] = m
            await record_ai_prediction_if_needed(m["id"])

        text = (
            "🎯 **تالار پیش‌بینی مسابقات آینده**\n"
            "─" * 28 + "\n"
            "یکی از مسابقات زیر را انتخاب کرده و نتیجه را حدس بزنید:\n"
            "*(Escobar AI همگام با شما پیش‌بینی خواهد کرد)*\n"
            "─" * 28
        )
        await query.message.edit_text(text, reply_markup=kb.get_upcoming_matches_keyboard(upcoming_matches), parse_mode="Markdown")

    elif data.startswith("select_pred_"):
        await query.answer()
        match_id = data.replace("select_pred_", "")
        m = MATCH_CACHE.get(match_id)
        if not m:
            await query.message.edit_text("⚠️ زمان پیش‌بینی این مسابقه به پایان رسیده است.", reply_markup=kb.get_back_button())
            return

        match_time = format_iran_time(m.get("date"))
        text = (
            f"🎯 **فرم پیش‌بینی مسابقه**\n"
            "─" * 28 + "\n"
            f"🏆 {m['league']}\n"
            f"▫️ **{m['home_team']}** ✕ **{m['away_team']}**\n"
            f"⏰ زمان مسابقه: `{match_time}` (به وقت تهران)\n"
            "─" * 28 + "\n"
            "پیش‌بینی شما برای نتیجه نهایی چیست؟"
        )
        await query.message.edit_text(text, reply_markup=kb.get_prediction_keyboard(m['id']), parse_mode="Markdown")

    elif data.startswith("pred_out_"):
        await query.answer()
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
                await query.message.edit_text("✅ **پیش‌بینی شما با موفقیت قفل و ثبت شد.**", reply_markup=kb.get_back_button())
            except Exception:
                await query.message.edit_text("⚠️ پیش‌بینی شما برای این مسابقه پیش‌تر ثبت شده است.", reply_markup=kb.get_back_button())

    elif data == "user_profile":
        await query.answer()
        user_id = query.from_user.id
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT points, exact_predictions, correct_results, total_predictions, duel_wins FROM users WHERE user_id = ?", (user_id,)) as cur:
                u = await cur.fetchone()

        if u:
            pts, exact, correct, total, dw = u
            badge = get_user_badge(pts)
            text = (
                f"👤 **کارت رسمی بازیکنی**\n"
                "─" * 28 + "\n"
                f"▫️ بازیکن: **{query.from_user.first_name}**\n"
                f"▫️ نشان کاربری: {badge} `Level PRO`\n"
                f"▫️ موجودی امتیاز: `{pts} PTS`\n"
                "─" * 28 + "\n"
                f"▫️ پیروزی در دوئل‌ها: `{dw} برد`\n"
                f"▫️ کل پیش‌بینی‌های ثبت‌شده: `{total}`\n"
                f"▫️ حدس دقیق نتیجه: `{exact}`\n"
                "─" * 28
            )
            await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data == "leaderboard_hub":
        await query.answer()
        text = await show_leaderboard_text()
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

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
        await update.message.reply_text("🎯 جهت ثبت پیش‌بینی و رقابت با Escobar AI، از دستور /start استفاده کنید.")
    elif msg in ["بازیها", "بازی ها"]:
        iran_now = get_iran_now()
        matches = await provider.get_matches(iran_now.strftime("%Y%m%d"), league_code="eng.1")
        if matches:
            t = "⚡ **مسابقات منتخب امروز (به وقت تهران):**\n" + "─" * 28 + "\n\n"
            for m in matches[:4]:
                tm = format_iran_time(m.get("date"))
                t += f"▫️ **{m['home_team']}** ✕ **{m['away_team']}** (`{tm}`)\n"
            await update.message.reply_text(t, parse_mode="Markdown")
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

    logger.info("Bot running with Premium Dashboard UI!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
