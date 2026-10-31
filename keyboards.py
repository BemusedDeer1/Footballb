from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_menu():
    """منوی اصلی شیک، مدرن، دسته‌بندی‌شده و متناسب با استانداردهای تلگرام"""
    keyboard = [
        [
            InlineKeyboardButton("⚡ مسابقات امروز", callback_data="select_matches_today"),
            InlineKeyboardButton("📅 مسابقات فردا", callback_data="select_matches_tomorrow")
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
            InlineKeyboardButton("🎯 پیش‌بینی مسابقات", callback_data="predictions_hub"),
            InlineKeyboardButton("🏦 جک‌پات هفتگی", callback_data="jackpot_hub")
        ],
        [
            InlineKeyboardButton("🎰 گردونه شانس", callback_data="spin_wheel"),
            InlineKeyboardButton("👤 پروفایل کاربری", callback_data="user_profile")
        ],
        [
            InlineKeyboardButton("🎖️ لیدربورد برترین‌ها", callback_data="leaderboard_hub")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_matches_leagues_keyboard(action_prefix="today"):
    """کیبورد انتخاب لیگ برای مشاهده بازی‌ها و پیش‌بینی"""
    keyboard = [
        [
            InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 لیگ برتر انگلیس", callback_data=f"{action_prefix}_eng.1"),
            InlineKeyboardButton("🇪🇸 لالیگا اسپانیا", callback_data=f"{action_prefix}_esp.1")
        ],
        [
            InlineKeyboardButton("🇮🇹 سری آ ایتالیا", callback_data=f"{action_prefix}_ita.1"),
            InlineKeyboardButton("🇩🇪 بوندسلیگا آلمان", callback_data=f"{action_prefix}_ger.1")
        ],
        [
            InlineKeyboardButton("🇫🇷 لیگ ۱ فرانسه", callback_data=f"{action_prefix}_fra.1"),
            InlineKeyboardButton("🏆 لیگ قهرمانان اروپا", callback_data=f"{action_prefix}_uefa.champions")
        ],
        [
            InlineKeyboardButton("🇮🇷 لیگ برتر ایران", callback_data=f"{action_prefix}_irn.1"),
            InlineKeyboardButton("🌍 تورنمنت‌های ملی و بین‌المللی", callback_data=f"{action_prefix}_all")
        ],
        [
            InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button():
    """دکمه استاندارد بازگشت به منوی اصلی"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")]
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
