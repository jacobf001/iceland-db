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

def parse_competition_name(html: str, motnumer: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    # Common generic titles we must ignore
    BAD = {
        "staða & úrslit",
        "staða og úrslit",
        "úrslit",
        "staða",
        "fixtures",
        "results",
    }

    # Grab candidate strings from headings + strong-ish elements first
    candidates = []

    for tag in soup.find_all(["h1","h2","h3","h4","strong","a","div","span"]):
        t = tag.get_text(" ", strip=True)
        if not t:
            continue
        tl = t.lower()
        if tl in BAD:
            continue
        # keep reasonable length candidates
        if 5 <= len(t) <= 120:
            candidates.append(t)

    # Fallback: also include any page text chunks
    if not candidates:
        for t in soup.stripped_strings:
            s = str(t).strip()
            if 5 <= len(s) <= 120 and s.lower() not in BAD:
                candidates.append(s)

    # Score candidates: prefer strings that look like Icelandic competition names
    def score(s: str) -> int:
        sl = s.lower()
        sc = 0

        # strong signals
        if "deild" in sl: sc += 50
        if "karla" in sl: sc += 40
        if "kvenna" in sl: sc += 40
        if "riðill" in sl: sc += 35
        if "bikar" in sl: sc += 25
        if "mót" in sl: sc += 10

        # tier patterns like "5. deild"
        if re.search(r"\b\d+\.\s*deild\b", sl): sc += 60

        # punish obviously not-a-title strings
        if "https://" in sl or "www." in sl: sc -= 50
        if "motnumer" in sl: sc -= 50
        if "veldu" in sl: sc -= 20
        if "smelltu" in sl: sc -= 20
        if sl in BAD: sc -= 200

        # small bonus if it contains Icelandic letters (often present in true names)
        if any(ch in s for ch in "ðþæöíúóáéý"): sc += 5

        return sc

    # De-dupe while preserving order
    seen = set()
    uniq = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)

    # Pick best
    best = None
    best_score = -10**9
    for c in uniq:
        sc = score(c)
        if sc > best_score:
            best_score = sc
            best = c

    # If we still ended up with generic, return Unknown
    if not best or best.lower() in BAD:
        return "Unknown competition"

    return best

import re

def infer_gender_tier(name_raw: str):
    n = (name_raw or "").lower()

    # gender
    gender = None
    if "kvenna" in n:
        gender = "W"
    elif "karla" in n:
        gender = "M"

    # competitions that should NOT get a tier
    CUP_WORDS = [
        "bikar", "bikarkeppni", "mjólkurbikar", "lengjubikar",
        "úrslitaleikur", "evrópuleikir", "utandeild", "fótbolti.net bikarinn",
        "meistarakeppni", "innanúss"
    ]
    if any(w in n for w in CUP_WORDS):
        return gender, None

    # tier 1 / 2 named leagues
    if "besta deild" in n:
        return gender, 1
    if "lengjudeild" in n:
        return gender, 2

    # numbered deilds are one tier BELOW the number (2.deild => tier 3, 3.deild => tier 4, etc)
    m = re.search(r"\b(\d+)\.\s*deild\b", n)
    if m:
        return gender, int(m.group(1)) + 1

    return gender, None

def parse_competitions_from_index(html: str, year: int):
    """
    Returns dict: motnumer -> {motnumer, season, name_raw, gender, tier, group_label, source_url}
    Extracts names from the year index page where they appear in plain HTML.
    """
    soup = BeautifulSoup(html, "lxml")
    comps = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = MOT_RE.search(href)
        if not m:
            continue

        mot = m.group(1)
        name = a.get_text(" ", strip=True)
        if not name:
            continue

        # ignore generic navigation items
        nl = name.lower()
        if nl in {"staða & úrslit", "staða og úrslit"}:
            continue

        gender, tier = infer_gender_tier(name)

        # group label e.g. "A riðill"
        group_label = None
        gm = re.search(r"\b([A-ZÁÐÉÍÓÚÝÞÆÖ])\s*riðill\b", name, flags=re.IGNORECASE)
        if gm:
            group_label = f"{gm.group(1).upper()} riðill"

        url = href if href.startswith("http") else f"https://www.ksi.is{href}"

        comps[mot] = {
            "motnumer": mot,
            "season": int(year),
            "gender": gender,
            "tier": tier,
            "name_raw": name,
            "group_label": group_label,
            "source_url": url,
        }

    return comps

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

LEIKUR_RE = re.compile(r"[?&]leikur=(\d+)")
WS_RE = re.compile(r"\s+")

def _clean(s: str) -> str:
    return WS_RE.sub(" ", (s or "")).strip()

def parse_matches_from_comp_page(html: str, motnumer: str, source_url: str):
    soup = BeautifulSoup(html, "lxml")
    matches = []

    # KSÍ match rows have: td[0]=date/time/venue, td[1]=ul.list.type2, td[2]=icons/links
    for tr in soup.select("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        team_ul = tds[1].select_one("ul.list.type2")
        if not team_ul:
            continue  # not a match row

        # --- match_id from leikur=... (preferred) ---
        match_id = None
        for a in tr.select('a[href*="leikur="]'):
            m = LEIKUR_RE.search(a.get("href", ""))
            if m:
                match_id = m.group(1)
                break

        # --- kickoff + venue from td[0] ---
        kickoff_raw = None
        venue_raw = None

        date_span = tds[0].select_one("span.date")
        if date_span:
            # Example text: "Mið. 7. 5. 2025 19:15"
            kickoff_raw = _clean(date_span.get_text(" ", strip=True))
            # Strip weekday tokens like "Mið." at the front if present
            kickoff_raw = re.sub(r"^[A-Za-zÁÐÉÍÓÚÝÞÆÖáðéíóúýþæö]+\.\s*", "", kickoff_raw)

        venue_a = tds[0].select_one("span.time a")
        if venue_a:
            venue_raw = _clean(venue_a.get_text(" ", strip=True))

        kickoff_utc = try_parse_kickoff(kickoff_raw) if kickoff_raw else None

        # --- teams + score from td[1] ---
        lis = team_ul.find_all("li", recursive=False)
        if len(lis) < 2:
            continue

        def parse_team(li):
            name_a = li.find("a")
            name = _clean(name_a.get_text(" ", strip=True)) if name_a else _clean(li.get_text(" ", strip=True))
            num_div = li.select_one("div.num")
            score = None
            if num_div:
                txt = _clean(num_div.get_text(" ", strip=True))
                if txt.isdigit():
                    score = int(txt)
            return name, score

        home_name, home_score = parse_team(lis[0])
        away_name, away_score = parse_team(lis[1])

        ft_home = home_score
        ft_away = away_score
        status = "played" if (ft_home is not None and ft_away is not None) else "scheduled"

        # If we couldn't find leikur=..., fall back to stable hash id
        if not match_id:
            match_id = stable_match_id(motnumer, kickoff_utc or "", home_name, away_name)

        matches.append({
            "match_id": str(match_id),
            "motnumer": motnumer,
            "kickoff_utc": kickoff_utc,
            "home_team_raw": home_name,
            "away_team_raw": away_name,
            "venue_raw": venue_raw,
            "status": status,
            "ft_home": ft_home,
            "ft_away": ft_away,
            # keep the competition page as source_url for now
            "source_url": source_url,
        })

    # De-dupe by match_id
    dedup = {}
    for m in matches:
        dedup[m["match_id"]] = m
    return list(dedup.values())

