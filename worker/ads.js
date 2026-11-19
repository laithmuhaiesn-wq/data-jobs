// Paid shop ads (owner 2026-11-19): one slim strip above the app's bottom bar and at the bottom of the website.
// Sold by the week, at most 3 shops at the same time (they take turns in the strip). Always labelled "إعلان" and never
// part of the price order. The owner adds and stops them at /admin/ads (behind the same login as /admin).
//
//   /ads.json        the ads running today (public; the app and the site read it)
//   /go/ad/<id>      a tap on an ad: counted (a number per ad, nothing personal), then on to the shop's page

export const MAX_LIVE = 3;
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
    + ' stopped INTEGER NOT NULL DEFAULT 0, clicks INTEGER NOT NULL DEFAULT 0)').run();
  ready = true;
}

export async function liveAds(db, day) {
  await ensure(db);
  const r = await db.prepare('SELECT id, shop, text_ar, text_en FROM ads WHERE stopped = 0 AND start <= ?1 AND end >= ?1'
    + ' ORDER BY start, id LIMIT ' + MAX_LIVE).bind(day).all();
  return r.results || [];
}

export async function publicAds(request, env) {
  let ads = [];
  if (env.CLICKS) {
    try {
      ads = (await liveAds(env.CLICKS, today())).map((a) => ({ id: a.id, shop: a.shop, ar: a.text_ar, en: a.text_en, go: '/go/ad/' + a.id }));
    } catch (e) {
      ads = [];
    }
  }
  return new Response(JSON.stringify({ ads }), {
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'public, max-age=300', 'Access-Control-Allow-Origin': '*' },
  });
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
  // at most 3 shops on any day: find the first day that is already full
  for (let d = start; d <= end; d = addDays(d, 1)) {
    const n = taken.filter((a) => a.start <= d && a.end >= d).length;
    if (n >= MAX_LIVE) return [null, 'Full on ' + d + ': ' + MAX_LIVE + ' ads already run that day. Pick a later start.'];
  }
  return [{ shop, text_ar: ar, text_en: en, url: link, start, end }, null];
}
