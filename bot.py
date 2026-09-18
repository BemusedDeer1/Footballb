import os
import threading
import logging
import asyncio
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone

from telegram import Update
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# آیدی سیستمی هوش مصنوعی
ESCOBAR_AI_ID = 999999999

# منطقه زمانی ایران (UTC+3:30)
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

def get_iran_now():
    return datetime.now(IRAN_TZ)

# -------------------------------------------------------------
# ۱. مینی وب‌سرور سبک برای پایدار نگه داشتن سرور کلود
# -------------------------------------------------------------
class SimpleHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Football Hub Bot with Escobar AI is Running! 200 OK")

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHealthServer)
    logger.info(f"Health server listening on port {port}")
    server.serve_forever()

LEAGUE_TITLES = {
    "eng.1": "🇬🇧 لیگ برتر انگلیس",
    "esp.1": "🇪🇸 لالیگا اسپانیا",
    "ita.1": "🇮🇹 سری آ ایتالیا",
    "ger.1": "🇩🇪 بوندسلیگا آلمان",
    "fra.1": "🇫🇷 لوشامپیونه فرانسه",
    "all": "🌍 بازی‌های مهم منتخب"
}

MATCH_CACHE = {}

# -------------------------------------------------------------
# ۲. آماده‌سازی Escobar AI و بررسی خودکار امتیازات
# -------------------------------------------------------------
async def ensure_escobar_ai():
    """ثبت یا اطمینان از وجود Escobar AI در جدول کاربران"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, first_name, username, points)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET first_name=?
        """, (ESCOBAR_AI_ID, "Escobar AI 🤖", "escobar_ai", 15, "Escobar AI 🤖"))
        await db.commit()

async def record_ai_prediction_if_needed(match_id: str):
    """ثبت پیش‌بینی هوشمند توسط خود ربات برای مسابقه"""
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
# ۳. هندلرهای تلگرام
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ESCOBAR_AI_ID:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
                INSERT INTO users (user_id, first_name, username)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET first_name=?, username=?
            """, (user.id, user.first_name, user.username, user.first_name, user.username))
            await db.commit()

    text = (
        f"⚽ **به FOOTBALL HUB خوش آمدید {user.first_name}!**\n\n"
        "مرجع نتایج زنده، برنامه مسابقات و پیش‌بینی آنلاین.\n"
        "🤖 **رقیب هوش مصنوعی شما: Escobar AI در جدول حاضر است!**\n\n"
        "یکی از گزینه‌های زیر را انتخاب کنید:"
    )
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=kb.get_main_menu(), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=kb.get_main_menu(), parse_mode="Markdown")

async def show_leaderboard_text():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT first_name, points, total_predictions FROM users ORDER BY points DESC, total_predictions DESC") as cur:
            all_users = await cur.fetchall()

    text = "🏅 **جدول رنکینگ و امتیازات اعضا:**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not all_users:
        text += "هنوز امتیازی ثبت نشده است."
    else:
        for idx, u in enumerate(all_users, 1):
            if idx == 1:
                badge = "🥇"
            elif idx == 2:
                badge = "🥈"
            elif idx == 3:
                badge = "🥉"
            else:
                badge = f"{idx}."

            name = u[0]
            pts = u[1]
            text += f"{badge} **{name}** — `{pts} امتیاز`\n"
    return text

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await show_leaderboard_text()
    await update.message.reply_text(text, parse_mode="Markdown")

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    iran_now = get_iran_now()

    if data == "home":
        await start(update, context)

    elif data == "select_matches_today":
        await query.message.edit_text(
            "🔥 **مشاهده بازی‌های امروز (به وقت ایران)**\n\nلیگ مورد نظر را انتخاب کنید:",
            reply_markup=kb.get_matches_leagues_keyboard("today"),
            parse_mode="Markdown"
        )

    elif data == "select_matches_tomorrow":
        await query.message.edit_text(
            "📅 **مشاهده بازی‌های فردا (به وقت ایران)**\n\nلیگ مورد نظر را انتخاب کنید:",
            reply_markup=kb.get_matches_leagues_keyboard("tmrw"),
            parse_mode="Markdown"
        )

    elif data == "select_standings_league":
        await query.message.edit_text(
            "🏆 **مشاهده جداول لیگ‌ها**\n\nجدول کدام لیگ را می‌خواهید؟",
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
            await query.message.edit_text(
                f"⏳ برای {league_title} در تاریخ {day_title} مسابقه‌ای ثبت نشده است.",
                reply_markup=kb.get_back_button()
            )
            return

        text = f"🔥 **برنامه مسابقات {league_title} ({day_title}):**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for m in matches[:8]:
            status_icon = "🟢 در حال برگزاری" if m['status'] == "LIVE" else ("✅ پایان یافته" if m['status'] == "FINISHED" else "⏳ شروع نشده")
            score_line = f"\n⚽ نتیجه: {m['home_score']} - {m['away_score']}" if m['home_score'] is not None else ""
            text += (
                f"🏆 {m['league']}\n"
                f"⚪ {m['home_team']} 🆚 {m['away_team']} 🔴\n"
                f"وضعیت: {status_icon}{score_line}\n"
                f"🏟 ورزشگاه: {m['venue']}\n\n"
            )
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data.startswith("table_"):
        league_code = data.replace("table_", "")
        league_title = LEAGUE_TITLES.get(league_code, "لیگ")
        standings = await provider.get_standings(league_code)
        
        if not standings:
            await query.message.edit_text(f"⏳ جدول {league_title} در دسترس نیست.", reply_markup=kb.get_back_button())
            return
            
        text = f"🏆 **جدول رده‌بندی {league_title} (۱۰ تیم برتر):**\n━━━━━━━━━━━━━━━━━━━━\n"
        text += "`رتبه | تیم             | ب  | امت`\n"
        text += "`--------------------------------`\n"
        for idx, s in enumerate(standings, 1):
            team_name = s['team'][:13]
            text += f"`{idx:<4} | {team_name:<15} | {s['p']:<2} | {s['pts']:<3}`\n"
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
            await query.message.edit_text("⏳ در حال حاضر مسابقه شروع‌نشده‌ای برای ثبت پیش‌بینی موجود نیست.", reply_markup=kb.get_back_button())
            return

        for m in upcoming_matches:
            MATCH_CACHE[m["id"]] = m
            # ثبت پیش‌بینی خودکار برای Escobar AI
            await record_ai_prediction_if_needed(m["id"])

        text = (
            "🎯 **بخش پیش‌بینی مسابقات داغ:**\n\n"
            "یکی از بازی‌های آینده را انتخاب و ثبت کنید:\n"
            "*(هوش مصنوعی Escobar AI نیز پیش‌بینی خود را ثبت می‌کند)*\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        await query.message.edit_text(
            text,
            reply_markup=kb.get_upcoming_matches_keyboard(upcoming_matches),
            parse_mode="Markdown"
        )

    elif data.startswith("select_pred_"):
        match_id = data.replace("select_pred_", "")
        m = MATCH_CACHE.get(match_id)
        if not m:
            await query.message.edit_text("⚠️ اطلاعات بازی منقضی شده است.", reply_markup=kb.get_back_button())
            return

        text = (
            f"🎯 **پیش‌بینی مسابقه:**\n\n"
            f"🏆 {m['league']}\n"
            f"⚪ **{m['home_team']}** 🆚 **{m['away_team']}** 🔴\n"
            f"🏟 {m['venue']}\n\n"
            "گزینه خود را انتخاب کنید:"
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
            async with db.execute("SELECT points, exact_predictions, correct_results, total_predictions, streak, xp, level FROM users WHERE user_id = ?", (user_id,)) as cur:
                u = await cur.fetchone()

        if u:
            pts, exact, correct, total, streak, xp, lvl = u
            acc = round((correct / total * 100), 1) if total > 0 else 0
            text = (
                f"👤 **پروفایل کاربری | {query.from_user.first_name}**\n\n"
                f"💎 سطح: {lvl}  |  ⭐ تجربه: {xp} XP\n"
                f"🏆 مجموع امتیازات: {pts}\n"
                f"🎯 پیش‌بینی دقیق: {exact}\n"
                f"🏅 برنده/مساوی درست: {correct}\n"
                f"⚽ تعداد کل پیش‌بینی‌ها: {total}\n"
                f"🔥 رکورد Streak فعال: {streak}\n"
                f"📈 نرخ دقت: {acc}%\n"
            )
            await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data == "leaderboard_hub":
        text = await show_leaderboard_text()
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data in ["my_teams", "search_team"]:
        await query.message.edit_text("⭐ این قابلیت به زودی در آپدیت بعدی فعال می‌شود.", reply_markup=kb.get_back_button())

# -------------------------------------------------------------
# ۴. پردازش پیام‌ها و دستورات فارسی در گروه‌ها
# -------------------------------------------------------------
async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.strip() if update.message and update.message.text else ""
    if not msg:
        return

    # پاسخ به کامندهای فارسی در گروه
    if msg in ["شروع", "منو", "فوتبال"]:
        await start(update, context)
    elif msg in ["جدول", "رنکینگ", "امتیازات"]:
        await leaderboard_cmd(update, context)
    elif msg in ["پیشبینی", "پیش بینی"]:
        update.callback_query = None
        # فراخوانی نمایش منوی بازی‌های پیش‌بینی
        await update.message.reply_text("🎯 برای ثبت پیش‌بینی و رقابت با Escobar AI دستور /start را بزنید یا از دکمه‌ها استفاده کنید.")
    elif msg in ["بازیها", "بازی ها"]:
        iran_now = get_iran_now()
        matches = await provider.get_matches(iran_now.strftime("%Y%m%d"), league_code="eng.1")
        if matches:
            t = "🔥 **بازی‌های امروز (لیگ برتر انگلیس):**\n\n"
            for m in matches[:4]:
                t += f"⚪ {m['home_team']} 🆚 {m['away_team']} 🔴\n"
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
    app.add_handler(CallbackQueryHandler(callback_router))
    # هندلر پیام‌های متنی و کامندهای فارسی
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_messages))

    logger.info("Bot starting with Iran Time & Escobar AI integration...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
