from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("🔥 بازی‌های امروز", callback_data="matches_today"),
         InlineKeyboardButton("📅 بازی‌های فردا", callback_data="matches_tomorrow")],
        [InlineKeyboardButton("🎯 بخش پیش‌بینی", callback_data="predictions_hub"),
         InlineKeyboardButton("🏆 جداول لیگ‌ها", callback_data="standings_hub")],
        [InlineKeyboardButton("⭐ تیم‌های من", callback_data="my_teams"),
         InlineKeyboardButton("🔎 جستجوی تیم", callback_data="search_team")],
        [InlineKeyboardButton("👤 پروفایل کاربری", callback_data="user_profile"),
         InlineKeyboardButton("🏅 رنکینگ و جدول", callback_data="leaderboard_hub")],
        [InlineKeyboardButton("👥 لیگ دوستان", callback_data="private_leagues_hub")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button(target="home"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ بازگشت به خانه 🏠", callback_data=target)]])

def get_prediction_keyboard(match_id):
    keyboard = [
        [
            InlineKeyboardButton("⚪ برد میزبان", callback_data=f"pred_out_{match_id}_HOME"),
            InlineKeyboardButton("🤝 تساوی", callback_data=f"pred_out_{match_id}_DRAW"),
            InlineKeyboardButton("🔵 برد میهمان", callback_data=f"pred_out_{match_id}_AWAY")
        ],
        [
            InlineKeyboardButton("⚽ ثبت نتیجه عددی دقیق", callback_data=f"pred_score_{match_id}")
        ],
        [InlineKeyboardButton("◀️ بازگشت", callback_data="predictions_hub")]
    ]
    return InlineKeyboardMarkup(keyboard)
  
