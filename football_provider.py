import aiohttp
from datetime import datetime

# ترجمه و یکسان‌سازی نام تیم‌های لیگ برتر ایران
IRAN_TEAMS_FA = {
    "Tractor": "تراکتور تبریز",
    "Tractor Sazi": "تراکتور تبریز",
    "Esteghlal": "استقلال تهران",
    "Esteghlal FC": "استقلال تهران",
    "Persepolis": "پرسپولیس تهران",
    "Persepolis FC": "پرسپولیس تهران",
    "Sepahan": "سپاهان اصفهان",
    "Sepahan S.C.": "سپاهان اصفهان",
    "Aluminium Arak": "آلومینیوم اراک",
    "Gol Gohar": "گل‌گهر سیرجان",
    "Gol Gohar Sirjan": "گل‌گهر سیرجان",
    "Foolad": "فولاد خوزستان",
    "Foolad Khuzestan": "فولاد خوزستان",
    "Paykan": "پیکان تهران",
    "Nassaji Mazandaran": "نساجی مازندران",
    "Nassaji Mazandaran FC": "نساجی مازندران",
    "Chador Malu Yazd": "چادرملو اردکان",
    "Chadormalu": "چادرملو اردکان",
    "Fajr Sepasi": "فجر سپاسی شیراز",
    "Fajr Sepasi FC": "فجر سپاسی شیراز",
    "Malavan": "ملوان بندرانزلی",
    "Malavan Bandar Anzali FC": "ملوان بندرانزلی",
    "Kheybar Khorramabad": "خیبر خرم‌آباد",
    "Kheybar Khorramabad FC": "خیبر خرم‌آباد",
    "Zob Ahan": "ذوب‌آهن اصفهان",
    "Esteghlal Khuzestan": "استقلال خوزستان",
    "Shams Azar Qazvin": "شمس‌آذر قزوین",
    "Mes Shahr Babak": "مس شهر بابک",
    "Sanat Naft Abadan": "صنعت نفت آبادان"
}

class FootballDataProvider:
    def __init__(self):
        self.espn_base = "https://site.api.espn.com/apis/site/v2/sports/soccer"
        # اندپوینت رایگان و آزاد دیتای لیگ ایران
        self.tsdb_base = "https://www.thesportsdb.com/api/v1/json/3"

    async def get_matches(self, date_str=None, league_code="eng.1"):
        """دریافت زنده برنامه مسابقات و نتایج"""
        if not date_str:
            date_str = datetime.utcnow().strftime("%Y%m%d")

        # اگر لیگ ایران بود، دیتای زنده مسابقات از لیگ ۴۶۹۱ (Persian Gulf Pro League) دریافت می‌شود
        if league_code == "irn.1":
            url = f"{self.tsdb_base}/eventsnextleague.php?id=4691"
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            events = data.get("events") or []
                            matches = []
                            for ev in events[:6]:
                                h_name = ev.get("strHomeTeam", "میزبان")
                                a_name = ev.get("strAwayTeam", "میهمان")
                                matches.append({
                                    "id": str(ev.get("idEvent")),
                                    "league": "🇮🇷 لیگ برتر ایران",
                                    "home_team": IRAN_TEAMS_FA.get(h_name, h_name),
                                    "away_team": IRAN_TEAMS_FA.get(a_name, a_name),
                                    "home_score": ev.get("intHomeScore"),
                                    "away_score": ev.get("intAwayScore"),
                                    "status": "FINISHED" if ev.get("strStatus") == "Match Finished" else "UPCOMING",
                                    "date": ev.get("dateEvent"),
                                    "venue": ev.get("strVenue") or "ورزشگاه اصلی"
                                })
                            if matches:
                                return matches
                except Exception as e:
                    print(f"Live Iran matches fetch error: {e}")
            return []

        # سایر لیگ‌های اروپایی (ESPN)
        url = f"{self.espn_base}/{league_code}/scoreboard?dates={date_str}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        matches = []
                        for event in data.get("events", []):
                            competition = event["competitions"][0]
                            home = competition["competitors"][0]
                            away = competition["competitors"][1]
                            
                            status_obj = event.get("status", {})
                            status_type = status_obj.get("type", {})
                            type_name = status_type.get("name", "").upper()
                            is_completed = status_type.get("completed", False)

                            # رفع باگ نمایش وضعیت: اگر نتیجه داشت یا تایپ نهایی بود بازی تمام شده است
                            h_score = home.get("score")
                            a_score = away.get("score")

                            if is_completed or "FINAL" in type_name or "FULL_TIME" in type_name or "FT" in type_name:
                                status = "FINISHED"
                            elif "PROGRESS" in type_name or "HALFTIME" in type_name or "LIVE" in type_name:
                                status = "LIVE"
                            elif h_score is not None and a_score is not None:
                                status = "FINISHED"
                            else:
                                status = "UPCOMING"

                            matches.append({
                                "id": event["id"],
                                "league": data.get("leagues", [{}])[0].get("name", "فوتبال"),
                                "home_team": home["team"]["displayName"],
                                "away_team": away["team"]["displayName"],
                                "home_score": h_score,
                                "away_score": a_score,
                                "status": status,
                                "date": event.get("date"),
                                "venue": competition.get("venue", {}).get("fullName", "ورزشگاه اختصاصی")
                            })
                        return matches
            except Exception as e:
                print(f"Provider fetch error: {e}")
        return []

    async def get_standings(self, league_code="eng.1"):
        """دریافت زنده جدول رده‌بندی از وب بدون هیچ فایل دستی"""
        # جدول زنده لیگ برتر ایران از سرور زنده TheSportsDB (لیگ ۴۶۹۱)
        if league_code == "irn.1":
            # دریافت جدول آخرین فصل فعال
            url = f"{self.tsdb_base}/lookuptable.php?l=4691&s=2026-2027"
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            table_rows = data.get("table") or []
                            standings = []
                            for row in table_rows[:10]:
                                en_team = row.get("strTeam", "")
                                standings.append({
                                    "team": IRAN_TEAMS_FA.get(en_team, en_team),
                                    "p": str(row.get("intPlayed", "0")),
                                    "w": str(row.get("intWin", "0")),
                                    "d": str(row.get("intDraw", "0")),
                                    "l": str(row.get("intLoss", "0")),
                                    "pts": str(row.get("intPoints", "0"))
                                })
                            if standings:
                                return standings
                except Exception as e:
                    print(f"Live Iran Standings fetch error: {e}")
            return []

        # جدول زنده لیگ‌های اروپایی از سرور رسمی ESPN
        url = f"https://site.api.espn.com/apis/v2/sports/soccer/{league_code}/standings"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        standings = []
                        entries = data.get("children", [{}])[0].get("standings", {}).get("entries", [])
                        for entry in entries[:10]:
                            stats = {s["name"]: s.get("displayValue") for s in entry.get("stats", [])}
                            standings.append({
                                "team": entry["team"]["displayName"],
                                "p": stats.get("gamesPlayed", "0"),
                                "w": stats.get("wins", "0"),
                                "d": stats.get("ties", "0"),
                                "l": stats.get("losses", "0"),
                                "pts": stats.get("points", "0")
                            })
                        if standings:
                            return standings
            except Exception as e:
                print(f"Standings error: {e}")
        return []

provider = FootballDataProvider()
