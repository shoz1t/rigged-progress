#!/usr/bin/env python3
"""Build the static site into _site/ (stdlib only).
Copies only publishable files (never tools/, design/, overrides, scripts) and renders the <noscript> fallback from progress.json."""
import html, json, os, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_site")
LABEL = {"completed": "Готово", "in_progress": "В работе", "testing": "На тесте", "planned": "В плане"}
e = html.escape


def noscript(d):
    ms = {m["id"]: m for m in d["milestones"]}
    cm = d["current_milestone"]
    cnt = {k: sum(1 for t in d["tasks"] if t["status"] == k) for k in LABEL}
    p = ['<div class="noscript-box">',
         f'<p><b>{e(cm["id"])} · {e(ms[cm["id"]]["public_title"])}</b>, обновлено {e(d["updated"])}.</p>',
         "<p>Скрипты отключены: ниже статичная сводка. Подробности и фильтр работают с JavaScript. "
         "Скрытые спойлеры в сводку не входят.</p>",
         "<p>" + ", ".join(f"{LABEL[k]}: {cnt[k]}" for k in LABEL) + "; открытых проблем: "
         + str(sum(1 for k in d["known_issues"] if k["status"] != "resolved")) + ".</p>",
         "<h2>Вехи</h2><ul class=\"nojs\">"]
    for m in d["milestones"]:
        p.append(f'<li><b>{e(m["id"])}</b> {e(m["public_title"])}: {LABEL[m["status"]]}'
                 + (" (данные уточняются)" if m.get("uncertain") else "") + "</li>")
    p.append("</ul><h2>Задачи</h2><ul class=\"nojs\">")
    for t in d["tasks"]:
        p.append(f'<li>{e(t["id"].replace("pkg-", "П-"))} {e(t["title"])}: {LABEL[t["status"]]}'
                 + (" (неточно)" if t.get("uncertain") else "") + "</li>")
    p.append("</ul><h2>Последние изменения</h2><ul class=\"nojs\">")
    if d["changelog"]:
        c = d["changelog"][0]
        for it in c["items"]:
            p.append(f"<li>{e(c['date'])}: {e(it)}</li>")
    p.append("</ul></div>")
    return "\n".join(p)


def main():
    d = json.load(open(os.path.join(ROOT, "data", "progress.json"), encoding="utf-8"))
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "data"))
    for f in ("404.html",):
        shutil.copy(os.path.join(ROOT, f), OUT)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))
    def strip(o):  # belt and braces: spoiler text must never reach _site
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k != "spoiler_detail"}
        if isinstance(o, list):
            return [strip(x) for x in o]
        return o
    with open(os.path.join(OUT, "data", "progress.json"), "w", encoding="utf-8") as f:
        json.dump(strip(d), f, ensure_ascii=False, indent=2)
    src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    if "<!--NOSCRIPT_FALLBACK-->" not in src:
        sys.exit("build: marker missing in index.html")
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(src.replace("<!--NOSCRIPT_FALLBACK-->", noscript(d)))
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    n = sum(len(fs) for _, _, fs in os.walk(OUT))
    print(f"build: {n} files in _site/")


if __name__ == "__main__":
    main()
