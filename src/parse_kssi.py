import re
import hashlib
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from datetime import timezone

MOT_RE = re.compile(r"motnumer=(\d+)")
MATCH_RE = re.compile(r"match/(\d+)")  # fallback if KSÍ uses match IDs in links

SCORE_RE = re.compile(r"\b(\d+)\s*[-–]\s*(\d+)\b")
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
DATE_RE = re.compile(r"\b\d{1,2}\.\s*\d{1,2}\.\s*\d{4}\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
# Iceland is UTC year-round; KSÍ sometimes includes tokens that dateutil doesn't know.
TZINFOS = {
    "BIRTU": timezone.utc,
    "ELKEM": timezone.utc,
    "AVIS": timezone.utc,
}

def stable_match_id(motnumer: str, kickoff_iso: str, home: str, away: str) -> str:
    raw = f"{motnumer}|{kickoff_iso}|{home.strip().lower()}|{away.strip().lower()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

def extract_motnumer_links(html: str):
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
        dt = dtparser.parse(t, dayfirst=True, fuzzy=True, tzinfos=TZINFOS)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return None

def _strip_score(text: str) -> str:
    return SCORE_RE.sub("", (text or "")).strip()

def _looks_like_datetime(text: str) -> bool:
    t = (text or "")
    return bool(TIME_RE.search(t) or DATE_RE.search(t))

def _split_front_datetime(text: str):
    """
    If a cell starts with date/time and then venue/team stuff, split it.
    Returns (kickoff_text_or_none, remainder_text).
    """
    t = (text or "").strip()
    if not t:
        return None, t

    # If there's a HH:MM, assume everything up to and including it is kickoff-ish.
    parts = t.split()
    time_idx = None
    for i, p in enumerate(parts):
        if re.fullmatch(r"\d{1,2}:\d{2}", p):
            time_idx = i
            break

    if time_idx is not None:
        kickoff_chunk = " ".join(parts[: time_idx + 1]).strip()
        remainder = " ".join(parts[time_idx + 1 :]).strip()
        # Only accept if kickoff_chunk actually parses
        if try_parse_kickoff(kickoff_chunk):
            return kickoff_chunk, remainder

    return None, t

def parse_matches_from_comp_page(html: str, motnumer: str, source_url: str):
    soup = BeautifulSoup(html, "lxml")
    rows = soup.find_all("tr")
    matches = []

    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue

        texts = [td.get_text(" ", strip=True) for td in tds]
        joined = " | ".join(texts)

        # Skip header-ish rows
        if any(x in joined.lower() for x in ["lið", "úrslit", "dagset", "staður", "umferð", "date", "time"]):
            continue

        # Score
        ft_home = ft_away = None
        mscore = SCORE_RE.search(joined)
        if mscore:
            ft_home, ft_away = int(mscore.group(1)), int(mscore.group(2))

        # Kickoff: try any cell that looks date/time-ish
        kickoff_utc = None
        kickoff_text = None
        for t in texts:
            if _looks_like_datetime(t):
                kt = try_parse_kickoff(t)
                if kt:
                    kickoff_utc = kt
                    kickoff_text = t
                    break

        # Team candidate cells: avoid date/time cells; strip scores
        teamish = []
        for t in texts:
            if not t:
                continue
            if _looks_like_datetime(t):
                continue
            cleaned = _strip_score(t)
            if len(cleaned) < 2:
                continue
            if re.fullmatch(r"\d+", cleaned):
                continue
            teamish.append(cleaned)

        # If still not enough, allow cells that might have embedded kickoff at the front
        if len(teamish) < 2:
            for t in texts:
                if not t:
                    continue
                cleaned = _strip_score(t)
                if len(cleaned) < 2:
                    continue
                teamish.append(cleaned)

        if len(teamish) < 2:
            continue

        # Choose home/away as the first two distinct non-empty teamish strings
        home = teamish[0].strip()
        away = next((x.strip() for x in teamish[1:] if x.strip() and x.strip() != home), None)
        if not away:
            continue

        # If home has embedded kickoff at the front, split it out
        if not kickoff_utc:
            ktxt, rem = _split_front_datetime(home)
            if ktxt:
                kickoff_utc = try_parse_kickoff(ktxt)
                home = rem or home

        # Same for away (rare)
        if not kickoff_utc:
            ktxt, rem = _split_front_datetime(away)
            if ktxt:
                kickoff_utc = try_parse_kickoff(ktxt)
                away = rem or away

        status = "played" if (ft_home is not None and ft_away is not None) else "scheduled"

        # Prefer match report URL if present
        a = tr.find("a", href=True)
        match_url = source_url
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
            "source_url": match_url,
        })

    # De-dupe by match_id
    dedup = {}
    for m in matches:
        dedup[m["match_id"]] = m
    return list(dedup.values())
