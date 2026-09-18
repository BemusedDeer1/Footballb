from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("🔥 بازی‌های امروز", callback_data="select_matches_today"),
         InlineKeyboardButton("📅 بازی‌های فردا", callback_data="select_matches_tomorrow")],
        [InlineKeyboardButton("🎯 بخش پیش‌بینی", callback_data="predictions_hub"),
         InlineKeyboardButton("🏆 جداول لیگ‌ها", callback_data="select_standings_league")],
        [InlineKeyboardButton("👤 پروفایل کاربری", callback_data="user_profile"),
         InlineKeyboardButton("🏅 رنکینگ و جدول", callback_data="leaderboard_hub")],
        [InlineKeyboardButton("⭐ تیم‌های من", callback_data="my_teams"),
         InlineKeyboardButton("🔎 جستجوی تیم", callback_data="search_team")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_matches_leagues_keyboard(action_prefix="today"):
    """کیبورد بازی‌ها که شامل گزینه همه بازی‌ها نیز هست"""
    keyboard = [
        [InlineKeyboardButton("🇬🇧 لیگ جزیره (انگلیس)", callback_data=f"{action_prefix}_eng.1"),
         InlineKeyboardButton("🇪🇸 لالیگا (اسپانیا)", callback_data=f"{action_prefix}_esp.1")],
        [InlineKeyboardButton("🇮🇹 سری آ (ایتالیا)", callback_data=f"{action_prefix}_ita.1"),
         InlineKeyboardButton("🇩🇪 بوندسلیگا (آلمان)", callback_data=f"{action_prefix}_ger.1")],
        [InlineKeyboardButton("🇫🇷 لوشامپیونه (فرانسه)", callback_data=f"{action_prefix}_fra.1")],
        [InlineKeyboardButton("🌍 همه بازی‌های مهم", callback_data=f"{action_prefix}_all")],
        [InlineKeyboardButton("◀️ بازگشت به خانه 🏠", callback_data="home")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_standings_leagues_keyboard():
    """کیبورد جدول لیگ‌ها — بدون گزینه غیرمنطقی همه بازی‌ها"""
    keyboard = [
        [InlineKeyboardButton("🇬🇧 لیگ برتر انگلیس", callback_data="table_eng.1"),
         InlineKeyboardButton("🇪🇸 لالیگا اسپانیا", callback_data="table_esp.1")],
        [InlineKeyboardButton("🇮🇹 سری آ ایتالیا", callback_data="table_ita.1"),
         InlineKeyboardButton("🇩🇪 بوندسلیگا آلمان", callback_data="table_ger.1")],
        [InlineKeyboardButton("🇫🇷 لوشامپیونه فرانسه", callback_data="table_fra.1")],
        [InlineKeyboardButton("◀️ بازگشت به خانه 🏠", callback_data="home")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_upcoming_matches_keyboard(matches):
    keyboard = []
    for m in matches[:6]:
        btn_text = f"⚽ {m['home_team']} 🆚 {m['away_team']}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_pred_{m['id']}")])
    keyboard.append([InlineKeyboardButton("◀️ بازگشت به خانه 🏠", callback_data="home")])
    return InlineKeyboardMarkup(keyboard)

def get_prediction_keyboard(match_id):
    keyboard = [
        [
            InlineKeyboardButton("⚪ برد میزبان", callback_data=f"pred_out_{match_id}_HOME"),
            InlineKeyboardButton("🤝 تساوی", callback_data=f"pred_out_{match_id}_DRAW"),
            InlineKeyboardButton("🔵 برد میهمان", callback_data=f"pred_out_{match_id}_AWAY")
        ],
        [InlineKeyboardButton("◀️ بازگشت به مسابقات", callback_data="predictions_hub")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button(target="home"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ بازگشت به خانه 🏠", callback_data=target)]])
