import aiohttp
from datetime import datetime

# تطبیق نام انگلیسی تیم‌های لیگ ایران با نام فارسی
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
    "Chadormalou Ardakan": "چادرملو اردکان",
    "Fajr Sepasi": "فجر سپاسی شیراز",
    "Fajr Sepasi Shiraz": "فجر سپاسی شیراز",
    "Malavan": "ملوان بندرانزلی",
    "Malavan Bandar Anzali FC": "ملوان بندرانزلی",
    "Kheybar Khorramabad": "خیبر خرم‌آباد",
    "Kheybar Khorramabad FC": "خیبر خرم‌آباد",
    "Zob Ahan": "ذوب‌آهن اصفهان",
    "Esteghlal Khuzestan": "استقلال خوزستان",
    "Shams Azar Qazvin": "شمس‌آذر قزوین",
    "Mes Shahr Babak": "مس شهر بابک",
    "Mes Shahr-e Babak": "مس شهر بابک",
    "Sanat Naft": "صنعت نفت آبادان",
    "Havadar": "هوادار تهران",
    "Mes Rafsanjan": "مس رفسنجان"
}

class FootballDataProvider:
    def __init__(self):
        self.espn_base = "https://site.api.espn.com/apis/site/v2/sports/soccer"
        self.tsdb_base = "https://www.thesportsdb.com/api/v1/json/3"

    async def get_matches(self, date_str=None, league_code="eng.1"):
        """دریافت زنده مسابقات با تفکیک دقیق بازی‌های شروع‌نشده و تمام‌شده"""
        if not date_str:
            date_str = datetime.utcnow().strftime("%Y%m%d")

        # لیگ برتر ایران با شناسه رسمی 4742
        if league_code == "irn.1":
            url = f"{self.tsdb_base}/eventsnextleague.php?id=4742"
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
                                st = ev.get("strStatus", "")
                                
                                if st in ["Match Finished", "FT", "AET"]:
                                    status = "FINISHED"
                                elif "In Progress" in st or "Live" in st:
                                    status = "LIVE"
                                else:
                                    status = "UPCOMING"

                                matches.append({
                                    "id": str(ev.get("idEvent")),
                                    "league": "🇮🇷 لیگ برتر ایران",
                                    "home_team": IRAN_TEAMS_FA.get(h_name, h_name),
                                    "away_team": IRAN_TEAMS_FA.get(a_name, a_name),
                                    "home_score": ev.get("intHomeScore") if status != "UPCOMING" else None,
                                    "away_score": ev.get("intAwayScore") if status != "UPCOMING" else None,
                                    "status": status,
                                    "date": ev.get("dateEvent"),
                                    "venue": ev.get("strVenue") or "ورزشگاه اختصاصی"
                                })
                            if matches:
                                return matches
                except Exception as e:
                    print(f"Iran matches fetch error: {e}")
            return []

        # سایر لیگ‌های اروپایی از سرور رسمی ESPN
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
                            state = status_type.get("state", "").lower()
                            is_completed = status_type.get("completed", False)

                            # تفکیک دقیق:
                            # 1. بازی تمام شده
                            if is_completed or "FINAL" in type_name or "FULL_TIME" in type_name or state == "post":
                                status = "FINISHED"
                                h_score = home.get("score")
                                a_score = away.get("score")
                            # 2. بازی در حال برگزاری
                            elif "PROGRESS" in type_name or "HALFTIME" in type_name or state == "in":
                                status = "LIVE"
                                h_score = home.get("score")
                                a_score = away.get("score")
                            # 3. بازی شروع نشده (نتیجه نباید نشان داده شود)
                            else:
                                status = "UPCOMING"
                                h_score = None
                                a_score = None

                            matches.append({
                                "id": event["id"],
                                "league": data.get("leagues", [{}])[0].get("name", "فوتبال"),
                                "home_team": home["team"]["displayName"],
                                "away_team": away["team"]["displayName"],
                                "home_score": h_score,
                                "away_score": a_score,
                                "status": status,
                                "date": event.get("date"),
                                "venue": competition.get("venue", {}).get("fullName", "ورزشگاه اصلی")
                            })
                        return matches
            except Exception as e:
                print(f"Provider fetch error: {e}")
        return []

    async def get_standings(self, league_code="eng.1"):
        """دریافت زنده و آنلاین جدول رده‌بندی"""
        # جدول زنده لیگ برتر ایران با شناسه اصلاح‌شده 4742
        if league_code == "irn.1":
            # جدول مسابقات از سرور آزاد دیتابیس فوتبال
            url = f"{self.tsdb_base}/lookuptable.php?l=4742&s=2024-2025"
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
                    print(f"Iran Standings fetch error: {e}")
            return []

        # جدول زنده لیگ‌های اروپایی از ESPN
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
