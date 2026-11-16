#!/usr/bin/env python3
"""
Regenerate the README tables from tools.yaml.

    python render_table.py                     # print both tables
    python render_table.py --write             # rewrite the blocks between the markers
    python render_table.py --check             # exit 1 if README and YAML disagree
    python render_table.py --need crawl,answer # tools that cover every tap you name

Every tool measures at one or more taps along the path from crawl to click.
The "Blind to" column and the coverage table are derived from `taps`, so a
tool can never claim a tap in one table and miss it in the other.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
README = ROOT / "README.md"

TAPS = {
    "crawl": "AI agent requests in your server logs",
    "fanout": "Sub queries the engine runs before answering",
    "answer": "Mentions and citations in the generated answer",
    "click": "Visits arriving from an AI answer",
}


def load(path: Path = ROOT / "tools.yaml") -> list[dict]:
    tools = yaml.safe_load(path.read_text(encoding="utf-8"))
    for t in tools:
        unknown = set(t["taps"]) - set(TAPS)
        if unknown or not t["taps"]:
            raise SystemExit(f"{t['id']}: taps must be a non empty subset of {list(TAPS)}, got {t['taps']}")
    return tools


def blind_to(t: dict) -> list[str]:
    return [tap for tap in TAPS if tap not in t["taps"]]


def price_cell(t: dict) -> str:
    note = t.get("price_note")
    if t["price"] is None:
        return note or "Not published"
    base = "Free" if t["price"] == 0 else f"{t['currency']}{t['price']:,}/mo"
    return f"{base}, {note}" if note else base


def _table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def matrix(tools: list[dict]) -> str:
    header = ["Tool", "Taps", "Blind to", "How it captures", "Engines", "Entry price",
              "Entry volume", "Developer surface"]
    rows = [[f"[{t['name']}]({t['url']})",
             ", ".join(tap for tap in TAPS if tap in t["taps"]),
             ", ".join(blind_to(t)) or "nothing",
             t["capture"], t["engines"], price_cell(t), t["volume"], t["dev"]]
            for t in tools]
    return _table(header, rows)


def coverage(tools: list[dict]) -> str:
    header = ["Tap", "What is measured", "Tools", "Count"]
    rows = []
    for tap, what in TAPS.items():
        names = [t["name"] for t in tools if tap in t["taps"]]
        rows.append([f"`{tap}`", what, ", ".join(names), f"{len(names)} of {len(tools)}"])
    return _table(header, rows)


BLOCKS = {"TABLE": matrix, "COVERAGE": coverage}


def splice(text: str, name: str, body: str) -> str:
    start, end = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    a, b = text.index(start) + len(start), text.index(end)
    return text[:a] + "\n" + body + "\n" + text[b:]


def need(tools: list[dict], wanted: list[str]) -> int:
    unknown = set(wanted) - set(TAPS)
    if unknown:
        print(f"unknown tap {sorted(unknown)}, choose from {list(TAPS)}", file=sys.stderr)
        return 2
    fit = [t for t in tools if set(wanted) <= set(t["taps"])]
    fit.sort(key=lambda t: (t["price"] is None, t["price"] or 0))
    for t in fit:
        print(f"{t['name']:<30} {price_cell(t):<32} taps: {', '.join(t['taps'])}")
    if not fit:
        print("no single tool covers all of those taps, combine two")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--need", metavar="TAPS", help="comma separated taps, for example crawl,answer")
    a = ap.parse_args(argv)
    tools = load()

    if a.need:
        return need(tools, [x.strip() for x in a.need.split(",") if x.strip()])

    if not (a.write or a.check):
        for name, fn in BLOCKS.items():
            print(f"{name}\n{fn(tools)}\n")
        return 0

    text = README.read_text(encoding="utf-8")
    new = text
    for name, fn in BLOCKS.items():
        new = splice(new, name, fn(tools))
    if a.check:
        if new != text:
            print("README tables are stale, run: python render_table.py --write", file=sys.stderr)
            return 1
        print("README tables match tools.yaml")
        return 0
    README.write_text(new, encoding="utf-8", newline="\n")
    print("README tables updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
