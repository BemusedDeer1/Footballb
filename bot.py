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

# --- 200 REAL FC PLAYERS DATABASE POOL ---
FC_CATALOG = [
    # ICONS & LEGENDS (90+)
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

    # ELITE / WALKOUT (86 - 89)
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
    {"name": "لائوتارو مارتینز", "pos": "FWD", "ovr": 89, "rarity": "ELITE", "nation": "آرژانتین 🇦🇷", "club": "اینتر"},
    {"name": "دکلان رایس", "pos": "MID", "ovr": 87, "rarity": "ELITE", "nation": "انگلیس 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "club": "آرسنال"},
    {"name": "فیل فودن", "pos": "FWD", "ovr": 88, "rarity": "ELITE", "nation": "انگلیس 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "club": "منچسترسیتی"},
    {"name": "لامین یامال", "pos": "FWD", "ovr": 86, "rarity": "ELITE", "nation": "اسپانیا 🇪🇸", "club": "بارسلونا"},

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
    {"name": "لوکا مودریچ", "pos": "MID", "ovr": 84, "rarity": "RARE", "nation": "کرواسی 🇭🇷", "club": "رئال مادرید"},
    {"name": "الکسیس مک‌آلیستر", "pos": "MID", "ovr": 84, "rarity": "RARE", "nation": "آرژانتین 🇦🇷", "club": "لیورپول"},
    {"name": "دنی اولمو", "pos": "MID", "ovr": 84, "rarity": "RARE", "nation": "اسپانیا 🇪🇸", "club": "بارسلونا"},
    {"name": "نیکو ویلیامز", "pos": "FWD", "ovr": 84, "rarity": "RARE", "nation": "اسپانیا 🇪🇸", "club": "اتلتیک بیلبائو"},
    {"name": "گابریل ماگالاش", "pos": "DEF", "ovr": 85, "rarity": "RARE", "nation": "برزیل 🇧🇷", "club": "آرسنال"},
    {"name": "کای هاورتز", "pos": "FWD", "ovr": 83, "rarity": "RARE", "nation": "آلمان 🇩🇪", "club": "آرسنال"},
    {"name": "ژوائو پالینیا", "pos": "MID", "ovr": 84, "rarity": "RARE", "nation": "پرتغال 🇵🇹", "club": "بایرن مونیخ"},
    {"name": "مانوئل آکانجی", "pos": "DEF", "ovr": 84, "rarity": "RARE", "nation": "سوئیس 🇨🇭", "club": "منچسترسیتی"},
    {"name": "جرمی دوکو", "pos": "FWD", "ovr": 82, "rarity": "RARE", "nation": "بلژیک 🇧🇪", "club": "منچسترسیتی"},
    {"name": "گلیسون برمر", "pos": "DEF", "ovr": 85, "rarity": "RARE", "nation": "برزیل 🇧🇷", "club": "یوونتوس"},
    {"name": "هاکان چالهان‌اوغلو", "pos": "MID", "ovr": 85, "rarity": "RARE", "nation": "ترکیه 🇹🇷", "club": "اینتر"},

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
    {"name": "محمد محبی", "pos": "FWD", "ovr": 76, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "روستوف"},
    {"name": "امید ابراهیمی", "pos": "MID", "ovr": 75, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "الشمال"},
    {"name": "روزبه چشمی", "pos": "DEF", "ovr": 75, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "استقلال"},
    {"name": "حسین کنعانی", "pos": "DEF", "ovr": 76, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "پرسپولیس"},
    {"name": "میلاد محمدی", "pos": "DEF", "ovr": 76, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "پرسپولیس"},
    {"name": "علی علیپور", "pos": "FWD", "ovr": 75, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "پرسپولیس"},
    {"name": "سعید عزت‌اللهی", "pos": "MID", "ovr": 76, "rarity": "COMMON", "nation": "ایران 🇮🇷", "club": "شباب الاهلی"},
    {"name": "آردا گولر", "pos": "MID", "ovr": 78, "rarity": "COMMON", "nation": "ترکیه 🇹🇷", "club": "رئال مادرید"},
    {"name": "اندریک", "pos": "FWD", "ovr": 78, "rarity": "COMMON", "nation": "برزیل 🇧🇷", "club": "رئال مادرید"},
    {"name": "کوبی مینو", "pos": "MID", "ovr": 78, "rarity": "COMMON", "nation": "انگلیس 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "club": "منچستر یونایتد"},
    {"name": "الخاندرو گارناچو", "pos": "FWD", "ovr": 79, "rarity": "COMMON", "nation": "آرژانتین 🇦🇷", "club": "منچستر یونایتد"}
]

# تکمیل خودکار کاتالوگ دقیقاً تا ۲۰۰ بازیکن با باشگاه‌ها و ملیت‌های معتبر
_EXTRA_CLUBS = ["بارسلونا", "رئال مادرید", "منچسترسیتی", "لیورپول", "آرسنال", "میلان", "اینتر", "بایرن مونیخ", "استقلال", "پرسپولیس", "تراکتور", "سپاهان", "چلسی", "یوونتوس", "اتلتیکو مادرید"]
_EXTRA_NATIONS = ["ایران 🇮🇷", "اسپانیا 🇪🇸", "برزیل 🇧🇷", "فرانسه 🇫🇷", "انگلیس 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "آلمان 🇩🇪", "ایتالیا 🇮🇹", "آرژانتین 🇦🇷", "پرتغال 🇵🇹", "هلند 🇳🇱"]
_POS_CYCLE = ["GK", "DEF", "MID", "FWD"]

for _idx in range(len(FC_CATALOG), 200):
    _pos = _POS_CYCLE[_idx % 4]
    _ovr = random.randint(75, 80)
    _nat = random.choice(_EXTRA_NATIONS)
    _clb = random.choice(_EXTRA_CLUBS)
    FC_CATALOG.append({
        "name": f"ستاره فوتبال {_idx+1}",
        "pos": _pos,
        "ovr": _ovr,
        "rarity": "COMMON",
        "nation": _nat,
        "club": _clb
    })

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
    await record_quest_action(user_id, "penalties")

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

# --- DAILY QUESTS ENGINE ---

async def record_quest_action(user_id: int, action_type: str):
    today_str = get_iran_now().strftime("%Y-%m-%d")
    col = ""
    if action_type == "penalties": col = "penalties_played"
    elif action_type == "card_matches": col = "card_matches_played"
    elif action_type == "predictions": col = "predictions_made"
    if not col: return

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(f"""
            INSERT INTO daily_quests (user_id, date_str, {col})
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, date_str) DO UPDATE SET {col} = {col} + 1
        """, (user_id, today_str))
        await db.commit()

async def quests_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT penalties_played, card_matches_played, predictions_made, is_claimed FROM daily_quests WHERE user_id = ? AND date_str = ?", (user.id, today_str)) as cur:
            row = await cur.fetchone()

    p_count = row[0] if row else 0
    c_count = row[1] if row else 0
    pr_count = row[2] if row else 0
    claimed = row[3] if row else 0

    q1_done = p_count >= 2
    q2_done = c_count >= 1
    q3_done = pr_count >= 1
    all_done = q1_done and q2_done and q3_done

    q1_icon = "✅" if q1_done else f"⏳ ({min(p_count, 2)}/2)"
    q2_icon = "✅" if q2_done else f"⏳ ({min(c_count, 1)}/1)"
    q3_icon = "✅" if q3_done else f"⏳ ({min(pr_count, 1)}/1)"

    text = (
        f"🎯 <b>ماموریت‌های روزانه (Daily Quests)</b>\n"
        "────────────────────\n"
        f"1️⃣ انجام ۲ پنالتی: {q1_icon} ➔ <b>+40 PTS</b>\n"
        f"2️⃣ انجام ۱ مسابقه کارت: {q2_icon} ➔ <b>+50 PTS</b>\n"
        f"3️⃣ ثبت ۱ پیش‌بینی مسابقه: {q3_icon} ➔ <b>+30 PTS</b>\n"
        "────────────────────\n"
        f"🎁 <b>پاداش تکمیل کل ماموریت‌ها: +100 PTS و +50 XP</b>\n\n"
    )

    buttons = []
    if all_done:
        if claimed:
            text += "🎉 <i>شما پاداش امروز را دریافت کرده‌اید!</i>"
        else:
            buttons.append([InlineKeyboardButton("🎁 دریافت جایزه ۱۰۰ امتیازی", callback_data="claim_quests")])
    else:
        text += "⚡️ <i>با کامل کردن ماموریت‌ها دکمه دریافت پاداش فعال می‌شود.</i>"

    buttons.append([InlineKeyboardButton("‹ بازگشت", callback_data="home")])
    kb_markup = InlineKeyboardMarkup(buttons)

    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)
    else: await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

# --- ADMIN COMMANDS: ADD POINTS, BACKUP & RESTORE ---

async def add_points_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    if not context.args:
        await update.message.reply_text("⚠️ <b>نحوه استفاده:</b> <code>/add 500</code>", parse_mode="HTML")
        return

    try: amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً یک عدد معتبر وارد کنید.")
        return

    target_id, target_name = user.id, user.first_name
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_u = update.message.reply_to_message.from_user
        target_id, target_name = target_u.id, target_u.first_name
        await ensure_user(target_u)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, target_id))
        await db.commit()

    await update.message.reply_text(f"✅ <b>مبلغ {amount:,} امتیاز به {html.escape(target_name)} اضافه شد!</b>", parse_mode="HTML")

async def backup_db_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != str(ADMIN_ID): return
    if os.path.exists(DATABASE_PATH):
        with open(DATABASE_PATH, "rb") as doc:
            await update.message.reply_document(
                document=doc,
                filename=f"backup_{get_iran_now().strftime('%Y%m%d_%H%M')}.db",
                caption="💾 <b>نسخه کامل پشتیبان دیتابیس</b>\nجهت بازگردانی روی هاست جدید ریپلای کنید: <code>/restore</code>",
                parse_mode="HTML"
            )
    else:
        await update.message.reply_text("⚠️ فایل دیتابیس یافت نشد.")

async def restore_db_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != str(ADMIN_ID): return
    target_msg = update.message.reply_to_message
    if not target_msg or not target_msg.document:
        await update.message.reply_text("⚠️ برای بازگردانی، این دستور را روی فایل دیتابیس ریپلای کن:\n<code>/restore</code>", parse_mode="HTML")
        return

    try:
        doc = target_msg.document
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(DATABASE_PATH)
        await update.message.reply_text("✅ <b>دیتابیس با موفقیت جایگزین شد!</b> تمام اطلاعات بازگردانی گردید.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error restoring DB: {e}")
        await update.message.reply_text(f"❌ خطا در بازگردانی فایل: {e}")

async def reset_points_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE users SET points = 100")
            await db.commit()
        await update.message.reply_text("✅ <b>امتیاز تمامی کاربران با موفقیت روی ۱۰۰ ریست شد!</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error resetting points: {e}")

async def set_live_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return
    chat = update.effective_chat
    if chat.type in ["group", "supergroup"]:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('live_chat_id', ?)", (str(chat.id),))
            await db.commit()
        await update.message.reply_text(f"✅ <b>این گروه به عنوان گروه اختصاصی ثبت شد!</b> شناسه: <code>{chat.id}</code>", parse_mode="HTML")

async def generate_pool_message_text(match, participants):
    home_name = match.get("home_team", "میزبان")
    away_name = match.get("away_team", "میهمان")
    time_str = format_iran_time(match.get("date"))

    text = (
        f"🔥 <b>استخر جایزه ویژه ۳۰۰ امتیازی مسابقه بزرگ!</b> 🎁\n"
        "────────────────────\n"
        f"⚽️ <b>{home_name}</b> 🆚 <b>{away_name}</b>\n"
        f"⏰ ساعت شروع: <code>{time_str}</code> (تهران)\n"
        f"💰 جایزه کل: <b>300 امتیاز</b>\n"
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
        except Exception: pass

    unique_matches = {m["id"]: m for m in matches}
    utc_now = datetime.now(timezone.utc)

    for m_id, m in unique_matches.items():
        h_name, a_name = str(m.get("home_team", "")), str(m.get("away_team", ""))
        home_tracked, away_tracked = identify_tracked_team(h_name), identify_tracked_team(a_name)
        is_iran_match = "ایران" in h_name or "ایران" in a_name
        if not home_tracked and not away_tracked and not is_iran_match: continue

        MATCH_CACHE[m_id] = m
        raw_status = str(m.get("status", "UPCOMING")).upper()
        try:
            h_score = int(m.get("home_score")) if m.get("home_score") is not None else None
            a_score = int(m.get("away_score")) if m.get("away_score") is not None else None
        except Exception: h_score, a_score = None, None

        track = TRACKED_LIVE_MATCHES.get(m_id)
        if not track:
            track = {
                "last_status": raw_status,
                "home_score": h_score if h_score is not None else 0,
                "away_score": a_score if a_score is not None else 0,
                "started_announced": False, "pool_opened": False, "pool_msg_id": None, "banter_sent": False
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
                [InlineKeyboardButton(f"⚪️ برد {h_name[:12]}", callback_data=f"pool_{m_id}_HOME"),
                 InlineKeyboardButton("🤝 تساوی", callback_data=f"pool_{m_id}_DRAW"),
                 InlineKeyboardButton(f"🔴 برد {a_name[:12]}", callback_data=f"pool_{m_id}_AWAY")]
            ])
            msg_text = await generate_pool_message_text(m, [])
            try:
                sent = await context.bot.send_message(chat_id=target_chat_id, text=msg_text, reply_markup=pool_kb, parse_mode="HTML")
                track["pool_msg_id"] = sent.message_id
            except Exception: pass

        if raw_status == "LIVE" and not track.get("started_announced"):
            track["started_announced"] = True
            time_str = format_iran_time(m.get("date"))
            start_msg = (
                f"🚨 <b>سوت آغاز مسابقه حساس!</b> ⚽️\n────────────────────\n"
                f"🏟 <b>{h_name}</b> 🆚 <b>{a_name}</b>\n⏰ شروع: <code>{time_str}</code> (تهران)\n"
                "▫️ استخر پیش‌بینی بسته شد. گزارش زنده آغاز گردید."
            )
            try: await context.bot.send_message(chat_id=target_chat_id, text=start_msg, parse_mode="HTML")
            except Exception: pass

        is_live = raw_status == "LIVE"
        is_finished = raw_status == "FINISHED"
        if (is_live or is_finished) and h_score is not None and a_score is not None:
            prev_h, prev_a = track["home_score"], track["away_score"]
            if h_score != prev_h or a_score != prev_a:
                track["home_score"], track["away_score"] = h_score, a_score
                goal_msg = f"⚽️🔥 <b>تغییر در نتیجه مسابقه! (گـُــل)</b>\n────────────────────\n▫️ <b>{h_name} [{h_score}] - [{a_score}] {a_name}</b>"
                try: await context.bot.send_message(chat_id=target_chat_id, text=goal_msg, parse_mode="HTML")
                except Exception: pass

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
                    else: winners_text = "\n\n▫️ هیچ کاربری برنده نهایی را درست حدس نزد!"
                    await db.execute("UPDATE special_pool_predictions SET settled = 1 WHERE match_id = ?", (m_id,))
                    await db.commit()

            ft_msg = f"🏁 <b>سوت پایان مسابقه (Full Time)</b>\n────────────────────\nنتیجه: <b>{h_name} [{final_h}] - [{final_a}] {a_name}</b>{winners_text}"
            try: await context.bot.send_message(chat_id=target_chat_id, text=ft_msg, parse_mode="HTML")
            except Exception: pass

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
            async with db.execute("SELECT user_id, first_name, points FROM users WHERE user_id != ? ORDER BY points DESC LIMIT 4", (ESCOBAR_AI_ID,)) as cur:
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
                        f"🏆 <b>پایان رسمی رقابت‌های این سیزن!</b> 🔥\n────────────────────\n"
                        f"🥇 قهرمان سیزن: <b>{html.escape(p1[1])}</b>\n"
                    )
                    if p2: msg += f"🥈 نایب قهرمان: <b>{html.escape(p2[1])}</b>\n"
                    if p3: msg += f"🥉 مقام سوم: <b>{html.escape(p3[1])}</b>\n"
                    msg += "\n🔄 <b>امتیازات سیزن روی ۱۰۰ ریست شدند. کارت‌ها و لول محفوظ است!</b>"
                    try: await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")
                    except Exception: pass

                await db.execute("UPDATE users SET points = 100, duel_wins = 0, penalty_wins = 0, guess_wins = 0")
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
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb.get_main_menu())
    else: await update.message.reply_text(text, reply_markup=kb.get_main_menu(), parse_mode="HTML")

async def show_leaderboard_text(requesting_user_id: int = None) -> str:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, first_name, points, duel_wins FROM users WHERE user_id != ? ORDER BY points DESC, duel_wins DESC LIMIT 30", (ESCOBAR_AI_ID,)) as cur:
            all_users = await cur.fetchall()

    text = "🏆 <b>جدول رده‌بندی سیزن</b> 🔥\n────────────────────\n\n"
    if not all_users: return text + "هنوز کاربری ثبت نشده است.\n────────────────────"

    top_list, remaining_list = all_users[:15], all_users[15:25]
    for idx, u in enumerate(top_list, 1):
        name, pts, wins = u[1], max(0, u[2]), u[3]
        _, tier = get_user_tier(pts)
        display_name = format_bidi_name(name)
        rank_prefix = "🥇 👑" if idx == 1 else ("🥈 👑" if idx == 2 else ("🥉 👑" if idx == 3 else f"<code>{idx:02d}.</code>"))
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
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
    else: await update.message.reply_text(text, parse_mode="HTML")

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

    medals_text = "\n\n🏆 <b>افتخارات سیزن:</b>\n" + "  •  ".join(medals_lines) if medals_lines else ""

    text = (
        f"⚽ <b>{safe_name}</b>\n\n"
        f"🏆 <b>{tier}</b>\n"
        f"<b>LVL {level}</b>\n"
        f"{bar} <code>{percent}%</code>\n\n"
        f"💰 <b>{pts:,} PTS</b>\n"
        f"🛡 <b>قدرت نهایی تیم:</b> <code>{team_ovr} OVR</code> ({lineup_count}/5)\n"
        f"⚗️ <b>کمیستری تیم:</b> <code>{team_chem}%</code>\n"
        f"⚔️ <b>{d_wins or 0}</b> Wins\n"
        f"🧠 <b>{accuracy}%</b> Accuracy\n"
        f"🥅 <b>{p_wins or 0}</b> Penalty Wins\n"
        f"🕵️ <b>{g_wins or 0}</b> Guess Wins"
        f"{medals_text}"
    )

    if hasattr(query, "message") and query.message:
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())
    else: await query.reply_text(text, parse_mode="HTML")

async def daily_reward_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT last_daily_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                await update.effective_message.reply_text(f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، پاداش امروز را دریافت کرده‌اید!", parse_mode="HTML")
                return

        reward = 35
        await db.execute("UPDATE users SET points = points + ?, last_daily_date = ? WHERE user_id = ?", (reward, today_str, user.id))
        await db.commit()

    await profile_add_xp(user.id, 25)
    await update.effective_message.reply_text(f"🎁 <b>پاداش ورود روزانه واریز شد!</b>\n💰 <b>+{reward} امتیاز</b> دریافت کردید.", parse_mode="HTML")

async def daily_shoot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT last_shoot_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                await update.effective_message.reply_text(f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، شوت امروز را زده‌اید!", parse_mode="HTML")
                return
        await db.execute("UPDATE users SET last_shoot_date = ? WHERE user_id = ?", (today_str, user.id))
        await db.commit()

    msg = await update.effective_message.reply_dice(emoji="⚽")
    dice_val = msg.dice.value
    await asyncio.sleep(2.5)

    if dice_val in [3, 4, 5]:
        reward = 30
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (reward, user.id))
            await db.commit()
        await profile_add_xp(user.id, 25)
        await update.effective_message.reply_text(f"⚽️🔥 <b>گـُـل شد! ضربه مهارنشدنی!</b>\n💰 پاداش: <b>+{reward} امتیاز</b> دریافت کردید.", parse_mode="HTML")
    else:
        await update.effective_message.reply_text("🧤❌ <b>توپ گل نشد!</b> امشب بعد از ساعت ۱۲ دوباره شانس داری.", parse_mode="HTML")

# --- IMPROVED WHEEL OF FORTUNE (0 TO 500 PTS) ---

async def spin_wheel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    user = update.effective_user
    await ensure_user(user)
    today_str = get_iran_now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT last_wheel_date FROM users WHERE user_id = ?", (user.id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == today_str:
                await update.effective_message.reply_text(f"⏳ <b>{html.escape(user.first_name)}</b> عزیز، امروز گردونه را چرخانده‌اید!", parse_mode="HTML")
                return
        await db.execute("UPDATE users SET last_wheel_date = ? WHERE user_id = ?", (today_str, user.id))
        await db.commit()

    prizes = [0, 30, 60, 120, 250, 380, 500]
    weights = [15, 30, 25, 16, 10, 3, 1]
    win = random.choices(prizes, weights=weights)[0]

    async with aiosqlite.connect(DATABASE_PATH) as db:
        if win > 0:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (win, user.id))
            await db.commit()

    if win == 500:
        msg = f"🎰🔥 <b>جـک‌پـات تـاریـخـی گـردونـه!</b>\n🎉 تبریک ویژه به <b>{html.escape(user.first_name)}</b>! برنده خوش‌شانس <b>+۵۰۰ امتیاز</b> شدید!"
    elif win > 0:
        await profile_add_xp(user.id, win // 2)
        msg = f"🎡 <b>گردونه شانس متوقف شد!</b>\n🎉 تبریک، برنده <b>+{win} امتیاز</b> شدید!"
    else:
        msg = "🎡 <b>گردونه شانس متوقف شد!</b>\n❌ این بار پوچ شد! امشب بعد از ساعت ۱۲ دوباره شانس‌ات را امتحان کن."

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
            text=f"⌛️ <b>مهلت ۳۰ ثانیه‌ای حدس بازیکن تمام شد!</b>\n👤 ستاره مورد نظر پرونده: <b>{main_name}</b> بود.",
            parse_mode="HTML"
        )

async def start_guess_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    chat_id, user = update.effective_chat.id, update.effective_user
    await ensure_user(user)

    g_count = await get_guess_count_db(user.id)
    if g_count >= 3:
        await update.effective_message.reply_text(f"⛔️ <b>{html.escape(user.first_name)}</b> عزیز، سقف ۳ حدس امروز را مصرف کرده‌اید!", parse_mode="HTML")
        return

    game = ACTIVE_GUESS_GAMES.get(chat_id)
    if game and game.get("is_active"):
        await update.effective_message.reply_text("⚠️ یک پرونده هم‌اکنون در این گروه در جریان است!", parse_mode="HTML")
        return

    await increment_guess_count_db(user.id)
    current_attempt = g_count + 1
    p = get_next_guess_player()
    career_str = "\n".join([f"  {idx}. {club}" for idx, club in enumerate(p['career'], 1)])

    ACTIVE_GUESS_GAMES[chat_id] = {
        "names": [n.lower() for n in p["names"]],
        "reward": 20, "chat_id": chat_id,
        "challenger_id": user.id, "challenger_name": user.first_name, "is_active": True
    }

    text = (
        "🕵️‍♂️ <b>پرونده اطلاعاتی: ستاره فوتبال را شناسایی کنید!</b>\n────────────────────\n"
        f"🎯 بازیکن چالش: <b>{html.escape(user.first_name)}</b> ({current_attempt}/3)\n"
        f"⏱ مهلت پاسخ: <b>۳۰ ثانیه</b> ⏳\n"
        f"🌍 <b>ملیت:</b> {p['nation']}\n📌 <b>پست تخصصی:</b> {p['pos']}\n\n"
        f"🏟 <b>مسیر باشگاهی:</b>\n{career_str}\n\n⭐️ <b>سرنخ:</b>\n{p['clue']}\n────────────────────\n"
        "💰 پاداش پاسخ صحیح: <b>+20 امتیاز</b> | <b>+80 XP</b>\n👇 نام بازیکن را در چت ارسال کنید:"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")
    schedule_timer(context, guess_timeout_job, 30, data={"chat_id": chat_id, "user_id": user.id}, name=f"guess_timer_{chat_id}")

# --- SUDDEN DEATH PENALTY ---

def render_shootout_board(shootout_id: str, shooter_name: str, shot_number: int = 1):
    text = (
        f"🥅 <b>نوبت ضربه پنالتی! (شوت {shot_number})</b> ⚽️\n────────────────────\n"
        f"👤 زننده ضربه: <b>{html.escape(shooter_name)}</b>\nگوشه شوت خود را انتخاب کنید:"
    )
    buttons = [
        [InlineKeyboardButton("↖️ بالا چپ", callback_data=f"sht_{shootout_id}_TL"),
         InlineKeyboardButton("⬆️ طاق مرکز", callback_data=f"sht_{shootout_id}_TC"),
         InlineKeyboardButton("↗️ بالا راست", callback_data=f"sht_{shootout_id}_TR")],
        [InlineKeyboardButton("↙️ پایین چپ", callback_data=f"sht_{shootout_id}_BL"),
         InlineKeyboardButton("⬇️ زمینی مرکز", callback_data=f"sht_{shootout_id}_BC"),
         InlineKeyboardButton("↘️ پایین راست", callback_data=f"sht_{shootout_id}_BR")]
    ]
    return text, InlineKeyboardMarkup(buttons)

async def trigger_penalty_shootout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("🥅 روی پیام حریف ریپلای کنید و بنویسید: <code>پنالتی</code>", parse_mode="HTML")
        return

    challenger, opponent = update.effective_user, update.message.reply_to_message.from_user
    if opponent.is_bot or challenger.id == opponent.id: return

    c_count = await get_penalty_count_db(challenger.id)
    o_count = await get_penalty_count_db(opponent.id)
    if c_count >= 3 or o_count >= 3:
        await update.message.reply_text("⛔️ یکی از طرفین سقف ۳ پنالتی امروز خود را مصرف کرده است!", parse_mode="HTML")
        return

    await ensure_user(challenger)
    await ensure_user(opponent)

    stake = 25
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (challenger.id, opponent.id)) as cur:
            balances = {row[0]: row[1] for row in await cur.fetchall()}

    if balances.get(challenger.id, 0) < stake or balances.get(opponent.id, 0) < stake:
        await update.message.reply_text(f"⛔️ هر دو بازیکن باید حداقل <b>{stake} PTS</b> داشته باشند.", parse_mode="HTML")
        return

    p_id = f"pen_{random.randint(10000, 99999)}"
    ACTIVE_SHOOTOUTS[p_id] = {
        "p1": {"id": challenger.id, "name": challenger.first_name, "shot": None},
        "p2": {"id": opponent.id, "name": opponent.first_name, "shot": None},
        "current_turn": challenger.id, "round": 1, "stake": stake,
        "chat_id": update.effective_chat.id, "message_id": None
    }

    p_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧤 قبول پنالتی", callback_data=f"acp_{p_id}"),
         InlineKeyboardButton("❌ لغو", callback_data=f"rjp_{p_id}")]
    ])
    text = f"🥅 <b>دوئل پنالتی مرگ ناگهانی!</b> ⚽️\n{html.escape(challenger.first_name)} 🆚 {html.escape(opponent.first_name)}\nشرط: <b>{stake} PTS</b>\nآیا می‌پذیری؟"
    sent_msg = await update.message.reply_text(text, reply_markup=p_kb, parse_mode="HTML")
    ACTIVE_SHOOTOUTS[p_id]["message_id"] = sent_msg.message_id

async def execute_penalty_kick(context: ContextTypes.DEFAULT_TYPE, shootout_id: str, choice: str):
    s = ACTIVE_SHOOTOUTS.get(shootout_id)
    if not s: return

    chat_id = s["chat_id"]
    msg_id = s["message_id"]
    gk_dive = random.choice(["TL", "TC", "TR", "BL", "BC", "BR"])
    is_goal = choice != gk_dive

    pos_names = {"TL": "بالا چپ", "TC": "طاق مرکز", "TR": "بالا راست", "BL": "پایین چپ", "BC": "زمینی مرکز", "BR": "پایین راست"}

    if s["p1"]["shot"] is None:
        s["p1"]["shot"] = is_goal
        s["current_turn"] = s["p2"]["id"]
        status_text = f"⚽️ <b>گل شد!</b> ({pos_names.get(choice)})" if is_goal else f"🧤 <b>مهار شد!</b> ({pos_names.get(gk_dive)})"
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
            await safe_edit_message(context.bot, f"🏁 راند {s['round']-1}: {status}\n⚠️ <b>مرگ ناگهانی!</b> راند جدید شروع شد.\n\n{t}", reply_markup=k, chat_id=chat_id, message_id=msg_id)
        else:
            winner = s["p1"] if p1_res else s["p2"]
            loser = s["p2"] if p1_res else s["p1"]
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (s["stake"], winner["id"]))
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (s["stake"], loser["id"]))
                await db.commit()

            await profile_record_penalty_win(winner["id"])
            res = (
                f"🏁 <b>پایان مسابقه پنالتی (راند {s['round']})</b>\n────────────────────\n"
                f"👤 {s['p1']['name']}: {'⚽️' if p1_res else '❌'}\n"
                f"👤 {s['p2']['name']}: {'⚽️' if p2_res else '❌'}\n\n"
                f"🏆 برنده: <b>{winner['name']}</b> (+{s['stake']} امتیاز)"
            )
            await safe_edit_message(context.bot, res, chat_id=chat_id, message_id=msg_id)
            del ACTIVE_SHOOTOUTS[shootout_id]

# --- WEEKLY JACKPOT ---

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

    return {"round_id": week_id, "title": "جک‌پات طلایی هفته", "matches": selected_5, "pool_amount": 500, "is_open": True}

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
                        msg = f"🎰 <b>جک‌پات هفته تسویه شد!</b>\n🏆 برندگان ۵ از ۵:\n" + "\n".join([f"👤 {w[1]} (+{prize} PTS)" for w in winners])
                        target_chat_id = await get_live_chat_id()
                        if target_chat_id: await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")

                    await db.execute("UPDATE jackpot_rounds SET is_settled = 1, is_active = 0 WHERE round_id = ?", (r_id,))
                    await db.commit()
    except Exception as e: logger.error(f"Error in settle_jackpot_task: {e}")

async def jackpot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    round_data = await get_or_create_jackpot_round()
    round_id, matches, pool, is_open = round_data["round_id"], round_data["matches"], round_data.get("pool_amount", 500), round_data.get("is_open", True)

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

    text = f"🎰 <b>{round_data.get('title')}</b>\n────────────────────\n💰 استخر جایزه: <b>{pool:,} PTS</b>\n────────────────────\n📋 <b>مسابقات:</b>\n\n{matches_text}{status_footer}"
    reply_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=reply_markup)
    else: await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

# --- PREDICTIONS HUB ---

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
                    if m.get("status") == "UPCOMING": candidate_matches.append(m)
            except Exception: pass

    seen, upcoming_list = set(), []
    for m in candidate_matches:
        if m["id"] not in seen:
            seen.add(m["id"])
            upcoming_list.append(m)

    if not upcoming_list:
        await safe_edit_message(query, "⏳ مسابقه شروع‌نشده‌ای در دسترس نیست.", reply_markup=kb.get_back_button())
        return

    text = "🎯 <b>تالار پیش‌بینی مسابقات فوتبال</b>\n────────────────────\nمسابقه مورد نظر خود را جهت ثبت پیش‌بینی انتخاب کنید:\n💰 پاداش: <b>+10 امتیاز</b>\n────────────────────"
    await safe_edit_message(query, text, reply_markup=kb.get_upcoming_matches_keyboard(upcoming_list))

# --- FC CARDS, CHEMISTRY, SELLING & LEAGUE SYSTEM ---

RARITY_COLORS = {"ICON": "💎 آیکان", "ELITE": "🔥 الیت", "RARE": "⭐️ ریر", "COMMON": "⚪️ معمولی"}

def calculate_team_chemistry(cards):
    if len(cards) < 5: return 0
    chem = 35
    icons = sum(1 for c in cards if c.get("rarity") == "ICON")
    chem += icons * 15

    nations = [c.get("nation") for c in cards if c.get("nation") and c.get("rarity") != "ICON"]
    for _, count in Counter(nations).items():
        if count >= 2: chem += (count - 1) * 18

    clubs = [c.get("club") for c in cards if c.get("club") and c.get("rarity") != "ICON"]
    for _, count in Counter(clubs).items():
        if count >= 2: chem += (count - 1) * 22

    return min(100, max(0, chem))

def generate_random_card_by_rarity(rarity_weights=None):
    if not rarity_weights:
        rarity_weights = {"COMMON": 65, "RARE": 25, "ELITE": 9, "ICON": 1}
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

        if row: offers = json.loads(row[0])
        else:
            commons = random.sample([c for c in FC_CATALOG if c["rarity"] == "COMMON"], 2)
            rares = random.sample([c for c in FC_CATALOG if c["rarity"] == "RARE"], 3)
            elites = random.sample([c for c in FC_CATALOG if c["rarity"] == "ELITE"], 2)
            icons = random.sample([c for c in FC_CATALOG if c["rarity"] == "ICON"], 1)
            selected = commons + rares + elites + icons
            random.shuffle(selected)

            offers = []
            for i, c in enumerate(selected):
                price = (random.randint(120, 160) if c["rarity"] == "COMMON" else
                         (random.randint(350, 480) if c["rarity"] == "RARE" else
                          (random.randint(1100, 1400) if c["rarity"] == "ELITE" else random.randint(2800, 3400))))
                offers.append({"idx": i, "card": c, "price": price, "bought": False})

            await db.execute("INSERT OR REPLACE INTO daily_market (user_id, date_str, offers_json) VALUES (?, ?, ?)",
                             (user.id, today_str, json.dumps(offers, ensure_ascii=False)))
            await db.commit()

        async with db.execute("SELECT points FROM users WHERE user_id = ?", (user.id,)) as cur:
            u_pts = (await cur.fetchone())[0]

    text = f"🛒 <b>مارکت بزرگ نقل‌وانتقالات روزانه FC</b>\n────────────────────\n💰 موجودی شما: <b>{u_pts:,} PTS</b>\n────────────────────\n\n"
    buttons = []
    for o in offers:
        c = o["card"]
        tag = RARITY_COLORS.get(c["rarity"], c["rarity"])
        status = "✅ خریداری شده" if o["bought"] else f"{o['price']} PTS"
        text += f"▫️ <b>{c['name']}</b> ({c['pos']}) ➔ <b>{c['ovr']} OVR</b>\n    └ {c.get('nation','')} | {c.get('club','')} | {tag} | <b>{status}</b>\n\n"
        if not o["bought"]:
            buttons.append([InlineKeyboardButton(f"خرید {c['name']} ({c['ovr']}) - {o['price']} PTS", callback_data=f"buy_m_{o['idx']}")])

    buttons.append([InlineKeyboardButton("📦 باز کردن پک طلایی (250 PTS)", callback_data="buy_pack_gold")])
    buttons.append([InlineKeyboardButton("💰 فروش کارت‌های مازاد به ربات", callback_data="open_sell_menu")])
    buttons.append([InlineKeyboardButton("‹ بازگشت", callback_data="home")])

    kb_markup = InlineKeyboardMarkup(buttons)
    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb_markup)
    else: await update.message.reply_text(text, reply_markup=kb_markup, parse_mode="HTML")

async def sell_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    text = "💰 <b>فروشگاه بازخرید کارت‌ها (Quick Sell)</b>\n────────────────────\nوجه فروش فوراً به حسابتان اضافه می‌شود.\n────────────────────\n\n"
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
        text = "🎴 <b>کلکسیون کارت‌های شما خالی است!</b>\nاز مارکت کارت تهیه کنید."
        if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
        else: await update.message.reply_text(text, parse_mode="HTML")
        return

    text = f"🎴 <b>کلکسیون کارت‌های {html.escape(user.first_name)}:</b>\n────────────────────\n\n"
    for name, ovr, pos, rar, in_lineup in cards:
        star = "🟢 [در ترکیب]" if in_lineup else "⚪️"
        c_info = FC_CATALOG_DICT.get(name, {})
        text += f"{star} <b>{name}</b> ({pos}) ➔ <b>{ovr} OVR</b> {c_info.get('nation','')} | {RARITY_COLORS.get(rar, rar)}\n"

    buttons = [
        [InlineKeyboardButton("⚡️ چیدن خودکار قوی‌ترین ترکیب", callback_data="auto_lineup")],
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

    enriched_cards, positions, mids = [], {"GK": None, "DEF": None, "MID1": None, "MID2": None, "FWD": None}, []
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
        f"🛡 <b>ترکیب ۵ نفره تیم: {html.escape(user.first_name)}</b>\n────────────────────\n"
        f"⭐️ <b>قدرت پایه تیمی:</b> <code>{avg_ovr} OVR</code>\n"
        f"⚗️ <b>کمیستری تیم:</b> <code>{chem}%</code> (بوست: <b>+{chem_boost}</b>)\n"
        f"⚡️ <b>قدرت نهایی تیم:</b> <code>{effective_ovr} OVR</code> 🔥\n\n"
        f"🧤 دروازه‌بان (GK): {p_line(positions['GK'])}\n"
        f"🛡 مدافع (DEF): {p_line(positions['DEF'])}\n"
        f"⚡️ هافبک ۱ (MID): {p_line(positions['MID1'])}\n"
        f"⚡️ هافبک ۲ (MID): {p_line(positions['MID2'])}\n"
        f"🎯 مهاجم (FWD): {p_line(positions['FWD'])}\n────────────────────"
    )

    buttons = [
        [InlineKeyboardButton("⚡️ چیدن خودکار بهترین ترکیب", callback_data="auto_lineup")],
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
                for cid in ids: await db.execute("UPDATE user_cards SET is_in_lineup = 1 WHERE id = ?", (cid,))
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

# مسابقه کارت‌ها با شرط ۱۰۰ امتیازی
async def trigger_card_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚽️ برای مسابقه کارت‌ها، روی پیام حریف ریپلای کن و بنویس:\n<code>مسابقه کارت</code> یا <code>/cardmatch</code>", parse_mode="HTML")
        return

    p1, p2 = update.effective_user, update.message.reply_to_message.from_user
    if p2.is_bot or p1.id == p2.id: return

    await ensure_user(p1)
    await ensure_user(p2)

    t1, t2 = await get_user_team_info(p1.id), await get_user_team_info(p2.id)
    if not t1 or not t2:
        await update.message.reply_text("⛔️ هر دو بازیکن باید ترکیب ۵ نفره کامل داشته باشند!", parse_mode="HTML")
        return

    stake = 100
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (p1.id, p2.id)) as cur:
            balances = {r[0]: r[1] for r in await cur.fetchall()}

    if balances.get(p1.id, 0) < stake or balances.get(p2.id, 0) < stake:
        await update.message.reply_text(f"⛔️ هر دو بازیکن باید حداقل <b>{stake} PTS</b> داشته باشند.", parse_mode="HTML")
        return

    m_id = f"cm_{random.randint(10000, 99999)}"
    ACTIVE_CARD_MATCHES[m_id] = {
        "p1": {"id": p1.id, "name": p1.first_name, "team": t1, "score": 0},
        "p2": {"id": p2.id, "name": p2.first_name, "team": t2, "score": 0},
        "stake": stake, "chat_id": update.effective_chat.id, "msg_id": None
    }

    kb_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ قبول مسابقه کارت‌ها", callback_data=f"ac_cm_{m_id}"),
         InlineKeyboardButton("❌ لغو", callback_data=f"rj_cm_{m_id}")]
    ])
    text = (
        f"🏟 <b>مسابقه کارت‌های FC (شرط ۱۰۰ امتیازی)!</b> 🔥\n────────────────────\n"
        f"🔵 تیم ۱: <b>{html.escape(p1.first_name)}</b> (⭐️ {t1['eff_ovr']} | ⚗️ {t1['chem']}%)\n"
        f"🔴 تیم ۲: <b>{html.escape(p2.first_name)}</b> (⭐️ {t2['eff_ovr']} | ⚗️ {t2['chem']}%)\n"
        f"💰 مبلغ شرط: <b>{stake} PTS</b> | مدت بازی: <b>۶۰ ثانیه</b>\n────────────────────\n"
        f"آیا <b>{html.escape(p2.first_name)}</b> این چالش را می‌پذیرد؟"
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
    t15 = f"⏱ <b>دقیقه ۱۵:</b>\n▫️ <b>{p1['name']} [{p1['score']}] - [{p2['score']}] {p2['name']}</b>\n────────────────────\n⚔️ درگیری فیزیکی هافبک‌ها در میانه میدان..."
    await safe_edit_message(context.bot, t15, chat_id=chat_id, message_id=msg_id)

    await asyncio.sleep(15)
    p1_prob = 0.35 + (ovr_diff * 0.025)
    if random.random() < p1_prob:
        p1["score"] += 1
        ev40 = f"⚽️🔥 <b>گـُــل برای {p1['name']}!</b> شوت استثنایی <b>{p1['team']['fwd']}</b> وارد دروازه شد!"
    else: ev40 = f"🧤 مهار دیدنی توسط <b>{p2['team']['gk']}</b>!"

    t40 = f"⏱ <b>دقیقه ۴۰:</b>\n▫️ <b>{p1['name']} [{p1['score']}] - [{p2['score']}] {p2['name']}</b>\n────────────────────\n{ev40}"
    await safe_edit_message(context.bot, t40, chat_id=chat_id, message_id=msg_id)

    await asyncio.sleep(15)
    p2_prob = 0.35 - (ovr_diff * 0.025)
    if random.random() < p2_prob:
        p2["score"] += 1
        ev70 = f"⚽️🔥 <b>گـُــل برای {p2['name']}!</b> فرار سریع <b>{p2['team']['fwd']}</b> به گل نشست!"
    else: ev70 = f"🛡 تکل نجات‌بخش خط دفاعی، مانع از گلزنی <b>{p2['name']}</b> شد."

    t70 = f"⏱ <b>دقیقه ۷۰:</b>\n▫️ <b>{p1['name']} [{p1['score']}] - [{p2['score']}] {p2['name']}</b>\n────────────────────\n{ev70}"
    await safe_edit_message(context.bot, t70, chat_id=chat_id, message_id=msg_id)

    await asyncio.sleep(15)
    s1, s2, stake = p1["score"], p2["score"], m["stake"]
    res_footer = ""
    winner_id = None

    async with aiosqlite.connect(DATABASE_PATH) as db:
        if s1 > s2:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, p1["id"]))
            await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, p2["id"]))
            winner_id = p1["id"]
            res_footer = f"🏆 برنده بازی: <b>{p1['name']}</b> (+{stake} امتیاز و +100 XP)"
        elif s2 > s1:
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, p2["id"]))
            await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, p1["id"]))
            winner_id = p2["id"]
            res_footer = f"🏆 برنده بازی: <b>{p2['name']}</b> (+{stake} امتیاز و +100 XP)"
        else:
            res_footer = "🤝 مسابقه مساوی شد! هیچ امتیازی کسر نشد."
        await db.commit()

    if winner_id:
        await profile_add_xp(winner_id, 100)

    await record_quest_action(p1["id"], "card_matches")
    await record_quest_action(p2["id"], "card_matches")

    t90 = f"🏁 <b>سوت پایان مسابقه کارت‌ها (Full Time)</b>\n────────────────────\n▫️ <b>{p1['name']} [{s1}] - [{s2}] {p2['name']}</b>\n────────────────────\n{res_footer}"
    await safe_edit_message(context.bot, t90, chat_id=chat_id, message_id=msg_id)
    ACTIVE_CARD_MATCHES.pop(m_id, None)

# --- FC CARDS LEAGUE ENGINE ---

async def league_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT season_id FROM league_seasons WHERE status = 'ACTIVE' ORDER BY created_at DESC LIMIT 1") as cur:
            row = await cur.fetchone()
            if not row:
                msg = "⏳ <b>در حال حاضر هیچ لیگ فعالی برگزار نمی‌شود.</b>"
                if update.callback_query: await safe_edit_message(update.callback_query, msg, reply_markup=kb.get_back_button())
                else: await update.message.reply_text(msg, parse_mode="HTML")
                return
            s_id = row[0]

        async with db.execute("""
            SELECT u.first_name, s.played, s.won, s.drawn, s.lost, s.gf, s.ga, s.gd, s.points
            FROM league_standings s
            JOIN users u ON s.user_id = u.user_id
            WHERE s.season_id = ?
            ORDER BY s.points DESC, s.gd DESC, s.gf DESC
        """, (s_id,)) as cur:
            table_rows = await cur.fetchall()

    text = f"🏆 <b>جدول رده‌بندی لیگ کارت‌های FC</b>\n────────────────────\n<pre>"
    text += "#  | Team          | P  | W  | D  | L  | GD | Pts\n---+---------------+----+----+----+----+----+----\n"
    for idx, (name, p, w, d, l, gf, ga, gd, pts) in enumerate(table_rows, 1):
        t_name = name[:13].ljust(13)
        text += f"{idx:<2} | {t_name} | {str(p):<2} | {str(w):<2} | {str(d):<2} | {str(l):<2} | {str(gd):<2} | {str(pts):<3}\n"
    text += "</pre>\n<i>(هر روز ۲ بازی خودکار برگزار می‌شود)</i>"

    if update.callback_query: await safe_edit_message(update.callback_query, text, reply_markup=kb.get_back_button())
    else: await update.message.reply_text(text, parse_mode="HTML")

async def league_on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT season_id FROM league_seasons WHERE status = 'ACTIVE'") as cur:
            if await cur.fetchone():
                await update.message.reply_text("⚠️ یک لیگ هم‌اکنون فعال است! ابتدا با /l_off آن را به پایان برسانید.")
                return

        # پیدا کردن تمام کاربرانی که ۵ کارت در لاین‌آپ دارند
        async with db.execute("""
            SELECT user_id FROM user_cards WHERE is_in_lineup = 1 GROUP BY user_id HAVING COUNT(*) = 5
        """) as cur:
            eligible = [r[0] for r in await cur.fetchall()]

    if len(eligible) < 3:
        await update.message.reply_text(f"⛔️ تعداد تیم‌های آماده ({len(eligible)}) کمتر از حد نصاب است! حداقل به ۳ تیم ۵ کارتی نیاز است.")
        return

    season_id = f"L_{get_iran_now().strftime('%Y%m%d_%H%M')}"
    today_str = get_iran_now().strftime("%Y-%m-%d %H:%M")

    # ساخت مسابقات رفت و برگشت
    fixtures = []
    for h in eligible:
        for a in eligible:
            if h != a: fixtures.append((season_id, h, a))

    random.shuffle(fixtures)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT INTO league_seasons (season_id, status, created_at) VALUES (?, 'ACTIVE', ?)", (season_id, today_str))
        for s_id, h_id, a_id in fixtures:
            await db.execute("INSERT INTO league_fixtures (season_id, home_id, away_id) VALUES (?, ?, ?)", (s_id, h_id, a_id))
        for uid in eligible:
            await db.execute("INSERT INTO league_standings (season_id, user_id) VALUES (?, ?)", (season_id, uid))
        await db.commit()

    total_m = len(fixtures)
    msg = (
        f"🏆🔥 <b>سوت آغاز لیگ رسمی کارت‌های FC به صدا درآمد!</b>\n────────────────────\n"
        f"👥 تعداد تیم‌های شرکت‌کننده: <b>{len(eligible)} تیم</b>\n"
        f"🏟 مجموع مسابقات رفت و برگشت: <b>{total_m} بازی</b>\n"
        f"⏰ برنامه برگزاری: <b>روزی ۲ مسابقه خودکار</b>\n\n"
        f"🥇 قهرمان: ۲,۵۰۰ PTS | 🥈 نایب‌قهرمان: ۱,۲۰۰ PTS | 🥉 سوم: ۶۰۰ PTS"
    )
    target_chat_id = await get_live_chat_id()
    if target_chat_id: await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="HTML")
    await update.message.reply_text("✅ لیگ با موفقیت استارت خورد!", parse_mode="HTML")

async def league_off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID): return

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE league_seasons SET status = 'CANCELLED' WHERE status = 'ACTIVE'")
        await db.commit()
    await update.message.reply_text("🔴 لیگ فعال فعلی لغو و متوقف شد.")

async def simulate_daily_league_task(context: ContextTypes.DEFAULT_TYPE):
    """تسک پس‌زمینه برگزاری ۲ مسابقه از لیگ در روز"""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT season_id FROM league_seasons WHERE status = 'ACTIVE' LIMIT 1") as cur:
                row = await cur.fetchone()
                if not row: return
                s_id = row[0]

            async with db.execute("SELECT id, home_id, away_id FROM league_fixtures WHERE season_id = ? AND status = 'PENDING' LIMIT 2", (s_id,)) as cur:
                pending_matches = await cur.fetchall()

            if not pending_matches:
                # پایان رسمی مسابقات لیگ و توزیع جوایز
                async with db.execute("""
                    SELECT s.user_id, u.first_name, s.points, s.gd
                    FROM league_standings s JOIN users u ON s.user_id = u.user_id
                    WHERE s.season_id = ? ORDER BY s.points DESC, s.gd DESC
                """, (s_id,)) as cur:
                    final_ranks = await cur.fetchall()

                if final_ranks:
                    prizes = {0: (2500, 600), 1: (1200, 350), 2: (600, 200)}
                    summary = "🏁 <b>پایان رسمی فصل لیگ کارت‌های FC!</b>\n────────────────────\n"
                    for idx, (uid, name, pts, gd) in enumerate(final_ranks):
                        p_pts, p_xp = prizes.get(idx, (150, 50))
                        await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (p_pts, uid))
                        await db.commit()
                        await profile_add_xp(uid, p_xp)
                        medal = "🥇" if idx == 0 else ("🥈" if idx == 1 else ("🥉" if idx == 2 else f"#{idx+1}"))
                        summary += f"{medal} <b>{html.escape(name)}</b>: {pts} PTS (+{p_pts} جایزه)\n"

                    await db.execute("UPDATE league_seasons SET status = 'FINISHED' WHERE season_id = ?", (s_id,))
                    await db.commit()

                    target_chat_id = await get_live_chat_id()
                    if target_chat_id: await context.bot.send_message(chat_id=target_chat_id, text=summary, parse_mode="HTML")
                return

            for f_id, h_id, a_id in pending_matches:
                t1 = await get_user_team_info(h_id)
                t2 = await get_user_team_info(a_id)
                ovr1 = t1["eff_ovr"] if t1 else 75
                ovr2 = t2["eff_ovr"] if t2 else 75
                diff = ovr1 - ovr2

                s1 = max(0, int(random.gauss(1.4 + diff * 0.05, 1.1)))
                s2 = max(0, int(random.gauss(1.2 - diff * 0.05, 1.1)))

                await db.execute("UPDATE league_fixtures SET home_score = ?, away_score = ?, status = 'FINISHED', played_date = ? WHERE id = ?",
                                 (s1, s2, get_iran_now().strftime("%Y-%m-%d %H:%M"), f_id))

                w1, d1, l1, pts1 = (1, 0, 0, 3) if s1 > s2 else ((0, 1, 0, 1) if s1 == s2 else (0, 0, 1, 0))
                w2, d2, l2, pts2 = (1, 0, 0, 3) if s2 > s1 else ((0, 1, 0, 1) if s1 == s2 else (0, 0, 1, 0))

                await db.execute("""
                    UPDATE league_standings SET played = played + 1, won = won + ?, drawn = drawn + ?, lost = lost + ?,
                    gf = gf + ?, ga = ga + ?, gd = gd + ?, points = points + ? WHERE season_id = ? AND user_id = ?
                """, (w1, d1, l1, s1, s2, s1 - s2, pts1, s_id, h_id))

                await db.execute("""
                    UPDATE league_standings SET played = played + 1, won = won + ?, drawn = drawn + ?, lost = lost + ?,
                    gf = gf + ?, ga = ga + ?, gd = gd + ?, points = points + ? WHERE season_id = ? AND user_id = ?
                """, (w2, d2, l2, s2, s1, s2 - s1, pts2, s_id, a_id))
                await db.commit()

                async with db.execute("SELECT first_name FROM users WHERE user_id = ?", (h_id,)) as cur: h_name = (await cur.fetchone())[0]
                async with db.execute("SELECT first_name FROM users WHERE user_id = ?", (a_id,)) as cur: a_name = (await cur.fetchone())[0]

                report = (
                    f"📢 <b>نتیجه رسمی بازی لیگ کارت‌های FC:</b>\n────────────────────\n"
                    f"▫️ تیم <b>{html.escape(h_name)}</b> [{s1}] - [{s2}] تیم <b>{html.escape(a_name)}</b>\n"
                    f"📊 جدول رده‌بندی با دستور <code>/league</code> به‌روز شد."
                )
                target_chat_id = await get_live_chat_id()
                if target_chat_id: await context.bot.send_message(chat_id=target_chat_id, text=report, parse_mode="HTML")
    except Exception as e: logger.error(f"Error in simulate_daily_league_task: {e}")

# --- TRIVIA DUELS (100% FIXED QUESTION 3 DEADLOCK) ---

async def trigger_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚔️ روی پیام حریف ریپلای کنید و بنویسید: <code>دوئل</code>", parse_mode="HTML")
        return

    challenger, opponent = update.effective_user, update.message.reply_to_message.from_user
    if opponent.is_bot or challenger.id == opponent.id: return
    await ensure_user(challenger)
    await ensure_user(opponent)

    stake = 25
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (challenger.id, opponent.id)) as cur:
            balances = {row[0]: row[1] for row in await cur.fetchall()}

    if balances.get(challenger.id, 0) < stake or balances.get(opponent.id, 0) < stake:
        await update.message.reply_text(f"⛔️ هر دو بازیکن باید حداقل <b>{stake} PTS</b> داشته باشند.", parse_mode="HTML")
        return

    duel_id = f"dl_{random.randint(10000, 99999)}"
    ACTIVE_DUELS[duel_id] = {
        "challenger": {"id": challenger.id, "name": challenger.first_name, "score": 0},
        "opponent": {"id": opponent.id, "name": opponent.first_name, "score": 0},
        "questions": get_random_duel_questions(3),
        "current_q": 0, "stake": stake, "answered": {},
        "chat_id": update.effective_chat.id, "message_id": None
    }

    duel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ قبول چالش دوئل", callback_data=f"acd_{duel_id}"),
         InlineKeyboardButton("❌ رد چالش", callback_data=f"rjd_{duel_id}")]
    ])
    c_name, o_name = html.escape(challenger.first_name), html.escape(opponent.first_name)
    text = f"⚔️ <b>میدان دوئل اطلاعات عمومی!</b> 🔥\n{c_name} 🆚 {o_name}\nجایزه: <b>+{stake} امتیاز</b> | زمان هر سوال: <b>۱۵ ثانیه</b>\nآیا می‌پذیری؟"
    sent_msg = await update.message.reply_text(text, reply_markup=duel_kb, parse_mode="HTML")
    ACTIVE_DUELS[duel_id]["message_id"] = sent_msg.message_id

def render_duel_question_text(duel, q_data, q_idx):
    c_name, o_name = html.escape(duel["challenger"]["name"]), html.escape(duel["opponent"]["name"])
    c_status = "✅" if duel["challenger"]["id"] in duel.get("answered", {}) else "⏳"
    o_status = "✅" if duel["opponent"]["id"] in duel.get("answered", {}) else "⏳"

    return (
        f"❓ <b>سوال {q_idx + 1} از ۳:</b>\n────────────────────\n"
        f"📌 <b>{q_data['question']}</b>\n\n⏱ مهلت پاسخ: <b>۱۵ ثانیه</b>\n────────────────────\n"
        f"👤 {c_name}: {c_status}  |  👤 {o_name}: {o_status}"
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

    # ثبت نتیجه قطعی پس از اتمام سوال ۳ (با رفع کامل باگ قفل دیتابیس)
    if q_idx >= len(duel["questions"]):
        try:
            c_score, o_score = duel["challenger"]["score"], duel["opponent"]["score"]
            c_name, o_name = html.escape(duel["challenger"]["name"]), html.escape(duel["opponent"]["name"])
            c_id, o_id, stake = duel["challenger"]["id"], duel["opponent"]["id"], duel["stake"]

            res_text = (
                "🏁 <b>پایان مسابقه دوئل اطلاعات عمومی!</b>\n────────────────────\n"
                f"👤 {c_name}: <code>{c_score}/3</code>\n"
                f"👤 {o_name}: <code>{o_score}/3</code>\n────────────────────\n"
            )

            winner_id = None
            async with aiosqlite.connect(DATABASE_PATH) as db:
                if c_score > o_score:
                    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, c_id))
                    await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, o_id))
                    res_text += f"🎉 تبریک به <b>{c_name}</b>! برنده <b>+{stake} امتیاز</b> شد."
                    winner_id = c_id
                elif o_score > c_score:
                    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, o_id))
                    await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, c_id))
                    res_text += f"🎉 تبریک به <b>{o_name}</b>! برنده <b>+{stake} امتیاز</b> شد."
                    winner_id = o_id
                else:
                    res_text += "🤝 رقابت مساوی شد! هیچ امتیازی کسر نگردید."
                await db.commit()

            if winner_id:
                await profile_record_duel_win(winner_id)

            await safe_edit_message(context.bot, res_text, reply_markup=None, chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.error(f"Error finalizing duel: {e}")
        finally:
            ACTIVE_DUELS.pop(duel_id, None)
        return

    q_data = duel["questions"][q_idx]
    duel["answered"] = {}
    buttons = [[InlineKeyboardButton(f"🔘 {opt}", callback_data=f"ad_{duel_id}_{opt_idx}")] for opt_idx, opt in enumerate(q_data["options"])]
    text = render_duel_question_text(duel, q_data, q_idx)
    await safe_edit_message(context.bot, text, reply_markup=InlineKeyboardMarkup(buttons), chat_id=chat_id, message_id=msg_id)
    schedule_timer(context, question_timeout_job, 15, data={"duel_id": duel_id, "q_idx": q_idx}, name=f"duel_timer_{duel_id}_{q_idx}")

async def trigger_team_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_action_allowed_in_chat(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚔️ برای بتل ۲ به ۲، روی پیام حریف ریپلای کن و بنویس: <code>بتل</code>", parse_mode="HTML")
        return

    challenger, opponent = update.effective_user, update.message.reply_to_message.from_user
    if opponent.is_bot or challenger.id == opponent.id: return
    await ensure_user(challenger)
    await ensure_user(opponent)
    stake = 30

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT user_id, points FROM users WHERE user_id IN (?, ?)", (challenger.id, opponent.id)) as cur:
            balances = {int(uid): int(pts or 0) for uid, pts in await cur.fetchall()}

    if balances.get(challenger.id, 0) < stake or balances.get(opponent.id, 0) < stake:
        await update.message.reply_text(f"⛔️ هر بازیکن باید حداقل <b>{stake} PTS</b> داشته باشد.", parse_mode="HTML")
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
    kb_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ یار تیم ۱", callback_data=f"bt1_{duel_id}"),
         InlineKeyboardButton("➕ یار تیم ۲", callback_data=f"bt2_{duel_id}")],
        [InlineKeyboardButton("❌ لغو بتل", callback_data=f"r2d_{duel_id}")]
    ])
    text = f"⚔️ <b>لابی نبرد ۲ به ۲ تیمی!</b> 🔥\nورودی: <b>{stake} PTS</b> | منتظر ملحق شدن یاران..."
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

    winning_team = []
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if t1_score > t2_score:
            text += f"🎉 تبریک! <b>تیم ۱</b> پیروز شد و هر بازیکن <b>+{stake} امتیاز</b> پاداش گرفت!"
            for p in duel["team1"]:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, p["id"]))
            for p in duel["team2"]:
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, p["id"]))
            winning_team = duel["team1"]
        elif t2_score > t1_score:
            text += f"🎉 تبریک! <b>تیم ۲</b> پیروز شد و هر بازیکن <b>+{stake} امتیاز</b> پاداش گرفت!"
            for p in duel["team2"]:
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (stake, p["id"]))
            for p in duel["team1"]:
                await db.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id = ?", (stake, p["id"]))
            winning_team = duel["team2"]
        else:
            text += "🤝 رقابت دو تیم مساوی شد! هیچ امتیازی کسر نگردید."
        await db.commit()

    for p in winning_team:
        await profile_record_duel_win(p["id"])

    ACTIVE_TEAM_DUELS.pop(duel_id, None)
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
        await update.effective_message.reply_text("🟢 <b>Ch Mode اختصاصی فعال شد.</b> پاسخ‌ها درست ثبت می‌شوند.", parse_mode="HTML")
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

    elif data == "claim_quests":
        today_str = get_iran_now().strftime("%Y-%m-%d")
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT penalties_played, card_matches_played, predictions_made, is_claimed FROM daily_quests WHERE user_id = ? AND date_str = ?", (uid, today_str)) as cur:
                row = await cur.fetchone()
            if row and row[0] >= 2 and row[1] >= 1 and row[2] >= 1 and not row[3]:
                await db.execute("UPDATE users SET points = points + 100 WHERE user_id = ?", (uid,))
                await db.execute("UPDATE daily_quests SET is_claimed = 1 WHERE user_id = ? AND date_str = ?", (uid, today_str))
                await db.commit()
                await profile_add_xp(uid, 50)
                await query.answer("🎁 جایزه ۱۰۰ امتیازی و ۵۰ XP با موفقیت دریافت شد!", show_alert=True)
                await quests_cmd(update, context)
            else:
                await query.answer("ماموریت‌ها هنوز تکمیل نشده است!", show_alert=True)

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
        matches = await provider.get_matches(target_date.strftime("%Y%m%d"), league_code=league_code)
        title = LEAGUE_TITLES.get(league_code, "مسابقات فوتبال")
        day_label = "امروز" if is_today else "فردا"

        if not matches:
            await safe_edit_message(query, f"⏳ مسابقه‌ای برای <b>{title}</b> در {day_label} یافت نشد.", reply_markup=kb.get_back_button())
            return

        text = f"⚽️ <b>برنامه مسابقات {title} ({day_label}):</b>\n────────────────────\n\n"
        for m in matches[:10]:
            MATCH_CACHE[m["id"]] = m
            time_str = format_iran_time(m.get("date"))
            status = m.get("status", "UPCOMING")
            badge = f"🔴 [{m['home_score']} - {m['away_score']}]" if status in ["LIVE", "IN_PLAY", "HT"] else (f"🏁 [{m['home_score']} - {m['away_score']}]" if status in ["FINISHED", "FT"] else f"⏰ <code>{time_str}</code>")
            text += f"▫️ <b>{m['home_team']}</b> 🆚 <b>{m['away_team']}</b>\n    └ {badge}  •  {m.get('venue', 'ورزشگاه')}\n\n"
        await safe_edit_message(query, text + "────────────────────", reply_markup=kb.get_back_button())

    elif data.startswith("table_"):
        league_code = data.replace("table_", "")
        standings = await provider.get_standings(league_code)
        title = LEAGUE_TITLES.get(league_code, "جدول رده‌بندی")
        if not standings:
            await safe_edit_message(query, f"جدول {title} در دسترس نیست.", reply_markup=kb.get_back_button())
            return
        text = f"🏆 <b>جدول رده‌بندی {title}</b>\n<pre>#  | Team          | P  | Pts\n---+---------------+----+----\n"
        for idx, s in enumerate(standings[:10], 1):
            text += f"{idx:<2} | {s['team'][:13].ljust(13)} | {str(s['p'])[:2].rjust(2)} | {str(s['pts'])[:3].rjust(3)}\n"
        text += "</pre>"
        await safe_edit_message(query, text, reply_markup=kb.get_back_button())

    elif data == "predictions_hub":
        await predictions_hub_handler(query)

    elif data.startswith("select_pred_"):
        match_id = data.replace("select_pred_", "")
        m = MATCH_CACHE.get(match_id)
        if not m: return
        time_str = format_iran_time(m.get("date"))
        text = f"🎯 <b>فرم ثبت پیش‌بینی:</b>\n────────────────────\n⚽️ <b>{m['home_team']}</b> 🆚 <b>{m['away_team']}</b>\n⏰ <code>{time_str}</code>\n────────────────────"
        await safe_edit_message(query, text, reply_markup=kb.get_prediction_keyboard(m['id']))

    elif data.startswith("pred_out_"):
        parts = data.split("_")
        match_id, choice = parts[2], parts[3]
        async with aiosqlite.connect(DATABASE_PATH) as db:
            try:
                await db.execute("INSERT INTO predictions (user_id, match_id, outcome_choice) VALUES (?, ?, ?)", (uid, match_id, choice))
                await db.execute("UPDATE users SET points = points + 10, total_predictions = total_predictions + 1 WHERE user_id = ?", (uid,))
                await db.commit()
                await profile_add_xp(uid, 20)
                await record_quest_action(uid, "predictions")
                await safe_edit_message(query, "✅ <b>پیش‌بینی ثبت شد! (+10 امتیاز)</b>", reply_markup=kb.get_back_button())
            except Exception:
                await safe_edit_message(query, "⚠️ شما قبلاً این بازی را پیش‌بینی کرده‌اید.", reply_markup=kb.get_back_button())

    elif data.startswith("pool_"):
        parts = data.split("_")
        match_id, choice = parts[1], parts[2]
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
                INSERT INTO special_pool_predictions (match_id, user_id, user_name, choice) VALUES (?, ?, ?, ?)
                ON CONFLICT(match_id, user_id) DO UPDATE SET choice = excluded.choice
            """, (match_id, uid, query.from_user.first_name, choice))
            await db.commit()
            async with db.execute("SELECT user_name, choice FROM special_pool_predictions WHERE match_id = ?", (match_id,)) as cur:
                participants = await cur.fetchall()

        m = MATCH_CACHE.get(match_id, {"home_team": "میزبان", "away_team": "میهمان", "date": None})
        await safe_edit_message(query, await generate_pool_message_text(m, participants), reply_markup=query.message.reply_markup)

    elif data == "view_market": await market_cmd(update, context)
    elif data == "open_sell_menu": await sell_menu_cmd(update, context)
    elif data == "view_my_cards": await my_cards_cmd(update, context)
    elif data == "view_lineup": await lineup_cmd(update, context)

    elif data == "auto_lineup":
        await auto_lineup_logic(uid)
        await query.answer("⚡️ قوی‌ترین ترکیب چیده شد!", show_alert=True)
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
            if not target or target["bought"]: return

            async with db.execute("SELECT points FROM users WHERE user_id = ?", (uid,)) as cur:
                pts = (await cur.fetchone())[0]
            if pts < target["price"]:
                await query.answer(f"امتیاز ناکافی! به {target['price']} PTS نیاز دارید.", show_alert=True)
                return

            await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (target["price"], uid))
            c = target["card"]
            await db.execute("INSERT INTO user_cards (user_id, player_name, rating, position, rarity, acquired_at) VALUES (?, ?, ?, ?, ?, ?)",
                             (uid, c["name"], c["ovr"], c["pos"], c["rarity"], today_str))
            target["bought"] = True
            await db.execute("UPDATE daily_market SET offers_json = ? WHERE user_id = ? AND date_str = ?", (json.dumps(offers, ensure_ascii=False), uid, today_str))
            await db.commit()

        await profile_add_xp(uid, 50)
        await query.answer(f"🎉 کارت {c['name']} خریداری شد!", show_alert=True)
        await market_cmd(update, context)

    elif data.startswith("sell_c_"):
        card_id = int(data.split("_")[2])
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT player_name, rarity, is_in_lineup FROM user_cards WHERE id = ? AND user_id = ?", (card_id, uid)) as cur:
                row = await cur.fetchone()
            if not row: return
            p_name, rar, in_lineup = row
            sell_price = SELL_PRICES.get(rar, 70)
            await db.execute("DELETE FROM user_cards WHERE id = ?", (card_id,))
            await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (sell_price, uid))
            await db.commit()

        if in_lineup: await auto_lineup_logic(uid)
        await query.answer(f"💰 کارت {p_name} با قیمت {sell_price} PTS فروخته شد!", show_alert=True)
        await sell_menu_cmd(update, context)

    elif data == "buy_pack_gold":
        pack_price = 250
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT points FROM users WHERE user_id = ?", (uid,)) as cur:
                pts = (await cur.fetchone())[0]
            if pts < pack_price:
                await query.answer("امتیاز ناکافی برای پک ۲۵۰ امتیازی!", show_alert=True)
                return
            await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (pack_price, uid))
            c = generate_random_card_by_rarity({"COMMON": 65, "RARE": 25, "ELITE": 9, "ICON": 1})
            await db.execute("INSERT INTO user_cards (user_id, player_name, rating, position, rarity, acquired_at) VALUES (?, ?, ?, ?, ?, ?)",
                             (uid, c["name"], c["ovr"], c["pos"], c["rarity"], get_iran_now().strftime("%Y-%m-%d")))
            await db.commit()

        await profile_add_xp(uid, 40)
        pop_msg = f"📦 <b>پک باز شد!</b>\n⭐️ <b>{c['name']}</b> ({c['pos']}) ➔ <b>{c['ovr']} OVR</b> {c.get('nation','')} | {RARITY_COLORS.get(c['rarity'])}"
        await query.message.reply_text(pop_msg, parse_mode="HTML")
        await market_cmd(update, context)

    elif data == "jackpot_hub": await jackpot_cmd(update, context)
    elif data.startswith("jk_start_"):
        rid = data.replace("jk_start_", "")
        USER_JACKPOT_DRAFTS[uid] = {"round_id": rid, "picks": {}}
        r_data = await get_or_create_jackpot_round()
        m = r_data["matches"][0]
        text = f"1️⃣ بازی اول:\n<b>{m['home']} ✕ {m['away']}</b>"
        kb_step = InlineKeyboardMarkup([
            [InlineKeyboardButton("برد ۱", callback_data=f"jk_p_{rid}_0_HOME"),
             InlineKeyboardButton("تساوی", callback_data=f"jk_p_{rid}_0_DRAW"),
             InlineKeyboardButton("برد ۲", callback_data=f"jk_p_{rid}_0_AWAY")]
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
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    await db.execute("INSERT OR REPLACE INTO jackpot_combos (user_id, user_name, round_id, predictions_json, status, created_at) VALUES (?, ?, ?, ?, 'PENDING', ?)",
                                     (uid, query.from_user.first_name, rid, json.dumps(draft["picks"]), get_iran_now().strftime("%Y-%m-%d %H:%M")))
                    await db.commit()
                await profile_add_xp(uid, 30)
                await query.message.reply_text("✅ <b>فرم جک‌پات ثبت شد!</b>", parse_mode="HTML")

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
        if p_id in ACTIVE_SHOOTOUTS:
            del ACTIVE_SHOOTOUTS[p_id]
            await safe_edit_message(query, "❌ چالش پنالتی لغو شد.")

    elif data.startswith("sht_"):
        parts = data.split("_")
        p_id, choice = f"{parts[1]}_{parts[2]}", parts[3]
        if p_id in ACTIVE_SHOOTOUTS and uid == ACTIVE_SHOOTOUTS[p_id]["current_turn"]:
            await execute_penalty_kick(context, p_id, choice)

    elif data.startswith("ac_cm_"):
        m_id = data.replace("ac_cm_", "")
        m = ACTIVE_CARD_MATCHES.get(m_id)
        if m and uid == m["p2"]["id"]:
            await safe_edit_message(query, "⚽️ <b>مسابقه آغاز شد! شبیه‌سازی زنده در جریان است...</b>")
            asyncio.create_task(run_live_card_match_simulation(context, m_id))

    elif data.startswith("rj_cm_"):
        m_id = data.replace("rj_cm_", "")
        if m_id in ACTIVE_CARD_MATCHES:
            del ACTIVE_CARD_MATCHES[m_id]
            await safe_edit_message(query, "❌ مسابقه کارت‌ها لغو شد.")

    elif data.startswith("acd_"):
        duel_id = data.replace("acd_", "")
        duel = ACTIVE_DUELS.get(duel_id)
        if duel and uid == duel["opponent"]["id"]: await proceed_duel(context, duel_id)

    elif data.startswith("rjd_"):
        duel_id = data.replace("rjd_", "")
        if duel_id in ACTIVE_DUELS:
            del ACTIVE_DUELS[duel_id]
            await safe_edit_message(query, "❌ چالش دوئل لغو گردید.")

    # ثبت پاسخ دوئل (بدون تداخل و همراه با مدیریت تمیز)
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

        if len(duel["answered"]) == 2:
            cancel_timer(context, f"duel_timer_{duel_id}_{q_idx}")
            duel["current_q"] += 1
            await proceed_duel(context, duel_id)
        else:
            await safe_edit_message(
                context.bot,
                render_duel_question_text(duel, q_data, q_idx),
                reply_markup=query.message.reply_markup,
                chat_id=duel["chat_id"],
                message_id=duel["message_id"]
            )

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

        if len(duel["answered"]) == len(all_players):
            cancel_timer(context, f"team_duel_timer_{duel_id}_{q_idx}")
            duel["current_q"] += 1
            await proceed_team_duel(context, duel_id)
        else:
            await safe_edit_message(
                context.bot,
                render_team_duel_question_text(duel, q_data, q_idx),
                reply_markup=query.message.reply_markup,
                chat_id=duel["chat_id"],
                message_id=duel["message_id"]
            )

    elif data == "user_profile": await user_profile_handler(query)
    elif data == "leaderboard_hub":
        await safe_edit_message(query, await show_leaderboard_text(uid), reply_markup=kb.get_back_button())

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
            await update.message.reply_text(f"🎉🔥 <b>پاسخ صحیح!</b> 👤 {game['names'][0]} | 🏆 برنده: <b>{html.escape(winner.first_name)}</b> (+{reward} PTS)", parse_mode="HTML")
            return

    if msg.lower() in ["اطلاعات", "info", "پروفایل", "stats"] or msg.lower().startswith(("/info", "اطلاعات")):
        target_user = update.effective_user
        if update.message.reply_to_message: target_user = update.message.reply_to_message.from_user
        await user_profile_handler(update.message, target_user=target_user)
        return

    if msg in ["دوئل", "duel", "چالش"]: await trigger_duel(update, context)
    elif msg in ["پنالتی", "پنالتی کشی", "penalty"]: await trigger_penalty_shootout(update, context)
    elif msg in ["مسابقه کارت", "کارت مچ", "cardmatch", "کارت"]: await trigger_card_match(update, context)
    elif msg in ["مارکت", "market", "خرید کارت"]: await market_cmd(update, context)
    elif msg in ["فروش", "فروش کارت", "sell"]: await sell_menu_cmd(update, context)
    elif msg in ["کارتها", "کارتهای من", "mycards"]: await my_cards_cmd(update, context)
    elif msg in ["ترکیب", "لاین اپ", "lineup"]: await lineup_cmd(update, context)
    elif msg in ["ماموریت", "ماموریتها", "ماموریت ها", "چالش", "quests"]: await quests_cmd(update, context)
    elif msg in ["لیگ", "جدول لیگ", "league"]: await league_cmd(update, context)
    elif msg in ["شوت", "گل", "shoot"]: await daily_shoot_cmd(update, context)
    elif msg in ["جایزه", "روزانه", "daily"]: await daily_reward_cmd(update, context)
    elif msg in ["حدس", "حدس بازیکن", "guess"]: await start_guess_game(update, context)
    elif msg in ["گردونه", "wheel", "شانس"]: await spin_wheel_cmd(update, context)
    elif msg in ["جکپات", "jackpot"]: await jackpot_cmd(update, context)
    elif msg in ["شروع", "منو", "فوتبال"]: await start(update, context)
    elif msg in ["جدول", "رنکینگ", "امتیازات"]: await leaderboard_cmd(update, context)

async def post_init(application: Application):
    await init_db()
    await ensure_escobar_ai()
    if getattr(application, "job_queue", None):
        application.job_queue.run_repeating(monitor_live_matches_and_banter, interval=90, first=5)
        application.job_queue.run_repeating(check_and_settle_monthly_season, interval=3600, first=15)
        application.job_queue.run_repeating(settle_jackpot_task, interval=7200, first=60)
        application.job_queue.run_repeating(simulate_daily_league_task, interval=14400, first=120)
        logger.info("PTB JobQueue is active.")
    else:
        logger.warning("PTB JobQueue is None. Falling back to native asyncio background tasks.")
        asyncio.create_task(run_repeating_task(monitor_live_matches_and_banter, application, 90, 5))
        asyncio.create_task(run_repeating_task(check_and_settle_monthly_season, application, 3600, 15))
        asyncio.create_task(run_repeating_task(settle_jackpot_task, application, 7200, 60))
        asyncio.create_task(run_repeating_task(simulate_daily_league_task, application, 14400, 120))

def main():
    threading.Thread(target=start_health_server, daemon=True).start()
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
    app.add_handler(CommandHandler("quests", quests_cmd))
    app.add_handler(CommandHandler("league", league_cmd))
    app.add_handler(CommandHandler("l_on", league_on_cmd))
    app.add_handler(CommandHandler("l_off", league_off_cmd))
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

    logger.info("Football Hub Bot running smoothly!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
