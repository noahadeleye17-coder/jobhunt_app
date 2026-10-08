import sqlite3
from pathlib import Path

from .models import Job, Profile
from .scoring import keep, score

BOARDS = {"remoteok", "remotive"}


def db(root: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(root / "jobs.db")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS jobs(
            id TEXT PRIMARY KEY, scope TEXT, company TEXT, tier TEXT, title TEXT, location TEXT, region TEXT,
            kind TEXT, url TEXT, posted TEXT, score INT, have TEXT, miss TEXT, email_notified INT DEFAULT 0,
            first_seen TEXT, last_seen TEXT, closed INT DEFAULT 0, notified INT DEFAULT 0)"""
    )
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)")}
    if "email_notified" not in columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN email_notified INT DEFAULT 0")
        connection.commit()
    return connection


def store(connection: sqlite3.Connection, jobs: list[Job], profile: Profile, now: str) -> int:
    ordered_jobs = sorted(jobs, key=lambda job: job.source in BOARDS)
    seen: set[tuple[str, str]] = set()
    kept = 0
    for job in ordered_jobs:
        dedupe_key = (job.company.casefold().strip(), job.title.casefold().strip())
        if dedupe_key in seen or not keep(job, profile):
            continue
        seen.add(dedupe_key)
        job_score, matched, missing = score(job, profile)
        connection.execute(
            """INSERT INTO jobs(id,scope,company,tier,title,location,region,kind,url,posted,score,have,miss,first_seen,last_seen)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 scope=excluded.scope, company=excluded.company, tier=excluded.tier, title=excluded.title,
                 location=excluded.location, region=excluded.region, kind=excluded.kind, url=excluded.url,
                 posted=excluded.posted, score=excluded.score, have=excluded.have, miss=excluded.miss,
                 last_seen=excluded.last_seen, closed=0""",
            (
                job.id, job.scope, job.company, job.tier, job.title, job.location, job.region, job.kind,
                job.url, job.posted, job_score, ",".join(matched), ",".join(missing), now, now,
            ),
        )
        kept += 1
    return kept


def close_missing(
    connection: sqlite3.Connection,
    scope: str,
    current_ids: set[str],
) -> int:
    existing = connection.execute(
        "SELECT id FROM jobs WHERE scope=? AND closed=0",
        (scope,),
    ).fetchall()
    stale_ids = [row["id"] for row in existing if row["id"] not in current_ids]
    if not stale_ids:
        return 0
    cursor = connection.executemany(
        "UPDATE jobs SET closed=1 WHERE scope=? AND closed=0 AND id=?",
        ((scope, job_id) for job_id in stale_ids),
    )
    return cursor.rowcount
