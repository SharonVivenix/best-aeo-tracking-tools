"""
Command line entry point.

    python -m aeolog access.log                       # hits per AI agent
    python -m aeolog access.log --by purpose          # training, search, user
    python -m aeolog access.log --by path --top 15    # where the agents spend requests
    python -m aeolog access.log --funnel --cited cited.csv
    python -m aeolog access.log --gaps --cited cited.csv
    python -m aeolog --agents                         # print the registry
    zcat access.log.*.gz | python -m aeolog -         # read stdin
"""
from __future__ import annotations

import argparse
import json
import sys

from .agents import AGENTS
from .parse import read
from .report import Log, load_cited

HEADERS = {
    "agent": ["agent", "vendor", "purpose", "hits", "pages", "errors", "last seen"],
    "purpose": ["purpose", "hits", "pages", "errors"],
    "path": ["path", "training", "search", "user", "errors", "ai clicks"],
    "funnel": ["engine", "pages", "indexed", "fetched live", "cited", "clicked"],
    "gaps": ["gap", "path", "who", "evidence"],
    "agents": ["token", "vendor", "engine", "purpose"],
}


def table(header: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "nothing to report"
    widths = [max(len(str(r[i])) for r in [header] + rows) for i in range(len(header))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*header), "  ".join("-" * w for w in widths)]
    lines += [fmt.format(*r) for r in rows]
    return "\n".join(line.rstrip() for line in lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aeolog", description="AI crawler and AI referral report from access logs.")
    ap.add_argument("logs", nargs="*", help="log files, .gz accepted, - for stdin")
    ap.add_argument("--by", choices=["agent", "purpose", "path"], default="agent")
    ap.add_argument("--funnel", action="store_true", help="pages per stage, per engine")
    ap.add_argument("--gaps", action="store_true", help="list pages that fall out between stages")
    ap.add_argument("--cited", metavar="CSV", help="citation export with url, engine, citations")
    ap.add_argument("--min-fetches", type=int, default=5, help="live fetches before a page counts as read")
    ap.add_argument("--top", type=int, default=20, help="rows for --by path")
    ap.add_argument("--assets", action="store_true", help="include css, js and image requests")
    ap.add_argument("--agents", action="store_true", help="print the agent registry and exit")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 when --gaps finds a blocked page")
    a = ap.parse_args(argv)

    if a.agents:
        view, rows = "agents", [[x.token, x.vendor, x.engine or "none", x.purpose] for x in AGENTS]
    else:
        if not a.logs:
            ap.error("give at least one log file, or - for stdin")
        log = Log(read(a.logs, assets=a.assets))
        if not log.lines:
            print("no parseable lines, is this a combined format access log?", file=sys.stderr)
            return 2
        cited = load_cited(a.cited) if a.cited else None
        if a.gaps:
            view, rows = "gaps", log.gaps(cited, a.min_fetches)
        elif a.funnel:
            view, rows = "funnel", log.funnel(cited)
        else:
            view = a.by
            rows = {"agent": log.by_agent, "purpose": log.by_purpose,
                    "path": lambda: log.by_path(a.top)}[view]()
        if not a.json:
            print(f"{log.lines:,} requests, {log.first:%Y-%m-%d} to {log.last:%Y-%m-%d}\n")

    if a.json:
        print(json.dumps([dict(zip(HEADERS[view], r)) for r in rows], indent=2))
    else:
        print(table(HEADERS[view], rows))
    if a.strict and view == "gaps" and any(r[0] == "blocked" for r in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
