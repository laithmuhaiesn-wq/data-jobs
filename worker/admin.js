// derbani.com/admin: the owner's private dashboard.
//
// Two locks: Cloudflare Access sits in front of /admin (login with a one-time code sent to the owner's email, only
// the owner's address is allowed), and this code checks Access's signed login token itself before answering, so
// /admin stays closed even if the Access rule were ever removed by mistake.
// Data: "Go to shop" clicks and the hourly data-health numbers, both from the D1 database `derbani-clicks`.

const TEAM = 'https://derbani.cloudflareaccess.com';
const AUD = '1131dc7ce2bb66b7539916285fb298971fc6cc683574a925b63832e58de67ead';

let certs = null;
let certsAt = 0;

const b64url = (s) => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(s.length / 4) * 4, '=')), (c) => c.charCodeAt(0));
const json64 = (s) => JSON.parse(new TextDecoder().decode(b64url(s)));

function cookie(request, name) {
  const m = (request.headers.get('cookie') || '').match(new RegExp('(?:^|;\\s*)' + name + '=([^;]+)'));
  return m ? m[1] : null;
}

/** The signed-in email when the request carries a valid Access login for this app, else null. */
export async function accessEmail(request, fetchCerts = (u) => fetch(u)) {
  const token = request.headers.get('cf-access-jwt-assertion') || cookie(request, 'CF_Authorization');
  if (!token) return null;
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  try {
    const head = json64(parts[0]);
    const body = json64(parts[1]);
    const aud = Array.isArray(body.aud) ? body.aud : [body.aud];
    if (head.alg !== 'RS256' || !aud.includes(AUD) || body.iss !== TEAM || !(body.exp > Date.now() / 1000)) return null;
    if (!certs || Date.now() - certsAt > 3600 * 1000) {
      const r = await fetchCerts(TEAM + '/cdn-cgi/access/certs');
      certs = (await r.json()).keys;
      certsAt = Date.now();
    }
    const jwk = certs.find((k) => k.kid === head.kid);
    if (!jwk) return null;
    const key = await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
    const ok = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, b64url(parts[2]), new TextEncoder().encode(parts[0] + '.' + parts[1]));
    return ok ? body.email || 'signed in' : null;
  } catch (e) {
    return null;
  }
}

const SECURE = {
  'Cache-Control': 'no-store',
  'X-Robots-Tag': 'noindex, nofollow',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'no-referrer',
  'X-Content-Type-Options': 'nosniff',
};

async function all(db, sql, ...args) {
  const r = await db.prepare(sql).bind(...args).all();
  return r.results || [];
}

async function data(env, request) {
  const db = env.CLICKS;
  const day = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
  const out = { today: day(0) };
  let hasClicks = true;
  try {
    await db.prepare('SELECT 1 FROM clicks LIMIT 1').all();
  } catch (e) {
    hasClicks = false;
  }
  const real = 'product > 0'; // product 0 = the first test click
  if (hasClicks) {
    out.totals = await all(db, `SELECT source,
        SUM(CASE WHEN day = ?1 THEN n ELSE 0 END) AS today, SUM(CASE WHEN day >= ?2 THEN n ELSE 0 END) AS d7,
        SUM(CASE WHEN day >= ?3 THEN n ELSE 0 END) AS d30, SUM(n) AS total
      FROM clicks WHERE ${real} GROUP BY source`, day(0), day(6), day(29));
    out.shops = await all(db, `SELECT shop, SUM(CASE WHEN day >= ?1 THEN n ELSE 0 END) AS d7,
        SUM(CASE WHEN day >= ?2 THEN n ELSE 0 END) AS d30, SUM(n) AS total
      FROM clicks WHERE ${real} GROUP BY shop ORDER BY d30 DESC, total DESC`, day(6), day(29));
    out.products = await all(db, `SELECT product, SUM(n) AS n FROM clicks WHERE ${real} AND day >= ?1
      GROUP BY product ORDER BY n DESC LIMIT 25`, day(29));
    out.days = await all(db, `SELECT day, SUM(CASE WHEN source = 'app' THEN n ELSE 0 END) AS app,
        SUM(CASE WHEN source = 'site' THEN n ELSE 0 END) AS site FROM clicks WHERE ${real} AND day >= ?1
      GROUP BY day ORDER BY day`, day(29));
    out.since = ((await all(db, `SELECT MIN(day) AS d FROM clicks WHERE ${real}`))[0] || {}).d || null;
  }
  try {
    const h = await all(db, "SELECT json FROM stats WHERE key = 'health'");
    out.health = h.length ? JSON.parse(h[0].json) : null;
    out.trend = (await all(db, "SELECT key, json FROM stats WHERE key >= ?1 AND key LIKE 'day:%' ORDER BY key", 'day:' + day(29)))
      .map((r) => ({ day: r.key.slice(4), ...JSON.parse(r.json) }));
  } catch (e) {
    out.health = null;
    out.trend = [];
  }
  // product names from the public search index (built hourly with the site)
  try {
    const r = await env.ASSETS.fetch(new Request(new URL('/search-index.json', request.url)));
    const items = (await r.json()).items || [];
    const names = {};
    for (const it of items) names[parseInt(it.u, 10)] = it.n;
    for (const p of out.products || []) p.name = names[p.product] || '#' + p.product;
  } catch (e) {}
  return out;
}

export async function admin(request, env) {
  const url = new URL(request.url);
  const email = await accessEmail(request);
  if (!email) {
    return new Response('Not signed in. Open https://derbani.com/admin to sign in.', { status: 403, headers: SECURE });
  }
  if (url.pathname === '/admin/data.json') {
    return new Response(JSON.stringify({ email, ...(await data(env, request)) }), {
      headers: { ...SECURE, 'Content-Type': 'application/json; charset=utf-8' },
    });
  }
  if (url.pathname === '/admin/app.js') {
    return new Response(APP_JS, { headers: { ...SECURE, 'Content-Type': 'text/javascript; charset=utf-8' } });
  }
  if (url.pathname !== '/admin' && url.pathname !== '/admin/') return new Response('Not found', { status: 404, headers: SECURE });
  return new Response(PAGE, {
    headers: {
      ...SECURE,
      'Content-Type': 'text/html; charset=utf-8',
      'Content-Security-Policy': "default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    },
  });
}

const PAGE = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Derbani admin</title>
<style>
:root{--ink:#141414;--paper:#f4f2ec;--surface:#fff;--mute:#6b6b6b;--green:#1f7a3d;--red:#c8102e;--warn:#9a5b00;--line:#d9d6cc}
@media (prefers-color-scheme:dark){:root{--ink:#f1efe8;--paper:#121212;--surface:#1c1c1c;--mute:#a3a3a3;--line:#333}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.stripe{height:6px;background:linear-gradient(90deg,#000 0 33%,#fff 33% 66%,var(--green) 66%)}
main{max-width:1100px;margin:0 auto;padding:16px}
header{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}
h1{margin:8px 0;font-size:26px}h2{margin:28px 0 10px;font-size:18px;border-inline-start:6px solid var(--red);padding-inline-start:8px}
.mute{color:var(--mute);font-size:13px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.tile{background:var(--surface);border:1.5px solid var(--ink);padding:10px 12px}.tile b{display:block;font-size:26px}
.scroll{overflow-x:auto;background:var(--surface);border:1.5px solid var(--ink)}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:start;white-space:nowrap}
th{font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.04em}td.n,th.n{text-align:end;font-variant-numeric:tabular-nums}
.ok{color:var(--green);font-weight:700}.bad{color:var(--red);font-weight:700}.warn{color:var(--warn);font-weight:700}
.chart{background:var(--surface);border:1.5px solid var(--ink);padding:10px}svg{display:block;width:100%;height:160px}
.legend{font-size:12px;color:var(--mute)}.legend i{display:inline-block;width:10px;height:10px;margin:0 4px 0 10px}
.note{background:var(--surface);border-inline-start:5px solid var(--warn);padding:8px 12px;margin:10px 0}
</style></head>
<body><div class="stripe"></div><main>
<header><h1>Derbani admin</h1><span class="mute" id="who"></span></header>
<div id="root"><p class="mute">Loading…</p></div>
</main><script src="/admin/app.js"></script></body></html>`;

const APP_JS = `
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (n) => (n || 0).toLocaleString('en');
const ago = (iso) => { if (!iso) return '—'; const m = Math.round((Date.now() - new Date(iso)) / 60000);
  return m < 60 ? m + ' min ago' : m < 2880 ? Math.round(m / 60) + ' h ago' : Math.round(m / 1440) + ' days ago'; };
const table = (head, rows) => '<div class="scroll"><table><thead><tr>' + head.map(([h, c]) => '<th class="' + (c || '') + '">' + h + '</th>').join('')
  + '</tr></thead><tbody>' + (rows.length ? rows.join('') : '<tr><td colspan="' + head.length + '" class="mute">Nothing yet</td></tr>') + '</tbody></table></div>';

function bars(days, keys, colors) {
  if (!days.length) return '<p class="mute">Nothing yet</p>';
  const max = Math.max(1, ...days.map((d) => keys.reduce((s, k) => s + (d[k] || 0), 0)));
  const w = 1000 / days.length;
  let svg = '';
  days.forEach((d, i) => { let y = 150; keys.forEach((k, j) => { const h = 140 * (d[k] || 0) / max;
    y -= h; svg += '<rect x="' + (i * w + 2) + '" y="' + y + '" width="' + Math.max(1, w - 4) + '" height="' + h + '" fill="' + colors[j] + '"><title>' + esc(d.day) + ' ' + k + ': ' + (d[k] || 0) + '</title></rect>'; }); });
  return '<div class="chart"><svg viewBox="0 0 1000 155" preserveAspectRatio="none">' + svg + '</svg><div class="legend">'
    + keys.map((k, j) => '<i style="background:' + colors[j] + '"></i>' + k).join('') + ' · max ' + max + ' a day · ' + esc(days[0].day) + ' to ' + esc(days[days.length - 1].day) + '</div></div>';
}

function render(d) {
  document.getElementById('who').textContent = 'Signed in as ' + d.email;
  const t = { app: {}, site: {} }; (d.totals || []).forEach((r) => (t[r.source] = r));
  const sum = (k) => (t.app[k] || 0) + (t.site[k] || 0);
  const h = d.health;
  let html = '<h2>Go to shop clicks</h2>';
  html += d.since ? '<p class="mute">Counting since ' + esc(d.since) + '. Bots are not counted; nothing personal is stored.</p>'
    : '<p class="mute">No real clicks yet. Every "Go to shop" tap on the site or in the app is counted from 12 November 2026.</p>';
  html += '<div class="tiles">' + [['Today', 'today'], ['Last 7 days', 'd7'], ['Last 30 days', 'd30'], ['All time', 'total']]
    .map(([l, k]) => '<div class="tile"><span class="mute">' + l + '</span><b>' + num(sum(k)) + '</b><span class="mute">app ' + num(t.app[k]) + ' · site ' + num(t.site[k]) + '</span></div>').join('') + '</div>';
  html += '<h2>Clicks per day (30 days)</h2>' + bars(d.days || [], ['app', 'site'], ['#c8102e', '#1f7a3d']);
  html += '<h2>Clicks by shop</h2>' + table([['Shop'], ['7 days', 'n'], ['30 days', 'n'], ['All time', 'n']],
    (d.shops || []).map((s) => '<tr><td>' + esc(s.shop) + '</td><td class="n">' + num(s.d7) + '</td><td class="n">' + num(s.d30) + '</td><td class="n">' + num(s.total) + '</td></tr>'));
  html += '<h2>Most clicked products (30 days)</h2>' + table([['Product'], ['Clicks', 'n']],
    (d.products || []).map((p) => '<tr><td>' + esc(p.name) + '</td><td class="n">' + num(p.n) + '</td></tr>'));
  html += '<h2>Data health</h2>';
  if (!h) { html += '<p class="note">No data-health numbers yet. They arrive with the next hourly run.</p>'; }
  else {
    const fresh = h.fresh_48h_pct >= 90 ? 'ok' : 'warn';
    html += '<p class="mute">Updated ' + ago(h.at) + '.</p><div class="tiles">'
      + [['Products', num(h.products)], ['At 2+ shops', num(h.at_2plus)], ['At 3+ shops', num(h.at_3plus)], ['Shop listings', num(h.offers)],
         ['Matched', h.matched_pct + '%'], ['Fresh (48 h)', '<span class="' + fresh + '">' + h.fresh_48h_pct + '%</span>'],
         ['Waiting to match', num(h.review_queue)], ['Odd prices held back', num(h.suspicious_prices)]]
      .map(([l, v]) => '<div class="tile"><span class="mute">' + l + '</span><b>' + v + '</b></div>').join('') + '</div>';
    html += '<h2>Shops</h2>' + table([['Shop'], ['Last run'], ['Result'], ['Runs OK (7 days)', 'n'], ['Listings', 'n'], ['Matched', 'n']],
      h.shops.map((s) => { const cls = !s.enabled ? 'warn' : s.last_status === 'ok' ? 'ok' : 'bad';
        const res = !s.enabled ? 'switched off' : s.last_status === 'ok' ? 'OK' : esc(s.last_status || '—') + (s.last_error ? ': ' + esc(s.last_error) : '');
        const rate = s.runs_7d ? Math.round(100 * s.ok_7d / s.runs_7d) : 0;
        return '<tr><td>' + esc(s.shop) + '</td><td>' + ago(s.last_run) + '</td><td class="' + cls + '">' + res + '</td><td class="n ' + (rate >= 90 ? 'ok' : 'warn') + '">'
          + s.ok_7d + '/' + s.runs_7d + '</td><td class="n">' + num(s.offers) + '</td><td class="n">' + num(s.matched) + '</td></tr>'; }));
    html += '<h2>Catalog growth (30 days)</h2>' + bars(d.trend || [], ['products'], ['#141414']);
    html += '<h2>New products added by themselves (14 days)</h2>' + table([['Product'], ['How'], ['When']],
      (h.catalog_added_14d || []).map((a) => '<tr><td>' + esc(a.name) + '</td><td>' + esc(a.way) + '</td><td>' + ago(a.at) + '</td></tr>'));
  }
  html += '<h2>Elsewhere</h2><p class="mute">Google Search Console and Bing Webmaster Tools show how people find derbani.com in search. '
    + 'Google Play Console will show app installs after the release.</p>';
  document.getElementById('root').innerHTML = html;
}

fetch('/admin/data.json', { credentials: 'same-origin' }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then(render).catch((e) => { document.getElementById('root').innerHTML = '<p class="note">Could not load the numbers (' + esc(e.message) + '). Reload to sign in again.</p>'; });
`;
