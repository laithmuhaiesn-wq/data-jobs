// derbani.com/admin: the owner's private dashboard.
//
// Two locks: Cloudflare Access sits in front of /admin (login with a one-time code sent to the owner's email, only
// the owner's address is allowed), and this code checks Access's signed login token itself before answering, so
// /admin stays closed even if the Access rule were ever removed by mistake.
// Data: "Go to shop" clicks and the hourly data-health numbers, both from the D1 database `derbani-clicks`.

import { AD_CATS, MAX_LIVE, checkAd, ensure, today } from './ads.js';

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
  // the admin runs on derbani.com, whose own files have no search index: kamkam.derbani.com's is read then (2026-11-23:
  // the product names were empty)
  try {
    let r = env.ASSETS ? await env.ASSETS.fetch(new Request(new URL('/search-index.json', request.url))).catch(() => null) : null;
    if (!r || !r.ok || !(r.headers.get('content-type') || '').includes('json')) r = await fetch('https://kamkam.derbani.com/search-index.json');
    const items = (await r.json()).items || [];
    const names = {};
    for (const it of items) names[parseInt(it.u, 10)] = it.n;
    for (const p of out.products || []) p.name = names[p.product] || '#' + p.product;
  } catch (e) {
    for (const p of out.products || []) p.name = p.name || 'Product #' + p.product;   // never an empty line
  }
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
  // ---- shop ads: list, add, stop (POST only from this same site: a page elsewhere cannot add or stop an ad)
  if (url.pathname.startsWith('/admin/ads')) {
    const db = env.CLICKS;
    const send = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { ...SECURE, 'Content-Type': 'application/json; charset=utf-8' } });
    if (url.pathname === '/admin/ads.js') return new Response(ADS_JS, { headers: { ...SECURE, 'Content-Type': 'text/javascript; charset=utf-8' } });
    if (url.pathname === '/admin/ads' && request.method === 'GET') {
      return new Response(ADS_PAGE, { headers: { ...SECURE, 'Content-Type': 'text/html; charset=utf-8',
        'Content-Security-Policy': "default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'" } });
    }
    if (!db) return send({ error: 'The database is not connected.' }, 500);
    await ensure(db);
    const day = today();
    if (url.pathname === '/admin/ads.json') {
      const r = await db.prepare('SELECT * FROM ads ORDER BY start DESC, id DESC LIMIT 200').all();
      return send({ email, today: day, max: MAX_LIVE, cats: AD_CATS, ads: r.results || [] });
    }
    if (request.method !== 'POST' || request.headers.get('origin') !== url.origin) return send({ error: 'Not allowed.' }, 403);
    if (url.pathname === '/admin/ads/add') {
      let body = {};
      try { body = await request.json(); } catch (e) {}
      const taken = (await db.prepare('SELECT start, end, category FROM ads WHERE stopped = 0 AND end >= ?1').bind(day).all()).results || [];
      const [ad, err] = checkAd(body, taken, day);
      if (err) return send({ error: err }, 400);
      await db.prepare('INSERT INTO ads (shop, text_ar, text_en, url, start, end, created, category) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)')
        .bind(ad.shop, ad.text_ar, ad.text_en, ad.url, ad.start, ad.end, new Date().toISOString(), ad.category).run();
      return send({ ok: true, ad });
    }
    if (url.pathname === '/admin/ads/stop') {
      const id = parseInt(url.searchParams.get('id') || '0', 10);
      await db.prepare('UPDATE ads SET stopped = 1 WHERE id = ?1').bind(id).run();
      return send({ ok: true });
    }
    return send({ error: 'Not found.' }, 404);
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
:root{--ink:#141414;--paper:#f4f2ec;--surface:#fff;--mute:#6b6b6b;--green:#1f7a3d;--red:#c8102e;--warn:#9a5b00;--line:#d9d6cc;--link:#0b5cad;--okbg:#e3f3ea;--warnbg:#fdf1dc;--badbg:#fbe4e7}
@media (prefers-color-scheme:dark){:root{--ink:#f1efe8;--paper:#121212;--surface:#1c1c1c;--mute:#a3a3a3;--line:#333;--link:#7ab8ff;--green:#5cc98a;--warn:#e0a640;--red:#ff6b81;--okbg:#14301f;--warnbg:#33260d;--badbg:#3a1219}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--link)}main{max-width:1100px;margin:0 auto;padding:16px}
header{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}
h1{margin:8px 0;font-size:24px}h2{margin:26px 0 10px;font-size:18px;border-inline-start:6px solid var(--red);padding-inline-start:8px}
.mute{color:var(--mute);font-size:13px}
.status{border-radius:10px;padding:10px 14px;margin:10px 0;font-weight:600}.status.ok{background:var(--okbg);color:var(--green)}
.status.warn{background:var(--warnbg);color:var(--warn)}.status.bad{background:var(--badbg);color:var(--red)}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:14px 0 4px;border-bottom:1.5px solid var(--line)}
.tab{font:inherit;font-weight:600;background:none;border:0;border-bottom:3px solid transparent;color:var(--mute);padding:8px 14px;cursor:pointer;margin-bottom:-1.5px}
.tab[aria-selected=true]{color:var(--ink);border-bottom-color:var(--red)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.tile b{display:block;font-size:24px}
.scroll{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:start;white-space:nowrap}
th{font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.04em}td.n,th.n{text-align:end;font-variant-numeric:tabular-nums}
td.w{white-space:normal}tr:last-child td{border-bottom:0}
.ok{color:var(--green);font-weight:700}.bad{color:var(--red);font-weight:700}.warn{color:var(--warn);font-weight:700}
.chart{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px}svg{display:block;width:100%;height:160px}
.legend{font-size:12px;color:var(--mute)}.legend i{display:inline-block;width:10px;height:10px;margin:0 4px 0 10px}
.note{background:var(--surface);border-inline-start:5px solid var(--warn);border-radius:6px;padding:8px 12px;margin:10px 0}
.tall{max-height:460px;overflow-y:auto;border:1px solid var(--line);border-radius:10px}.tall .scroll{border:0;border-radius:0}.tall thead th{position:sticky;top:0;background:var(--surface)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}.chip{font:inherit;font-size:13px;background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:999px;padding:4px 12px;cursor:pointer}
.chip.on{background:var(--ink);color:var(--paper);border-color:var(--ink)}.chip b{font-weight:700;margin-inline-start:4px}
.pill{display:inline-block;font-size:12px;font-weight:700;padding:1px 8px;border-radius:999px}.pill.ok{background:var(--okbg)}.pill.warn{background:var(--warnbg)}.pill.bad{background:var(--badbg)}
.report{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;white-space:pre-wrap;font-size:13px;max-height:420px;overflow-y:auto}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
</style></head>
<body><main>
<header><h1>Derbani admin</h1><span class="mute"><a href="/admin/ads">Shop ads ›</a> · <span id="who"></span></span></header>
<div id="root"><p class="mute">Loading…</p></div>
</main><script src="/admin/app.js"></script></body></html>`;

const APP_JS = `
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (n) => (n || 0).toLocaleString('en');
const ago = (iso) => { if (!iso) return '—'; const m = Math.round((Date.now() - new Date(iso)) / 60000);
  return m < 1 ? 'just now' : m < 60 ? m + ' min ago' : m < 2880 ? Math.round(m / 60) + ' h ago' : Math.round(m / 1440) + ' days ago'; };
const KIND = { phone: 'Phones', tablet: 'Tablets', laptop: 'Laptops', tv: 'TVs', watch: 'Watches', audio: 'Headphones',
  speaker: 'Speakers', console: 'Consoles', monitor: 'Monitors', printer: 'Printers', desktop: 'Desktops', router: 'Routers',
  powerbank: 'Power banks', storage: 'Storage', camera: 'Cameras', projector: 'Projectors', smarthome: 'Smart home',
  peripheral: 'Keyboards & mice', tabletacc: 'Tablet pens', pcpart: 'PC parts' };
const JOB = { hourly: 'Hourly (shops, matching, site)', nightly: 'Nightly (slow shops, catalog, backup)', electronics: 'Electronics (every 6 h)',
  slow: 'Slow shops', fast: 'Fast shop', watch: 'Watch (every 5 min)' };
const table = (head, rows) => '<div class="scroll"><table><thead><tr>' + head.map(([h, c]) => '<th class="' + (c || '') + '">' + h + '</th>').join('')
  + '</tr></thead><tbody>' + (rows.length ? rows.join('') : '<tr><td colspan="' + head.length + '" class="mute">Nothing yet</td></tr>') + '</tbody></table></div>';
const tiles = (list) => '<div class="tiles">' + list.map(([l, v, sub]) => '<div class="tile"><span class="mute">' + l + '</span><b>' + v + '</b>'
  + (sub ? '<span class="mute">' + sub + '</span>' : '') + '</div>').join('') + '</div>';
const link = (url, text) => '<a href="' + esc(url) + '" rel="noopener noreferrer" target="_blank">' + esc(text) + '</a>';

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

// ---- the line at the top: green when all is well, amber when something waits, red when the API is down or a step failed
function status(h) {
  if (!h || !h.system) return ['warn', 'No status yet: it arrives with the next hourly run.'];
  const sys = h.system, bad = [], warn = [];
  if (!sys.api_local) bad.push('the API on the PC is not answering');
  else if (!sys.api_public) bad.push('the API answers on the PC but not from the internet (tunnel)');
  Object.keys(sys.jobs || {}).forEach((k) => { if (sys.jobs[k].failed) warn.push(k + ' run: ' + sys.jobs[k].failed + ' failed'); });
  const hr = (sys.jobs || {}).hourly;
  if (!hr || (Date.now() - new Date(hr.at)) > 3 * 3600000) bad.push('the hourly run has not finished for over 3 hours (PC off or asleep?)');
  const probs = h.problems || [];
  const broken = probs.filter((p) => p.kind === 'broken').length, waiting = probs.filter((p) => p.kind === 'waiting').length;
  if (broken) warn.push(broken + ' shop' + (broken > 1 ? 's' : '') + ' broken (the daily doctor fixes them)');
  if (bad.length) return ['bad', 'Needs attention: ' + bad.concat(warn).join(' · ')];
  if (warn.length) return ['warn', 'Mostly fine: ' + warn.join(' · ')];
  return ['ok', 'All OK · API up · last hourly run ' + ago(hr.at) + (waiting ? ' · ' + waiting + ' shops paused by their own limits' : '')];
}

function overview(d, h) {
  const t = { app: {}, site: {} }; (d.totals || []).forEach((r) => (t[r.source] = r));
  const tr = (h && h.traffic) || [];
  const today = tr.length ? tr[tr.length - 1].visitors : null;
  let html = '';
  if (h) html += tiles([['Visitors today', today == null ? '—' : num(today)], ['Shop clicks today', num((t.app.today || 0) + (t.site.today || 0))],
    ['Products', num(h.products)], ['Fresh (48 h)', '<span class="' + (h.fresh_48h_pct >= 90 ? 'ok' : 'warn') + '">' + h.fresh_48h_pct + '%</span>'],
    ['Matched', h.matched_pct + '%'], ['Prices down today', num(h.moves ? h.moves.down : 0), h.moves ? num(h.moves.up) + ' went up' : '']]);
  const sys = h && h.system;
  html += '<div class="cols"><div><h2>System</h2>';
  if (!sys) html += '<p class="mute">Arrives with the next hourly run.</p>';
  else {
    html += '<p class="mute">Checked ' + ago(sys.checked) + ' from the PC.</p>' + table([['Part'], ['State']], [
      '<tr><td>API on the PC</td><td class="' + (sys.api_local ? 'ok' : 'bad') + '">' + (sys.api_local ? 'Up' : 'Down') + '</td></tr>',
      '<tr><td>api.derbani.com (tunnel)</td><td class="' + (sys.api_public ? 'ok' : 'bad') + '">' + (sys.api_public ? 'Up' : 'Down') + '</td></tr>'])
      + '<h2>Jobs</h2>' + table([['Job'], ['Last finished'], ['Took', 'n'], ['Result']], Object.keys(JOB).filter((k) => sys.jobs[k]).map((k) => {
        const j = sys.jobs[k];
        return '<tr><td>' + JOB[k] + '</td><td>' + ago(j.at) + '</td><td class="n">' + Math.round(j.secs / 60) + ' min</td><td class="'
          + (j.failed ? 'warn">Failed: ' + esc(j.failed) : 'ok">OK') + '</td></tr>'; }));
  }
  html += '</div><div><h2>Shop problems</h2>';
  const probs = (h && h.problems) || [];
  const KINDP = { broken: ['bad', 'Broken: the shop changed its site'], waiting: ['warn', 'Paused by the shop (we wait, never get around it)'], stale: ['warn', 'Not read lately'] };
  html += probs.length ? table([['Shop'], ['What'], ['Read 24 h', 'n']], probs.map((p) => '<tr><td>' + esc(p.name || p.shop) + '</td><td class="w"><span class="pill '
      + (KINDP[p.kind] || ['warn'])[0] + '">' + (KINDP[p.kind] || ['', p.kind])[1] + '</span><br><span class="mute">'
      + (p.kind !== 'waiting' ? esc(p.detail) : /429/.test(p.detail) ? 'Said "too many requests": resting, then one page every 3 hours'
        : /Challenge|bot check/i.test(p.detail) ? 'Bot check: tried again every few days' : 'Asked us to stop for now') + '</span></td><td class="n">'
      + (p.fresh_24h == null ? '—' : Math.round(100 * p.fresh_24h) + '%') + '</td></tr>'))
    : '<p class="ok">No shop problems.</p>';
  html += '</div></div><h2>Daily doctor (9:30 every morning)</h2>';
  html += h && h.doctor ? '<p class="mute">Report of ' + esc(h.doctor.day) + '. The doctor fixes broken shops and reader gaps by itself, with tests.</p><div class="report">' + esc(h.doctor.text) + '</div>'
    : '<p class="mute">No report yet.</p>';
  return html;
}

function money(d, h) {
  const t = { app: {}, site: {} }; (d.totals || []).forEach((r) => (t[r.source] = r));
  const sum = (k) => (t.app[k] || 0) + (t.site[k] || 0);
  let html = '<h2>Website visitors</h2>';
  const tr = (h && h.traffic) || [];
  if (!tr.length) {
    html += '<p class="note">' + (h && h.traffic_error ? 'Traffic could not be read: ' + esc(h.traffic_error) : 'Traffic numbers arrive with the next hourly run.') + '</p>';
  } else {
    const last = (n, k) => tr.slice(-n).reduce((s, x) => s + (x[k] || 0), 0);
    const cc = {}; tr.slice(-7).forEach((x) => (x.countries || []).forEach(([c, n]) => (cc[c] = (cc[c] || 0) + n)));
    const top = Object.entries(cc).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([c, n]) => esc(c) + ' ' + num(n)).join(' · ');
    html += '<p class="mute">From Cloudflare. Visitors = different internet addresses per day; page views include some search-engine bots. App use is not tracked.</p>'
      + tiles([['Visitors today', num(last(1, 'visitors'))], ['Visitors (7 days)', num(last(7, 'visitors'))], ['Page views today', num(last(1, 'views'))],
        ['Page views (7 days)', num(last(7, 'views'))], ['Page views (30 days)', num(last(30, 'views'))]])
      + '<p class="mute">Top countries this week (requests): ' + (top || '—') + '</p>'
      + bars(tr.map((x) => ({ day: x.day, visitors: x.visitors })), ['visitors'], ['#1f7a3d']);
  }
  html += '<h2>Go to shop clicks</h2>' + (d.since ? '<p class="mute">Counting since ' + esc(d.since) + '. Bots are not counted; nothing personal is stored.</p>'
    : '<p class="mute">No real clicks yet.</p>')
    + tiles([['Today', 'today'], ['Last 7 days', 'd7'], ['Last 30 days', 'd30'], ['All time', 'total']].map(([l, k]) => [l, num(sum(k)), 'app ' + num(t.app[k]) + ' · site ' + num(t.site[k])]));
  html += '<h2>Clicks per day (30 days)</h2>' + bars(d.days || [], ['app', 'site'], ['#c8102e', '#1f7a3d']);
  html += '<div class="cols"><div><h2>Clicks by shop</h2>' + table([['Shop'], ['7 days', 'n'], ['30 days', 'n'], ['All time', 'n']],
    (d.shops || []).map((s) => '<tr><td>' + esc(s.shop) + '</td><td class="n">' + num(s.d7) + '</td><td class="n">' + num(s.d30) + '</td><td class="n">' + num(s.total) + '</td></tr>'))
    + '</div><div><h2>Most clicked products (30 days)</h2>' + table([['Product'], ['Clicks', 'n']],
    (d.products || []).map((p) => '<tr><td class="w">' + esc(p.name) + '</td><td class="n">' + num(p.n) + '</td></tr>')) + '</div></div>';
  const ch = (h && h.cheapest) || [];
  html += '<h2>Which shop is cheapest most often</h2><p class="mute">Products sold by 2 or more shops (in stock, read in the last 48 h). '
    + '"Cheapest" = how many of them this shop has the lowest price on. Useful when you talk to shops.</p>'
    + '<div class="tall">' + table([['Shop'], ['Cheapest on', 'n'], ['Of', 'n'], ['Share', 'n'], ['Mostly in']], ch.map((x) => {
      const kinds = Object.entries(x.kinds || {}).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, n]) => esc(KIND[k] || k) + ' ' + n).join(' · ');
      return '<tr><td>' + esc(x.shop) + '</td><td class="n">' + num(x.cheapest) + '</td><td class="n">' + num(x.sells) + '</td><td class="n">' + x.pct + '%</td><td class="w mute">' + kinds + '</td></tr>'; })) + '</div>';
  return html;
}

function data(d, h) {
  if (!h) return '<p class="note">No data-health numbers yet. They arrive with the next hourly run.</p>';
  let html = '<p class="mute">Updated ' + ago(h.at) + '.</p>' + tiles([['Products', num(h.products)], ['At 2+ shops', num(h.at_2plus)], ['At 3+ shops', num(h.at_3plus)],
    ['Shop listings', num(h.offers)], ['Matched', h.matched_pct + '%'], ['Fresh (48 h)', '<span class="' + (h.fresh_48h_pct >= 90 ? 'ok' : 'warn') + '">' + h.fresh_48h_pct + '%</span>'],
    ['Waiting to match', num(h.review_queue)], ['Odd prices held back', num(h.suspicious_prices)], ['Listings held (other product)', num(h.moves ? h.moves.held : 0)]]);
  const mv = h.moves;
  html += '<h2>Price moves (last 24 hours)</h2>';
  html += mv ? tiles([['Went down', '<span class="ok">' + num(mv.down) + '</span>'], ['Went up', '<span class="warn">' + num(mv.up) + '</span>']])
    + '<h2>Biggest drops</h2>' + table([['Product'], ['Shop'], ['Was', 'n'], ['Now', 'n'], ['Down', 'n']], (mv.drops || []).map((x) => '<tr><td class="w">' + esc(x.name)
      + '</td><td>' + link(x.url, x.shop) + '</td><td class="n">' + num(x.was) + '</td><td class="n">' + num(x.now) + '</td><td class="n ok">' + x.pct + '%</td></tr>'))
    : '<p class="mute">Arrives with the next hourly run.</p>';
  html += '<h2>Shops</h2>' + table([['Shop'], ['Last run'], ['Result'], ['Runs OK (7 days)', 'n'], ['Listings', 'n'], ['Matched', 'n']],
    h.shops.map((s) => {
      const paused = s.last_status === 'blocked' || s.last_status === 'limited';
      const cls = !s.enabled ? 'warn' : s.last_status === 'ok' ? 'ok' : paused ? 'warn' : 'bad';
      const res = !s.enabled ? 'Switched off' : s.last_status === 'ok' ? 'OK' : s.last_status === 'blocked' ? 'Paused: bot check'
        : s.last_status === 'limited' ? 'Paused: asked us to slow down' : esc(s.last_status || '—');
      const rate = s.runs_7d ? Math.round(100 * s.ok_7d / s.runs_7d) : 0;
      return '<tr><td>' + esc(s.shop) + '</td><td>' + ago(s.last_run) + '</td><td class="' + cls + '">' + res + '</td><td class="n ' + (rate >= 90 ? 'ok' : 'warn') + '">'
        + s.ok_7d + '/' + s.runs_7d + '</td><td class="n">' + num(s.offers) + '</td><td class="n">' + num(s.matched) + '</td></tr>'; }));
  (h.pending || []).forEach((p) => {
    const name = KIND[p.category] || esc(p.category);
    html += '<h2>' + name + ': waiting for your check (hidden from visitors)</h2>'
      + '<p class="note">Collected and matched, not shown yet. Open each link and check the shop sells exactly that product at that price. '
      + 'When everything matches, tell Claude "' + name.toLowerCase() + ' checked". The sample changes every day.</p>'
      + tiles([['Products', num(p.products)], ['Shop listings', num(p.listings)], ['At 2+ shops', num(p.at_2plus)]])
      + '<h2>' + name + ': ' + p.matches.length + ' matches to check</h2>'
      + table([['#'], ['Shop'], ['What the shop calls it'], ['Our product']], p.matches.map((m, i) => '<tr><td>' + (i + 1) + '</td><td>'
        + esc(m.shop) + '</td><td class="w">' + link(m.url, m.title) + '</td><td class="w">' + esc(m.product) + '</td></tr>'))
      + '<h2>' + name + ': ' + p.prices.length + ' prices to check</h2>'
      + table([['#'], ['Product'], ['Shop'], ['Our price', 'n']], p.prices.map((x, i) => '<tr><td>' + (i + 1) + '</td><td class="w">'
        + esc(x.product) + '</td><td>' + link(x.url, x.shop) + '</td><td class="n">' + num(x.price) + ' JOD</td></tr>'));
  });
  const acc = h.accuracy || [], hid = acc.filter((a) => a.hidden);
  html += '<h2>Accuracy check (every hour)</h2><p class="mute">Shops far apart in price for one product. Over 2x (and 15+ JOD) between shops is almost always '
    + 'two products joined: <b>hidden</b> until fixed (the hourly fix and the daily doctor handle it). 1.5x to 2x stays up: usually a real difference.</p>'
    + tiles([['Hidden now', '<span class="' + (hid.length ? 'bad' : 'ok') + '">' + num(hid.length) + '</span>'], ['To look at', num(acc.length - hid.length)]])
    + (acc.length ? '<div class="tall">' + table([['Product'], ['Apart', 'n'], ['State'], ['Shops and prices']], acc.map((a) => '<tr><td class="w">'
      + esc(a.name) + '</td><td class="n">' + a.ratio + 'x</td><td class="' + (a.hidden ? 'bad' : 'warn') + '">' + (a.hidden ? 'Hidden' : 'Look')
      + '</td><td class="w">' + a.offers.map((o) => link(o.url, o.shop + ' ' + num(o.price)) + ' <span class="mute">' + esc(o.title) + '</span>').join('<br>') + '</td></tr>')) + '</div>' : '');
  html += '<h2>Catalog growth (30 days)</h2>' + bars(d.trend || [], ['products'], ['#888']);
  const added = h.catalog_added_14d || [], kinds = {};
  added.forEach((a) => { const k = a.cat || 'phone'; kinds[k] = (kinds[k] || 0) + 1; });
  html += '<h2>New products added by themselves (14 days): ' + num(added.length) + '</h2>'
    + '<div class="chips" id="addedkinds"><button type="button" class="chip on" data-k="">All <b>' + num(added.length) + '</b></button>'
    + Object.keys(kinds).sort((a, b) => kinds[b] - kinds[a]).map((k) => '<button type="button" class="chip" data-k="' + esc(k) + '">'
      + esc(KIND[k] || k) + ' <b>' + num(kinds[k]) + '</b></button>').join('') + '</div>'
    + '<div class="tall">' + table([['Product'], ['Kind'], ['How'], ['When']],
      added.map((a) => '<tr data-k="' + esc(a.cat || 'phone') + '"><td class="w">' + esc(a.name) + '</td><td>'
        + esc(KIND[a.cat || 'phone'] || a.cat) + '</td><td class="w">' + esc(a.way) + '</td><td>' + ago(a.at) + '</td></tr>')) + '</div>';
  return html;
}

function ads() {
  const box = document.getElementById('adsbox');
  fetch('/admin/ads.json', { credentials: 'same-origin' }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }).then((D) => {
    const st = (a) => a.stopped ? ['Stopped', 'warn'] : a.end < D.today ? ['Ended', 'warn'] : a.start > D.today ? ['Starts ' + a.start, 'warn'] : ['Live now', 'ok'];
    const live = D.ads.filter((a) => !a.stopped && a.start <= D.today && a.end >= D.today);
    box.innerHTML = tiles([['Live today', num(live.length) + ' / ' + D.max], ['All ads', num(D.ads.length)], ['Taps on ads (all)', num(D.ads.reduce((s, a) => s + (a.clicks || 0), 0))]])
      + '<p><a href="/admin/ads">Add or stop shop ads ›</a></p>'
      + table([['Shop'], ['State'], ['Where'], ['Dates'], ['Taps', 'n']], D.ads.map((a) => { const [t, c] = st(a);
        return '<tr><td>' + esc(a.shop) + '</td><td><span class="pill ' + c + '">' + esc(t) + '</span></td><td>' + esc(D.cats[a.category || ''] || a.category)
          + '</td><td>' + esc(a.start) + ' to ' + esc(a.end) + '</td><td class="n">' + num(a.clicks) + '</td></tr>'; }))
      + '<p class="mute">Google ads in the app (AdMob) report their earnings in the AdMob account, not here.</p>';
  }).catch((e) => { box.innerHTML = '<p class="note">Could not load the ads (' + esc(e.message) + ').</p>'; });
}

const TABS = [['overview', 'Overview'], ['money', 'Money'], ['data', 'Data'], ['ads', 'Ads']];
function render(d) {
  document.getElementById('who').textContent = 'Signed in as ' + d.email;
  const h = d.health, [cls, line] = status(h);
  const html = '<div class="status ' + cls + '">' + esc(line) + '</div><div class="tabs" role="tablist">'
    + TABS.map(([k, l]) => '<button type="button" class="tab" role="tab" data-tab="' + k + '">' + l + '</button>').join('') + '</div>'
    + '<section data-tab="overview">' + overview(d, h) + '</section><section data-tab="money">' + money(d, h) + '</section>'
    + '<section data-tab="data">' + data(d, h) + '</section><section data-tab="ads"><h2>Shop ads</h2><div id="adsbox"><p class="mute">Loading…</p></div></section>'
    + '<h2>Elsewhere</h2><p class="mute">Google Search Console and Bing Webmaster Tools show how people find the site in search. Google Play Console will show app installs after the release.</p>';
  document.getElementById('root').innerHTML = html;
  let adsLoaded = false;
  const pick = (k) => {
    if (!TABS.some((t) => t[0] === k)) k = 'overview';
    document.querySelectorAll('.tab').forEach((b) => b.setAttribute('aria-selected', b.dataset.tab === k ? 'true' : 'false'));
    document.querySelectorAll('section[data-tab]').forEach((s) => { s.hidden = s.dataset.tab !== k; });
    if (k === 'ads' && !adsLoaded) { adsLoaded = true; ads(); }
    if (location.hash.slice(1) !== k) history.replaceState(null, '', '#' + k);
  };
  document.querySelector('.tabs').addEventListener('click', (ev) => { const b = ev.target.closest('.tab'); if (b) pick(b.dataset.tab); });
  pick(location.hash.slice(1));
  const box = document.getElementById('addedkinds');
  if (box) box.addEventListener('click', (ev) => {   // show one kind of new product, or all of them
    const b = ev.target.closest('button[data-k]');
    if (!b) return;
    box.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
    const k = b.getAttribute('data-k');
    document.querySelectorAll('tr[data-k]').forEach((r) => { r.hidden = !!k && r.getAttribute('data-k') !== k; });
  });
}

fetch('/admin/data.json', { credentials: 'same-origin' }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then(render).catch((e) => { document.getElementById('root').innerHTML = '<p class="note">Could not load the numbers (' + esc(e.message) + '). Reload to sign in again.</p>'; });
`;

const ADS_PAGE = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Kamkam shop ads</title>
<style>
:root{--ink:#141414;--paper:#f4f2ec;--surface:#fff;--mute:#6b6b6b;--green:#1f7a3d;--red:#c8102e;--warn:#9a5b00;--line:#d9d6cc}
@media (prefers-color-scheme:dark){:root{--ink:#f1efe8;--paper:#121212;--surface:#1c1c1c;--mute:#a3a3a3;--line:#333}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:900px;margin:0 auto;padding:16px}h1{margin:8px 0;font-size:26px}h2{margin:26px 0 10px;font-size:19px;border-inline-start:6px solid var(--red);padding-inline-start:8px}
.mute{color:var(--mute);font-size:14px}.box{background:var(--surface);border:1.5px solid var(--ink);border-radius:12px;padding:14px;margin:10px 0}
label{display:block;margin:10px 0 4px;font-weight:700;font-size:14px}input{width:100%;font:inherit;padding:10px;border:1.5px solid var(--line);border-radius:8px;background:var(--paper);color:var(--ink)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}button{font:inherit;font-weight:700;padding:10px 16px;border-radius:999px;border:0;background:var(--red);color:#fff;cursor:pointer;margin-top:12px}
button.stop{background:var(--ink);color:var(--paper);padding:6px 12px;margin:0;font-size:13px}.err{color:var(--red);font-weight:700}.ok{color:var(--green);font-weight:700}
.ad{display:flex;justify-content:space-between;gap:10px;align-items:center;border-top:1px solid var(--line);padding:10px 0}.ad:first-child{border-top:0}
.pill{display:inline-block;font-size:12px;font-weight:700;padding:1px 8px;border-radius:999px}.live{background:#e3f3ea;color:var(--green)}.soon{background:#fdf1dc;color:var(--warn)}.done{background:var(--line);color:var(--mute)}
.strip{background:#fff8e1;color:#3a2a00;border:1.5px solid #ffc629;border-radius:10px;padding:8px 12px;direction:rtl}.strip b{background:#3a2a00;color:#ffc629;border-radius:4px;padding:0 6px;font-size:12px;margin-inline-start:6px}
</style></head>
<body><main>
<p><a href="/admin">‹ Admin</a></p><h1>Shop ads</h1>
<p class="mute">A labelled card ("إعلان") between products: in its category's lists (after the 4th product, then every 12) and
product pages; an all-pages ad also shows on home and deals and fills categories that have no ad. Sold by the week; at most 3 ads
on any page at the same time. An ad starts and stops by itself on its dates. Ads never change the price order.</p>
<div id="root"><p class="mute">Loading…</p></div>
</main><script src="/admin/ads.js"></script></body></html>`;

const ADS_JS = `
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let D = null;
function state(a) { return a.stopped ? ['Stopped', 'done'] : a.end < D.today ? ['Ended', 'done'] : a.start > D.today ? ['Starts ' + a.start, 'soon'] : ['Live now', 'live']; }
function draw(msg) {
  const live = D.ads.filter((a) => !a.stopped && a.start <= D.today && a.end >= D.today).length;
  let h = '<h2>Add an ad</h2><div class="box">'
    + '<label for="shop">Shop</label><input id="shop" maxlength="60" placeholder="SmartBuy">'
    + '<label for="ar">Ad text (Arabic, short)</label><input id="ar" dir="rtl" maxlength="90" placeholder="خصم 10% على سماعات Sony هذا الأسبوع">'
    + '<label for="en">Ad text (English, optional)</label><input id="en" maxlength="90" placeholder="10% off Sony headphones this week">'
    + '<label for="cat">Where it shows</label><select id="cat">' + Object.keys(D.cats).map((k) => '<option value="' + k + '">' + esc(D.cats[k]) + '</option>').join('') + '</select>'
    + '<label for="url">Link (the shop page the ad opens)</label><input id="url" inputmode="url" placeholder="https://...">'
    + '<div class="row"><div><label for="start">Start date</label><input id="start" type="date" value="' + D.today + '" min="' + D.today + '"></div>'
    + '<div><label for="weeks">Weeks</label><input id="weeks" type="number" min="1" max="12" value="1"></div></div>'
    + '<p class="mute">How it looks:</p><div class="strip" id="prev">…</div>'
    + '<button id="add" type="button">Add the ad</button> <span id="msg">' + (msg || '') + '</span></div>';
  h += '<h2>Ads (' + live + ' of ' + D.max + ' live today)</h2><div class="box">' + (D.ads.length ? D.ads.map((a) => {
    const [st, cls] = state(a);
    return '<div class="ad"><div><b>' + esc(a.shop) + '</b> <span class="pill ' + cls + '">' + st + '</span> <span class="mute">' + esc(D.cats[a.category || ''] || a.category) + '</span><br><span dir="rtl">' + esc(a.text_ar) + '</span><br>'
      + '<span class="mute">' + esc(a.start) + ' to ' + esc(a.end) + ' · ' + a.clicks + ' taps · <a href="' + esc(a.url) + '" target="_blank" rel="noopener noreferrer">link</a></span></div>'
      + (!a.stopped && a.end >= D.today ? '<button class="stop" type="button" data-id="' + a.id + '">Stop</button>' : '') + '</div>';
  }).join('') : '<p class="mute">No ads yet.</p>') + '</div>';
  document.getElementById('root').innerHTML = h;
  const prev = () => { document.getElementById('prev').innerHTML = esc(document.getElementById('shop').value || 'Shop') + ': '
    + esc(document.getElementById('ar').value || 'نص الإعلان') + ' <b>إعلان</b>'; };
  ['shop', 'ar'].forEach((k) => document.getElementById(k).addEventListener('input', prev)); prev();
  document.getElementById('add').addEventListener('click', add);
  document.querySelectorAll('button.stop').forEach((b) => b.addEventListener('click', () => {
    if (confirm('Stop this ad now? It disappears from the app and the site within a few minutes.')) post('/admin/ads/stop?id=' + b.dataset.id, {}).then(() => load('<span class="ok">Stopped.</span>'));
  }));
}
function post(path, body) {
  return fetch(path, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    .then((r) => r.json().then((j) => { if (!r.ok) throw new Error(j.error || r.status); return j; }));
}
function add() {
  const v = (k) => document.getElementById(k).value;
  post('/admin/ads/add', { shop: v('shop'), text_ar: v('ar'), text_en: v('en'), url: v('url'), start: v('start'), weeks: v('weeks'), category: v('cat') })
    .then((j) => load('<span class="ok">Added: ' + esc(j.ad.start) + ' to ' + esc(j.ad.end) + '.</span>'))
    .catch((e) => { document.getElementById('msg').innerHTML = '<span class="err">' + esc(e.message) + '</span>'; });
}
function load(msg) {
  fetch('/admin/ads.json', { credentials: 'same-origin' }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => { D = d; draw(msg); })
    .catch((e) => { document.getElementById('root').innerHTML = '<p class="err">Could not load the ads (' + esc(e.message) + '). Reload to sign in again.</p>'; });
}
load();
`;
