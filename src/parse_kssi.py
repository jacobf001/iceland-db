import re
import hashlib
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from datetime import timezone

MOT_RE = re.compile(r"motnumer=(\d+)")
MATCH_RE = re.compile(r"match/(\d+)")  # fallback if KSÍ uses match IDs in links

def stable_match_id(motnumer: str, kickoff_iso: str, home: str, away: str) -> str:
    raw = f"{motnumer}|{kickoff_iso}|{home.strip().lower()}|{away.strip().lower()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

def extract_motnumer_links(html: str):
    """
    Extract all motnumer IDs from a page.
    Works on pages that list competitions with links containing ?motnumer=XXXXX
    """
    motnums = set()
    for m in MOT_RE.finditer(html):
        motnums.add(m.group(1))
    return sorted(motnums)

def parse_competition_name(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find(["h1", "h2"])
    return h1.get_text(strip=True) if h1 else "Unknown competition"

def try_parse_kickoff(text: str):
    """
    Attempt to parse KSÍ-ish date strings.
    Returns ISO UTC string or None.
    """
    t = (text or "").strip()
    if not t:
        return None
    try:
        dt = dtparser.parse(t, dayfirst=True, fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return None

def parse_matches_from_comp_page(html: str, motnumer: str, source_url: str):
    """
    Very tolerant parser:
    - looks for table rows that contain two team-like cells and (optionally) a date/time cell and score.
    This will not be perfect on day 1, but it will ingest *something* consistently.
    """
    soup = BeautifulSoup(html, "lxml")

    rows = soup.find_all("tr")
    matches = []

    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue

        # Heuristics: find home/away by looking for " - " separator or two adjacent team columns
        texts = [td.get_text(" ", strip=True) for td in tds]
        joined = " | ".join(texts)

        # Skip obvious headers
        if any(x.lower() in joined.lower() for x in ["lið", "úrslit", "dagset", "staður", "umferð"]):
            continue

        # Find a score like "2 - 1" or "2–1"
        score = None
        ft_home = ft_away = None
        mscore = re.search(r"(\d+)\s*[-–]\s*(\d+)", joined)
        if mscore:
            ft_home, ft_away = int(mscore.group(1)), int(mscore.group(2))
            score = f"{ft_home}-{ft_away}"

        # Try to find two team names: common pattern is "... Home ... Away ..."
        # We'll grab the longest two non-date-ish strings.
        candidates = [t for t in texts if t and not re.search(r"\d{1,2}[./-]\d{1,2}", t)]
        candidates = [t for t in candidates if len(t) >= 2 and not re.fullmatch(r"\d+", t)]
        candidates = sorted(set(candidates), key=len, reverse=True)

        if len(candidates) < 2:
            continue

        home = candidates[0]
        away = candidates[1]

        # Try parse kickoff from any cell that looks date/time-ish
        kickoff_utc = None
        for t in texts:
            if re.search(r"\d{1,2}[./-]\d{1,2}", t) or re.search(r"\d{1,2}:\d{2}", t):
                kickoff_utc = try_parse_kickoff(t)
                if kickoff_utc:
                    break

        status = "played" if score else "scheduled"

        # Prefer match report URL if present
        a = tr.find("a", href=True)
        match_url = None
        match_id = None
        if a:
            href = a["href"]
            match_url = href if href.startswith("http") else href
            mid = MATCH_RE.search(href)
            if mid:
                match_id = mid.group(1)

        if not match_id:
            match_id = stable_match_id(motnumer, kickoff_utc or "", home, away)

        matches.append({
            "match_id": match_id,
            "motnumer": motnumer,
            "kickoff_utc": kickoff_utc,
            "home_team_raw": home,
            "away_team_raw": away,
            "venue_raw": None,
            "status": status,
            "ft_home": ft_home,
            "ft_away": ft_away,
            "source_url": match_url or source_url,
        })

    # De-dupe by match_id
    dedup = {}
    for m in matches:
        dedup[m["match_id"]] = m
    return list(dedup.values())
