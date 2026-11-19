// Derbani compare (plan 2b.5). Pick up to 4 products of the same kind on their pages, then see them side by side.
// The choice lives only in this browser (localStorage); nothing is sent anywhere. /compare.json is built every hour.
(function () {
  var en = document.documentElement.lang === "en";
  var KEY = "derbani-compare", MAX = 4;
  var T = en ? {
    add: "+ Compare", added: "✓ In compare", bar: "Compare", full: "You can compare up to 4. Remove one first.",
    other: "Compare holds one kind at a time, so it was started again with this product.",
    empty: "Nothing to compare yet. Use the “Compare” button on a product page.",
    one: "Add one more product to compare.", price: "Lowest price", shops: "Shops", at: "at", jod: "JOD",
    remove: "Remove", src: "Maker's page", none: "Not stated by the maker", nosrc: "Not checked yet", share: "Link to this comparison:"
  } : {
    add: "+ قارن", added: "✓ في المقارنة", bar: "قارن", full: "يمكنك مقارنة 4 منتجات كحد أقصى. احذف واحداً أولاً.",
    other: "المقارنة لنوع واحد في كل مرة، لذلك بدأنا مقارنة جديدة بهذا المنتج.",
    empty: "لا يوجد ما نقارنه بعد. استخدم زر «قارن» في صفحة أي منتج.",
    one: "أضف منتجاً آخر للمقارنة.", price: "أقل سعر", shops: "عدد المتاجر", at: "في", jod: "دينار",
    remove: "إزالة", src: "صفحة الشركة", none: "لا تذكره الشركة", nosrc: "لم تُراجع بعد", share: "رابط هذه المقارنة:"
  };
  var pre = en ? "/en" : "";

  function load() {
    try { var v = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(v) ? v : []; } catch (e) { return []; }
  }
  function save(list) { try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) { /* private window: works for this page only */ } }
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text != null) n.textContent = text;
    return n;
  }
  function link(list) { return pre + "/compare?ids=" + list.map(function (x) { return x.id; }).join(","); }

  var bar;
  function drawBar(list) {
    if (document.getElementById("compare")) return;     // the compare page itself needs no bar
    if (!bar) { bar = el("a", { "class": "cmpbar" }); document.body.appendChild(bar); }
    bar.hidden = list.length === 0;
    bar.textContent = T.bar + " (" + list.length + ")";
    bar.href = link(list);
  }

  // ---- the button on a product page ----
  var btn = document.querySelector("button.cmp");
  var note;
  function drawBtn(list) {
    if (!btn) return;
    var inList = list.some(function (x) { return String(x.id) === btn.dataset.id; });
    btn.textContent = inList ? T.added : T.add;
    btn.classList.toggle("on", inList);
    btn.hidden = false;
  }
  function say(text) {
    if (!note) { note = el("span", { "class": "mute cmpnote", role: "status" }); btn.parentNode.appendChild(note); }
    note.textContent = " " + text;
  }
  if (btn) {
    btn.addEventListener("click", function () {
      var list = load(), id = btn.dataset.id, cat = btn.dataset.cat;
      if (list.some(function (x) { return String(x.id) === id; })) {
        list = list.filter(function (x) { return String(x.id) !== id; });
      } else if (list.length && list[0].c !== cat) {
        list = [{ id: Number(id), c: cat }]; say(T.other);
      } else if (list.length >= MAX) {
        say(T.full); return;
      } else {
        list.push({ id: Number(id), c: cat });
      }
      save(list); drawBtn(list); drawBar(list);
    });
  }
  var start = load();
  drawBtn(start); drawBar(start);

  // ---- the compare page ----
  var table = document.getElementById("compare");
  if (!table) return;
  var status = document.getElementById("cmp-status");
  var fromUrl = (new URLSearchParams(location.search).get("ids") || "").split(",").filter(function (x) { return /^\d+$/.test(x); }).slice(0, MAX);

  fetch("/compare.json").then(function (r) { return r.json(); }).then(function (all) {
    var ids = fromUrl.length ? fromUrl : load().map(function (x) { return String(x.id); });
    var items = ids.map(function (id) { return all[id] ? Object.assign({ id: id }, all[id]) : null; }).filter(Boolean);
    if (items.length) items = items.filter(function (x) { return x.c === items[0].c; });   // one kind at a time
    if (fromUrl.length) save(items.map(function (x) { return { id: Number(x.id), c: x.c }; }));
    draw(items);

    function draw(items) {
      table.textContent = "";
      if (!items.length) { status.textContent = T.empty; return; }
      status.textContent = items.length === 1 ? T.one : "";
      var head = el("tr"); head.appendChild(el("th"));
      items.forEach(function (x) {
        var th = el("th", { scope: "col" });
        if (x.i) th.appendChild(el("img", { src: x.i, alt: "", width: "90", height: "90", loading: "lazy", referrerpolicy: "no-referrer" }));
        var a = el("a", { href: pre + "/p/" + x.u }, x.n); th.appendChild(a);
        var rm = el("button", { type: "button", "class": "rm", "aria-label": T.remove + " " + x.n }, "×");
        rm.addEventListener("click", function () {
          var rest = items.filter(function (y) { return y.id !== x.id; });
          save(rest.map(function (y) { return { id: Number(y.id), c: y.c }; }));
          history.replaceState(null, "", link(rest.map(function (y) { return { id: y.id }; })));
          draw(rest);
        });
        th.appendChild(rm);
        head.appendChild(th);
      });
      var thead = el("thead"); thead.appendChild(head); table.appendChild(thead);
      var body = el("tbody");
      var prices = items.map(function (x) { return x.p; }).filter(function (p) { return p != null; });
      var low = prices.length ? Math.min.apply(null, prices) : null;
      row(T.price, items.map(function (x) {
        return x.p == null ? "—" : x.p.toFixed(x.p % 1 ? 2 : 0) + " " + T.jod + (x.b ? " " + T.at + " " + x.b : "");
      }), items.map(function (x) { return items.length > 1 && x.p === low; }));
      row(T.shops, items.map(function (x) { return String(x.s); }));
      // every specification any of them states, in the order the maker data gives
      var keys = [], labels = {};
      items.forEach(function (x) { x.r.forEach(function (r) { if (keys.indexOf(r[0]) < 0) { keys.push(r[0]); labels[r[0]] = en ? r[1] : r[2]; } }); });
      keys.forEach(function (k) {
        var vals = items.map(function (x) {
          var hit = x.r.filter(function (r) { return r[0] === k; })[0];
          return hit ? hit[3] : (x.src ? T.none : T.nosrc);
        });
        var differ = vals.some(function (v) { return v !== vals[0]; });
        row(labels[k], vals, null, differ);
      });
      table.appendChild(body);
      var share = location.origin + link(items.map(function (x) { return { id: x.id }; }));
      if (items.length > 1) status.textContent = T.share + " " + share;

      function row(label, vals, best, differ) {
        var tr = el("tr", differ ? { "class": "diff" } : {});
        tr.appendChild(el("th", { scope: "row" }, label));
        vals.forEach(function (v, i) { tr.appendChild(el("td", best && best[i] ? { "class": "low" } : {}, v)); });
        body.appendChild(tr);
      }
    }
  }).catch(function () { status.textContent = T.empty; });
})();

// "Get it on Google Play" bar (shown only when the site sets the Play link, and only to Android visitors; a closed bar stays closed)
(function () {
  var bar = document.getElementById("appbar");
  if (!bar || !bar.dataset.play || !/Android/i.test(navigator.userAgent)) return;
  try { if (localStorage.getItem("derbani-appbar") === "closed") return; } catch (e) { /* private window */ }
  bar.hidden = false;
  bar.querySelector(".x").addEventListener("click", function () {
    bar.hidden = true;
    try { localStorage.setItem("derbani-appbar", "closed"); } catch (e) { /* private window */ }
  });
})();

// Copy the product's name in one tap, and hide list pictures a shop no longer serves (no inline scripts: CSP).
(function () {
  var en = document.documentElement.lang === "en";
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest("button.copy");
    if (!b) return;
    var text = b.getAttribute("data-copy") || "", label = b.textContent;
    var done = function () { b.textContent = en ? "Copied" : "تم النسخ"; setTimeout(function () { b.textContent = label; }, 1600); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { window.prompt("", text); });
    } else { window.prompt("", text); }
  });
  // a shop picture that does not load shows the plain shaded box, not the browser's broken-picture mark;
  // pictures that failed before this script ran are found by the scan below
  function noPic(t) {
    if (t && t.tagName === "IMG" && (t.classList.contains("thumb") || t.classList.contains("shot"))) {
      t.classList.add("none"); t.removeAttribute("src"); t.removeAttribute("srcset");
    }
  }
  document.addEventListener("error", function (ev) { noPic(ev.target); }, true);
  Array.prototype.forEach.call(document.querySelectorAll("img.thumb, img.shot"), function (t) {
    if (t.complete && t.getAttribute("src") && t.naturalWidth === 0) noPic(t);
  });
})();

// Derbani saved products and price alerts (same feature as the app's Saved screen).
// The list lives only in this browser (localStorage); nothing is sent anywhere. /prices.json is built every hour.
// An alert shows when today's lowest price is under the price the visitor last saw, or at/under their target price.
(function () {
  var en = document.documentElement.lang === "en";
  var KEY = "derbani-saved", MAX = 100;
  var T = en ? {
    save: "♡ Save", saved: "♥ Saved", target: "Tell me when it is", under: "JOD or less", set: "Set", clear: "Remove target",
    empty: "Nothing saved yet. Use the “Save” button on a product page.", was: "was", now: "now", jod: "JOD",
    dropped: "Cheaper since you last looked", hit: "At or under your price", yourPrice: "Your price", none: "Not sold right now",
    remove: "Remove", seen: "Mark as seen", targetSet: "Saved. We will show it here when the price reaches {p} JOD.",
    savedNote: "Saved. Open “Saved” at the top any time."
  } : {
    save: "♡ احفظ", saved: "♥ محفوظ", target: "نبّهني عندما يصبح", under: "دينار أو أقل", set: "حدّد", clear: "إزالة السعر",
    empty: "لا يوجد شيء محفوظ بعد. استخدم زر «احفظ» في صفحة أي منتج.", was: "كان", now: "الآن", jod: "دينار",
    dropped: "صار أرخص منذ آخر مرة رأيته", hit: "وصل إلى السعر الذي تريده أو أقل", yourPrice: "سعرك", none: "غير متوفر حالياً",
    remove: "إزالة", seen: "تمت المشاهدة", targetSet: "تم. سنظهره هنا عندما يصل السعر إلى {p} دينار.",
    savedNote: "تم الحفظ. افتح «المحفوظة» في الأعلى في أي وقت."
  };
  var pre = en ? "/en" : "";

  function load() {
    try { var v = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(v) ? v : []; } catch (e) { return []; }
  }
  function store(list) { try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX))); } catch (e) { /* private window */ } }
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text != null) n.textContent = text;
    return n;
  }
  function money(p) { return p.toFixed(p % 1 ? 2 : 0); }
  function find(list, id) { return list.filter(function (x) { return String(x.id) === String(id); })[0]; }
  function alertOf(x, price) {
    if (price == null) return null;
    if (x.target != null && price <= x.target && !(x.seen != null && x.seen <= x.target)) return "hit";
    if (x.seen != null && price < x.seen - 0.001) return "dropped";
    return null;
  }

  var prices = null;
  function withPrices(fn) {
    if (prices) return fn(prices);
    fetch("/prices.json").then(function (r) { return r.json(); }).then(function (p) { prices = p; fn(p); }).catch(function () { fn({}); });
  }

  // ---- count of alerts next to "Saved" in the menu ----
  function drawCount() {
    var list = load();
    var badges = document.querySelectorAll(".savedn");
    if (!list.length) { badges.forEach(function (b) { b.hidden = true; }); return; }
    withPrices(function (p) {
      var n = list.filter(function (x) { return alertOf(x, p[x.id]); }).length;
      badges.forEach(function (b) { b.hidden = n === 0; b.textContent = String(n); });
    });
  }

  // ---- the button and target price on a product page ----
  var btn = document.querySelector("button.save");
  var box, note;
  function say(text) {
    if (!note) { note = el("span", { "class": "mute cmpnote", role: "status" }); btn.parentNode.appendChild(note); }
    note.textContent = " " + text;
  }
  function drawBtn() {
    var list = load(), x = find(list, btn.dataset.id);
    btn.textContent = x ? T.saved : T.save;
    btn.classList.toggle("on", !!x);
    btn.hidden = false;
    if (box) { box.remove(); box = null; }
    if (!x) return;
    box = el("span", { "class": "target" });
    var lab = el("label", {}, T.target + " ");
    var inp = el("input", { type: "number", min: "1", step: "1", inputmode: "decimal", "aria-label": T.target });
    if (x.target != null) inp.value = x.target;
    lab.appendChild(inp); lab.appendChild(document.createTextNode(" " + T.under));
    var set = el("button", { type: "button" }, T.set);
    set.addEventListener("click", function () {
      var v = parseFloat(inp.value), all = load(), it = find(all, btn.dataset.id);
      if (!it) return;
      it.target = v > 0 ? v : null;
      store(all); drawCount();
      say(it.target != null ? T.targetSet.replace("{p}", money(it.target)) : "");
    });
    box.appendChild(lab); box.appendChild(set);
    btn.parentNode.insertBefore(box, btn.nextSibling);
  }
  if (btn) {
    btn.addEventListener("click", function () {
      var list = load(), id = btn.dataset.id;
      if (find(list, id)) {
        list = list.filter(function (x) { return String(x.id) !== id; });
        say("");
      } else {
        var price = parseFloat(btn.dataset.price);
        list.unshift({ id: Number(id), n: btn.dataset.name, u: btn.dataset.slug, i: btn.dataset.img || "",
                       seen: isNaN(price) ? null : price, target: null });
        say(T.savedNote);
      }
      store(list); drawBtn(); drawCount();
    });
    drawBtn();
    // the visitor is looking at today's price now: an alert for this product is done
    var it0 = find(load(), btn.dataset.id), p0 = parseFloat(btn.dataset.price);
    if (it0 && !isNaN(p0) && it0.seen !== p0) { var all0 = load(); find(all0, btn.dataset.id).seen = p0; store(all0); }
  }
  drawCount();

  // ---- the Saved page ----
  var page = document.getElementById("saved");
  if (!page) return;
  var status = document.getElementById("saved-status");
  withPrices(function (p) {
    var list = load();
    if (!list.length) { status.textContent = T.empty; return; }
    list.sort(function (a, b) { return (alertOf(b, p[b.id]) ? 1 : 0) - (alertOf(a, p[a.id]) ? 1 : 0); });
    list.forEach(function (x) {
      var price = p[x.id], why = alertOf(x, price);
      var row = el("div", { "class": "savedrow" + (why ? " alert" : "") });
      if (x.i) row.appendChild(el("img", { src: x.i, alt: "", width: "64", height: "64", loading: "lazy", referrerpolicy: "no-referrer" }));
      var mid = el("div");
      mid.appendChild(el("a", { href: pre + "/p/" + x.u }, x.n));
      var line = price == null ? T.none : T.now + " " + money(price) + " " + T.jod;
      if (why === "dropped") line += " (" + T.was + " " + money(x.seen) + ")";
      mid.appendChild(el("div", { "class": "num" }, line));
      if (x.target != null) mid.appendChild(el("div", { "class": "mute" }, T.yourPrice + ": " + money(x.target) + " " + T.jod));
      if (why) mid.appendChild(el("b", { "class": "why" }, why === "hit" ? T.hit : T.dropped));
      row.appendChild(mid);
      var actions = el("div", { "class": "acts" });
      if (why) {
        var ok = el("button", { type: "button" }, T.seen);
        ok.addEventListener("click", function () {
          var all = load(), it = find(all, x.id);
          if (it) { it.seen = price; store(all); }
          row.classList.remove("alert"); ok.remove(); var w = row.querySelector(".why"); if (w) w.remove(); drawCount();
        });
        actions.appendChild(ok);
      }
      var rm = el("button", { type: "button", "class": "rm", "aria-label": T.remove + " " + x.n }, "×");
      rm.addEventListener("click", function () {
        store(load().filter(function (y) { return String(y.id) !== String(x.id); }));
        row.remove(); drawCount();
        if (!load().length) status.textContent = T.empty;
      });
      actions.appendChild(rm);
      row.appendChild(actions);
      page.appendChild(row);
    });
  });
})();

// Kamkam design 2 (2026-11-18): light/dark switch, share button, recently viewed, the current menu item.
// Like the rest of this file: everything stays in this browser (localStorage); nothing is sent anywhere.
(function () {
  var root = document.documentElement, en = root.lang === "en", pre = en ? "/en" : "";
  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function put(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* private window */ } }
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text != null) n.textContent = text;
    return n;
  }

  // ---- light / dark: follows the phone or computer until the visitor picks one ----
  var THEME = "kamkam-theme", dark = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  function apply(v) { if (v === "dark" || v === "light") root.setAttribute("data-theme", v); else root.removeAttribute("data-theme"); }
  apply(get(THEME));
  var tb = document.querySelector("button.theme");
  if (tb) {
    tb.hidden = false;
    tb.addEventListener("click", function () {
      var now = root.getAttribute("data-theme") || (dark && dark.matches ? "dark" : "light");
      var next = now === "dark" ? "light" : "dark";
      // picking what the device already uses means "follow the device" again
      put(THEME, (dark && dark.matches ? "dark" : "light") === next ? null : next);
      apply(get(THEME) || null);
      if (!get(THEME)) root.removeAttribute("data-theme");
    });
  }

  // ---- the current page in the menu ----
  var here = location.pathname.replace(/\.html$/, "").replace(/\/$/, "") || "/";
  document.querySelectorAll("header.site nav a").forEach(function (a) {
    var p = a.getAttribute("href").replace(/\/$/, "") || "/";
    if (p === here) {
      a.setAttribute("aria-current", "page");
      var d = a.closest("details.cats");
      if (d) d.classList.add("here");
    }
  });
  // the categories menu closes on a click outside it, and on Escape
  var cm = document.querySelector("header.site details.cats");
  if (cm) {
    document.addEventListener("click", function (ev) { if (cm.open && !cm.contains(ev.target)) cm.open = false; });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && cm.open) { cm.open = false; cm.querySelector("summary").focus(); }
    });
  }

  // ---- share a product: the phone's share sheet, or the link copied ----
  var sb = document.querySelector("button.share");
  if (sb) {
    sb.hidden = false;
    sb.addEventListener("click", function () {
      var u = sb.dataset.url, t = sb.dataset.title;
      if (navigator.share) { navigator.share({ title: t, url: u }).catch(function () {}); return; }
      var done = function () { var s = sb.querySelector("span"), old = s.textContent; s.textContent = sb.dataset.done; setTimeout(function () { s.textContent = old; }, 2000); };
      if (navigator.clipboard) navigator.clipboard.writeText(u).then(done, function () { window.prompt("", u); });
      else window.prompt("", u);
    });
  }

  // ---- recently viewed: kept when a product page opens, shown on the home page ----
  var RECENT = "kamkam-recent", MAX = 12;
  function recent() { try { var v = JSON.parse(get(RECENT) || "[]"); return Array.isArray(v) ? v : []; } catch (e) { return []; } }
  var me = document.querySelector("button.save[data-id]");
  if (me) {
    var item = { id: Number(me.dataset.id), n: me.dataset.name, u: me.dataset.slug, i: me.dataset.img || "" };
    var list = recent().filter(function (x) { return x.id !== item.id; });
    list.unshift(item);
    put(RECENT, JSON.stringify(list.slice(0, MAX)));
  }
  var box = document.getElementById("recent"), ul = document.getElementById("recentlist");
  var seen = recent();
  if (box && ul && seen.length) {
    fetch("/prices.json").then(function (r) { return r.json(); }).catch(function () { return {}; }).then(function (p) {
      seen.forEach(function (x) {
        var a = el("a", { href: pre + "/p/" + x.u });
        a.appendChild(x.i ? el("img", { "class": "thumb", src: x.i, alt: "", width: "96", height: "96", loading: "lazy", referrerpolicy: "no-referrer" })
                          : el("span", { "class": "thumb none" }));
        a.appendChild(el("span", { "class": "name" }, x.n));
        var price = p[x.id];
        if (price != null) a.appendChild(el("span", { "class": "tag" }, box.dataset.from.replace("{p}", price.toFixed(price % 1 ? 2 : 0))));
        var li = el("li"); li.appendChild(a); ul.appendChild(li);
      });
      box.hidden = false;
    });
  }
})();
