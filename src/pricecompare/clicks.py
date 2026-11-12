"""Private "Go to shop" click report for the owner (plan 2.5).

The counts live in the Cloudflare D1 database `derbani-clicks` (written by worker/index.js: day, shop, product,
app or site, count; nothing personal). This reads them through the Cloudflare API and writes a short Markdown
report. It runs nightly in the PRIVATE project only (the run page is private); the public runner copy refuses it,
so click numbers never appear in public logs. Shop-facing reports come later, when the owner starts charging.

Product 0 is not a real product (the first test click on 2026-11-12) and is left out.
"""
from __future__ import annotations

import csv
import io
import os
from collections import defaultdict
from datetime import date, timedelta

import httpx

DATABASE_ID = "0952643a-c495-42eb-abaa-f56608fe11d1"
API = "https://price-compare-jo-api.onrender.com"
PUBLIC_RUNNER = "data-jobs"


def fetch_rows(token: str, account: str, client: httpx.Client | None = None) -> list[dict]:
    c = client or httpx.Client(timeout=60)
    r = c.post(f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{DATABASE_ID}/query",
               headers={"Authorization": f"Bearer {token}"},
               json={"sql": "SELECT day, shop, product, source, n FROM clicks WHERE product > 0 ORDER BY day"})
    if "no such table" in r.text:  # no click yet since the counter went live
        return []
    r.raise_for_status()
    body = r.json()
    if not body.get("success"):
        raise RuntimeError(f"Cloudflare D1 query failed: {body.get('errors')}")
    return body["result"][0]["results"]


def product_names(ids: list[int], client: httpx.Client | None = None) -> dict[int, str]:
    """Names from the public price API; a product that has since gone shows as its number."""
    if not ids:
        return {}
    c = client or httpx.Client(timeout=90)
    names: dict[int, str] = {}
    for i in range(0, len(ids), 100):
        try:
            r = c.get(f"{API}/variants", params={"ids": ",".join(map(str, ids[i:i + 100]))})
            r.raise_for_status()
            names.update({p["id"]: p["label"] for p in r.json()["results"]})
        except Exception:
            pass
    return names


def report(rows: list[dict], names: dict[int, str], today: date) -> str:
    def total(since: date | None = None, **match) -> int:
        return sum(r["n"] for r in rows if (since is None or r["day"] >= since.isoformat())
                   and all(r[k] == v for k, v in match.items()))

    d7, d30 = today - timedelta(days=6), today - timedelta(days=29)
    out = [f"# Go to shop clicks (private) — {today.isoformat()}", ""]
    if not rows:
        return "\n".join(out + ["No clicks counted yet."]) + "\n"
    first = rows[0]["day"]
    out += [f"Counting since {first}. Bots are not counted; nothing personal is stored.", "",
            "| | Today | Last 7 days | Last 30 days | All time |", "|---|---:|---:|---:|---:|"]
    for label, m in (("All", {}), ("App", {"source": "app"}), ("Website", {"source": "site"})):
        out.append(f"| {label} | {total(today, **m)} | {total(d7, **m)} | {total(d30, **m)} | {total(None, **m)} |")

    by_shop: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    by_product: dict[int, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    for r in rows:
        s = by_shop[r["shop"]]
        s[2] += r["n"]
        if r["day"] >= d30.isoformat():
            s[1] += r["n"]
            by_product[r["product"]] += r["n"]
        if r["day"] >= d7.isoformat():
            s[0] += r["n"]
        by_day[r["day"]] += r["n"]
    out += ["", "## By shop", "", "| Shop | Last 7 days | Last 30 days | All time |", "|---|---:|---:|---:|"]
    out += [f"| {shop} | {a} | {b} | {c} |" for shop, (a, b, c) in sorted(by_shop.items(), key=lambda x: (-x[1][1], -x[1][2], x[0]))]
    out += ["", "## Top products (last 30 days)", "", "| Product | Clicks |", "|---|---:|"]
    out += [f"| {names.get(p, f'#{p}')} | {n} |" for p, n in sorted(by_product.items(), key=lambda x: (-x[1], x[0]))[:20]]
    out += ["", "## Last 14 days", "", "| Day | Clicks |", "|---|---:|"]
    out += [f"| {d} | {by_day.get(d, 0)} |" for d in ((today - timedelta(days=i)).isoformat() for i in range(14))]
    return "\n".join(out) + "\n"


def to_csv(rows: list[dict]) -> str:
    f = io.StringIO()
    w = csv.DictWriter(f, fieldnames=["day", "shop", "product", "source", "n"])
    w.writeheader()
    w.writerows(rows)
    return f.getvalue()


def main(csv_path: str | None = None) -> None:
    if os.environ.get("GITHUB_REPOSITORY", "").endswith("/" + PUBLIC_RUNNER):
        raise SystemExit("the click report is private: it never runs in the public runner copy")
    token, account = os.environ.get("CLOUDFLARE_API_TOKEN"), os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not token or not account:
        raise SystemExit("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are needed")
    rows = fetch_rows(token, account)
    text = report(rows, product_names(sorted({r["product"] for r in rows})), date.today())
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text)
    if csv_path:  # the raw counts, kept as a private backup next to the database backup
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            f.write(to_csv(rows))
