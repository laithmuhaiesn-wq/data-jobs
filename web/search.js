// Derbani site search. Reads /search-index.json (built every hour with the pages) and lists matching products.
// The folding rules (Arabic letters, digits, Arabic brand names) come from the same index, so they match the app's search.
(function () {
  var form = document.querySelector("main form.search") || document.querySelector("form.search");
  var input = form && form.querySelector("input");
  var list = document.getElementById("results");
  var status = document.getElementById("status");
  if (!input || !list) return;
  var en = document.documentElement.lang === "en";
  var q = new URLSearchParams(location.search).get("q") || "";
  input.value = q;
  if (!q.trim()) return;
  status.textContent = en ? "Searching…" : "جارٍ البحث…";

  function fold(s, letters) {
    s = s.normalize("NFKC").toLowerCase().replace(/[ً-ٰٟ]/g, "");
    s = s.replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 0x660); })
         .replace(/[۰-۹]/g, function (d) { return String(d.charCodeAt(0) - 0x6F0); });
    var out = "";
    for (var i = 0; i < s.length; i++) {
      var c = s[i];
      out += Object.prototype.hasOwnProperty.call(letters, c) ? letters[c] : c;
    }
    return out;
  }

  function words(text, ix) {
    var s = " " + fold(text, ix.letters) + " ";
    Object.keys(ix.phrases).sort(function (a, b) { return b.length - a.length; }).forEach(function (p) {
      s = s.split(" " + p + " ").join(" " + ix.phrases[p] + " ");
    });
    var out = [];
    (s.match(/[؀-ۿ]+|[a-z0-9]+/g) || []).forEach(function (w) {
      if (/[؀-ۿ]/.test(w)) {
        var hit = ix.words[w];
        if (!hit) {
          ["وال", "بال", "لل", "ال", "و", "ب", "ل"].some(function (a) {
            if (w.indexOf(a) === 0 && ix.words[w.slice(a.length)]) { hit = ix.words[w.slice(a.length)]; return true; }
            return false;
          });
        }
        if (hit) out = out.concat(hit.split(" "));
        else if (ix.stop.indexOf(w) < 0) out.push(w);
      } else if (ix.stop.indexOf(w) < 0) {
        out.push(w);
      }
    });
    return out;
  }

  function show(items, total) {
    list.textContent = "";
    items.forEach(function (it) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = (en ? "/en" : "") + "/p/" + it.u;
      var n = document.createElement("span"); n.className = "name"; n.textContent = it.n;
      var t = document.createElement("span"); t.className = "tag";
      t.textContent = (en ? "From " : "من ") + it.p.toLocaleString("en", { maximumFractionDigits: 2 }) + (en ? " JOD" : " د.أ");
      var m = document.createElement("span"); m.className = "mute";
      m.textContent = it.s === 1 ? (en ? "1 shop" : "متجر واحد") : (en ? it.s + " shops" : it.s + " متاجر");
      a.appendChild(n); a.appendChild(t); a.appendChild(m); li.appendChild(a); list.appendChild(li);
    });
    status.textContent = total ? (en ? total + " results" : total + " نتيجة") : (en ? "No results. Try another name." : "لا توجد نتائج. جرّب اسماً آخر.");
  }

  fetch("/search-index.json").then(function (r) { return r.json(); }).then(function (ix) {
    var want = words(q, ix);
    var hits = ix.items.filter(function (it) {
      return want.length && want.every(function (w) { return it.h.indexOf(w) >= 0 || it.k.indexOf(w) >= 0; });
    });
    hits.sort(function (a, b) { return b.r - a.r || a.p - b.p; });
    show(hits.slice(0, 80), hits.length);
  }).catch(function () {
    status.textContent = en ? "Search is not available right now." : "البحث غير متاح الآن.";
  });
})();
