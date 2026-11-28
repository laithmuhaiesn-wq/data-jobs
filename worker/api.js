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

  if (path === '/health') return json({ ok: true, variants: d.all.length, built: d.built });

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
async function startJobs(env) {
  const r = await fetch('https://api.github.com/repos/laithmuhaiesn-wq/data-jobs/actions/workflows/jobs.yml/dispatches', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + env.GITHUB_TOKEN, Accept: 'application/vnd.github+json', 'User-Agent': 'kamkam-clock', 'X-GitHub-Api-Version': '2022-11-28' },
    body: JSON.stringify({ ref: 'main' }),
  });
  if (r.status !== 204) throw new Error('GitHub answered ' + r.status);
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(startJobs(env));
  },
  async fetch(request) {
    try {
      return await api(request);
    } catch (e) {
      return json({ detail: 'try again soon' }, 503);
    }
  },
};
