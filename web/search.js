// Derbani site search. Reads /search-index.json (built every hour with the pages) and lists matching products.
// The folding rules (Arabic letters, digits, Arabic brand names) come from the same index, so they match the app's search.
// The search rules, the same as search.py (the API) and local_search.dart (the app): the nightly search check compares them.
var KamkamSearch = (function () {
  var AR = "؀-ۿ", cut = new RegExp("[" + AR + "]+|[a-z0-9]+", "g"), tok = new RegExp("[a-z0-9" + AR + "]+", "g");
  var arabic = new RegExp("^[" + AR + "]"), letters = /^\p{L}+$/u;
  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

  function fold(s, map) {
    s = s.normalize("NFKC").toLowerCase().replace(/[ً-ٰٟ]/g, "");
    s = s.normalize("NFD").replace(/[̀-ͯ]/g, "").normalize("NFC");
    s = s.replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 0x660); })
         .replace(/[۰-۹]/g, function (d) { return String(d.charCodeAt(0) - 0x6F0); });
    var out = "";
    for (var i = 0; i < s.length; i++) out += has(map, s[i]) ? map[s[i]] : s[i];
    return out;
  }

  // One typing slip: one letter wrong, missing, extra, or two neighbours swapped.
  function near(a, b) {
    if (Math.abs(a.length - b.length) > 1) return false;
    var i;
    if (a.length === b.length) {
      var d = [];
      for (i = 0; i < a.length; i++) if (a[i] !== b[i]) d.push(i);
      return d.length === 1 || (d.length === 2 && d[1] === d[0] + 1 && a[d[0]] === b[d[1]] && a[d[1]] === b[d[0]]);
    }
    if (a.length > b.length) { var t = a; a = b; b = t; }
    i = 0;
    while (i < a.length && a[i] === b[i]) i++;
    return a.slice(i) === b.slice(i + 1);
  }

  function arabicWord(w, ix) {
    var forms = [w], i, k, hit;
    (ix.articles || []).forEach(function (a) { if (w.indexOf(a) === 0 && w.length - a.length >= 2) forms.push(w.slice(a.length)); });
    forms.slice().forEach(function (f) { if (f.slice(-2) === "ات" && f.length >= 5) forms.push(f.slice(0, -2)); });
    for (i = 0; i < forms.length; i++) {
      if (ix.stop.indexOf(forms[i]) >= 0) return "";
      if (has(ix.words, forms[i])) return ix.words[forms[i]];
    }
    for (i = 0; i < forms.length; i++) {
      if (forms[i].length < 4) continue;
      hit = null;
      for (k in ix.words) if (k.length >= 4 && near(forms[i], k)) { hit = k; break; }
      if (hit) return ix.words[hit];
    }
    return w;
  }

  function words(text, ix) {
    var keys = Object.keys(ix.phrases).sort(function (a, b) { return b.length - a.length; });
    // (a letter before the phrase is put back, and the one after is only looked at, so no lookbehind is needed)
    var re = new RegExp("(^|[^" + AR + "a-z])(" + keys.join("|") + ")(?![" + AR + "a-z])", "g");
    var t = fold(text, ix.letters).replace(re, function (m, before, p) { return before + " " + ix.phrases[p] + " "; });
    var parts = (t.match(cut) || []).map(function (w) {
      if (arabic.test(w)) w = arabicWord(w, ix);
      return ix.en && has(ix.en, w) ? ix.en[w] : w;
    });
    t = parts.filter(Boolean).join(" ").replace(/\b(\d+) (gb|tb|g)\b/g, "$1$2").replace(/\b([asmxz]) (\d{1,3})\b/g, "$1$2");
    var out = [];
    t.split(" ").forEach(function (w) { if (w && ix.stop.indexOf(w) < 0 && out.indexOf(w) < 0) out.push(w); });
    return out.slice(0, ix.max || 8);
  }

  // The kind named in the query, if any: "تابلت هونر" -> "tablet".
  function kind(text, ix) {
    var cats = ix.categories || {}, ws = fold(text, ix.letters).match(cut) || [];
    for (var i = 0; i < ws.length; i++) {
      if (has(cats, ws[i])) return cats[ws[i]];
      if (ws[i].indexOf("ال") === 0 && has(cats, ws[i].slice(2))) return cats[ws[i].slice(2)];
    }
    return null;
  }

  // The matching products, best first: exact before forgiven slips, then most compared, then cheapest.
  function find(text, ix) {
    var want = words(text, ix), cat = kind(text, ix), known = ix.known || [], forgive = {}, found = [];
    if (!want.length && !cat) return [];
    want.forEach(function (w) {   // a slip is forgiven only in a word no product contains, never in a real name or a model number
      if (known.indexOf(w) < 0 && w.length >= 4 && letters.test(w) &&
          !ix.items.some(function (it) { return it.h.indexOf(w) >= 0 || it.k.indexOf(w) >= 0; })) forgive[w] = 1;
    });
    ix.items.forEach(function (it) {
      if (cat && it.c !== cat) return;
      var slips = 0;
      var ok = want.every(function (w) {
        if (it.h.indexOf(w) >= 0 || it.k.indexOf(w) >= 0) return true;
        if (!has(forgive, w)) return false;
        if (!(it.h.match(tok) || []).some(function (t) { return t.length >= 4 && near(w, t); })) return false;
        slips++;
        return true;
      });
      if (ok) found.push([slips, it]);
    });
    found.sort(function (a, b) { return a[0] - b[0] || b[1].r - a[1].r || a[1].p - b[1].p; });
    return found.map(function (f) { return f[1]; });
  }
  return { fold: fold, near: near, words: words, find: find };
})();
if (typeof module !== "undefined") module.exports = KamkamSearch;

(function () {
  if (typeof document === "undefined") return;   // the nightly check loads only the rules
  var form = document.querySelector("main form.search") || document.querySelector("form.search");
  var input = form && form.querySelector("input");
  var list = document.getElementById("results");
  var status = document.getElementById("status");
  if (!input || !list) return;
  var en = document.documentElement.lang === "en";
  var q = new URLSearchParams(location.search).get("q") || "";
  input.value = q;
  var empty = !q.trim();
  status.textContent = empty ? "" : (en ? "Searching…" : "جارٍ البحث…");

  function show(items, total) {
    list.textContent = "";
    var g = document.getElementById("sgroups");
    if (g) g.hidden = true;
    list.hidden = false;
    items.forEach(function (it) { list.appendChild(cardOf(it)); });
    status.textContent = total ? (en ? total + " results" : total + " نتيجة") : (en ? "No results. Try another name." : "لا توجد نتائج. جرّب اسماً آخر.");
  }

  // Results of several kinds: one group per kind ("Phones (48)"), its first 6 cards and "See all" for the rest.
  function showGrouped(hits, cats, cfg, pick) {
    var g = document.getElementById("sgroups");
    if (!g) { g = document.createElement("div"); g.id = "sgroups"; list.parentNode.insertBefore(g, list); }
    g.textContent = ""; g.hidden = false; list.hidden = true;
    cats.forEach(function (c) {
      var mine = hits.filter(function (it) { return it.c === c; });
      var head = document.createElement("div"); head.className = "ghead";
      var h = document.createElement("h2"); h.textContent = (en ? cfg.categories[c].en : cfg.categories[c].ar) + " (" + mine.length + ")";
      head.appendChild(h);
      if (mine.length > 6) {
        var b = document.createElement("button"); b.type = "button"; b.className = "flink";
        b.textContent = en ? "See all ›" : "عرض الكل ›";
        b.addEventListener("click", function () { pick(c); window.scrollTo(0, 0); });
        head.appendChild(b);
      }
      var ul = document.createElement("ul"); ul.className = "list";
      mine.slice(0, 6).forEach(function (it) { ul.appendChild(cardOf(it)); });
      g.appendChild(head); g.appendChild(ul);
    });
    status.textContent = en ? hits.length + " results" : hits.length + " نتيجة";
  }

  function cardOf(it) {
    {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = (en ? "/en" : "") + "/p/" + it.u;
      if (it.i) {
        var im = document.createElement("img"); im.className = "thumb"; im.src = it.i; im.alt = ""; im.width = 96; im.height = 96;
        im.loading = "lazy"; im.decoding = "async"; im.referrerPolicy = "no-referrer";
        a.appendChild(im);
      } else { var ph = document.createElement("span"); ph.className = "thumb none"; a.appendChild(ph); }
      var n = document.createElement("span"); n.className = "name"; n.textContent = it.n;
      var t = document.createElement("span"); t.className = "tag";
      t.textContent = (en ? "From " : "من ") + it.p.toLocaleString("en", { maximumFractionDigits: 2 }) + (en ? " JOD" : " د.أ");
      var m = document.createElement("span"); m.className = "mute";
      m.textContent = it.s === 1 ? (en ? "1 shop" : "متجر واحد") : (en ? it.s + " shops" : it.s + " متاجر");
      a.appendChild(n); a.appendChild(t); a.appendChild(m); li.appendChild(a);
      return li;
    }
  }

  // Smart filters over the results (filters.js): one row of kinds when the results mix them ("Phones", "TVs"),
  // then the chosen kind's own quick choices ("55 inch", "Under 150 JOD") and sorting.
  function smart(hits) {
    var F = window.DerbaniFilters, box = document.getElementById("sflt");
    if (!F || !box || !hits.length) return;
    F.loadConfig().then(function (cfg) {
      if (!cfg) return;
      var counts = {};
      hits.forEach(function (it) { counts[it.c] = (counts[it.c] || 0) + 1; });
      var cats = Object.keys(counts).filter(function (c) { return cfg.categories[c]; }).sort(function (a, b) { return counts[b] - counts[a]; });
      var kinds = document.getElementById("skinds"), inner = document.createElement("div");
      box.textContent = "";
      box.appendChild(inner);
      function pick(cat) {
        if (kinds) {
          Array.prototype.forEach.call(kinds.querySelectorAll("button"), function (b) { b.setAttribute("aria-pressed", b.value === (cat || "") ? "true" : "false"); });
        }
        if (!cat) { inner.textContent = ""; box.hidden = true; if (cats.length > 1) showGrouped(hits, cats, cfg, pick); else show(hits, hits.length); return; }
        var mine = hits.filter(function (it) { return it.c === cat; });
        new F.Bar({box: inner, cat: cat, items: mine, groups: false, render: function (shown) { show(shown, shown.length); }});
        box.hidden = false;
      }
      if (kinds && cats.length > 1) {
        kinds.textContent = "";
        [""].concat(cats).forEach(function (c) {
          var b = document.createElement("button");
          b.type = "button"; b.className = "fchip"; b.value = c;
          b.textContent = c ? (en ? cfg.categories[c].en : cfg.categories[c].ar) : F.T.all;
          var n = document.createElement("small"); n.textContent = String(c ? counts[c] : hits.length); b.appendChild(n);
          b.addEventListener("click", function () { pick(c); });
          kinds.appendChild(b);
        });
        kinds.hidden = false;
        pick("");
      } else {
        pick(cats[0]);
      }
    });
  }

  // A search that found nothing is sent to us, the words only, so the missing word or product gets fixed. Phone numbers,
  // emails, links and long numbers never leave the page (the server checks again: worker/misses.js).
  var RECORD_MISSES = false;   // off until the privacy page says it
  function missed(text) {
    if (!RECORD_MISSES || !navigator.sendBeacon || text.length > 60 || /@|:\/\/|www\./.test(text)) return;
    if (/[\d٠-٩۰-۹](?:[^\p{L}]*[\d٠-٩۰-۹]){6,}/u.test(text)) return;
    try {
      if (sessionStorage.getItem("miss:" + text)) return;   // once per visit (a reload is not a second wish)
      sessionStorage.setItem("miss:" + text, "1");
    } catch (e) {}
    try { navigator.sendBeacon("/search-miss?s=site", text); } catch (e) {}
  }

  function load() { return fetch("/search-index.json").then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  load().catch(function () { return new Promise(function (ok) { setTimeout(ok, 1500); }).then(load); }).then(function (ix) {
    if (empty) {   // before anything is typed: every product, most compared first
      var mixed = ix.items.slice().sort(function (a, b) { return b.r - a.r || a.p - b.p; });
      show(mixed, mixed.length);
      status.textContent = en ? "Every product, most compared first. Type a name to search." : "كل المنتجات، الأكثر مقارنة أولاً. اكتب اسم الجهاز للبحث.";
      smart(mixed);
      return;
    }
    var hits = KamkamSearch.find(q, ix);
    show(hits, hits.length);
    smart(hits);
    if (!hits.length) missed(q);
  }).catch(function () {
    status.textContent = en ? "Search is not available right now." : "البحث غير متاح الآن.";
  });
})();
