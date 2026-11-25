// Searches that found nothing (owner 2026-11-25): POST /search-miss?s=site|app with the typed words as the body.
// Kept: the words, the day, app or site, and a count. Never kept: name, address (IP), device, cookie or place.
// Anything that looks like a phone number, an email, a link or a long number is dropped, here and before it is sent.
// Old days are deleted after KEEP_DAYS.
// OFF until the privacy page says it (the owner reads that text first): set ON here and RECORD_MISSES in web/search.js and
// recordMisses in app/lib/misses.dart together.

export const ON = false;
const KEEP_DAYS = 90, MAX_DAY = 2000, PER_MINUTE = 10;
const BOT = /bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|telegram|curl|wget|python|headless/i;

/** The words to keep, or null when they must not be kept. */
export function cleanSearch(text) {
  let s = String(text || '').normalize('NFKC').toLowerCase();
  s = s.replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x660)).replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x6f0));
  if (/@|:\/\/|www\.|\.(com|net|org|jo)\b/.test(s)) return null;
  s = s.replace(/[^\p{L}\p{N}+.\-"' ]+/gu, ' ').replace(/\s+/g, ' ').trim();
  if (s.length < 2 || s.length > 60 || s.split(' ').length > 8 || !/[\p{L}\p{N}]/u.test(s)) return null;
  if (/\d(?:[\s+.\-"']*\d){6,}/.test(s)) return null; // 7 or more digits: a phone, card or ID number
  return s;
}

// too many from one visitor in a minute: counted in memory only, for that minute, and never written anywhere
let minute = 0;
let seen = new Map();
function tooMany(request) {
  const now = Math.floor(Date.now() / 60000);
  if (now !== minute) { minute = now; seen = new Map(); }
  const key = request.headers.get('cf-connecting-ip') || '';
  const n = (seen.get(key) || 0) + 1;
  if (seen.size < 5000 || seen.has(key)) seen.set(key, n);
  return n > PER_MINUTE;
}

let ready = false;
export async function searchMiss(request, env, on = ON) {
  const ok = new Response(null, { status: 204, headers: { 'Cache-Control': 'no-store' } });
  if (!on || request.method !== 'POST' || !env.CLICKS || BOT.test(request.headers.get('user-agent') || '')) return ok;
  const url = new URL(request.url);
  const origin = request.headers.get('origin');
  if ((origin && origin !== url.origin) || Number(request.headers.get('content-length') || 0) > 400 || tooMany(request)) return ok;
  try {
    const q = cleanSearch((await request.text()).slice(0, 400));
    if (!q) return ok;
    const db = env.CLICKS;
    if (!ready) {
      await db.prepare('CREATE TABLE IF NOT EXISTS search_miss (day TEXT NOT NULL, q TEXT NOT NULL, source TEXT NOT NULL,' +
        ' n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, q, source))').run();
      ready = true;
    }
    const day = new Date().toISOString().slice(0, 10);
    const source = url.searchParams.get('s') === 'app' ? 'app' : 'site';
    await db.prepare('INSERT INTO search_miss (day, q, source, n) SELECT ?1, ?2, ?3, 1 WHERE (SELECT COUNT(*) FROM search_miss WHERE day = ?1) < ' + MAX_DAY +
      ' ON CONFLICT (day, q, source) DO UPDATE SET n = n + 1').bind(day, q, source).run();
    if (Math.random() < 0.05) {
      await db.prepare('DELETE FROM search_miss WHERE day < ?1').bind(new Date(Date.now() - KEEP_DAYS * 86400000).toISOString().slice(0, 10)).run();
    }
  } catch (e) {}
  return ok;
}
