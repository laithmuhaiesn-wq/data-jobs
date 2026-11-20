"""The scheduled jobs, run on the owner's PC (2026-11-17: moved off GitHub + Neon, whose free 5 GB a month ran out).

Same steps as the old GitHub workflows, against the PostgreSQL on this PC. Windows Task Scheduler starts them with
pythonw (no window): `pythonw -m pricecompare.pc_jobs hourly`. One copy of a job at a time (a lock file); every
job first makes sure the database is running. Logs: logs/jobs-<job>-<date>.log, kept 14 days.

    hourly       20 shops, match new listings, (every 6 h) grow the catalog, build + publish derbani.com, (every 3 h) health
    fast         Action, every 3 h
    slow         iService, Leaders, Platinum (+ their electronics), every 4 h
    electronics  the electronics sections of 20 shops, six at a time, every 6 h
    nightly      night shops, full matching, catalog growth, report, smoke test, backup, click report
    start        start the database (at logon)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME = Path.home() / ".derbani"
# Database, its tools and the tunnel program. NOT under AppData: the Claude desktop app keeps a private copy of
# AppData\Local, so files put there from a Claude session are invisible to Windows' own scheduled tasks (2026-11-17).
PG = Path.home() / "derbani-server"
PG_BIN, PG_DATA = PG / "pgsql" / "bin", PG / "data"
PY = Path(sys.executable).with_name("python.exe") if os.name == "nt" else Path(sys.executable)
# the API runs for days: the windowless interpreter, because the venv's python.exe starts the real one as a child that
# would get a console window of its own (Windows Terminal) even when the parent is started without one
PYW = Path(sys.executable).with_name("pythonw.exe") if os.name == "nt" else Path(sys.executable)
NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: nothing pops up on the owner's screen
LOGS = ROOT / "logs"
BACKUPS = HOME / "backups"

HOURLY = ("smartbuy estorejo gts citycenter ammar igeek xmart dna compujordan newvision cse midteks osjo smartsystems "
          "almohanad pccircle h4m newton profpc alruwwad bci numberone").split()
ELECTRONICS = ("smartbuy estorejo gts ammar igeek xmart dna compujordan newvision cse midteks osjo smartsystems "
               "almohanad pccircle h4m profpc alruwwad action alaryan bci numberone").split()
SHOPIFY = {"smartbuy", "igeek", "estorejo", "xmart", "dna"}
SLOW, SLOW_ELECTRONICS = ["iservice", "leaders", "platinum"], ["iservice", "platinum"]
NIGHTLY = ["iservice", "leaders", "platinum", "alaryan", "darwish"]


class Job:
    def __init__(self, name: str):
        self.name, self.failed = name, []
        LOGS.mkdir(exist_ok=True)
        self.log = (LOGS / f"jobs-{name}-{datetime.now():%Y-%m-%d}.log").open("a", encoding="utf-8")

    def say(self, text: str) -> None:
        self.log.write(f"{datetime.now():%H:%M:%S} {text}\n")
        self.log.flush()

    def run(self, *args: str, label: str = "", timeout: int = 3600) -> bool:
        if args[0].endswith((".exe", ".cmd")):
            cmd = list(args)
        elif args[0].endswith(".py"):
            cmd = [str(PY), *args]
        else:
            cmd = [str(PY), "-m", "pricecompare.cli", *args]
        self.say(f"== {label or ' '.join(args)}")
        try:
            r = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout, creationflags=NO_WINDOW,
                               env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            self.log.write(r.stdout[-20000:])
            ok = r.returncode == 0
        except subprocess.TimeoutExpired:
            ok = False
            self.say("timed out")
        if not ok:
            self.failed.append(label or " ".join(args))
            self.say("FAILED")
        return ok

    def collect_one(self, shop: str, extra: list[str], part: str) -> None:
        if shop not in SHOPIFY:
            self.run("collect", shop, *extra, label=f"collect {shop} {part}")
            return
        with shopify_turn(self):  # one Shopify shop at a time across ALL jobs (hourly and electronics overlap)
            self.run("collect", shop, *extra, label=f"collect {shop} {part}")

    def collect(self, shops: list[str], part: str = "main", parallel: int = 1) -> None:
        extra = [] if part == "main" else ["--part", part]
        if parallel <= 1:
            for s in shops:
                self.collect_one(s, extra, part)
            return
        # Shopify counts requests per visitor address across ALL its shops: from one home connection, Shopify shops
        # read side by side get "slow down" (429, 2026-11-17). They share one lane, one after another; others run
        # side by side (each shop still waits its polite 3 s between its own requests).
        lanes = [[s] for s in shops if s not in SHOPIFY] + ([[s for s in shops if s in SHOPIFY]] if set(shops) & SHOPIFY else [])
        with ThreadPoolExecutor(parallel) as ex:
            list(ex.map(lambda lane: [self.collect_one(s, extra, part) for s in lane], lanes))

    def restore_ids(self) -> None:
        """Until the site is switched back on after the move (publish-ok), listings seen for the first time get their
        product's OLD id back before matching, so late shops keep their old addresses too (scripts/restore_ids.py)."""
        old = HOME / "old_products.json"
        if not (HOME / "publish-ok").exists() and old.exists():
            self.run("scripts/restore_ids.py", str(old), label="restore old product ids")
            self.run("scripts/restore_offer_ids.py", str(old), label="restore old listing numbers (shop links)")

    def publish(self) -> None:
        # A fresh database fills over a night or two (the catalog grows from the shops). Until then the site keeps its
        # last full copy: publishing a half-empty site would take thousands of pages off search engines.
        if not (HOME / "publish-ok").exists():
            reason = ready_to_publish()
            if not reason:
                self.say("publishing is off until ~/.derbani/publish-ok exists (or 95% of the old site is back)")
                return
            (HOME / "publish-ok").write_text(reason)
            self.say(f"publishing switched on: {reason}")
        if not self.run("build-web"):
            return
        self.run("indexnow-prepare")
        npx = r"C:\Program Files\nodejs\npx.cmd" if os.name == "nt" else "npx"
        if self.run(npx, "--yes", "wrangler@4", "deploy", label="publish kamkam.derbani.com", timeout=900):
            self.run("indexnow-send")


def database_up() -> bool:
    r = subprocess.run([str(PG_BIN / "pg_isready.exe"), "-h", "localhost", "-p", "5432", "-q"], creationflags=NO_WINDOW)
    return r.returncode == 0


def start_database(job: Job) -> None:
    if database_up():
        return
    job.say("starting the database")
    # Popen, not run: pg_ctl hands the server off and returns; nothing waits on its output
    subprocess.Popen([str(PG_BIN / "pg_ctl.exe"), "-D", str(PG_DATA), "-l", str(PG / "start.log"), "start"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                     creationflags=NO_WINDOW | 0x00000200)  # + CREATE_NEW_PROCESS_GROUP: survives this job ending
    for _ in range(60):
        if database_up():
            return
        time.sleep(1)
    raise SystemExit("database did not start")


API_PORT = 8787  # the live API on this PC; Cloudflare Tunnel "derbani-pc" serves it as https://api.derbani.com


def _detached(cmd: list[str], log: Path, env: dict | None = None) -> None:
    subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log.open("a", encoding="utf-8"), stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, creationflags=NO_WINDOW | 0x00000200 | 0x00000008)  # + DETACHED_PROCESS


def start_services(job: Job) -> None:
    """The live API and the tunnel to it: started when not running (at logon, and checked again by every job)."""
    import httpx
    try:
        httpx.get(f"http://127.0.0.1:{API_PORT}/health", timeout=20).raise_for_status()
    except Exception:
        job.say("starting the API")
        # the public API reads with its own read-only login (security check 2026-11-20); the full login stays with the jobs
        ro = HOME / "api_database_url.txt"
        env = {**os.environ, "DATABASE_URL": ro.read_text().strip()} if ro.exists() else None
        _detached([str(PYW), "-m", "uvicorn", "pricecompare.api.app:create_app", "--factory", "--host", "127.0.0.1",
                   "--port", str(API_PORT), "--proxy-headers", "--no-access-log"], LOGS / "api.log", env)
    running = subprocess.run(["tasklist", "/FI", "IMAGENAME eq cloudflared.exe"], capture_output=True, text=True,
                             creationflags=NO_WINDOW).stdout
    token = HOME / "tunnel_token.txt"
    if "cloudflared.exe" not in running and token.exists():
        job.say("starting the tunnel")
        _detached([str(PG / "cloudflared.exe"), "tunnel", "--no-autoupdate", "run", "--token", token.read_text().strip()],
                  LOGS / "tunnel.log")


def backup(job: Job) -> None:
    """Nightly dump on this PC (14 kept) and a copy off the PC: a release asset in the PRIVATE GitHub project."""
    BACKUPS.mkdir(parents=True, exist_ok=True)
    out = BACKUPS / f"derbani-{datetime.now():%Y-%m-%d}.dump"
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    if not job.run(str(PG_BIN / "pg_dump.exe"), "-Fc", "--no-owner", "--no-privileges", "-f", str(out), url, label="backup"):
        return
    if out.stat().st_size < 20000:
        job.failed.append("backup too small")
        return
    for old in sorted(BACKUPS.glob("derbani-*.dump"))[:-14]:
        old.unlink()
    gh = r"C:\Program Files\GitHub CLI\gh.exe"
    repo = "laithmuhaiesn-wq/price-compare-jo-pilot"
    if Path(gh).exists():
        subprocess.run([gh, "release", "create", "db-backups", "-R", repo, "--title", "Database backups (private)",
                        "--notes", "Nightly database dumps from the owner's PC. Newest 14 kept."],
                       capture_output=True, creationflags=NO_WINDOW)
        job.run(gh, "release", "upload", "db-backups", str(out), "--clobber", "-R", repo, label="backup off the PC")
        r = subprocess.run([gh, "release", "view", "db-backups", "-R", repo, "--json", "assets", "-q", ".assets[].name"],
                           capture_output=True, text=True, creationflags=NO_WINDOW)
        for name in sorted(n for n in r.stdout.split() if n.startswith("derbani-"))[:-14]:
            subprocess.run([gh, "release", "delete-asset", "db-backups", name, "-R", repo, "-y"],
                           capture_output=True, creationflags=NO_WINDOW)


@contextmanager
def shopify_turn(job: "Job", wait_max: float = 3 * 3600):
    """A lock file shared by every job: two jobs reading Shopify shops at once from one home address get 429s.
    A lock older than 2 h is left over from a crash and is taken over."""
    lock = LOGS / ".shopify-lane"
    LOGS.mkdir(exist_ok=True)
    start = time.monotonic()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, job.name.encode())
            os.close(fd)
            break
        except FileExistsError:
            if time.time() - lock.stat().st_mtime > 2 * 3600 or time.monotonic() - start > wait_max:
                lock.unlink(missing_ok=True)
                continue
            time.sleep(15)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


SWITCH_ON_BY = datetime(2026, 11, 21, tzinfo=timezone.utc)  # the shops resting since 17 Nov are back by then


def ready_to_publish() -> str:
    """Publishing switches itself on when 95% of the products on the live site are back in the PC database (same
    ids, so same links), or on 21 Nov in any case: by then every resting shop has been read again, and what is still
    missing has left the shops. Returns the reason, or "" while not ready."""
    import json

    from pricecompare.db.session import get_engine, make_session
    from pricecompare.views import build_variant_data

    if datetime.now(timezone.utc) >= SWITCH_ON_BY:
        return "21 Nov reached"
    old_file = HOME / "old_products.json"
    if not old_file.exists():
        return ""
    old = {p["id"] for p in json.loads(old_file.read_text(encoding="utf-8"))["results"]}
    with make_session(get_engine()) as s:
        new = {v["id"] for v in build_variant_data(s)}
    share = len(old & new) / max(len(old), 1)
    return f"{share:.0%} of the old site's products are back" if share >= 0.95 else ""


def every(hours: int) -> bool:
    return datetime.now(timezone.utc).hour % hours == 0


def main(name: str) -> int:
    job = Job(name)
    lock = LOGS / f".lock-{name}"
    if lock.exists() and time.time() - lock.stat().st_mtime < 3 * 3600:
        job.say("still running from before: skipped")
        return 0
    lock.write_text(str(os.getpid()))
    started = time.time()
    try:
        start_database(job)
        start_services(job)
        if name == "start":
            return 0
        if name == "hourly":
            # Shopify shops are read every 3 hours, 30 s between requests (Shopify's limit for a home connection)
            job.collect([s for s in HOURLY if s not in SHOPIFY or every(3)])
            job.restore_ids()
            job.run("match-new")
            if every(6):
                job.run("auto-grow", "--match")
            job.publish()
            if every(3):
                job.run("push-health")
        elif name == "fill":  # once, into an empty database: every shop and section, six shops at a time, no matching
            job.collect(sorted(set(HOURLY + ["action"] + SLOW + NIGHTLY)), parallel=6)
            job.collect(sorted(set(ELECTRONICS + SLOW_ELECTRONICS)), part="electronics", parallel=6)
        elif name == "fast":
            job.collect(["action"])
            job.restore_ids()
            job.run("match-new")
        elif name == "slow":
            job.collect(SLOW)
            job.collect(SLOW_ELECTRONICS, part="electronics")
            job.restore_ids()
            job.run("match-new")
        elif name == "electronics":
            # Shopify shops are not here: their whole catalogue comes in one list with the hourly "main" read
            job.collect([s for s in ELECTRONICS if s not in SHOPIFY], part="electronics", parallel=6)
            job.restore_ids()
            job.run("match-new")
        elif name == "nightly":
            job.collect(NIGHTLY)
            job.run("seed-catalog")
            job.restore_ids()
            job.run("auto-grow")
            job.run("match")
            job.run("report")
            job.run("fix-images")  # pictures visitors could not load: dropped, new ones from the shop pages
            job.run("deal-cards")  # pictures for social media in ~/Derbani deal cards (nothing is posted)
            backup(job)
            (HOME / "clicks").mkdir(parents=True, exist_ok=True)
            job.run("clicks-report", "--csv", str(HOME / "clicks" / f"clicks-{datetime.now():%Y-%m-%d}.csv"))
            if datetime.now().day == 1:  # last month's report for each shop, in ~/Derbani shop reports (nothing is sent)
                job.run("shop-reports")
            for old in LOGS.glob("jobs-*.log"):  # logs older than 14 days go
                if time.time() - old.stat().st_mtime > 14 * 86400:
                    old.unlink()
        else:
            raise SystemExit(f"unknown job {name}")
    except BaseException as e:  # pythonw has no screen: the reason must reach the log
        import traceback
        job.say("CRASHED: " + "".join(traceback.format_exception(e))[-3000:])
        raise
    finally:
        job.say(f"done in {int(time.time() - started)} s; failed: {', '.join(job.failed) or 'nothing'}")
        lock.unlink(missing_ok=True)
    return 1 if job.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "hourly"))
