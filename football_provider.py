import aiohttp
from datetime import datetime, timedelta

class FootballDataProvider:
    def __init__(self):
        self.espn_base = "https://site.api.espn.com/apis/site/v2/sports/soccer"

    async def get_matches(self, date_str=None, league_code="eng.1"):
        """دریافت لیست بازی‌ها بر اساس تاریخ به صورت YYYYMMDD"""
        if not date_str:
            date_str = datetime.utcnow().strftime("%Y%m%d")
        
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
                                "venue": competition.get("venue", {}).get("fullName", "نامشخص")
                            })
                        return matches
            except Exception as e:
                print(f"Provider fetch error: {e}")
        return []

    async def get_standings(self, league_code="eng.1"):
        """دریافت جدول مسابقات"""
        url = f"https://site.api.espn.com/apis/v2/sports/soccer/{league_code}/standings"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        standings = []
                        entries = data.get("children", [{}])[0].get("standings", {}).get("entries", [])
                        for entry in entries[:10]: # نمایش ۱۰ تیم برتر
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
