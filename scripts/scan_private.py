#!/usr/bin/env python3
"""Scan every publishable text file of the repo for private data / secrets. Exit 1 on any hit."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import privacy  # noqa: E402

ROOT = os.path.dirname(HERE)
SKIP_DIRS = {"private", ".git", "_site", "node_modules", "fonts", "__pycache__"}
SKIP_FILES = {"privacy.py", "stopwords.py", "stopword_hashes.json", "REVIEW.md"}  # local-only or pattern definitions
TEXT = (".html", ".css", ".js", ".json", ".md", ".py", ".sh", ".yml", ".yaml", ".svg", ".txt", ".gitignore")
bad = 0
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in SKIP_DIRS]
    for fn in fns:
        if fn in SKIP_FILES or not fn.endswith(TEXT):
            continue
        p = os.path.join(dp, fn)
        rel = os.path.relpath(p, ROOT)
        try:
            text = open(p, encoding="utf-8").read()
        except UnicodeDecodeError:
            continue
        for label, snip in privacy.find_private(text):
            if snip == "noreply@anthropic.com" and rel.endswith((".sh", "scan_private.py")):
                continue  # commit trailer
            print(f"scan: {rel}: {label}: {snip!r}")
            bad += 1
if bad:
    print(f"scan: {bad} private-data hit(s)")
    sys.exit(1)
print("scan: clean")
