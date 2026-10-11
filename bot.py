import os
import re
import html
import random
import logging
import asyncio
import threading
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from collections import Counter

import aiosqlite
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)

from config import BOT_TOKEN, ADMIN_ID, DATABASE_PATH, DEFAULT_POINTS, LEAGUE_CODES, ACTIVE_MONITOR_LEAGUES
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

# --- FC CARDS DATABASE POOL (EXPANDED WITH NATION & CLUB) ---
FC_CATALOG = [
    # ICONS & GOATs (90+)
    {"name": "پله", "pos": "FWD", "ovr": 95, "rarity": "ICON", "nation": "برزیل 🇧🇷", "club": "سانتوس"},
    {"name": "دیگو مارادونا", "pos": "MID", "ovr": 95, "rarity": "ICON", "nation": "آرژانتین 🇦🇷", "club": "ناپولی"},
    {"name": "زین‌الدین زیدان", "pos": "MID", "ovr": 94, "rarity": "ICON", "nation": "فرانسه 🇫🇷", "club": "رئال مادرید"},
    {"name": "پائولو مالدینی", "pos": "DEF", "ovr": 94, "rarity": "ICON", "nation": "ایتالیا 🇮🇹", "club": "میلان"},
    {"name": "لو یاشین", "pos": "GK", "ovr": 94, "rarity": "ICON", "nation": "روسیه 🇷🇺", "club": "دینامو مسکو"},
    {"name": "رونالدو نازاریو", "pos": "FWD", "ovr": 94, "rarity": "ICON", "nation": "برزیل 🇧🇷", "club": "رئال مادرید"},
    {"name": "رونالدینیو", "pos": "MID", "ovr": 93, "rarity": "ICON", "nation": "برزیل 🇧🇷", "club": "بارسلونا"},
    {"name": "یوهان کرویف", "pos": "FWD", "ovr": 93, "rarity": "ICON", "nation": "هلند 🇳🇱", "club": "بارسلونا"},
    {"name": "تیری آنری", "pos": "FWD", "ovr": 93, "rarity": "ICON", "nation": "فرانسه 🇫🇷", "club": "آرسنال"},
    {"name": "لیونل مسی", "pos": "FWD", "ovr": 93, "rarity": "ICON", "nation": "آرژانتین 🇦🇷", "club": "اینتر میامی"},
    {"name": "کریستیانو رونالدو", "pos": "FWD", "ovr": 92, "rarity": "ICON", "nation": "پرتغال 🇵🇹", "club": "النصر"},
    {"name": "ایکر کاسیاس", "pos": "GK", "ovr": 92, "rarity": "ICON", "nation": "اسپانیا 🇪🇸", "club": "رئال مادرید"},
    {"name": "جانلوئیجی بوفون", "pos": "GK", "ovr": 92, "rarity": "ICON", "nation": "ایتالیا 🇮🇹", "club": "یوونتوس"},
    {"name": "روبرتو کارلوس", "pos": "DEF", "ovr": 91, "rarity": "ICON", "nation": "برزیل 🇧🇷", "club": "رئال مادرید"},
    {"name": "کافو", "pos": "DEF", "ovr": 91, "rarity": "ICON", "nation": "برزیل 🇧🇷", "club": "میلان"},
    {"name": "سرخیو راموس", "pos": "DEF", "ovr": 91, "rarity": "ICON", "nation": "اسپانیا 🇪🇸", "club": "رئال مادرید"},
    {"name": "کارلس پویول", "pos": "DEF", "ovr": 91, "rarity": "ICON", "nation": "اسپانیا 🇪🇸", "club": "بارسلونا"},
    {"name": "ژاوی هرناندز", "pos": "MID", "ovr": 91, "rarity": "ICON", "nation": "اسپانیا 🇪🇸", "club": "بارسلونا"},
    {"name": "آندرس اینیستا", "pos": "MID", "ovr": 91, "rarity": "ICON", "nation": "اسپانیا 🇪🇸", "club": "بارسلونا"},
    {"name": "کیلیان امباپه", "pos": "FWD", "ovr": 91, "rarity": "ICON", "nation": "فرانسه 🇫🇷", "club": "رئال مادرید"},
    {"name": "ارلینگ هالند", "pos": "FWD", "ovr": 91, "rarity": "ICON", "nation": "نروژ 🇳🇴", "club": "منچسترسیتی"},
    {"name": "کوین دی‌بروینه", "pos": "MID", "ovr": 91, "rarity": "ICON", "nation": "بلژیک 🇧🇪", "club": "منچسترسیتی"},
    {"name": "ویرجیل فن‌دایک", "pos": "DEF", "ovr": 90, "rarity": "ICON", "nation": "هلند 🇳🇱", "club": "لیورپول"},
    {"name": "مانوئل نویر", "pos": "GK", "ovr": 90, "rarity": "ICON", "nation": "آلمان 🇩🇪", "club": "بایرن مونیخ"},

    # WALKOUT / ELITE (86 - 89)
    {"name": "وینیسیوس جونیور", "pos": "FWD", "ovr": 89, "rarity": "ELITE", "nation": "برزیل 🇧🇷", "club": "رئال مادرید"},
    {"name": "جود بلینگهام", "pos": "MID", "ovr": 89, "rarity": "ELITE", "nation": "انگلیس 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "club": "رئال مادرید"},
    {"name": "رودری", "pos": "MID", "ovr": 89, "rarity": "ELITE", "nation": "اسپانیا 🇪🇸", "club": "منچسترسیتی"},
    {"name": "تیبو کورتوا", "pos": "GK", "ovr": 89, "rarity": "ELITE", "nation": "بلژیک 🇧🇪", "club": "رئال مادرید"},
    {"name": "آلیسون بکر", "pos": "GK", "ovr": 89, "rarity": "ELITE", "nation": "برزیل 🇧🇷", "club": "لیورپول"},
    {"name": "هری کین", "pos": "FWD", "ovr": 89, "rarity": "ELITE", "nation": "انگلیس 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "club": "بایرن مونیخ"},
    {"name": "محمد صلاح", "pos": "FWD", "ovr": 89, "rarity": "ELITE", "nation": "مصر 🇪🇬", "club": "لیورپول"},
    {"name": "روبرت لواندوفسکی", "pos": "FWD", "ovr": 88, "rarity": "ELITE", "nation": "لهستان 🇵🇱", "club": "بارسلونا"},
    {"name": "روبن دیاز", "pos": "DEF", "ovr": 88, "rarity": "ELITE", "nation": "پرتغال 🇵🇹", "club": "منچسترسیتی"},
    {"name": "فدریکو والورده", "pos": "MID", "ovr": 88, "rarity": "ELITE", "nation": "اروگوئه 🇺🇾", "club": "رئال مادرید"},
    {"name": "یان اوبلاک", "pos": "GK", "ovr": 88, "rarity": "ELITE", "nation": "اسلوونی 🇸🇮", "club": "اتلتیکو مادرید"},
    {"name": "آنتونیو رودیگر", "pos": "DEF", "ovr": 87, "rarity": "ELITE", "nation": "آلمان 🇩🇪", "club": "رئال مادرید"},
    {"name": "تئو ارناندز", "pos": "DEF", "ovr": 87, "rarity": "ELITE", "nation": "فرانسه 🇫🇷", "club": "میلان"},
    {"name": "مارتین اودگارد", "pos": "MID", "ovr": 87, "rarity": "ELITE", "nation": "نروژ 🇳🇴", "club": "آرسنال"},
    {"name": "بوکایو ساکا", "pos": "FWD", "ovr": 87, "rarity": "ELITE", "nation": "انگلیس 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "club": "آرسنال"},
    {"name": "فلورین ویرتز", "pos": "MID", "ovr": 87, "rarity": "ELITE", "nation": "آلمان 🇩🇪", "club": "بایر لورکوزن"},
    {"name": "جمال موسیالا", "pos": "MID", "ovr": 87, "rarity": "ELITE", "nation": "آلمان 🇩🇪", "club": "بایرن مونیخ"},
    {"name": "مارکینیوس", "pos": "DEF", "ovr": 86, "rarity": "ELITE", "nation": "برزیل 🇧🇷", "club": "پاری‌سن‌ژرمن"},
    {"name": "سون هیونگ مین", "pos": "FWD", "ovr": 86, "rarity": "ELITE", "nation": "کره جنوبی 🇰🇷", "club": "تاتنهام"},
    {"name": "برناردو سیلوا", "pos": "MID", "ovr": 86, "rarity": "ELITE", "nation": "پرتغال 🇵🇹", "club": "منچسترسیتی"},
    {"name": "مایک منیان", "pos": "GK", "ovr": 86, "rarity": "ELITE", "nation": "فرانسه 🇫🇷", "club": "میلان"},

    # RARE GOLD (82 - 85)
    {"name": "فرنکی دی‌یونگ", "pos": "MID", "ovr": 85, "rarity": "RARE", "nation": "هلند 🇳🇱", "club": "بارسلونا"},
    {"name": "رافائل لیائو", "pos": "FWD", "ovr": 85, "rarity": "RARE", "nation": "پرتغال 🇵🇹", "club": "میلان"},
    {"name": "پدری", "pos": "MID", "ovr": 85, "rarity": "RARE", "nation": "اسپانیا 🇪🇸", "club": "بارسلونا"},
    {"name": "دوناروما", "pos": "GK", "ovr": 85, "rarity": "RARE", "nation": "ایتالیا 🇮🇹", "club": "پاری‌سن‌ژرمن"},
    {"name": "امیلیانو مارتینز", "pos": "GK", "ovr": 85, "rarity": "RARE", "nation": "آرژانتین 🇦🇷", "club": "استون ویلا"},
    {"name": "الساندرو باستونی", "pos": "DEF", "ovr": 85, "rarity": "RARE", "nation": "ایتالیا 🇮🇹", "club": "اینتر"},
    {"name": "نیکولو بارلا", "pos": "MID", "ovr": 85, "rarity": "RARE", "nation": "ایتالیا 🇮🇹", "club": "اینتر"},
    {"name": "ویلیام سالیبا", "pos": "DEF", "ovr": 85, "rarity": "RARE", "nation": "فرانسه 🇫🇷", "club": "آرسنال"},
    {"name": "یوشکو گواردیول", "pos": "DEF", "ovr": 85, "rarity": "RARE", "nation": "کرواسی 🇭🇷", "club": "منچسترسیتی"},
    {"name": "اشرف حکیمی", "pos": "DEF", "ovr": 84, "rarity": "RARE", "nation": "مراکش 🇲🇦", "club": "پاری‌سن‌ژرمن"},
    {"name": "ادر میلیتائو", "pos": "DEF", "ovr": 84, "rarity": "RARE", "nation": "برزیل 🇧🇷", "club": "رئال مادرید"},
    {"name": "اورلین شوامنی", "pos": "MID", "ovr": 84, "rarity": "RARE", "nation": "فرانسه 🇫🇷", "club": "رئال مادرید"},
    {"name": "ادواردو کاماوینگا", "pos": "MID", "ovr": 84, "rarity": "RARE", "nation": "فرانسه 🇫🇷", "club": "رئال مادرید"},
    {"name": "برونو فرناندز", "pos": "MID", "ovr": 84, "rarity": "RARE", "nation": "پرتغال 🇵🇹", "club": "منچستر یونایتد"},
    {"name": "خولیان آلوارز", "pos": "FWD", "ovr": 84, "rarity": "RARE", "nation": "آرژانتین 🇦🇷", "club": "اتلتیکو مادرید"},
    {"name": "آلفونسو دیویس", "pos": "DEF", "ovr": 84, "rarity": "RARE", "nation": "کانادا 🇨🇦", "club": "بایرن مونیخ"},
    {"name": "گاوی", "pos": "MID", "ovr": 83, "rarity": "RARE", "nation": "اسپانیا 🇪🇸", "club": "بارسلونا"},
    {"name": "داروین نونیز", "pos": "FWD", "ovr": 83, "rarity": "RARE", "nation": "اروگوئه 🇺🇾", "club": "لیورپول"},
    {"name": "فدریکو کیه‌زا", "pos": "FWD", "ovr": 83, "rarity": "RARE", "nation": "ایتالیا 🇮🇹", "club": "لیورپول"},
    {"name": "خویچا کواراتسخلیا", "pos": "FWD", "ovr": 83, "rarity": "RARE", "nation": "گرجستان 🇬🇪", "club": "ناپولی"},
    {"name": "مهدی طارمی", "pos": "FWD", "ovr": 82, "rarity": "RARE", "nation": "ایران 🇮🇷", "club": "اینتر"},
    {"name": "سردار آزمون", "pos": "FWD", "ovr": 82, "rarity": "RARE", "nation": "ایران 🇮🇷", "club": "شباب الاهلی"},
    {"name": "گرگور کوبل", "pos": "GK", "ovr": 84, "rarity": "RARE", "nation": "سوئیس 🇨🇭", "club": "دورتموند"},
    {"name": "یان سومر", "pos": "GK", "ovr": 83, "rarity": "RARE", "nation": "سوئیس 🇨🇭", "club": "اینتر"},

    # COMMON (75 - 81)
    {"name": "داوید رایا", "pos": "GK", "ovr": 81, "rarity": "COMMON", "nation": "اسپانیا 🇪🇸", "club": "آرسنال"},
    {"name": "آندره اونانا", "pos": "GK", "ovr": 81, "rarity": "COMMON", "nation": "کامرون 🇨🇲", "club": "منچستر یونایتد"},
    {"name": "نیک پوپ", "pos": "GK", "ovr": 81, "rarity": "COMMON", "nation": "انگلیس 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "club": "نیوکاسل"},
    {"name": "اسکات مک‌تامینی", "pos": "MID", "ovr": 80, "rarity": "COMMON", "nation": "اسکاتلند 🏴󠁧󠁢󠁳󠁣󠁴󠁿", "club": "ناپولی"},
    {"name": "ریچارلیسون", "pos": "FWD", "ovr": 80, "rarity": "COMMON", "nation": "برزیل 🇧🇷", "club": "تاتنهام"},
    {"name": "مارکوس رشفورد", "pos": "FWD", "ovr": 81, "rarity": "COMMON", "nation": "انگلیس 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "club": "منچستر یونایتد"},
    {"name": "تیمو ورنر", "pos": "FWD", "ovr": 80, "rarity": "COMMON", "nation": "آلمان 🇩🇪", "club": "تاتنهام"},
    {"name": "هری مگوایر", "pos": "DEF", "ovr": 79, "rarity": "COMMON", "nation": "انگلیس 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "club": "منچستر یونایتد"},
    {"name": "واتارو اندو", "pos": "MID", "ovr": 79, "rarity": "COMMON", "nation": "ژاپن 🇯🇵", "club": "لیورپول"},
    {"name": "آنتونی", "pos": "FWD", "ovr": 78, "rarity": "COMMON", "nation": "برزیل 🇧🇷", "club": "منچستر یونایتد"},
    {"name": "میخائیلو مودریک", "pos": "FWD", "ovr": 78, "rarity": "COMMON", "nation": "اوکراین 🇺🇦", "club": "چلسی"},
    {"name": "علیرضا جهانبخش", "pos": "FWD", "ovr": 77, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "هیرنفین"},
    {"name": "رامین رضاییان", "pos": "DEF", "ovr": 77, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "استقلال"},
    {"name": "علیرضا بیرانوند", "pos": "GK", "ovr": 77, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "تراکتور"},
    {"name": "سامان قدوس", "pos": "MID", "ovr": 76, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "کلبا"},
    {"name": "سید حسین حسینی", "pos": "GK", "ovr": 76, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "استقلال"},
    {"name": "شجاع خلیل‌زاده", "pos": "DEF", "ovr": 75, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "تراکتور"},
    {"name": "مهدی ترابی", "pos": "MID", "ovr": 76, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "تراکتور"},
    {"name": "مهدی قایدی", "pos": "FWD", "ovr": 76, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "کلبا"},
    {"name": "محمد محبی", "pos": "FWD", "ovr": 76, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "روستوف"}
]

FC_CATALOG_DICT = {c["name"]: c for c in FC_CATALOG}

SELL_PRICES = {
    "ICON": 1400,
    "ELITE": 550,
    "RARE": 200,
    "COMMON": 70
}

GUESS_PLAYERS_FILE = os.path.join(os.path.dirname(__file__), "guess_players.json")
try:
    with open(GUESS_PLAYERS_FILE, "r", encoding="utf-8") as f:
        RAW_GUESS_PLAYERS = json.load(f)
except Exception as e:
    logger.error(f"Error loading guess_players.json: {e}")
    RAW_GUESS_PLAYERS = []

GUESS_DECK = []

def refill_guess_deck():
    global GUESS_DECK
    GUESS_DECK = RAW_GUESS_PLAYERS.copy()
    random.shuffle(GUESS_DECK)

def get_next_guess_player():
    global GUESS_DECK
    if not GUESS_DECK:
        refill_guess_deck()
    if not GUESS_DECK:
        return {
            "names": ["مسی", "messi"],
            "nation": "آرژانتین 🇦🇷",
            "pos": "مهاجم کاذب",
            "career": ["بارسلونا 🇪🇸", "اینتر میامی 🇺🇸"],
            "clue": "⭐ برنده ۸ توپ طلا"
        }
    return GUESS_DECK.pop()

ACTIVE_GUESS_GAMES = {}
MATCH_CACHE = {}
ACTIVE_DUELS = {}
ACTIVE_TEAM_DUELS = {}
ACTIVE_SHOOTOUTS = {}
ACTIVE_CARD_MATCHES = {}
CHEAT_MODE_USERS = set()
TRACKED_LIVE_MATCHES = {}
USER_JACKPOT_DRAFTS = {}
ACTIVE_ASYNCIO_TIMERS = {}

def schedule_timer(context, callback_coro, delay_seconds, data, name=None):
    if getattr(context, 'job_queue', None):
        return context.job_queue.run_once(callback_coro, delay_seconds, data=data, name=name)

    async def _timer_runner():
        try:
            await asyncio.sleep(delay_seconds)
            class SimpleJob:
                def __init__(self, d): self.data = d
            class SimpleContext:
                def __init__(self, c, d):
                    self.bot = c.bot
                    self.application = getattr(c, 'application', None)
                    self.job_queue = None
                    self.job = SimpleJob(d)
            await callback_coro(SimpleContext(context, data))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f'Error in timer {name}: {e}')
        finally:
            if name: ACTIVE_ASYNCIO_TIMERS.pop(name, None)

    task = asyncio.create_task(_timer_runner())
    if name:
        cancel_timer(context, name)
        ACTIVE_ASYNCIO_TIMERS[name] = task
    return task

def cancel_timer(context, name):
    if getattr(context, 'job_queue', None):
        for j in context.job_queue.get_jobs_by_name(name): j.schedule_removal()
    if name in ACTIVE_ASYNCIO_TIMERS:
        task = ACTIVE_ASYNCIO_TIMERS.pop(name, None)
        if task and not task.done(): task.cancel()

async def run_repeating_task(coro_fn, app, interval_sec, initial_delay_sec=5):
    class SimpleContext:
        def __init__(self, application):
            self.bot = application.bot
            self.application = application
            self.job_queue = None

    await asyncio.sleep(initial_delay_sec)
    ctx = SimpleContext(app)
    while True:
        try:
            await coro_fn(ctx)
        except Exception as e:
            logger.error(f'Error in background task {coro_fn.__name__}: {e}')
        await asyncio.sleep(interval_sec)

LEAGUE_TITLES = {
    "eng.1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",
    "esp.1": "🇪🇸 La Liga",
    "ita.1": "🇮🇹 Serie A",
    "ger.1": "🇩🇪 Bundesliga",
    "fra.1": "🇫🇷 Ligue 1",
    "uefa.champions": "🏆 Champions League",
    "fifa.friendly": "🌍 مسابقات ملی و فیفادی",
    "uefa.nations": "🇪🇺 لیگ ملت‌های اروپا",
    "fifa.worldq.afc": "🌏 انتخابی جام جهانی (آسیا)",
    "fifa.worldq.uefa": "🏆 انتخابی جام جهانی (اروپا)",
    "irn.1": "🇮🇷 لیگ برتر ایران",
    "all": "🌐 گلچین مسابقات معتبر"
}

BANTER_TEXTS = {
    "real": [
        "⚪️ باختین کهکشانی‌های پوشالی! حتی دروازه‌بانتونم دیگه رو نداره تو صورت هوادار نگاه کنه!",
        "⚪️ ادعای پادشاهی اروپا داشتین ولی باختین، سکوت کنید لااقل!",
        "⚪️ دوباره باختین؟ وقتی می‌بازید ناله نکنید و گردن داور نندازید!"
    ],
    "barca": [
        "🔴🔵 مسخره‌ترین نمایش ممکن! حتی تیم نونهالان هم از این خط دفاع بهتر بازی می‌کنه!",
        "🔴🔵 دوباره تحقیر شدین؟ بارسا فقط ساخته شده واسه کامبک خوردن و اشک ریختن!",
        "🔴🔵 این باختتونم مثل همیشه مایه آبروریزی بود؛ حداقل تا هفته بعد یه جا قایم شین!"
    ],
    "atletico": [
        "🔴⚪️ باختین اتوبوس‌سوارها! این همه دفاع اتوبوسی آخرش به همین باخت ختم شد؟",
        "🔴⚪️ سیمئونه خودش هم دیگه از این سبک خسته‌کننده خجالت می‌کشه!"
    ],
    "liverpool": [
        "🔴 باختین مدعی‌ها! این لیگه نه جام‌های شانسکی؛ باختین و رفتین پی کارتون!",
        "🔴 دوباره باختین؟ آنفیلد شده کاروانسرا، روح کلوپ هم از این بازیتون خجالت می‌کشه!"
    ],
    "united": [
        "🔴 باختین ارواح سرگردان! اولدترافورد دیگه تئاتر رویاها نیست، قبرستان آرزوهاست!",
        "🔴 دوباره باختین؟ یونایتد فقط برای تفریح و میم شدن رقبا تو اینترنت ساخته شده!"
    ]
}

def get_iran_now():
    return datetime.now(IRAN_TZ)

def format_iran_time(dt_str: str) -> str:
    if not dt_str: return "نامشخص"
    try:
        clean_time = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_time)
        dt_iran = dt.astimezone(IRAN_TZ)
        return dt_iran.strftime("%H:%M")
    except Exception: return "نامشخص"

def get_user_tier(points: int) -> tuple[str, str]:
    pts = max(0, int(points or 0))
    if pts >= 3000: return "🌌", "Football Immortal"
    elif pts >= 2200: return "🐐", "G.O.A.T"
    elif pts >= 1600: return "⚡️", "Galactico"
    elif pts >= 1100: return "👑", "Ballon d'Or"
    elif pts >= 800: return "💎", "Legend"
    elif pts >= 550: return "🔮", "World Class"
    elif pts >= 350: return "🎖", "Captain"
    elif pts >= 200: return "🌟", "First Team"
    elif pts >= 100: return "⚡️", "Semi-Pro"
    else: return "🔰", "Academy"

def xp_for_next_level(level: int) -> int:
    return 100 + max(0, level - 1) * 25

def calculate_level(xp: int):
    level = 1
    remaining = max(0, int(xp or 0))
    while remaining >= xp_for_next_level(level):
        remaining -= xp_for_next_level(level)
        level += 1
        if level >= 1000: break
    needed = xp_for_next_level(level)
    percent = int((remaining / needed) * 100) if needed else 100
    return level, remaining, needed, percent

def render_xp_bar(percent: int, width: int = 10) -> str:
    percent = max(0, min(100, percent))
    filled = round(percent / 100 * width)
    return "█" * filled + "░" * (width - filled)

async def profile_add_xp(user_id: int, amount: int):
    if amount <= 0: return
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT profile_xp FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                cur_xp = row[0] if row and row[0] is not None else 0
            new_xp = cur_xp + amount
            lvl, _, _, _ = calculate_level(new_xp)
            await db.execute("UPDATE users SET profile_xp = ?, profile_level = ? WHERE user_id = ?", (new_xp, lvl, user_id))
            await db.commit()
    except Exception as e:
        logger.error(f"Error adding XP: {e}")

async def profile_record_answer(user_id: int, is_correct: bool):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if is_correct:
            await db.execute("""
                UPDATE users SET profile_answered = profile_answered + 1, profile_correct = profile_correct + 1
                WHERE user_id = ?
            """, (user_id,))
        else:
            await db.execute("UPDATE users SET profile_answered = profile_answered + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
    await profile_add_xp(user_id, 15 if is_correct else 3)

async def profile_record_duel_win(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET duel_wins = duel_wins + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
    await profile_add_xp(user_id, 120)

async def profile_record_penalty_win(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET penalty_wins = penalty_wins + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
    await profile_add_xp(user_id, 100)

async def profile_record_guess_win(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET guess_wins = guess_wins + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
    await profile_add_xp(user_id, 80)

def format_bidi_name(name: str) -> str:
    cleaned = (name or "بازیکن").strip()
    return f"{LRM}{html.escape(cleaned)}{LRM}"

class SimpleHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Football Hub Online! 200 OK")

    def log_message(self, format, *args): return

def start_health_server():
    port = int(os.getenv("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), SimpleHealthServer)
        logger.info(f"Health server on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Health server error: {e}")

def identify_tracked_team(team_name: str):
    name = (team_name or "").lower()
    if any(x in name for x in ["real madrid", "رئال مادرید", "madrid"]) and "atletico" not in name and "اتلتیکو" not in name:
        return "real"
    if any(x in name for x in ["barcelona", "بارسلونا", "barca"]):
        return "barca"
    if any(x in name for x in ["atletico", "اتلتیکو", "atlético"]):
        return "atletico"
    if any(x in name for x in ["liverpool", "لیورپول"]):
        return "liverpool"
    if any(x in name for x in ["manchester united", "man utd", "منچستر یونایتد", "یونایتد"]):
        return "united"
    return None

async def get_live_chat_id():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = 'live_chat_id'") as cur:
            row = await cur.fetchone()
            if row and row[0]: return int(row[0])
    return None

async def is_action_allowed_in_chat(update: Update) -> bool:
    chat = update.effective_chat
    if not chat or chat.type == "private": return True
    target_chat_id = await get_live_chat_id()
    if not target_chat_id or chat.id == target_chat_id: return True
    await update.effective_message.reply_text(
        "⛔️ <b>بخش‌های مسابقاتی و امتیازی فقط در گروه اختصاصی ربات فعال است!</b>",
        parse_mode="HTML"
    )
    return False

async def safe_edit_message(query_or_bot, text, reply_markup=None, chat_id=None, message_id=None):
    try:
        if chat_id is not None and message_id is not None:
            await query_or_bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text,
                reply_markup=reply_markup, parse_mode="HTML"
            )
        else:
            await query_or_bot.message.edit_text(
                text=text, reply_markup=reply_markup, parse_mode="HTML"
            )
        return True
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.warning(f"Bad request in safe_edit_message: {e}")
        return False
    except Exception as e:
        logger.debug(f"Edit warning: {e}")
        return False

async def ensure_user(user):
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
                INSERT OR IGNORE INTO users (user_id, first_name, username, points, xp)
                VALUES (?, ?, ?, 100, 0)
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
                INSERT OR IGNORE INTO users (user_id, first_name, username, points, xp)
                VALUES (?, ?, ?, 100, 0)
            """, (ESCOBAR_AI_ID, "Escobar AI 🤖", "escobar_ai"))
            await db.commit()
    except Exception as e:
        logger.error(f"Error in ensure_escobar_ai: {e}")

async def get_penalty_count_db(user_id: int) -> int:
    today_str = get_iran_now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT penalty_date, penalty_count FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str: return row[1] or 0
    return 0

async def increment_penalty_count_db(user_id: int):
    today_str = get_iran_now().strftime("%Y-%m-%d")
    cur_count = await get_penalty_count_db(user_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE users SET penalty_date = ?, penalty_count = ? WHERE user_id = ?
        """, (today_str, cur_count + 1, user_id))
        await db.commit()

async def get_guess_count_db(user_id: int) -> int:
    today_str = get_iran_now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT last_guess_date, guess_count FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str: return row[1] or 0
    return 0

async def increment_guess_count_db(user_id: int):
    today_str = get_iran_now().strftime("%Y-%m-%d")
    cur_count = await get_guess_count_db(user_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE users SET last_guess_date = ?, guess_count = ? WHERE user_id = ?
        """, (today_str, cur_count + 1, user_id))
        await db.commit()

# --- ADMIN COMMANDS: ADD POINTS, BACKUP & RESTORE ---

async def add_points_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID):
        return

    if not context.args:
        await update.message.reply_text("⚠️ <b>نحوه استفاده:</b> <code>/add 500</code>", parse_mode="HTML")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً یک عدد معتبر وارد کنید.")
        return

    target_id = user.id
    target_name = user.first_name

    # اگر روی پیام کاربری ریپلای شده باشد، امتیاز به او تعلق می‌گیرد؛ در غیر اینصورت به ادمین اضافه می‌شود
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_u = update.message.reply_to_message.from_user
        target_id = target_u.id
        target_name = target_u.first_name
        await ensure_user(target_u)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, target_id))
        await db.commit()

    await update.message.reply_text(
        f"✅ <b>مبلغ {amount:,} امتیاز با موفقیت به حساب {html.escape(target_name)} اضافه شد!</b>",
        parse_mode="HTML"
    )

async def backup_db_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != str(ADMIN_ID):
        await update.message.reply_text("⛔️ دسترسی غیرمجاز!")
        return

    if os.path.exists(DATABASE_PATH):
        with open(DATABASE_PATH, "rb") as doc:
            await update.message.reply_document(
                document=doc,
                filename=f"backup_{get_iran_now().strftime('%Y%m%d_%H%M')}.db",
                caption="💾 <b>نسخه کامل پشتیبان دیتابیس ربات</b>\nجهت بازگردانی روی هاست جدید، همین فایل را به ربات بفرستید و روی آن بنویسید: <code>/restore</code>",
                parse_mode="HTML"
            )
    else:
        await update.message.reply_text("⚠️ فایل دیتابیس یافت نشد.")

async def restore_db_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != str(ADMIN_ID):
        await update.message.reply_text("⛔️ دسترسی غیرمجاز!")
        return

    target_msg = update.message.reply_to_message
    if not target_msg or not target_msg.document:
        await update.message.reply_text("⚠️ برای بازگردانی، این دستور را روی فایل دیتابیس ریپلای کن:\n<code>/restore</code>", parse_mode="HTML")
        return

    try:
        doc = target_msg.document
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(DATABASE_PATH)
        await update.message.reply_text("✅ <b>دیتابیس با موفقیت جایگزین شد!</b> تمامی اطلاعات کاربران بازگردانی گردید.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error restoring DB: {e}")
        await update.message.reply_text(f"❌ خطا در بازگردانی فایل دیتابیس: {e}")

async def reset_points_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID):
        await update.message.reply_text("⛔️ دسترسی غیرمجاز!")
        return
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE users SET points = 100")
            await db.commit()
        await update.message.reply_text("✅ <b>امتیاز تمامی کاربران با موفقیت روی ۱۰۰ ریست شد!</b>\nافتخارات و مدال‌ها حفظ شدند.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error resetting points: {e}")

async def set_live_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID):
        await update.message.reply_text("⛔️ این دستور فقط برای مالک و ادمین اصلی ربات مجاز است.")
        return

    chat = update.effective_chat
    if chat.type in ["group", "supergroup"]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('live_chat_id', ?)", (str(chat.id),))
            await db.commit()
        await update.message.reply_text(
            f"✅ <b>این گروه به عنوان گروه اختصاصی مسابقات و گزارش زنده ثبت شد!</b> 🏟🔥\n"
            f"شناسه: <code>{chat.id}</code>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("⚠️ این دستور باید در گروه ارسال شود.")

async def generate_pool_message_text(match, participants):
    home_name = match.get("home_team", "میزبان")
    away_name = match.get("away_team", "میهمان")
    time_str = format_iran_time(match.get("date"))

    text = (
        f"🔥 <b>استخر جایزه ویژه ۳۰۰ امتیازی مسابقه بزرگ!</b> 🎁\n"
        "────────────────────\n"
        f"⚽️ <b>{home_name}</b> 🆚 <b>{away_name}</b>\n"
        f"⏰ ساعت شروع: <code>{time_str}</code> (تهران)\n"
        f"💰 جایزه کل: <b>300 امتیاز</b> (تقسیم عادلانه بین برندگان)\n"
        "────────────────────\n"
        "👥 <b>لیست شرکت‌کنندگان:</b>\n"
    )

    home_pickers = [p[0] for p in participants if p[1] == "HOME"]
    draw_pickers = [p[0] for p in participants if p[1] == "DRAW"]
    away_pickers = [p[0] for p in participants if p[1] == "AWAY"]

    h_str = ", ".join([html.escape(n) for n in home_pickers[:5]]) if home_pickers else "هیچ‌کس"
    d_str = ", ".join([html.escape(n) for n in draw_pickers[:5]]) if draw_pickers else "هیچ‌کس"
    a_str = ", ".join([html.escape(n) for n in away_pickers[:5]]) if away_pickers else "هیچ‌کس"

    text += f"▫️ برد {home_name} ({len(home_pickers)} نفر): <i>{h_str}</i>\n"
    text += f"▫️ تساوی ({len(draw_pickers)} نفر): <i>{d_str}</i>\n"
    text += f"▫️ برد {away_name} ({len(away_pickers)} نفر): <i>{a_str}</i>\n"
    text += "\n👇 <b>پیش‌بینی خود را انتخاب کنید:</b>"
    return text

async def monitor_live_matches_and_banter(context: ContextTypes.DEFAULT_TYPE):
    target_chat_id = await get_live_chat_id()
    if not target_chat_id: return

    iran_now = get_iran_now()
    today_str = iran_now.strftime("%Y%m%d")

    matches = []
    for l_code in ACTIVE_MONITOR_LEAGUES:
        try:
            m_list = await provider.get_matches(today_str, league_code=l_code)
            if m_list: matches.extend(m_list)
        except Exception as e:
            logger.debug(f"Monitor error for {l_code}: {e}")

    unique_matches = {m["id"]: m for m in matches}
    utc_now = datetime.now(timezone.utc)

    for m_id, m in unique_matches.items():
        h_name = str(m.get("home_team", ""))
        a_name = str(m.get("away_team", ""))

        home_tracked = identify_tracked_team(h_name)
        away_tracked = identify_tracked_team(a_name)

        is_iran_match = "ایران" in h_name or "ایران" in a_name
        if not home_tracked and not away_tracked and not is_iran_match:
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
                "pool_msg_id": None,
                "banter_sent": False
            }
            TRACKED_LIVE_MATCHES[m_id] = track

        match_date_str = m.get("date")
        minutes_to_start = 9999
        if match_date_str:
            try:
                dt_match = datetime.fromisoformat(match_date_str.replace("Z", "+00:00"))
                minutes_to_start = (dt_match - utc_now).total_seconds() / 60
            except Exception: pass

        if 0 < minutes_to_start <= 45 and not track.get("pool_opened") and raw_status == "UPCOMING":
            track["pool_opened"] = True
            pool_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"⚪️ برد {h_name[:12]}", callback_data=f"pool_{m_id}_HOME"),
                    InlineKeyboardButton("🤝 تساوی", callback_data=f"pool_{m_id}_DRAW"),
                    InlineKeyboardButton(f"🔴 برد {a_name[:12]}", callback_data=f"pool_{m_id}_AWAY")
                ]
            ])
            msg_text = await generate_pool_message_text(m, [])
            try:
                sent = await context.bot.send_message(chat_id=target_chat_id, text=msg_text, reply_markup=pool_kb, parse_mode="HTML")
                track["pool_msg_id"] = sent.message_id
            except Exception as e:
                logger.error(f"Error opening pool: {e}")

        if raw_status == "LIVE" and not track.get("started_announced"):
            track["started_announced"] = True
            time_str = format_iran_time(m.get("date"))
            start_msg = (
                f"🚨 <b>سوت آغاز مسابقه حساس!</b> ⚽️\n"
                "────────────────────\n"
                f"🏟 <b>{h_name}</b> 🆚 <b>{a_name}</b>\n"
                f"⏰ شروع: <code>{time_str}</code> (تهران)\n"
                "▫️ استخر پیش‌بینی بسته شد. گزارش زنده آغاز گردید."
            )
            try:
                await context.bot.send_message(chat_id=target_chat_id, text=start_msg, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error sending start match: {e}")

        is_live = raw_status == "LIVE"
        is_finished = raw_status == "FINISHED"
        if (is_live or is_finished) and h_score is not None and a_score is not None:
            prev_h = track["home_score"]
            prev_a = track["away_score"]
            if h_score != prev_h or a_score != prev_a:
                track["home_score"] = h_score
                track["away_score"] = a_score
                goal_msg = (
                    f"⚽️🔥 <b>تغییر در نتیجه مسابقه! (گـُــل)</b>\n"
                    "────────────────────\n"
                    f"▫️ <b>{h_name} [{h_score}] - [{a_score}] {a_name}</b>"
                )
                try:
                    await context.bot.send_message(chat_id=target_chat_id, text=goal_msg, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Error sending goal: {e}")

        if is_finished and track["last_status"] != "FINISHED":
            track["last_status"] = "FINISHED"
            final_h = h_score if h_score is not None else track["home_score"]
            final_a = a_score if a_score is not None else track["away_score"]
            actual_outcome = "HOME" if final_h > final_a else ("AWAY" if final_a > final_h else "DRAW")

            winners_text = ""
            if track.get("pool_opened"):
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    async with db.execute("SELECT user_id, user_name FROM special_pool_predictions WHERE match_id = ? AND choice = ?", (m_id, actual_outcome)) as cur:
                        winners = await cur.fetchall()

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
                f"🏁 <b>سوت پایان مسابقه (Full Time)</b>\n"
                "────────────────────\n"
                f"نتیجه قطعی: <b>{h_name} [{final_h}] - [{final_a}] {a_name}</b>{winners_text}"
            )
            try:
                await context.bot.send_message(chat_id=target_chat_id, text=ft_msg, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error sending FT: {e}")

            if not track.get("banter_sent") and final_h != final_a:
                loser_key = None
                if final_h < final_a and home_tracked: loser_key = home_tracked
                elif final_a < final_h and away_tracked: loser_key = away_tracked

                if loser_key and loser_key in BANTER_TEXTS:
                    track["banter_sent"] = True
                    banter_msg = random.choice(BANTER_TEXTS[loser_key])
                    await asyncio.sleep(2)
                    try:
                        await context.bot.send_message(
                            chat_id=target_chat_id,
                            text=f"📢 <b>پیام ویژه هواداری:</b>\n{banter_msg}",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.error(f"Error sending banter: {e}")

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
            async with db.execute("""
                SELECT user_id, first_name, points FROM users
                WHERE user_id != ? ORDER BY points DESC LIMIT 4
            """, (ESCOBAR_AI_ID,)) as cur:
                top4 = await cur.fetchall()

            if top4 and len(top4) >= 1:
                p1 = top4[0]
                await db.execute("UPDATE users SET season_gold = season_gold + 1 WHERE user_id = ?", (p1[0],))
                p2 = top4[1] if len(top4) >= 2 else None
                if p2: await db.execute("UPDATE users SET season_silver = season_silver + 1 WHERE user_id = ?", (p2[0],))
                p3 = top4[2] if len(top4) >= 3 else None
                if p3: await db.execute("UPDATE users SET season_bronze = season_bronze + 1 WHERE user_id = ?", (p3[0],))
                p4 = top4[3] if len(top4) >= 4 else None
                if p4: await db.execute("UPDATE users SET season_fourth = season_fourth + 1 WHERE user_id = ?", (p4[0],))

                target_chat_id = await get_live_chat_id()
                if target_chat_id:
                    msg = (
                        f"🏆 <b>پایان رسمی رقابت‌های این سیزن!</b> 🔥\n"
                        "────────────────────\n"
                        "👑 <b>تالار قهرمانان ماه:</b>\n\n"
                        f"🥇 قهرمان سیزن: <b>{html.escape(p1[1])}</b> (رتبه ۱)\n"
                    )
                    if p2: msg += f"🥈 نایب قهرمان: <b>{html.escape(p2[1])}</b> (رتبه ۲)\n"
                    if p3: msg += f"🥉 مقام سوم: <b>{html.escape(p3[1])}</b> (رتبه ۳)\n"
                    if p4: msg += f"🎖 مقام چهارم: <b>{html.escape(p4[1])}</b> (رتبه ۴)\n"

                    msg += (
                        "\n⚡️ افتخارات در کارنامه بازیکنان ثبت شد!\n"
                        "🔄 <b>امتیازات برای سیزن جدید روی ۱۰۰ ریست شدند.</b>\n"
                        "رقابت سیزن جدید آغاز شد! 🔥"
                    )
                    try:
                        await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")
                    except Exception as e:
                        logger.error(f"Error sending season announcement: {e}")

                await db.execute("""
                    UPDATE users SET
                        points = 100,
                        duel_wins = 0,
                        penalty_wins = 0,
                        guess_wins = 0
                """)
                await db.execute("UPDATE bot_settings SET value = ? WHERE key = 'last_settled_month'", (cur_month_str,))
                await db.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT points, profile_level, profile_xp FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            pts = row[0] if row else 100
            lvl = row[1] if row and row[1] else 1
            xp = row[2] if row and row[2] else 0

    icon, tier = get_user_tier(pts)
    safe_name = html.escape(user.first_name)
    _, _, _, pct = calculate_level(xp)
    bar = render_xp_bar(pct, width=10)

    text = (
        f"⚽ <b>{safe_name}</b>\n\n"
        f"🏆 <b>{tier}</b>\n"
        f"<b>LVL {lvl}</b>\n"
        f"{bar} <code>{pct}%</code>\n\n"
        f"💰 <b>{pts:,} PTS</b>\n"
        f"────────────────────\n"
        f"به هاب هوشمند فوتبال خوش آمدید!\n"
        f"یکی از بخش‌های زیر را انتخاب کنید:"
    )
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb.get_main_menu())
    else:
        await update.message.reply_text(text, reply_markup=kb.get_main_menu(), parse_mode="HTML")

async def show_leaderboard_text(requesting_user_id: int = None) -> str:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT user_id, first_name, points, duel_wins FROM users WHERE user_id != ? ORDER BY points DESC, duel_wins DESC LIMIT 30",
            (ESCOBAR_AI_ID,)
        ) as cur:
            all_users = await cur.fetchall()

    text = "🏆 <b>جدول رده‌بندی سیزن</b> 🔥\n────────────────────\n\n"
    if not all_users:
        text += "هنوز کاربری ثبت نشده است.\n────────────────────"
        return text

    top_list = all_users[:15]
    remaining_list = all_users[15:25]

    for idx, u in enumerate(top_list, 1):
        name, pts, wins = u[1], max(0, u[2]), u[3]
        _, tier = get_user_tier(pts)
        display_name = format_bidi_name(name)

        if idx == 1: rank_prefix = "🥇 👑"
        elif idx == 2: rank_prefix = "🥈 👑"
        elif idx == 3: rank_prefix = "🥉 👑"
        else: rank_prefix = f"<code>{idx:02d}.</code>"

        text += f"{rank_prefix} <b>{display_name}</b> ({tier})\n    └ 💰 <code>{pts} PTS</code>  ▫️  ⚔️ <code>{wins}</code>\n\n"

    if remaining_list:
        text += "────────────────────\n\n"
        for idx, u in enumerate(remaining_list, 16):
            name, pts, wins = u[1], max(0, u[2]), u[3]
            _, tier = get_user_tier(pts)
            display_name = format_bidi_name(name)
            text += f"<code>{idx:02d}.</code> <b>{display_name}</b> ({tier})\n    └ 💰 <code>{pts} PTS</code>  ▫️  ⚔️ <code>{wins}</code>\n\n"

    text += "────────────────────"
    return text

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    text = await show_leaderboard_text(user_id)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
    else:
        await update.message.reply_text(text, parse_mode="HTML")

async def user_profile_handler(query, target_user=None):
    user = target_user or query.from_user
    user_id = user.id
    await ensure_user(user)

    team_info = await get_user_team_info(user_id)
    team_ovr = team_info["eff_ovr"] if team_info else 0
    team_chem = team_info["chem"] if team_info else 0

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("""
            SELECT points, profile_xp, profile_level, profile_correct, profile_answered,
                   duel_wins, penalty_wins, guess_wins,
                   season_gold, season_silver, season_bronze, season_fourth
            FROM users WHERE user_id = ?
        """, (user_id,)) as cur:
            row = await cur.fetchone()

        async with db.execute("SELECT COUNT(*) FROM user_cards WHERE user_id = ? AND is_in_lineup = 1", (user_id,)) as cur:
            lineup_count = (await cur.fetchone())[0]

    if not row: return

    pts, xp, level, correct, answered, d_wins, p_wins, g_wins, gold, silver, bronze, fourth = row
    pts = max(0, pts or 0)
    level, cur_xp, needed_xp, percent = calculate_level(xp or 0)
    accuracy = round((correct / answered) * 100) if answered else 0
    _, tier = get_user_tier(pts)
    safe_name = html.escape(user.first_name)
    bar = render_xp_bar(percent, width=10)

    medals_lines = []
    if gold: medals_lines.append(f"🥇 {gold} بار رتبه اول")
    if silver: medals_lines.append(f"🥈 {silver} بار رتبه دوم")
    if bronze: medals_lines.append(f"🥉 {bronze} بار رتبه سوم")
    if fourth: medals_lines.append(f"🎖 {fourth} بار رتبه چهارم")

    medals_text = ""
    if medals_lines:
        medals_text = "\n\n🏆 <b>افتخارات سیزن:</b>\n" + "  •  ".join(medals_lines)

    text = (
        f"⚽ <b>{safe_name}</b>\n\n"
        f"🏆 <b>{tier}</b>\n"
        f"<b>LVL {level}</b>\n"
        f"{bar} <code>{percent}%</code>\n\n"
        f"💰 <b>{pts:,} PTS</b>\n"
        f"🛡 <b>قدرت تیم کارت‌ها:</b> <code>{team_ovr} OVR</code> ({lineup_count}/5)\n"
        f"⚗️ <b>کمیستری تیم:</b> <code>{team_chem}%</code>\n"
        f"⚔️ <b>{d_wins or 0}</b> Wins\n"
        f"🧠 <b>{accuracy}%</b> Accuracy\n"
        f"🥅 <b>{p_wins or 0}</b> Penalty Wins\n"
        f"🕵️ <b>{g_wins or 0}</b> Guess Wins"
        f"{medals_text}"
    )

    if hasattr(query, "message") and query.message:
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())
    else:
        await query.reply_text(text, parse_mode="HTML")

async def daily_reward_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT last_daily_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                await update.effective_message.reply_text(
                    f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، پاداش روزانه امروز را دریافت کرده‌اید!\nامشب بعد از ساعت ۱۲ پاداش فردا فعال خواهد شد.",
                    parse_mode="HTML"
                )
                return

        reward = 25
        await db.execute("UPDATE users SET points = points + ?, last_daily_date = ? WHERE user_id = ?", (reward, today_str, user.id))
        await db.commit()

    await profile_add_xp(user.id, 20)
    await update.effective_message.reply_text(
        f"🎁 <b>پاداش روزانه واریز شد!</b>\n💰 <b>+{reward} امتیاز</b> دریافت کردید.",
        parse_mode="HTML"
    )

async def daily_shoot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT last_shoot_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                await update.effective_message.reply_text(
                    f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، شوت روزانه امروز را زده‌اید!\nامشب بعد از ساعت ۱۲ شانس شوت فردا فعال خواهد شد.",
                    parse_mode="HTML"
                )
                return

        await db.execute("UPDATE users SET last_shoot_date = ? WHERE user_id = ?", (today_str, user.id))
        await db.commit()

    msg = await update.effective_message.reply_dice(emoji="⚽")
    dice_val = msg.dice.value
    await asyncio.sleep(2.5)

    if dice_val in [3, 4, 5]:
        reward = 20
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, user.id))
            await db.commit()
        await profile_add_xp(user.id, 25)
        await update.effective_message.reply_text(
            f"⚽️🔥 <b>گـُـل شد! ضربه غیرقابل مهار!</b>\n💰 پاداش: <b>+{reward} امتیاز</b> دریافت کردید.",
            parse_mode="HTML"
        )
    else:
        await update.effective_message.reply_text(
            "🧤❌ <b>توپ گل نشد!</b> (برخورد به تیرک یا مهار دروازه‌بان)\nامشب بعد از ساعت ۱۲ دوباره شانس داری.",
            parse_mode="HTML"
        )

async def spin_wheel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT last_wheel_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                await update.effective_message.reply_text(
                    f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، امروز گردونه را چرخانده‌اید!\nامشب بعد از ساعت ۱۲ شانس مجدد فعال خواهد شد.",
                    parse_mode="HTML"
                )
                return

        await db.execute("UPDATE users SET last_wheel_date = ? WHERE user_id = ?", (today_str, user.id))
        await db.commit()

    prizes = [10, 15, 25, 40, 60, 100, 0]
    weights = [30, 25, 20, 12, 8, 3, 2]
    win = random.choices(prizes, weights=weights)[0]

    async with aiosqlite.connect(DATABASE_PATH) as db:
        if win > 0:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (win, user.id))
            await db.commit()

    if win > 0:
        await profile_add_xp(user.id, win)
        msg = f"🎡 <b>گردونه شانس متوقف شد!</b>\n🎉 تبریک، شما برنده <b>+{win} امتیاز</b> شدید!"
    else:
        msg = "🎡 <b>گردونه شانس متوقف شد!</b>\n❌ این‌بار پوچ بود! امشب بعد از ساعت ۱۲ دوباره شانس‌ات را امتحان کن."

    if update.callback_query: await update.callback_query.message.reply_text(msg, parse_mode="HTML")
    else: await update.effective_message.reply_text(msg, parse_mode="HTML")

async def guess_timeout_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    game = ACTIVE_GUESS_GAMES.get(chat_id)
    if game and game.get("is_active"):
        game["is_active"] = False
        main_name = game["names"][0]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⌛️ <b>مهلت ۳۰ ثانیه‌ای حدس بازیکن به پایان رسید!</b>\n"
                 f"👤 ستاره مورد نظر پرونده: <b>{main_name}</b> بود.",
            parse_mode="HTML"
        )

async def start_guess_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    chat_id = update.effective_chat.id
    user = update.effective_user
    await ensure_user(user)

    g_count = await get_guess_count_db(user.id)
    if g_count >= 3:
        await update.effective_message.reply_text(
            f"⛔️ <b>{html.escape(user.first_name)}</b> عزیز، شما سقف ۳ بار حدس بازیکن امروز خود را مصرف کرده‌اید!\n"
            "امشب بعد از ساعت ۱۲ سهمیه ۳تایی جدید شما آزاد خواهد شد.",
            parse_mode="HTML"
        )
        return

    game = ACTIVE_GUESS_GAMES.get(chat_id)
    if game and game.get("is_active"):
        challenger_name = html.escape(game.get("challenger_name", "کاربر"))
        await update.effective_message.reply_text(
            f"⚠️ یک پرونده هم‌اکنون برای <b>{challenger_name}</b> در این گروه در جریان است!\nلطفاً تا پایان مهلت ۳۰ ثانیه‌ای شکیبا باشید.",
            parse_mode="HTML"
        )
        return

    await increment_guess_count_db(user.id)
    current_attempt = g_count + 1

    p = get_next_guess_player()
    career_str = "\n".join([f"  {idx}. {club}" for idx, club in enumerate(p['career'], 1)])

    ACTIVE_GUESS_GAMES[chat_id] = {
        "names": [n.lower() for n in p["names"]],
        "reward": 15,
        "chat_id": chat_id,
        "challenger_id": user.id,
        "challenger_name": user.first_name,
        "is_active": True
    }

    text = (
        "🕵️‍♂️ <b>پرونده اطلاعاتی: ستاره فوتبال را شناسایی کنید!</b>\n"
        "────────────────────\n"
        f"🎯 بازیکن چالش: <b>{html.escape(user.first_name)}</b> (فرصت {current_attempt} از ۳)\n"
        f"⏱ مهلت پاسخ: <b>۳۰ ثانیه</b> ⏳\n"
        f"🌍 <b>ملیت:</b> {p['nation']}\n"
        f"📌 <b>پست تخصصی:</b> {p['pos']}\n\n"
        f"🏟 <b>مسیر باشگاهی:</b>\n{career_str}\n\n"
        f"⭐️ <b>سرنخ کلیدی:</b>\n{p['clue']}\n"
        "────────────────────\n"
        "💰 پاداش پاسخ صحیح: <b>+15 امتیاز</b> | <b>+80 XP</b>\n"
        "👇 نام بازیکن را در چت ارسال کنید:"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")
    schedule_timer(
        context, guess_timeout_job, 30,
        data={"chat_id": chat_id, "user_id": user.id},
        name=f"guess_timer_{chat_id}"
    )

# --- SUDDEN DEATH PENALTY ---

def render_shootout_board(shootout_id: str, shooter_name: str, shot_number: int = 1):
    text = (
        f"🥅 <b>نوبت ضربه پنالتی! (شوت {shot_number})</b> ⚽️\n"
        "────────────────────\n"
        f"👤 زننده ضربه: <b>{html.escape(shooter_name)}</b>\n"
        "گوشه شوت خود را انتخاب کنید:"
    )
    buttons = [
        [
            InlineKeyboardButton("↖️ بالا چپ", callback_data=f"sht_{shootout_id}_TL"),
            InlineKeyboardButton("⬆️ مرکز طاق", callback_data=f"sht_{shootout_id}_TC"),
            InlineKeyboardButton("↗️ بالا راست", callback_data=f"sht_{shootout_id}_TR")
        ],
        [
            InlineKeyboardButton("↙️ پایین چپ", callback_data=f"sht_{shootout_id}_BL"),
            InlineKeyboardButton("⬇️ زمینی مرکز", callback_data=f"sht_{shootout_id}_BC"),
            InlineKeyboardButton("↘️ پایین راست", callback_data=f"sht_{shootout_id}_BR")
        ]
    ]
    return text, InlineKeyboardMarkup(buttons)

async def trigger_penalty_shootout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "🥅 <b>نحوه شروع پنالتی:</b>\nروی پیام حریف ریپلای کنید و بنویسید: <code>پنالتی</code> یا <code>/penalty</code>",
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
        await update.message.reply_text(f"⛔️ <b>{html.escape(challenger.first_name)}</b> عزیز، شما سقف ۳ پنالتی امروز را زده‌اید!", parse_mode="HTML")
        return

    o_count = await get_penalty_count_db(opponent.id)
    if o_count >= 3:
        await update.message.reply_text(f"⛔️ حریف شما <b>{html.escape(opponent.first_name)}</b> امروز ۳ پنالتی خود را بازی کرده است!", parse_mode="HTML")
        return

    await ensure_user(challenger)
    await ensure_user(opponent)

    stake = 20
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (challenger.id, opponent.id)) as cur:
            balances = {row[0]: row[1] for row in await cur.fetchall()}

    c_pts = balances.get(challenger.id, 0)
    o_pts = balances.get(opponent.id, 0)

    if c_pts < stake:
        await update.message.reply_text(f"⛔️ حداقل موجودی برای پنالتی <b>{stake} PTS</b> است.\nموجودی شما: <code>{c_pts} PTS</code>", parse_mode="HTML")
        return
    if o_pts < stake:
        await update.message.reply_text(f"⛔️ <b>{html.escape(opponent.first_name)}</b> حداقل <b>{stake} PTS</b> موجودی ندارد.", parse_mode="HTML")
        return

    p_id = f"pen_{random.randint(10000, 99999)}"
    ACTIVE_SHOOTOUTS[p_id] = {
        "p1": {"id": challenger.id, "name": challenger.first_name, "shot": None},
        "p2": {"id": opponent.id, "name": opponent.first_name, "shot": None},
        "current_turn": challenger.id,
        "round": 1,
        "stake": stake,
        "chat_id": update.effective_chat.id,
        "message_id": None
    }

    p_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧤 قبول چالش پنالتی", callback_data=f"acp_{p_id}"),
         InlineKeyboardButton("❌ انصراف", callback_data=f"rjp_{p_id}")]
    ])

    c_name = html.escape(challenger.first_name)
    o_name = html.escape(opponent.first_name)

    text = (
        "🥅 <b>دوئل پنالتی (مرگ ناگهانی)!</b> ⚽️\n"
        "────────────────────\n"
        f"👤 شوت‌زن اول: <b>{c_name}</b> ({c_count + 1}/3)\n"
        f"👤 شوت‌زن دوم: <b>{o_name}</b> ({o_count + 1}/3)\n"
        f"💰 مبلغ شرط: <b>{stake} PTS</b>\n"
        "────────────────────\n"
        f"آیا <b>{o_name}</b> چالش پنالتی را می‌پذیرد؟"
    )
    sent_msg = await update.message.reply_text(text, reply_markup=p_kb, parse_mode="HTML")
    ACTIVE_SHOOTOUTS[p_id]["message_id"] = sent_msg.message_id

async def execute_penalty_kick(context: ContextTypes.DEFAULT_TYPE, shootout_id: str, choice: str):
    s = ACTIVE_SHOOTOUTS.get(shootout_id)
    if not s: return

    chat_id = s["chat_id"]
    msg_id = s["message_id"]

    gk_dive = random.choice(["TL", "TC", "TR", "BL", "BC", "BR"])
    is_goal = choice != gk_dive

    pos_names = {
        "TL": "گوشه بالا چپ", "TC": "مرکز طاق دروازه", "TR": "گوشه بالا راست",
        "BL": "زاویه پایین چپ", "BC": "مرکز زمینی", "BR": "زاویه پایین راست"
    }

    if s["p1"]["shot"] is None:
        s["p1"]["shot"] = is_goal
        s["current_turn"] = s["p2"]["id"]
        status_text = f"⚽️ <b>گل شد!</b> ({pos_names.get(choice, choice)})" if is_goal else f"🧤 <b>مهار شد!</b> (شیرجه به {pos_names.get(gk_dive, gk_dive)})"
        t, k = render_shootout_board(shootout_id, s["p2"]["name"], 2)
        await safe_edit_message(context.bot, f"👤 {s['p1']['name']}: {status_text}\n\n{t}", reply_markup=k, chat_id=chat_id, message_id=msg_id)
    else:
        s["p2"]["shot"] = is_goal
        p1_res, p2_res = s["p1"]["shot"], s["p2"]["shot"]

        if p1_res == p2_res:
            s["p1"]["shot"] = None
            s["p2"]["shot"] = None
            s["current_turn"] = s["p1"]["id"]
            s["round"] += 1
            status = "🔥 هر دو گل زدند!" if p1_res else "❌ هر دو خراب کردند!"
            t, k = render_shootout_board(shootout_id, s["p1"]["name"], 1)
            await safe_edit_message(
                context.bot,
                f"🏁 پایان راند {s['round']-1}: {status}\n⚠️ <b>مرگ ناگهانی!</b> راند جدید آغاز شد.\n\n{t}",
                reply_markup=k, chat_id=chat_id, message_id=msg_id
            )
        else:
            winner = s["p1"] if p1_res else s["p2"]
            loser = s["p2"] if p1_res else s["p1"]
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (s["stake"], winner["id"]))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (s["stake"], loser["id"]))
                await db.commit()

            await profile_record_penalty_win(winner["id"])
            res = (
                f"🏁 <b>پایان مسابقه (راند {s['round']})</b>\n────────────────────\n"
                f"👤 {s['p1']['name']}: {'⚽️' if p1_res else '❌'}\n"
                f"👤 {s['p2']['name']}: {'⚽️' if p2_res else '❌'}\n\n"
                f"🏆 برنده: <b>{winner['name']}</b> (+{s['stake']} امتیاز)"
            )
            await safe_edit_message(context.bot, res, chat_id=chat_id, message_id=msg_id)
            del ACTIVE_SHOOTOUTS[shootout_id]

# --- WEEKLY JACKPOT (5 MATCHES) ---

async def get_or_create_jackpot_round():
    iran_now = get_iran_now()
    week_id = f"JKW{iran_now.strftime('%U_%Y')}"

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT round_id, title, matches_json, pool_amount, is_active FROM jackpot_rounds WHERE round_id = ?", (week_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "round_id": row[0],
                    "title": row[1] or "جک‌پات طلایی هفته",
                    "matches": json.loads(row[2]),
                    "pool_amount": row[3] or 500,
                    "is_open": bool(row[4])
                }

    candidates = []
    for day in range(7):
        d_str = (iran_now + timedelta(days=day)).strftime("%Y%m%d")
        for l_code in ["eng.1", "esp.1", "ita.1", "uefa.champions", "irn.1"]:
            try:
                m_list = await provider.get_matches(d_str, league_code=l_code)
                for m in m_list:
                    if m.get("status") == "UPCOMING":
                        if not any(c["id"] == str(m["id"]) for c in candidates):
                            candidates.append({
                                "id": str(m["id"]),
                                "home": m["home_team"],
                                "away": m["away_team"],
                                "date": m.get("date")
                            })
                    if len(candidates) >= 5: break
            except Exception: continue
            if len(candidates) >= 5: break
        if len(candidates) >= 5: break

    if len(candidates) < 5:
        tmrw = iran_now + timedelta(days=1)
        tmrw_iso = tmrw.replace(hour=21, minute=0).astimezone(timezone.utc).isoformat()
        day_after_iso = (iran_now + timedelta(days=2)).replace(hour=22, minute=30).astimezone(timezone.utc).isoformat()
        sample_pool = [
            {"id": "fut_1", "home": "رئال مادرید", "away": "بارسلونا", "date": tmrw_iso},
            {"id": "fut_2", "home": "منچسترسیتی", "away": "لیورپول", "date": tmrw_iso},
            {"id": "fut_3", "home": "تیم ملی ایران", "away": "کره جنوبی", "date": tmrw_iso},
            {"id": "fut_4", "home": "فرانسه", "away": "ایتالیا", "date": day_after_iso},
            {"id": "fut_5", "home": "بایرن مونیخ", "away": "دورتموند", "date": day_after_iso}
        ]
        needed = 5 - len(candidates)
        candidates.extend(sample_pool[:needed])

    selected_5 = candidates[:5]
    now_str = iran_now.strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO jackpot_rounds (round_id, title, matches_json, pool_amount, is_active, is_settled, created_at)
            VALUES (?, ?, ?, 500, 1, 0, ?)
        """, (week_id, "جک‌پات طلایی هفته", json.dumps(selected_5, ensure_ascii=False), now_str))
        await db.commit()

    return {
        "round_id": week_id,
        "title": "جک‌پات طلایی هفته",
        "matches": selected_5,
        "pool_amount": 500,
        "is_open": True
    }

async def settle_jackpot_task(context: ContextTypes.DEFAULT_TYPE):
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT round_id, matches_json, pool_amount FROM jackpot_rounds WHERE is_settled = 0 AND is_active = 1") as cur:
                rounds = await cur.fetchall()

        for r_id, m_json, pool in rounds:
            matches = json.loads(m_json)
            results = {}
            all_finished = True

            for idx, m in enumerate(matches):
                m_id = m["id"]
                m_data = MATCH_CACHE.get(m_id)
                if not m_data or m_data.get("status") not in ["FINISHED", "FT", "POST"]:
                    all_finished = False
                    break
                h = int(m_data.get("home_score", 0))
                a = int(m_data.get("away_score", 0))
                results[str(idx)] = "HOME" if h > a else ("AWAY" if a > h else "DRAW")

            if all_finished and len(results) == 5:
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    async with db.execute("SELECT user_id, predictions_json, user_name FROM jackpot_combos WHERE round_id = ?", (r_id,)) as cur:
                        entries = await cur.fetchall()

                    winners = []
                    for uid, p_json, name in entries:
                        u_preds = json.loads(p_json)
                        if all(u_preds.get(k) == results.get(k) for k in results):
                            winners.append((uid, name))

                    if winners:
                        prize = pool // len(winners)
                        for w_id, _ in winners:
                            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (prize, w_id))
                        msg = (
                            f"🎰 <b>جک‌پات هفته تسویه شد!</b>\n"
                            f"🏆 برندگان ۵ از ۵:\n" +
                            "\n".join([f"👤 {w[1]} (+{prize} PTS)" for w in winners])
                        )
                        target_chat_id = await get_live_chat_id()
                        if target_chat_id:
                            await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")
                        elif ADMIN_ID:
                            await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="HTML")

                    await db.execute("UPDATE jackpot_rounds SET is_settled = 1, is_active = 0 WHERE round_id = ?", (r_id,))
                    await db.commit()
    except Exception as e:
        logger.error(f"Error in settle_jackpot_task: {e}")

async def jackpot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    round_data = await get_or_create_jackpot_round()
    if not round_data:
        msg_not_ready = "⏳ مسابقات جک‌پات این هفته هنوز آماده نشده است."
        if update.callback_query: await update.callback_query.answer(msg_not_ready, show_alert=True)
        else: await update.effective_message.reply_text(msg_not_ready)
        return

    round_id = round_data["round_id"]
    matches = round_data["matches"]
    pool = round_data.get("pool_amount", 500)
    is_open = round_data.get("is_open", True)

    user_combo = None
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT predictions_json FROM jackpot_combos WHERE user_id = ? AND round_id = ?", (user.id, round_id)) as cur:
            row = await cur.fetchone()
            if row: user_combo = json.loads(row[0])

    matches_text = ""
    for idx, m in enumerate(matches, 1):
        user_pick = ""
        if user_combo:
            p_val = user_combo.get(str(idx - 1), "—")
            p_label = "برد ۱" if p_val == "HOME" else ("تساوی X" if p_val == "DRAW" else ("برد ۲" if p_val == "AWAY" else "—"))
            user_pick = f"  ➔  <b>{p_label}</b>"
        time_display = format_iran_time(m.get("date"))
        matches_text += f"{idx}. <b>{m['home']}</b> 🆚 <b>{m['away']}</b> ({time_display}){user_pick}\n"

    buttons = []
    if user_combo:
        status_footer = "\n✅ <b>فرم جک‌پات شما برای این راند با موفقیت ثبت شده است!</b>"
        buttons.append([InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")])
    elif not is_open:
        status_footer = "\n⚠️ <b>مسابقات این راند آغاز شده و مهلت ثبت به پایان رسیده است.</b>"
        buttons.append([InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")])
    else:
        status_footer = "\n👇 برای شروع ثبت پیش‌بینی روی دکمه زیر کلیک کنید:"
        buttons.append([InlineKeyboardButton("📝 ثبت پیش‌بینی (۵ بازی)", callback_data=f"jk_start_{round_id}")])
        buttons.append([InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")])

    text = (
        f"🎰 <b>{round_data.get('title', 'جک‌پات طلایی هفته')}</b>\n"
        "────────────────────\n"
        f"💰 استخر جایزه: <b>{pool:,} PTS</b>\n"
        "▫️ شرط برد: پیش‌بینی دقیق نتیجه هر ۵ مسابقه\n"
        "────────────────────\n"
        "📋 <b>مسابقات این راند:</b>\n\n"
        f"{matches_text}"
        f"{status_footer}"
    )

    reply_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=reply_markup)
    else: await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

# --- PREDICTIONS HUB LOGIC ---

async def predictions_hub_handler(query):
    iran_now = get_iran_now()
    dates = [iran_now.strftime("%Y%m%d"), (iran_now + timedelta(days=1)).strftime("%Y%m%d")]

    candidate_matches = []
    for d in dates:
        for l_code in ACTIVE_MONITOR_LEAGUES:
            try:
                m_list = await provider.get_matches(d, league_code=l_code)
                for m in m_list:
                    MATCH_CACHE[m["id"]] = m
                    if m.get("status") == "UPCOMING":
                        candidate_matches.append(m)
            except Exception:
                pass

    seen = set()
    upcoming_list = []
    for m in candidate_matches:
        if m["id"] not in seen:
            seen.add(m["id"])
            upcoming_list.append(m)

    if not upcoming_list:
        await safe_edit_message(query, "⏳ مسابقه شروع‌نشده‌ای در دسترس نیست.", reply_markup=kb.get_back_button())
        return

    text = (
        "🎯 <b>تالار پیش‌بینی مسابقات فوتبال</b>\n"
        "────────────────────\n"
        "مسابقه مورد نظر خود را جهت ثبت نتیجه انتخاب کنید:\n"
        "💰 پاداش شرکت: <b>+10 امتیاز هدیه</b>\n"
        "────────────────────"
    )
    await safe_edit_message(query, text, reply_markup=kb.get_upcoming_matches_keyboard(upcoming_list))

# --- FC CARDS SYSTEM & CHEMISTRY & SELLING ---

RARITY_COLORS = {
    "ICON": "💎 آیکان افسانه‌ای",
    "ELITE": "🔥 ستاره الیت",
    "RARE": "⭐️ گلد ریر",
    "COMMON": "⚪️ معمولی"
}

def calculate_team_chemistry(cards):
    """
    محاسبه کمیستری تیم از ۰ تا ۱۰۰ بر پایه ملیت، باشگاه و کارت‌های آیکان
    """
    if len(cards) < 5: return 0
    chem = 35 # پایه کمیستری تیم ۵ نفره

    # کارت‌های آیکان وحشی (Wildcard): به کل تیم کمیستری می‌دهند
    icons = sum(1 for c in cards if c.get("rarity") == "ICON")
    chem += icons * 15

    # کمیستری ملیت
    nations = [c.get("nation") for c in cards if c.get("nation") and c.get("rarity") != "ICON"]
    n_counts = Counter(nations)
    for n, count in n_counts.items():
        if count >= 2:
            chem += (count - 1) * 18

    # کمیستری باشگاه
    clubs = [c.get("club") for c in cards if c.get("club") and c.get("rarity") != "ICON"]
    c_counts = Counter(clubs)
    for cl, count in c_counts.items():
        if count >= 2:
            chem += (count - 1) * 22

    return min(100, max(0, chem))

def generate_random_card_by_rarity(rarity_weights=None):
    if not rarity_weights:
        rarity_weights = {"COMMON": 65, "RARE": 25, "ELITE": 8, "ICON": 2}
    rarities = list(rarity_weights.keys())
    weights = list(rarity_weights.values())
    chosen_rarity = random.choices(rarities, weights=weights)[0]
    filtered = [c for c in FC_CATALOG if c["rarity"] == chosen_rarity]
    return random.choice(filtered)

async def market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT offers_json FROM daily_market WHERE user_id = ? AND date_str = ?", (user.id, today_str)) as cur:
            row = await cur.fetchone()

        if row:
            offers = json.loads(row[0])
        else:
            # ایجاد ۸ آفر گلچین‌شده در روز (۲ معمولی، ۳ ریر، ۲ الیت، ۱ آیکان)
            commons = random.sample([c for c in FC_CATALOG if c["rarity"] == "COMMON"], 2)
            rares = random.sample([c for c in FC_CATALOG if c["rarity"] == "RARE"], 3)
            elites = random.sample([c for c in FC_CATALOG if c["rarity"] == "ELITE"], 2)
            icons = random.sample([c for c in FC_CATALOG if c["rarity"] == "ICON"], 1)

            selected = commons + rares + elites + icons
            random.shuffle(selected)

            offers = []
            for i, c in enumerate(selected):
                if c["rarity"] == "COMMON": price = random.randint(120, 160)
                elif c["rarity"] == "RARE": price = random.randint(350, 480)
                elif c["rarity"] == "ELITE": price = random.randint(1100, 1400)
                else: price = random.randint(2800, 3400)

                offers.append({"idx": i, "card": c, "price": price, "bought": False})

            await db.execute("INSERT OR REPLACE INTO daily_market (user_id, date_str, offers_json) VALUES (?, ?, ?)",
                             (user.id, today_str, json.dumps(offers, ensure_ascii=False)))
            await db.commit()

        async with db.execute("SELECT points FROM users WHERE user_id = ?", (user.id,)) as cur:
            u_pts = (await cur.fetchone())[0]

    text = (
        "🛒 <b>مارکت بزرگ نقل‌وانتقالات روزانه (FC Market)</b>\n"
        "────────────────────\n"
        f"💰 موجودی شما: <b>{u_pts:,} PTS</b>\n"
        "⏰ مهلت اعتبار پیشنهادات: <b>تا ساعت ۲۴:۰۰ امشب</b>\n"
        "────────────────────\n\n"
    )

    buttons = []
    for o in offers:
        c = o["card"]
        tag = RARITY_COLORS.get(c["rarity"], c["rarity"])
        status = "✅ خریده شده" if o["bought"] else f"{o['price']} PTS"
        text += (
            f"▫️ <b>{c['name']}</b> ({c['pos']}) ➔ <b>{c['ovr']} OVR</b>\n"
            f"    └ 🌍 {c.get('nation', '')} | 🏟 {c.get('club', '')}\n"
            f"    └ رده: {tag} | قیمت: <b>{status}</b>\n\n"
        )
        if not o["bought"]:
            buttons.append([InlineKeyboardButton(f"خرید {c['name']} ({c['ovr']} OVR) - {o['price']} PTS", callback_data=f"buy_m_{o['idx']}")])

    buttons.append([InlineKeyboardButton("📦 باز کردن پک طلایی (Gold Pack: 250 PTS)", callback_data="buy_pack_gold")])
    buttons.append([InlineKeyboardButton("💰 فروش کارت‌های مازاد شما به ربات", callback_data="open_sell_menu")])
    buttons.append([InlineKeyboardButton("‹ بازگشت", callback_data="home")])

    kb_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)
    else:
        await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

async def sell_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی فروش مستقیم کارت‌ها به ربات با واریز آنی امتیاز"""
    user = update.effective_user
    await ensure_user(user)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT id, player_name, rating, position, rarity, is_in_lineup FROM user_cards WHERE user_id = ? ORDER BY rating DESC", (user.id,)) as cur:
            cards = await cur.fetchall()

    if not cards:
        text = "🎴 <b>کارت فعالی برای فروش ندارید!</b>"
        if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
        else: await update.message.reply_text(text, parse_mode="HTML")
        return

    text = (
        "💰 <b>فروشگاه بازخرید کارت‌ها (Quick Sell)</b>\n"
        "────────────────────\n"
        "هر کارتی را بفروشید، هزینه آن فوراً به حساب امتیازات شما اضافه می‌شود.\n"
        "<i>(نکته: کارت‌های حاضر در ترکیب اصلی علامت 🟢 دارند)</i>\n"
        "────────────────────\n\n"
    )

    buttons = []
    for cid, name, ovr, pos, rar, in_lineup in cards:
        price = SELL_PRICES.get(rar, 70)
        badge = "🟢 " if in_lineup else ""
        buttons.append([InlineKeyboardButton(f"فروش {badge}{name} ({ovr}) ➔ +{price} PTS", callback_data=f"sell_c_{cid}")])

    buttons.append([InlineKeyboardButton("‹ بازگشت به مارکت", callback_data="view_market")])
    buttons.append([InlineKeyboardButton("‹ منوی اصلی", callback_data="home")])

    kb_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)
    else: await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

async def my_cards_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT player_name, rating, position, rarity, is_in_lineup FROM user_cards WHERE user_id = ? ORDER BY rating DESC", (user.id,)) as cur:
            cards = await cur.fetchall()

    if not cards:
        text = "🎴 <b>کلکسیون کارت‌های شما خالی است!</b>\nاز بخش مارکت (<code>/market</code>) یا پک‌های شانسی کارت بخرید."
        if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
        else: await update.message.reply_text(text, parse_mode="HTML")
        return

    text = f"🎴 <b>کلکسیون کارت‌های {html.escape(user.first_name)}:</b>\n────────────────────\n\n"
    for name, ovr, pos, rar, in_lineup in cards:
        star = "🟢 [در ترکیب]" if in_lineup else "⚪️"
        c_info = FC_CATALOG_DICT.get(name, {})
        nat = c_info.get("nation", "")
        text += f"{star} <b>{name}</b> ({pos}) ➔ <b>{ovr} OVR</b> {nat} | {RARITY_COLORS.get(rar, rar)}\n"

    buttons = [
        [InlineKeyboardButton("⚡️ چیدن خودکار قوی‌ترین ترکیب ۵ نفره", callback_data="auto_lineup")],
        [InlineKeyboardButton("💰 فروش کارت‌ها به ربات", callback_data="open_sell_menu")],
        [InlineKeyboardButton("‹ بازگشت", callback_data="home")]
    ]
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=InlineKeyboardMarkup(buttons))
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

async def lineup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT player_name, rating, position FROM user_cards WHERE user_id = ? AND is_in_lineup = 1", (user.id,)) as cur:
            lineup = await cur.fetchall()

    enriched_cards = []
    positions = {"GK": None, "DEF": None, "MID1": None, "MID2": None, "FWD": None}
    mids = []
    for name, ovr, pos in lineup:
        c_info = FC_CATALOG_DICT.get(name, {"nation": "", "club": "", "rarity": "COMMON"})
        card_obj = {"name": name, "ovr": ovr, "pos": pos, "nation": c_info.get("nation"), "club": c_info.get("club"), "rarity": c_info.get("rarity")}
        enriched_cards.append(card_obj)

        if pos == "GK" and not positions["GK"]: positions["GK"] = card_obj
        elif pos == "DEF" and not positions["DEF"]: positions["DEF"] = card_obj
        elif pos == "FWD" and not positions["FWD"]: positions["FWD"] = card_obj
        elif pos == "MID": mids.append(card_obj)

    if len(mids) >= 1: positions["MID1"] = mids[0]
    if len(mids) >= 2: positions["MID2"] = mids[1]

    total_ovr = sum(p["ovr"] for p in positions.values() if p)
    count = sum(1 for p in positions.values() if p)
    avg_ovr = round(total_ovr / count, 1) if count > 0 else 0

    chem = calculate_team_chemistry(enriched_cards) if count == 5 else 0
    chem_boost = round((chem / 100.0) * 6.0, 1)
    effective_ovr = round(avg_ovr + chem_boost, 1)

    def p_line(p):
        if not p: return "—"
        return f"<b>{p['name']}</b> ({p['ovr']}) {p.get('nation', '')}"

    text = (
        f"🛡 <b>ترکیب ۵ نفره تیم: {html.escape(user.first_name)}</b>\n"
        "────────────────────\n"
        f"⭐️ <b>قدرت پایه تیمی:</b> <code>{avg_ovr} OVR</code>\n"
        f"⚗️ <b>کمیستری تیم:</b> <code>{chem}%</code> (بوست: <b>+{chem_boost}</b>)\n"
        f"⚡️ <b>قدرت نهایی تیم:</b> <code>{effective_ovr} OVR</code> 🔥\n\n"
        f"🧤 دروازه‌بان (GK): {p_line(positions['GK'])}\n"
        f"🛡 مدافع (DEF): {p_line(positions['DEF'])}\n"
        f"⚡️ هافبک ۱ (MID): {p_line(positions['MID1'])}\n"
        f"⚡️ هافبک ۲ (MID): {p_line(positions['MID2'])}\n"
        f"🎯 مهاجم (FWD): {p_line(positions['FWD'])}\n"
        "────────────────────\n"
        "<i>(نکته: کارت‌های هم‌ملیت، هم‌باشگاهی یا آیکان‌ها کمیستری و قدرت نهایی تیم را تا ۶ واحد بالا می‌برند!)</i>"
    )

    buttons = [
        [InlineKeyboardButton("⚡️ چیدن خودکار قوی‌ترین ترکیب", callback_data="auto_lineup")],
        [InlineKeyboardButton("🎴 کل کارت‌ها", callback_data="view_my_cards"),
         InlineKeyboardButton("💰 فروش کارت‌ها", callback_data="open_sell_menu")],
        [InlineKeyboardButton("‹ بازگشت", callback_data="home")]
    ]
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=InlineKeyboardMarkup(buttons))
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

async def auto_lineup_logic(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE user_cards SET is_in_lineup = 0 WHERE user_id = ?", (user_id,))
        for pos, count in [("GK", 1), ("DEF", 1), ("MID", 2), ("FWD", 1)]:
            async with db.execute("SELECT id FROM user_cards WHERE user_id = ? AND position = ? ORDER BY rating DESC LIMIT ?", (user_id, pos, count)) as cur:
                ids = [r[0] for r in await cur.fetchall()]
                for cid in ids:
                    await db.execute("UPDATE user_cards SET is_in_lineup = 1 WHERE id = ?", (cid,))
        await db.commit()

async def get_user_team_info(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT player_name, rating, position FROM user_cards WHERE user_id = ? AND is_in_lineup = 1", (user_id,)) as cur:
            cards = await cur.fetchall()

    if len(cards) < 5:
        await auto_lineup_logic(user_id)
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT player_name, rating, position FROM user_cards WHERE user_id = ? AND is_in_lineup = 1", (user_id,)) as cur:
                cards = await cur.fetchall()

    if len(cards) < 5: return None

    enriched = []
    for c in cards:
        c_info = FC_CATALOG_DICT.get(c[0], {"nation": "", "club": "", "rarity": "COMMON"})
        enriched.append({"name": c[0], "ovr": c[1], "pos": c[2], "nation": c_info.get("nation"), "club": c_info.get("club"), "rarity": c_info.get("rarity")})

    base_ovr = round(sum(c["ovr"] for c in enriched) / len(enriched), 1)
    chem = calculate_team_chemistry(enriched)
    chem_boost = round((chem / 100.0) * 6.0, 1)
    effective_ovr = round(base_ovr + chem_boost, 1)

    fwd = next((c["name"] for c in enriched if c["pos"] == "FWD"), "مهاجم")
    gk = next((c["name"] for c in enriched if c["pos"] == "GK"), "دروازه‌بان")
    return {"base_ovr": base_ovr, "chem": chem, "eff_ovr": effective_ovr, "fwd": fwd, "gk": gk, "cards": enriched}

async def trigger_card_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚽️ برای مسابقه کارت‌ها، روی پیام حریف ریپلای کن و بنویس:\n<code>مسابقه کارت</code> یا <code>/cardmatch</code>", parse_mode="HTML")
        return

    p1, p2 = update.effective_user, update.message.reply_to_message.from_user
    if p2.is_bot or p1.id == p2.id:
        await update.message.reply_text("⚠️ امکان مسابقه با این کاربر وجود ندارد.")
        return

    await ensure_user(p1)
    await ensure_user(p2)

    t1 = await get_user_team_info(p1.id)
    t2 = await get_user_team_info(p2.id)

    if not t1:
        await update.message.reply_text(f"⛔️ <b>{html.escape(p1.first_name)}</b> عزیز، ترکیب ۵ نفره کارت‌های شما تکمیل نیست!\nابتدا از <code>/market</code> کارت تهیه کرده و با <code>/lineup</code> بچینید.", parse_mode="HTML")
        return
    if not t2:
        await update.message.reply_text(f"⛔️ حریف شما <b>{html.escape(p2.first_name)}</b> ترکیب ۵ نفره کارت‌ها را کامل نکرده است.", parse_mode="HTML")
        return

    stake = 30
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (p1.id, p2.id)) as cur:
            balances = {r[0]: r[1] for r in await cur.fetchall()}

    if balances.get(p1.id, 0) < stake or balances.get(p2.id, 0) < stake:
        await update.message.reply_text(f"⛔️ هر دو بازیکن باید حداقل <b>{stake} PTS</b> موجودی داشته باشند.", parse_mode="HTML")
        return

    m_id = f"cm_{random.randint(10000, 99999)}"
    ACTIVE_CARD_MATCHES[m_id] = {
        "p1": {"id": p1.id, "name": p1.first_name, "team": t1, "score": 0},
        "p2": {"id": p2.id, "name": p2.first_name, "team": t2, "score": 0},
        "stake": stake,
        "chat_id": update.effective_chat.id,
        "msg_id": None
    }

    kb_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ قبول مسابقه کارت‌ها", callback_data=f"ac_cm_{m_id}"),
         InlineKeyboardButton("❌ لغو", callback_data=f"rj_cm_{m_id}")]
    ])

    text = (
        "🏟 <b>مسابقه بزرگ شبیه‌سازی کارت‌های FC!</b> 🔥\n"
        "────────────────────\n"
        f"🔵 تیم ۱: <b>{html.escape(p1.first_name)}</b> (⭐️ قدرت: <code>{t1['eff_ovr']}</code> | کمیستری: {t1['chem']}%)\n"
        f"🔴 تیم ۲: <b>{html.escape(p2.first_name)}</b> (⭐️ قدرت: <code>{t2['eff_ovr']}</code> | کمیستری: {t2['chem']}%)\n"
        f"💰 مبلغ شرط: <b>{stake} PTS</b> | مدت مسابقه: <b>۶۰ ثانیه</b>\n"
        "────────────────────\n"
        f"آیا <b>{html.escape(p2.first_name)}</b> مسابقه را می‌پذیرد؟"
    )
    sent = await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")
    ACTIVE_CARD_MATCHES[m_id]["msg_id"] = sent.message_id

async def run_live_card_match_simulation(context: ContextTypes.DEFAULT_TYPE, m_id: str):
    m = ACTIVE_CARD_MATCHES.get(m_id)
    if not m: return

    chat_id, msg_id = m["chat_id"], m["msg_id"]
    p1, p2 = m["p1"], m["p2"]
    ovr_diff = p1["team"]["eff_ovr"] - p2["team"]["eff_ovr"]

    await asyncio.sleep(15)
    t15 = (
        f"⏱ <b>دقیقه ۱۵ مسابقه:</b>\n"
        f"▫️ <b>{p1['name']} [{p1['score']}] - [{p2['score']}] {p2['name']}</b>\n"
        "────────────────────\n"
        f"⚔️ نبرد تاکتیکی هافبک‌ها در میانه زمین! کمیستری تیم‌ها نقشه بازی را تعیین می‌کند..."
    )
    await safe_edit_message(context.bot, t15, chat_id=chat_id, message_id=msg_id)

    await asyncio.sleep(15)
    p1_prob = 0.35 + (ovr_diff * 0.025)
    if random.random() < p1_prob:
        p1["score"] += 1
        event_40 = f"⚽️🔥 <b>گـُــل برای {p1['name']}!</b> شوت استثنایی <b>{p1['team']['fwd']}</b> به تور چسبید!"
    else:
        event_40 = f"🧤 مهار تماشایی توسط <b>{p2['team']['gk']}</b>! دروازه نجات یافت."

    t40 = (
        f"⏱ <b>دقیقه ۴۰ مسابقه:</b>\n"
        f"▫️ <b>{p1['name']} [{p1['score']}] - [{p2['score']}] {p2['name']}</b>\n"
        "────────────────────\n"
        f"{event_40}"
    )
    await safe_edit_message(context.bot, t40, chat_id=chat_id, message_id=msg_id)

    await asyncio.sleep(15)
    p2_prob = 0.35 - (ovr_diff * 0.025)
    if random.random() < p2_prob:
        p2["score"] += 1
        event_70 = f"⚽️🔥 <b>گـُــل برای {p2['name']}!</b> فرار فوق‌العاده <b>{p2['team']['fwd']}</b> به گل تبدیل شد!"
    else:
        event_70 = f"🛡 تکل نجات‌بخش خط دفاعی، مانع از گلزنی <b>{p2['name']}</b> شد."

    t70 = (
        f"⏱ <b>دقیقه ۷۰ مسابقه:</b>\n"
        f"▫️ <b>{p1['name']} [{p1['score']}] - [{p2['score']}] {p2['name']}</b>\n"
        "────────────────────\n"
        f"{event_70}"
    )
    await safe_edit_message(context.bot, t70, chat_id=chat_id, message_id=msg_id)

    await asyncio.sleep(15)
    s1, s2 = p1["score"], p2["score"]
    stake = m["stake"]

    res_footer = ""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if s1 > s2:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, p1["id"]))
            await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, p2["id"]))
            await profile_add_xp(p1["id"], 100)
            res_footer = f"🏆 برنده بازی: <b>{p1['name']}</b> (+{stake} امتیاز و +100 XP)"
        elif s2 > s1:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, p2["id"]))
            await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, p1["id"]))
            await profile_add_xp(p2["id"], 100)
            res_footer = f"🏆 برنده بازی: <b>{p2['name']}</b> (+{stake} امتیاز و +100 XP)"
        else:
            res_footer = "🤝 مسابقه با نتیجه مساوی به پایان رسید! هیچ امتیازی کسر نشد."
        await db.commit()

    t90 = (
        f"🏁 <b>سوت پایان مسابقه کارت‌ها (Full Time)</b>\n"
        "────────────────────\n"
        f"▫️ <b>{p1['name']} (⭐️ {p1['team']['eff_ovr']}) [{s1}] - [{s2}] (⭐️ {p2['team']['eff_ovr']}) {p2['name']}</b>\n"
        "────────────────────\n"
        f"{res_footer}"
    )
    await safe_edit_message(context.bot, t90, chat_id=chat_id, message_id=msg_id)
    ACTIVE_CARD_MATCHES.pop(m_id, None)

# --- TRIVIA DUELS (1v1 & 2v2) ---

async def trigger_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚔️ روی پیام حریف ریپلای کنید و بنویسید: <code>دوئل</code> یا <code>/duel</code>", parse_mode="HTML")
        return

    challenger, opponent = update.effective_user, update.message.reply_to_message.from_user
    if opponent.is_bot or challenger.id == opponent.id:
        await update.message.reply_text("⚠️ امکان دوئل با این کاربر نیست.")
        return

    await ensure_user(challenger)
    await ensure_user(opponent)

    stake = 25
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (challenger.id, opponent.id)) as cur:
            balances = {row[0]: row[1] for row in await cur.fetchall()}

    c_pts = balances.get(challenger.id, 0)
    o_pts = balances.get(opponent.id, 0)

    if c_pts < stake:
        await update.message.reply_text(f"⛔️ شما برای دوئل حداقل <b>{stake} PTS</b> لازم دارید.\nموجودی: <code>{c_pts} PTS</code>", parse_mode="HTML")
        return
    if o_pts < stake:
        await update.message.reply_text(f"⛔️ <b>{html.escape(opponent.first_name)}</b> برای دوئل حداقل <b>{stake} PTS</b> لازم دارد.", parse_mode="HTML")
        return

    duel_id = f"dl_{random.randint(10000, 99999)}"
    ACTIVE_DUELS[duel_id] = {
        "challenger": {"id": challenger.id, "name": challenger.first_name, "score": 0},
        "opponent": {"id": opponent.id, "name": opponent.first_name, "score": 0},
        "questions": get_random_duel_questions(3),
        "current_q": 0,
        "stake": stake,
        "answered": {},
        "chat_id": update.effective_chat.id,
        "message_id": None
    }

    duel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ قبول چالش دوئل", callback_data=f"acd_{duel_id}"),
         InlineKeyboardButton("❌ رد چالش", callback_data=f"rjd_{duel_id}")]
    ])

    c_name, o_name = html.escape(challenger.first_name), html.escape(opponent.first_name)
    text = (
        "⚔️ <b>میدان دوئل اطلاعات عمومی فوتبال!</b> 🔥\n"
        "────────────────────\n"
        f"👤 چلنجر: <b>{c_name}</b>  ▫️  هماورد: <b>{o_name}</b>\n"
        f"💰 جایزه رقابت: <b>+{stake} امتیاز</b> 🪙\n"
        "⏱ زمان هر سوال: <b>15 ثانیه</b> ⏳\n"
        "────────────────────\n"
        f"آیا <b>{o_name}</b> چالش را می‌پذیرد؟"
    )
    sent_msg = await update.message.reply_text(text, reply_markup=duel_kb, parse_mode="HTML")
    ACTIVE_DUELS[duel_id]["message_id"] = sent_msg.message_id

def render_duel_question_text(duel, q_data, q_idx):
    c_id, o_id = duel["challenger"]["id"], duel["opponent"]["id"]
    c_name, o_name = html.escape(duel["challenger"]["name"]), html.escape(duel["opponent"]["name"])
    c_status = "✅ پاسخ داده شد" if c_id in duel.get("answered", {}) else "⏳ در حال پاسخ..."
    o_status = "✅ پاسخ داده شد" if o_id in duel.get("answered", {}) else "⏳ در حال پاسخ..."

    return (
        f"❓ <b>سوال {q_idx + 1} از ۳:</b>\n"
        "────────────────────\n"
        f"📌 <b>{q_data['question']}</b>\n\n"
        "⏱ مهلت پاسخ: <b>۱۵ ثانیه</b>\n"
        "────────────────────\n"
        f"👤 {c_name}: {c_status}\n"
        f"👤 {o_name}: {o_status}"
    )

async def question_timeout_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    duel_id, q_idx = job_data["duel_id"], job_data["q_idx"]
    duel = ACTIVE_DUELS.get(duel_id)
    if duel and duel.get("current_q") == q_idx:
        duel["current_q"] += 1
        await proceed_duel(context, duel_id)

async def proceed_duel(context: ContextTypes.DEFAULT_TYPE, duel_id: str):
    duel = ACTIVE_DUELS.get(duel_id)
    if not duel: return

    chat_id, msg_id = duel["chat_id"], duel["message_id"]
    q_idx = duel["current_q"]

    if q_idx >= len(duel["questions"]):
        c_score, o_score = duel["challenger"]["score"], duel["opponent"]["score"]
        c_name, o_name = html.escape(duel["challenger"]["name"]), html.escape(duel["opponent"]["name"])
        c_id, o_id = duel["challenger"]["id"], duel["opponent"]["id"]
        stake = duel["stake"]

        res_text = (
            "🏁 <b>پایان دوئل اطلاعات عمومی!</b>\n"
            "────────────────────\n"
            f"👤 {c_name}: <code>{c_score}/3</code>\n"
            f"👤 {o_name}: <code>{o_score}/3</code>\n"
            "────────────────────\n"
        )

        async with aiosqlite.connect(DATABASE_PATH) as db:
            if c_score > o_score:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, c_id))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, o_id))
                res_text += f"🎉 تبریک به <b>{c_name}</b>! برنده <b>+{stake} امتیاز</b> شد."
                await profile_record_duel_win(c_id)
            elif o_score > c_score:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, o_id))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, c_id))
                res_text += f"🎉 تبریک به <b>{o_name}</b>! برنده <b>+{stake} امتیاز</b> شد."
                await profile_record_duel_win(o_id)
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
    schedule_timer(context, question_timeout_job, 15, data={"duel_id": duel_id, "q_idx": q_idx}, name=f"duel_timer_{duel_id}_{q_idx}")

async def trigger_team_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚔️ برای شروع بتل ۲ به ۲، روی پیام حریف ریپلای کن و بنویس:\n<code>بتل</code> یا <code>/battle</code>", parse_mode="HTML")
        return

    challenger, opponent = update.effective_user, update.message.reply_to_message.from_user
    if opponent.is_bot or challenger.id == opponent.id:
        await update.message.reply_text("⚠️ امکان بتل با این کاربر نیست.")
        return

    await ensure_user(challenger)
    await ensure_user(opponent)
    stake = 30

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (challenger.id, opponent.id)) as cur:
            balances = {int(uid): int(pts or 0) for uid, pts in await cur.fetchall()}

    if balances.get(challenger.id, 0) < stake or balances.get(opponent.id, 0) < stake:
        await update.message.reply_text(f"⛔️ هر بازیکن برای شروع بتل باید حداقل <b>{stake} PTS</b> داشته باشد.", parse_mode="HTML")
        return

    duel_id = f"tm_{random.randint(10000, 99999)}"
    ACTIVE_TEAM_DUELS[duel_id] = {
        "team1": [{"id": challenger.id, "name": challenger.first_name}],
        "team2": [{"id": opponent.id, "name": opponent.first_name}],
        "questions": get_random_duel_questions(3),
        "current_q": 0, "stake": stake, "answered": {},
        "scores": {challenger.id: 0, opponent.id: 0},
        "accepted": {challenger.id, opponent.id},
        "chat_id": update.effective_chat.id, "message_id": None,
        "started": False, "finished": False,
    }
    text = render_team_duel_lobby(ACTIVE_TEAM_DUELS[duel_id])
    kb_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ یار تیم ۱", callback_data=f"bt1_{duel_id}"),
         InlineKeyboardButton("➕ یار تیم ۲", callback_data=f"bt2_{duel_id}")],
        [InlineKeyboardButton("❌ لغو بتل", callback_data=f"r2d_{duel_id}")]
    ])
    sent = await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")
    ACTIVE_TEAM_DUELS[duel_id]["message_id"] = sent.message_id

def render_team_duel_lobby(duel):
    def player_line(team):
        lines = []
        for idx in range(2):
            if idx < len(team): lines.append(f"<b>{html.escape(team[idx]['name'])}</b>")
            else: lines.append("<i>[در انتظار یار...]</i>")
        return " & ".join(lines)

    return (
        "⚔️ <b>لابی نبرد ۲ به ۲ تیمی (بتل)!</b> 🔥\n"
        "────────────────────\n"
        f"🔵 <b>تیم ۱:</b> {player_line(duel['team1'])}\n"
        f"🔴 <b>تیم ۲:</b> {player_line(duel['team2'])}\n"
        "────────────────────\n"
        f"💰 ورودی هر نفر: <b>{duel['stake']} PTS</b> | جایزه تیم برنده: <b>+{duel['stake']} PTS</b>\n"
        "⏱ زمان هر سوال: <b>۱۵ ثانیه</b>\n\n"
        "👇 برای عضویت روی دکمه‌های زیر بزنید:"
    )

def render_team_duel_question_text(duel, q_data, q_idx):
    def player_status(team):
        parts = []
        for p in team:
            name = html.escape(p["name"])
            sc = duel["scores"].get(p["id"], 0)
            ans = "✅" if p["id"] in duel.get("answered", {}) else "⏳"
            parts.append(f"{name}: <code>{sc}</code> {ans}")
        return " | ".join(parts)

    return (
        f"⚔️ <b>بتل ۲ به ۲ تیمی (سوال {q_idx + 1} از ۳)</b>\n"
        "────────────────────\n"
        f"🔵 تیم ۱: {player_status(duel['team1'])}\n"
        f"🔴 تیم ۲: {player_status(duel['team2'])}\n"
        "────────────────────\n"
        f"❓ <b>{q_data['question']}</b>\n\n"
        "⏱ مهلت پاسخ: <b>۱۵ ثانیه</b>"
    )

async def team_duel_timeout_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    duel_id, q_idx = job_data["duel_id"], job_data["q_idx"]
    duel = ACTIVE_TEAM_DUELS.get(duel_id)
    if duel and duel["current_q"] == q_idx and not duel.get("finished"):
        duel["current_q"] += 1
        await proceed_team_duel(context, duel_id)

async def finish_team_duel(context: ContextTypes.DEFAULT_TYPE, duel_id: str):
    duel = ACTIVE_TEAM_DUELS.get(duel_id)
    if not duel or duel.get("finished"): return
    duel["finished"] = True
    chat_id, msg_id = duel["chat_id"], duel["message_id"]
    stake = duel["stake"]

    t1_score = sum(duel["scores"].get(p["id"], 0) for p in duel["team1"])
    t2_score = sum(duel["scores"].get(p["id"], 0) for p in duel["team2"])
    t1_names = " & ".join(f"<b>{html.escape(p['name'])}</b>" for p in duel["team1"])
    t2_names = " & ".join(f"<b>{html.escape(p['name'])}</b>" for p in duel["team2"])

    text = (
        "🏁 <b>پایان رقابت نبرد ۲ به ۲ تیمی!</b>\n"
        "────────────────────\n"
        f"🔵 تیم ۱ ({t1_names}): <b>{t1_score} امتیاز</b>\n"
        f"🔴 تیم ۲ ({t2_names}): <b>{t2_score} امتیاز</b>\n"
        "────────────────────\n"
    )

    async with aiosqlite.connect(DATABASE_PATH) as db:
        if t1_score > t2_score:
            text += f"🎉 تبریک! <b>تیم ۱</b> پیروز شد و هر بازیکن <b>+{stake} امتیاز</b> پاداش گرفت!"
            for p in duel["team1"]:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, p["id"]))
                await profile_record_duel_win(p["id"])
            for p in duel["team2"]:
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, p["id"]))
        elif t2_score > t1_score:
            text += f"🎉 تبریک! <b>تیم ۲</b> پیروز شد و هر بازیکن <b>+{stake} امتیاز</b> پاداش گرفت!"
            for p in duel["team2"]:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, p["id"]))
                await profile_record_duel_win(p["id"])
            for p in duel["team1"]:
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, p["id"]))
        else:
            text += "🤝 رقابت دو تیم مساوی شد! هیچ امتیازی کسر نگردید."
        await db.commit()

    del ACTIVE_TEAM_DUELS[duel_id]
    await safe_edit_message(context.bot, text, chat_id=chat_id, message_id=msg_id)

async def proceed_team_duel(context: ContextTypes.DEFAULT_TYPE, duel_id: str):
    duel = ACTIVE_TEAM_DUELS.get(duel_id)
    if not duel or duel.get("finished"): return
    q_idx = duel["current_q"]
    if q_idx >= len(duel["questions"]):
        await finish_team_duel(context, duel_id)
        return

    duel["answered"] = {}
    q_data = duel["questions"][q_idx]
    buttons = []
    for opt_idx, opt_text in enumerate(q_data["options"]):
        buttons.append([InlineKeyboardButton(f"🔘 {opt_text}", callback_data=f"at2_{duel_id}_{opt_idx}")])

    text = render_team_duel_question_text(duel, q_data, q_idx)
    await safe_edit_message(context.bot, text, reply_markup=InlineKeyboardMarkup(buttons), chat_id=duel["chat_id"], message_id=duel["message_id"])
    schedule_timer(context, team_duel_timeout_job, 15, data={"duel_id": duel_id, "q_idx": q_idx}, name=f"team_duel_timer_{duel_id}_{q_idx}")

async def cheat_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, chat = update.effective_user, update.effective_chat
    if chat is None or chat.type != "private" or str(user.id) != str(ADMIN_ID): return

    command = (update.effective_message.text or "").split()[0].split("@")[0].lower()
    if command == "/ch_on":
        CHEAT_MODE_USERS.add(user.id)
        await update.effective_message.reply_text("🟢 <b>Ch Mode اختصاصی فعال شد.</b> پاسخ‌ها همیشه صحیح ثبت می‌شوند.", parse_mode="HTML")
    elif command == "/ch_off":
        CHEAT_MODE_USERS.discard(user.id)
        await update.effective_message.reply_text("🔴 <b>Ch Mode غیرفعال شد.</b>", parse_mode="HTML")

# --- CALLBACK ROUTER ---

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data == "home":
        await start(update, context)

    elif data == "spin_wheel":
        await spin_wheel_cmd(update, context)

    # بخش برنامه مسابقات و جداول لیگ‌ها
    elif data == "select_matches_today":
        await safe_edit_message(query, "🔥 <b>لیگ مورد نظر برای مسابقات امروز:</b>", reply_markup=kb.get_matches_leagues_keyboard("today"))

    elif data == "select_matches_tomorrow":
        await safe_edit_message(query, "📅 <b>لیگ مورد نظر برای مسابقات فردا:</b>", reply_markup=kb.get_matches_leagues_keyboard("tmrw"))

    elif data == "select_standings_league":
        await safe_edit_message(query, "🏆 <b>جدول رده‌بندی لیگ مورد نظر:</b>", reply_markup=kb.get_standings_leagues_keyboard())

    elif data.startswith("today_") or data.startswith("tmrw_"):
        is_today = data.startswith("today_")
        league_code = data.split("_")[1]
        target_date = get_iran_now() if is_today else (get_iran_now() + timedelta(days=1))
        date_str = target_date.strftime("%Y%m%d")

        matches = await provider.get_matches(date_str, league_code=league_code)
        title = LEAGUE_TITLES.get(league_code, "مسابقات فوتبال")
        day_label = "امروز" if is_today else "فردا"

        if not matches:
            await safe_edit_message(
                query,
                f"⏳ مسابقه‌ای برای <b>{title}</b> در {day_label} یافت نشد.",
                reply_markup=kb.get_back_button()
            )
            return

        text = f"⚽️ <b>برنامه مسابقات {title} ({day_label}):</b>\n────────────────────\n\n"
        for m in matches[:10]:
            MATCH_CACHE[m["id"]] = m
            time_str = format_iran_time(m.get("date"))
            status = m.get("status", "UPCOMING")
            if status in ["LIVE", "IN_PLAY", "1H", "2H", "HT"]:
                badge = f"🔴 زنده [{m['home_score']} - {m['away_score']}]"
            elif status in ["FINISHED", "FT", "POST"]:
                badge = f"🏁 پایان [{m['home_score']} - {m['away_score']}]"
            else:
                badge = f"⏰ <code>{time_str}</code>"

            text += f"▫️ <b>{m['home_team']}</b> 🆚 <b>{m['away_team']}</b>\n    └ {badge}  •  {m.get('venue', 'ورزشگاه')}\n\n"

        text += "────────────────────"
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data.startswith("table_"):
        league_code = data.replace("table_", "")
        standings = await provider.get_standings(league_code)
        title = LEAGUE_TITLES.get(league_code, "جدول رده‌بندی")

        if not standings:
            await safe_edit_message(query, f"جدول رده‌بندی {title} در دسترس نیست.", reply_markup=kb.get_back_button())
            return

        text = f"🏆 <b>جدول رده‌بندی {title}</b>\n<pre>"
        text += "#  | Team          | P  | Pts\n---+---------------+----+----\n"
        for idx, s in enumerate(standings[:10], 1):
            team_str = s['team'][:13].ljust(13)
            p_str = str(s['p'])[:2].rjust(2)
            pts_str = str(s['pts'])[:3].rjust(3)
            text += f"{idx:<2} | {team_str} | {p_str} | {pts_str}\n"
        text += "</pre>\n<i>(P: تعداد بازی  |  Pts: مجموع امتیاز)</i>"
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    # تالار پیش‌بینی
    elif data == "predictions_hub":
        await predictions_hub_handler(query)

    elif data.startswith("select_pred_"):
        match_id = data.replace("select_pred_", "")
        m = MATCH_CACHE.get(match_id)
        if not m:
            await query.answer("اطلاعات این مسابقه منقضی شده است.", show_alert=True)
            return
        time_str = format_iran_time(m.get("date"))
        text = (
            f"🎯 <b>فرم ثبت پیش‌بینی:</b>\n"
            f"────────────────────\n"
            f"⚽️ <b>{m['home_team']}</b> 🆚 <b>{m['away_team']}</b>\n"
            f"⏰ شروع: <code>{time_str}</code> (تهران)\n"
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
                await profile_add_xp(user_id, 20)
                await safe_edit_message(query, "✅ <b>پیش‌بینی ثبت شد! (+10 امتیاز و +20 XP هدیه)</b>", reply_markup=kb.get_back_button())
            except Exception:
                await safe_edit_message(query, "⚠️ شما قبلاً این بازی را پیش‌بینی کرده‌اید.", reply_markup=kb.get_back_button())

    elif data.startswith("pool_"):
        parts = data.split("_")
        match_id, choice = parts[1], parts[2]
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

        await query.answer("✅ ثبت شد!", show_alert=False)
        m = MATCH_CACHE.get(match_id, {"home_team": "میزبان", "away_team": "میهمان", "date": None})
        new_text = await generate_pool_message_text(m, participants)
        await safe_edit_message(query, new_text, reply_markup=query.message.reply_markup)

    # بخش کارت‌ها و مارکت
    elif data == "view_market":
        await market_cmd(update, context)

    elif data == "open_sell_menu":
        await sell_menu_cmd(update, context)

    elif data == "view_my_cards":
        await my_cards_cmd(update, context)

    elif data == "view_lineup":
        await lineup_cmd(update, context)

    elif data == "auto_lineup":
        await auto_lineup_logic(uid)
        await query.answer("⚡️ قوی‌ترین ترکیب با کارت‌های موجود شما چیده شد!", show_alert=True)
        await lineup_cmd(update, context)

    elif data.startswith("buy_m_"):
        idx = int(data.split("_")[2])
        today_str = get_iran_now().strftime("%Y-%m-%d")

        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT offers_json FROM daily_market WHERE user_id = ? AND date_str = ?", (uid, today_str)) as cur:
                row = await cur.fetchone()
            if not row: return
            offers = json.loads(row[0])
            target = next((o for o in offers if o["idx"] == idx), None)
            if not target or target["bought"]:
                await query.answer("این کارت قبلاً خریداری شده است.", show_alert=True)
                return

            async with db.execute("SELECT points FROM users WHERE user_id = ?", (uid,)) as cur:
                pts = (await cur.fetchone())[0]

            if pts < target["price"]:
                await query.answer(f"امتیاز ناکافی! به {target['price']} PTS نیاز دارید.", show_alert=True)
                return

            await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (target["price"], uid))
            c = target["card"]
            await db.execute("""
                INSERT INTO user_cards (user_id, player_name, rating, position, rarity, acquired_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (uid, c["name"], c["ovr"], c["pos"], c["rarity"], today_str))

            target["bought"] = True
            await db.execute("UPDATE daily_market SET offers_json = ? WHERE user_id = ? AND date_str = ?", (json.dumps(offers, ensure_ascii=False), uid, today_str))
            await db.commit()

        await profile_add_xp(uid, 50)
        await query.answer(f"🎉 کارت {c['name']} ({c['ovr']} OVR) خریداری شد!", show_alert=True)
        await market_cmd(update, context)

    elif data.startswith("sell_c_"):
        card_id = int(data.split("_")[2])
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT player_name, rarity, is_in_lineup FROM user_cards WHERE id = ? AND user_id = ?", (card_id, uid)) as cur:
                row = await cur.fetchone()

            if not row:
                await query.answer("این کارت یافت نشد.", show_alert=True)
                return

            p_name, rar, in_lineup = row
            sell_price = SELL_PRICES.get(rar, 70)

            await db.execute("DELETE FROM user_cards WHERE id = ?", (card_id,))
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (sell_price, uid))
            await db.commit()

        if in_lineup:
            await auto_lineup_logic(uid)

        await query.answer(f"💰 کارت {p_name} با موفقیت به مبلغ {sell_price} PTS فروخته شد!", show_alert=True)
        await sell_menu_cmd(update, context)

    elif data == "buy_pack_gold":
        pack_price = 250
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT points FROM users WHERE user_id = ?", (uid,)) as cur:
                pts = (await cur.fetchone())[0]
            if pts < pack_price:
                await query.answer(f"امتیاز ناکافی! قیمت گلد پک {pack_price} PTS است.", show_alert=True)
                return

            await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (pack_price, uid))
            c = generate_random_card_by_rarity({"COMMON": 60, "RARE": 30, "ELITE": 8, "ICON": 2})
            today_str = get_iran_now().strftime("%Y-%m-%d")
            await db.execute("""
                INSERT INTO user_cards (user_id, player_name, rating, position, rarity, acquired_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (uid, c["name"], c["ovr"], c["pos"], c["rarity"], today_str))
            await db.commit()

        await profile_add_xp(uid, 40)
        pop_msg = f"📦 <b>پک باز شد!</b>\n⭐️ <b>{c['name']}</b> ({c['pos']})\nریتینگ: <b>{c['ovr']} OVR</b> {c.get('nation', '')} | {RARITY_COLORS.get(c['rarity'], c['rarity'])}"
        await query.message.reply_text(pop_msg, parse_mode="HTML")
        await market_cmd(update, context)

    # بخش جک‌پات
    elif data == "jackpot_hub":
        await jackpot_cmd(update, context)

    elif data.startswith("jk_start_"):
        rid = data.replace("jk_start_", "")
        USER_JACKPOT_DRAFTS[uid] = {"round_id": rid, "picks": {}}
        r_data = await get_or_create_jackpot_round()
        m = r_data["matches"][0]
        text = f"1️⃣ بازی اول:\n<b>{m['home']} ✕ {m['away']}</b>"
        kb_step = InlineKeyboardMarkup([
            [InlineKeyboardButton("برد میزبان", callback_data=f"jk_p_{rid}_0_HOME")],
            [InlineKeyboardButton("تساوی", callback_data=f"jk_p_{rid}_0_DRAW")],
            [InlineKeyboardButton("برد میهمان", callback_data=f"jk_p_{rid}_0_AWAY")]
        ])
        await safe_edit_message(query, text, reply_markup=kb_step)

    elif data.startswith("jk_p_"):
        p = data.split("_")
        rid, idx, choice = p[2], int(p[3]), p[4]
        if uid not in USER_JACKPOT_DRAFTS: return
        USER_JACKPOT_DRAFTS[uid]["picks"][str(idx)] = choice
        r_data = await get_or_create_jackpot_round()
        matches = r_data["matches"] if r_data else []

        if idx < 4 and idx + 1 < len(matches):
            m = matches[idx + 1]
            text = f"{idx + 2}️⃣ بازی بعدی:\n<b>{m['home']} ✕ {m['away']}</b>"
            kb_step = InlineKeyboardMarkup([
                [InlineKeyboardButton("برد ۱", callback_data=f"jk_p_{rid}_{idx+1}_HOME"),
                 InlineKeyboardButton("تساوی X", callback_data=f"jk_p_{rid}_{idx+1}_DRAW"),
                 InlineKeyboardButton("برد ۲", callback_data=f"jk_p_{rid}_{idx+1}_AWAY")]
            ])
            await safe_edit_message(query, text, reply_markup=kb_step)
        else:
            draft = USER_JACKPOT_DRAFTS.pop(uid, None)
            if draft:
                now_str = get_iran_now().strftime("%Y-%m-%d %H:%M")
                picks_json = json.dumps(draft["picks"], ensure_ascii=False)
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    await db.execute("""
                        INSERT OR REPLACE INTO jackpot_combos (user_id, user_name, round_id, predictions_json, status, created_at)
                        VALUES (?, ?, ?, ?, 'PENDING', ?)
                    """, (uid, query.from_user.first_name, rid, picks_json, now_str))
                    await db.commit()

                await profile_add_xp(uid, 30)
                await query.message.reply_text("✅ <b>فرم جک‌پات شما با موفقیت ثبت شد!</b>", parse_mode="HTML")

    # پنالتی
    elif data.startswith("acp_"):
        p_id = data.replace("acp_", "")
        s = ACTIVE_SHOOTOUTS.get(p_id)
        if s and uid == s["p2"]["id"]:
            await increment_penalty_count_db(s["p1"]["id"])
            await increment_penalty_count_db(s["p2"]["id"])
            t, k = render_shootout_board(p_id, s["p1"]["name"], 1)
            await safe_edit_message(query, t, reply_markup=k)

    elif data.startswith("rjp_"):
        p_id = data.replace("rjp_", "")
        s = ACTIVE_SHOOTOUTS.get(p_id)
        if s and uid in [s["p1"]["id"], s["p2"]["id"]]:
            del ACTIVE_SHOOTOUTS[p_id]
            await safe_edit_message(query, "❌ چالش پنالتی لغو شد.")

    elif data.startswith("sht_"):
        parts = data.split("_")
        p_id = f"{parts[1]}_{parts[2]}"
        choice = parts[3]
        if p_id in ACTIVE_SHOOTOUTS and uid == ACTIVE_SHOOTOUTS[p_id]["current_turn"]:
            await execute_penalty_kick(context, p_id, choice)

    # مسابقه کارت
    elif data.startswith("ac_cm_"):
        m_id = data.replace("ac_cm_", "")
        m = ACTIVE_CARD_MATCHES.get(m_id)
        if m and uid == m["p2"]["id"]:
            await safe_edit_message(query, "⚽️ <b>مسابقه کارت‌ها آغاز شد! در حال شبیه‌سازی زنده...</b>")
            asyncio.create_task(run_live_card_match_simulation(context, m_id))

    elif data.startswith("rj_cm_"):
        m_id = data.replace("rj_cm_", "")
        if m_id in ACTIVE_CARD_MATCHES:
            del ACTIVE_CARD_MATCHES[m_id]
            await safe_edit_message(query, "❌ مسابقه کارت‌ها لغو شد.")

    # دوئل
    elif data.startswith("acd_"):
        duel_id = data.replace("acd_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if duel and uid == duel["opponent"]["id"]:
            await proceed_duel(context, duel_id)

    elif data.startswith("rjd_"):
        duel_id = data.replace("rjd_", "")
        if duel_id in ACTIVE_DUELS:
            del ACTIVE_DUELS[duel_id]
            await safe_edit_message(query, "❌ چالش دوئل لغو گردید.")

    elif data.startswith("ad_"):
        parts = data.split("_")
        duel_id, opt_idx = f"{parts[1]}_{parts[2]}", int(parts[3])
        duel = ACTIVE_DUELS.get(duel_id)
        if not duel or uid not in [duel["challenger"]["id"], duel["opponent"]["id"]] or uid in duel["answered"]:
            return

        q_idx = duel["current_q"]
        if q_idx >= len(duel["questions"]): return
        q_data = duel["questions"][q_idx]

        is_correct = (opt_idx == q_data["correct_idx"])
        if uid == int(ADMIN_ID) and uid in CHEAT_MODE_USERS: is_correct = True

        duel["answered"][uid] = is_correct
        await profile_record_answer(uid, is_correct)

        if is_correct:
            if uid == duel["challenger"]["id"]: duel["challenger"]["score"] += 1
            else: duel["opponent"]["score"] += 1

        await safe_edit_message(
            context.bot,
            render_duel_question_text(duel, q_data, q_idx),
            reply_markup=query.message.reply_markup,
            chat_id=duel["chat_id"],
            message_id=duel["message_id"]
        )

        if len(duel["answered"]) == 2:
            cancel_timer(context, f"duel_timer_{duel_id}_{q_idx}")
            duel["current_q"] += 1
            await proceed_duel(context, duel_id)

    # بتل تیمی
    elif data.startswith("bt1_") or data.startswith("bt2_"):
        duel_id = data.split("_", 1)[1]
        team_num = 1 if data.startswith("bt1_") else 2
        duel = ACTIVE_TEAM_DUELS.get(duel_id)
        if not duel or duel.get("started"): return

        user = query.from_user
        await ensure_user(user)
        target_team = duel["team1"] if team_num == 1 else duel["team2"]
        other_team = duel["team2"] if team_num == 1 else duel["team1"]

        if any(p["id"] == user.id for p in target_team): return
        other_team[:] = [p for p in other_team if p["id"] != user.id]
        if len(target_team) >= 2: return

        target_team.append({"id": user.id, "name": user.first_name})
        duel["scores"][user.id] = 0
        duel["accepted"].add(user.id)

        if len(duel["team1"]) == 2 and len(duel["team2"]) == 2:
            duel["started"] = True
            await proceed_team_duel(context, duel_id)
        else:
            await safe_edit_message(query, render_team_duel_lobby(duel), reply_markup=query.message.reply_markup)

    elif data.startswith("r2d_"):
        duel_id = data.replace("r2d_", "")
        if duel_id in ACTIVE_TEAM_DUELS:
            del ACTIVE_TEAM_DUELS[duel_id]
            await safe_edit_message(query, "❌ بتل تیمی لغو شد.")

    elif data.startswith("at2_"):
        parts = data.split("_")
        duel_id, opt_idx = f"{parts[1]}_{parts[2]}", int(parts[3])
        duel = ACTIVE_TEAM_DUELS.get(duel_id)
        if not duel or duel.get("finished"): return

        all_players = [p["id"] for p in duel["team1"] + duel["team2"]]
        if uid not in all_players or uid in duel.get("answered", {}): return

        q_idx = duel["current_q"]
        if q_idx >= len(duel["questions"]): return
        q_data = duel["questions"][q_idx]

        is_correct = (opt_idx == q_data["correct_idx"])
        if uid == int(ADMIN_ID) and uid in CHEAT_MODE_USERS: is_correct = True

        duel["answered"][uid] = is_correct
        await profile_record_answer(uid, is_correct)
        if is_correct: duel["scores"][uid] = duel["scores"].get(uid, 0) + 1

        await safe_edit_message(
            context.bot,
            render_team_duel_question_text(duel, q_data, q_idx),
            reply_markup=query.message.reply_markup,
            chat_id=duel["chat_id"],
            message_id=duel["message_id"]
        )

        if len(duel["answered"]) == len(all_players):
            cancel_timer(context, f"team_duel_timer_{duel_id}_{q_idx}")
            duel["current_q"] += 1
            await proceed_team_duel(context, duel_id)

    elif data == "user_profile":
        await user_profile_handler(query)

    elif data == "leaderboard_hub":
        text = await show_leaderboard_text(query.from_user.id)
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.strip() if update.message and update.message.text else ""
    if not msg: return

    chat_id = update.effective_chat.id

    game = ACTIVE_GUESS_GAMES.get(chat_id)
    if game and game.get("is_active"):
        user_ans = msg.lower()
        if any(alias in user_ans for alias in game["names"]):
            winner = update.effective_user
            reward = game["reward"]
            game["is_active"] = False

            cancel_timer(context, f"guess_timer_{chat_id}")
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, winner.id))
                await db.commit()
            await profile_record_guess_win(winner.id)

            main_name = game["names"][0]
            await update.message.reply_text(
                f"🎉🔥 <b>پاسخ صحیح!</b>\n👤 ستاره: <b>{main_name}</b>\n🏆 برنده: <b>{html.escape(winner.first_name)}</b> (+{reward} امتیاز و +80 XP)",
                parse_mode="HTML"
            )
            return

    if msg.lower() in ["اطلاعات", "info", "پروفایل", "stats"] or msg.lower().startswith(("/info", "اطلاعات")):
        target_user = update.effective_user
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
        await user_profile_handler(update.message, target_user=target_user)
        return

    if msg in ["دوئل", "duel", "چالش"]:
        await trigger_duel(update, context)
    elif msg in ["پنالتی", "پنالتی کشی", "penalty"]:
        await trigger_penalty_shootout(update, context)
    elif msg in ["مسابقه کارت", "کارت مچ", "cardmatch", "کارت"]:
        await trigger_card_match(update, context)
    elif msg in ["مارکت", "market", "خرید کارت"]:
        await market_cmd(update, context)
    elif msg in ["فروش", "فروش کارت", "sell"]:
        await sell_menu_cmd(update, context)
    elif msg in ["کارتها", "کارتهای من", "mycards"]:
        await my_cards_cmd(update, context)
    elif msg in ["ترکیب", "لاین اپ", "lineup"]:
        await lineup_cmd(update, context)
    elif msg in ["شوت", "گل", "shoot"]:
        await daily_shoot_cmd(update, context)
    elif msg in ["جایزه", "روزانه", "daily"]:
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

async def post_init(application: Application):
    await init_db()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                user_id INTEGER,
                match_id TEXT,
                outcome_choice TEXT,
                predicted_home INTEGER,
                predicted_away INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, match_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS special_pool_predictions (
                match_id TEXT,
                user_id INTEGER,
                user_name TEXT,
                choice TEXT,
                settled INTEGER DEFAULT 0,
                PRIMARY KEY (match_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jackpot_rounds (
                round_id TEXT PRIMARY KEY,
                title TEXT,
                matches_json TEXT,
                pool_amount INTEGER DEFAULT 500,
                is_active INTEGER DEFAULT 1,
                is_settled INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jackpot_combos (
                user_id INTEGER,
                user_name TEXT,
                round_id TEXT,
                predictions_json TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at TEXT,
                PRIMARY KEY (user_id, round_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                player_name TEXT,
                rating INTEGER,
                position TEXT,
                rarity TEXT,
                is_in_lineup INTEGER DEFAULT 0,
                acquired_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_market (
                user_id INTEGER,
                date_str TEXT,
                offers_json TEXT,
                PRIMARY KEY (user_id, date_str)
            )
        """)
        await db.commit()

    await ensure_escobar_ai()
    if getattr(application, "job_queue", None):
        application.job_queue.run_repeating(monitor_live_matches_and_banter, interval=90, first=5)
        application.job_queue.run_repeating(check_and_settle_monthly_season, interval=3600, first=15)
        application.job_queue.run_repeating(settle_jackpot_task, interval=7200, first=60)
        logger.info("PTB JobQueue is active.")
    else:
        logger.warning("PTB JobQueue is None. Falling back to native asyncio background tasks.")
        asyncio.create_task(run_repeating_task(monitor_live_matches_and_banter, application, 90, 5))
        asyncio.create_task(run_repeating_task(check_and_settle_monthly_season, application, 3600, 15))
        asyncio.create_task(run_repeating_task(settle_jackpot_task, application, 7200, 60))

def main():
    t = threading.Thread(target=start_health_server, daemon=True)
    t.start()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ranking", leaderboard_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CommandHandler("duel", trigger_duel))
    app.add_handler(CommandHandler("battle", trigger_team_duel))
    app.add_handler(CommandHandler("penalty", trigger_penalty_shootout))
    app.add_handler(CommandHandler("cardmatch", trigger_card_match))
    app.add_handler(CommandHandler("market", market_cmd))
    app.add_handler(CommandHandler("sell", sell_menu_cmd))
    app.add_handler(CommandHandler("pack", lambda u, c: market_cmd(u, c)))
    app.add_handler(CommandHandler("mycards", my_cards_cmd))
    app.add_handler(CommandHandler("lineup", lineup_cmd))
    app.add_handler(CommandHandler("shoot", daily_shoot_cmd))
    app.add_handler(CommandHandler("daily", daily_reward_cmd))
    app.add_handler(CommandHandler("guess", start_guess_game))
    app.add_handler(CommandHandler("wheel", spin_wheel_cmd))
    app.add_handler(CommandHandler("jackpot", jackpot_cmd))
    app.add_handler(CommandHandler("add", add_points_cmd))
    app.add_handler(CommandHandler("backup", backup_db_cmd))
    app.add_handler(CommandHandler("restore", restore_db_cmd))
    app.add_handler(CommandHandler("reset_points", reset_points_cmd))
    app.add_handler(CommandHandler("set_live", set_live_group))
    app.add_handler(CommandHandler("ch_on", cheat_mode_command))
    app.add_handler(CommandHandler("ch_off", cheat_mode_command))
    app.add_handler(CommandHandler("info", lambda u, c: handle_group_messages(u, c)))

    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.Regex(r"^\s*بتل\s*$"), trigger_team_duel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_messages))

    logger.info("Football Hub Bot successfully initialized with Expanded Catalog & Chemistry!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
