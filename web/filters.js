// Derbani smart filters. Each category has its own quick choices ("55 inch", "Gaming", "Under 150 JOD") shown as one row
// at the top, plus "More filters" (brand, storage, processor, screen...) and sorting. What to offer comes from
// /api/filters.json, built from facets.py, so a new category gets its filters without changing this file.
// List pages: the page works fully without this script (the full list, grouped by brand). Choices live in the address
// (?q=t55|t65&sort=price) so a filtered list can be shared and Back returns to it. Nothing is sent anywhere.
(function () {
  var en = document.documentElement.lang === "en", pre = en ? "/en" : "";
  var T = en ? {
    more: "More filters", clear: "Clear all", sort: "Sort", found: "{n} products", none: "Nothing matches these filters.",
    price: "Price (JOD)", min: "From", max: "To", two: "At 2+ shops", drop: "Price dropped", show: "Show {n} products",
    s0: "Most compared", s1: "Lowest price", s2: "Highest price", s3: "Biggest saving between shops", s4: "Biggest price drop",
    from: "From {p} JOD", was: "Was {p}", one: "1 shop", many: "{n} shops", all: "All"
  } : {
    more: "فلاتر أكثر", clear: "مسح الكل", sort: "الترتيب", found: "{n} منتج", none: "لا يوجد منتج بهذه الاختيارات.",
    price: "السعر (دينار)", min: "من", max: "إلى", two: "في متجرين أو أكثر", drop: "انخفض سعره", show: "عرض {n} منتج",
    s0: "الأكثر مقارنة", s1: "الأقل سعراً", s2: "الأعلى سعراً", s3: "أكبر فرق بين المتاجر", s4: "أكبر انخفاض في السعر",
    from: "من {p} د.أ", was: "كان {p}", one: "متجر واحد", many: "{n} متاجر", all: "الكل"
  };
  var NUMERIC = {storage: 1, ram: 1, size: 1, screen: 1};
  var config = null;

  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text != null) n.textContent = text;
    return n;
  }
  function fmt(s, o) { return s.replace(/\{(\w+)\}/g, function (_, k) { return o[k]; }); }
  function money(p) { return (Math.round(p * 100) / 100).toLocaleString("en-US", {maximumFractionDigits: 2}); }
  function gb(v) { var n = parseFloat(v); return /TB/.test(v) ? n * 1024 : n; }
  function name(o) { return en ? o.en : o.ar; }
  function loadConfig() {
    if (config) return Promise.resolve(config);
    return fetch("/api/filters.json").then(function (r) { return r.ok ? r.json() : null; }).then(function (c) { config = c; return c; });
  }

  // A filter bar over a list of products. opts: box, cat, onlyBrand, items, groups (false = quick choices only),
  // url (keep choices in the address), render(hits, filtering)
  function Bar(opts) {
    var self = this, cfg = (config.categories || {})[opts.cat] || {quick: [], groups: []};
    var quick = cfg.quick || [], groups = opts.groups === false ? [] : (cfg.groups || []).filter(function (g) {
      return !(opts.onlyBrand && g.key === "brand");
    });
    var st = read(), panel, toggle, count, sortSel;

    function read() {
      var q = opts.url ? new URLSearchParams(location.search) : new URLSearchParams(), s = {q: [], sel: {}, sort: q.get("sort") || "",
        min: q.get("min") || "", max: q.get("max") || "", two: q.get("two") === "1", drop: q.get("drop") === "1"};
      if (q.get("q")) s.q = q.get("q").split("|");
      (opts.groups === false ? [] : ((config.categories[opts.cat] || {}).groups || [])).forEach(function (g) {
        var v = q.get(g.key); if (v) s.sel[g.key] = v.split("|");
      });
      return s;
    }
    function write() {
      if (!opts.url) return;
      var q = new URLSearchParams();
      if (st.q.length) q.set("q", st.q.join("|"));
      groups.forEach(function (g) { if ((st.sel[g.key] || []).length) q.set(g.key, st.sel[g.key].join("|")); });
      ["sort", "min", "max"].forEach(function (k) { if (st[k]) q.set(k, st[k]); });
      if (st.two) q.set("two", "1");
      if (st.drop) q.set("drop", "1");
      var s = q.toString();
      history.replaceState(null, "", location.pathname + (s ? "?" + s : "") + location.hash);
    }
    function moreCount() {
      var n = 0;
      groups.forEach(function (g) { n += (st.sel[g.key] || []).length; });
      return n + (st.min ? 1 : 0) + (st.max ? 1 : 0) + (st.two ? 1 : 0) + (st.drop ? 1 : 0);
    }
    function quickOk(v, skipSet) {
      var tags = v.q || [], bySet = {};
      st.q.forEach(function (id) {
        var d = quick.find(function (x) { return x.id === id; });
        if (d && d.set !== skipSet) (bySet[d.set] = bySet[d.set] || []).push(id);
      });
      return Object.keys(bySet).every(function (s) { return bySet[s].some(function (id) { return tags.indexOf(id) >= 0; }); });
    }
    function passes(v, skipGroup, skipSet) {
      var f = v.f || {};
      if (opts.onlyBrand && v.brand !== opts.onlyBrand) return false;
      if (!quickOk(v, skipSet)) return false;
      for (var i = 0; i < groups.length; i++) {
        var g = groups[i].key, want = st.sel[g];
        if (g !== skipGroup && want && want.length && want.indexOf(f[g]) < 0) return false;
      }
      var p = v.best_price != null ? v.best_price : v.p;
      if ((st.min || st.max) && p == null) return false;
      if (st.min && p < parseFloat(st.min)) return false;
      if (st.max && p > parseFloat(st.max)) return false;
      if (st.two && (v.ranked_shops != null ? v.ranked_shops : v.r || 0) < 2) return false;
      if (st.drop && !(v.drop > 0)) return false;
      return true;
    }
    function price(v) { return v.best_price != null ? v.best_price : v.p; }
    function sorted(list) {
      var by = {
        price: function (a, b) { return (price(a) == null) - (price(b) == null) || price(a) - price(b); },
        high: function (a, b) { return (price(a) == null) - (price(b) == null) || price(b) - price(a); },
        save: function (a, b) { return (b.save || 0) - (a.save || 0); },
        drop: function (a, b) { return (b.drop || 0) - (a.drop || 0); }
      }[st.sort];
      return by ? list.slice().sort(by) : list;
    }
    function chip(text, on, n, click) {
      var b = el("button", {type: "button", "class": "fchip", "aria-pressed": on ? "true" : "false"});
      b.appendChild(document.createTextNode(text));
      if (n != null) b.appendChild(el("small", null, String(n)));
      if (!on && n === 0) b.disabled = true;
      b.addEventListener("click", click);
      return b;
    }
    function fieldset(title, kids) {
      var sec = el("fieldset", {"class": "fgroup"});
      if (title) sec.appendChild(el("legend", null, title));
      var row = el("div", {"class": "fchips"});
      kids.forEach(function (c) { row.appendChild(c); });
      sec.appendChild(row);
      return sec;
    }

    opts.box.textContent = "";
    var quickRow = el("div", {"class": "fquick", role: "group"});
    var bar = el("div", {"class": "fbar"});
    if (groups.length) {
      toggle = el("button", {type: "button", "class": "fbtn", "aria-expanded": "false"});
      toggle.addEventListener("click", function () { open(panel.hidden); });
      bar.appendChild(toggle);
    }
    sortSel = el("select", {"aria-label": T.sort});
    [["", T.s0], ["price", T.s1], ["high", T.s2], ["save", T.s3], ["drop", T.s4]].forEach(function (o) {
      if (opts.groups === false && (o[0] === "save" || o[0] === "drop")) return;   // search results carry prices only
      var op = el("option", {value: o[0]}, o[1]);
      if (o[0] === st.sort) op.selected = true;
      sortSel.appendChild(op);
    });
    sortSel.addEventListener("change", function () { st.sort = sortSel.value; update(); });
    count = el("span", {"class": "fcount mute", "aria-live": "polite"});
    bar.appendChild(sortSel); bar.appendChild(count);
    panel = el("div", {"class": "fpanel"});
    panel.hidden = true;
    opts.box.appendChild(quickRow); opts.box.appendChild(bar); opts.box.appendChild(panel);
    opts.box.hidden = false;

    function open(yes) { panel.hidden = !yes; if (toggle) toggle.setAttribute("aria-expanded", yes ? "true" : "false"); }

    function drawQuick() {
      quickRow.textContent = "";
      quick.forEach(function (d) {
        var on = st.q.indexOf(d.id) >= 0;
        var n = opts.items.filter(function (v) { return passes(v, null, d.set) && (v.q || []).indexOf(d.id) >= 0; }).length;
        if (!on && !opts.items.some(function (v) { return (v.q || []).indexOf(d.id) >= 0; })) return;   // nothing like it on the list
        quickRow.appendChild(chip(name(d), on, n, function () {
          var i = st.q.indexOf(d.id);
          if (i >= 0) st.q.splice(i, 1); else st.q.push(d.id);
          update();
        }));
      });
      quickRow.hidden = !quickRow.childNodes.length;
    }
    function drawPanel(total) {
      panel.textContent = "";
      groups.forEach(function (g) {
        var have = {}, counts = {};
        opts.items.forEach(function (v) {
          var x = (v.f || {})[g.key];
          if (!x || (opts.onlyBrand && v.brand !== opts.onlyBrand)) return;
          have[x] = (have[x] || 0) + 1;
          if (passes(v, g.key, null)) counts[x] = (counts[x] || 0) + 1;
        });
        var values = Object.keys(have);
        if (values.length < 2) return;
        values.sort(NUMERIC[g.key] ? function (a, b) { return gb(a) - gb(b); } : function (a, b) { return have[b] - have[a]; });
        var chosen = st.sel[g.key] || [];
        panel.appendChild(fieldset(name(g), values.map(function (x) {
          var label = x, vn = (config.values || {})[x];
          if (vn) label = name(vn);
          else if (g.key === "brand" && !en) { var hit = opts.items.find(function (v) { return v.brand === x; }); if (hit) label = hit.brand_ar; }
          return chip(label, chosen.indexOf(x) >= 0, counts[x] || 0, function () {
            var list = (st.sel[g.key] || []).slice(), i = list.indexOf(x);
            if (i >= 0) list.splice(i, 1); else list.push(x);
            st.sel[g.key] = list;
            update();
          });
        })));
      });
      var pf = el("fieldset", {"class": "fgroup"});
      pf.appendChild(el("legend", null, T.price));
      var row = el("div", {"class": "fprice"});
      ["min", "max"].forEach(function (k) {
        var lab = el("label", null, T[k] + " ");
        var inp = el("input", {type: "number", inputmode: "numeric", min: "0", step: "1", value: st[k]});
        inp.addEventListener("change", function () { st[k] = inp.value && +inp.value >= 0 ? String(Math.round(+inp.value)) : ""; update(); });
        lab.appendChild(inp);
        row.appendChild(lab);
      });
      pf.appendChild(row);
      panel.appendChild(pf);
      panel.appendChild(fieldset("", [
        chip(T.two, st.two, null, function () { st.two = !st.two; update(); }),
        chip(T.drop, st.drop, null, function () { st.drop = !st.drop; update(); })
      ]));
      var foot = el("div", {"class": "ffoot"});
      var done = el("button", {type: "button", "class": "fdone"}, fmt(T.show, {n: total}));
      done.addEventListener("click", function () { open(false); });
      foot.appendChild(done);
      panel.appendChild(foot);
    }

    function update() {
      write();
      var hits = sorted(opts.items.filter(function (v) { return passes(v, null, null); }));
      var n = moreCount(), filtering = !!(n || st.q.length || st.sort);
      if (toggle) toggle.textContent = T.more + (n ? " (" + n + ")" : "");
      count.textContent = fmt(T.found, {n: hits.length});
      drawQuick();
      if (groups.length) drawPanel(hits.length);
      var old = bar.querySelector(".flink");
      if (old) old.remove();
      if (n || st.q.length) {
        var clear = el("button", {type: "button", "class": "flink"}, T.clear);
        clear.addEventListener("click", function () { st = {q: [], sel: {}, sort: st.sort, min: "", max: "", two: false, drop: false}; update(); });
        bar.insertBefore(clear, count);
      }
      opts.render(hits, filtering);
    }
    self.update = update;
    self.setItems = function (items) { opts.items = items; update(); };
    update();
  }

  function card(v) {
    var li = el("li"), a = el("a", {href: pre + "/p/" + (v.slug || v.u)});
    a.appendChild(el("span", {"class": "name"}, (v.label || v.n || "").trim()));
    var p = v.best_price != null ? v.best_price : v.p;
    if (p != null) a.appendChild(el("span", {"class": "tag"}, fmt(T.from, {p: money(p)})));
    if (v.was) a.appendChild(el("s", {"class": "mute"}, fmt(T.was, {p: money(v.was)})));
    a.appendChild(el("span", {"class": "mute"}, v.shops === 1 || v.s === 1 ? T.one : fmt(T.many, {n: v.shops || v.s})));
    li.appendChild(a);
    return li;
  }

  window.DerbaniFilters = {Bar: Bar, card: card, loadConfig: loadConfig, T: T};

  // ---- list pages: /tvs, /en/laptops/asus ...
  var box = document.getElementById("flt"), all = document.getElementById("all");
  if (!box || !all || !window.fetch) return;
  var cat = box.getAttribute("data-cat");
  Promise.all([loadConfig(), fetch("/api/list-" + cat + ".json").then(function (r) { return r.ok ? r.json() : null; })]).then(function (x) {
    var d = x[1];
    if (!x[0] || !d || !d.results || !d.results.length || !d.results[0].q) return;   // older files: leave the plain list
    var results = el("ul", {"class": "list", id: "fres"});
    results.hidden = true;
    all.parentNode.insertBefore(results, all);
    new Bar({box: box, cat: cat, onlyBrand: box.getAttribute("data-brand") || "", items: d.results, url: true, render: function (hits, filtering) {
      results.textContent = "";
      if (filtering) {
        if (!hits.length) results.appendChild(el("li", {"class": "mute"}, T.none));
        hits.forEach(function (v) { results.appendChild(card(v)); });
      }
      results.hidden = !filtering;
      all.hidden = filtering;
    }});
  }).catch(function () { /* offline: the plain list stays */ });
})();
