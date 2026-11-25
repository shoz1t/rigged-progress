"""Story/spoiler stop-list stored as sha256 hashes only (plaintext lives in the untracked data/private/).
Text is normalised (lowercase, yo->e), split into words; every word, word prefix (>=3 chars) and every
2-3 word phrase prefix is hashed with a 'p:' (prefix) or 'w:' (whole word) tag and compared."""
import hashlib, json, os, re

_H = set(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "stopword_hashes.json"))))
_W = re.compile(r"[\w]+", re.U)


def _h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def hits(text):
    words = _W.findall(text.lower().replace("ё", "е"))
    found = []
    spans = []
    for n in (1, 2, 3):
        for i in range(len(words) - n + 1):
            spans.append(" ".join(words[i:i + n]))
    for sp in spans:
        if _h("w:" + sp) in _H:
            found.append(sp)
            continue
        for k in range(3, len(sp) + 1):
            if _h("p:" + sp[:k]) in _H:
                found.append(sp)
                break
    return sorted(set(found))
