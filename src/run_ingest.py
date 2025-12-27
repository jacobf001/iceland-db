print("RUN_INGEST STARTED")
print(">>> KSÍ INGEST VERSION 3 (INDEX NAME MAP) ACTIVE <<<")

from src.fetch import get
from src.load import db, upsert_competition, upsert_match, get_or_create_team, upsert_team_alias
from src.kssi_sources import competitions_index_url, competition_url
from src.parse_kssi import (
    extract_motnumer_links,
    parse_competitions_from_index,
    parse_matches_from_comp_page,
)

SEASON = 2025  # change as needed


def main():
    index_url = competitions_index_url(SEASON)
    index_html = get(index_url)

    print("INDEX_URL:", index_url)
    print("INDEX_HTML_LEN:", len(index_html))

    # Build competition metadata (name/gender/tier/group) from the index page
    comps = parse_competitions_from_index(index_html, year=SEASON)
    print("COMPS_FROM_INDEX:", len(comps))

    # Fallback: if parsing fails for some reason, at least get motnums
    motnums = list(comps.keys())
    if not motnums:
        motnums = extract_motnumer_links(index_html)

    print("MOTNUMS_FOUND:", len(motnums))
    print("FIRST_10_MOTNUMS:", motnums[:10])

    if not motnums:
        raise RuntimeError(f"No motnumer links found on index page: {index_url}")

    # Start small to avoid hammering KSÍ on day 1:
    # motnums = motnums[:50]  # remove this cap once confirmed working

    with db() as conn:
        with conn.transaction():
            # 1) Upsert competitions using the index-derived names (the important fix)
            for mot in motnums:
                url = competition_url(mot)

                comp = comps.get(mot) or {
                    "motnumer": mot,
                    "season": SEASON,
                    "gender": None,
                    "tier": None,
                    "name_raw": "Unknown competition",
                    "group_label": None,
                    "source_url": url,
                }

                # Ensure season + source_url always correct
                comp["season"] = SEASON
                comp["source_url"] = url

                upsert_competition(conn, comp)

            # 2) Now ingest matches (still using the competition page HTML)
            for mot in motnums:
                url = competition_url(mot)
                html = get(url)

                matches = parse_matches_from_comp_page(html, mot, url)
                for m in matches:
                    home_id = get_or_create_team(conn, m["home_team_raw"])
                    away_id = get_or_create_team(conn, m["away_team_raw"])

                    upsert_team_alias(conn, m["home_team_raw"], home_id)
                    upsert_team_alias(conn, m["away_team_raw"], away_id)

                    m["home_team_id"] = home_id
                    m["away_team_id"] = away_id

                    upsert_match(conn, m)


if __name__ == "__main__":
    main()
