// derbani.com: the static website (served straight from ./web_build without running this code) plus one address:
//
//   /go/<offer id>?p=<product id>&s=app|site[&u=<shop address>]
//
// "Go to shop" passes through here. It counts the click (day, shop, product, app or site) and sends the visitor on to
// the shop with utm_source=derbani. Nothing personal is stored: no IP address, no cookie, no device, no visitor id.
// The shop address comes from /go-map.json (built every hour with the site). An offer newer than that map may pass
// its address in ?u=, which is followed only when it is on a known shop's site, so this is never an open redirect.

import { admin } from './admin.js';

let map = null; // { o: { "<offer id>": [url, shop] }, h: [shop hosts] }, kept while this copy of the worker lives
let mapAt = 0;
let tableReady = false;

const BOT = /bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|telegram|curl|wget|python|headless/i;

async function loadMap(env, request) {
  if (map && Date.now() - mapAt < 10 * 60 * 1000) return map;
  try {
    const r = await env.ASSETS.fetch(new Request(new URL('/go-map.json', request.url)));
    if (r.ok) {
      map = await r.json();
      mapAt = Date.now();
    }
  } catch (e) {}
  return map || { o: {}, h: [] };
}

function withUtm(target) {
  const u = new URL(target);
  u.searchParams.set('utm_source', 'derbani');
  u.searchParams.set('utm_medium', 'referral');
  return u.toString();
}

async function count(env, shop, product, source) {
  if (!env.CLICKS) return; // the counting database is not connected yet: still send the visitor on
  if (!tableReady) {
    await env.CLICKS.prepare(
      'CREATE TABLE IF NOT EXISTS clicks (day TEXT NOT NULL, shop TEXT NOT NULL, product INTEGER NOT NULL, source TEXT NOT NULL,' +
      ' n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, shop, product, source))').run();
    tableReady = true;
  }
  const day = new Date().toISOString().slice(0, 10);
  await env.CLICKS.prepare(
    'INSERT INTO clicks (day, shop, product, source, n) VALUES (?1, ?2, ?3, ?4, 1)' +
    ' ON CONFLICT (day, shop, product, source) DO UPDATE SET n = n + 1').bind(day, shop, product, source).run();
}

async function go(request, env, ctx) {
  const url = new URL(request.url);
  const id = url.pathname.split('/')[2] || '';
  const product = parseInt(url.searchParams.get('p') || '0', 10) || 0;
  const source = url.searchParams.get('s') === 'app' ? 'app' : 'site';
  const m = await loadMap(env, request);
  let target = null;
  let shop = null;
  if (/^\d+$/.test(id) && m.o[id]) {
    [target, shop] = m.o[id];
  } else {
    try {
      const u = new URL(url.searchParams.get('u') || '');
      const host = u.hostname.replace(/^www\./, '');
      if (u.protocol === 'https:' && m.h.includes(host)) {
        target = u.toString();
        shop = host;
      }
    } catch (e) {}
  }
  if (!target) return Response.redirect(new URL('/', request.url).toString(), 302);
  if (request.method === 'GET' && !BOT.test(request.headers.get('user-agent') || '')) {
    ctx.waitUntil(count(env, shop, product, source).catch(() => {}));
  }
  return new Response(null, {
    status: 302,
    headers: { Location: withUtm(target), 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow', 'Referrer-Policy': 'origin' },
  });
}

export default {
  async fetch(request, env, ctx) {
    const path = new URL(request.url).pathname;
    if (path.startsWith('/go/')) return go(request, env, ctx);
    if (path === '/admin' || path.startsWith('/admin/')) return admin(request, env);
    return env.ASSETS.fetch(request); // everything else is the website (its own 404 page included)
  },
};
