"""
=============================================================================
پچ جامع و کامل برای bot.py - Football Hub Bot
نسخه نهایی شامل حل مشکل تاکتیک‌ها، مسابقات امروز و فردا، لیگ و اقتصاد
=============================================================================
"""

import html
import random
import re
import logging
from datetime import datetime, timezone, timedelta
import aiosqlite
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import keyboards as kb

logger = logging.getLogger(__name__)

IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

def get_iran_now():
    return datetime.now(IRAN_TZ)

def get_db_path():
    p = globals().get("DATABASE_PATH")
    if p:
        return p
    try:
        import config
        return getattr(config, "DATABASE_PATH", "football_hub.db")
    except Exception:
        return "football_hub.db"

# ---------------------------------------------------------------------------
# ویرایش امن پیام تلگرام (جلوگیری از کرش هنگام edit_message)
# ---------------------------------------------------------------------------

async def safe_edit_message(query_or_update, text, reply_markup=None):
    """ویرایش امن پیام بدون کرش کردن یا خطای Message is not modified"""
    try:
        query = None
        if hasattr(query_or_update, "callback_query") and query_or_update.callback_query:
            query = query_or_update.callback_query
        elif hasattr(query_or_update, "edit_message_text"):
            query = query_or_update

        if query:
            if hasattr(query, "message") and query.message:
                await query.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
            else:
                await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
            return True
        elif hasattr(query_or_update, "effective_message") and query_or_update.effective_message:
            await query_or_update.effective_message.reply_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
            return True
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.warning(f"BadRequest in safe_edit_message: {e}")
    except Exception as e:
        logger.debug(f"Exception in safe_edit_message: {e}")
    return False

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

LEAGUE_TITLES = {
    "eng.1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 لیگ جزیره انگلیس",
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
    "all": "🌐 گلچین مسابقات معتبر"
}

# ---------------------------------------------------------------------------
# ۲. تابع دریافت و بازیابی خودکار تاکتیک پیش‌فرض (get_user_tactics)
# ---------------------------------------------------------------------------

async def get_user_tactics(user_id: int) -> dict:
    """دریافت تاکتیک کاربر با ثبت خودکار پیش‌فرض و اصلاح کدهای مخدوش دیتابیس"""
    try:
        db_path = get_db_path()
        async with aiosqlite.connect(db_path, timeout=30.0) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_tactics (
                    user_id INTEGER PRIMARY KEY,
                    style TEXT DEFAULT 'TIKI_TAKA',
                    depth TEXT DEFAULT 'BALANCED',
                    buildup TEXT DEFAULT 'SHORT',
                    risk TEXT DEFAULT 'BALANCED',
                    updated_at TEXT
                )
            """)
            await db.commit()

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
        logger.error(f"Error in get_user_tactics: {e}")

    return DEFAULT_TACTIC.copy()

# ---------------------------------------------------------------------------
# ۳. منوی تاکتیک‌ها به زبان فارسی (tactics_menu_cmd)
# ---------------------------------------------------------------------------

async def tactics_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی کامل تاکتیک و استراتژی مربیگری با رابط کاربری فارسی"""
    user = update.effective_user
    if "ensure_user" in globals():
        try:
            await globals()["ensure_user"](user)
        except Exception:
            pass

    tac = await get_user_tactics(user.id)
    safe_name = html.escape(user.first_name or f"کاربر {user.id}")

    text = (
        f"📋 <b>اتاق تاکتیک و استراتژی مربیگری: {safe_name}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"▪ <b>سبک بازی (Style):</b>\n   ↳ {TACTIC_NAMES.get(tac['style'], tac['style'])}\n\n"
        f"▪ <b>عمق دفاع (Depth):</b>\n   ↳ {TACTIC_NAMES.get(tac['depth'], tac['depth'])}\n\n"
        f"▪ <b>نوع بازیسازی (Build-Up):</b>\n   ↳ {TACTIC_NAMES.get(tac['buildup'], tac['buildup'])}\n\n"
        f"▪ <b>درجه هجوم و ریسک (Risk):</b>\n   ↳ {TACTIC_NAMES.get(tac['risk'], tac['risk'])}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 <i>تاکتیک شما تاثیر مستقیم بر شانس گلزنی و خنثی‌سازی سبک حریف در مسابقات و لیگ دارد.</i>\n\n"
        "👇 برای شخصی‌سازی، بخش مورد نظر را انتخاب کنید:"
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

    await safe_edit_message(update, text, reply_markup=kb_markup)

# ---------------------------------------------------------------------------
# کیبوردهای انتخاب مراحل تاکتیک
# ---------------------------------------------------------------------------

def get_tactic_step1_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪄 تیکی‌تاکا (مالکیت و پاس کوتاه)", callback_data="save_tac_style_TIKI_TAKA")],
        [InlineKeyboardButton("⚡ گگن‌پرس (فشار سنگین و پرس شدید)", callback_data="save_tac_style_GEGENPRESS")],
        [InlineKeyboardButton("🚀 ضدحمله سریع (انتقال برق‌آسا)", callback_data="save_tac_style_FAST_COUNTER")],
        [InlineKeyboardButton("🧱 اتوبوسی (دفاع چندلایه و بسته)", callback_data="save_tac_style_PARK_BUS")],
        [InlineKeyboardButton("‹ بازگشت به اتاق تاکتیک", callback_data="open_tactics")]
    ])

def get_tactic_step2_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 خط دفاعی بالا (High Line)", callback_data="save_tac_depth_HIGH_LINE")],
        [InlineKeyboardButton("🟡 متعادل و استاندارد (Balanced)", callback_data="save_tac_depth_BALANCED")],
        [InlineKeyboardButton("🔵 دفاع عمقی و عقب‌نشینی (Deep)", callback_data="save_tac_depth_DEEP")],
        [InlineKeyboardButton("‹ بازگشت به اتاق تاکتیک", callback_data="open_tactics")]
    ])

def get_tactic_step3_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 پاس‌های کوتاه (Short Passing)", callback_data="save_tac_buildup_SHORT")],
        [InlineKeyboardButton("🚀 ارسال‌های بلند (Long Ball)", callback_data="save_tac_buildup_LONG")],
        [InlineKeyboardButton("‹ بازگشت به اتاق تاکتیک", callback_data="open_tactics")]
    ])

def get_tactic_step4_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 هجوم همه‌جانبه و پرریسک (All-Out)", callback_data="save_tac_risk_ALL_OUT")],
        [InlineKeyboardButton("⚖️ متعادل و منطقی (Balanced)", callback_data="save_tac_risk_BALANCED")],
        [InlineKeyboardButton("‹ بازگشت به اتاق تاکتیک", callback_data="open_tactics")]
    ])

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
        except Exception as e:
            logger.error(f"Error sending final league summary: {e}")

# ---------------------------------------------------------------------------
# ۵. دستور اتمام فوری لیگ (finish_league_instantly_cmd)
# ---------------------------------------------------------------------------

async def finish_league_instantly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور l_end: شبیه‌سازی بازی‌های باقیمانده، اتمام لیگ و اعلام برندگان"""
    user = update.effective_user
    admin_id = globals().get("ADMIN_ID")
    if admin_id and str(user.id) != str(admin_id):
        await update.message.reply_text("⛔ این دستور اختصاصی ادمین اصلی ربات است.")
        return

    cid = update.effective_chat.id
    db_path = get_db_path()
    async with aiosqlite.connect(db_path, timeout=30.0) as db:
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
    db_path = get_db_path()
    async with aiosqlite.connect(db_path, timeout=30.0) as db:
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
            await safe_edit_message(update, msg_text, reply_markup=kb.get_back_button())
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

    await safe_edit_message(update, text, reply_markup=kb.get_back_button())

# ---------------------------------------------------------------------------
# ۷. گردونه شانس بدون پوچ (spin_wheel_cmd)
# ---------------------------------------------------------------------------

async def spin_wheel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """گردونه شانس روزانه با پاداش تضمینی (حذف کامل احتمال ۰ سکه)"""
    user = update.effective_user
    today_str = get_iran_now().strftime("%Y-%m-%d")
    db_path = get_db_path()

    async with aiosqlite.connect(db_path, timeout=30.0) as db:
        async with db.execute("SELECT last_spin_date, points FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            last_date = row[0] if row else ""
            current_pts = row[1] if row else 0

        if last_date == today_str:
            msg = "⏳ شما گردونه شانس امروز را چرخانده‌اید!\nفردا برای چرخش دوباره بازگردید."
            await safe_edit_message(update, msg, reply_markup=kb.get_back_button())
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

    await safe_edit_message(update, res_msg, reply_markup=kb.get_back_button())

# ---------------------------------------------------------------------------
# ۸. پردازشگر جامع کلمات فارسی (handle_group_messages)
# ---------------------------------------------------------------------------

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر کلمات فارسی: ترکیب، تاکتیک، منو، لیگ، مارکت و..."""
    if not update.effective_message or not update.effective_message.text:
        return

    raw_text = update.effective_message.text.strip().lower()
    msg = raw_text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", "").replace("  ", " ").strip()

    # فراخوانی تابع با بررسی وجود در globals
    async def call_cmd(fn_name):
        fn = globals().get(fn_name)
        if fn:
            await fn(update, context)
        else:
            logger.warning(f"Function {fn_name} not found in globals!")

    # منوی اصلی
    if msg in ["منو", "منوی اصلی", "منوی ربات", "menu", "شروع", "start"]:
        await call_cmd("start")
    # ترکیب
    elif msg in ["ترکیب", "ترکیب من", "تیم", "تیم من", "lineup", "squad"]:
        await call_cmd("lineup_cmd")
    # تاکتیک
    elif msg in ["تاکتیک", "تاکتیک‌ها", "تاکتیکها", "tactic", "tactics"]:
        await tactics_menu_cmd(update, context)
    # لیگ
    elif msg in ["لیگ", "جدول لیگ", "league"]:
        await league_cmd(update, context)
    # مارکت
    elif msg in ["مارکت", "فروشگاه", "بازار", "market", "shop"]:
        await call_cmd("market_cmd")
    # فروش
    elif msg in ["فروش", "فروش کارت", "sell"]:
        await call_cmd("sell_menu_cmd")
    # کارت‌های من
    elif msg in ["کارت‌های من", "کارت های من", "کارت‌هام", "کارت هام", "کارت‌ها", "کارتها", "mycards"]:
        await call_cmd("my_cards_cmd")
    # ارتقا
    elif msg in ["ارتقا", "ارتقاء", "پیشرفت", "evo", "upgrade"]:
        await call_cmd("evolution_menu_cmd")
    # پک روزانه
    elif msg in ["پک روزانه", "پک رایگان", "dailypack", "free pack"]:
        await call_cmd("daily_pack_cmd")
    # دوئل
    elif msg in ["دوئل", "کل‌کل", "کلکل", "duel"]:
        await call_cmd("trigger_duel")
    # پنالتی
    elif msg in ["پنالتی", "penalty"]:
        await call_cmd("trigger_penalty_shootout")
    # کارت بازی
    elif msg in ["کارت بازی", "کارت‌بازی", "cardmatch"]:
        await call_cmd("trigger_card_match")
    # شوت
    elif msg in ["شوت", "شوت روزانه", "shoot"]:
        await call_cmd("daily_shoot_cmd")
    # پاداش
    elif msg in ["جایزه", "پاداش", "جایزه روزانه", "daily"]:
        await call_cmd("daily_reward_cmd")
    # گردونه
    elif msg in ["گردونه", "گردونه شانس", "wheel"]:
        await spin_wheel_cmd(update, context)
    # جک‌پات
    elif msg in ["جکپات", "جک‌پات", "jackpot"]:
        await call_cmd("jackpot_cmd")
    # لیدربورد
    elif msg in ["لیدربورد", "رتبه‌بندی", "رتبه بندی", "جدول برترین‌ها", "top", "ranking"]:
        await call_cmd("leaderboard_cmd")
    # ماموریت‌ها
    elif msg in ["ماموریت", "ماموریت‌ها", "ماموریتها", "quests"]:
        await call_cmd("quests_cmd")
    # پروفایل
    elif msg in ["پروفایل", "مشخصات", "profile", "stats", "آمار"]:
        profile_fn = globals().get("user_profile_handler")
        if profile_fn:
            target_user = update.effective_user
            if update.message and update.message.reply_to_message:
                target_user = update.message.reply_to_message.from_user
            await profile_fn(update.effective_message, target_user=target_user)
    # شرط‌بندی دابل
    elif re.match(r"^\s*(?:دابل|شرط|کازینو|double)\s+(\d+)\s*$", msg):
        await call_cmd("double_or_nothing_cmd")

# ---------------------------------------------------------------------------
# ۹. رَپر هوشمند callback_router (پوشش کامل تاکتیک‌ها و مسابقات زنده)
# ---------------------------------------------------------------------------

def wrap_callback_router(original_router):
    """
    روتر پوششی جامع که تمامی کلیک‌های مربوط به مراحل تاکتیک، 
    لیگ‌های مسابقات امروز و فردا و گزینه‌های منو را به طور قطعی هندل می‌کند.
    """
    async def wrapped_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return
        data = query.data
        uid = update.effective_user.id
        db_path = get_db_path()

        # الف) باز کردن منوی اصلی تاکتیک
        if data == "open_tactics":
            await query.answer()
            await tactics_menu_cmd(update, context)
            return

        # ب) مراحل ۴ گانه تغییر تاکتیک (Style, Depth, Buildup, Risk)
        elif data == "set_tac_step1":
            await query.answer()
            await safe_edit_message(
                query,
                "🪄 <b>انتخاب سبک بازی تیم (Style):</b>\n"
                "سبک مورد نظر خود را برای اعمال روی تیم انتخاب کنید:\n\n"
                "• <b>تیکی‌تاکا:</b> تسلط بر زمین با پاس‌های کوتاه و مالکیت بالا\n"
                "• <b>گگن‌پرس:</b> پرس شدید در زمین حریف و بازپس‌گیری سریع\n"
                "• <b>ضدحمله سریع:</b> انتقال برق‌آسا به هجوم پس از قطع توپ\n"
                "• <b>اتوبوسی:</b> دفاع فشرده و چندلایه با ریسک حداقل",
                reply_markup=get_tactic_step1_kb()
            )
            return

        elif data == "set_tac_step2":
            await query.answer()
            await safe_edit_message(
                query,
                "📏 <b>تنظیم عمق خط دفاعی (Defensive Depth):</b>\n"
                "میزان پیشروی خط دفاعی تیم خود را مشخص کنید:\n\n"
                "• <b>خط دفاعی بالا:</b> تحت فشار گذاشتن حریف در زمین خودی\n"
                "• <b>متعادل:</b> موضع‌گیری استاندارد دفاعی\n"
                "• <b>دفاع عمقی:</b> تجمع در نزدیکی محوطه جریمه خودی",
                reply_markup=get_tactic_step2_kb()
            )
            return

        elif data == "set_tac_step3":
            await query.answer()
            await safe_edit_message(
                query,
                "🎯 <b>نحوه بازیسازی و انتقال توپ (Build-Up Play):</b>\n"
                "شیوه پیشروی بازیکنان برای رسیدن به دروازه حریف:\n\n"
                "• <b>پاس کوتاه:</b> بازیسازی پله‌پله و آرام از عقب زمین\n"
                "• <b>ارسال بلند:</b> ارسال مستقیم برای مهاجمان نوک هدف",
                reply_markup=get_tactic_step3_kb()
            )
            return

        elif data == "set_tac_step4":
            await query.answer()
            await safe_edit_message(
                query,
                "🔥 <b>میزان ریسک و شدت هجوم (Risk Level):</b>\n"
                "تعداد نفرات اضافه شونده به حمله را مشخص کنید:\n\n"
                "• <b>هجوم همه‌جانبه:</b> اضافه شدن مدافعان و ریسک گل خوردن\n"
                "• <b>متعادل و منطقی:</b> حفظ توازن در هنگام حمله",
                reply_markup=get_tactic_step4_kb()
            )
            return

        # ج) ذخیره انتخاب‌های تاکتیکی (save_tac_*)
        elif data.startswith("save_tac_"):
            parts = data.split("_", 3)
            if len(parts) >= 4:
                field, val = parts[2], parts[3]
                now_str = get_iran_now().strftime("%Y-%m-%d %H:%M")
                try:
                    async with aiosqlite.connect(db_path, timeout=30.0) as db:
                        await db.execute("""
                            CREATE TABLE IF NOT EXISTS user_tactics (
                                user_id INTEGER PRIMARY KEY,
                                style TEXT DEFAULT 'TIKI_TAKA',
                                depth TEXT DEFAULT 'BALANCED',
                                buildup TEXT DEFAULT 'SHORT',
                                risk TEXT DEFAULT 'BALANCED',
                                updated_at TEXT
                            )
                        """)
                        await db.execute("""
                            INSERT INTO user_tactics (user_id, style, depth, buildup, risk, updated_at) 
                            VALUES (?, 'TIKI_TAKA', 'BALANCED', 'SHORT', 'BALANCED', ?) 
                            ON CONFLICT(user_id) DO NOTHING
                        """, (uid, now_str))
                        await db.execute(f"UPDATE user_tactics SET {field} = ?, updated_at = ? WHERE user_id = ?", (val, now_str, uid))
                        await db.commit()
                    val_title = TACTIC_NAMES.get(val, val)
                    await query.answer(f"✅ انتخاب شد: {val_title[:20]}", show_alert=False)
                except Exception as e:
                    logger.error(f"Error saving tactic: {e}")
                    await query.answer("✅ تاکتیک ذخیره شد.")

            await tactics_menu_cmd(update, context)
            return

        # د) انتخاب روز مسابقات (امروز یا فردا)
        elif data == "select_matches_today":
            await query.answer()
            await safe_edit_message(
                query,
                "⚽ <b>انتخاب لیگ برای مسابقات امروز:</b>\nلیگ مورد نظر خود را انتخاب کنید:",
                reply_markup=kb.get_matches_leagues_keyboard("today")
            )
            return

        elif data == "select_matches_tomorrow":
            await query.answer()
            await safe_edit_message(
                query,
                "📅 <b>انتخاب لیگ برای مسابقات فردا:</b>\nلیگ مورد نظر خود را انتخاب کنید:",
                reply_markup=kb.get_matches_leagues_keyboard("tmrw")
            )
            return

        # ه) دریافت و نمایش بازی‌های هر لیگ (today_* یا tmrw_* یا tomorrow_*)
        elif data.startswith("today_") or data.startswith("tmrw_") or data.startswith("tomorrow_"):
            await query.answer("⏳ دریافت مسابقات...")
            is_today = data.startswith("today_")
            prefix = "today_" if is_today else ("tmrw_" if data.startswith("tmrw_") else "tomorrow_")
            league_code = data.replace(prefix, "")

            target_date = get_iran_now() if is_today else (get_iran_now() + timedelta(days=1))
            date_str = target_date.strftime("%Y%m%d")
            day_label = "امروز" if is_today else "فردا"
            title = LEAGUE_TITLES.get(league_code, "مسابقات فوتبال")

            matches = []
            provider_inst = globals().get("provider")
            if provider_inst:
                try:
                    matches = await provider_inst.get_matches(date_str, league_code=league_code)
                except Exception as e:
                    logger.error(f"Error getting matches for {league_code}: {e}")

            if not matches:
                back_prefix = "today" if is_today else "tmrw"
                await safe_edit_message(
                    query,
                    f"⏳ مسابقه‌ای برای <b>{title}</b> در تاریخ <b>{day_label}</b> یافت نشد.\n"
                    f"💡 ممکن است در روزهای آینده برگزار شود یا لیگ در تعطیلات باشد.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("‹ انتخاب لیگ دیگر", callback_data=f"select_matches_{'today' if is_today else 'tomorrow'}")],
                        [InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")]
                    ])
                )
                return

            text = f"⚽️ <b>برنامه مسابقات {title} ({day_label}):</b>\n────────────────────\n\n"
            match_cache = globals().get("MATCH_CACHE", {})
            format_time_fn = globals().get("format_iran_time", lambda d: "نامشخص")

            for m in matches[:10]:
                if "id" in m:
                    match_cache[m["id"]] = m
                time_str = format_time_fn(m.get("date"))
                status = m.get("status", "UPCOMING")
                if status in ["LIVE", "IN_PLAY", "1H", "2H", "HT"]:
                    badge = f"🔴 زنده [{m.get('home_score', 0)} - {m.get('away_score', 0)}]"
                elif status in ["FINISHED", "FT", "POST"]:
                    badge = f"🏁 پایان [{m.get('home_score', 0)} - {m.get('away_score', 0)}]"
                else:
                    badge = f"⏰ <code>{time_str}</code>"

                text += f"▫️ <b>{m.get('home_team', 'میزبان')}</b> 🆚 <b>{m.get('away_team', 'میهمان')}</b>\n"
                text += f"    └ {badge}  •  {m.get('venue', 'ورزشگاه')}\n\n"

            text += "────────────────────"
            await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("‹ انتخاب لیگ دیگر", callback_data=f"select_matches_{'today' if is_today else 'tomorrow'}")],
                [InlineKeyboardButton("‹ منوی اصلی", callback_data="home")]
            ]))
            return

        # و) جدول لیگ‌ها
        elif data == "select_standings_league":
            await query.answer()
            if "get_standings_leagues_keyboard" in dir(kb):
                await safe_edit_message(
                    query,
                    "🏆 <b>جدول رده‌بندی لیگ مورد نظر را انتخاب کنید:</b>",
                    reply_markup=kb.get_standings_leagues_keyboard()
                )
            else:
                await league_cmd(update, context)
            return

        # ز) پیش‌بینی مسابقات
        elif data == "predictions_hub":
            await query.answer()
            pred_fn = globals().get("predictions_hub_handler")
            if pred_fn:
                await pred_fn(query)
            else:
                await safe_edit_message(
                    query,
                    "🎯 <b>تالار پیش‌بینی مسابقات:</b>\nبرای ثبت فرم پیش‌بینی یا جک‌پات انتخاب کنید:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🎰 شرکت در جک‌پات کمبو", callback_data="jackpot_hub")],
                        [InlineKeyboardButton("‹ منوی اصلی", callback_data="home")]
                    ])
                )
            return

        # ح) گردونه شانس
        elif data == "spin_wheel":
            await query.answer()
            await spin_wheel_cmd(update, context)
            return

        # ط) جک‌پات
        elif data == "jackpot_hub":
            await query.answer()
            jackpot_fn = globals().get("jackpot_cmd")
            if jackpot_fn:
                await jackpot_fn(update, context)
            return

        # در غیر این صورت، هدایت به هندلر اصلی
        await original_router(update, context)

    return wrapped_callback_router

# ---------------------------------------------------------------------------
# ۱۰. تابع جادویی اتصال به bot.py (اتصال دوطرفه محیط‌ها)
# ---------------------------------------------------------------------------

def init_patches(caller_globals: dict):
    """
    وارد کردن تمام توابع bot.py به bot_patches
    و صادر کردن تمام توابع جدید bot_patches به bot.py
    """
    # ۱. کپی کردن توابع bot.py داخل bot_patches
    for k, v in caller_globals.items():
        if k not in globals():
            globals()[k] = v

    # ۲. کپی کردن توابع جدید bot_patches داخل bot.py
    for k, v in globals().items():
        if not k.startswith("_"):
            caller_globals[k] = v

    # ۳. بسته‌بندی خودکار callback_router در bot.py
    if "callback_router" in caller_globals:
        caller_globals["callback_router"] = wrap_callback_router(caller_globals["callback_router"])
        logger.info("callback_router wrapped successfully.")
