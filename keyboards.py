from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_menu():
    """منوی اصلی شیک، مدرن، دسته‌بندی‌شده و متناسب با استانداردهای تلگرام"""
    keyboard = [
        [
            InlineKeyboardButton("⚡ مسابقات امروز", callback_data="select_matches_today"),
            InlineKeyboardButton("📅 بازی‌های فردا", callback_data="select_matches_tomorrow")
        ],
        [
            InlineKeyboardButton("🛡️ ترکیب و تیم من", callback_data="view_lineup"),
            InlineKeyboardButton("📋 تاکتیک‌های مربیگری", callback_data="open_tactics")
        ],
        [
            InlineKeyboardButton("🛒 مارکت و فروشگاه", callback_data="view_market"),
            InlineKeyboardButton("🏆 جدول لیگ سراسری", callback_data="select_standings_league")
        ],
        [
            InlineKeyboardButton("🎯 تالار پیش‌بینی", callback_data="predictions_hub"),
            InlineKeyboardButton("🎰 جک‌پات کمبو", callback_data="jackpot_hub")
        ],
        [
            InlineKeyboardButton("🎡 گردونه شانس", callback_data="spin_wheel"),
            InlineKeyboardButton("👤 پروفایل کاربری", callback_data="user_profile")
        ],
        [
            InlineKeyboardButton("🎖️ رده‌بندی سیزن (لیدربورد)", callback_data="leaderboard_hub")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_matches_leagues_keyboard(action_prefix="today"):
    """کیبورد انتخاب لیگ سازگار با تمامی پیشوندهای today و tmrw"""
    prefix = "today" if action_prefix == "today" else "tmrw"
    keyboard = [
        [
            InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 لیگ جزیره", callback_data=f"{prefix}_eng.1"),
            InlineKeyboardButton("🇪🇸 لالیگا", callback_data=f"{prefix}_esp.1")
        ],
        [
            InlineKeyboardButton("🇮🇹 سری آ", callback_data=f"{prefix}_ita.1"),
            InlineKeyboardButton("🇩🇪 بوندسلیگا", callback_data=f"{prefix}_ger.1")
        ],
        [
            InlineKeyboardButton("🇫🇷 لوشامپیونه", callback_data=f"{prefix}_fra.1"),
            InlineKeyboardButton("🏆 لیگ قهرمانان", callback_data=f"{prefix}_uefa.champions")
        ],
        [
            InlineKeyboardButton("🇮🇷 لیگ برتر ایران", callback_data=f"{prefix}_irn.1"),
            InlineKeyboardButton("🌍 بازی‌های ملی", callback_data=f"{prefix}_fifa.friendly")
        ],
        [
            InlineKeyboardButton("🌐 گلچین مسابقات معتبر", callback_data=f"{prefix}_all")
        ],
        [
            InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_standings_leagues_keyboard():
    """کیبورد انتخاب لیگ برای جدول رده‌بندی"""
    keyboard = [
        [
            InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 لیگ جزیره", callback_data="table_eng.1"),
            InlineKeyboardButton("🇪🇸 لالیگا", callback_data="table_esp.1")
        ],
        [
            InlineKeyboardButton("🇮🇹 سری آ", callback_data="table_ita.1"),
            InlineKeyboardButton("🇩🇪 بوندسلیگا", callback_data="table_ger.1")
        ],
        [
            InlineKeyboardButton("🇫🇷 لوشامپیونه", callback_data="table_fra.1"),
            InlineKeyboardButton("🇮🇷 لیگ برتر ایران", callback_data="table_irn.1")
        ],
        [
            InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button(target="home"):
    """دکمه استاندارد بازگشت"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data=target)]
    ])

def get_pagination_keyboard(current_page, total_pages, prefix):
    """کیبورد ناوبری و صفحه‌بندی فهرست‌ها"""
    buttons = []
    nav_row = []
    if current_page > 1:
        nav_row.append(InlineKeyboardButton("◀ قبلی", callback_data=f"{prefix}_page_{current_page - 1}"))
    nav_row.append(InlineKeyboardButton(f"صفحه {current_page} از {total_pages}", callback_data="noop"))
    if current_page < total_pages:
        nav_row.append(InlineKeyboardButton("بعدی ▶", callback_data=f"{prefix}_page_{current_page + 1}"))
    
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")])
    return InlineKeyboardMarkup(buttons)
