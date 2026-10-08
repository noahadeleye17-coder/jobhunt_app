from dataclasses import dataclass


@dataclass
class Job:
    id: str
    scope: str
    source: str
    company: str
    tier: str
    title: str
    location: str
    url: str
    posted: str | None
    text: str
    remote: bool
    kind: str
    region: str = "unclear"


@dataclass(frozen=True)
class Company:
    name: str
    ats: str
    slug: str
    tier: str
    scope: str | None = None

    @property
    def job_scope(self) -> str:
        return self.scope or f"{self.ats}:{self.name}"


@dataclass(frozen=True)
class Profile:
    skills: frozenset[str]
    core: frozenset[str]
    exclude_titles: str
    prefer_titles: str
    min_score: int
