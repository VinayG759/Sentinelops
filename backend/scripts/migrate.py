"""Apply supabase/migrations/*.sql in order, once each.

Usage (from backend/):  uv run python scripts/migrate.py
Prints the target host first — check it before anything is applied.
"""

import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import REPO_ROOT, get_settings  # noqa: E402

MIGRATIONS = REPO_ROOT / "supabase" / "migrations"


def main() -> None:
    url = get_settings().supabase_db_url
    if not url:
        sys.exit("SUPABASE_DB_URL is empty in .env")
    print(f"Target database host: {urlparse(url).hostname}")

    with psycopg.connect(url, prepare_threshold=None, autocommit=True) as conn:
        conn.execute(
            "create table if not exists public.schema_migrations "
            "(name text primary key, applied_at timestamptz not null default now())"
        )
        conn.execute("alter table public.schema_migrations enable row level security")
        applied = {r[0] for r in conn.execute("select name from public.schema_migrations")}

        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in applied:
                print(f"  skip   {path.name}")
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("insert into public.schema_migrations (name) values (%s)", (path.name,))
            print(f"  apply  {path.name}")
    print("Done.")


if __name__ == "__main__":
    main()
