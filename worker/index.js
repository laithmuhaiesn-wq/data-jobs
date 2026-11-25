// kamkam.derbani.com (Kamkam, a Derbani product): the static website (served straight from ./web_build without running this code) plus one address:
//
//   /go/<offer id>?p=<product id>&s=app|site[&u=<shop address>]
//
// "Go to shop" passes through here. It counts the click (day, shop, product, app or site) and sends the visitor on to
// the shop with utm_source=kamkam. Nothing personal is stored: no IP address, no cookie, no device, no visitor id.
// The shop address comes from /go-map.json (built every hour with the site). An offer newer than that map may pass
// its address in ?u=, which is followed only when it is on a known shop's site, so this is never an open redirect.

import { admin } from './admin.js';
import { goAd, publicAds } from './ads.js';
import { searchMiss } from './misses.js';

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
  u.searchParams.set('utm_source', 'kamkam');
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

// A shop picture that failed to load in a visitor's browser or the app is reported here (POST, the picture address as
// the body). Only the address and a count are kept. The nightly job reads the list, stops showing pictures that failed
// for at least two loads, and looks for a new one on the shop's product page (shops' pictures are never fetched by us).
let imgReady = false;
async function imgFail(request, env) {
  const ok = new Response(null, { status: 204, headers: { 'Cache-Control': 'no-store' } });
  if (request.method !== 'POST' || !env.CLICKS || BOT.test(request.headers.get('user-agent') || '')) return ok;
  let u = '';
  try { u = (await request.text()).trim(); } catch (e) {}
  if (!/^https?:\/\/[^\s]{4,490}$/.test(u)) return ok;
  try {
    if (!imgReady) {
      await env.CLICKS.prepare('CREATE TABLE IF NOT EXISTS img_fail (url TEXT PRIMARY KEY, n INTEGER NOT NULL DEFAULT 0, day TEXT NOT NULL)').run();
      imgReady = true;
    }
    const day = new Date().toISOString().slice(0, 10);
    await env.CLICKS.prepare('INSERT INTO img_fail (url, n, day) VALUES (?1, 1, ?2) ON CONFLICT (url) DO UPDATE SET n = n + 1, day = ?2')
      .bind(u, day).run();
  } catch (e) {}
  return ok;
}

// Everything else is the website. An address with no file any more goes to the page that took its place
// (redirect-map.json, made with the site: Cloudflare's own list of redirects stops at 2000), else the site's 404 page.
// /api/v/<id>.json (the app's product page) is cut out of its bundle: one file per product would be over Cloudflare's limit
// of 20,000 files.
const BUNDLES = 200; // the same number is in src/pricecompare/api_static.py
async function oneProduct(request, env, url, id) {
  const none = new Response('{"detail":"unknown variant"}', { status: 404, headers: { 'content-type': 'application/json' } });
  const r = await env.ASSETS.fetch(new Request(new URL('/api/vs/' + (id % BUNDLES) + '.json', url)));
  if (!r.ok) return none;
  const found = (await r.json())[id];
  if (!found) return none;
  return new Response(request.method === 'HEAD' ? null : JSON.stringify(found),
    { headers: { 'content-type': 'application/json', 'cache-control': 'public, max-age=0, must-revalidate', 'x-content-type-options': 'nosniff' } });
}

let moved = null;
let movedAt = 0;
async function page(request, env) {
  const r = await env.ASSETS.fetch(request);
  if (r.status !== 404 || (request.method !== 'GET' && request.method !== 'HEAD')) return r;
  const url = new URL(request.url);
  const product = /^\/api\/v\/(\d{1,12})\.json$/.exec(url.pathname);
  if (product) return oneProduct(request, env, url, Number(product[1]));
  if (!moved || Date.now() - movedAt > 10 * 60 * 1000) {
    try {
      const m = await env.ASSETS.fetch(new Request(new URL('/redirect-map.json', url)));
      if (m.ok) { moved = await m.json(); movedAt = Date.now(); }
    } catch (e) {}
  }
  let path = url.pathname;
  try { path = decodeURIComponent(path); } catch (e) {}
  path = path.replace(/\.html$/, '').replace(/(.)\/+$/, '$1');
  const to = moved && Object.prototype.hasOwnProperty.call(moved, path) ? moved[path] : null;
  if (to && to !== path) return new Response(null, { status: 301, headers: { Location: new URL(to, url).toString(), 'Cache-Control': 'public, max-age=600' } });
  const none = await env.ASSETS.fetch(new Request(new URL('/404', url)));
  return new Response(request.method === 'HEAD' ? null : none.body, { status: 404, headers: none.ok ? none.headers : r.headers });
}

export default {
  async fetch(request, env, ctx) {
    const path = new URL(request.url).pathname;
    if (path === '/ads.json') return publicAds(request, env, ctx);
    if (path.startsWith('/go/ad/')) return goAd(request, env, ctx, withUtm);
    if (path === '/img-fail') return imgFail(request, env);
    if (path === '/search-miss') return searchMiss(request, env);
    if (path.startsWith('/go/')) return go(request, env, ctx);
    if (path === '/admin' || path.startsWith('/admin/')) return admin(request, env);
    return page(request, env);
  },
};
