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
        return "نامشخص"
    try:
        clean_str = utc_date_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(clean_str)
        dt_iran = dt_utc.astimezone(IRAN_TZ)
        return dt_iran.strftime("%H:%M")
    except Exception:
        return "20:00"

def get_user_badge(points: int) -> str:
    """محاسبه ایموجی سطح کاربر بر اساس امتیاز"""
    if points >= 200:
        return "💎"
    elif points >= 150:
        return "🥇"
    elif points >= 100:
        return "🥈"
    else:
        return "🥉"

# -------------------------------------------------------------
# ۱. مینی سرور سلامت برای پایداری ۲۴ ساعته
# -------------------------------------------------------------
class SimpleHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Football Hub Engine 2.0 with Duels is Online! 200 OK")

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHealthServer)
    logger.info(f"Health server listening on port {port}")
    server.serve_forever()

LEAGUE_TITLES = {
    "eng.1": "🇬🇧 Premier League",
    "esp.1": "🇪🇸 La Liga",
    "ita.1": "🇮🇹 Serie A",
    "ger.1": "🇩🇪 Bundesliga",
    "fra.1": "🇫🇷 Ligue 1",
    "all": "🌍 Top European Matches"
}

MATCH_CACHE = {}
ACTIVE_DUELS = {}

# -------------------------------------------------------------
# ۲. اطمینان از مقدار اولیه کاربران و Escobar AI
# -------------------------------------------------------------
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

# -------------------------------------------------------------
# ۳. هندلرهای منو و تلگرام
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    text = (
        f"⚽ **به اپلیکیشن FOOTBALL HUB خوش آمدید {user.first_name}!**\n"
        "──────────────────────\n"
        "⚡ مرکز نتایج زنده، برنامه مسابقات، پیش‌بینی و دوئل‌های دونفره!\n"
        "💰 موجودی اولیه شما: **100 امتیاز**\n"
        "🤖 **رقیب هوش مصنوعی شما: Escobar AI**\n\n"
        "یک بخش را از منوی زیر انتخاب کنید:"
    )
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=kb.get_main_menu(), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=kb.get_main_menu(), parse_mode="Markdown")

async def show_leaderboard_text():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT first_name, points, duel_wins FROM users ORDER BY points DESC, duel_wins DESC") as cur:
            all_users = await cur.fetchall()

    text = "🏅 **جدول رنکینگ و رقابت اعضا:**\n──────────────────────\n\n"
    if not all_users:
        text += "هنوز کاربری ثبت نشده است."
    else:
        for idx, u in enumerate(all_users, 1):
            name, pts, wins = u[0], u[1], u[2]
            badge = get_user_badge(pts)
            rank_str = "🥇" if idx == 1 else ("🥈" if idx == 2 else ("🥉" if idx == 3 else f"#{idx}"))
            text += f"{rank_str} {badge} **{name}** ➔ `{pts} PTS` (برد دوئل: {wins})\n"
    return text

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await show_leaderboard_text()
    await update.message.reply_text(text, parse_mode="Markdown")

# -------------------------------------------------------------
# ۴. سیستم دوئل اطلاعات عمومی فوتبالی (Duel System)
# -------------------------------------------------------------
async def trigger_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دعوت به دوئل با ریپلای روی پیام دوست در گروه"""
    if not update.message.reply_to_message:
        await update.message.reply_text("💡 برای دوئل، روی پیام یکی از دوستانتان در گروه ریپلای بزنید و بنویسید: `دوئل` یا `/duel`")
        return

    challenger = update.effective_user
    opponent = update.message.reply_to_message.from_user

    if opponent.is_bot:
        await update.message.reply_text("🤖 نمی‌توانید با ربات دوئل کنید!")
        return

    if challenger.id == opponent.id:
        await update.message.reply_text("⚠️ نمی‌توانید با خودتان دوئل کنید!")
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
        "answered": set()
    }

    duel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ قبول چالش دوئل", callback_data=f"accept_duel_{duel_id}"),
         InlineKeyboardButton("❌ رد چالش", callback_data=f"reject_duel_{duel_id}")]
    ])

    text = (
        f"⚔️ **چالش دوئل اطلاعات عمومی فوتبال!**\n"
        "──────────────────────\n"
        f"👤 چلنجر: **{challenger.first_name}**\n"
        f"🎯 حریف: **{opponent.first_name}**\n"
        f"💰 شرط مسابقه: **۲۵ امتیاز**\n"
        "❓ مسابقه شامل ۳ سوال سرعتی ۴ گزینه‌ای است.\n\n"
        f"آیا {opponent.first_name} چالش را می‌پذیرد؟"
    )
    await update.message.reply_text(text, reply_markup=duel_kb, parse_mode="Markdown")

async def start_duel_question(query, duel_id):
    duel = ACTIVE_DUELS.get(duel_id)
    if not duel:
        return

    q_idx = duel["current_q"]
    if q_idx >= len(duel["questions"]):
        # پایان دوئل و اعلام برنده
        c_score = duel["challenger"]["score"]
        o_score = duel["opponent"]["score"]
        stake = duel["stake"]

        c_id, c_name = duel["challenger"]["id"], duel["challenger"]["name"]
        o_id, o_name = duel["opponent"]["id"], duel["opponent"]["name"]

        res_text = (
            "🏁 **پایان دوئل اطلاعات عمومی فوتبال!**\n"
            "──────────────────────\n"
            f"📊 نتیجه نهایی:\n"
            f"👤 {c_name}: `{c_score}` پاسخ درست\n"
            f"👤 {o_name}: `{o_score}` پاسخ درست\n\n"
        )

        async with aiosqlite.connect(DATABASE_PATH) as db:
            if c_score > o_score:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, c_id))
                await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (stake, o_id))
                res_text += f"🏆 **تبریک به {c_name}! برنده ۲۵ امتیاز شد.** 🔥"
            elif o_score > c_score:
                await db.execute("UPDATE users SET points = points + ?, duel_wins = duel_wins + 1 WHERE user_id = ?", (stake, o_id))
                await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (stake, c_id))
                res_text += f"🏆 **تبریک به {o_name}! برنده ۲۵ امتیاز شد.** 🔥"
            else:
                res_text += "🤝 **نتیجه مساوی شد! هیچ امتیازی کسر نگردید.**"
            await db.commit()

        del ACTIVE_DUELS[duel_id]
        await query.message.edit_text(res_text, parse_mode="Markdown")
        return

    q_data = duel["questions"][q_idx]
    duel["answered"] = set()

    buttons = []
    for opt_idx, opt_text in enumerate(q_data["options"]):
        buttons.append([InlineKeyboardButton(f"🔘 {opt_text}", callback_data=f"ans_duel_{duel_id}_{opt_idx}")])

    text = (
        f"❓ **سوال شماره {q_idx + 1} از ۳:**\n"
        "──────────────────────\n"
        f"📌 {q_data['question']}\n\n"
        "هر دو بازیکن باید پاسخ خود را انتخاب کنند:"
    )
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

# -------------------------------------------------------------
# ۵. مسیریاب کلیک‌های شیشه‌ای (Router)
# -------------------------------------------------------------
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    iran_now = get_iran_now()

    if data == "home":
        await start(update, context)

    # قبول یا رد دوئل
    elif data.startswith("accept_duel_"):
        duel_id = data.replace("accept_duel_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if not duel:
            await query.message.edit_text("⚠️ این دوئل منقضی شده است.")
            return

        if query.from_user.id != duel["opponent"]["id"]:
            await query.answer("⛔ فقط حریف دعوت‌شده می‌تواند چالش را قبول کند!", show_alert=True)
            return

        await start_duel_question(query, duel_id)

    elif data.startswith("reject_duel_"):
        duel_id = data.replace("reject_duel_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if duel and query.from_user.id in [duel["opponent"]["id"], duel["challenger"]["id"]]:
            del ACTIVE_DUELS[duel_id]
            await query.message.edit_text("❌ دوئل لغو شد.")

    elif data.startswith("ans_duel_"):
        parts = data.split("_")
        duel_id = parts[2]
        chosen_idx = int(parts[3])
        duel = ACTIVE_DUELS.get(duel_id)

        if not duel:
            await query.answer("⚠️ دوئل به پایان رسیده است.", show_alert=True)
            return

        user_id = query.from_user.id
        if user_id not in [duel["challenger"]["id"], duel["opponent"]["id"]]:
            await query.answer("⛔ شما در این دوئل نیستید!", show_alert=True)
            return

        if user_id in duel["answered"]:
            await query.answer("⚠️ شما قبلاً به این سوال پاسخ داده‌اید!", show_alert=True)
            return

        duel["answered"].add(user_id)
        curr_q = duel["questions"][duel["current_q"]]

        if chosen_idx == curr_q["correct_idx"]:
            if user_id == duel["challenger"]["id"]:
                duel["challenger"]["score"] += 1
            else:
                duel["opponent"]["score"] += 1
            await query.answer("✅ پاسخ درست!", show_alert=False)
        else:
            await query.answer("❌ پاسخ غلط!", show_alert=False)

        # اگر هر دو نفر جواب دادند، رفتن به سوال بعدی
        if len(duel["answered"]) >= 2:
            duel["current_q"] += 1
            await start_duel_question(query, duel_id)

    # بازی‌های امروز و فردا
    elif data == "select_matches_today":
        await query.message.edit_text(
            "🔥 **مشاهده بازی‌های امروز (به وقت تهران)**\n\nلیگ مورد نظر را انتخاب کنید:",
            reply_markup=kb.get_matches_leagues_keyboard("today"),
            parse_mode="Markdown"
        )

    elif data == "select_matches_tomorrow":
        await query.message.edit_text(
            "📅 **مشاهده بازی‌های فردا (به وقت تهران)**\n\nلیگ مورد نظر را انتخاب کنید:",
            reply_markup=kb.get_matches_leagues_keyboard("tmrw"),
            parse_mode="Markdown"
        )

    elif data == "select_standings_league":
        await query.message.edit_text(
            "🏆 **مشاهده جداول معتبر فوتبال**\n\nجدول رده‌بندی کدام لیگ را می‌خواهید؟",
            reply_markup=kb.get_standings_leagues_keyboard(),
            parse_mode="Markdown"
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
            await query.message.edit_text(f"⏳ برای {league_title} مسابقه‌ای ثبت نشده است.", reply_markup=kb.get_back_button())
            return

        text = f"🔥 **برنامه مسابقات {league_title} ({day_title}):**\n──────────────────────\n\n"
        for m in matches[:8]:
            match_time = format_iran_time(m.get("date"))
            if m['status'] == "LIVE":
                status_badge = "🟢 LIVE"
            elif m['status'] == "FINISHED":
                status_badge = "✅ FT (پایان)"
            else:
                status_badge = f"⏳ شروع نشده | ⏰ ساعت: {match_time}"

            score_line = f"\n⚽ نتیجه: {m['home_score']} - {m['away_score']}" if m['home_score'] is not None else ""
            text += (
                f"🏆 {m['league']}\n"
                f"⚪ **{m['home_team']}** 🆚 **{m['away_team']}** 🔴\n"
                f"وضعیت: {status_badge}{score_line}\n"
                f"🏟 {m['venue']}\n"
                "──────────────────────\n"
            )
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data.startswith("table_"):
        league_code = data.replace("table_", "")
        league_title = LEAGUE_TITLES.get(league_code, "League")
        standings = await provider.get_standings(league_code)
        
        if not standings:
            await query.message.edit_text(f"⏳ جدول {league_title} در دسترس نیست.", reply_markup=kb.get_back_button())
            return
            
        text = f"🏆 **{league_title} Standings (Top 10)**\n"
        text += "```text\n"
        text += "#  | Team          | P  | Pts\n"
        text += "---+---------------+----+----\n"
        for idx, s in enumerate(standings, 1):
            team_name = s['team'][:13]
            text += f"{idx:<2} | {team_name:<13} | {s['p']:<2} | {s['pts']:<3}\n"
        text += "```"
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data == "predictions_hub":
        today_str = iran_now.strftime("%Y%m%d")
        tmrw_str = (iran_now + timedelta(days=1)).strftime("%Y%m%d")

        candidate_matches = []
        for l_code in ["eng.1", "esp.1", "ita.1", "ger.1"]:
            candidate_matches.extend(await provider.get_matches(today_str, league_code=l_code))
            candidate_matches.extend(await provider.get_matches(tmrw_str, league_code=l_code))

        upcoming_matches = [m for m in candidate_matches if m.get("status") == "UPCOMING"]

        if not upcoming_matches:
            await query.message.edit_text("⏳ مسابقه شروع‌نشده‌ای برای ثبت پیش‌بینی موجود نیست.", reply_markup=kb.get_back_button())
            return

        for m in upcoming_matches:
            MATCH_CACHE[m["id"]] = m
            await record_ai_prediction_if_needed(m["id"])

        text = (
            "🎯 **بخش پیش‌بینی مسابقات آینده:**\n\n"
            "یکی از بازی‌ها را انتخاب کنید:\n"
            "*(Escobar AI نیز در کنار شما پیش‌بینی ثبت می‌کند)*\n"
            "──────────────────────"
        )
        await query.message.edit_text(text, reply_markup=kb.get_upcoming_matches_keyboard(upcoming_matches), parse_mode="Markdown")

    elif data.startswith("select_pred_"):
        match_id = data.replace("select_pred_", "")
        m = MATCH_CACHE.get(match_id)
        if not m:
            await query.message.edit_text("⚠️ اطلاعات بازی منقضی شده است.", reply_markup=kb.get_back_button())
            return

        match_time = format_iran_time(m.get("date"))
        text = (
            f"🎯 **فرم پیش‌بینی مسابقه:**\n"
            "──────────────────────\n"
            f"🏆 {m['league']}\n"
            f"⚪ **{m['home_team']}** 🆚 **{m['away_team']}** 🔴\n"
            f"⏰ شروع مسابقه (به وقت ایران): `{match_time}`\n\n"
            "پیش‌بینی شما برای نتیجه بازی چیست؟"
        )
        await query.message.edit_text(text, reply_markup=kb.get_prediction_keyboard(m['id']), parse_mode="Markdown")

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
                await query.message.edit_text("✅ **پیش‌بینی شما با موفقیت ثبت شد و قفل گردید!**", reply_markup=kb.get_back_button())
            except Exception:
                await query.message.edit_text("⚠️ شما قبلاً پیش‌بینی خود را برای این بازی ثبت کرده‌اید.", reply_markup=kb.get_back_button())

    elif data == "user_profile":
        user_id = query.from_user.id
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT points, exact_predictions, correct_results, total_predictions, duel_wins FROM users WHERE user_id = ?", (user_id,)) as cur:
                u = await cur.fetchone()

        if u:
            pts, exact, correct, total, dw = u
            badge = get_user_badge(pts)
            text = (
                f"👤 **کارت بازیکن | {query.from_user.first_name}**\n"
                "──────────────────────\n"
                f"سطح بازیکن: {badge}\n"
                f"🏆 موجودی امتیاز: `{pts} PTS`\n"
                f"⚔️ بردهای دوئل: `{dw}`\n"
                f"🎯 پیش‌بینی دقیق: `{exact}`\n"
                f"⚽ کل پیش‌بینی‌ها: `{total}`\n"
            )
            await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data == "leaderboard_hub":
        text = await show_leaderboard_text()
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

# -------------------------------------------------------------
# ۶. پیام‌های متنی در گروه و کامندهای فارسی
# -------------------------------------------------------------
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
        await update.message.reply_text("🎯 برای ثبت پیش‌بینی و رقابت با هوش مصنوعی Escobar AI، دستور /start را لمس کنید.")
    elif msg in ["بازیها", "بازی ها"]:
        iran_now = get_iran_now()
        matches = await provider.get_matches(iran_now.strftime("%Y%m%d"), league_code="eng.1")
        if matches:
            t = "🔥 **بازی‌های منتخب امروز (به وقت ایران):**\n──────────────────────\n"
            for m in matches[:4]:
                tm = format_iran_time(m.get("date"))
                t += f"⚪ {m['home_team']} 🆚 {m['away_team']} (⏰ {tm})\n"
            await update.message.reply_text(t, parse_mode="Markdown")

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

    logger.info("Bot v2.0 running with Duels and Persistent Data!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
