import hashlib
from dateutil import tz
from src.load import db, upsert_competition, upsert_match

def stable_match_id(motnumer: str, kickoff_iso: str, home: str, away: str) -> str:
    raw = f"{motnumer}|{kickoff_iso}|{home.strip().lower()}|{away.strip().lower()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

def main():
    # TODO: replace these with real parsed results from KSÍ pages
    competitions = [
        {
            "motnumer": "12345",
            "season": 2025,
            "gender": "M",
            "tier": "5",
            "name_raw": "5. deild karla - A riðill",
            "group_label": "A",
            "source_url": "https://example.com",
        }
    ]

    matches = [
        {
            "motnumer": "12345",
            "kickoff_utc": "2025-06-01T19:15:00Z",
            "home_team_raw": "Team A",
            "away_team_raw": "Team B",
            "venue_raw": "Some Stadium",
            "status": "scheduled",
            "ft_home": None,
            "ft_away": None,
            "source_url": "https://example.com/match/1",
        }
    ]

    with db() as conn:
        with conn.transaction():
            for c in competitions:
                upsert_competition(conn, c)

            for m in matches:
                m["match_id"] = stable_match_id(
                    m["motnumer"],
                    m["kickoff_utc"] or "",
                    m["home_team_raw"],
                    m["away_team_raw"],
                )
                upsert_match(conn, m)

if __name__ == "__main__":
    main()
