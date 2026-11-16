#!/usr/bin/env python3
"""
Write examples/access.example.log and examples/cited.example.csv.

Fourteen days of synthetic traffic for a fictional site, seeded so the output
never changes. Four problems are planted on purpose and the tests look for them:

    /blog/aeo-checklist   a firewall rule answers Anthropic agents with 403
    /docs/api-reference   the page moved, every request gets 404, one engine still cites it
    /pricing              ChatGPT fetches it live every day and never cites it
    /changelog            people read it, no crawler has ever requested it

IP addresses come from the documentation ranges in RFC 5737.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
START = datetime(2026, 10, 1, tzinfo=timezone.utc)
DAYS = 14

PAGES = ["/", "/pricing", "/features", "/docs", "/docs/quickstart", "/docs/api-reference",
         "/blog", "/blog/compare-trackers", "/blog/aeo-checklist", "/blog/log-analysis",
         "/integrations", "/about"]
MOVED = "/docs/api-reference"
FIREWALLED = "/blog/aeo-checklist"

WEBKIT = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; {}; +{})"
UA = {
    "GPTBot": WEBKIT.format("GPTBot/1.2", "https://openai.com/gptbot"),
    "OAI-SearchBot": WEBKIT.format("OAI-SearchBot/1.0", "https://openai.com/searchbot"),
    "ChatGPT-User": WEBKIT.format("ChatGPT-User/1.0", "https://openai.com/bot"),
    "ClaudeBot": WEBKIT.format("ClaudeBot/1.0", "claudebot@anthropic.com"),
    "Claude-SearchBot": WEBKIT.format("Claude-SearchBot/1.0", "https://www.anthropic.com"),
    "Claude-User": WEBKIT.format("Claude-User/1.0", "Claude-User@anthropic.com"),
    "PerplexityBot": WEBKIT.format("PerplexityBot/1.0", "https://perplexity.ai/perplexitybot"),
    "Perplexity-User": WEBKIT.format("Perplexity-User/1.0", "https://perplexity.ai/perplexity-user"),
    "CCBot": "CCBot/2.0 (https://commoncrawl.org/faq/)",
    "Bytespider": "Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 (KHTML, like Gecko) Mobile Safari/537.36 (compatible; Bytespider; spider-feedback@bytedance.com)",
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "bingbot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm) Chrome/116.0.1938.76 Safari/537.36",
}
BROWSERS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/19.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0",
]
ANTHROPIC = ("ClaudeBot", "Claude-SearchBot", "Claude-User")

# crawler -> requests per day, spread over random pages
CRAWL_PER_DAY = {"GPTBot": 15, "OAI-SearchBot": 8, "ClaudeBot": 6, "Claude-SearchBot": 3,
                 "PerplexityBot": 6, "CCBot": 2, "Bytespider": 3, "Googlebot": 12, "bingbot": 6}
# user triggered agent -> (page, fetches per day)
LIVE_PER_DAY = {"ChatGPT-User": [("/pricing", 3), ("/blog/compare-trackers", 4), ("/features", 1)],
                "Claude-User": [("/docs/quickstart", 1), (FIREWALLED, 1)],
                "Perplexity-User": [("/blog/log-analysis", 2)]}
# (page, referrer, query string, clicks per day)
AI_CLICKS = [("/blog/compare-trackers", "https://chatgpt.com/", "", 3),
             ("/features", "-", "?utm_source=chatgpt.com", 1),
             ("/blog/log-analysis", "https://www.perplexity.ai/", "", 2),
             ("/docs/quickstart", "https://claude.ai/", "", 1)]

CITED = [("https://example.com/blog/compare-trackers", "chatgpt", 31),
         ("https://example.com/features", "chatgpt", 6),
         ("https://example.com/blog/compare-trackers", "perplexity", 9),
         ("https://example.com/blog/log-analysis", "perplexity", 22),
         ("https://example.com/docs/api-reference", "perplexity", 3),
         ("https://example.com/docs/quickstart", "claude", 4)]


def status_for(page: str, agent: str | None) -> int:
    if page == MOVED:
        return 404
    if page == FIREWALLED and agent in ANTHROPIC:
        return 403
    return 200


def build() -> list[str]:
    rng = random.Random(7)
    rows = []

    def add(day: int, page: str, agent: str | None, referrer: str = "-", query: str = "") -> None:
        when = START + timedelta(days=day, seconds=rng.randrange(86400))
        ip = f"198.51.100.{rng.randrange(1, 255)}" if agent else f"203.0.113.{rng.randrange(1, 255)}"
        ua = UA[agent] if agent else rng.choice(BROWSERS)
        status = status_for(page, agent)
        size = rng.randrange(4000, 42000) if status == 200 else 512
        rows.append((when, f'{ip} - - [{when:%d/%b/%Y:%H:%M:%S %z}] "GET {page}{query} HTTP/1.1" '
                           f'{status} {size} "{referrer}" "{ua}"'))

    for day in range(DAYS):
        for agent, n in CRAWL_PER_DAY.items():
            for _ in range(n):
                add(day, rng.choice(PAGES), agent)
        for agent, plan in LIVE_PER_DAY.items():
            for page, n in plan:
                for _ in range(n):
                    add(day, page, agent)
        for page, referrer, query, n in AI_CLICKS:
            for _ in range(n):
                add(day, page, None, referrer, query)
        for _ in range(40):
            page = rng.choice(PAGES + ["/changelog", "/changelog"])
            add(day, page, None, rng.choice(["-", "-", "https://www.google.com/"]))
        for _ in range(6):
            add(day, "/static/app.js", None, "https://example.com/")

    rows.sort(key=lambda r: r[0])
    return [line for _, line in rows]


def main() -> None:
    lines = build()
    (HERE / "access.example.log").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    csv_rows = ["url,engine,citations"] + [f"{u},{e},{n}" for u, e, n in CITED]
    (HERE / "cited.example.csv").write_text("\n".join(csv_rows) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(lines):,} log lines and {len(CITED)} citation rows")


if __name__ == "__main__":
    main()
