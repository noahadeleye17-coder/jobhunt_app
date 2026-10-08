import json
import re
import sys
from pathlib import Path
from typing import Any

from .models import Company, Profile
from .scoring import VOCAB

SUPPORTED_ATS = frozenset({"greenhouse", "lever", "ashby"})


class ConfigError(ValueError):
    """Raised when a required JSON configuration is missing or invalid."""


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as exc:
        raise ConfigError(f"Required configuration file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc


def _string_list(value: Any, field: str, path: Path) -> frozenset[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ConfigError(f"{path}: '{field}' must be a list of non-empty strings")
    return frozenset(item.strip().lower() for item in value)


def load_config(root: Path) -> tuple[Profile, list[Company]]:
    profile_path = root / "profile.json"
    raw_profile = _read_json(profile_path)
    if not isinstance(raw_profile, dict):
        raise ConfigError(f"{profile_path}: expected a JSON object")

    skills = _string_list(raw_profile.get("skills"), "skills", profile_path)
    core = _string_list(raw_profile.get("core"), "core", profile_path)
    if not core.issubset(skills):
        raise ConfigError(f"{profile_path}: every core skill must also appear in skills")
    unknown = sorted(skills - VOCAB.keys())
    if unknown:
        print(
            f"Warning: {profile_path}: scorer cannot detect these skills: {', '.join(unknown)}",
            file=sys.stderr,
        )

    exclude_titles = raw_profile.get("exclude_titles")
    prefer_titles = raw_profile.get("prefer_titles")
    if not isinstance(exclude_titles, str) or not isinstance(prefer_titles, str):
        raise ConfigError(f"{profile_path}: 'exclude_titles' and 'prefer_titles' must be strings")
    for field, pattern in (("exclude_titles", exclude_titles), ("prefer_titles", prefer_titles)):
        try:
            re.compile(pattern, re.I)
        except re.error as exc:
            raise ConfigError(f"{profile_path}: invalid '{field}' regular expression: {exc}") from exc

    min_score = raw_profile.get("min_score")
    if isinstance(min_score, bool) or not isinstance(min_score, int) or not 0 <= min_score <= 100:
        raise ConfigError(f"{profile_path}: 'min_score' must be an integer from 0 to 100")
    profile = Profile(skills, core, exclude_titles, prefer_titles, min_score)

    companies_path = root / "companies.json"
    raw_companies = _read_json(companies_path)
    if not isinstance(raw_companies, list):
        raise ConfigError(f"{companies_path}: expected a JSON array")

    companies: list[Company] = []
    seen: set[tuple[str, str]] = set()
    seen_scopes = {"remoteok:*", "remotive:*"}
    for index, raw in enumerate(raw_companies):
        label = f"{companies_path}: entry {index + 1}"
        if not isinstance(raw, dict):
            raise ConfigError(f"{label} must be a JSON object")
        fields = ("name", "ats", "slug", "tier")
        if any(not isinstance(raw.get(field), str) or not raw[field].strip() for field in fields):
            raise ConfigError(f"{label} requires non-empty string fields: {', '.join(fields)}")
        name, ats, slug, tier = (raw[field].strip() for field in fields)
        if ats not in SUPPORTED_ATS:
            raise ConfigError(f"{label}: unsupported ats '{ats}'; expected one of {', '.join(sorted(SUPPORTED_ATS))}")
        scope = raw.get("scope")
        if scope is not None and (not isinstance(scope, str) or not scope.strip()):
            raise ConfigError(f"{label}: 'scope' must be a non-empty string when provided")
        key = (ats, name.casefold())
        if key in seen:
            raise ConfigError(f"{label}: duplicate company '{name}' for {ats}")
        seen.add(key)
        company = Company(name, ats, slug, tier, scope.strip() if scope else None)
        if company.job_scope in seen_scopes:
            raise ConfigError(f"{label}: duplicate source scope '{company.job_scope}'")
        seen_scopes.add(company.job_scope)
        companies.append(company)

    return profile, companies
