from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("⚡ مسابقات امروز", callback_data="select_matches_today"),
         InlineKeyboardButton("📅 برنامه فردا", callback_data="select_matches_tomorrow")],
        [InlineKeyboardButton("🎯 تالار پیش‌بینی", callback_data="predictions_hub"),
         InlineKeyboardButton("🏆 جدول لیگ‌ها", callback_data="select_standings_league")],
        [InlineKeyboardButton("🎡 گردونه شانس", callback_data="spin_wheel"),
         InlineKeyboardButton("🎰 جک‌پات کمبو", callback_data="jackpot_hub")],
        [InlineKeyboardButton("👤 حساب کاربری", callback_data="user_profile"),
         InlineKeyboardButton("🎖 برترین‌ها", callback_data="leaderboard_hub")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_matches_leagues_keyboard(action_prefix="today"):
    keyboard = [
        [InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 لیگ جزیره", callback_data=f"{action_prefix}_eng.1"),
         InlineKeyboardButton("🇪🇸 لالیگا", callback_data=f"{action_prefix}_esp.1")],
        [InlineKeyboardButton("🇮🇹 سری آ", callback_data=f"{action_prefix}_ita.1"),
         InlineKeyboardButton("🇩🇪 بوندسلیگا", callback_data=f"{action_prefix}_ger.1")],
        [InlineKeyboardButton("🇫🇷 لوشامپیونه", callback_data=f"{action_prefix}_fra.1"),
         InlineKeyboardButton("🌐 گلچین اروپا", callback_data=f"{action_prefix}_all")],
        [InlineKeyboardButton("‹ بازگشت", callback_data="home")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_standings_leagues_keyboard():
    keyboard = [
        [InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League", callback_data="table_eng.1"),
         InlineKeyboardButton("🇪🇸 La Liga", callback_data="table_esp.1")],
        [InlineKeyboardButton("🇮🇹 Serie A", callback_data="table_ita.1"),
         InlineKeyboardButton("🇩🇪 Bundesliga", callback_data="table_ger.1")],
        [InlineKeyboardButton("🇫🇷 Ligue 1", callback_data="table_fra.1")],
        [InlineKeyboardButton("‹ بازگشت", callback_data="home")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_upcoming_matches_keyboard(matches):
    keyboard = []
    for m in matches[:8]:
        btn_text = f"⚽ {m['home_team']} ✕ {m['away_team']}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_pred_{m['id']}")])
    keyboard.append([InlineKeyboardButton("‹ بازگشت به منو", callback_data="home")])
    return InlineKeyboardMarkup(keyboard)

def get_prediction_keyboard(match_id):
    keyboard = [
        [
            InlineKeyboardButton("⚪ برد میزبان", callback_data=f"pred_out_{match_id}_HOME"),
            InlineKeyboardButton("🤝 مساوی", callback_data=f"pred_out_{match_id}_DRAW"),
            InlineKeyboardButton("🔴 برد میهمان", callback_data=f"pred_out_{match_id}_AWAY")
        ],
        [InlineKeyboardButton("‹ لیست مسابقات", callback_data="predictions_hub")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button(target="home"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("‹ بازگشت به منو", callback_data=target)]])
