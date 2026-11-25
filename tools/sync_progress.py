#!/usr/bin/env python3
"""Regenerate data/progress.json from the RIGGED project sources.

Deterministic rules (no network, stdlib only):
  * milestones/packages exist only if the technical roadmap lists them (section 3 / table in section 8);
  * a task is `completed` ONLY when the review verdict line it points to (a gate in
    data/overrides.json) is found in the review file and is PASS;
    otherwise: uncommitted work in the source tree -> `in_progress`;
    implemented but not PASS -> `testing`; nothing -> `planned`;
  * dates come from the review text (`Дата:`), else from git; evidence commits are verified in git;
  * changelog = hand-written lines (overrides) + automatic commit counters for anything newer;
  * public texts, titles, spoiler flags, priorities come from data/overrides.json;
  * output is built from an explicit allow-list of keys and every string is scanned for
    absolute paths, emails, tokens, vendor ids. Any hit aborts the run (exit 2).

Usage: sync_progress.py [--rigged-root DIR] [--out FILE] [--check] [--snapshot-counts]
"""
import argparse, datetime, json, os, re, subprocess, sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import privacy  # noqa: E402
import stopwords  # noqa: E402

STATUSES = ("completed", "in_progress", "testing", "planned")
SPOILERS = ("none", "minor", "major")


HASH = re.compile(r"[,;]?\s*\(?\b(?=[0-9a-f]*\d)[0-9a-f]{7,10}\b\)?")


def clean_text(s):
    """Replace private commit hashes in free text."""
    s = HASH.sub(" (коммит)", s)
    return re.sub(r"(коммит[а-я]*)\)?\s*\(коммит\)", r"\1", s).replace("  ", " ").replace("( коммит)", "(коммит)")


def public_source(raw):
    """Generalise an internal reference: never publish file names or hashes."""
    if not raw:
        return raw
    out = []
    for part in re.split(r";\s*", raw):
        if re.search(r"REVIEW|CRITIC", part):
            g = "ревью критика"
        elif re.search(r"@[0-9a-f]{7}|git log", part):
            g = "коммит"
        else:
            g = "внутренний документ"
        if g not in out:
            out.append(g)
    return "; ".join(out)


def deep_clean(o):
    if isinstance(o, str):
        return clean_text(o)
    if isinstance(o, list):
        return [deep_clean(x) for x in o]
    if isinstance(o, dict):
        return type(o)((k, deep_clean(v)) for k, v in o.items())
    return o


def merge_private(ov, pv):
    ov["gates"] = pv["gates"]
    for tid, p in pv["tasks"].items():
        if tid in ov["tasks"]:
            ov["tasks"][tid].update(p)
    for mid, p in pv["milestones"].items():
        if mid in ov["milestones"]:
            ov["milestones"][mid].update(p)
    for k in ov["known_issues"]:
        k.update({a: b for a, b in pv["known_issues"].get(k["id"], {}).items() if a == "source"})
    for t in ov["tests"]:
        t.update(pv["tests"].get(t["id"], {}))
    for s_ in ov["sources"]:
        s_.update(pv["sources"].get(s_["id"], {}))
    return ov


def die(msg, code=1):
    print("sync_progress: ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def warn(msg):
    print("sync_progress: warning: " + msg, file=sys.stderr)


class Project:
    def __init__(self, root):
        self.root = root
        self.src = os.path.join(root, "source")
        self.docs = os.path.join(root, "docs")
        for p in (self.src, self.docs):
            if not os.path.isdir(os.path.join(p, ".git")):
                die(f"not a git repository: {p}")
        self._git_cache = {}

    def git(self, repo, *args):
        key = (repo, args)
        if key not in self._git_cache:
            r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip())
            self._git_cache[key] = r.stdout
        return self._git_cache[key]

    def repo_for(self, ref_path):
        return self.docs  # all public refs point into docs/

    def resolve(self, ref_path):
        """'docs/build/x.md' -> absolute file inside the docs repo."""
        assert ref_path.startswith("docs/")
        return os.path.join(self.docs, ref_path[len("docs/"):])

    def file_date(self, ref_path):
        full = self.resolve(ref_path)
        if not os.path.exists(full):
            return None
        rel = os.path.relpath(full, self.docs)
        out = self.git(self.docs, "log", "-1", "--format=%cs", "--", rel).strip()
        if out:
            return out
        # untracked artifact: newest mtime inside
        newest = 0
        if os.path.isdir(full):
            for dp, _, fs in os.walk(full):
                for f in fs:
                    newest = max(newest, os.path.getmtime(os.path.join(dp, f)))
        else:
            newest = os.path.getmtime(full)
        return datetime.date.fromtimestamp(newest).isoformat() if newest else None

    def commit_date(self, which, h):
        repo = self.src if which == "source" else self.docs
        try:
            return self.git(repo, "show", "-s", "--format=%cs", h).strip().splitlines()[0]
        except RuntimeError:
            return None

    def package_commits(self, num):
        """Short hashes of source commits whose subject starts with 'Package <num>' (newest first)."""
        out = self.git(self.src, "log", "--format=%h %s")
        return [l.split()[0] for l in out.splitlines() if re.match(r"\S+ Package %s\b" % re.escape(num), l, re.I)]

    def commit_dates(self, which):
        repo = self.src if which == "source" else self.docs
        return self.git(repo, "log", "--format=%cs").split()

    def dirty_paths(self):
        out = self.git(self.src, "status", "--porcelain", "--untracked-files=all")
        res = []
        for line in out.splitlines():
            p = line[3:].split(" -> ")[-1].strip().strip('"')
            res.append(p)
        return res

    def dirty_mtime_date(self):
        newest = 0
        for p in self.dirty_paths():
            f = os.path.join(self.src, p)
            if os.path.exists(f):
                newest = max(newest, os.path.getmtime(f))
        return datetime.date.fromtimestamp(newest).isoformat() if newest else None


# ---------------------------------------------------------------- roadmap
def parse_roadmap(proj):
    path = os.path.join(proj.docs, "RIGGED_IMPLEMENTATION_ROADMAP.md")
    if not os.path.exists(path):
        die("roadmap not found")
    text = open(path, encoding="utf-8").read()
    milestones = OrderedDict()
    for m in re.finditer(r"^### (M\d+[ab]?) — (.+?) \((P\d), ", text, re.M):
        milestones[m.group(1)] = {"title": f"{m.group(1)} — {m.group(2)}", "priority": m.group(3)}
    packages = []
    sec = text.split("## 8. Порядок реализации", 1)
    if len(sec) == 2:
        for m in re.finditer(r"^\| (\d+[ab]?) \|", sec[1].split("\n## ", 1)[0], re.M):
            packages.append(m.group(1))
    if not milestones or not packages:
        die("roadmap structure not recognised (milestones/packages)")
    return milestones, packages


# ---------------------------------------------------------------- gates
def classify(line):
    m = re.search(r"PASS|FAIL|Нужны исправления", line, re.I)
    if not m:
        return "UNKNOWN"
    t = m.group(0).upper()
    return "PASS" if t == "PASS" else ("FAIL" if t == "FAIL" else "NEEDS_FIXES")


def eval_gate(proj, gid, g):
    full = proj.resolve(g["file"])
    if not os.path.exists(full):
        return {"class": "MISSING", "date": None, "line": ""}
    text = open(full, encoding="utf-8").read()
    start = 0
    if g.get("after"):
        i = text.rfind(g["after"])
        if i < 0:
            return {"class": "MISSING", "date": None, "line": ""}
        start = i
    rx = re.compile(g["line"], re.M)
    ms = list(rx.finditer(text, start))
    if not ms:
        return {"class": "MISSING", "date": None, "line": ""}
    m = ms[-1] if g.get("pick", "last") == "last" else ms[0]
    ls = text.rfind("\n", 0, m.start()) + 1
    le = text.find("\n", m.end())
    line = text[ls: le if le >= 0 else len(text)]
    dm = re.search(r"Дата:\s*(\d{4}-\d{2}-\d{2})", text[:600])
    date = dm.group(1) if dm else proj.file_date(g["file"])
    return {"class": classify(line), "date": date, "line": line.strip()}


# ---------------------------------------------------------------- build
def resolve_evidence(proj, ev, known_gate_dates):
    typ, ref = ev["type"], ev["ref"]
    out = OrderedDict(type=typ, ref=ref)
    date = ev.get("date")
    m = re.fullmatch(r"(source|docs)@([0-9a-f]{7,10})", ref)
    if m:
        date = proj.commit_date(m.group(1), m.group(2))
        if not date:
            die(f"commit {ref} not found in git")
    elif ref.startswith("docs/"):
        pm = re.match(r"(docs/[A-Za-z0-9_./-]+)", ref)
        rp = pm.group(1)
        if not os.path.exists(proj.resolve(rp)):
            die(f"evidence file missing: {rp}")
        date = known_gate_dates.get(rp) or ev.get("date") or proj.file_date(rp)
    else:
        die(f"evidence ref not allowed: {ref}")
    out["date"] = date
    out["ref"] = ("коммит кода" if ref.startswith("source@") else "коммит документации") if m else \
        ("ревью критика" if typ == "review" and re.search(r"REVIEW|CRITIC", ref) else
         "внутренний документ" if typ == "review" else "артефакт проверки")
    return out


def build(proj, ov):
    road_ms, road_pkgs = parse_roadmap(proj)
    gates = {gid: dict(eval_gate(proj, gid, g), file=g["file"]) for gid, g in ov["gates"].items()}
    gate_dates = {}
    for g in gates.values():
        if g["date"]:
            gate_dates[g["file"]] = max(g["date"], gate_dates.get(g["file"], ""))
    dirty = proj.dirty_paths()

    def is_dirty(paths):
        return any(d == p or d.startswith(p.rstrip("/") + "/") for d in dirty for p in paths)

    # tasks, in roadmap order; unknown overrides are errors, new roadmap packages are added neutrally
    tasks = []
    ov_tasks = ov["tasks"]
    for tid in ov_tasks:
        num = tid.split("-", 1)[1]
        if num not in road_pkgs:
            die(f"task {tid} has no package in the roadmap")
    for num in road_pkgs:
        tid = "pkg-" + num
        t = ov_tasks.get(tid)
        new = t is None
        if new:
            warn(f"package {num} is in the roadmap but not in overrides: added as planned, neutral text")
            t = {"milestone": None, "title": f"Пакет {num}", "priority": "TBD",
                 "summary": "Описание ещё не опубликовано.", "details": "Пакет появился в roadmap; публичное описание не подготовлено.",
                 "spoiler": "major", "evidence": []}
        g = gates.get(t.get("gate")) if t.get("gate") else None
        if t.get("gate") and g is None:
            die(f"{tid}: unknown gate {t['gate']}")
        if g and g["class"] == "PASS" and t.get("fixes_unverified"):
            status = "testing"  # PASS with fixes, but the fixes were not re-checked
        elif g and g["class"] == "PASS":
            status = "completed"
        elif is_dirty(t.get("worktree_paths", [])):
            status = "in_progress"
        elif t.get("implemented") or proj.package_commits(num) or (g and g["class"] != "MISSING") or any(
                e["ref"].startswith(("source@", "docs@")) for e in t.get("evidence", [])):
            status = "testing"
        else:
            status = "planned"
        task = OrderedDict(id=tid, milestone=t["milestone"], title=t["title"], status=status,
                           priority=t["priority"], summary=t["summary"], details=t["details"])
        evs = list(t.get("evidence", []))
        if not any(e["ref"].startswith("source@") for e in evs):
            evs += [{"type": "commit", "ref": "source@" + h} for h in proj.package_commits(num)[:3]]
        task["evidence"] = [resolve_evidence(proj, e, gate_dates) for e in evs]
        if status != "in_progress" and t.get("details_when_committed"):
            task["details"] = t["details_when_committed"]
            task["summary"] = t.get("summary_when_committed", task["summary"])
        task["spoiler"] = t["spoiler"]
        unc = bool(t.get("uncertain")) or new or bool(t.get("fixes_unverified"))
        if g and g["class"] in ("MISSING", "UNKNOWN"):
            unc = True
            task["details"] += " Строка вердикта в источнике не найдена: статус требует проверки."
        if unc:
            task["uncertain"] = True
        tasks.append(task)

    by_ms = {}
    for t in tasks:
        by_ms.setdefault(t["milestone"], []).append(t)

    milestones = []
    for mid, rm in road_ms.items():
        o = ov["milestones"].get(mid)
        if o is None:
            warn(f"milestone {mid} not in overrides: neutral entry")
            o = {"title": rm["title"], "public_title": mid, "spoiler": "major", "gate_verdict": "не проводилась", "uncertain": True}
        ts = by_ms.get(mid, [])
        gids = o.get("gates", [])
        gs = [gates[x] for x in gids]
        all_pass = bool(gs) and all(x["class"] == "PASS" for x in gs)
        sts = [t["status"] for t in ts]
        if all_pass and o.get("fixes_unverified"):
            status = "testing"
        elif all_pass:
            status = "completed"
        elif not ts or all(s == "planned" for s in sts):
            status = "planned"
        elif all(s == "completed" for s in sts) and not gs:
            status = "completed"
        else:
            status = "in_progress"
        m = OrderedDict(id=mid, title=f'{mid} — {o["public_title"]}', public_title=o["public_title"], status=status,
                        packages=[t["id"].split("-", 1)[1] for t in ts])
        if gs:
            dates = [x["date"] for x in gs if x["date"]]
            m["gate"] = OrderedDict(verdict=o["gate_verdict"], date=max(dates) if dates else None, source=public_source(o["gate_source"]))
            if not all_pass:
                m["gate"]["verdict"] = "в источнике нет вердикта PASS (" + ", ".join(sorted({x["class"] for x in gs})) + ")"
        else:
            m["gate"] = OrderedDict(verdict=o["gate_verdict"], date=None, source=None)
        m["spoiler"] = o["spoiler"]
        # PASS "with fixes" with no recorded re-check, or fixes not re-verified -> uncertain
        fixes_pass = any(re.search(r"исправлен|fixes|правк", x["line"], re.I) for x in gs) and not re.search(r"повторн", o["gate_verdict"])
        unc = bool(o.get("uncertain")) or bool(o.get("fixes_unverified")) or (all_pass and fixes_pass)
        if status in ("completed", "testing") and any(s == "testing" for s in sts):
            unc = True
        if unc:
            m["uncertain"] = True
        if o.get("note"):
            m["note"] = o["note"]
        milestones.append(m)

    # current milestone
    cur = next((m for m in milestones if m["status"] == "in_progress"), None) or next((m for m in milestones if m["status"] not in ("completed", "testing")), milestones[-1])
    also = []
    for m in milestones:
        if m is cur or m["status"] != "in_progress":
            continue
        for t in by_ms.get(m["id"], []):
            if t["status"] == "in_progress":
                also.append(f"{t['id'].split('-', 1)[1]} ({m['id']})")
    cm = OrderedDict(id=cur["id"], title=cur["title"], status=cur["status"],
                     packages=[t["id"].split("-", 1)[1] for t in by_ms.get(cur["id"], []) if t["status"] == "in_progress"] or cur["packages"])
    if also:
        cm["also_in_progress"] = also
    if ov.get("current_milestone_note"):
        cm["note"] = ov["current_milestone_note"]

    # tests / known issues: curated, but their sources must resolve
    def check_refs(items, what):
        for it in items:
            for m in re.finditer(r"docs/[A-Za-z0-9_./-]+\.(?:md|txt|json)", it.get("source") or ""):
                if not os.path.exists(proj.resolve(m.group(0))):
                    die(f"{what} {it['id']}: source file missing: {m.group(0)}")
    check_refs(ov["tests"], "test")
    check_refs(ov["known_issues"], "known issue")

    # changelog
    counts = {}
    for which in ("source", "docs"):
        for d in proj.commit_dates(which):
            counts.setdefault(d, {"source": 0, "docs": 0})[which] += 1
    snap = ov.get("changelog_counts", {})
    cl = {d: list(items) for d, items in ov["changelog"].items()}
    for d, c in counts.items():
        prev = snap.get(d, {"source": 0, "docs": 0})
        ds, dd = c["source"] - prev["source"], c["docs"] - prev["docs"]
        if ds > 0 or dd > 0:
            parts = []
            if ds > 0:
                parts.append(f"{ds} в коде игры")
            if dd > 0:
                parts.append(f"{dd} в документации")
            tag = "авто" if d in cl else "авто"
            cl.setdefault(d, []).append(f"[{tag}] Новые коммиты, ещё без описания: " + ", ".join(parts) + ".")
    changelog = [OrderedDict(date=d, items=cl[d]) for d in sorted(cl, reverse=True)]

    cands = list(counts)
    dm = proj.dirty_mtime_date()
    if dm:
        cands.append(dm)
    updated = max(cands)

    out = OrderedDict()
    out["project"] = "RIGGED"
    out["updated"] = updated
    out["current_milestone"] = cm
    out["milestones"] = milestones
    out["tasks"] = tasks
    out["tests"] = [OrderedDict((k, (public_source(v) if k == "source" else v)) for k, v in t.items()) for t in ov["tests"]]
    out["known_issues"] = [OrderedDict((k, (public_source(v) if k == "source" else v)) for k, v in k_.items()) for k_ in ov["known_issues"]]
    out["changelog"] = changelog
    out["sources"] = [OrderedDict((k, ("внутренний документ" if k == "path" else v)) for k, v in s_.items()) for s_ in ov["sources"]]
    return deep_clean(out), counts


def guard(out):
    bad = []
    for path, s in privacy.walk_strings(out):
        for pat in stopwords.hits(s):
            bad.append(f"{path}: story stop-word /{pat}/: {s[:60]!r}")
    for path, s in privacy.walk_strings(out):
        for label, snip in privacy.find_private(s):
            bad.append(f"{path}: {label}: {snip!r}")
    if bad:
        print("sync_progress: PRIVATE DATA DETECTED, refusing to write:", file=sys.stderr)
        for b in bad[:30]:
            print("  " + b, file=sys.stderr)
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rigged-root", default=os.environ.get("RIGGED_ROOT") or os.path.normpath(os.path.join(REPO, "..", "rigged")))
    ap.add_argument("--overrides", default=os.path.join(REPO, "data", "overrides.json"))
    ap.add_argument("--private", default=os.path.join(REPO, "data", "private", "private.json"))
    ap.add_argument("--out", default=os.path.join(REPO, "data", "progress.json"))
    ap.add_argument("--check", action="store_true", help="do not write; exit 3 if file would change")
    ap.add_argument("--snapshot-counts", action="store_true", help="print current commit counters for overrides.changelog_counts")
    a = ap.parse_args()
    proj = Project(a.rigged_root)
    ov = json.load(open(a.overrides, encoding="utf-8"))
    pvp = a.private
    if not os.path.exists(pvp):
        die("private mapping missing: " + os.path.relpath(pvp, REPO) + " (untracked; keep it on the dev machine)")
    ov = merge_private(ov, json.load(open(pvp, encoding="utf-8")))
    out, counts = build(proj, ov)
    if a.snapshot_counts:
        print(json.dumps(counts, indent=2, sort_keys=True))
        return
    guard(out)
    text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    old = open(a.out, encoding="utf-8").read() if os.path.exists(a.out) else ""
    if a.check:
        sys.exit(0 if old == text else 3)
    if old != text:
        open(a.out, "w", encoding="utf-8").write(text)
        print("sync_progress: progress.json updated")
    else:
        print("sync_progress: no changes")


if __name__ == "__main__":
    main()
