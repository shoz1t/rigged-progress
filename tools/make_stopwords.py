#!/usr/bin/env python3
"""Build scripts/stopword_hashes.json from the PRIVATE plaintext list data/private/stopwords.txt.
Lines: 'p:stem' (prefix of a word or of a 2-3 word phrase) or 'w:word' (whole word). Lowercase, e instead of yo."""
import hashlib, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = os.path.join(ROOT, "data", "private", "stopwords.txt")
if not os.path.exists(src):
    sys.exit("private stopwords.txt missing")
out = sorted({hashlib.sha256(l.strip().replace("ё", "е").lower().encode()).hexdigest() for l in open(src, encoding="utf-8") if l.strip()})
json.dump(out, open(os.path.join(ROOT, "scripts", "stopword_hashes.json"), "w"), indent=0)
print(len(out), "hashes")
