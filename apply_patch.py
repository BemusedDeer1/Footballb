#!/usr/bin/env python3
"""
اسکریپت خودکار به‌روزرسانی bot.py در ۱ ثانیه
کافی است این اسکریپت را داخل پوشه پروژه اجرا کنید:
python apply_patch.py
"""

import os
import shutil

def main():
    bot_path = "bot.py"
    if not os.path.exists(bot_path):
        print("❌ فایل bot.py در این پوشه پیدا نشد! لطفاً این فایل را داخل پوشه اصلی پروژه قرار دهید.")
        return

    # پشتیبان‌گیری
    shutil.copyfile(bot_path, "bot.py.backup")
    print("📦 نسخه پشتیبان ساخته شد: bot.py.backup")

    with open(bot_path, "r", encoding="utf-8") as f:
        content = f.read()

    # رفع باگ split در صورت وجود
    if 'parts = data.split("_")' in content:
        content = content.replace('parts = data.split("_")', 'parts = data.split("_", 3)')
        print("✅ باگ ذخیره تاکتیک‌ها برطرف شد.")

    # افزودن پچ‌های هوشمند درست قبل از شروع برنامه (def main):
    inject_code = (
        "\n# --- FOOTBALL BOT PATCHES & UPGRADES ---\n"
        "try:\n"
        "    from bot_patches import *\n"
        "    if 'callback_router' in globals():\n"
        "        callback_router = wrap_callback_router(callback_router)\n"
        "except Exception as _patch_err:\n"
        "    print(f'Error loading patches: {_patch_err}')\n"
        "# --------------------------------------\n\n"
    )

    if "from bot_patches import *" not in content:
        if "def main():" in content:
            content = content.replace("def main():", inject_code + "def main():", 1)
            print("✅ تمامی توابع جدید و سیستم لیگ و تاکتیک‌ها با موفقیت روی bot.py ست شدند!")
        else:
            content += "\n" + inject_code
            print("✅ پچ به انتهای bot.py اضافه شد!")
    else:
        print("ℹ️ پچ قبلاً اعمال شده بود.")

    with open(bot_path, "w", encoding="utf-8") as f:
        f.write(content)

    print("\n🎉 تمام شد! فایل bot.py آماده است و بدون هیچ دستکاری دستی کار خواهد کرد.")

if __name__ == "__main__":
    main()
