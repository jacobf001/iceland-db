import os
import psycopg
from psycopg.rows import dict_row


def db():
    """
    Connect using discrete env vars (avoids URL parsing / password encoding issues).
    Required env vars:
      PGHOST, PGUSER, PGPASSWORD
    Optional:
      PGPORT (default 5432), PGDATABASE (default postgres), PGSSLMODE (default require)
    """
    host = os.environ["PGHOST"]
    port = int(os.environ.get("PGPORT", "5432"))
    user = os.environ["PGUSER"]
    password = os.environ["PGPASSWORD"]
    database = os.environ.get("PGDATABASE", "postgres")
    sslmode = os.environ.get("PGSSLMODE", "require")

    return psycopg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=database,
        sslmode=sslmode,
        connect_timeout=10,
        options="-c statement_timeout=15000",
        row_factory=dict_row,
    )


def upsert_competition(conn, c: dict):
    conn.execute(
        """
        insert into competitions (motnumer, season, gender, tier, name_raw, group_label, source_url, updated_at)
        values (%(motnumer)s, %(season)s, %(gender)s, %(tier)s, %(name_raw)s, %(group_label)s, %(source_url)s, now())
        on conflict (motnumer) do update set
          season = excluded.season,
          gender = excluded.gender,
          tier = excluded.tier,
          name_raw = excluded.name_raw,
          group_label = excluded.group_label,
          source_url = excluded.source_url,
          updated_at = now()
        """,
        c,
    )


def upsert_match(conn, m):
    conn.execute(
        """
        insert into matches (
          match_id, motnumer, kickoff_utc,
          home_team_raw, away_team_raw,
          home_team_id, away_team_id,
          venue_raw, status, ft_home, ft_away, source_url
        ) values (
          %(match_id)s, %(motnumer)s, %(kickoff_utc)s,
          %(home_team_raw)s, %(away_team_raw)s,
          %(home_team_id)s, %(away_team_id)s,
          %(venue_raw)s, %(status)s, %(ft_home)s, %(ft_away)s, %(source_url)s
        )
        on conflict (match_id) do update set
          kickoff_utc = excluded.kickoff_utc,
          home_team_raw = excluded.home_team_raw,
          away_team_raw = excluded.away_team_raw,
          home_team_id = excluded.home_team_id,
          away_team_id = excluded.away_team_id,
          venue_raw = excluded.venue_raw,
          status = excluded.status,
          ft_home = excluded.ft_home,
          ft_away = excluded.ft_away,
          source_url = excluded.source_url,
          last_seen_at = now(),
          updated_at = now()
        """,
        m,
    )


def get_or_create_team(conn, name_canonical: str) -> int:
    """
    Insert team if it doesn't exist, return team_id.
    """
    name = (name_canonical or "").strip()
    if not name:
        raise ValueError("name_canonical is empty")

    row = conn.execute(
        """
        insert into teams (name_canonical)
        values (%s)
        on conflict (name_canonical) do update
          set name_canonical = excluded.name_canonical
        returning team_id
        """,
        (name,),
    ).fetchone()

    # psycopg returns a tuple-like row
    return row[0]

def upsert_team_alias(conn, alias: str, team_id: int) -> None:
    a = (alias or "").strip()
    if not a:
        return

    conn.execute(
        """
        insert into team_aliases (alias, team_id)
        values (%s, %s)
        on conflict (alias) do update
          set team_id = excluded.team_id
        """,
        (a, team_id),
    )

