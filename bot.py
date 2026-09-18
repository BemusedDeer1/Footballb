import os
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
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

class SimpleHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Football Bot is Running and Healthy! 200 OK")

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

# کش ساده برای دسترسی به مشخصات بازی‌ها
MATCH_CACHE = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, first_name, username)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET first_name=?, username=?
        """, (user.id, user.first_name, user.username, user.first_name, user.username))
        await db.commit()

    text = (
        f"⚽ **به FOOTBALL HUB خوش آمدید {user.first_name}!**\n\n"
        "مرجع هوشمند نتایج زنده، برنامه مسابقات آینده، جداول معتبر و پیش‌بینی مسابقات.\n"
        "یکی از گزینه‌های زیر را انتخاب کنید:"
    )
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=kb.get_main_menu(), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=kb.get_main_menu(), parse_mode="Markdown")

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "home":
        await start(update, context)

    elif data == "select_matches_today":
        await query.message.edit_text(
            "🔥 **مشاهده بازی‌های امروز**\n\nلطفاً لیگ مورد نظر را انتخاب کنید:",
            reply_markup=kb.get_leagues_keyboard("today"),
            parse_mode="Markdown"
        )

    elif data == "select_matches_tomorrow":
        await query.message.edit_text(
            "📅 **مشاهده بازی‌های فردا**\n\nلطفاً لیگ مورد نظر را انتخاب کنید:",
            reply_markup=kb.get_leagues_keyboard("tmrw"),
            parse_mode="Markdown"
        )

    elif data == "select_standings_league":
        await query.message.edit_text(
            "🏆 **مشاهده جداول لیگ‌ها**\n\nجدول کدام لیگ را می‌خواهید مشاهده کنید؟",
            reply_markup=kb.get_leagues_keyboard("table"),
            parse_mode="Markdown"
        )

    elif data.startswith("today_") or data.startswith("tmrw_"):
        is_today = data.startswith("today_")
        league_code = data.replace("today_", "").replace("tmrw_", "")
        target_date = datetime.utcnow() if is_today else datetime.utcnow() + timedelta(days=1)
        date_str = target_date.strftime("%Y%m%d")

        matches = []
        if league_code == "all":
            for l_id in ["eng.1", "esp.1", "ita.1"]:
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
        if league_code == "all":
            league_code = "eng.1"

        league_title = LEAGUE_TITLES.get(league_code, "لیگ")
        standings = await provider.get_standings(league_code)
        
        if not standings:
            await query.message.edit_text(
                f"⏳ جدول {league_title} در حال حاضر در دسترس نیست.",
                reply_markup=kb.get_back_button()
            )
            return
            
        text = f"🏆 **جدول رده‌بندی {league_title} (۱۰ تیم برتر):**\n━━━━━━━━━━━━━━━━━━━━\n"
        text += "`رتبه | تیم             | ب  | امت`\n"
        text += "`--------------------------------`\n"
        for idx, s in enumerate(standings, 1):
            team_name = s['team'][:13]
            text += f"`{idx:<4} | {team_name:<15} | {s['p']:<2} | {s['pts']:<3}`\n"
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    # =========================================================================
    # بخش پیش‌بینی هوشمند (فقط مسابقات آینده و شروع‌نشده)
    # =========================================================================
    elif data == "predictions_hub":
        today_str = datetime.utcnow().strftime("%Y%m%d")
        tmrw_str = (datetime.utcnow() + timedelta(days=1)).strftime("%Y%m%d")

        # جمع‌آوری بازی‌های امروز و فردا
        candidate_matches = []
        for l_code in ["eng.1", "esp.1", "ita.1", "ger.1"]:
            # بازی‌های امروز
            candidate_matches.extend(await provider.get_matches(today_str, league_code=l_code))
            # بازی‌های فردا
            candidate_matches.extend(await provider.get_matches(tmrw_str, league_code=l_code))

        # فیلتر جدی: فقط بازی‌هایی که قطعاً شروع نشده‌اند (UPCOMING)
        upcoming_matches = [m for m in candidate_matches if m.get("status") == "UPCOMING"]

        if not upcoming_matches:
            await query.message.edit_text(
                "⏳ در حال حاضر هیچ مسابقه‌ای که شروع نشده باشد برای ثبت پیش‌بینی پیدا نشد.",
                reply_markup=kb.get_back_button()
            )
            return

        # ذخیره در کش
        for m in upcoming_matches:
            MATCH_CACHE[m["id"]] = m

        text = (
            "🎯 **بخش پیش‌بینی مسابقات آینده:**\n\n"
            "یکی از بازی‌های زیر را که هنوز شروع نشده است انتخاب کنید و نتیجه را حدس بزنید:\n"
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
            # اگر در حافظه نبود، مستقیم از بازی‌های فردا مجدد جستجو کن
            candidate = await provider.get_matches((datetime.utcnow() + timedelta(days=1)).strftime("%Y%m%d"))
            for item in candidate:
                if item["id"] == match_id:
                    m = item
                    break

        if not m:
            await query.message.edit_text("⚠️ اطلاعات مسابقه یافت نشد یا مهلت پیش‌بینی به پایان رسیده است.", reply_markup=kb.get_back_button())
            return

        text = (
            f"🎯 **ثبت پیش‌بینی مسابقه:**\n\n"
            f"🏆 {m['league']}\n"
            f"⚪ **{m['home_team']}** 🆚 **{m['away_team']}** 🔴\n"
            f"🏟 {m['venue']}\n\n"
            "نتیجه احتمالی را انتخاب کنید:"
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
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT first_name, points FROM users ORDER BY points DESC LIMIT 5") as cur:
                top_users = await cur.fetchall()

        text = "🏅 **جدول برترین کاربران (رنکینگ کلی):**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        if not top_users:
            text += "هنوز امتیازی ثبت نشده است."
        else:
            for idx, user in enumerate(top_users):
                text += f"{medals[idx]} {user[0]} — **{user[1]}** امتیاز\n"

        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data == "my_teams":
        await query.message.edit_text("⭐ به زودی: امکان افزودن تیم‌های دلخواه به لیست علاقه‌مندی‌ها.", reply_markup=kb.get_back_button())

    elif data == "search_team":
        await query.message.edit_text("🔎 به زودی: موتور جستجوی اختصاصی تیم‌ها و وضعیت فرم ۵ بازی اخیر.", reply_markup=kb.get_back_button())

    elif data == "private_leagues_hub":
        await query.message.edit_text("👥 **لیگ خصوصی بین دوستان**\n\nبه زودی با ساخت کد اختصاصی می‌توانید دوستانتان را به چالش بکشید!", reply_markup=kb.get_back_button())

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            user_count = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM predictions") as cur:
            pred_count = (await cur.fetchone())[0]

    text = (
        "🤖 **پنل مدیریت فوتبال هاب**\n\n"
        f"👥 تعداد کل کاربران: {user_count}\n"
        f"🎯 کل پیش‌بینی‌های ثبت‌شده: {pred_count}\n"
        "وضعیت سرور و وب‌هوک کاملاً نرمال است."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def post_init(application: Application):
    await init_db()

def main():
    t = threading.Thread(target=start_health_server, daemon=True)
    t.start()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(callback_router))

    logger.info("Bot starting with polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
