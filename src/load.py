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


def upsert_match(conn, m: dict):
    conn.execute(
        """
        insert into matches (
          match_id, motnumer, kickoff_utc, home_team_raw, away_team_raw,
          venue_raw, status, ft_home, ft_away, source_url, last_seen_at, updated_at
        ) values (
          %(match_id)s, %(motnumer)s, %(kickoff_utc)s, %(home_team_raw)s, %(away_team_raw)s,
          %(venue_raw)s, %(status)s, %(ft_home)s, %(ft_away)s, %(source_url)s, now(), now()
        )
        on conflict (match_id) do update set
          motnumer = excluded.motnumer,
          kickoff_utc = excluded.kickoff_utc,
          home_team_raw = excluded.home_team_raw,
          away_team_raw = excluded.away_team_raw,
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
