#!/usr/bin/env python3
"""Stdlib-only validation of data/progress.json (schema + cross-checks + privacy scan).
Usage: validate.py [path/to/progress.json]   exit 0 = ok"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import privacy  # noqa: E402
import stopwords  # noqa: E402

ROOT = os.path.dirname(HERE)
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "progress.json")
errors = []
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ST = {"completed", "in_progress", "testing", "planned"}
SP = {"none", "minor", "major"}
KI = {"open", "intermittent", "resolved", "uncertain"}
EV = {"review", "commit", "test"}
REF = {"коммит кода", "коммит документации", "ревью критика", "внутренний документ", "артефакт проверки"}
HASH = re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,10}\b")


def err(m):
    errors.append(m)


def need(o, key, typ, where, nullable=False):
    if key not in o:
        err(f"{where}: missing '{key}'"); return None
    v = o[key]
    if v is None and nullable:
        return v
    if not isinstance(v, typ) or (typ is not bool and isinstance(v, bool)):
        err(f"{where}.{key}: expected {typ.__name__}, got {type(v).__name__}"); return None
    return v


def date(v, where, nullable=False):
    if v is None and nullable:
        return
    if not isinstance(v, str) or not DATE.match(v):
        err(f"{where}: bad date {v!r}")


def allowed(o, keys, where):
    for k in o:
        if k not in keys:
            err(f"{where}: unexpected key '{k}'")


try:
    d = json.load(open(path, encoding="utf-8"))
except Exception as e:
    print(f"validate: cannot parse {path}: {e}"); sys.exit(1)

allowed(d, {"project", "updated", "current_milestone", "milestones", "tasks", "tests", "known_issues", "changelog", "sources"}, "$")
need(d, "project", str, "$")
date(d.get("updated"), "$.updated")
cm = need(d, "current_milestone", dict, "$") or {}
ms = need(d, "milestones", list, "$") or []
tasks = need(d, "tasks", list, "$") or []
tests = need(d, "tests", list, "$") or []
kis = need(d, "known_issues", list, "$") or []
chg = need(d, "changelog", list, "$") or []
srcs = need(d, "sources", list, "$") or []

mids = set()
for i, m in enumerate(ms):
    w = f"milestones[{i}]"
    allowed(m, {"id", "title", "public_title", "status", "packages", "gate", "spoiler", "uncertain", "note"}, w)
    mid = need(m, "id", str, w); need(m, "title", str, w); need(m, "public_title", str, w)
    if mid in mids: err(f"{w}: duplicate id {mid}")
    mids.add(mid)
    if m.get("status") not in ST: err(f"{w}: bad status {m.get('status')!r}")
    if m.get("status") == "completed" and any(t.get("milestone") == m.get("id") and t.get("status") == "in_progress" for t in tasks): err(f"{w}: completed with in-progress task")
    if m.get("spoiler") not in SP: err(f"{w}: bad spoiler")
    need(m, "packages", list, w)
    g = need(m, "gate", dict, w) or {}
    need(g, "verdict", str, w + ".gate"); date(g.get("date"), w + ".gate.date", True)
    if m.get("status") == "completed" and g.get("date") is None and m.get("packages"):
        err(f"{w}: completed milestone without gate date")

tids = set()
for i, t in enumerate(tasks):
    w = f"tasks[{i}]"
    allowed(t, {"id", "milestone", "title", "status", "priority", "summary", "details", "evidence", "spoiler", "uncertain"}, w)
    tid = need(t, "id", str, w)
    if tid in tids: err(f"{w}: duplicate id")
    tids.add(tid)
    for k in ("title", "summary", "details", "priority"): need(t, k, str, w)
    if t.get("milestone") not in mids: err(f"{w}: unknown milestone {t.get('milestone')!r}")
    if t.get("status") not in ST: err(f"{w}: bad status {t.get('status')!r}")
    if t.get("spoiler") not in SP: err(f"{w}: bad spoiler")
    ev = need(t, "evidence", list, w) or []
    for j, e in enumerate(ev):
        allowed(e, {"type", "ref", "date"}, f"{w}.evidence[{j}]")
        if e.get("type") not in EV: err(f"{w}.evidence[{j}]: bad type")
        if not isinstance(e.get("ref"), str) or e["ref"] not in REF: err(f"{w}.evidence[{j}]: bad ref {e.get('ref')!r}")
        date(e.get("date"), f"{w}.evidence[{j}].date")
    # status rule: completed needs verifiable evidence of a review
    if t.get("status") == "completed" and not any(e.get("type") == "review" for e in ev):
        err(f"{w}: completed without a review evidence")
    if t.get("status") == "completed" and t.get("spoiler") != "none" and False:
        pass
for m in ms:
    for p in m.get("packages", []):
        if "pkg-" + p not in tids: err(f"milestone {m['id']}: package {p} has no task")
if cm.get("id") not in mids: err("current_milestone.id unknown")

for i, t in enumerate(tests):
    w = f"tests[{i}]"
    need(t, "id", str, w); date(t.get("date"), w + ".date")
    if not all(x.strip() in mids for x in str(t.get("milestone")).split("/")): err(f"{w}: unknown milestone")
    for k in ("unit", "window"):
        o = t.get(k)
        if o is not None:
            for n in ("pass", "fail"):
                if not isinstance(o.get(n), int) or o[n] < 0: err(f"{w}.{k}.{n}: bad number")
            if o.get("skip") is not None and (not isinstance(o["skip"], int) or o["skip"] < 0): err(f"{w}.{k}.skip bad")
for i, k in enumerate(kis):
    w = f"known_issues[{i}]"
    need(k, "id", str, w); need(k, "title", str, w); need(k, "detail", str, w)
    if k.get("status") not in KI: err(f"{w}: bad status")
    if k.get("spoiler") not in SP: err(f"{w}: bad spoiler")
last = ""
for i, c in enumerate(chg):
    w = f"changelog[{i}]"
    date(c.get("date"), w + ".date")
    if last and c.get("date", "") > last: err(f"{w}: not sorted newest first")
    last = c.get("date", last)
    if not isinstance(c.get("items"), list) or not c["items"]: err(f"{w}: items")
for i, s in enumerate(srcs):
    for k in ("id", "name", "path", "used_for"): need(s, k, str, f"sources[{i}]")

for p, s in privacy.walk_strings(d):
    for pat in stopwords.hits(s):
        err(f"{p}: story stop-word /{pat}/: {s[:70]!r}")
    if HASH.search(s):
        err(f"{p}: commit hash in public data: {s[:70]!r}")
    if p.endswith(".spoiler_detail") or ".spoiler_detail" in p:
        err(f"{p}: spoiler_detail must not be published")
    for label, snip in privacy.find_private(s):
        err(f"{p}: private data ({label}): {snip!r}")

if errors:
    print(f"validate: {len(errors)} problem(s) in {path}")
    for e in errors[:50]: print("  - " + e)
    sys.exit(1)
print(f"validate: OK ({len(ms)} milestones, {len(tasks)} tasks, {len(tests)} tests, {len(kis)} issues, {len(chg)} changelog days)")
