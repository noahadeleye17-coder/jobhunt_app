import concurrent.futures as cf
import datetime as dt
import html
import re
import threading
from collections.abc import Callable, Iterable
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import Company, Job

UA = {"User-Agent": "jobhunt/0.2 (personal job search)"}
INTERN = re.compile(r"\bintern(ship)?s?\b|trainee|apprentice|new grad|graduate", re.I)
_thread_local = threading.local()
_skip_lock = threading.Lock()
_skipped = 0


def _session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        session = requests.Session()
        session.headers.update(UA)
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.mount("http://", HTTPAdapter(max_retries=retry))
        _thread_local.session = session
    return session


def get(url: str, **kwargs: Any) -> Any:
    response = _session().get(url, timeout=25, **kwargs)
    response.raise_for_status()
    return response.json()


def clean(value: Any) -> str:
    text = html.unescape(str(value or ""))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()[:8000]


def make_job(
    company: Company,
    source: str,
    external_id: Any,
    title: Any,
    location: Any,
    remote: Any,
    url: Any,
    posted: Any,
    text: Any,
    hint: Any = "",
) -> Job:
    if external_id is None or not str(external_id).strip():
        raise ValueError(f"{source} job is missing its external ID")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"{source} job {external_id} is missing its title")
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"{source} job {external_id} is missing its URL")
    normalized_location = clean(location)
    normalized_title = clean(title)
    normalized_posted = str(posted) if posted is not None else None
    hint_text = clean(hint)
    return Job(
        id=f"{source}:{external_id}",
        scope=company.job_scope,
        source=source,
        company=company.name,
        tier=company.tier,
        title=normalized_title,
        location=normalized_location,
        url=url.strip(),
        posted=normalized_posted,
        text=clean(text),
        remote=bool(remote) or "remote" in normalized_location.casefold() or "remote" in normalized_title.casefold(),
        kind="internship" if INTERN.search(normalized_title) or "intern" in hint_text.casefold() else "full-time",
    )


def skipped_count() -> int:
    return _skipped


def _build(rows: Iterable[Any], build: Callable[[Any], Job]) -> list[Job]:
    """Build jobs row by row; skip malformed postings, but fail the source if none are usable."""
    global _skipped
    rows = list(rows)
    jobs: list[Job] = []
    for row in rows:
        try:
            jobs.append(build(row))
        except (AttributeError, KeyError, TypeError, ValueError):
            with _skip_lock:
                _skipped += 1
    if rows and not jobs:
        raise ValueError("every posting in the response was malformed")
    return jobs


def greenhouse(company: Company) -> list[Job]:
    data = get(
        f"https://boards-api.greenhouse.io/v1/boards/{company.slug}/jobs",
        params={"content": "true"},
    )
    return _build(
        data["jobs"],
        lambda job: make_job(
            company, "greenhouse", job["id"], job["title"],
            (job.get("location") or {}).get("name"), None, job["absolute_url"],
            job.get("updated_at"), job.get("content"),
        ),
    )


def lever(company: Company) -> list[Job]:
    def build(job: dict[str, Any]) -> Job:
        categories = job.get("categories") or {}
        timestamp = job.get("createdAt")
        posted = (
            dt.datetime.fromtimestamp(timestamp / 1000, dt.timezone.utc).isoformat()
            if timestamp else None
        )
        return make_job(
            company, "lever", job["id"], job["text"], categories.get("location"),
            job.get("workplaceType") == "remote", job["hostedUrl"], posted,
            job.get("descriptionPlain"), categories.get("commitment", ""),
        )

    data = get(f"https://api.lever.co/v0/postings/{company.slug}", params={"mode": "json"})
    if not isinstance(data, list):
        raise ValueError("unexpected Lever response shape")
    return _build(data, build)


def ashby(company: Company) -> list[Job]:
    data = get(f"https://api.ashbyhq.com/posting-api/job-board/{company.slug}")
    return _build(
        data["jobs"],
        lambda job: make_job(
            company, "ashby", job["id"], job["title"], job.get("location"),
            job.get("isRemote"), job["jobUrl"], job.get("publishedAt"),
            job.get("descriptionPlain"), job.get("employmentType") or "",
        ),
    )


def remoteok(_: None) -> list[Job]:
    def build(job: dict[str, Any]) -> Job:
        company = Company(job.get("company", ""), "remoteok", "*", "board", "remoteok:*")
        return make_job(
            company, "remoteok", job["id"], job["position"], job.get("location"),
            True, job["url"], job.get("date"), job.get("description"),
        )

    return _build([job for job in get("https://remoteok.com/api")[1:] if job.get("position")], build)


def remotive(_: None) -> list[Job]:
    def build(job: dict[str, Any]) -> Job:
        company = Company(job["company_name"], "remotive", "*", "board", "remotive:*")
        return make_job(
            company, "remotive", job["id"], job["title"], job.get("candidate_required_location"),
            True, job["url"], job.get("publication_date"), job.get("description"),
            job.get("job_type", ""),
        )

    data = get("https://remotive.com/api/remote-jobs", params={"category": "software-dev"})
    return _build(data["jobs"], build)


FETCHERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
SourceKey = tuple[str, str]
SourceResult = tuple[str, list[Job] | Exception]


def fetch_all(companies: list[Company]) -> dict[SourceKey, SourceResult]:
    tasks: dict[SourceKey, tuple[Any, Company | None, str]] = {}
    for company in companies:
        key = (company.ats, company.name)
        if key in tasks:
            raise ValueError(f"Duplicate fetch task: {company.ats}/{company.name}")
        tasks[key] = (FETCHERS[company.ats], company, company.job_scope)
    tasks[("remoteok", "*")] = (remoteok, None, "remoteok:*")
    tasks[("remotive", "*")] = (remotive, None, "remotive:*")

    result: dict[SourceKey, SourceResult] = {}
    with cf.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetcher, company): (key, scope)
            for key, (fetcher, company, scope) in tasks.items()
        }
        for future in cf.as_completed(futures):
            key, scope = futures[future]
            try:
                result[key] = (scope, future.result())
            except Exception as exc:
                result[key] = (scope, exc)
    return result
