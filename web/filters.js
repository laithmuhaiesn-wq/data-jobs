// Derbani list filters: brand, storage, processor, screen size... plus price, "at 2+ shops", "price dropped" and sorting.
// The page works fully without this script (the full list, grouped by brand). The choices live in the address
// (?storage=256GB&sort=price) so a filtered list can be shared and Back returns to it. Nothing is sent anywhere.
(function () {
  var box = document.getElementById("flt"), all = document.getElementById("all");
  if (!box || !all || !window.fetch) return;
  var en = document.documentElement.lang === "en", pre = en ? "/en" : "";
  var cat = box.getAttribute("data-cat"), onlyBrand = box.getAttribute("data-brand") || "";
  var GROUPS = {phone: ["brand", "storage"], tablet: ["brand", "storage"],
                laptop: ["brand", "chip", "ram", "storage", "screen", "gpu"], tv: ["brand", "size"]}[cat] || ["brand"];
  if (onlyBrand) GROUPS = GROUPS.filter(function (g) { return g !== "brand"; });
  var T = en ? {
    filters: "Filters", clear: "Clear all", sort: "Sort", found: "{n} products", none: "Nothing matches these filters.",
    price: "Price (JOD)", min: "From", max: "To", two: "At 2+ shops", drop: "Price dropped", show: "Show {n} products",
    s0: "Most compared", s1: "Lowest price", s2: "Highest price", s3: "Biggest saving between shops", s4: "Biggest price drop",
    from: "From {p} JOD", was: "Was {p}", one: "1 shop", many: "{n} shops",
    g: {brand: "Brand", storage: "Storage", ram: "RAM", chip: "Processor", screen: "Screen", gpu: "Graphics", size: "Screen size"},
    v: {card: "Graphics card", "built-in": "Built-in"}
  } : {
    filters: "الفلاتر", clear: "مسح الكل", sort: "الترتيب", found: "{n} منتج", none: "لا يوجد منتج بهذه الاختيارات.",
    price: "السعر (دينار)", min: "من", max: "إلى", two: "في متجرين أو أكثر", drop: "انخفض سعره", show: "عرض {n} منتج",
    s0: "الأكثر مقارنة", s1: "الأقل سعراً", s2: "الأعلى سعراً", s3: "أكبر فرق بين المتاجر", s4: "أكبر انخفاض في السعر",
    from: "من {p} د.أ", was: "كان {p}", one: "متجر واحد", many: "{n} متاجر",
    g: {brand: "الماركة", storage: "السعة", ram: "الرام", chip: "المعالج", screen: "الشاشة", gpu: "كرت الشاشة", size: "حجم الشاشة"},
    v: {card: "كرت شاشة منفصل", "built-in": "مدمج"}
  };
  var NUMERIC = {storage: 1, ram: 1, size: 1, screen: 1};
  var items = [], state = read();

  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text != null) n.textContent = text;
    return n;
  }
  function fmt(s, o) { return s.replace(/\{(\w+)\}/g, function (_, k) { return o[k]; }); }
  function money(p) { return (Math.round(p * 100) / 100).toLocaleString("en-US", {maximumFractionDigits: 2}); }
  function gb(v) { var n = parseFloat(v); return /TB/.test(v) ? n * 1024 : n; }

  function read() {
    var q = new URLSearchParams(location.search), s = {sel: {}, sort: q.get("sort") || "", min: q.get("min") || "",
      max: q.get("max") || "", two: q.get("two") === "1", drop: q.get("drop") === "1"};
    GROUPS.forEach(function (g) { var v = q.get(g); if (v) s.sel[g] = v.split("|"); });
    return s;
  }
  function write() {
    var q = new URLSearchParams();
    GROUPS.forEach(function (g) { if ((state.sel[g] || []).length) q.set(g, state.sel[g].join("|")); });
    ["sort", "min", "max"].forEach(function (k) { if (state[k]) q.set(k, state[k]); });
    if (state.two) q.set("two", "1");
    if (state.drop) q.set("drop", "1");
    var s = q.toString();
    history.replaceState(null, "", location.pathname + (s ? "?" + s : "") + location.hash);
  }
  function active() {
    var n = 0;
    GROUPS.forEach(function (g) { n += (state.sel[g] || []).length; });
    return n + (state.min ? 1 : 0) + (state.max ? 1 : 0) + (state.two ? 1 : 0) + (state.drop ? 1 : 0);
  }
  // does the product pass every filter, leaving out one group (for that group's counts)?
  function passes(v, skip) {
    var f = v.f || {};
    if (onlyBrand && v.brand !== onlyBrand) return false;
    for (var i = 0; i < GROUPS.length; i++) {
      var g = GROUPS[i], want = state.sel[g];
      if (g !== skip && want && want.length && want.indexOf(f[g]) < 0) return false;
    }
    var p = v.best_price;
    if ((state.min || state.max) && p == null) return false;
    if (state.min && p < parseFloat(state.min)) return false;
    if (state.max && p > parseFloat(state.max)) return false;
    if (state.two && (v.ranked_shops || 0) < 2) return false;
    if (state.drop && !(v.drop > 0)) return false;
    return true;
  }
  function sorted(list) {
    var by = {
      price: function (a, b) { return (a.best_price == null) - (b.best_price == null) || a.best_price - b.best_price; },
      high: function (a, b) { return (a.best_price == null) - (b.best_price == null) || b.best_price - a.best_price; },
      save: function (a, b) { return (b.save || 0) - (a.save || 0); },
      drop: function (a, b) { return (b.drop || 0) - (a.drop || 0); }
    }[state.sort];
    return by ? list.slice().sort(by) : list;    // the file is already "most compared first"
  }

  function card(v) {
    var li = el("li"), a = el("a", {href: pre + "/p/" + v.slug});
    a.appendChild(el("span", {"class": "name"}, v.label.trim()));
    if (v.best_price != null) a.appendChild(el("span", {"class": "tag"}, fmt(T.from, {p: money(v.best_price)})));
    if (v.was) a.appendChild(el("s", {"class": "mute"}, fmt(T.was, {p: money(v.was)})));
    a.appendChild(el("span", {"class": "mute"}, v.shops === 1 ? T.one : fmt(T.many, {n: v.shops})));
    li.appendChild(a);
    return li;
  }
  function label(g, value) {
    if (g === "brand") { var hit = items.find(function (v) { return v.brand === value; }); return en || !hit ? value : hit.brand_ar; }
    return T.v[value] || value;
  }

  var panel, results, count, toggle, sortSel;
  function build() {
    box.textContent = "";
    var bar = el("div", {"class": "fbar"});
    toggle = el("button", {type: "button", "class": "fbtn", "aria-expanded": "false", "aria-controls": "fpanel"});
    toggle.addEventListener("click", function () { open(panel.hidden); });
    sortSel = el("select", {"aria-label": T.sort});
    [["", T.s0], ["price", T.s1], ["high", T.s2], ["save", T.s3], ["drop", T.s4]].forEach(function (o) {
      var op = el("option", {value: o[0]}, o[1]);
      if (o[0] === state.sort) op.selected = true;
      sortSel.appendChild(op);
    });
    sortSel.addEventListener("change", function () { state.sort = sortSel.value; update(); });
    count = el("span", {"class": "fcount mute", "aria-live": "polite"});
    bar.appendChild(toggle); bar.appendChild(sortSel); bar.appendChild(count);
    panel = el("div", {id: "fpanel", "class": "fpanel"});
    panel.hidden = window.matchMedia("(max-width:860px)").matches && !active();   // on phones it opens on a tap
    box.appendChild(bar); box.appendChild(panel);
    results = el("ul", {"class": "list", id: "fres"});
    results.hidden = true;
    all.parentNode.insertBefore(results, all);
    box.hidden = false;
    update();
  }
  function open(yes) { panel.hidden = !yes; toggle.setAttribute("aria-expanded", yes ? "true" : "false"); }

  function chipRow(title, chips) {
    var sec = el("fieldset", {"class": "fgroup"});
    sec.appendChild(el("legend", null, title));
    var row = el("div", {"class": "fchips"});
    chips.forEach(function (c) { row.appendChild(c); });
    sec.appendChild(row);
    return sec;
  }
  function chip(text, on, n, click) {
    var b = el("button", {type: "button", "class": "fchip", "aria-pressed": on ? "true" : "false"});
    b.appendChild(document.createTextNode(text));
    if (n != null) b.appendChild(el("small", null, String(n)));
    if (!on && n === 0) b.disabled = true;
    b.addEventListener("click", click);
    return b;
  }

  function drawPanel() {
    panel.textContent = "";
    GROUPS.forEach(function (g) {
      var counts = {};
      items.forEach(function (v) { var x = (v.f || {})[g]; if (x && passes(v, g)) counts[x] = (counts[x] || 0) + 1; });
      var have = {};
      items.forEach(function (v) { var x = (v.f || {})[g]; if (x && (!onlyBrand || v.brand === onlyBrand)) have[x] = (have[x] || 0) + 1; });
      var values = Object.keys(have);
      if (values.length < 2) return;                  // one choice filters nothing
      values.sort(NUMERIC[g] ? function (a, b) { return gb(a) - gb(b); } : function (a, b) { return have[b] - have[a]; });
      var chosen = state.sel[g] || [];
      panel.appendChild(chipRow(T.g[g], values.map(function (x) {
        var on = chosen.indexOf(x) >= 0;
        return chip(label(g, x), on, counts[x] || 0, function () {
          var list = (state.sel[g] || []).slice(), i = list.indexOf(x);
          if (i >= 0) list.splice(i, 1); else list.push(x);
          state.sel[g] = list;
          update();
        });
      })));
    });
    var price = el("fieldset", {"class": "fgroup"});
    price.appendChild(el("legend", null, T.price));
    var row = el("div", {"class": "fprice"});
    ["min", "max"].forEach(function (k) {
      var lab = el("label", null, T[k] + " ");
      var inp = el("input", {type: "number", inputmode: "numeric", min: "0", step: "1", value: state[k]});
      inp.addEventListener("change", function () { state[k] = inp.value && +inp.value >= 0 ? String(Math.round(+inp.value)) : ""; update(); });
      lab.appendChild(inp);
      row.appendChild(lab);
    });
    price.appendChild(row);
    panel.appendChild(price);
    panel.appendChild(chipRow("", [
      chip(T.two, state.two, null, function () { state.two = !state.two; update(); }),
      chip(T.drop, state.drop, null, function () { state.drop = !state.drop; update(); })
    ]));
    var foot = el("div", {"class": "ffoot"});
    if (active()) {
      var clear = el("button", {type: "button", "class": "flink"}, T.clear);
      clear.addEventListener("click", function () { state = {sel: {}, sort: state.sort, min: "", max: "", two: false, drop: false}; update(); });
      foot.appendChild(clear);
    }
    var done = el("button", {type: "button", "class": "fdone"});
    done.addEventListener("click", function () { open(false); toggle.scrollIntoView({block: "start"}); });
    foot.appendChild(done);
    panel.appendChild(foot);
    return done;
  }

  function update() {
    write();
    var hits = sorted(items.filter(function (v) { return passes(v, null); }));
    var n = active(), filtering = n > 0 || state.sort;
    toggle.textContent = T.filters + (n ? " (" + n + ")" : "");
    count.textContent = fmt(T.found, {n: hits.length});
    var done = drawPanel();
    done.textContent = fmt(T.show, {n: hits.length});
    results.textContent = "";
    if (filtering) {
      if (!hits.length) results.appendChild(el("li", {"class": "mute"}, T.none));
      hits.forEach(function (v) { results.appendChild(card(v)); });
    }
    results.hidden = !filtering;
    all.hidden = !!filtering;
  }

  fetch("/api/list-" + cat + ".json").then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
    if (!d || !d.results || !d.results.length || !d.results[0].f) return;   // older file: leave the plain list
    items = d.results;
    build();
  }).catch(function () { /* offline: the plain list stays */ });
})();
