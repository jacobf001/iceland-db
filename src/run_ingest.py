from src.fetch import get
from src.load import db, upsert_competition, upsert_match
from src.kssi_sources import competitions_index_url, competition_url
from src.parse_kssi import extract_motnumer_links, parse_competition_name, parse_matches_from_comp_page

print(">>> KSÍ INGEST VERSION 2 ACTIVE <<<")


SEASON = 2025  # change as needed

def main():
    index_url = competitions_index_url(SEASON)
    index_html = get(index_url)

    print("INDEX_URL:", index_url)
    print("INDEX_HTML_LEN:", len(index_html))

    motnums = extract_motnumer_links(index_html)
    print("MOTNUMS_FOUND:", len(motnums))
    print("FIRST_10_MOTNUMS:", motnums[:10])
    if not motnums:
        raise RuntimeError(f"No motnumer links found on index page: {index_url}")

    # Start small to avoid hammering KSÍ on day 1:
    motnums = motnums[:50]  # remove this cap once confirmed working

    with db() as conn:
        with conn.transaction():
            for mot in motnums:
                url = competition_url(mot)
                html = get(url)

                name_raw = parse_competition_name(html)

                comp = {
                    "motnumer": mot,
                    "season": SEASON,
                    "gender": None,
                    "tier": None,
                    "name_raw": name_raw,
                    "group_label": None,
                    "source_url": url,
                }
                upsert_competition(conn, comp)

                matches = parse_matches_from_comp_page(html, mot, url)
                for m in matches:
                    upsert_match(conn, m)

if __name__ == "__main__":
    main()
