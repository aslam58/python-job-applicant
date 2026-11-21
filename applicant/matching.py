"""Location matching, employer presets, resume reading, and deterministic job ranking."""
from __future__ import annotations

import math
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree as ET

INDIA_BOARDS: list[dict[str, str]] = [
    {"type": "smartrecruiters", "token": "Freshworks", "company": "Freshworks", "country": "in"},
    {"type": "smartrecruiters", "token": "BoschGroup", "company": "Bosch Group", "country": "in"},
    {"type": "smartrecruiters", "token": "SopraSteria1", "company": "Sopra Steria", "country": "in"},
    {"type": "lever", "token": "cred", "company": "CRED"},
    {"type": "lever", "token": "smart-working-solutions", "company": "Smart Working Solutions"},
]

CITY_GROUPS: list[tuple[str, str]] = [
    ("bangalore", "bengaluru"),
    ("gurgaon", "gurugram"),
    ("vizag", "visakhapatnam"),
    ("bombay", "mumbai"),
    ("madras", "chennai"),
    ("calcutta", "kolkata"),
    ("cochin", "kochi"),
    ("trivandrum", "thiruvananthapuram"),
    ("pondicherry", "puducherry"),
]

INDIA_PLACES: set[str] = {
    "india", "chennai", "madurai", "hyderabad", "coimbatore", "kerala",
    "pune", "noida", "delhi", "new delhi", "ahmedabad", "jaipur",
    "indore", "chandigarh", "mohali", "kozhikode", "lucknow",
    "mysore", "mysuru", "nagpur", "vadodara", "surat", "bhubaneswar",
    "guwahati", "patna", "bhopal", "thane", "navi mumbai", "faridabad",
    "ghaziabad", "mangalore", "mangaluru", "vijayawada", "warangal",
}
INDIA_PLACES.update(name for group in CITY_GROUPS for name in group)

TITLE_VARIANTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"full[ -]?stack", re.I), "full stack"),
    (re.compile(r"front[ -]?end", re.I), "front end"),
    (re.compile(r"back[ -]?end", re.I), "back end"),
    (re.compile(r"dev[ -]?ops", re.I), "dev ops"),
    (re.compile(r"e[ -]?commerce", re.I), "e commerce"),
    (re.compile(r"micro[ -]?services?", re.I), "micro service"),
)


def normalize_location(value: str | None) -> str:
    text = re.sub(r"[^\w]+", " ", (value or "").casefold()).strip()
    for group in CITY_GROUPS:
        for name in group:
            text = re.sub(r"\b" + re.escape(name) + r"\b", group[0], text)
    return text


def _contains_india_place(place: str) -> bool:
    normalized = normalize_location(place)
    if not normalized:
        return False
    if normalized in INDIA_PLACES:
        return True
    parts = normalized.split()
    if any(part in INDIA_PLACES for part in parts):
        return True
    return any(f"{a} {b}" in INDIA_PLACES for a, b in zip(parts, parts[1:]))


def india_search(settings: Mapping[str, Any]) -> bool:
    india_cfg = settings.get("india", {})
    if isinstance(india_cfg, Mapping) and india_cfg.get("enabled", False):
        return True
    return any(_contains_india_place(place) for place in settings.get("location_keywords", []) if isinstance(place, str))


def effective_boards(
    settings: Mapping[str, Any],
    *,
    errors: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    raw_boards = list(settings.get("boards", []))
    if india_search(settings):
        india_cfg = settings.get("india", {})
        preset = india_cfg.get("boards", INDIA_BOARDS) if isinstance(india_cfg, Mapping) else INDIA_BOARDS
        if isinstance(preset, list):
            raw_boards.extend(preset)
        elif errors is not None:
            errors.append({"board": "india", "error": "india.boards must be a list of board objects"})
        else:
            raise ValueError("india.boards must be a list of board objects")

    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index, board in enumerate(raw_boards, 1):
        if not isinstance(board, dict):
            msg = f"Skipped board entry {index}: expected a JSON object"
            if errors is None:
                raise ValueError(msg)
            errors.append({"board": f"board[{index}]", "error": msg})
            continue
        kind = board.get("type")
        token = board.get("token")
        if not isinstance(kind, str) or not kind.strip() or not isinstance(token, str) or not token.strip():
            label = str(board.get("company") or token or f"board[{index}]")
            msg = "Board entry must include non-empty string 'type' and 'token'"
            if errors is None:
                raise ValueError(msg)
            errors.append({"board": label, "error": msg})
            continue
        country = str(board.get("country") or "").strip()
        key = (kind.strip().casefold(), token.strip().casefold(), country.casefold())
        unique.setdefault(key, board)
    return list(unique.values())


def normalize_phrase_variants(text: str) -> str:
    result = text
    for pattern, replacement in TITLE_VARIANTS:
        result = pattern.sub(replacement, result)
    return result


def contains_phrase(value: str, phrase: str) -> bool:
    cleaned = phrase.strip()
    return bool(cleaned and re.search(r"(?<!\w)" + re.escape(cleaned) + r"(?!\w)", value, re.I))


def matches(job: Mapping[str, Any], settings: Mapping[str, Any]) -> bool:
    title = normalize_phrase_variants(str(job["title"]))
    location = normalize_location(str(job.get("location", "")))
    include = settings.get("title_keywords", [])
    places = settings.get("location_keywords", [])
    exclude = settings.get("exclude_title_keywords", [])
    desc_keywords = settings.get("description_keywords", [])

    title_ok = not include or any(contains_phrase(title, normalize_phrase_variants(k)) for k in include)
    location_ok = not places or any(contains_phrase(location, normalize_location(k)) for k in places)
    exclude_ok = not any(contains_phrase(title, normalize_phrase_variants(k)) for k in exclude)
    if not (title_ok and location_ok and exclude_ok):
        return False
    if desc_keywords:
        haystack = normalize_phrase_variants(f"{job['title']} {job.get('description', '')}")
        return any(contains_phrase(haystack, normalize_phrase_variants(k)) for k in desc_keywords)
    return True


def _extract_docx_xml_text(xml_bytes: bytes) -> str:
    root = ET.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", ns):
        parts: list[str] = []
        for elem in paragraph.iter():
            local = elem.tag.rsplit("}", 1)[-1]
            if local == "t" and elem.text:
                parts.append(elem.text)
            elif local == "tab":
                parts.append(" ")
            elif local in {"br", "cr"}:
                parts.append("\n")
        line = "".join(parts)
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def read_resume(path: str | Path) -> str:
    target = Path(path)
    if not target.is_file():
        raise ValueError("Resume file not found. Enter a PDF, DOCX or TXT file path.")
    suffix = target.suffix.lower()
    if suffix == ".txt":
        text = target.read_text(encoding="utf-8-sig")
    elif suffix == ".docx":
        try:
            with zipfile.ZipFile(target) as doc:
                parts = [_extract_docx_xml_text(doc.read("word/document.xml"))]
                extras = sorted(
                    name for name in doc.namelist()
                    if re.fullmatch(r"word/(?:header|footer)\d*\.xml", name)
                )
                for extra in extras:
                    extracted = _extract_docx_xml_text(doc.read(extra))
                    if extracted:
                        parts.append(extracted)
                text = "\n".join(p for p in parts if p)
        except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
            raise ValueError("Cannot read this DOCX. Save it again or export it as TXT.") from exc
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF support requires pypdf. Run python -m pip install -r requirements.txt.") from exc
        try:
            reader = PdfReader(target)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ValueError("Cannot read this PDF. Use an unlocked text PDF or export it as TXT.") from exc
    else:
        raise ValueError("Use a text PDF, DOCX or UTF-8 TXT resume.")
    if not any(c.isalpha() for c in text):
        raise ValueError("No readable text found. For a scan, supply a searchable PDF or a text copy.")
    return text


STOP: set[str] = set("""
a about above across after all also am an and any application applications apply are as at
background be been being benefits both by can candidate candidates career careers company
contact could cv degree description duties each education email employer employment equal etc
excellent experience experienced for from full have having help how i if in including into is it
job jobs join key knowledge looking more most my new of on one only opportunity or other our
out over part people per position preferred professional professionals profile qualifications
qualified related relevant required requirements responsibilities responsible resume right role
skills some strong such support team teams than that the their them these they this those
through time to under understanding up us use used using we well what when where which who
will with within work worked working would year years you your
""".split())

SYNONYMS: dict[str, str] = {
    "js": "javascript",
    "ts": "typescript",
    "k8s": "kubernetes",
    "py": "python",
    "nodejs": "node.js",
    "nextjs": "next.js",
    "vuejs": "vue.js",
    "reactjs": "react.js",
    "postgres": "postgresql",
    "golang": "go",
}

_NO_SINGULARIZE_SUFFIXES = ("ss", "us", "is", "ics", "as", "os", "js", "ts", "ops")
_KEEP_PLURAL_FORM: set[str] = {"kubernetes", "postgres", "series", "species"}

TOKEN = re.compile(
    r"(?:asp)?\.net\b|"
    r"[a-z0-9]+\.js\b|"
    r"ci/cd\b|"
    r"a/b\b|"
    r"scikit-learn\b|"
    r"[^\W_]+(?:\+\+|#)?",
    re.UNICODE | re.I,
)

SEGMENT_SPLIT = re.compile(r"[\r\n!?;:,|•]+|\.(?!js\b|net\b)")


def _canonical_token(token: str) -> str:
    if token in SYNONYMS:
        return SYNONYMS[token]
    if token in _KEEP_PLURAL_FORM:
        return token
    if len(token) >= 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) >= 5 and token.endswith(("ches", "shes", "xes", "zes")):
        return token[:-2]
    if len(token) >= 5 and token.endswith("s") and not token.endswith(_NO_SINGULARIZE_SUFFIXES):
        return token[:-1]
    return token


def _is_usable_word(token: str) -> bool:
    return token not in STOP and not token.isnumeric() and (len(token) > 1 or token in {"c", "r"})


def tokens(text: str) -> set[str]:
    cleaned = re.sub(r"https?://\S+|www\.\S+|\S+@\S+", " ", text or "", flags=re.I)
    lowered = cleaned.casefold()
    raw_words = TOKEN.findall(lowered)
    words = {_canonical_token(t) for t in raw_words if _is_usable_word(t)}
    # Keep source adjacency. Punctuation and line breaks delimit phrases.
    bigrams: set[str] = set()
    for segment in SEGMENT_SPLIT.split(lowered):
        adjacent = TOKEN.findall(segment)
        mapped = [_canonical_token(t) if _is_usable_word(t) else None for t in adjacent]
        bigrams.update(
            f"{a} {b}"
            for a, b in zip(mapped, mapped[1:])
            if a is not None and b is not None and a != b
        )
    return words | bigrams


def rank(jobs: list[dict[str, Any]], resume: str) -> list[dict[str, Any]]:
    """Weight shared words and bigrams by rarity across the filtered listings; title hits count twice."""
    words = tokens(resume)
    if not words:
        raise ValueError("The resume contains no usable search terms. Check the extracted document.")
    frequency: Counter[str] = Counter()
    fields: list[tuple[set[str], set[str]]] = []
    for job in jobs:
        title = tokens(job["title"])
        body = tokens(job.get("description", ""))
        fields.append((title, title | body))
        frequency.update(title | body)
    for job, (title, vocabulary) in zip(jobs, fields):
        overlap: dict[str, float] = {}
        missing: dict[str, float] = {}
        for term in vocabulary:
            rarity = 1 + math.log((1 + len(jobs)) / (1 + frequency[term]))
            weight = rarity * (2 if term in title else 1)
            if term in words:
                overlap[term] = weight
            elif " " not in term:
                missing[term] = weight
        norm = 1 + 0.05 * math.log1p(len(vocabulary))
        job["resume_score"] = round(sum(overlap.values()) / norm, 2)
        job["matched_terms"] = sorted(overlap, key=lambda t: (-overlap[t], t))[:12]
        job["missing_terms"] = sorted(missing, key=lambda t: (-missing[t], t))[:8]
    jobs.sort(key=lambda j: (-j["resume_score"], j["title"].casefold(), j["company"].casefold()))
    return jobs
