from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_menu():
    keyboard = [
        [
            InlineKeyboardButton("⚡ مسابقات زنده و امروز", callback_data="select_matches_today"),
            InlineKeyboardButton("📅 بازی‌های فردا", callback_data="select_matches_tomorrow")
        ],
        [
            InlineKeyboardButton("🎯 تالار پیش‌بینی", callback_data="predictions_hub"),
            InlineKeyboardButton("🎰 جک‌پات کمبو (۵ مسابقه)", callback_data="jackpot_hub")
        ],
        [
            InlineKeyboardButton("🏆 جدول زنده لیگ‌ها", callback_data="select_standings_league"),
            InlineKeyboardButton("🎡 گردونه شانس", callback_data="spin_wheel")
        ],
        [
            InlineKeyboardButton("👤 حساب کاربری و افتخارات", callback_data="user_profile"),
            InlineKeyboardButton("🎖 جدول رده‌بندی سیزن", callback_data="leaderboard_hub")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_matches_leagues_keyboard(action_prefix="today"):
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
            InlineKeyboardButton("🇫🇷 لوشامپیونه فرانسه", callback_data=f"{action_prefix}_fra.1"),
            InlineKeyboardButton("🏆 لیگ قهرمانان اروپا", callback_data=f"{action_prefix}_uefa.champions")
        ],
        [
            InlineKeyboardButton("🇮🇷 لیگ برتر ایران", callback_data=f"{action_prefix}_irn.1"),
            InlineKeyboardButton("🌍 بازی‌های ملی و فیفادی", callback_data=f"{action_prefix}_fifa.friendly")
        ],
        [
            InlineKeyboardButton("🌐 همه بازی‌های معتبر روز", callback_data=f"{action_prefix}_all")
        ],
        [
            InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_standings_leagues_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League", callback_data="table_eng.1"),
            InlineKeyboardButton("🇪🇸 La Liga", callback_data="table_esp.1")
        ],
        [
            InlineKeyboardButton("🇮🇹 Serie A", callback_data="table_ita.1"),
            InlineKeyboardButton("🇩🇪 Bundesliga", callback_data="table_ger.1")
        ],
        [
            InlineKeyboardButton("🇫🇷 Ligue 1", callback_data="table_fra.1"),
            InlineKeyboardButton("🇮🇷 لیگ برتر خلیج فارس", callback_data="table_irn.1")
        ],
        [
            InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_upcoming_matches_keyboard(matches):
    keyboard = []
    for m in matches[:8]:
        btn_text = f"⚽️ {m['home_team']} ✕ {m['away_team']}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_pred_{m['id']}")])
    keyboard.append([InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="home")])
    return InlineKeyboardMarkup(keyboard)

def get_prediction_keyboard(match_id):
    keyboard = [
        [
            InlineKeyboardButton("⚪️ برد میزبان (1)", callback_data=f"pred_out_{match_id}_HOME"),
            InlineKeyboardButton("🤝 تساوی (X)", callback_data=f"pred_out_{match_id}_DRAW"),
            InlineKeyboardButton("🔴 برد میهمان (2)", callback_data=f"pred_out_{match_id}_AWAY")
        ],
        [
            InlineKeyboardButton("‹ تالار مسابقات", callback_data="predictions_hub"),
            InlineKeyboardButton("‹ منوی اصلی", callback_data="home")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_jackpot_match_keyboard(round_id, match_index, total_matches):
    keyboard = [
        [
            InlineKeyboardButton("⚪️ میزبان", callback_data=f"jk_pick_{round_id}_{match_index}_HOME"),
            InlineKeyboardButton("🤝 تساوی", callback_data=f"jk_pick_{round_id}_{match_index}_DRAW"),
            InlineKeyboardButton("🔴 میهمان", callback_data=f"jk_pick_{round_id}_{match_index}_AWAY")
        ],
        [
            InlineKeyboardButton("‹ انصراف و بازگشت", callback_data="jackpot_hub")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button(target="home"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data=target)]])
