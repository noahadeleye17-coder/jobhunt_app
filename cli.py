import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path
from typing import Sequence

from .config import ConfigError, load_config
from .email_delivery import EmailDeliveryError, send_digest
from .fetchers import fetch_all, skipped_count
from .models import Job, Profile
from .storage import close_missing, db, store

ROOT = Path(__file__).resolve().parent.parent


def render(rows: Sequence[sqlite3.Row], title: str) -> str:
    lines = [f"# {title}", ""]
    for kind, label in (("internship", "Internships"), ("full-time", "Roles")):
        section = [row for row in rows if row["kind"] == kind]
        if not section:
            continue
        lines += [f"## {label}", ""]
        for row in section:
            gaps = row["miss"].replace(",", ", ") or "none spotted"
            region = "" if row["region"] == "open" else " (region unclear: check posting)"
            lines += [
                f"- **{row['score']}** [{row['title']}]({row['url']}) at {row['company']} [{row['tier']}]",
                f"  {row['location'] or 'Remote'}{region} | matches: {row['have'].replace(',', ', ') or '-'} | gaps: {gaps}",
            ]
        lines.append("")
    return "\n".join(lines) if len(lines) > 2 else f"# {title}\n\nNothing new."


def pick(
    connection: sqlite3.Connection,
    profile: Profile,
    limit: int,
    only_new: bool,
    notification_column: str = "notified",
) -> list[sqlite3.Row]:
    if notification_column not in {"notified", "email_notified"}:
        raise ValueError(f"Unsupported notification column: {notification_column}")
    rows = []
    for kind in ("internship", "full-time"):
        query = "SELECT * FROM jobs WHERE closed=0 AND score>=? AND kind=?"
        if only_new:
            query += f" AND {notification_column}=0"
        rows.extend(
            connection.execute(query + " ORDER BY score DESC LIMIT ?", (profile.min_score, kind, limit)).fetchall()
        )
    return rows


def mark(connection: sqlite3.Connection, column: str, rows: Sequence[sqlite3.Row]) -> None:
    if column not in {"notified", "email_notified"}:
        raise ValueError(f"Unsupported notification column: {column}")
    if rows:
        placeholders = ",".join("?" for _ in rows)
        connection.execute(
            f"UPDATE jobs SET {column}=1 WHERE id IN ({placeholders})",
            [row["id"] for row in rows],
        )


def cmd_check() -> None:
    _, companies = load_config(ROOT)
    for (source, name), (_, result) in sorted(fetch_all(companies).items()):
        message = str(result) if isinstance(result, Exception) else f"{len(result)} jobs"
        print(f"{'FAIL' if isinstance(result, Exception) else ' ok '}  {source}/{name}: {message}")


def cmd_run() -> None:
    profile, companies = load_config(ROOT)
    results = fetch_all(companies)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    jobs: list[Job] = []
    successful: list[tuple[str, set[str]]] = []
    good_sources, bad_sources = [], []
    for (source, name), (scope, result) in results.items():
        if isinstance(result, Exception):
            bad_sources.append(f"{source}/{name}: {result}")
            continue
        good_sources.append(f"{source}:{name}")
        jobs.extend(result)
        successful.append((scope, {job.id for job in result}))
    if not good_sources:
        sys.exit("All sources failed:\n" + "\n".join(bad_sources))

    connection = db(ROOT)
    try:
        kept = store(connection, jobs, profile, now)
        closed = sum(close_missing(connection, scope, ids) for scope, ids in successful)
        today = dt.date.today().isoformat()
        rows = pick(connection, profile, 15, only_new=True)
        email_rows = pick(
            connection,
            profile,
            15,
            only_new=True,
            notification_column="email_notified",
        )
        text = render(rows, f"Job digest {today}")
        email_text = render(email_rows, f"Job digest {today}")
        if rows:
            path = ROOT / f"digest-{today}.md"
            earlier = path.read_text(encoding="utf-8") + "\n---\n\n" if path.exists() else ""
            path.write_text(earlier + text, encoding="utf-8")
        mark(connection, "notified", rows)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    email_sent, email_error = False, None
    try:
        email_sent = send_digest(f"Job digest {today}", email_text)
    except EmailDeliveryError as exc:
        email_error = exc
    if email_sent:
        connection = db(ROOT)
        try:
            mark(connection, "email_notified", email_rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    print(text)
    print(f"\n{len(good_sources)} sources ok, {len(bad_sources)} failed | {kept} matching jobs seen | {closed} closed since last run")
    skipped = skipped_count()
    if skipped:
        print(f"{skipped} malformed postings skipped")
    print(f"Email: {'sent' if email_sent else 'FAILED' if email_error else 'not configured'}")
    for failure in bad_sources:
        print("  FAILED", failure)
    if email_error:
        sys.exit(f"Email delivery error: {email_error}")


def cmd_top(limit: int) -> None:
    profile, _ = load_config(ROOT)
    connection = db(ROOT)
    try:
        print(render(pick(connection, profile, limit, only_new=False), "Top open jobs"))
    finally:
        connection.close()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("check", help="test every company source without database writes")
    subcommands.add_parser("run", help="fetch, score, store, and write today's digest")
    top = subcommands.add_parser("top", help="show the best open jobs")
    top.add_argument("n", nargs="?", type=int, default=15)
    args = parser.parse_args()

    try:
        if args.command == "check":
            cmd_check()
        elif args.command == "run":
            cmd_run()
        else:
            if args.n < 1:
                parser.error("top limit must be at least 1")
            cmd_top(args.n)
    except ConfigError as exc:
        parser.exit(2, f"Configuration error: {exc}\n")
    except EmailDeliveryError as exc:
        parser.exit(1, f"Email delivery error: {exc}\n")
