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
LRM = "\u200E"

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

def get_user_tier(points: int) -> tuple[str, str]:
    if points >= 1500:
        return "🐐", "G.O.A.T"
    elif points >= 1100:
        return "👑", "Ballon d'Or"
    elif points >= 800:
        return "💎", "Legend"
    elif points >= 550:
        return "🔮", "World Class"
    elif points >= 350:
        return "🎖", "Captain"
    elif points >= 200:
        return "🌟", "First Team"
    elif points >= 100:
        return "⚡️", "Semi-Pro"
    else:
        return "🔰", "Academy"

def format_bidi_name(name: str, max_len: int = 15) -> str:
    safe_name = html.escape(str(name).strip())
    if len(safe_name) > max_len:
        safe_name = safe_name[:max_len] + "…"
    return f"{LRM}{safe_name}{LRM}"

def get_rank_badge(rank: int, is_ai: bool = False) -> str:
    if is_ai:
        return "🤖"
    if rank == 1:
        return "🥇 👑"
    elif rank == 2:
        return "🥈 👑"
    elif rank == 3:
        return "🥉 👑"
    
    rank_badges = {
        4: "🌟",
        5: "🌟",
        6: "🔥",
        7: "💎",
        8: "🦁",
        9: "⚡️",
        10: "🎯",
        11: "⚔️",
        12: "⚽️",
        13: "🚀",
        14: "💫",
        15: "✨"
    }
    return rank_badges.get(rank, "🔹")

class SimpleHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Football Hub Online! 200 OK")

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

RAW_GUESS_PLAYERS = [
    {"nation": "آرژانتین 🇦🇷", "pos": "مهاجم کاذب / وینگر راست", "career": ["نیوولز اولد بویز 🇦🇷", "بارسلونا 🇪🇸", "پاری‌سن‌ژرمن 🇫🇷", "اینتر میامی 🇺🇸"], "clue": "ثبت ۹۱ گل رسمی در یک سال تقویمی (۲۰۱۲) و برنده ۸ توپ طلا", "names": ["مسی", "لیونل مسی", "messi"]},
    {"nation": "پرتغال 🇵🇹", "pos": "وینگر چپ / مهاجم هدف", "career": ["اسپورتینگ لیسبون 🇵🇹", "منچستریونایتد 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "رئال مادرید 🇪🇸", "یوونتوس 🇮🇹", "النصر 🇸🇦"], "clue": "تنها بازیکن با بیش از ۹۰۰ گل رسمی، ۵ قهرمانی UCL و فریاد شادی Siuuu", "names": ["رونالدو", "کریستیانو رونالدو", "کریس رونالدو", "ronaldo", "cr7"]},
    {"nation": "نروژ 🇳🇴", "pos": "مهاجم نوک فیزیکی", "career": ["برنه 🇳🇴", "مولده 🇳🇴", "ردبول سالزبورگ 🇦🇹", "دورتموند 🇩🇪", "منچسترسیتی 🏴󠁧󠁢󠁥󠁮󠁧󠁿"], "clue": "ثبت ۳۶ گل در اولین فصل لیگ جزیره و ماشین گلزنی پپ گواردیولا", "names": ["هالند", "ارلینگ هالند", "haaland"]},
    {"nation": "اسپانیا 🇪🇸", "pos": "وینگر معکوس پای چپ", "career": ["لاماسیا 🇪🇸", "بارسلونا 🇪🇸"], "clue": "جوان‌ترین گلزن تاریخ یورو با سوپرگل کات‌دار به فرانسه در ۱۶ سالگی", "names": ["یامال", "لامین یامال", "yamal"]},
    {"nation": "فرانسه 🇫🇷", "pos": "مهاجم سرعتی / وینگر", "career": ["موناکو 🇫🇷", "پاری‌سن‌ژرمن 🇫🇷", "رئال مادرید 🇪🇸"], "clue": "هت‌تریک در فینال جام جهانی ۲۰۲۲ و آقای گل تاریخ پاری‌سن‌ژرمن", "names": ["امباپه", "کیلیان امباپه", "mbappe"]},
    {"nation": "انگلیس 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "pos": "هافبک باکس‌تو‌باکس نفوذی", "career": ["بیرمنگام 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "دورتموند 🇩🇪", "رئال مادرید 🇪🇸"], "clue": "بایگانی شدن شماره ۲۲ در نوجوانی و برنده جایزه کوپا و گلدن بوی ۲۰۲۳", "names": ["بلینگام", "جود بلینگام", "bellingham"]},
    {"nation": "مصر 🇪🇬", "pos": "وینگر راست نفوذی", "career": ["المقاولون 🇪🇬", "بازل 🇨🇭", "چلسی 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "فیورنتینا 🇮🇹", "رم 🇮🇹", "لیورپول 🏴󠁧󠁢󠁥󠁮󠁧󠁿"], "clue": "بهترین گلزن آفریقایی تاریخ لیگ جزیره با ۳ کفش طلای انگلیس", "names": ["صلاح", "محمد صلاح", "salah"]},
    {"nation": "برزیل 🇧🇷", "pos": "وینگر چپ تکنیکی", "career": ["فلامینگو 🇧🇷", "رئال مادرید 🇪🇸"], "clue": "زدن گل پیروزی در دو فینال لیگ قهرمانان ۲۰۲۲ و ۲۰۲۴ مقابل لیورپول و دورتموند", "names": ["وینیسیوس", "وینی", "vinicius", "vini"]},
    {"nation": "لهستان 🇵🇱", "pos": "مهاجم هدف تمام‌کننده", "career": ["لخ پوزنان 🇵🇱", "دورتموند 🇩🇪", "بایرن مونیخ 🇩🇪", "بارسلونا 🇪🇸"], "clue": "زدن ۵ گل در ۹ دقیقه مقابل وولفسبورگ پس از ورود به زمین", "names": ["لواندوفسکی", "لوا", "lewandowski"]},
    {"nation": "کرواسی 🇭🇷", "pos": "پلی‌میکر مرکزی با پاس بیرون پا", "career": ["دینامو زاگرب 🇭🇷", "تاتنهام 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "رئال مادرید 🇪🇸"], "clue": "پایان‌دهنده سلطه مسی و رونالدو بر توپ طلا با دریافت جایزه سال ۲۰۱۸", "names": ["مودریچ", "لوکا مودریچ", "modric"]},
    {"nation": "بلژیک 🇧🇪", "pos": "هافبک میانی طراح خط کشی", "career": ["خنک 🇧🇪", "چلسی 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "ولفسبورگ 🇩🇪", "منچسترسیتی 🏴󠁧󠁢󠁥󠁮󠁧󠁿"], "clue": "رکورددار ۲۰ پاس گل در یک فصل لیگ جزیره و معمار سه‌گانه سیتیزن‌ها", "names": ["دی بروینه", "کوین دی بروینه", "دیبروینه", "de bruyne"]},
    {"nation": "فرانسه 🇫🇷", "pos": "هافبک هجومی / شماره ۱۰ فانتزی", "career": ["کن 🇫🇷", "بوردو 🇫🇷", "یوونتوس 🇮🇹", "رئال مادرید 🇪🇸"], "clue": "والیه پای چپ افسانه‌ای گلاسکو ۲۰۰۲ و دو گل با سر در فینال جام جهانی ۹۸", "names": ["زیدان", "زین الدین زیدان", "zidane"]},
    {"nation": "برزیل 🇧🇷", "pos": "مهاجم نوک زهرآگین", "career": ["کروزیرو 🇧🇷", "پی‌اس‌وی 🇳🇱", "بارسلونا 🇪🇸", "اینتر میلان 🇮🇹", "رئال مادرید 🇪🇸", "میلان 🇮🇹"], "clue": "ال فنومنو؛ زدن دو گل در فینال ۲۰۰۲ پس از دو سال مصدومیت شدید رباط", "names": ["رونالدو برزیلی", "رونالدو نازاریو", "نازاریو", "r9"]},
    {"nation": "فرانسه 🇫🇷", "pos": "وینگر چپ / مهاجم", "career": ["موناکو 🇫🇷", "یوونتوس 🇮🇹", "آرسنال 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "بارسلونا 🇪🇸", "نیویورک ردبولز 🇺🇸"], "clue": "بهترین گلزن تاریخ توپچی‌های لندن با مجسمه اختصاصی بیرون ورزشگاه امارات", "names": ["آنری", "تیری آنری", "هنری", "تیری هنری", "henry"]},
    {"nation": "هلند 🇳🇱", "pos": "مهاجم سایه تکنیکی", "career": ["آژاکس 🇳🇱", "اینتر 🇮🇹", "آرسنال 🏴󠁧󠁢󠁥󠁮󠁧󠁿"], "clue": "ملقب به هلندی غیرپروازی به خاطر فوبیای هواپیما و صاحب زیباترین استپ‌های تاریخ", "names": ["برکمپ", "دنیس برکمپ", "bergkamp"]},
    {"nation": "سوئد 🇸🇪", "pos": "مهاجم آکروباتیک تنومند", "career": ["مالمو 🇸🇪", "آژاکس 🇳🇱", "یوونتوس 🇮🇹", "اینتر 🇮🇹", "بارسلونا 🇪🇸", "میلان 🇮🇹", "پی‌اس‌جی 🇫🇷", "منچستریونایتد 🏴󠁧󠁢󠁥󠁮󠁧󠁿"], "clue": "کمربند مشکی تکواندو و سوپرگل برگردان از فاصله ۳۲ متری به انگلیس", "names": ["زلاتان", "ابراهیموویچ", "زلاتان ابراهیموویچ", "ibrahimovic"]},
    {"nation": "آلمان 🇩🇪", "pos": "سوئیپر کیپر مدرن", "career": ["شالکه ۰۴ 🇩🇪", "بایرن مونیخ 🇩🇪"], "clue": "انقلاب در شیوه بازی سنگربان‌ها با خروج از محوطه و نامزد توپ طلای ۲۰۱۴", "names": ["نویر", "مانوئل نویر", "neuer"]},
    {"nation": "ایتالیا 🇮🇹", "pos": "رجیستا (طراح عقب‌زمین)", "career": ["برشا 🇮🇹", "اینتر 🇮🇹", "میلان 🇮🇹", "یوونتوس 🇮🇹", "نیویورک سیتی 🇺🇸"], "clue": "معروف به موزارت و مهندس با پاس‌های قوسی و ایستگاهی‌های کات‌دار", "names": ["پیرلو", "آندریا پیرلو", "pirlo"]},
    {"nation": "اروگوئه 🇺🇾", "pos": "مهاجم فرصت‌طلب درگیر", "career": ["ناسیونال 🇺🇾", "خرونینگن 🇳🇱", "آژاکس 🇳🇱", "لیورپول 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "بارسلونا 🇪🇸", "اتلتیکو مادرید 🇪🇸"], "clue": "کفش طلای اروپا بدون حتی یک گل از روی نقطه پنالتی و اخراج مقابل غنا ۲۰۱۰", "names": ["سوارز", "لوییس سوارز", "لویز سوارز", "suarez"]},
    {"nation": "ساحل عاج 🇨🇮", "pos": "مهاجم قدرتی سرزن", "career": ["مارسی 🇫🇷", "چلسی 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "گالاتاسرای 🇹🇷", "مونترال 🇨🇦"], "clue": "متوقف‌کننده جنگ داخلی کشورش و زننده پنالتی قهرمانی فینال مونیخ ۲۰۱۲", "names": ["دروگبا", "دیدیه دروگبا", "drogba"]},
    {"nation": "آلمان 🇩🇪", "pos": "فضاشناس (رائوم‌دویتر)", "career": ["بایرن مونیخ 🇩🇪"], "clue": "بیش از ۷۰۰ بازی برای باواریایی‌ها و زدن ۵ گل در جام جهانی ۲۰۱۰ در جوانی", "names": ["مولر", "توماس مولر", "muller"]},
    {"nation": "ولز 🏴󠁧󠁢󠁷󠁬󠁳󠁿", "pos": "وینگر سرعتی شوت‌زن", "career": ["ساوتهمپتون 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "تاتنهام 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "رئال مادرید 🇪🇸", "لس‌آنجلس اف‌سی 🇺🇸"], "clue": "سوپرگل قیچی برگردان فینال کیف ۲۰۱۸ و کورس ویرانگر کوپا دل ری با بارترا", "names": ["بیل", "گرت بیل", "bale"]},
    {"nation": "کامرون 🇨🇲", "pos": "مهاجم زهرآگین", "career": ["مایورکا 🇪🇸", "بارسلونا 🇪🇸", "اینتر 🇮🇹", "آنژی 🇷🇺", "چلسی 🏴󠁧󠁢󠁥󠁮󠁧󠁿"], "clue": "تنها بازیکنی که در دو سال متوالی با دو تیم مختلف فاتح سه‌گانه اروپا شد", "names": ["اتوئو", "ساموئل اتوئو", "etoo"]},
    {"nation": "اسپانیا 🇪🇸", "pos": "مدافع میانی گلزن", "career": ["سویا 🇪🇸", "رئال مادرید 🇪🇸", "پاری‌سن‌ژرمن 🇫🇷"], "clue": "زننده سرنوشت‌سازترین ضربه سر تاریخ در دقیقه ۹۲:۴۸ فینال لیسبون", "names": ["راموس", "سرخیو راموس", "ramos"]},
    {"nation": "کلمبیا 🇨🇴", "pos": "هافبک هجومی شوت‌زن", "career": ["پورتو 🇵🇹", "موناکو 🇫🇷", "رئال مادرید 🇪🇸", "بایرن مونیخ 🇩🇪", "اورتون 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "رایو وایکانو 🇪🇸"], "clue": "کفش طلای جام جهانی ۲۰۱۴ و گل برتر سال با استپ سینه و والی سرضرب", "names": ["خامس", "خامس رودریگز", "جیمز رودریگز", "james"]},
    {"nation": "هلند 🇳🇱", "pos": "وینگر تکنیکی پای چپ", "career": ["پی‌اس‌وی 🇳🇱", "چلسی 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "رئال مادرید 🇪🇸", "بایرن مونیخ 🇩🇪"], "clue": "تخصص همیشگی در کات‌این به داخل محوطه و شوت به زاویه مخالف ملقب به شیشه‌ای", "names": ["روبن", "آرین روبن", "robben"]},
    {"nation": "انگلیس 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "pos": "مهاجم کامل بازیساز", "career": ["تاتنهام 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "میلوال 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "بایرن مونیخ 🇩🇪"], "clue": "آقای گل تاریخ تاتنهام و کاپیتان انگلستان در حسرت جام تیمی تا سن ۳۰ سالگی", "names": ["کین", "هری کین", "kane"]},
    {"nation": "اسپانیا 🇪🇸", "pos": "هافبک طراح تکنیکی", "career": ["بارسلونا 🇪🇸", "ویسل کوبه 🇯🇵", "الامارات 🇦🇪"], "clue": "زننده گل قهرمانی اسپانیا در فینال جام جهانی ۲۰۱۰ در وقت‌های اضافه", "names": ["اینیستا", "آندرس اینیستا", "iniesta"]},
    {"nation": "فرانسه 🇫🇷", "pos": "هافبک دفاعی بازیاب", "career": ["کان 🇫🇷", "لسترسیتی 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "چلسی 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "الاتحاد 🇸🇦"], "clue": "موتور محرک معجزه قهرمانی لسترسیتی در سال ۲۰۱۶ با ریه‌های بی‌پایان", "names": ["کانته", "انگولو کانته", "kante"]},
    {"nation": "نیجریه 🇳🇬", "pos": "مهاجم نوک ماسک‌دار", "career": ["شارلوا 🇧🇪", "لیل 🇫🇷", "ناپولی 🇮🇹", "گالاتاسرای 🇹🇷"], "clue": "آقای گل و قهرمان سری آ با ناپولی پس از ۳۳ سال با ماسک محافظ مشکی", "names": ["اوسیمهن", "ویکتور اوسیمهن", "osimhen"]},
    {"nation": "آلمان 🇩🇪", "pos": "مترونوم خط میانی", "career": ["بایر لورکوزن 🇩🇪", "بایرن مونیخ 🇩🇪", "رئال مادرید 🇪🇸"], "clue": "خداحافظی در اوج با فتح ششمین لیگ قهرمانان و دقت پاس ۹۵ درصدی", "names": ["کروس", "تونی کروس", "kroos"]},
    {"nation": "پرتغال 🇵🇹", "pos": "وینگر فانتزی نمایشی", "career": ["اسپورتینگ 🇵🇹", "بارسلونا 🇪🇸", "پورتو 🇵🇹", "اینتر 🇮🇹", "بشیکتاش 🇹🇷"], "clue": "استاد شوت‌ها و سانترهای بیرون پای تریولا (Trivela) و حرکات رابونا", "names": ["کوارشما", "ریکاردو کوارشما", "quaresma"]},
    {"nation": "گرجستان 🇬🇪", "pos": "وینگر کلاسیک دریبل‌زن", "career": ["دینامو باتومی 🇬🇪", "روبین کازان 🇷🇺", "ناپولی 🇮🇹"], "clue": "ملقب به کوارادونا با تکنیک سنتی ناب در کسب اسکودتوی ۲۰۲۳ ناپولی", "names": ["کواراتسخلیا", "خویچا", "خویچا کواراتسخلیا", "kvaratskhelia"]},
    {"nation": "ایران 🇮🇷", "pos": "مهاجم باهوش چارچوب‌شناس", "career": ["شاهین بوشهر 🇮🇷", "پرسپولیس 🇮🇷", "الغرافیه 🇶🇦", "ریو آوه 🇵🇹", "پورتو 🇵🇹", "اینتر میلان 🇮🇹"], "clue": "سوپرگل قیچی برگردان برتر سال یوفا به چلسی و آقای گل لیگ پرتغال", "names": ["طارمی", "مهدی طارمی", "taremi"]},
    {"nation": "غنا 🇬🇭", "pos": "هافبک فیزیکی شوت‌زن", "career": ["باستیا 🇫🇷", "لیون 🇫🇷", "چلسی 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "رئال مادرید 🇪🇸", "میلان 🇮🇹"], "clue": "ملقب به قطار بوفالو با شوت وحشتناک پای چپ از ۳۵ متری به بارسلونا در ۲۰۰۹", "names": ["اسین", "مایکل اسین", "essien"]}
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
    except BadRequest as e:
        logger.warning(f"Bad request in safe_edit_message: {e}")
    except Exception as e:
        logger.warning(f"Unexpected edit warning: {e}")

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

# شمارنده پنالتی (۳ بار در روز)
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

# شمارنده حدس بازیکن (۳ بار در روز)
async def get_guess_count_db(user_id: int) -> int:
    today_str = get_iran_now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT last_guess_date, guess_count FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                return row[1] or 0
    return 0

async def increment_guess_count_db(user_id: int):
    today_str = get_iran_now().strftime("%Y-%m-%d")
    cur_count = await get_guess_count_db(user_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE users SET last_guess_date = ?, guess_count = ? WHERE user_id = ?
        """, (today_str, cur_count + 1, user_id))
        await db.commit()

async def reset_points_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID):
        await update.message.reply_text("⛔️ دسترسی غیرمجاز!")
        return
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE users SET points = 100")
            await db.commit()
        await update.message.reply_text("✅ <b>امتیاز تمامی کاربران با موفقیت روی ۱۰۰ ریست شد!</b>\nافتخارات و مدال‌های سیزن حفظ شدند.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error resetting points: {e}")

async def set_live_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in ["group", "supergroup"]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('live_chat_id', ?)", (str(chat.id),))
            await db.commit()
        await update.message.reply_text(
            f"✅ <b>این گروه به عنوان گروه اختصاصی مسابقات و گزارش زنده ثبت شد!</b> 🏟🔥\n"
            f"شناسه اختصاصی: <code>{chat.id}</code>\n"
            "رویدادها و گزارش بازی‌های مهم در همین گروه ارسال خواهد شد.",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("⚠️ این دستور باید در گروه ارسال شود.")

async def generate_pool_message_text(match_data, pool_participants=None):
    h_name = match_data.get("home_team", "")
    a_name = match_data.get("away_team", "")
    time_str = format_iran_time(match_data.get("date"))

    text = (
        f"🚨🔥 <b>۱۵ دقیقه تا نبرد حساس! استخر ۳۰۰ امتیازی ویژه</b> 🏆\n"
        "────────────────────\n"
        f"⚽️ <b>{h_name}</b> 🆚 <b>{a_name}</b>\n"
        f"⏰ ساعت شروع: <code>{time_str}</code> (به وقت تهران)\n"
        "💰 <b>جایزه کل: ۳۰۰ امتیاز</b> 🪙\n"
        "⚡️ جایزه بین افرادی که نتیجه را درست حدس بزنند تقسیم می‌شود!\n"
        "────────────────────\n"
    )

    if pool_participants:
        text += f"👥 <b>شرکت‌کنندگان ({len(pool_participants)} نفر):</b>\n"
        for uname, choice in pool_participants:
            choice_label = f"برد {h_name[:10]}" if choice == "HOME" else ("مساوی" if choice == "DRAW" else f"برد {a_name[:10]}")
            text += f"▫️ <b>{html.escape(uname)}</b>: <i>{choice_label}</i>\n"
    else:
        text += "▫️ هنوز پیش‌بینی‌ای ثبت نشده است!\n"

    text += "\n👇 <b>پیش‌بینی خود را انتخاب کنید:</b>"
    return text

async def monitor_real_barca_live_job(context: ContextTypes.DEFAULT_TYPE):
    target_chat_id = await get_live_chat_id()
    if not target_chat_id:
        return

    iran_now = get_iran_now()
    dates = [
        (iran_now - timedelta(days=1)).strftime("%Y%m%d"),
        iran_now.strftime("%Y%m%d"),
        (iran_now + timedelta(days=1)).strftime("%Y%m%d")
    ]

    matches = []
    for d in dates:
        for l_code in ["esp.1", "uefa.champions"]:
            try:
                m_list = await provider.get_matches(d, league_code=l_code)
                matches.extend(m_list)
            except Exception:
                pass

    unique_matches = {m["id"]: m for m in matches}
    utc_now = datetime.now(timezone.utc)

    for m_id, m in unique_matches.items():
        h_name = str(m.get("home_team", ""))
        a_name = str(m.get("away_team", ""))
        combined = (h_name + " " + a_name).lower()

        if not any(x in combined for x in ["barcelona", "barca", "بارسلونا", "real madrid", "madrid", "رئال"]):
            continue

        MATCH_CACHE[m_id] = m
        raw_status = str(m.get("status", "UPCOMING")).upper()

        try:
            h_score = int(m.get("home_score")) if m.get("home_score") is not None else None
            a_score = int(m.get("away_score")) if m.get("away_score") is not None else None
        except Exception:
            h_score, a_score = None, None

        track = TRACKED_LIVE_MATCHES.get(m_id)
        if not track:
            track = {
                "last_status": raw_status,
                "home_score": h_score if h_score is not None else 0,
                "away_score": a_score if a_score is not None else 0,
                "started_announced": False,
                "ht_announced": False,
                "second_half_announced": False,
                "pool_opened": False,
                "pool_msg_id": None
            }
            TRACKED_LIVE_MATCHES[m_id] = track

        match_date_str = m.get("date")
        minutes_to_start = 9999
        if match_date_str:
            try:
                dt_match = datetime.fromisoformat(match_date_str.replace("Z", "+00:00"))
                diff_sec = (dt_match - utc_now).total_seconds()
                minutes_to_start = int(diff_sec // 60)
            except Exception:
                pass

        if raw_status in ["UPCOMING", "PRE"] and not track["pool_opened"] and (0 <= minutes_to_start <= 25):
            track["pool_opened"] = True
            pool_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"⚪️ برد {h_name[:10]}", callback_data=f"pool_{m_id}_HOME"),
                    InlineKeyboardButton("🤝 مساوی", callback_data=f"pool_{m_id}_DRAW"),
                    InlineKeyboardButton(f"🔴 برد {a_name[:10]}", callback_data=f"pool_{m_id}_AWAY")
                ]
            ])
            pool_text = await generate_pool_message_text(m, [])
            try:
                sent = await context.bot.send_message(chat_id=target_chat_id, text=pool_text, reply_markup=pool_kb, parse_mode="HTML")
                track["pool_msg_id"] = sent.message_id
            except Exception:
                pass

        is_finished = raw_status in ["FINISHED", "FT", "POST"]
        is_in_play = (raw_status in ["LIVE", "IN_PLAY", "1H", "2H", "HT", "HALFTIME"]) or (h_score is not None and not is_finished)

        if is_in_play and not track["started_announced"]:
            track["started_announced"] = True
            track["last_status"] = "LIVE"
            if track.get("pool_msg_id"):
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=target_chat_id,
                        message_id=track["pool_msg_id"],
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔒 مهلت پیش‌بینی به پایان رسید", callback_data="none")]])
                    )
                except Exception:
                    pass

            start_msg = (
                f"📢 <b>سوت آغاز مسابقه به صدا درآمد!</b>\n"
                "────────────────────\n"
                f"⚪️ <b>{h_name}</b> 🆚 <b>{a_name}</b> 🔴\n\n"
                f"🎙 گزارش زنده رویدادها و گل‌ها آغاز شد."
            )
            await context.bot.send_message(chat_id=target_chat_id, text=start_msg, parse_mode="HTML")

        if is_in_play and h_score is not None and a_score is not None:
            if h_score > track["home_score"]:
                track["home_score"] = h_score
                goal_msg = (
                    f"⚽️🔥 <b>گـُـل برای {h_name}!</b>\n"
                    "────────────────────\n"
                    f"📊 نتیجه لحظه‌ای:\n"
                    f"⚪️ <b>{h_name}</b> [{h_score}] - [{a_score}] <b>{a_name}</b> 🔴"
                )
                await context.bot.send_message(chat_id=target_chat_id, text=goal_msg, parse_mode="HTML")

            elif a_score > track["away_score"]:
                track["away_score"] = a_score
                goal_msg = (
                    f"⚽️🔥 <b>گـُـل برای {a_name}!</b>\n"
                    "────────────────────\n"
                    f"📊 نتیجه لحظه‌ای:\n"
                    f"⚪️ <b>{h_name}</b> [{h_score}] - [{a_score}] <b>{a_name}</b> 🔴"
                )
                await context.bot.send_message(chat_id=target_chat_id, text=goal_msg, parse_mode="HTML")

        if raw_status in ["HT", "HALFTIME"] and not track["ht_announced"]:
            track["ht_announced"] = True
            cur_h = h_score if h_score is not None else track["home_score"]
            cur_a = a_score if a_score is not None else track["away_score"]
            ht_msg = (
                f"⏸ <b>پایان نیمه اول مسابقه (HT)</b>\n"
                "────────────────────\n"
                f"⚪️ <b>{h_name}</b> [{cur_h}] - [{cur_a}] <b>{a_name}</b> 🔴"
            )
            await context.bot.send_message(chat_id=target_chat_id, text=ht_msg, parse_mode="HTML")

        if raw_status in ["2H", "LIVE"] and track["ht_announced"] and not track["second_half_announced"]:
            track["second_half_announced"] = True
            sh_msg = (
                f"▶️ <b>شروع نیمه دوم مسابقه</b>\n"
                "────────────────────\n"
                f"⚪️ <b>{h_name}</b> 🆚 <b>{a_name}</b> 🔴"
            )
            await context.bot.send_message(chat_id=target_chat_id, text=sh_msg, parse_mode="HTML")

        if is_finished and track["last_status"] != "FINISHED":
            track["last_status"] = "FINISHED"
            final_h = h_score if h_score is not None else track["home_score"]
            final_a = a_score if a_score is not None else track["away_score"]
            actual_outcome = "HOME" if final_h > final_a else ("AWAY" if final_a > final_h else "DRAW")

            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute("SELECT user_id, user_name FROM special_pool_predictions WHERE match_id = ? AND choice = ?", (m_id, actual_outcome)) as cur:
                    winners = await cur.fetchall()

                winners_text = ""
                if winners:
                    share = 300 // len(winners)
                    winners_text = f"\n\n🎁 <b>برندگان استخر ۳۰۰ امتیازی (هر نفر +{share} PTS):</b>\n"
                    for w_id, w_name in winners:
                        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (share, w_id))
                        winners_text += f"▫️ <b>{html.escape(w_name)}</b>\n"
                else:
                    winners_text = "\n\n▫️ هیچ کاربری برنده نهایی را درست حدس نزد!"

                await db.execute("UPDATE special_pool_predictions SET settled = 1 WHERE match_id = ?", (m_id,))
                await db.commit()

            ft_msg = (
                f"🏁 <b>سوت پایان مسابقه (FT)</b>\n"
                "────────────────────\n"
                f"نتیجه نهایی: <b>{h_name} [{final_h}] - [{final_a}] {a_name}</b>{winners_text}"
            )
            await context.bot.send_message(chat_id=target_chat_id, text=ft_msg, parse_mode="HTML")

async def check_and_settle_monthly_season(context: ContextTypes.DEFAULT_TYPE):
    iran_now = get_iran_now()
    cur_month_str = iran_now.strftime("%Y-%m")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = 'last_settled_month'") as cur:
            row = await cur.fetchone()
            last_settled = row[0] if row else None

        if not last_settled:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('last_settled_month', ?)", (cur_month_str,))
            await db.commit()
            return

        if cur_month_str != last_settled:
            logger.info(f"Settling season for previous month: {last_settled}")
            async with db.execute("SELECT user_id, first_name, points FROM users WHERE user_id != ? ORDER BY points DESC LIMIT 3", (ESCOBAR_AI_ID,)) as cur:
                top3 = await cur.fetchall()

            if top3 and len(top3) >= 3:
                p1, p2, p3 = top3[0], top3[1], top3[2]
                await db.execute("UPDATE users SET season_gold = season_gold + 1 WHERE user_id = ?", (p1[0],))
                await db.execute("UPDATE users SET season_silver = season_silver + 1 WHERE user_id = ?", (p2[0],))
                await db.execute("UPDATE users SET season_bronze = season_bronze + 1 WHERE user_id = ?", (p3[0],))

                target_chat_id = await get_live_chat_id()
                if target_chat_id:
                    msg = (
                        f"🏆🔥 <b>پایان رسمی رقابت‌های این سیزن!</b> 🏁\n"
                        "────────────────────\n"
                        "👑 <b>تالار قهرمانان و برندگان مدال ماه:</b>\n\n"
                        f"🥇 قهرمان سیزن: <b>{html.escape(p1[1])}</b> (مدال طلا 🥇)\n"
                        f"🥈 نایب قهرمان: <b>{html.escape(p2[1])}</b> (مدال نقره 🥈)\n"
                        f"🥉 مقام سوم: <b>{html.escape(p3[1])}</b> (مدال برنز 🥉)\n\n"
                        "⚡️ مدال‌های افتخار در پروفایل این ۳ ستاره ثبت گردید.\n"
                        "🔄 <b>امتیازات برای سیزن جدید همگی روی ۱۰۰ ریست شدند!</b>\n"
                        "رقابت برای قهرمانی سیزن جدید آغاز شد! 🔥"
                    )
                    try:
                        await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")
                    except Exception as e:
                        logger.error(f"Error sending season announcement: {e}")

                await db.execute("UPDATE users SET points = 100")
                await db.execute("UPDATE bot_settings SET value = ? WHERE key = 'last_settled_month'", (cur_month_str,))
                await db.commit()

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
            await db.commit()
    except Exception as e:
        logger.error(f"Error in record_ai_prediction: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT points FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            pts = row[0] if row else 100

    icon, tier = get_user_tier(pts)
    safe_name = html.escape(user.first_name)

    text = (
        f"⚽️ <b>FOOTBALL HUB</b>\n"
        f"────────────────────\n"
        f"👤 بازیکن: <b>{safe_name}</b>\n"
        f"⚡️ موجودی: <code>{pts} PTS</code>  ▫️  سطح: {icon} <b>{tier}</b>\n"
        f"────────────────────\n"
        f"جهت دسترسی به بخش‌های ربات از منوی زیر استفاده کنید:"
    )

    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb.get_main_menu())
    else:
        await update.message.reply_text(text, reply_markup=kb.get_main_menu(), parse_mode="HTML")

async def show_leaderboard_text() -> str:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT user_id, first_name, points, duel_wins FROM users ORDER BY points DESC, duel_wins DESC"
        ) as cur:
            all_users = await cur.fetchall()

    text = "🏆 <b>جدول رده‌بندی سیزن</b> 🔥\n"
    text += "────────────────────\n\n"

    if not all_users:
        text += "هنوز کاربری ثبت نشده است.\n"
        text += "────────────────────"
        return text

    top_list = all_users[:15]
    remaining_list = all_users[15:]

    for idx, u in enumerate(top_list, 1):
        u_id, name, pts, wins = u[0], u[1], max(0, u[2]), u[3]
        is_ai = (u_id == ESCOBAR_AI_ID)
        
        badge = get_rank_badge(idx, is_ai=is_ai)
        _, tier = get_user_tier(pts)
        display_name = format_bidi_name(name)

        if idx <= 3:
            rank_prefix = f"{badge}"
        else:
            rank_prefix = f"<code>{idx:02d}.</code> {badge}"

        text += f"{rank_prefix} <b>{display_name}</b> ({tier})\n"
        text += f"    └ 💰 <code>{pts} PTS</code>  ▫️  ⚔️ <code>{wins}</code>\n\n"

    if remaining_list:
        text += "────────────────────\n\n"
        for idx, u in enumerate(remaining_list, 16):
            u_id, name, pts, wins = u[0], u[1], max(0, u[2]), u[3]
            is_ai = (u_id == ESCOBAR_AI_ID)
            
            badge = "🔰" if pts < 100 else "🔹"
            if is_ai:
                badge = "🤖"
                
            _, tier = get_user_tier(pts)
            display_name = format_bidi_name(name)

            text += f"<code>{idx:02d}.</code> {badge} <b>{display_name}</b> ({tier})\n"
            text += f"    └ 💰 <code>{pts} PTS</code>  ▫️  ⚔️ <code>{wins}</code>\n\n"

    text += "────────────────────"
    return text

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await show_leaderboard_text()
    await update.message.reply_text(text, parse_mode="HTML")

async def user_profile_handler(query):
    user_id = query.from_user.id
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("""
            SELECT points, duel_wins, total_predictions, correct_results, exact_predictions, season_gold, season_silver, season_bronze
            FROM users WHERE user_id = ?
        """, (user_id,)) as cur:
            u = await cur.fetchone()

    pts, dw, total, correct, exact, g, s, b = u if u else (100, 0, 0, 0, 0, 0, 0, 0)
    icon, tier = get_user_tier(pts)
    safe_name = html.escape(query.from_user.first_name)
    p_today = await get_penalty_count_db(user_id)
    g_today = await get_guess_count_db(user_id)

    trophies = ""
    if g > 0 or s > 0 or b > 0:
        trophies = f"\n🏆 <b>ویترین مدال‌های سیزن:</b>\n🥇 طلا: {g}  ▫️  🥈 نقره: {s}  ▫️  🥉 برنز: {b}\n"

    text = (
        f"👤 <b>پروفایل بازیکن: {safe_name}</b>\n"
        f"────────────────────\n"
        f"🌟 رتبه: {icon} <b>{tier}</b>\n"
        f"⚡️ موجودی: <code>{pts} PTS</code>  ▫️  ⚔️ بردها: <code>{dw}</code>\n"
        f"🥅 پنالتی‌های امروز: <code>{p_today}/3</code>\n"
        f"🕵️‍♂️ پرونده‌های حدس امروز: <code>{g_today}/3</code>\n"
        f"{trophies}"
        f"────────────────────"
    )
    await safe_edit_message(query, text, reply_markup=kb.get_back_button())

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

async def guess_timeout_job(context: ContextTypes.DEFAULT_TYPE):
    global ACTIVE_GUESS_GAME
    if ACTIVE_GUESS_GAME and ACTIVE_GUESS_GAME.get("is_active"):
        chat_id = ACTIVE_GUESS_GAME["chat_id"]
        main_name = ACTIVE_GUESS_GAME["names"][0]
        player_name = html.escape(ACTIVE_GUESS_GAME["player_name"])
        ACTIVE_GUESS_GAME["is_active"] = False
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏰ <b>مهلت ۴۵ ثانیه‌ای پاسخ به پایان رسید!</b>\n"
                 f"👤 ستاره مورد نظر: <b>{main_name}</b> ({player_name}) بود.",
            parse_mode="HTML"
        )

# چالش حدس: ۳ بار در روز + ۱۰ امتیاز پاداش
async def start_guess_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update):
        return

    user = update.effective_user
    await ensure_user(user)

    g_count = await get_guess_count_db(user.id)
    if g_count >= 3:
        await update.effective_message.reply_text(
            f"⛔️ <b>{html.escape(user.first_name)}</b> عزیز، شما سهمیه ۳ بار حدس بازیکن امروز خود را مصرف کرده‌اید!\n"
            "فردا مجدداً می‌توانید ۳ پرونده دیگر حل کنید.",
            parse_mode="HTML"
        )
        return

    global ACTIVE_GUESS_GAME
    if ACTIVE_GUESS_GAME and ACTIVE_GUESS_GAME.get("is_active"):
        challenger_name = html.escape(ACTIVE_GUESS_GAME.get("challenger_name", "کاربر"))
        await update.effective_message.reply_text(
            f"⚠️ یک پرونده هم‌اکنون برای <b>{challenger_name}</b> در جریان است!\n"
            "لطفاً تا پایان تایمر ۴۵ ثانیه‌ای شکیبا باشید.",
            parse_mode="HTML"
        )
        return

    await increment_guess_count_db(user.id)
    current_attempt = g_count + 1

    p = get_next_guess_player()
    career_str = "\n".join([f"  {idx}. {club}" for idx, club in enumerate(p['career'], 1)])

    ACTIVE_GUESS_GAME = {
        "names": p["names"],
        "player_name": p["names"][1] if len(p["names"]) > 1 else p["names"][0],
        "reward": 10,  # ۱۰ امتیاز برای هر پاسخ درست
        "chat_id": update.effective_chat.id,
        "challenger_id": user.id,
        "challenger_name": user.first_name,
        "is_active": True
    }

    text = (
        "🕵️‍♂️ <b>پرونده اطلاعاتی: ستاره فوتبال را شناسایی کنید!</b>\n"
        "────────────────────\n"
        f"🎯 بازیکن چالش: <b>{html.escape(user.first_name)}</b> (فرصت {current_attempt} از ۳)\n"
        f"⏱ مهلت پاسخ: <b>۴۵ ثانیه</b> ⏳\n"
        f"🌍 <b>ملیت:</b> {p['nation']}\n"
        f"📌 <b>پست تخصصی:</b> {p['pos']}\n\n"
        f"🏟 <b>مسیر باشگاهی:</b>\n{career_str}\n\n"
        f"⭐️ <b>سرنخ کلیدی:</b>\n{p['clue']}\n"
        "────────────────────\n"
        "💰 پاداش پاسخ صحیح: <b>+10 امتیاز</b>\n"
        "👇 نام بازیکن را در گروه ارسال کنید:"
    )
    await update.message.reply_text(text, parse_mode="HTML")
    context.job_queue.run_once(guess_timeout_job, 45, name=f"guess_timer_{user.id}")

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

# مسابقه پنالتی: ۳ بار در روز + شرط ۱۵ امتیاز
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
    if c_count >= 3:
        await update.message.reply_text(f"⛔️ <b>{html.escape(challenger.first_name)}</b> عزیز، شما سقف مجاز ۳ پنالتی در روز خود را مصرف کرده‌اید!", parse_mode="HTML")
        return

    o_count = await get_penalty_count_db(opponent.id)
    if o_count >= 3:
        await update.message.reply_text(f"⛔️ حریف شما <b>{html.escape(opponent.first_name)}</b> امروز ۳ پنالتی خود را بازی کرده است!", parse_mode="HTML")
        return

    await ensure_user(challenger)
    await ensure_user(opponent)

    p_id = str(random.randint(10000, 99999))
    ACTIVE_SHOOTOUTS[p_id] = {
        "p1": {"id": challenger.id, "name": challenger.first_name, "shot": None},
        "p2": {"id": opponent.id, "name": opponent.first_name, "shot": None},
        "current_turn": challenger.id,
        "round": 1,
        "stake": 15,  # تغییر به ۱۵ امتیاز
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
        f"👤 شوت‌زن اول: <b>{c_name}</b> ({c_count + 1}/3)\n"
        f"👤 شوت‌زن دوم: <b>{o_name}</b> ({o_count + 1}/3)\n"
        "💰 شرط مسابقه: <b>15 امتیاز</b> 🪙\n"
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

        await query.answer("✅ پیش‌بینی شما ثبت شد!", show_alert=False)

        m = MATCH_CACHE.get(match_id)
        if not m:
            m = {"home_team": "میزبان", "away_team": "میهمان", "date": None}

        new_text = await generate_pool_message_text(m, participants)
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
        league_title = LEAGUE_TITLES.get(league_code, "فوتبال")
        day_title = "امروز" if is_today else "فردا"

        matches = []
        if league_code == "all":
            for l_id in ["eng.1", "esp.1", "ita.1", "ger.1"]:
                m_list = await provider.get_matches(target_date.strftime("%Y%m%d"), league_code=l_id)
                matches.extend(m_list[:2])
        else:
            matches = await provider.get_matches(target_date.strftime("%Y%m%d"), league_code=league_code)

        if not matches:
            await safe_edit_message(query, f"⏳ مسابقه‌ای برای {league_title} در تاریخ {day_title} ثبت نشده است.", reply_markup=kb.get_back_button())
            return

        text = f"⚽️ <b>اسکوربورد مسابقات {league_title} ({day_title}):</b>\n"
        text += "────────────────────\n\n"

        for m in matches[:8]:
            h_team = html.escape(str(m['home_team']))
            a_team = html.escape(str(m['away_team']))
            h_sc = m.get('home_score')
            a_sc = m.get('away_score')
            status = str(m.get('status', 'UPCOMING')).upper()
            match_time = format_iran_time(m.get("date"))

            if status in ["LIVE", "IN_PLAY", "1H", "2H", "HT"]:
                score_box = f"<b>{h_sc}</b> - <b>{a_sc}</b>" if h_sc is not None else "0 - 0"
                status_badge = "🔴 <b>در حال برگزاری (LIVE)</b>"
                match_header = f"⚽️ <b>{h_team}</b> <code>{score_box}</code> <b>{a_team}</b>"
            elif status in ["FINISHED", "FT", "POST"]:
                score_box = f"<b>{h_sc}</b> - <b>{a_sc}</b>" if h_sc is not None else "0 - 0"
                status_badge = "🏁 <b>پایان مسابقه (FT)</b>"
                match_header = f"⚽️ <b>{h_team}</b> <code>{score_box}</code> <b>{a_team}</b>"
            else:
                status_badge = f"⏰ ساعت <b>{match_time}</b> (به وقت تهران)"
                match_header = f"⚽️ <b>{h_team}</b> 🆚 <b>{a_team}</b>"

            text += (
                f"{match_header}\n"
                f"   └ {status_badge}\n"
                "────────────────────\n"
            )

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
        await user_profile_handler(query)

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

    global ACTIVE_GUESS_GAME
    if ACTIVE_GUESS_GAME and ACTIVE_GUESS_GAME.get("is_active") and ACTIVE_GUESS_GAME["chat_id"] == update.effective_chat.id:
        if update.effective_user.id == ACTIVE_GUESS_GAME["challenger_id"]:
            user_ans = msg.lower()
            if any(alias in user_ans for alias in ACTIVE_GUESS_GAME["names"]):
                winner = update.effective_user
                reward = ACTIVE_GUESS_GAME["reward"]

                current_jobs = context.job_queue.get_jobs_by_name(f"guess_timer_{winner.id}")
                for j in current_jobs:
                    j.schedule_removal()

                async with aiosqlite.connect(DATABASE_PATH) as db:
                    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, winner.id))
                    await db.commit()
                
                await update.message.reply_text(
                    f"🎉🔥 <b>پاسخ کاملاً صحیح! هویت ستاره به درستی تشخیص داده شد!</b>\n"
                    f"👤 برنده چالش: <b>{html.escape(winner.first_name)}</b>\n"
                    f"💰 پاداش: <b>+{reward} امتیاز</b> به حساب شما اضافه شد.",
                    parse_mode="HTML"
                )
                ACTIVE_GUESS_GAME["is_active"] = False
                return

    if msg in ["دوئل", "duel", "چالش"]:
        if await is_action_allowed_in_chat(update):
            await trigger_duel(update, context)
    elif msg in ["پنالتی", "پنالتی کشی", "penalty"]:
        if await is_action_allowed_in_chat(update):
            await trigger_penalty_shootout(update, context)
    elif msg in ["شوت", "گل", "shoot"]:
        if await is_action_allowed_in_chat(update):
            await daily_shoot_cmd(update, context)
    elif msg in ["جایزه", "روزانه", "daily"]:
        if await is_action_allowed_in_chat(update):
            await daily_reward_cmd(update, context)
    elif msg in ["حدس", "حدس بازیکن", "guess"]:
        await start_guess_game(update, context)
    elif msg in ["گردونه", "wheel", "شانس"]:
        await spin_wheel_cmd(update, context)
    elif msg in ["جکپات", "jackpot"]:
        await jackpot_cmd(update, context)

    elif msg in ["شروع", "منو", "فوتبال"]:
        await start(update, context)
    elif msg in ["جدول", "رنکینگ", "امتیازات"]:
        await leaderboard_cmd(update, context)
    elif msg in ["پیشبینی", "پیش بینی"]:
        await update.message.reply_text("🎯 جهت ورود به تالار پیش‌بینی، دستور /start را ارسال فرمایید.", parse_mode="HTML")
    elif msg in ["بازیها", "بازی ها"]:
        iran_now = get_iran_now()
        matches = await provider.get_matches(iran_now.strftime("%Y%m%d"), league_code="eng.1")
        if matches:
            t = "🔥 <b>مسابقات منتخب امروز (به وقت تهران):</b>\n────────────────────\n\n"
            for m in matches[:4]:
                tm = format_iran_time(m.get("date"))
                t += f"▫️ <b>{m['home_team']}</b> 🆚 <b>{m['away_team']}</b> (⏰ <code>{tm}</code>)\n"
            await update.message.reply_text(t, parse_mode="HTML")
        else:
            await update.message.reply_text("⏳ مسابقه‌ای برای امروز یافت نشد.")

async def post_init(application: Application):
    await init_db()
    await ensure_escobar_ai()
    application.job_queue.run_repeating(monitor_real_barca_live_job, interval=25, first=3)
    application.job_queue.run_repeating(check_and_settle_monthly_season, interval=3600, first=10)

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

    logger.info("Bot fully upgraded: 3x Guess (10 PTS) & 3x Penalty (15 PTS) online!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
