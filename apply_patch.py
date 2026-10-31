#!/usr/bin/env python3
"""
اسکریپت خودکار اعمال پچ روی bot.py در ۱ ثانیه
اجرا: python apply_patch.py
"""

import os
import shutil

def main():
    bot_path = "bot.py"
    if not os.path.exists(bot_path):
        print("❌ فایل bot.py پیدا نشد! این فایل را داخل پوشه اصلی پروژه قرار دهید.")
        return

    # ساخت فایل بکاپ
    shutil.copyfile(bot_path, "bot.py.backup")
    print("📦 نسخه پشتیبان ساخته شد: bot.py.backup")

    with open(bot_path, "r", encoding="utf-8") as f:
        content = f.read()

    # رفع باگ split
    if 'parts = data.split("_")' in content:
        content = content.replace('parts = data.split("_")', 'parts = data.split("_", 3)')
        print("✅ باگ ذخیره تاکتیک‌ها برطرف شد.")

    # تزریق ماژول هماهنگ‌کننده پچ‌ها
    inject_code = (
        "\n# --- FOOTBALL BOT PATCHES & UPGRADES ---\n"
        "try:\n"
        "    import bot_patches\n"
        "    bot_patches.init_patches(globals())\n"
        "except Exception as _patch_err:\n"
        "    print(f'Error initializing patches: {_patch_err}')\n"
        "# --------------------------------------\n\n"
    )

    # پاک کردن تزریق‌های قبلی در صورت وجود
    if "from bot_patches import *" in content:
        content = content.replace("from bot_patches import *\ncallback_router = wrap_callback_router(callback_router)\n", "")
        content = content.replace("from bot_patches import *", "")
    if "import bot_patches\n    bot_patches.init_patches(globals())" in content:
        print("ℹ️ پچ قبلاً اعمال شده است.")
    else:
        if "def main():" in content:
            content = content.replace("def main():", inject_code + "def main():", 1)
            print("✅ ماژول هماهنگ‌کننده با موفقیت قبل از def main قرار گرفت!")
        else:
            content += "\n" + inject_code
            print("✅ پچ به انتهای فایل افزوده شد!")

    with open(bot_path, "w", encoding="utf-8") as f:
        f.write(content)

    print("\n🎉 تمام شد! فایل bot.py بدون هیچ دستکاری پیچیده‌ای آماده شد.")

if __name__ == "__main__":
    main()
