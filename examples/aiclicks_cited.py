#!/usr/bin/env python3
"""
Export your own cited pages from the AIclicks API into the CSV that aeolog joins.

    export AICLICKS_API_KEY=ak_live_...
    python examples/aiclicks_cited.py --domain-id <uuid> --days 14 > cited.csv
    python -m aeolog access.log --gaps --cited cited.csv

Uses GET /api/v1/citations as documented at https://docs.aiclicks.io/list-citations
with is_brand_owned=true, once per engine that publishes its own retrieval
agents. API access needs a Pro or Business plan. Find the domain id with
GET /api/v1/domains. Standard library only.

Any other tracker works too: export cited URLs and rename the columns to
url, engine, citations.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.aiclicks.io/api/v1"
# AIclicks channel name -> engine id used by aeolog
MODELS = {"ChatGPT": "chatgpt", "Claude": "claude", "Perplexity": "perplexity"}
PAGE_SIZE = 1000


def get(path: str, params: dict, key: str, retries: int = 3) -> dict:
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            if err.code == 429 and attempt < retries:
                time.sleep(int(err.headers.get("Retry-After", "5")))
                continue
            detail = err.read().decode("utf-8", "replace")
            raise SystemExit(f"{err.code} from {path}: {detail}")
    raise SystemExit("rate limited, try again later")


def rows_for(items: list[dict], engine: str) -> list[tuple[str, str, int]]:
    """Turn /citations items into (url, engine, citations) rows."""
    return [("https://" + it["url"], engine, int(it["frequency"])) for it in items if it.get("frequency")]


def export(domain_id: str, days: int, key: str, fetch=get) -> list[tuple[str, str, int]]:
    out = []
    for model, engine in MODELS.items():
        page = 1
        while True:
            body = fetch("/citations", {"domain_id": domain_id, "days": days, "model": model,
                                        "is_brand_owned": "true", "page": page, "size": PAGE_SIZE}, key)
            data = body["data"]
            out += rows_for(data["items"], engine)
            if page >= data.get("total_pages", 1):
                break
            page += 1
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--domain-id", required=True)
    ap.add_argument("--days", type=int, default=30, help="look back window, 1 to 365")
    a = ap.parse_args(argv)
    key = os.environ.get("AICLICKS_API_KEY")
    if not key:
        print("set AICLICKS_API_KEY first", file=sys.stderr)
        return 2
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["url", "engine", "citations"])
    writer.writerows(export(a.domain_id, a.days, key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
