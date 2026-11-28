// api.derbani.com without the PC (docs/cloud-move-plan.md, 2026-11-27). The same answers as the old Python API
// (src/pricecompare/api/app.py), made from the files the hourly build already publishes under /api/:
// summaries.json (every product's summary), search.json (the search rules and every product's search text),
// vs/<n>.json (each product's full page), and the fixed lists (categories, guides, shops, filters).
// Typed search uses web/search.js, the site's copy of the same rules (the nightly search check keeps them equal).
// Its own worker (kamkam-api, worker/api.wrangler.jsonc): on the site's worker, the site's own /search page would answer.
import Search from '../web/search.js';

const DISCLAIMER = "Prices are copied from each shop's public page and may be out of date. Check the shop before buying.";
const BUNDLES = 200; // the same number is in src/pricecompare/api_static.py
const KEEP_MS = 5 * 60 * 1000; // files re-read every 5 minutes (the site is published hourly)
const FILES = 'https://kamkam.derbani.com/api/';

let cache = null;
let cacheAt = 0;

async function file(path) {
  const r = await fetch(FILES + path, { cf: { cacheTtl: 300 } });
  if (!r.ok) throw new Error(path + ' ' + r.status);
  return r.json();
}

async function load() {
  if (cache && Date.now() - cacheAt < KEEP_MS) return cache;
  const [sum, ix, deals] = await Promise.all([file('summaries.json'), file('search.json'), file('deals.json')]);
  const all = sum.results;
  const byId = new Map(all.map((v) => [v.id, v]));
  // search.json has [id, text, joined text]; web/search.js wants {h, k, c}
  ix.items = ix.items.filter((r) => byId.has(r[0])).map((r) => ({ id: r[0], h: r[1], k: r[2], c: byId.get(r[0]).category }));
  // summaries.json also holds old ids of joined products (for the saved list); lists and search use only today's
  const today = new Set(ix.items.map((it) => it.id));
  cache = { all: all.filter((v) => today.has(v.id)), byId, ix, built: deals.built || null };
  cacheAt = Date.now();
  return cache;
}

// most compared first, then cheapest; products without a ranked price last (app.py rank_key)
function rank(a, b) {
  return (b.ranked_shops - a.ranked_shops) || ((a.best_price == null) - (b.best_price == null)) ||
    ((a.best_price || 0) - (b.best_price || 0)) || (a.label < b.label ? -1 : a.label > b.label ? 1 : 0) || (a.id - b.id);
}

function summary(v) {
  const out = {};
  for (const k of ['id', 'category', 'brand', 'brand_ar', 'model', 'storage', 'storage_gb', 'ram_gb', 'label', 'slug', 'market', 'gray', 'image', 'images',
    'best_price', 'best_store', 'highest_price', 'save', 'ranked_shops', 'shops', 'was', 'drop', 'drop_pct', 'dropped_at', 'at_lowest', 'kinds', 'f', 'q']) {
    if (k in v) out[k] = v[k];
  }
  return out;
}

function int(x, def, lo, hi) {
  const n = x == null || x === '' ? def : Number(x);
  return Number.isInteger(n) && n >= lo && n <= hi ? n : null;
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', 'cache-control': 'public, max-age=60', 'access-control-allow-origin': '*', 'x-content-type-options': 'nosniff' },
  });
}

async function product(id) {
  const r = await fetch(FILES + 'vs/' + (id % BUNDLES) + '.json', { cf: { cacheTtl: 300 } });
  return r.ok ? (await r.json())[id] || null : null;
}

export async function api(request) {
  if (request.method !== 'GET' && request.method !== 'HEAD') return json({ detail: 'Method Not Allowed' }, 405);
  const url = new URL(request.url);
  const q = url.searchParams;
  const path = url.pathname.replace(/\/+$/, '') || '/';
  const fixed = { '/filters': 'filters.json', '/guides': 'guides.json', '/shops': 'shops.json', '/categories': 'categories.json' };
  if (fixed[path]) return json(await file(fixed[path]));

  const d = await load();
  const inCategory = (category, def = 'phone') => {
    const c = category || def;
    return c == null || c === 'all' ? d.all : d.all.filter((v) => v.category === c);
  };
  const bad = (field) => json({ detail: [{ loc: ['query', field], msg: 'invalid value' }] }, 422);

  if (path === '/health') return json({ ok: true, variants: d.all.length, built: d.built, sale: saleSeason(new Date()) || ((await autoSale()) ? 'price drops' : null) });

  if (path === '/search') {
    const text = q.get('q') || '', brand = q.get('brand'), category = q.get('category');
    const limit = int(q.get('limit'), 30, 1, 1000);
    if (limit == null) return bad('limit');
    if (text.length > 80) return bad('q');
    const okBrand = (v) => !brand || [v.brand.toLowerCase(), v.brand_ar].includes(brand.toLowerCase());
    let hits;
    if (text.trim()) {
      const rows = new Set(inCategory(category || Search.kind(text, d.ix), null).filter(okBrand).map((v) => v.id));
      hits = Search.scored(text, d.ix).filter((f) => rows.has(f[1].id))
        .map((f) => [f[0], d.byId.get(f[1].id)])
        .sort((a, b) => a[0] - b[0] || rank(a[1], b[1])).map((f) => f[1]);
    } else {
      hits = inCategory(category).filter(okBrand).sort(rank);
    }
    return json({ disclaimer: DISCLAIMER, count: hits.length, results: hits.slice(0, limit).map(summary) });
  }

  if (path === '/popular') {
    const limit = int(q.get('limit'), 12, 1, 50);
    if (limit == null) return bad('limit');
    const top = inCategory(q.get('category')).filter((v) => v.ranked_shops >= 2 && !v.gray).sort(rank).slice(0, limit);
    return json({ disclaimer: DISCLAIMER, results: top.map(summary) });
  }

  if (path === '/brands') {
    const counts = new Map();
    for (const v of inCategory(q.get('category'))) {
      if (!counts.has(v.brand)) counts.set(v.brand, { brand: v.brand, brand_ar: v.brand_ar, variants: 0 });
      counts.get(v.brand).variants++;
    }
    return json({ results: [...counts.values()].sort((a, b) => (b.variants - a.variants) || (a.brand < b.brand ? -1 : a.brand > b.brand ? 1 : 0)) });
  }

  if (path === '/deals') {
    const limit = int(q.get('limit'), 30, 1, 60);
    if (limit == null) return bad('limit');
    const byLabel = (a, b) => (a.label < b.label ? -1 : a.label > b.label ? 1 : 0);
    const live = inCategory(q.get('category')).filter((v) => !v.gray && v.best_price != null);
    const drops = live.filter((v) => v.drop >= 1).sort((a, b) => (b.drop_pct - a.drop_pct) || byLabel(a, b)).slice(0, limit);
    const gaps = live.filter((v) => v.ranked_shops >= 2 && v.save >= 5).sort((a, b) => (b.save - a.save) || byLabel(a, b)).slice(0, limit);
    return json({ disclaimer: DISCLAIMER, built: d.built, drops: drops.map(summary), gaps: gaps.map(summary) });
  }

  if (path === '/variants' || path === '/compare') {
    const ids = q.get('ids') || '';
    if (ids.length > (path === '/variants' ? 600 : 60)) return bad('ids');
    const want = ids.split(',').map((x) => x.trim()).filter((x) => /^\d+$/.test(x)).map(Number).slice(0, path === '/variants' ? 80 : 4);
    if (path === '/variants') {
      return json({ disclaimer: DISCLAIMER, built: d.built, results: want.filter((i) => d.byId.has(i)).map((i) => summary(d.byId.get(i))) });
    }
    const out = [];
    for (const i of want) {
      const v = d.byId.get(i);
      if (v) out.push({ ...summary(v), specs: ((await product(i)) || {}).specs ?? null });
    }
    return json({ disclaimer: DISCLAIMER, built: d.built, results: out });
  }

  const one = /^\/variants\/(\d{1,12})$/.exec(path);
  if (one) {
    const v = await product(Number(one[1]));
    return v ? json(v) : json({ detail: 'unknown variant' }, 404);
  }
  return json({ detail: 'Not Found' }, 404);
}

// The clock of the cloud jobs: every hour at :05 (wrangler cron) the GitHub "jobs" run is started. GitHub's own schedule
// was too unreliable (1 run in 16 hours on 2026-11-27). GITHUB_TOKEN: a worker secret, a fine-grained token that can
// only start workflows in laithmuhaiesn-wq/data-jobs (Actions: read and write).
// Sale mode (owner 2026-11-28: "handled now for all major sales"): in these seasons the jobs run every 30 minutes
// instead of every hour. Two ways in: this calendar of the yearly sales in Jordan (the Hijri ones found each year from
// the Umm al-Qura calendar, so they never need updating), and api/sale.json, which every cloud run writes when far
// more prices went down than on a usual day (src/pricecompare/sale.py): a sale nobody put in the calendar.
const HIJRI = new Intl.DateTimeFormat('en-u-ca-islamic-umalqura', { year: 'numeric', month: 'numeric', day: 'numeric', timeZone: 'Asia/Amman' });
function hijri(now) {
  const p = Object.fromEntries(HIJRI.formatToParts(now).map((x) => [x.type, x.value]));
  return { m: Number(p.month), d: Number(p.day) };
}
// [month, day] .. [month, day] in Amman's calendar; a season that crosses the new year is written as two
const SEASONS = [
  ['New year', [12, 24], [12, 31]], ['New year', [1, 1], [1, 3]],
  ["Mother's Day", [3, 16], [3, 22]],
  ['Independence Day', [5, 22], [5, 26]],
  ['Back to school', [8, 18], [9, 8]],
  ['11.11', [11, 9], [11, 12]],
];
const HIJRI_SEASONS = [   // Hijri [month, day] .. [month, day]
  ['Ramadan and Eid al-Fitr', [9, 1], [10, 4]],
  ['Eid al-Adha', [12, 1], [12, 13]],
];
function saleSeason(now) {
  const amman = new Date(now.getTime() + 3 * 3600000);
  const y = amman.getUTCFullYear(), md = (amman.getUTCMonth() + 1) * 100 + amman.getUTCDate();
  const nov1 = new Date(Date.UTC(y, 10, 1)).getUTCDay();
  const thanksgiving = 1 + ((4 - nov1 + 7) % 7) + 21;                          // the 4th Thursday of November
  if (md >= 1100 + thanksgiving - 3 && md <= 1100 + thanksgiving + 4) return 'Black Friday week';   // Monday .. Cyber Monday
  for (const [name, a, b] of SEASONS) if (md >= a[0] * 100 + a[1] && md <= b[0] * 100 + b[1]) return name;
  const h = hijri(now), hmd = h.m * 100 + h.d;
  for (const [name, a, b] of HIJRI_SEASONS) if (hmd >= a[0] * 100 + a[1] && hmd <= b[0] * 100 + b[1]) return name;
  return null;
}
let auto = { at: 0, on: false };
async function autoSale() {        // what the last cloud run found from the day's price drops (5 minutes kept)
  if (Date.now() - auto.at > KEEP_MS) {
    try {
      const r = await fetch(FILES + 'sale.json', { cf: { cacheTtl: 300 } });
      auto = { at: Date.now(), on: r.ok && (await r.json()).auto === true };
    } catch (e) { auto = { at: Date.now(), on: false }; }
  }
  return auto.on;
}
function saleMode(now) {
  return saleSeason(now) !== null;
}

function dispatch(env, workflow, inputs) {
  return fetch('https://api.github.com/repos/laithmuhaiesn-wq/data-jobs/actions/workflows/' + workflow + '/dispatches', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + env.GITHUB_TOKEN, Accept: 'application/vnd.github+json', 'User-Agent': 'kamkam-clock', 'X-GitHub-Api-Version': '2022-11-28' },
    body: JSON.stringify(inputs ? { ref: 'main', inputs } : { ref: 'main' }),
  });
}

async function startJobs(env) {
  const r = await dispatch(env, 'jobs.yml');
  if (r.status !== 204) {
    // GitHub refused to start the jobs (key expired, workflow switched off, account limit): the owner is told at once.
    // If GitHub refuses for days, it is time for the server plan (docs/cloud-move-plan.md, "Plan B: a server").
    await dispatch(env, 'alarm.yml', { why: 'GitHub refused to start the hourly jobs (answer ' + r.status + '). If this goes on, move the jobs to a server (plan B).' });
    throw new Error('GitHub answered ' + r.status);
  }
}

// The hourly alarm (owner 2026-11-28: "full auto and doesn't need me"): the site's files carry the time they were built.
// Over 2.5 hours old = the runs stopped or fail: an email (alarm.yml) the first hour it happens, then every 12 hours.
async function watch(env, now) {
  let built = null;
  try {
    const r = await fetch(FILES + 'deals.json', { cf: { cacheTtl: 0 } });
    built = (await r.json()).built;
  } catch (e) { /* no answer from the site counts as old */ }
  const hours = built ? (now - new Date(built)) / 3600000 : 99;
  if (hours < 2.5) return;
  if (hours < 3.5 || now.getUTCHours() % 12 === 0) {
    await dispatch(env, 'alarm.yml', { why: built ? 'the site was last published ' + Math.floor(hours) + ' hours ago: the hourly jobs stopped or fail'
      : 'the site files do not answer' });
  }
}

export { saleMode, saleSeason };

export default {
  async scheduled(event, env, ctx) {
    const now = new Date(event.scheduledTime);
    if (now.getUTCMinutes() >= 30 && !saleMode(now) && !(await autoSale())) return;   // half past: only in a sale
    ctx.waitUntil(startJobs(env));
    if (now.getUTCMinutes() < 30) ctx.waitUntil(watch(env, now));
  },
  async fetch(request, env, ctx) {
    try {
      // The same question within 5 minutes is answered from Cloudflare's cache near the visitor (owner 2026-11-28:
      // "100,000 users a day": faster, and the worker's work is paid per use). The files behind it change hourly.
      const url = new URL(request.url);
      if (request.method !== 'GET' || url.pathname === '/health' || !ctx) return await api(request);
      const cache = caches.default;
      const hit = await cache.match(request);
      if (hit) return hit;
      const res = await api(request);
      if (res.status !== 200) return res;
      const keep = new Response(res.body, res);
      keep.headers.set('Cache-Control', 'public, max-age=300');
      ctx.waitUntil(cache.put(request, keep.clone()));
      return keep;
    } catch (e) {
      return json({ detail: 'try again soon' }, 503);
    }
  },
};
