"""Parse access logs in the combined log format used by nginx, Apache and most CDNs."""
from __future__ import annotations

import gzip
import re
import sys
from datetime import datetime
from typing import Iterator, NamedTuple, Optional
from urllib.parse import parse_qs, urlsplit

from .agents import UTM_SOURCES, Agent, classify, referrer_engine

LINE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] '
    r'"(?P<method>[A-Z]+) (?P<target>\S+)[^"]*" (?P<status>\d{3}) \S+'
    r'(?: "(?P<referrer>[^"]*)" "(?P<ua>[^"]*)")?'
)
ASSETS = re.compile(
    r"\.(?:css|js|mjs|map|png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|eot|mp4|webm|json|xml|txt)$",
    re.IGNORECASE,
)


class Hit(NamedTuple):
    when: datetime
    path: str
    status: int
    agent: Optional[Agent]  # None means not an AI related agent
    referral: Optional[str]  # engine id when a person arrived from an AI answer
    is_asset: bool


def normalize(path: str) -> str:
    """Drop the trailing slash so /blog/ and /blog count as one page."""
    if len(path) > 1 and path.endswith("/"):
        return path[:-1]
    return path or "/"


def parse_line(line: str) -> Optional[Hit]:
    m = LINE.match(line)
    if not m:
        return None
    try:
        when = datetime.strptime(m["ts"], "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None
    target = urlsplit(m["target"])
    path = normalize(target.path)
    agent = classify(m["ua"] or "")
    referral = None
    if agent is None:
        ref = m["referrer"] or ""
        if ref not in ("", "-"):
            referral = referrer_engine(urlsplit(ref).netloc)
        if referral is None and target.query:
            for source in parse_qs(target.query).get("utm_source", ()):
                referral = referral or UTM_SOURCES.get(source.lower())
    return Hit(when, path, int(m["status"]), agent, referral, bool(ASSETS.search(path)))


def open_log(name: str):
    if name == "-":
        return sys.stdin
    if name.endswith(".gz"):
        return gzip.open(name, "rt", encoding="utf-8", errors="replace")
    return open(name, "r", encoding="utf-8", errors="replace")


def read(names: list[str], assets: bool = False) -> Iterator[Hit]:
    """Yield hits from every file. Static assets are skipped unless asked for."""
    for name in names:
        handle = open_log(name)
        try:
            for line in handle:
                hit = parse_line(line)
                if hit and (assets or not hit.is_asset):
                    yield hit
        finally:
            if handle is not sys.stdin:
                handle.close()
