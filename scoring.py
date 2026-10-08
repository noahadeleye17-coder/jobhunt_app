import re

from .models import Job, Profile

DEV = re.compile(
    r"engineer|developer|software|backend|back-end|frontend|front-end|full[\s-]?stack|"
    r"\bswe\b|devops|\bsre\b|mobile|programmer",
    re.I,
)
OK_REGION = re.compile(r"worldwide|anywhere|global|africa|nigeria|emea|international", re.I)
BAD_REGION = re.compile(
    r"\b(us|usa|united states|canada|uk|united kingdom|europe|eu|germany|france|spain|poland|"
    r"india|brazil|latam|latin america|apac|australia|mexico|netherlands|ireland|portugal|"
    r"singapore|japan|north america)\b",
    re.I,
)

VOCAB = {
    "javascript": r"javascript", "typescript": r"typescript", "python": r"python",
    "go": r"golang|(?-i:\bGo\b)", "rust": r"\brust\b", "java": r"\bjava\b", "kotlin": r"kotlin",
    "swift": r"\bswift\b", "c#": r"c#|\.net\b", "c++": r"c\+\+", "php": r"\bphp\b", "ruby": r"\bruby\b",
    "scala": r"\bscala\b", "elixir": r"elixir", "react": r"\breact\b", "react native": r"react[\s-]native",
    "next.js": r"next\.?js", "vue": r"\bvue(\.js)?\b", "angular": r"angular", "node.js": r"\bnode(\.?js)?\b",
    "express": r"express\.?js|(?-i:\bExpress\b)", "django": r"django", "flask": r"\bflask\b",
    "fastapi": r"fastapi", "spring": r"spring\s?boot", "rails": r"\brails\b", "laravel": r"laravel",
    "graphql": r"graphql", "rest": r"rest(ful)?[\s-]*(api|service|endpoint)s?", "grpc": r"grpc",
    "mongodb": r"mongo(db)?", "postgresql": r"postgres(ql)?", "mysql": r"mysql", "sql": r"\bsql\b",
    "redis": r"redis", "kafka": r"kafka", "elasticsearch": r"elasticsearch",
    "aws": r"\baws\b|amazon web services", "gcp": r"\bgcp\b|google cloud", "azure": r"azure",
    "docker": r"docker", "kubernetes": r"kubernetes|\bk8s\b", "terraform": r"terraform",
    "ci/cd": r"ci/cd|\bcicd\b", "github actions": r"github actions", "tailwind": r"tailwind",
    "cloudinary": r"\bcloudinary\b",
    "flutter": r"flutter", "oauth": r"oauth", "jwt": r"\bjwt\b",
    "llm": r"\bllms?\b|large language model", "machine learning": r"machine learning|\bml\b",
}
VOCAB_RX = {key: re.compile(pattern, re.I) for key, pattern in VOCAB.items()}


def keep(job: Job, profile: Profile) -> bool:
    if not DEV.search(job.title) or re.search(profile.exclude_titles, job.title, re.I) or not job.remote:
        return False
    if OK_REGION.search(job.location):
        job.region = "open"
    elif BAD_REGION.search(job.location):
        return False
    else:
        job.region = "unclear"
    return True


def score(job: Job, profile: Profile) -> tuple[int, list[str], list[str]]:
    text = f"{job.title} {job.text}"
    needed = {key for key, pattern in VOCAB_RX.items() if pattern.search(text)}
    matched = needed & profile.skills
    missing = needed - profile.skills

    def weight(skills: set[str] | frozenset[str]) -> int:
        return sum(2 if skill in profile.core else 1 for skill in skills)

    skill_score = weight(matched) / weight(needed) if needed else 0.4
    title_bonus = 0.15 if re.search(profile.prefer_titles, job.title, re.I) else 0
    final_score = round(min(1, 0.85 * skill_score + title_bonus) * 100)
    return final_score, sorted(matched), sorted(missing)
