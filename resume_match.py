"""Local document reading and deterministic, explainable job ranking."""
import math
import re
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


def read_resume(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError("Resume file not found. Enter a PDF, DOCX or TXT file path.")
    suffix = path.suffix.lower()
    if suffix == ".txt":
        text = path.read_text(encoding="utf-8-sig")
    elif suffix == ".docx":
        try:
            with zipfile.ZipFile(path) as doc:
                root = ET.fromstring(doc.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            text = "\n".join("".join(t.text or "" for t in p.findall(".//w:t", ns))
                             for p in root.findall(".//w:p", ns))
        except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
            raise ValueError("Cannot read this DOCX. Save it again or export it as TXT.") from exc
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF support requires pypdf. Run python -m pip install -r requirements.txt.") from exc
        try:
            reader = PdfReader(path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ValueError("Cannot read this PDF. Use an unlocked text PDF or export it as TXT.") from exc
    else:
        raise ValueError("Use a text PDF, DOCX or UTF-8 TXT resume.")
    if not any(c.isalpha() for c in text):
        raise ValueError("No readable text found. For a scan, supply a searchable PDF or a text copy.")
    return text


STOP = set("""
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
TOKEN = re.compile(r"\.net\b|[^\W_]+(?:\+\+|#)?", re.UNICODE | re.I)


def tokens(text):
    text = re.sub(r"https?://\S+|www\.\S+|\S+@\S+", " ", text, flags=re.I)
    raw_words = TOKEN.findall(text.casefold())
    words = {t for t in raw_words
             if t not in STOP and not t.isnumeric() and (len(t) > 1 or t in {"c", "r"})}
    # Keep source adjacency. Punctuation and line breaks delimit phrases.
    bigrams = set()
    for segment in re.split(r"[\r\n.!?;:,|•]+", text.casefold()):
        adjacent = TOKEN.findall(segment)
        bigrams.update(f"{a} {b}" for a, b in zip(adjacent, adjacent[1:])
                       if a in words and b in words)
    return words | bigrams



def rank(jobs, resume):
    """Weight shared words and bigrams by rarity across the filtered listings; title hits count twice."""
    words = tokens(resume)
    if not words:
        raise ValueError("The resume contains no usable search terms. Check the extracted document.")
    frequency = Counter()
    fields = []
    for job in jobs:
        title = tokens(job["title"])
        body = tokens(job.get("description", ""))
        fields.append((title, title | body))
        frequency.update(title | body)
    for job, (title, vocabulary) in zip(jobs, fields):
        overlap = {}
        for term in words & vocabulary:
            rarity = 1 + math.log((1 + len(jobs)) / (1 + frequency[term]))
            overlap[term] = rarity * (2 if term in title else 1)
        norm = 1 + 0.05 * math.log1p(len(vocabulary))
        job["resume_score"] = round(sum(overlap.values()) / norm, 2)
        job["matched_terms"] = sorted(overlap, key=lambda t: (-overlap[t], t))[:12]
    jobs.sort(key=lambda j: (-j["resume_score"], j["title"].casefold(), j["company"].casefold()))
