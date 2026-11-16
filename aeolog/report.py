"""Aggregate hits into the views the CLI prints."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from typing import Iterable, Optional
from urllib.parse import urlsplit

from .agents import AGENTS, BY_TOKEN, PURPOSES, RETRIEVAL
from .parse import Hit, normalize

# Engines that publish both a search agent and a user agent, so a funnel makes sense.
FUNNEL_ENGINES = tuple(
    e for e in dict.fromkeys(a.engine for a in AGENTS if a.engine)
    if {"search", "user"} <= {a.purpose for a in AGENTS if a.engine == e}
)


def ok(status: int) -> bool:
    return 200 <= status < 400


class Log:
    """Everything the reports need, built in one pass over the hits."""

    def __init__(self, hits: Iterable[Hit]):
        self.agent_hits: Counter = Counter()                 # token -> hits
        self.agent_errors: Counter = Counter()               # token -> 4xx and 5xx
        self.agent_paths: dict = defaultdict(set)            # token -> paths
        self.agent_last: dict = {}                           # token -> datetime
        self.path_agent_status: dict = defaultdict(Counter)  # (path, token) -> status -> n
        self.referrals: dict = defaultdict(Counter)          # path -> engine -> n
        self.human_paths: set = set()
        self.first = self.last = None
        self.lines = 0
        for h in hits:
            self.lines += 1
            if self.first is None or h.when < self.first:
                self.first = h.when
            if self.last is None or h.when > self.last:
                self.last = h.when
            if h.agent is None:
                if ok(h.status):
                    self.human_paths.add(h.path)
                if h.referral:
                    self.referrals[h.path][h.referral] += 1
                continue
            t = h.agent.token
            self.agent_hits[t] += 1
            self.agent_paths[t].add(h.path)
            self.path_agent_status[(h.path, t)][h.status] += 1
            if not ok(h.status):
                self.agent_errors[t] += 1
            if t not in self.agent_last or h.when > self.agent_last[t]:
                self.agent_last[t] = h.when

    # -- lookups ----------------------------------------------------------

    def fetched_ok(self, path: str, engine: str, purpose: str) -> int:
        """Successful fetches of a path by one engine's agents of one purpose."""
        return sum(
            n
            for a in AGENTS if a.engine == engine and a.purpose == purpose
            for status, n in self.path_agent_status.get((path, a.token), {}).items() if ok(status)
        )

    def paths(self) -> set:
        return self.human_paths | {p for p, _ in self.path_agent_status}

    # -- views ------------------------------------------------------------

    def by_agent(self) -> list[list[str]]:
        rows = []
        for a in AGENTS:
            n = self.agent_hits[a.token]
            if not n:
                continue
            err = self.agent_errors[a.token]
            rows.append([a.token, a.vendor, a.purpose, str(n), str(len(self.agent_paths[a.token])),
                         f"{100 * err / n:.1f}%", self.agent_last[a.token].strftime("%Y-%m-%d")])
        return rows

    def by_purpose(self) -> list[list[str]]:
        rows = []
        for purpose in PURPOSES:
            tokens = [a.token for a in AGENTS if a.purpose == purpose]
            n = sum(self.agent_hits[t] for t in tokens)
            err = sum(self.agent_errors[t] for t in tokens)
            pages = set().union(*(self.agent_paths[t] for t in tokens))
            rows.append([purpose, str(n), str(len(pages)), f"{100 * err / n:.1f}%" if n else "n/a"])
        return rows

    def by_path(self, top: int) -> list[list[str]]:
        rows = []
        for path in self.paths():
            counts: Counter = Counter()
            errors = 0
            for a in AGENTS:
                for status, n in self.path_agent_status.get((path, a.token), {}).items():
                    counts[a.purpose] += n
                    errors += 0 if ok(status) else n
            clicks = sum(self.referrals[path].values()) if path in self.referrals else 0
            total = sum(counts.values()) + clicks
            if total:
                rows.append((total, [path, str(counts["training"]), str(counts["search"]),
                                     str(counts["user"]), str(errors), str(clicks)]))
        rows.sort(key=lambda r: (-r[0], r[1][0]))
        return [r for _, r in rows[:top]]

    def funnel(self, cited: Optional[dict]) -> list[list[str]]:
        """Pages per stage for each engine that publishes search and user agents."""
        universe = self.paths()
        rows = []
        for engine in FUNNEL_ENGINES:
            indexed = {p for p in universe if self.fetched_ok(p, engine, "search")}
            live = {p for p in universe if self.fetched_ok(p, engine, "user")}
            clicked = {p for p, c in self.referrals.items() if c[engine]}
            if not (indexed or live or clicked):
                continue
            n_cited = str(len(cited.get(engine, {}))) if cited is not None else "n/a"
            rows.append([engine, str(len(universe)), str(len(indexed)), str(len(live)),
                         n_cited, str(len(clicked))])
        return rows

    def gaps(self, cited: Optional[dict], min_fetches: int = 5) -> list[list[str]]:
        out = []
        # 1. retrieval agents that never got a successful response for a page
        for (path, token), statuses in sorted(self.path_agent_status.items()):
            bad = {s: n for s, n in statuses.items() if not ok(s)}
            if BY_TOKEN[token].purpose in RETRIEVAL and bad and len(bad) == len(statuses):
                worst = max(bad, key=bad.get)
                out.append(["blocked", path, token,
                            f"{sum(bad.values())} failed, 0 succeeded, mostly {worst}"])
        # 2. pages people load that no search agent has requested
        seen_by_search = {p for (p, t) in self.path_agent_status if BY_TOKEN[t].purpose == "search"}
        for path in sorted(self.human_paths - seen_by_search):
            out.append(["not indexed", path, "all search agents", "people load it, no search agent has"])
        if cited is None:
            return out
        # 3 and 4 need a citation export
        for engine in FUNNEL_ENGINES:
            cites = cited.get(engine, {})
            for path in sorted(self.paths()):
                live = self.fetched_ok(path, engine, "user")
                if live >= min_fetches and path not in cites:
                    out.append(["read, not cited", path, engine, f"{live} live fetches, 0 citations"])
            for path, n in sorted(cites.items()):
                reached = self.fetched_ok(path, engine, "search") + self.fetched_ok(path, engine, "user")
                if not reached:
                    out.append(["cited, no fetch", path, engine,
                                f"{n} citations, no successful fetch in this log window"])
        return out


def load_cited(name: str) -> dict:
    """Read a citation export with url, engine and citations columns.

    Returns engine -> path -> citations. Any tracker export works after a
    column rename. A missing citations column counts each row as one.
    """
    cited: dict = defaultdict(Counter)
    with open(name, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            n = int(float(row.get("citations") or 1))
            if n > 0:
                path = normalize(urlsplit(row["url"].strip()).path)
                cited[row["engine"].strip().lower()][path] += n
    return {engine: dict(paths) for engine, paths in cited.items()}
