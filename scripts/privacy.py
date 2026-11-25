"""Shared private-data patterns (stdlib only). Used by sync, validate and CI scan."""
import re

PATTERNS = [
    ("absolute path", re.compile(r"(?:(?<![\w.])/(?:home|Users|root|tmp|var|etc|mnt|media|opt)/[^\s\"']+|\b[A-Za-z]:\\[^\s\"']+)")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("api key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}|\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{30,}|\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}\.")),
    ("long hex/base64 secret", re.compile(r"\b[0-9a-fA-F]{32,}\b|\b[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/])")),
    ("uuid", re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")),
    ("credential assignment", re.compile(r"(?i)\b(api[_-]?key|secret|passw(?:or)?d|token|bearer)\b\s*[:=]\s*\S{6,}")),
    ("vendor/licence id", re.compile(r"(?i)\b(?:licen[cs]e|vendor|order|asset)[ _-]?(?:id|no)\s*[:=#]?\s*[A-Za-z0-9-]{5,}")),
    ("internal agent id", re.compile(r"\b(?:agent|session)[-_ ]?id\b\s*[:=]\s*\S+", re.I)),
]


def find_private(text):
    """Return list of (label, snippet) for every private-data hit in text."""
    hits = []
    for label, rx in PATTERNS:
        for m in rx.finditer(text):
            hits.append((label, m.group(0)[:60]))
    return hits


def walk_strings(obj, path="$"):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_strings(k, path + ".<key>")
            yield from walk_strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_strings(v, f"{path}[{i}]")
