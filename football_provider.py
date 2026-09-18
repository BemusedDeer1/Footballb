import aiohttp
from datetime import datetime

# نام‌های استاندارد فارسی برای تیم‌های لیگ برتر ایران
IRAN_TEAMS_FA = {
    "Tractor": "تراکتور",
    "Esteghlal": "استقلال تهران",
    "Persepolis": "پرسپولیس",
    "Sepahan": "سپاهان اصفهان",
    "Aluminium Arak": "آلومینیوم اراک",
    "Gol Gohar": "گل‌گهر سیرجان",
    "Foolad": "فولاد خوزستان",
    "Paykan": "پیکان",
    "Nassaji Mazandaran": "نساجی مازندران",
    "Chadormalu": "چادرملو اردکان",
    "Fajr Sepasi": "فجر سپاسی",
    "Malavan": "ملوان انزلی",
    "Kheybar Khorramabad": "خیبر خرم‌آباد",
    "Zob Ahan": "ذوب‌آهن",
    "Esteghlal Khuzestan": "استقلال خوزستان",
    "Shams Azar Qazvin": "شمس‌آذر قزوین",
    "Mes Shahr Babak": "مس شهر بابک",
    "Sanat Naft": "صنعت نفت آبادان"
}

class FootballDataProvider:
    def __init__(self):
        self.espn_base = "https://site.api.espn.com/apis/site/v2/sports/soccer"

    async def get_matches(self, date_str=None, league_code="eng.1"):
        """دریافت بازی‌های روز/فردا"""
        if not date_str:
            date_str = datetime.utcnow().strftime("%Y%m%d")

        # در صورتی که لیگ ایران انتخاب شده باشد از اندپوینت fotmob استفاده می‌شود
        if league_code == "irn.1":
            url = "https://www.fotmob.com/api/leagues?id=523"
            async with aiohttp.ClientSession() as session:
                try:
                    headers = {"User-Agent": "Mozilla/5.0"}
                    async with session.get(url, headers=headers, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            fixtures = data.get("fixtures", {}).get("allMatches", [])
                            matches = []
                            for m in fixtures[:6]:
                                h_name = m.get("home", {}).get("name", "میزبان")
                                a_name = m.get("away", {}).get("name", "میهمان")
                                h_fa = IRAN_TEAMS_FA.get(h_name, h_name)
                                a_fa = IRAN_TEAMS_FA.get(a_name, a_name)
                                matches.append({
                                    "id": str(m.get("id", "")),
                                    "league": "🇮🇷 لیگ برتر ایران",
                                    "home_team": h_fa,
                                    "away_team": a_fa,
                                    "home_score": m.get("home", {}).get("score"),
                                    "away_score": m.get("away", {}).get("score"),
                                    "status": "FINISHED" if m.get("status", {}).get("finished") else "UPCOMING",
                                    "date": m.get("status", {}).get("utcTime"),
                                    "venue": "ورزشگاه آزادی / اختصاصی"
                                })
                            return matches
                except Exception as e:
                    print(f"Error fetching Iran matches: {e}")
            return []

        # سایر لیگ‌های معتبر اروپایی
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
                            
                            status_type = event["status"]["type"]["name"]
                            status = "UPCOMING"
                            if "STATUS_IN_PROGRESS" in status_type or "HALFTIME" in status_type:
                                status = "LIVE"
                            elif "STATUS_FINAL" in status_type:
                                status = "FINISHED"

                            matches.append({
                                "id": event["id"],
                                "league": data.get("leagues", [{}])[0].get("name", "فوتبال"),
                                "home_team": home["team"]["displayName"],
                                "away_team": away["team"]["displayName"],
                                "home_score": home.get("score"),
                                "away_score": away.get("score"),
                                "status": status,
                                "date": event.get("date"),
                                "venue": competition.get("venue", {}).get("fullName", "ورزشگاه اصلی")
                            })
                        return matches
            except Exception as e:
                print(f"Provider fetch error: {e}")
        return []

    async def get_standings(self, league_code="eng.1"):
        """دریافت جدول لیگ‌ها بدون نیاز به هیچ توکنی"""
        
        # هندل کردن جدول لیگ برتر خلیج فارس
        if league_code == "irn.1":
            url = "https://www.fotmob.com/api/leagues?id=523"
            async with aiohttp.ClientSession() as session:
                try:
                    headers = {"User-Agent": "Mozilla/5.0"}
                    async with session.get(url, headers=headers, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            table_data = data.get("table", [{}])[0].get("data", {}).get("table", {}).get("all", [])
                            standings = []
                            for row in table_data[:10]:
                                en_name = row.get("name", "")
                                fa_name = IRAN_TEAMS_FA.get(en_name, en_name)
                                standings.append({
                                    "team": fa_name,
                                    "p": str(row.get("played", "0")),
                                    "w": str(row.get("wins", "0")),
                                    "d": str(row.get("draws", "0")),
                                    "l": str(row.get("losses", "0")),
                                    "pts": str(row.get("pts", "0"))
                                })
                            if standings:
                                return standings
                except Exception as e:
                    print(f"Iran table error: {e}")

        # جداول لیگ‌های اروپایی از سرور رسمی ESPN
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
                        return standings
            except Exception as e:
                print(f"Standings error: {e}")
        return []

provider = FootballDataProvider()
