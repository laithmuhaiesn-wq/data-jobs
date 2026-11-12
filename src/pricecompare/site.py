"""Static read-only pilot page: data embedded as JSON, search done in the browser. No images."""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from .views import build_variant_data

PAGE = """<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jordan phone prices (pilot)</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#ddd;--ok:#0a7a3d;--warn:#b45309}
@media(prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--mut:#999;--line:#333;--ok:#4ade80;--warn:#fbbf24}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.4 system-ui,sans-serif}
main{max-width:760px;margin:0 auto;padding:16px}
input{width:100%;box-sizing:border-box;padding:12px;font-size:16px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg)}
.card{border:1px solid var(--line);border-radius:8px;padding:12px;margin:12px 0}
.card h2{font-size:17px;margin:0 0 6px}.tag{font-size:12px;color:var(--warn)}
.row{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-top:1px solid var(--line)}
.best{color:var(--ok);font-weight:600}.stale,.out{color:var(--mut);text-decoration:line-through}
.mut{color:var(--mut);font-size:13px}a{color:inherit}
</style></head><body><main>
<h1>Jordan phone prices <span class="mut">(private pilot)</span></h1>
<p class="mut">New phones only. Prices are copied from each shop's public page and may be out of date: check the shop before buying. Generated __GENERATED__.</p>
<input id="q" placeholder="Search a phone, e.g. iphone 17 pro 256" autofocus>
<div id="out"></div>
<p class="mut"><a href="remove-my-shop.html">Shop owner? Ask us to remove your shop.</a></p>
<script>
const DATA=__DATA__;
const out=document.getElementById('out'),q=document.getElementById('q');
function esc(s){return s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function render(){
  const t=q.value.toLowerCase().split(/\\s+/).filter(Boolean);
  const list=DATA.filter(v=>t.every(w=>v.label.toLowerCase().includes(w))).slice(0,40);
  out.innerHTML=list.map(v=>{
    const best=Math.min(...v.offers.filter(o=>o.rank).map(o=>o.price),Infinity);
    return '<div class="card"><h2>'+esc(v.label)+'</h2>'+(v.gray?'<div class="tag">Not the official Jordan version ('+esc(v.market)+')</div>':'')+
    v.offers.map(o=>'<div class="row"><span>'+esc(o.store)+(o.stale?' <span class="mut">(old)</span>':'')+(o.stock?'':' <span class="mut">(out of stock)</span>')+'</span>'+
    '<span class="'+(o.rank&&o.price===best?'best':(o.rank?'':'stale'))+'"><a href="'+esc(o.url)+'" rel="noopener nofollow">'+o.price.toFixed(2)+' JOD</a></span></div>').join('')+'</div>';
  }).join('')||'<p class="mut">No results.</p>';
}
q.addEventListener('input',render);render();
</script></main></body></html>"""

REMOVE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Remove my shop</title></head><body style="font:16px/1.5 system-ui;max-width:640px;margin:16px auto;padding:0 16px">
<h1>Remove my shop</h1>
<p>If you own a shop listed here and want it removed or a price corrected, tell us and we will stop collecting from it and
delete its offers.</p>
<p><b>Contact: to be set before any public launch.</b></p>
<p><a href="index.html">Back</a></p></body></html>"""


def build(s: Session, out_dir: Path, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    data = build_variant_data(s, now)
    out_dir.mkdir(parents=True, exist_ok=True)
    page = PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    page = page.replace("__GENERATED__", html.escape(now.strftime("%Y-%m-%d %H:%M UTC")))
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    (out_dir / "remove-my-shop.html").write_text(REMOVE, encoding="utf-8")
    return len(data)
