"""
=============================================================================
پچ جامع و کامل برای bot.py - Football Hub Bot
تمامی توابع، هندلرها، تاکتیک‌ها، اقتصاد، و روترهای کلیکی منو
=============================================================================
"""

import html
import random
import re
from datetime import datetime, timezone, timedelta
import aiosqlite
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import BOT_TOKEN, ADMIN_ID, DATABASE_PATH, DEFAULT_POINTS
import keyboards as kb

IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

def get_iran_now():
    return datetime.now(IRAN_TZ)

# ---------------------------------------------------------------------------
# ۱. تعاریف و دیکشنری‌های استاندارد تاکتیک
# ---------------------------------------------------------------------------

TACTIC_NAMES = {
    "TIKI_TAKA": "🪄 تیکی‌تاکا (پاس‌کاری کوتاه و مالکیت)",
    "GEGENPRESS": "⚡ گگن‌پرس (فشار سنگین و پرس شدید)",
    "FAST_COUNTER": "🚀 ضدحمله سریع (انتقال برق‌آسا)",
    "PARK_BUS": "🧱 اتوبوسی (دفاع چندلایه و بسته)",
    "HIGH_LINE": "🔴 خط دفاعی بالا (پرس در زمین حریف)",
    "BALANCED": "🟡 متعادل و استاندارد",
    "DEEP": "🔵 دفاع عمقی و عقب‌نشینی",
    "SHORT": "🎯 بازیسازی با پاس کوتاه",
    "LONG": "🚀 بازیسازی با ارسال‌های بلند",
    "ALL_OUT": "🔥 هجوم همه‌جانبه و پرریسک",
}

DEFAULT_TACTIC = {
    "style": "TIKI_TAKA",
    "depth": "BALANCED",
    "buildup": "SHORT",
    "risk": "BALANCED"
}

CORRECTION_MAP = {
    "TIKI": "TIKI_TAKA",
    "FAST": "FAST_COUNTER",
    "PARK": "PARK_BUS",
    "HIGH": "HIGH_LINE",
    "ALL": "ALL_OUT"
}

# ---------------------------------------------------------------------------
# ۲. تابع دریافت و بازیابی خودکار تاکتیک پیش‌فرض (get_user_tactics)
# ---------------------------------------------------------------------------

async def get_user_tactics(user_id: int) -> dict:
    """دریافت تاکتیک کاربر با ثبت خودکار پیش‌فرض و اصلاح کدهای مخدوش دیتابیس"""
    try:
        async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
            async with db.execute(
                "SELECT style, depth, buildup, risk FROM user_tactics WHERE user_id = ?",
                (user_id,)
            ) as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    style = CORRECTION_MAP.get(row[0], row[0])
                    depth = CORRECTION_MAP.get(row[1], row[1])
                    buildup = CORRECTION_MAP.get(row[2], row[2])
                    risk = CORRECTION_MAP.get(row[3], row[3])
                    return {
                        "style": style or "TIKI_TAKA",
                        "depth": depth or "BALANCED",
                        "buildup": buildup or "SHORT",
                        "risk": risk or "BALANCED"
                    }

            # اگر تاکتیکی برای کاربر نبود، پیش‌فرض را ذخیره کن
            now_str = get_iran_now().strftime("%Y-%m-%d %H:%M")
            await db.execute("""
                INSERT OR IGNORE INTO user_tactics (user_id, style, depth, buildup, risk, updated_at)
                VALUES (?, 'TIKI_TAKA', 'BALANCED', 'SHORT', 'BALANCED', ?)
            """, (user_id, now_str))
            await db.commit()
    except Exception as e:
        pass

    return DEFAULT_TACTIC.copy()

# ---------------------------------------------------------------------------
# ۳. منوی تاکتیک‌ها به زبان فارسی (tactics_menu_cmd)
# ---------------------------------------------------------------------------

async def tactics_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی کامل تاکتیک و استراتژی مربیگری با رابط کاربری فارسی"""
    user = update.effective_user
    tac = await get_user_tactics(user.id)

    text = (
        f"📋 <b>اتاق تاکتیک و استراتژی مربیگری: {html.escape(user.first_name)}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"▪ <b>سبک بازی (Style):</b>\n   ↳ {TACTIC_NAMES.get(tac['style'], tac['style'])}\n\n"
        f"▪ <b>عمق دفاع (Depth):</b>\n   ↳ {TACTIC_NAMES.get(tac['depth'], tac['depth'])}\n\n"
        f"▪ <b>نوع بازیسازی (Build-Up):</b>\n   ↳ {TACTIC_NAMES.get(tac['buildup'], tac['buildup'])}\n\n"
        f"▪ <b>درجه هجوم و ریسک (Risk):</b>\n   ↳ {TACTIC_NAMES.get(tac['risk'], tac['risk'])}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 <i>تاکتیک شما تاثیر مستقیم بر شانس گلزنی و خنثی‌سازی سبک حریف در مسابقات و لیگ دارد.</i>\n\n"
        "👇 برای تغییر، بخش مورد نظر را انتخاب کنید:"
    )

    kb_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ تغییر سبک بازی (Style)", callback_data="set_tac_step1")],
        [InlineKeyboardButton("2️⃣ عمق خط دفاعی (Depth)", callback_data="set_tac_step2")],
        [InlineKeyboardButton("3️⃣ نحوه بازیسازی (Build-Up)", callback_data="set_tac_step3")],
        [InlineKeyboardButton("4️⃣ ریسک و میزان هجوم (Risk)", callback_data="set_tac_step4")],
        [
            InlineKeyboardButton("🛡️ مشاهده ترکیب من", callback_data="view_lineup"),
            InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")
        ]
    ])

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb_markup, parse_mode="HTML")
        except Exception:
            pass
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

# ---------------------------------------------------------------------------
# ۴. تسویه حساب قطعی و ارسال جدول نهایی لیگ (settle_league_season)
# ---------------------------------------------------------------------------

async def settle_league_season(context: ContextTypes.DEFAULT_TYPE, db, s_id: str, chat_id: int = None):
    """تسویه لیگ: محاسبه رتبه‌ها، واریز جوایز، اتمام لیگ و ارسال پیام رسمی"""
    async with db.execute("""
        SELECT s.user_id, u.first_name, s.points, s.gd, s.won, s.drawn, s.lost, s.gf, s.ga
        FROM league_standings s 
        LEFT JOIN users u ON s.user_id = u.user_id
        WHERE s.season_id = ? 
        ORDER BY s.points DESC, s.gd DESC, s.gf DESC
    """, (s_id,)) as cur:
        final_ranks = await cur.fetchall()

    if not final_ranks:
        await db.execute("UPDATE league_seasons SET status = 'FINISHED' WHERE season_id = ?", (s_id,))
        await db.commit()
        return

    # اقتصاد متوازن جوایز پایان فصل
    prizes = {
        0: (5000, 1000),  # قهرمان: ۵۰۰۰ سکه + ۱۰۰۰ XP
        1: (3000, 600),   # نایب‌قهرمان: ۳۰۰۰ سکه + ۶۰۰ XP
        2: (1800, 400),   # رتبه سوم: ۱۸۰۰ سکه + ۴۰۰ XP
    }

    summary = (
        f"🏆 <b>پایان فصل و اعلام جدول رسمی لیگ سراسری</b>\n"
        f"🆔 شناسه لیگ: <code>{s_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    for idx, (uid, name, pts, gd, w, d, l, gf, ga) in enumerate(final_ranks):
        p_pts, p_xp = prizes.get(idx, (500, 150))
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (p_pts, uid))
        
        try:
            await db.execute("UPDATE users SET profile_xp = profile_xp + ? WHERE user_id = ?", (p_xp, uid))
        except Exception:
            pass
        
        medal = "🥇" if idx == 0 else ("🥈" if idx == 1 else ("🥉" if idx == 2 else f"<b>#{idx+1}</b>"))
        safe_name = html.escape(name or f"کاربر {uid}")
        summary += f"{medal} <b>{safe_name}</b> | <b>{pts}</b> امتیاز (تفاضل: <b>{gd:+d}</b>)\n"
        summary += f"   🎁 جایزه: <code>+{p_pts:,}</code> سکه | <code>+{p_xp}</code> XP\n\n"

    summary += "━━━━━━━━━━━━━━━━━━━━━━\n"
    summary += "🎉 تبریک به قهرمانان این فصل لیگ!\n"
    summary += "⚡ ادمین محترم می‌تواند با دستور <code>/l_on</code> فصل جدید را استارت بزند."

    await db.execute("UPDATE league_seasons SET status = 'FINISHED' WHERE season_id = ?", (s_id,))
    await db.commit()

    if chat_id and context and context.bot:
        try:
            await context.bot.send_message(chat_id=chat_id, text=summary, parse_mode="HTML")
        except Exception:
            pass

# ---------------------------------------------------------------------------
# ۵. دستور اتمام فوری لیگ (finish_league_instantly_cmd)
# ---------------------------------------------------------------------------

async def finish_league_instantly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور l_end: شبیه‌سازی بازی‌های باقیمانده، اتمام لیگ و اعلام برندگان"""
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID):
        await update.message.reply_text("⛔ این دستور اختصاصی ادمین اصلی ربات است.")
        return

    cid = update.effective_chat.id
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        async with db.execute("SELECT season_id FROM league_seasons WHERE status = 'ACTIVE'") as cur:
            row = await cur.fetchone()
            if not row:
                await update.message.reply_text("❌ هیچ لیگ فعالی در حال برگزاری نیست!")
                return
            s_id = row[0]

        async with db.execute("""
            SELECT id, home_user_id, away_user_id 
            FROM league_fixtures 
            WHERE season_id = ? AND (status = 'PENDING' OR status IS NULL OR status = '')
        """, (s_id,)) as cur:
            pending = await cur.fetchall()

        await update.message.reply_text(f"⚡ در حال شبیه‌سازی سریع {len(pending)} بازی باقیمانده و تسویه حساب لیگ...")

        now_time = get_iran_now().strftime("%Y-%m-%d %H:%M")
        for f_id, h_id, a_id in pending:
            async with db.execute("SELECT rating FROM user_cards WHERE user_id = ? AND is_in_lineup = 1", (h_id,)) as ccur:
                h_rows = await ccur.fetchall()
            async with db.execute("SELECT rating FROM user_cards WHERE user_id = ? AND is_in_lineup = 1", (a_id,)) as ccur:
                a_rows = await ccur.fetchall()

            h_rat = sum([r[0] for r in h_rows]) if h_rows else 375
            a_rat = sum([r[0] for r in a_rows]) if a_rows else 375

            prob_h = 0.45 + ((h_rat - a_rat) / 2000.0)
            prob_h = max(0.15, min(0.75, prob_h))

            rv = random.random()
            if rv < prob_h:
                s1, s2 = random.randint(1, 4), random.randint(0, 2)
            elif rv < prob_h + 0.25:
                s1 = s2 = random.randint(0, 3)
            else:
                s1, s2 = random.randint(0, 2), random.randint(1, 4)

            w1, d1, l1, pts1 = (1, 0, 0, 3) if s1 > s2 else ((0, 1, 0, 1) if s1 == s2 else (0, 0, 1, 0))
            w2, d2, l2, pts2 = (1, 0, 0, 3) if s2 > s1 else ((0, 1, 0, 1) if s1 == s2 else (0, 0, 1, 0))

            await db.execute("""
                UPDATE league_fixtures 
                SET home_score = ?, away_score = ?, status = 'FINISHED', played_date = ? 
                WHERE id = ?
            """, (s1, s2, now_time, f_id))

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

        await db.commit()
        await settle_league_season(context, db, s_id, chat_id=cid)

# ---------------------------------------------------------------------------
# ۶. دستور جدول لیگ (league_cmd)
# ---------------------------------------------------------------------------

async def league_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش جدول رده‌بندی لیگ فعال یا آخرین فصل برگزارشده"""
    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("""
            SELECT season_id, status, created_at 
            FROM league_seasons 
            WHERE status = 'ACTIVE' 
            ORDER BY created_at DESC LIMIT 1
        """) as cur:
            season_row = await cur.fetchone()

        is_active = True
        if not season_row:
            is_active = False
            async with db.execute("""
                SELECT season_id, status, created_at 
                FROM league_seasons 
                WHERE status = 'FINISHED' 
                ORDER BY created_at DESC LIMIT 1
            """) as cur:
                season_row = await cur.fetchone()

        if not season_row:
            msg_text = (
                "🏆 <b>لیگ سراسری فوتبال FC</b>\n\n"
                "❌ در حال حاضر هیچ لیگی فعال نیست.\n"
                "⚡ ادمین می‌تواند با دستور <code>/l_on</code> لیگ جدید را آغاز کند."
            )
            if update.callback_query:
                await update.callback_query.edit_message_text(msg_text, reply_markup=kb.get_back_button(), parse_mode="HTML")
            elif update.effective_message:
                await update.effective_message.reply_text(msg_text, reply_markup=kb.get_back_button(), parse_mode="HTML")
            return

        s_id, status, c_date = season_row
        status_label = "🟢 در حال برگزاری" if is_active else "🏁 پایان‌یافته"

        async with db.execute("""
            SELECT s.user_id, u.first_name, s.played, s.won, s.drawn, s.lost, s.gf, s.ga, s.gd, s.points
            FROM league_standings s 
            LEFT JOIN users u ON s.user_id = u.user_id
            WHERE s.season_id = ? 
            ORDER BY s.points DESC, s.gd DESC, s.gf DESC
        """, (s_id,)) as cur:
            standings = await cur.fetchall()

        text = (
            f"🏆 <b>جدول رده‌بندی لیگ سراسری</b> ({status_label})\n"
            f"🆔 شناسه: <code>{s_id}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<code>رتبه | تیم | بازی | تفاضل | امتیاز</code>\n"
        )

        for idx, (uid, name, p, w, d, l, gf, ga, gd, pts) in enumerate(standings):
            medal = "🥇" if idx == 0 else ("🥈" if idx == 1 else ("🥉" if idx == 2 else f"#{idx+1}"))
            safe_name = html.escape(name or f"کاربر {uid}")[:12]
            text += f"{medal} <b>{safe_name}</b> | {p} ب | {gd:+d} | <b>{pts}</b> امتیـاز\n"

        text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        if is_active:
            text += "⚽ بازی‌ها به صورت روزانه شبیه‌سازی می‌شوند.\n"
            text += "💡 ادمین می‌تواند با <code>/pl</code> یک دور بازی را شبیه‌سازی کند."
        else:
            text += "✅ مسابقات این فصل به پایان رسیده و جوایز اهدا شده است."

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb.get_back_button(), parse_mode="HTML")
        except Exception:
            pass
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=kb.get_back_button(), parse_mode="HTML")

# ---------------------------------------------------------------------------
# ۷. پردازشگر جامع کلمات فارسی (handle_group_messages)
# ---------------------------------------------------------------------------

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر کلمات فارسی: ترکیب، تاکتیک، منو، لیگ، مارکت و..."""
    if not update.effective_message or not update.effective_message.text:
        return

    msg = update.effective_message.text.strip().lower()

    # منوی اصلی
    if msg in ["منو", "منوی اصلی", "منوی ربات", "menu", "شروع", "start"]:
        await start(update, context)
    # ترکیب
    elif msg in ["ترکیب", "ترکیب من", "تیم", "تیم من", "lineup", "squad"]:
        await lineup_cmd(update, context)
    # تاکتیک
    elif msg in ["تاکتیک", "تاکتیک‌ها", "تاکتیکها", "tactic", "tactics"]:
        await tactics_menu_cmd(update, context)
    # لیگ
    elif msg in ["لیگ", "جدول لیگ", "league"]:
        await league_cmd(update, context)
    # مارکت
    elif msg in ["مارکت", "فروشگاه", "بازار", "market", "shop"]:
        await market_cmd(update, context)
    # فروش
    elif msg in ["فروش", "فروش کارت", "sell"]:
        await sell_menu_cmd(update, context)
    # کارت‌های من
    elif msg in ["کارت‌های من", "کارت های من", "کارت‌هام", "کارت هام", "کارت‌ها", "mycards"]:
        await my_cards_cmd(update, context)
    # ارتقا
    elif msg in ["ارتقا", "ارتقاء", "پیشرفت", "evo", "upgrade"]:
        await evolution_menu_cmd(update, context)
    # پک روزانه
    elif msg in ["پک روزانه", "پک رایگان", "dailypack", "free pack"]:
        await daily_pack_cmd(update, context)
    # دوئل
    elif msg in ["دوئل", "کل‌کل", "کلکل", "duel"]:
        await trigger_duel(update, context)
    # پنالتی
    elif msg in ["پنالتی", "penalty"]:
        await trigger_penalty_shootout(update, context)
    # کارت بازی
    elif msg in ["کارت بازی", "کارت‌بازی", "cardmatch"]:
        await trigger_card_match(update, context)
    # شوت
    elif msg in ["شوت", "شوت روزانه", "shoot"]:
        await daily_shoot_cmd(update, context)
    # پاداش
    elif msg in ["جایزه", "پاداش", "جایزه روزانه", "daily"]:
        await daily_reward_cmd(update, context)
    # گردونه
    elif msg in ["گردونه", "گردونه شانس", "wheel"]:
        await spin_wheel_cmd(update, context)
    # جک‌پات
    elif msg in ["جکپات", "جک‌پات", "jackpot"]:
        await jackpot_cmd(update, context)
    # لیدربورد
    elif msg in ["لیدربورد", "رتبه‌بندی", "رتبه بندی", "جدول برترین‌ها", "top", "ranking"]:
        await leaderboard_cmd(update, context)
    # ماموریت‌ها
    elif msg in ["ماموریت", "ماموریت‌ها", "ماموریتها", "quests"]:
        await quests_cmd(update, context)
    elif msg in ["پروفایل", "مشخصات", "profile", "stats", "آمار"]:
        target_user = update.effective_user
        if update.message and update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
        await user_profile_handler(update.effective_message, target_user=target_user)

# ---------------------------------------------------------------------------
# ۸. گردونه شانس بدون پوچ (spin_wheel_cmd)
# ---------------------------------------------------------------------------

async def spin_wheel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """گردونه شانس روزانه با پاداش تضمینی (حذف کامل احتمال ۰ سکه)"""
    user = update.effective_user
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH, timeout=30.0) as db:
        async with db.execute("SELECT last_spin_date, points FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            last_date = row[0] if row else ""
            current_pts = row[1] if row else 0

        if last_date == today_str:
            msg = "⏳ شما گردونه شانس امروز را چرخانده‌اید!\nفردا برای چرخش دوباره بازگردید."
            if update.callback_query:
                await update.callback_query.edit_message_text(msg, reply_markup=kb.get_back_button())
            elif update.effective_message:
                await update.effective_message.reply_text(msg, reply_markup=kb.get_back_button())
            return

        wheel_options = [
            (50, 30),    # ۵۰ سکه (۳۰٪ شانس)
            (100, 30),   # ۱۰۰ سکه (۳۰٪ شانس)
            (200, 20),   # ۲۰۰ سکه (۲۰٪ شانس)
            (350, 12),   # ۳۵۰ سکه (۱۲٪ شانس)
            (600, 6),    # ۶۰۰ سکه (۶٪ شانس)
            (1200, 2),   # ۱۲۰۰ سکه جک‌پات (۲٪ شانس)
        ]

        prizes, weights = zip(*wheel_options)
        won_amount = random.choices(prizes, weights=weights, k=1)[0]

        await db.execute("""
            UPDATE users 
            SET points = points + ?, last_spin_date = ? 
            WHERE user_id = ?
        """, (won_amount, today_str, user.id))
        await db.commit()

    res_msg = (
        f"🎰 <b>گردونه شانس چرخید و متوقف شد!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎁 تبریک! شما برنده <b>+{won_amount:,} سکه</b> شدید!\n"
        f"💰 موجودی جدید شما: <b>{(current_pts + won_amount):,} سکه</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ چرخش بعدی فردا فعال خواهد شد."
    )

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(res_msg, reply_markup=kb.get_back_button(), parse_mode="HTML")
        except Exception:
            pass
    elif update.effective_message:
        await update.effective_message.reply_text(res_msg, reply_markup=kb.get_back_button(), parse_mode="HTML")

# ---------------------------------------------------------------------------
# ۹. رَپر هوشمند callback_router (اتصال تمام دکمه‌های منو و رفع باگ split)
# ---------------------------------------------------------------------------

def wrap_callback_router(original_router):
    """
    روتر پوششی که دکمه‌های جاافتاده منو و ذخیره تاکتیک‌ها را هندل کرده
    و بقیه درخواست‌ها را به روتر اصلی هدایت می‌کند.
    """
    async def wrapped_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return
        data = query.data
        uid = update.effective_user.id

        # ۱. رفع باگ حیاتی split در ذخیره تاکتیک‌ها
        if data.startswith("save_tac_"):
            parts = data.split("_", 3)
            if len(parts) >= 4:
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
                await query.answer("✅ تاکتیک جدید با موفقیت ذخیره شد!")
            await tactics_menu_cmd(update, context)
            return

        elif data == "open_tactics":
            await query.answer()
            await tactics_menu_cmd(update, context)
            return

        # ۲. دکمه‌های مسابقات امروز و فردا
        elif data == "select_matches_today":
            await query.answer()
            try:
                await query.edit_message_text(
                    "⚽ <b>انتخاب لیگ برای مسابقات امروز:</b>\nلیگ مورد نظر خود را انتخاب کنید:",
                    reply_markup=kb.get_matches_leagues_keyboard("today"),
                    parse_mode="HTML"
                )
            except Exception:
                pass
            return

        elif data == "select_matches_tomorrow":
            await query.answer()
            try:
                await query.edit_message_text(
                    "📅 <b>انتخاب لیگ برای مسابقات فردا:</b>\nلیگ مورد نظر خود را انتخاب کنید:",
                    reply_markup=kb.get_matches_leagues_keyboard("tomorrow"),
                    parse_mode="HTML"
                )
            except Exception:
                pass
            return

        # ۳. جدول رده‌بندی لیگ
        elif data == "select_standings_league":
            await query.answer()
            await league_cmd(update, context)
            return

        # ۴. مرکز پیش‌بینی
        elif data == "predictions_hub":
            await query.answer()
            try:
                await query.edit_message_text(
                    "🎯 <b>مرکز پیش‌بینی و جک‌پات مسابقات:</b>\n"
                    "برای شرکت در فرم مسابقات یا جک‌پات هفتگی، روی دکمه زیر کلیک کنید:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🏦 شرکت در جک‌پات مسابقات", callback_data="jackpot_hub")],
                        [InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")]
                    ]),
                    parse_mode="HTML"
                )
            except Exception:
                pass
            return

        # ۵. گردونه شانس
        elif data == "spin_wheel":
            await query.answer()
            await spin_wheel_cmd(update, context)
            return

        # ۶. جک‌پات
        elif data == "jackpot_hub":
            await query.answer()
            await jackpot_cmd(update, context)
            return

        # در غیر این صورت، هندلر اصلی bot.py را اجرا کن
        await original_router(update, context)

    return wrapped_callback_router
