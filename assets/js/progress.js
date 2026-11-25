/* RIGGED progress: reads data/progress.json (relative URL, works under any base path). No dependencies. */
(function () {
  "use strict";
  var ST = {
    completed: { key: "done", label: "Готово", cls: "st-done" },
    in_progress: { key: "progress", label: "В работе", cls: "st-progress" },
    testing: { key: "testing", label: "На тесте", cls: "st-testing" },
    planned: { key: "planned", label: "В плане", cls: "st-planned" }
  };
  var KEYS = ["done", "progress", "testing", "planned"];
  var KI = {
    open: { label: "Открыта", cls: "st-issue" },
    intermittent: { label: "Плавающая", cls: "st-issue" },
    resolved: { label: "Закрыта", cls: "st-done" },
    uncertain: { label: "Уточняется", cls: "st-planned" }
  };
  var EVT = { review: "Ревью", commit: "Коммит", test: "Тест, артефакт" };
  var $ = function (id) { return document.getElementById(id); };
  var data, state = { status: "all", q: "", spoilers: false }, revealed = {}, uid = 0;

  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (attrs[k] === false || attrs[k] == null) continue;
      if (k === "class") el.className = attrs[k]; else el.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
    }
    for (var i = 2; i < arguments.length; i++) add(el, arguments[i]);
    return el;
  }
  function add(el, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) { c.forEach(function (x) { add(el, x); }); return; }
    el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
  }
  function glyph() { var i = h("i", { class: "g", "aria-hidden": "true" }); return i; }
  function stEl(cls, label) { return h("span", { class: "st " + cls }, glyph(), label); }
  function dateRu(s, short) {
    if (!s) return "—";
    var p = s.split("-"); if (p.length !== 3) return s;
    var d = new Date(+p[0], +p[1] - 1, +p[2]);
    return short ? d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" }) :
      d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
  }
  function timeEl(s, short) { return h("time", { datetime: s || null }, dateRu(s, short)); }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  function plural(n, a, b, c) { var m = n % 100, d = n % 10; return (m > 10 && m < 20) ? c : d === 1 ? a : (d > 1 && d < 5) ? b : c; }

  /* ---------- derived ---------- */
  function msById() { var m = {}; data.milestones.forEach(function (x) { m[x.id] = x; }); return m; }
  function taskDate(t) { return (t.evidence || []).reduce(function (a, e) { return e.date && e.date > a ? e.date : a; }, ""); }
  function pkgNum(t) { return parseInt(t.id.replace(/\D+/g, ""), 10) || 0; }
  function counts() {
    var c = { all: data.tasks.length, done: 0, progress: 0, testing: 0, planned: 0 };
    data.tasks.forEach(function (t) { c[ST[t.status].key]++; });
    return c;
  }
  function openIssues() { return data.known_issues.filter(function (k) { return k.status !== "resolved"; }); }

  /* ---------- hash state: #section?status=done&q=text ---------- */
  function parseHash() {
    var raw = decodeURIComponent((location.hash || "").slice(1)), i = raw.indexOf("?"), sec = i < 0 ? raw : raw.slice(0, i);
    var qs = new URLSearchParams(i < 0 ? "" : raw.slice(i + 1));
    var s = qs.get("status");
    return { sec: sec, status: KEYS.indexOf(s) >= 0 ? s : "all", q: qs.get("q") || "" };
  }
  function writeHash() {
    var qs = new URLSearchParams();
    if (state.status !== "all") qs.set("status", state.status);
    if (state.q) qs.set("q", state.q);
    var s = qs.toString();
    var url = location.pathname + location.search + (s ? "#tasks?" + s : "");
    try { history.replaceState(null, "", url); } catch (e) { /* file:// etc. */ }
  }

  /* ---------- overview ---------- */
  function renderHero() {
    var ms = msById(), cm = data.current_milestone, m = ms[cm.id];
    var line = $("status-line"); line.textContent = "";
    add(line, [h("em", { class: "acc" }, cm.id), h("b", null, m ? m.public_title : cm.title),
      h("span", null, cm.status === "in_progress" ? "в работе" : (ST[cm.status] || {}).label || cm.status),
      h("span", null, "обновлено ", timeEl(data.updated))]);
    if (cm.note) add(line, h("span", { style: "flex-basis:100%" }, cm.note));
    if (cm.also_in_progress && cm.also_in_progress.length) add(line, h("span", { style: "flex-basis:100%" }, "Параллельно в работе: пакет " + cm.also_in_progress.join(", ") + "."));
    var c = counts(), iss = openIssues().length, wrap = $("tally-wrap"); wrap.textContent = "";
    function cell(v, label, cls, href) {
      return h("a", { href: href }, h("span", { class: "v" }, v), h("span", { class: "k " + cls }, glyph(), label));
    }
    wrap.appendChild(h("div", { class: "tally", role: "group", "aria-label": "Счётчики" },
      cell(c.done, "Готово", "st-done", "#tasks?status=done"), cell(c.progress, "В работе", "st-progress", "#tasks?status=progress"),
      cell(c.testing, "На тесте", "st-testing", "#tasks?status=testing"), cell(c.planned, "В плане", "st-planned", "#tasks?status=planned"),
      cell(iss, "Открытые проблемы", "st-issue", "#issues")));
    var link = $("subnav");
    KEYS.forEach(function (k) { var a = link.querySelector('[data-status="' + k + '"] .n'); if (a) a.textContent = c[k]; });
    var ia = link.querySelector('[data-sec="issues"] .n'); if (ia) ia.textContent = iss;
  }

  /* ---------- roadmap ---------- */
  function renderRoad() {
    var ol = $("road"), cur = data.current_milestone.id; ol.textContent = "";
    data.milestones.forEach(function (m, i) {
      var tasks = data.tasks.filter(function (t) { return t.milestone === m.id; });
      var done = tasks.filter(function (t) { return t.status === "completed"; }).length;
      var cls = m.status === "completed" ? "done" : m.status === "in_progress" ? "now" : m.status === "testing" ? "test" : "";
      var tag = m.status === "completed" ? "готово" : m.id === cur ? "сейчас" : m.status === "in_progress" ? "в работе" : m.status === "testing" ? "на тесте" : "в плане";
      var li = h("li", { class: cls, style: "--p:" + (tasks.length ? Math.round(100 * done / tasks.length) : 0) + "%;--i:" + i, "aria-current": m.id === cur ? "step" : null },
        h("span", { class: "tick", "aria-hidden": "true" }),
        h("div", { class: "m-id" }, m.id + " · " + tag),
        h("div", { class: "m-t" }, m.public_title),
        h("div", { class: "m-p" }, "Пакеты: " + done + " из " + tasks.length + " готовы"));
      var g = m.gate || {};
      if (g.verdict) li.appendChild(h("div", { class: "m-g" }, "Проверка: " + g.verdict + (g.date ? ", " + dateRu(g.date) : "")));
      if (m.uncertain) li.appendChild(h("div", { class: "m-note" }, h("span", { class: "unc" }, "Данные уточняются"), m.note ? " " + m.note : ""));
      else if (m.note) li.appendChild(h("div", { class: "m-note" }, m.note));
      ol.appendChild(li);
    });
  }

  /* ---------- ledger ---------- */
  function evList(ev) {
    return h("ul", { class: "ev", "aria-label": "Источники и подтверждения" }, (ev || []).map(function (e) {
      return h("li", null, h("span", { class: "ty" }, EVT[e.type] || e.type), h("code", null, e.ref), e.date ? h("span", { class: "meta" }, timeEl(e.date)) : null);
    }));
  }
  function taskRow(t, i, latest, ms) {
    var st = ST[t.status], m = ms[t.milestone], d = taskDate(t);
    var sum = h("summary", null,
      h("span", { class: "id" }, t.id.replace("pkg-", "П-")), h("span", { class: "t" }, t.title),
      h("span", { class: "side" }, h("span", { class: "stc" }, stEl(st.cls, st.label), t.uncertain ? h("span", { class: "unc", title: "Статус не подтверждён полностью" }, "Неточно") : null),
        h("span", null, (m ? m.id + " · " + m.public_title : t.milestone)), h("span", null, d ? "обн. " : "", d ? timeEl(d, true) : "—")),
      h("i", { class: "chev", "aria-hidden": "true" }));
    var body = h("div", { class: "body" }, h("p", null, t.summary));
    if (t.details && t.details !== t.summary) body.appendChild(h("p", null, t.details));
    if (t.uncertain) body.appendChild(h("p", { class: "warn" }, "Неточно: статус или подтверждение не полностью проверены. Подробности в описании выше и в источниках ниже."));
    body.appendChild(h("dl", null, h("dt", null, "Веха"), h("dd", null, m ? m.id + ", " + m.public_title : t.milestone),
      h("dt", null, "Приоритет"), h("dd", null, t.priority), h("dt", null, "Статус"), h("dd", null, st.label)));
    if (t.evidence && t.evidence.length) { body.appendChild(h("p", { class: "meta" }, "Подтверждения (внутренние материалы, не публикуются):")); body.appendChild(evList(t.evidence)); }
    var li = h("li", { class: "row" + (latest ? " latest" : ""), "data-st": st.key, style: "--i:" + Math.min(i, 12) }, h("details", null, sum, body));
    li._t = t; return li;
  }
  var rows = [];
  function renderTasks() {
    var ms = msById(), list = $("list"); list.textContent = ""; rows = [];
    var sorted = data.tasks.slice().sort(function (a, b) { return taskDate(b).localeCompare(taskDate(a)) || pkgNum(b) - pkgNum(a); });
    var latest = sorted.filter(function (t) { return t.status === "in_progress"; })[0] || sorted[0];
    sorted.forEach(function (t, i) { var r = taskRow(t, i, t === latest, ms); rows.push(r); list.appendChild(r); });
    var seg = $("seg"), c = counts();
    seg.querySelectorAll("input,label").forEach(function (n) { n.remove(); });
    [["all", "Все"], ["done", "Готово"], ["progress", "В работе"], ["testing", "На тесте"], ["planned", "В плане"]].forEach(function (p) {
      var id = "s-" + p[0], key = p[0];
      var input = h("input", { type: "radio", name: "status", id: id, value: key });
      input.checked = state.status === key;
      input.addEventListener("change", function () { state.status = key; applyFilter(); writeHash(); updateNav(); });
      var cls = key === "all" ? null : { done: "st-done", progress: "st-progress", testing: "st-testing", planned: "st-planned" }[key];
      seg.appendChild(input); seg.appendChild(h("label", { for: id }, cls ? h("span", { class: "st " + cls }, glyph()) : null, p[1] + " " + c[key]));
    });
    applyFilter();
  }
  function applyFilter() {
    var q = state.q.trim().toLowerCase(), ms = msById(), shown = 0;
    rows.forEach(function (r) {
      var t = r._t, ok = state.status === "all" || ST[t.status].key === state.status;
      if (ok && q) {
        var m = ms[t.milestone];
        var hay = [t.title, t.summary, t.details, t.id, t.id.replace("pkg-", "п-"), t.milestone, m ? m.public_title : ""].join(" ").toLowerCase();
        ok = hay.indexOf(q) >= 0;
      }
      r.hidden = !ok; if (ok) shown++;
    });
    $("count").textContent = "Показано " + shown + " из " + rows.length;
    var seg = $("seg"); seg.querySelectorAll("input").forEach(function (i) { i.checked = i.value === state.status; });
    var qi = $("q"); if (qi.value !== state.q) qi.value = state.q;
    var empty = $("list").querySelector(".empty"); if (empty) empty.remove();
    if (!shown) $("list").appendChild(h("li", { class: "empty" }, "Ничего не найдено. Сбросьте фильтр или поиск."));
  }

  /* ---------- tests ---------- */
  function bar(p, f, s, label) {
    var tot = (p || 0) + (f || 0) + (s || 0); if (!tot) return null;
    return h("div", { class: "bar-t", role: "img", "aria-label": label }, h("i", { style: "flex:" + (p || 0) }), f ? h("i", { class: "f", style: "flex:" + f }) : null, s ? h("i", { class: "s", style: "flex:" + s }) : null);
  }
  function suite(name, o) {
    if (!o) return null;
    var txt = o.pass + " пройдено, " + o.fail + " упало" + (o.skip != null ? ", " + o.skip + " пропущено" : "");
    return h("div", null, h("p", null, h("span", { class: "meta" }, name + ": "), h("b", null, o.pass + " пройдено"), " · ",
      h("span", { class: o.fail ? "fail" : "" }, o.fail + " упало"), o.skip != null ? [" · ", h("span", { class: "meta" }, o.skip + " пропущено")] : null),
      bar(o.pass, o.fail, o.skip, name + ": " + txt));
  }
  function renderTests() {
    var body = $("tests-body"); body.textContent = "";
    body.appendChild(h("p", { class: "meta", style: "margin-bottom:16px;max-width:66ch" }, "Цифры взяты из последней проверки каждой вехи, а не из непрерывного прогона. Окно и unit-наборы запускались без видимого окна."));
    var ms = msById(), list = h("ol", { class: "tests-list", "aria-label": "Результаты проверок по вехам" });
    data.tests.slice().reverse().forEach(function (t) {
      var m = ms[t.milestone];
      var li = h("li", null, h("div", { class: "th" }, h("b", null, (m ? m.id + " · " + m.public_title : t.milestone)), h("span", { class: "meta" }, timeEl(t.date)), h("span", { class: "meta" }, t.scope)),
        suite("Unit", t.unit), suite("Окно", t.window),
        t.check_build ? h("p", { class: "meta" }, "Проверка сборки: " + t.check_build) : null,
        t.notes ? h("p", null, t.notes) : null,
        !t.unit && !t.window ? h("p", { class: "meta" }, "Нет сводки pass/fail для этой записи.") : null,
        t.source ? h("p", { class: "src" }, "Источник: " + t.source) : null);
      list.appendChild(li);
    });
    body.appendChild(list);
  }

  /* ---------- issues ---------- */
  function renderIssues() {
    var ol = $("issue-list"); ol.textContent = "";
    var order = { open: 0, intermittent: 1, uncertain: 2, resolved: 3 };
    data.known_issues.slice().sort(function (a, b) { return (order[a.status] - order[b.status]) || a.id.localeCompare(b.id); }).forEach(function (k, i) {
      var s = KI[k.status] || { label: k.status, cls: "st-planned" };
      var body = h("div", { class: "body" });
      body.appendChild(h("p", null, k.detail));
      if (k.source) body.appendChild(h("p", { class: "meta" }, "Источник: " + k.source));
      var li = h("li", { class: "row", style: "--i:" + Math.min(i, 12) }, h("details", null,
        h("summary", null, h("span", { class: "id" }, k.id.replace("KI-", "И-")), h("span", { class: "t" }, k.title),
          h("span", { class: "side" }, h("span", { class: "stc" }, stEl(s.cls, s.label), k.status === "uncertain" ? h("span", { class: "unc" }, "Неточно") : null)), h("i", { class: "chev", "aria-hidden": "true" })), body));
      ol.appendChild(li);
    });
  }

  /* ---------- changelog, sources ---------- */
  function renderLog() {
    var ol = $("log"); ol.textContent = "";
    data.changelog.forEach(function (c) {
      ol.appendChild(h("li", null, h("time", { datetime: c.date }, dateRu(c.date)),
        h("ul", null, c.items.map(function (it) {
          var m = /^\[([^\]]+)\]\s*(.*)$/.exec(it);
          return h("li", { style: "display:block;border:0;padding:0" }, m ? [h("span", { class: "tag" }, m[1] + " "), m[2]] : it);
        }))));
    });
  }
  function renderSources() {
    var r = $("rules"); r.textContent = "";
    add(r, [h("p", null, "Готово ставится только при найденном вердикте PASS независимого ревью или критика. «На тесте» означает: реализовано, но независимой проверки нет. Знак «Неточно» означает, что источники противоречат друг другу или повторной проверки нет."),
      h("p", { class: "meta" }, "Названия и описания написаны владельцем проекта; сюжетные подробности не публикуются. Статусы, вердикты, даты и коммиты выводятся скриптом из документов и истории разработки.")]);
    var ul = $("source-list"); ul.textContent = "";
    data.sources.forEach(function (s) { ul.appendChild(h("li", null, h("b", null, s.name), " — ", s.used_for, h("br"), h("span", { class: "meta" }, s.path))); });
  }

  /* ---------- nav ---------- */
  var currentSec = "overview";
  function updateNav() {
    document.querySelectorAll("#subnav a").forEach(function (a) {
      var on = a.dataset.sec === currentSec && (!a.dataset.status || (currentSec === "tasks" && a.dataset.status === state.status));
      if (on) a.setAttribute("aria-current", "location"); else a.removeAttribute("aria-current");
    });
  }
  function watchSections() {
    if (!("IntersectionObserver" in window)) return;
    var ids = ["overview", "roadmap", "tasks", "tests", "issues", "changelog"], vis = {};
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { vis[e.target.id] = e.isIntersecting ? e.intersectionRatio : 0; });
      var best = ids.reduce(function (a, id) { return (vis[id] || 0) > (vis[a] || 0) ? id : a; }, currentSec);
      if (best !== currentSec) { currentSec = best; updateNav(); }
    }, { rootMargin: "-20% 0px -50% 0px", threshold: [0, 0.1, 0.5] });
    ids.forEach(function (id) { var el = $(id); if (el) io.observe(el); });
  }
  function onHash(scroll) {
    var p = parseHash();
    state.status = p.status; state.q = p.q;
    if (rows.length) applyFilter();
    var target = $(p.sec) || (p.status !== "all" || p.q ? $("tasks") : null);
    if (target && scroll) {
      currentSec = target.id; target.scrollIntoView();
      var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduce) window.scrollTo(0, window.scrollY);
    }
    updateNav();
  }

  /* ---------- init ---------- */
  function renderAll() {
    renderHero(); renderRoad(); renderTasks(); renderTests(); renderIssues(); renderLog(); renderSources();
    onHash(true);
  }
  function init() {
    $("q").addEventListener("input", function (e) { state.q = e.target.value; applyFilter(); writeHash(); });
    window.addEventListener("hashchange", function () { onHash(true); });
    var url = new URL("data/progress.json", document.baseURI);
    fetch(url, { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then(function (d) {
      data = d; renderAll(); watchSections();
    }).catch(function (e) {
      $("status-line").textContent = "";
      $("status-line").appendChild(h("span", { class: "err", role: "alert" }, "Не удалось загрузить data/progress.json (" + e.message + "). Обновите страницу позже."));
    });
  }
  init();
})();
