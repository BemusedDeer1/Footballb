import os
import asyncio
import logging
from datetime import datetime, timedelta
from aiohttp import web
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

# تنظیمات لاگ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------
# ۱. مینی وب‌سرور سبک برای پاس کردن Health Check در Koyeb / Render
# -------------------------------------------------------------
async def health_check_handler(request):
    """پاسخ مثبت به درخواست‌های مانیتورینگ سرور ابری"""
    return web.Response(text="Football Bot is active and healthy! ⚽", status=200)

async def start_dummy_web_server():
    """راه‌اندازی سرور روی پورت تعیین‌شده توسط کلود"""
    app = web.Application()
    app.router.add_get("/", health_check_handler)
    app.router.add_get("/health", health_check_handler)
    
    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Web health server started successfully on port {port}")

# -------------------------------------------------------------
# ۲. دستورات و مدیریت رویدادهای ربات تلگرام
# -------------------------------------------------------------
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
        "مرجع هوشمند نتایج زنده، مسابقات آینده، پیش‌بینی مسابقات و رقابت با دوستان.\n"
        "یک بخش را از منوی زیر انتخاب کنید:"
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

    elif data in ["matches_today", "matches_tomorrow"]:
        target_date = datetime.utcnow() if data == "matches_today" else datetime.utcnow() + timedelta(days=1)
        matches = await provider.get_matches(target_date.strftime("%Y%m%d"))
        
        if not matches:
            await query.message.edit_text("⏳ در حال حاضر مسابقه‌ای در این تاریخ ثبت نشده است.", reply_markup=kb.get_back_button())
            return

        text = "🔥 **برنامه مسابقات معتبر:**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for m in matches[:6]:
            status_icon = "🟢 در حال برگزاری" if m['status'] == "LIVE" else ("✅ پایان یافته" if m['status'] == "FINISHED" else "⏳ شروع نشده")
            score_line = f"\n⚽ نتیجه: {m['home_score']} - {m['away_score']}" if m['home_score'] is not None else ""
            text += (
                f"🏆 {m['league']}\n"
                f"⚪ {m['home_team']} 🆚 {m['away_team']} 🔴\n"
                f"وضعیت: {status_icon}{score_line}\n"
                f"🏟 ورزشگاه: {m['venue']}\n\n"
            )
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data == "standings_hub":
        standings = await provider.get_standings("eng.1")
        if not standings:
            await query.message.edit_text("⏳ جدول در حال حاضر در دسترس نیست.", reply_markup=kb.get_back_button())
            return
            
        text = "🏆 **جدول لیگ برتر انگلیس (۱۰ تیم اول):**\n━━━━━━━━━━━━━━━━━━━━\n"
        text += "`تیم              | ب | م | ب | امت`\n"
        for s in standings:
            text += f"`{s['team'][:12]:<12} | {s['w']} | {s['d']} | {s['l']} | {s['pts']}`\n"
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

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

    elif data == "predictions_hub":
        matches = await provider.get_matches()
        if not matches:
            await query.message.edit_text("⏳ مسابقه‌ای برای پیش‌بینی وجود ندارد.", reply_markup=kb.get_back_button())
            return
        m = matches[0]
        text = (
            f"🎯 **ثبت پیش‌بینی مسابقه:**\n\n"
            f"🏆 {m['league']}\n"
            f"⚪ {m['home_team']} 🆚 {m['away_team']} 🔴\n\n"
            "گزینه مورد نظر خود را انتخاب کنید:"
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

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پنل مدیریت اختصاصی برای ادمین تعیین‌شده"""
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
        "سیستم در وضعیت پایدار و آنلاین است."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# -------------------------------------------------------------
# ۳. اجرای همزمان وب‌سرور و ربات تلگرام
# -------------------------------------------------------------
async def run_services():
    # آماده‌سازی دیتابیس
    await init_db()
    
    # روشن کردن وب‌سرور برای جلوگیری از خواب رفتن و ارور پورت
    await start_dummy_web_server()

    # راه‌اندازی بات تلگرام با ساختار غیراسپم
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(callback_router))

    logger.info("Initializing Telegram Bot Polling...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # نگه‌داشتن تسک به صورت زنده تا برنامه بسته نشود
    stop_event = asyncio.Event()
    await stop_event.wait()

def main():
    try:
        asyncio.run(run_services())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application shut down.")

if __name__ == "__main__":
    main()
    await query.answer()
    data = query.data

    if data == "home":
        await start(update, context)

    elif data in ["matches_today", "matches_tomorrow"]:
        target_date = datetime.utcnow() if data == "matches_today" else datetime.utcnow() + timedelta(days=1)
        matches = await provider.get_matches(target_date.strftime("%Y%m%d"))
        
        if not matches:
            await query.message.edit_text("⏳ در حال حاضر مسابقه‌ای در این تاریخ ثبت نشده است.", reply_markup=kb.get_back_button())
            return

        text = "🔥 **برنامه مسابقات معتبر:**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for m in matches[:6]:
            status_icon = "🟢 در حال برگزاری" if m['status'] == "LIVE" else ("✅ پایان یافته" if m['status'] == "FINISHED" else "⏳ شروع نشده")
            score_line = f"\n⚽ نتیجه: {m['home_score']} - {m['away_score']}" if m['home_score'] is not None else ""
            text += (
                f"🏆 {m['league']}\n"
                f"⚪ {m['home_team']} 🆚 {m['away_team']} 🔴\n"
                f"وضعیت: {status_icon}{score_line}\n"
                f"🏟 ورزشگاه: {m['venue']}\n\n"
            )
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data == "standings_hub":
        standings = await provider.get_standings("eng.1")
        text = "🏆 **جدول لیگ برتر انگلیس (۱۰ تیم اول):**\n━━━━━━━━━━━━━━━━━━━━\n"
        text += "`تیم              | ب | م | ب | امت`\n"
        for s in standings:
            text += f"`{s['team'][:12]:<12} | {s['w']} | {s['d']} | {s['l']} | {s['pts']}`\n"
        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

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
        for idx, user in enumerate(top_users):
            text += f"{medals[idx]} {user[0]} — **{user[1]}** امتیاز\n"

        await query.message.edit_text(text, reply_markup=kb.get_back_button(), parse_mode="Markdown")

    elif data == "predictions_hub":
        matches = await provider.get_matches()
        if not matches:
            await query.message.edit_text("⏳ مسابقه بازی برای پیش‌بینی وجود ندارد.", reply_markup=kb.get_back_button())
            return
        m = matches[0]
        text = (
            f"🎯 **ثبت پیش‌بینی مسابقه حساس:**\n\n"
            f"🏆 {m['league']}\n"
            f"⚪ {m['home_team']} 🆚 {m['away_team']} 🔴\n\n"
            "گزینه مورد نظر خود را انتخاب کنید:"
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

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پنل مدیریت اختصاصی برای ادمین تعیین‌شده"""
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
        "سیستم آماده همگام‌سازی و اعمال نتایج مسابقات است."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

def main():
    import asyncio
    asyncio.run(init_db())

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(callback_router))

    print("Football Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
