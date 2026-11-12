"""Minimal robots.txt matcher with Google-style wildcards (* and $) and longest-match-wins.

urllib.robotparser treats '*' literally, so rules like `Disallow: /*?page=` would be ignored.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse


def _pattern(rule: str) -> re.Pattern:
    anchored = rule.endswith("$")
    body = re.escape(rule[:-1] if anchored else rule).replace(r"\*", ".*")
    return re.compile("^" + body + ("$" if anchored else ""))


class RobotsRules:
    def __init__(self, allow_all: bool = False, disallow_all: bool = False):
        self.allow_all, self.disallow_all = allow_all, disallow_all
        self._rules: list[tuple[re.Pattern, int, bool]] = []  # (pattern, length, is_allow)
        self.crawl_delay: float = 0.0  # seconds the shop asks for between requests

    @classmethod
    def parse(cls, text: str, agent: str) -> "RobotsRules":
        agent = agent.lower().split("/")[0]
        groups: list[tuple[list[str], list[tuple[str, str]]]] = []
        agents: list[str] = []
        rules: list[tuple[str, str]] = []
        in_rules = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, val = (x.strip() for x in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if in_rules:
                    groups.append((agents, rules))
                    agents, rules, in_rules = [], [], False
                agents.append(val.lower())
            elif key in ("allow", "disallow"):
                in_rules = True
                rules.append((key, val))
            elif key == "crawl-delay":
                in_rules = True
                rules.append((key, val))
        groups.append((agents, rules))
        specific = [g for g in groups if any(a != "*" and a in agent for a in g[0])]
        chosen = specific or [g for g in groups if "*" in g[0]]
        r = cls()
        for _, rs in chosen:
            for kind, val in rs:
                if kind == "crawl-delay":
                    try:
                        r.crawl_delay = max(r.crawl_delay, min(float(val), 60.0))
                    except ValueError:
                        pass
                    continue
                if val:  # empty Disallow = allow everything
                    r._rules.append((_pattern(val), len(val), kind == "allow"))
        return r

    def can_fetch(self, url: str) -> bool:
        if self.disallow_all:
            return False
        if self.allow_all:
            return True
        p = urlparse(url)
        target = (p.path or "/") + (f"?{p.query}" if p.query else "")
        best: tuple[int, bool] | None = None
        for pat, length, is_allow in self._rules:
            if pat.match(target) and (best is None or length > best[0] or (length == best[0] and is_allow)):
                best = (length, is_allow)
        return True if best is None else best[1]
