// Derbani site search. Reads /search-index.json (built every hour with the pages) and lists matching products.
// The folding rules (Arabic letters, digits, Arabic brand names) come from the same index, so they match the app's search.
// The search rules, the same as search.py (the API) and local_search.dart (the app): the nightly search check compares them.
var KamkamSearch = (function () {
  var AR = "؀-ۿ", cut = new RegExp("[" + AR + "]+|[a-z0-9]+", "g"), tok = new RegExp("[a-z0-9" + AR + "]+", "g");
  var arabic = new RegExp("^[" + AR + "]"), letters = /^\p{L}+$/u;
  // in stock first, then most compared, then cheapest; a product out of stock (p null) is still found (2026-11-26:
  // "Powerology PP068" found nothing on the site while its page was there)
  function cheaper(a, b) { return (a.p == null) - (b.p == null) || b.r - a.r || (a.p || 0) - (b.p || 0); }

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
    var alone = ix.alone || {};   // "ram" typed alone lists the RAM sticks; in "iphone 8gb ram" it is only a skipped word
    if (!words(text, ix).length) for (i = 0; i < ws.length; i++) {
      if (has(alone, ws[i])) return alone[ws[i]];
      if (ws[i].indexOf("ال") === 0 && has(alone, ws[i].slice(2))) return alone[ws[i].slice(2)];
    }
    return null;
  }

  // The matching products, best first: exact before forgiven slips, then most compared, then cheapest.
  function find(text, ix) { return scored(text, ix).map(function (f) { return f[1]; }); }

  // [slips, item] pairs, fewest slips first (the API worker orders each group its own way)
  function scored(text, ix) {
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
    found.sort(function (a, b) { return a[0] - b[0] || cheaper(a[1], b[1]); });
    return found;
  }
  // How many slips apart two words are (2 at most counts; swapped neighbours are one slip).
  function slips(a, b) {
    if (Math.abs(a.length - b.length) > 2) return 9;
    var d = [], i, j;
    for (i = 0; i <= a.length; i++) { d[i] = [i]; for (j = 1; j <= b.length; j++) d[i][j] = i ? 0 : j; }
    for (i = 1; i <= a.length; i++) for (j = 1; j <= b.length; j++) {
      var same = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + same);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
    return d[a.length][b.length];
  }

  // For a search that found nothing: {text: "did you mean" or null, items: similar products}. One word is changed to the
  // closest word of the products that have all the other words; with none close, one word is left out for the similar ones.
  function suggest(text, ix) {
    var want = words(text, ix), cat = kind(text, ix), best = null, drop = null, first = null;
    // a word no product has, one slip from a real one ("galxay"), is put right first
    want.forEach(function (w, n) {
      if (first || (ix.known || []).indexOf(w) >= 0 || w.length < 4 || !letters.test(w) || ix.items.some(function (it) { return it.h.indexOf(w) >= 0 || it.k.indexOf(w) >= 0; })) return;
      var top = null, to = null;
      ix.items.forEach(function (it) {
        (it.h.match(tok) || []).forEach(function (t) { if (t.length >= 4 && t !== "samaah" && near(w, t) && (!top || better(it, top) < 0)) { top = it; to = t; } });
      });
      if (to) first = { n: n, t: to };
    });
    if (first) {
      var fixedText = want.map(function (x, k) { return k === first.n ? first.t : x; }).filter(function (x) { return x !== "samaah"; }).join(" "), hits = find(fixedText, ix);
      return hits.length ? { text: fixedText, items: hits.slice(0, 6) } : suggest(fixedText, ix);
    }
    function better(a, b) { return cheaper(a, b); }
    want.forEach(function (w, n) {
      var rest = want.filter(function (x, k) { return k !== n; });
      var mine = ix.items.filter(function (it) {
        return (!cat || it.c === cat) && rest.every(function (x) { return it.h.indexOf(x) >= 0 || it.k.indexOf(x) >= 0; });
      }).sort(better);
      if (!mine.length) return;
      var plain = letters.test(w), limit = plain && w.length >= 6 ? 2 : 1;
      if (w.length >= 2) mine.forEach(function (it) {
        (it.h.match(tok) || []).forEach(function (t) {
          if (t === w || t === "samaah" || t.length < 2 || letters.test(t) !== plain || (plain && t.length < 4) || Math.abs(t.length - w.length) > limit) return;
          if (!plain && (t.length !== w.length || t.split('').sort().join('') !== w.split('').sort().join(''))) return;   // numbers: only two swapped digits
          var d = slips(w, t);
          if (d <= limit && (!best || d < best.d || (d === best.d && better(it, best.it) < 0))) best = { d: d, it: it, n: n, t: t };
        });
      });
      if (!arabic.test(w) && rest.some(function (x) { return x.length >= 3 && /\p{L}/u.test(x); }) && (!drop || mine.length < drop.length)) drop = mine;
    });
    if (best) {
      // the visitor's own writing with that one word changed ("ايفون 71" -> "ايفون 17"), else the plain words
      var w0 = want[best.n], done = false;
      var typed = text.trim().split(/\s+/).map(function (x) { if (!done && fold(x, ix.letters) === w0) { done = true; return best.t; } return x; }).join(" ");
      if (!done) typed = want.map(function (x, k) { return k === best.n ? best.t : x; }).filter(function (x) { return x !== "samaah"; }).join(" ");
      var got = find(typed, ix);
      if (got.length) return { text: typed, items: got.slice(0, 6) };
    }
    return { text: null, items: (drop || []).slice(0, 6) };
  }
  return { fold: fold, near: near, words: words, kind: kind, find: find, scored: scored, suggest: suggest };
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
      t.textContent = it.p == null ? (en ? "Out of stock" : "غير متوفر")
        : (en ? "From " : "من ") + it.p.toLocaleString("en", { maximumFractionDigits: 2 }) + (en ? " JOD" : " د.أ");
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

  // Nothing found: "did you mean ...?", similar products, and the app's arrival alert (owner's design A, 2026-11-25).
  function nothing(ix) {
    var sug = KamkamSearch.suggest(q, ix);
    status.textContent = en ? "No results for “" + q + "”" : "لا توجد نتائج لـ «" + q + "»";
    status.className = "nores";
    list.textContent = "";
    if (sug.text) {
      var box = document.createElement("div"), b = document.createElement("b"), a = document.createElement("a"), p = document.createElement("p");
      box.className = "didyou";
      b.textContent = sug.text;
      p.appendChild(document.createTextNode(en ? "Did you mean " : "هل تقصد "));
      p.appendChild(b);
      p.appendChild(document.createTextNode(en ? "?" : "؟"));
      a.className = "btn red"; a.href = location.pathname + "?q=" + encodeURIComponent(sug.text);
      a.textContent = en ? "Show results" : "اعرض النتائج";
      box.appendChild(p); box.appendChild(a);
      list.parentNode.insertBefore(box, list);
    }
    if (sug.items.length) {
      var h = document.createElement("h2"); h.textContent = en ? "Similar products" : "منتجات قريبة";
      list.parentNode.insertBefore(h, list);
      sug.items.forEach(function (it) { list.appendChild(cardOf(it)); });
    }
    var play = list.getAttribute("data-play");
    if (play) {   // the alert itself is in the app
      var n = document.createElement("a"); n.className = "btn"; n.href = play; n.rel = "noopener";
      n.textContent = en ? "Tell me when it arrives (in the app)" : "نبّهني عند وصوله (في التطبيق)";
      list.parentNode.insertBefore(n, list.nextSibling);
    }
  }

  // A search that found nothing is sent to us, the words only, so the missing word or product gets fixed. Phone numbers,
  // emails, links and long numbers never leave the page (the server checks again: worker/misses.js).
  var RECORD_MISSES = true;   // the privacy page says it (2026-11-25)
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
      var mixed = ix.items.filter(function (it) { return it.p != null; }).sort(cheaper);
      show(mixed, mixed.length);
      status.textContent = en ? "Every product, most compared first. Type a name to search." : "كل المنتجات، الأكثر مقارنة أولاً. اكتب اسم الجهاز للبحث.";
      smart(mixed);
      return;
    }
    var hits = KamkamSearch.find(q, ix);
    show(hits, hits.length);
    smart(hits);
    if (!hits.length) { nothing(ix); missed(q); }
  }).catch(function () {
    status.textContent = en ? "Search is not available right now." : "البحث غير متاح الآن.";
  });
})();
