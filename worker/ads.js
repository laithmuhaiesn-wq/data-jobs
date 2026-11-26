// Paid shop ads (owner 2026-11-19): labelled cards between products, matched to a category (or all pages).
// Sold by the week, at most 3 ads at the same time on any page (a category's own ads plus the all-pages ones). Always labelled "إعلان" and never
// part of the price order. The owner adds and stops them at /admin/ads (behind the same login as /admin).
//
//   /ads.json        the ads running today (public; the app and the site read it)
//   /go/ad/<id>      a tap on an ad: counted (a number per ad, nothing personal), then on to the shop's page

export const MAX_LIVE = 3;
// '' = all pages; the rest are the site's live categories (display.py LIVE_CATEGORIES)
export const AD_CATS = { '': 'All pages', phone: 'Phones', tablet: 'Tablets', laptop: 'Laptops', tv: 'TVs', watch: 'Smartwatches',
  audio: 'Headphones', console: 'Game consoles', monitor: 'Monitors', speaker: 'Speakers', printer: 'Printers',
  desktop: 'Desktops', router: 'Routers', powerbank: 'Power banks', storage: 'Storage', camera: 'Cameras',
  projector: 'Projectors', smarthome: 'Smart home', peripheral: 'Keyboards and mice', tabletacc: 'Tablet accessories',
  pcpart: 'PC parts', ram: 'RAM' };
const BOT = /bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|telegram|curl|wget|python|headless/i;
let ready = false;

/** Today's date in Amman (UTC+3 all year), as YYYY-MM-DD: ads start and end on Jordan days. */
export function today(now = new Date()) {
  return new Date(now.getTime() + 3 * 3600 * 1000).toISOString().slice(0, 10);
}

export function addDays(day, n) {
  const d = new Date(day + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export async function ensure(db) {
  if (ready) return;
  await db.prepare('CREATE TABLE IF NOT EXISTS ads (id INTEGER PRIMARY KEY AUTOINCREMENT, shop TEXT NOT NULL, text_ar TEXT NOT NULL,'
    + ' text_en TEXT NOT NULL, url TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, created TEXT NOT NULL,'
    + " stopped INTEGER NOT NULL DEFAULT 0, clicks INTEGER NOT NULL DEFAULT 0, category TEXT NOT NULL DEFAULT '')").run();
  try { // ads made before categories: the column is added once
    await db.prepare("ALTER TABLE ads ADD COLUMN category TEXT NOT NULL DEFAULT ''").run();
  } catch (e) {}
  ready = true;
}

export async function liveAds(db, day) {
  await ensure(db);
  const r = await db.prepare('SELECT id, shop, text_ar, text_en, category, end FROM ads WHERE stopped = 0 AND start <= ?1 AND end >= ?1'
    + ' ORDER BY start, id LIMIT 60').bind(day).all();
  return r.results || [];
}

// Kept at the edge for 5 minutes: visitors get it at once, without a database trip each time (an ad the owner adds
// or stops shows within 5 minutes). Each ad says its last day ("until"), so the app can keep a copy for a slow start.
export async function publicAds(request, env, ctx) {
  const key = new Request(new URL('/ads.json', request.url).toString());
  const cache = typeof caches !== 'undefined' ? caches.default : null;
  if (cache) {
    const hit = await cache.match(key).catch(() => null);
    if (hit) return hit;
  }
  let ads = [];
  if (env.CLICKS) {
    try {
      ads = (await liveAds(env.CLICKS, today())).map((a) => ({ id: a.id, shop: a.shop, ar: a.text_ar, en: a.text_en, cat: a.category || '', until: a.end, go: '/go/ad/' + a.id }));
    } catch (e) {
      ads = [];
    }
  }
  const res = new Response(JSON.stringify({ ads }), {
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'public, max-age=300', 'Access-Control-Allow-Origin': '*' },
  });
  if (cache && ctx) ctx.waitUntil(cache.put(key, res.clone()).catch(() => {}));
  return res;
}

export async function goAd(request, env, ctx, withUtm) {
  const url = new URL(request.url);
  const id = parseInt(url.pathname.split('/')[3] || '0', 10) || 0;
  let target = null;
  if (env.CLICKS && id) {
    try {
      await ensure(env.CLICKS);
      const r = await env.CLICKS.prepare('SELECT url FROM ads WHERE id = ?1').bind(id).all();
      target = (r.results || [])[0]?.url || null;
    } catch (e) {}
  }
  if (!target || !target.startsWith('https://')) return Response.redirect(new URL('/', request.url).toString(), 302);
  if (request.method === 'GET' && !BOT.test(request.headers.get('user-agent') || '')) {
    ctx.waitUntil(env.CLICKS.prepare('UPDATE ads SET clicks = clicks + 1 WHERE id = ?1').bind(id).run().catch(() => {}));
  }
  return new Response(null, {
    status: 302,
    headers: { Location: withUtm(target), 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow', 'Referrer-Policy': 'origin' },
  });
}

/** Checks a new ad from the admin form. Returns [ad, null] or [null, error]. `taken` = the ads not stopped. */
export function checkAd(body, taken, day) {
  const s = (v, n) => String(v == null ? '' : v).trim().slice(0, n);
  const shop = s(body.shop, 60);
  const ar = s(body.text_ar, 90);
  const en = s(body.text_en, 90) || ar;
  const link = s(body.url, 500);
  const start = s(body.start, 10);
  const weeks = parseInt(body.weeks, 10);
  const category = s(body.category, 20);
  if (!(category in AD_CATS)) return [null, 'Pick where the ad shows.'];
  if (!shop) return [null, 'Write the shop name.'];
  if (!ar) return [null, 'Write the ad text in Arabic.'];
  try {
    if (new URL(link).protocol !== 'https:') throw new Error();
  } catch (e) {
    return [null, 'The link must be a full https:// address of the shop page.'];
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start)) return [null, 'Pick a start date.'];
  if (start < day) return [null, 'The start date has passed.'];
  if (!(weeks >= 1 && weeks <= 12)) return [null, 'Weeks must be 1 to 12.'];
  const end = addDays(start, 7 * weeks - 1);
  // at most 3 ads on any page on any day: an all-pages ad shares every category's places, a category ad its own
  const meets = (a) => !category || !a.category || a.category === category;
  for (let d = start; d <= end; d = addDays(d, 1)) {
    const n = taken.filter((a) => meets(a) && a.start <= d && a.end >= d).length;
    if (n >= MAX_LIVE) return [null, 'Full on ' + d + ': ' + MAX_LIVE + ' ads already run there that day. Pick a later start or another category.'];
  }
  return [{ shop, text_ar: ar, text_en: en, url: link, start, end, category }, null];
}
