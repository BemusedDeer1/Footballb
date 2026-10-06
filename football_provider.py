import logging
import aiohttp
from datetime import datetime
from config import LEAGUE_CODES

logger = logging.getLogger(__name__)

# ترجمه و تطبیق نام تیم‌های ملی و باشگاهی به زبان فارسی
TEAMS_FA = {
    # تیم‌های ملی پرطرفدار
    "Iran": "🇮🇷 تیم ملی ایران",
    "Argentina": "🇦🇷 آرژانتین",
    "Brazil": "🇧🇷 برزیل",
    "France": "🇫🇷 فرانسه",
    "Germany": "🇩🇪 آلمان",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 انگلیس",
    "Spain": "🇪🇸 اسپانیا",
    "Portugal": "🇵🇹 پرتغال",
    "Italy": "🇮🇹 ایتالیا",
    "Netherlands": "🇳🇱 هلند",
    "Croatia": "🇭🇷 کرواسی",
    "Uruguay": "🇺🇾 اروگوئه",
    "Belgium": "🇧🇪 بلژیک",
    "Japan": "🇯🇵 ژاپن",
    "South Korea": "🇰🇷 کره جنوبی",
    "Saudi Arabia": "🇸🇦 عربستان",
    "Qatar": "🇶🇦 قطر",
    "Uzbekistan": "🇺🇿 ازبکستان",
    "United Arab Emirates": "🇦🇪 امارات",
    "Iraq": "🇮🇶 عراق",
    "Morocco": "🇲🇦 مراکش",
    "Senegal": "🇸🇳 سنگال",
    "USA": "🇺🇸 آمریکا",
    "United States": "🇺🇸 آمریکا",
    # لیگ برتر ایران
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
    "Chador Malu Yazd": "چادرملو اردکان",
    "Chadormalu": "چادرملو اردکان",
    "Malavan": "ملوان بندرانزلی",
    "Kheybar Khorramabad": "خیبر خرم‌آباد",
    "Zob Ahan": "ذوب‌آهن اصفهان",
    "Esteghlal Khuzestan": "استقلال خوزستان",
    "Shams Azar Qazvin": "شمس‌آذر قزوین",
    "Mes Rafsanjan": "مس رفسنجان",
    "Havadar": "هوادار تهران"
}

class FootballDataProvider:
    def __init__(self):
        self.espn_base = "https://site.api.espn.com/apis/site/v2/sports/soccer"
        self.tsdb_base = "https://www.thesportsdb.com/api/v1/json/3"
        self._session = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=12)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def translate_team(self, name: str) -> str:
        if not name:
            return "تیم فوتبال"
        return TEAMS_FA.get(name, name)

    async def get_matches(self, date_str=None, league_code="eng.1"):
        """دریافت زنده مسابقات باشگاهی و بازی‌های ملی (فیفادی)"""
        if not date_str:
            date_str = datetime.utcnow().strftime("%Y%m%d")

        session = await self.get_session()

        # بخش گلچین (ترکیب لیگ‌های برتر و تورنمنت‌های ملی)
        if league_code == "all":
            all_matches = []
            selected_leagues = [
                "eng.1", "esp.1", "uefa.champions",
                "fifa.friendly", "uefa.nations", "fifa.worldq.afc", "fifa.worldq.uefa"
            ]
            for l_code in selected_leagues:
                try:
                    res = await self.get_matches(date_str, league_code=l_code)
                    if res:
                        all_matches.extend(res)
                except Exception as e:
                    logger.debug(f"Error fetching {l_code}: {e}")
            return all_matches

        # لیگ برتر ایران از TheSportsDB
        if league_code == "irn.1":
            url = f"{self.tsdb_base}/eventsnextleague.php?id=4742"
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        events = data.get("events") or []
                        matches = []
                        for ev in events[:8]:
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
                                "home_team": self.translate_team(h_name),
                                "away_team": self.translate_team(a_name),
                                "home_score": ev.get("intHomeScore") if status != "UPCOMING" else None,
                                "away_score": ev.get("intAwayScore") if status != "UPCOMING" else None,
                                "status": status,
                                "date": ev.get("dateEvent"),
                                "venue": ev.get("strVenue") or "ورزشگاه اختصاصی"
                            })
                        if matches:
                            return matches
            except Exception as e:
                logger.error(f"Iran matches fetch error: {e}")
            return []

        # سایر لیگ‌های اروپایی و مسابقات ملی از سرور ESPN
        url = f"{self.espn_base}/{league_code}/scoreboard?dates={date_str}"
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    matches = []
                    for event in data.get("events", []):
                        competition = event["competitions"][0]
                        competitors = competition.get("competitors", [])
                        if len(competitors) < 2:
                            continue

                        # تفکیک دقیق میزبان و میهمان بر اساس فیلد homeAway
                        if competitors[0].get("homeAway") == "home":
                            home = competitors[0]
                            away = competitors[1]
                        else:
                            home = competitors[1]
                            away = competitors[0]
                        
                        status_obj = event.get("status", {})
                        status_type = status_obj.get("type", {})
                        type_name = status_type.get("name", "").upper()
                        state = status_type.get("state", "").lower()
                        is_completed = status_type.get("completed", False)

                        if is_completed or "FINAL" in type_name or "FULL_TIME" in type_name or state == "post":
                            status = "FINISHED"
                            h_score = home.get("score")
                            a_score = away.get("score")
                        elif "PROGRESS" in type_name or "HALFTIME" in type_name or state == "in":
                            status = "LIVE"
                            h_score = home.get("score")
                            a_score = away.get("score")
                        else:
                            status = "UPCOMING"
                            h_score = None
                            a_score = None

                        league_name = data.get("leagues", [{}])[0].get("name", "فوتبال")
                        matches.append({
                            "id": event["id"],
                            "league": league_name,
                            "home_team": self.translate_team(home["team"]["displayName"]),
                            "away_team": self.translate_team(away["team"]["displayName"]),
                            "home_score": h_score,
                            "away_score": a_score,
                            "status": status,
                            "date": event.get("date"),
                            "venue": competition.get("venue", {}).get("fullName", "ورزشگاه اصلی")
                        })
                    return matches
        except Exception as e:
            logger.debug(f"Provider fetch error for {league_code}: {e}")
        return []

    async def get_standings(self, league_code="eng.1"):
        """دریافت جدول رده‌بندی لیگ‌ها"""
        session = await self.get_session()

        if league_code == "irn.1":
            url = f"{self.tsdb_base}/lookuptable.php?l=4742&s=2024-2025"
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        table_rows = data.get("table") or []
                        standings = []
                        for row in table_rows[:12]:
                            en_team = row.get("strTeam", "")
                            standings.append({
                                "team": self.translate_team(en_team),
                                "p": str(row.get("intPlayed", "0")),
                                "w": str(row.get("intWin", "0")),
                                "d": str(row.get("intDraw", "0")),
                                "l": str(row.get("intLoss", "0")),
                                "pts": str(row.get("intPoints", "0"))
                            })
                        if standings:
                            return standings
            except Exception as e:
                logger.error(f"Iran Standings fetch error: {e}")
            return []

        url = f"https://site.api.espn.com/apis/v2/sports/soccer/{league_code}/standings"
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    standings = []
                    children = data.get("children", [])
                    if children:
                        entries = children[0].get("standings", {}).get("entries", [])
                    else:
                        entries = data.get("standings", [{}])[0].get("entries", [])

                    for entry in entries[:12]:
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
            logger.debug(f"Standings error for {league_code}: {e}")
        return []

provider = FootballDataProvider()
