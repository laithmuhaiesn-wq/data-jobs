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
  document.addEventListener("error", function (ev) {
    var t = ev.target;
    if (t && t.tagName === "IMG" && t.classList.contains("thumb")) { t.classList.add("none"); t.removeAttribute("src"); }
  }, true);
})();
