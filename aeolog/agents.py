"""
Registry of AI related user agents and referrers.

Each agent has a purpose, and the purpose decides what blocking it costs you:

    training   collects pages that may be used to train models
    search     builds the index an engine retrieves from when it answers
    user       fetches one page live because a person asked a question

Only `search` and `user` agents decide whether a page can be retrieved and
cited in a live answer. Tokens are matched as case insensitive substrings of
the User-Agent header, longest token first.

Not listed on purpose: Google-Extended and Applebot-Extended. They are
robots.txt control tokens, not crawlers, and never appear in a log.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

PURPOSES = ("training", "search", "user")
RETRIEVAL = ("search", "user")


class Agent(NamedTuple):
    token: str
    vendor: str
    engine: Optional[str]  # engine id used in citation exports, None if no single engine
    purpose: str


AGENTS = (
    Agent("GPTBot", "OpenAI", "chatgpt", "training"),
    Agent("OAI-SearchBot", "OpenAI", "chatgpt", "search"),
    Agent("ChatGPT-User", "OpenAI", "chatgpt", "user"),
    Agent("ClaudeBot", "Anthropic", "claude", "training"),
    Agent("Claude-SearchBot", "Anthropic", "claude", "search"),
    Agent("Claude-User", "Anthropic", "claude", "user"),
    Agent("PerplexityBot", "Perplexity", "perplexity", "search"),
    Agent("Perplexity-User", "Perplexity", "perplexity", "user"),
    Agent("meta-externalagent", "Meta", "meta-ai", "training"),
    Agent("meta-externalfetcher", "Meta", "meta-ai", "user"),
    Agent("MistralAI-User", "Mistral", "le-chat", "user"),
    Agent("DuckAssistBot", "DuckDuckGo", "duckassist", "user"),
    Agent("CCBot", "Common Crawl", None, "training"),
    Agent("Bytespider", "ByteDance", None, "training"),
    # Classic search crawlers whose index also feeds AI answers.
    Agent("Googlebot", "Google", "google-ai", "search"),
    Agent("bingbot", "Microsoft", "copilot", "search"),
)

_BY_LENGTH = tuple(sorted(AGENTS, key=lambda a: -len(a.token)))
BY_TOKEN = {a.token: a for a in AGENTS}

# Referrer host -> engine id. A person arriving from one of these clicked a
# link inside an AI answer.
REFERRERS = {
    "chatgpt.com": "chatgpt",
    "chat.openai.com": "chatgpt",
    "perplexity.ai": "perplexity",
    "claude.ai": "claude",
    "gemini.google.com": "google-ai",
    "copilot.microsoft.com": "copilot",
    "grok.com": "grok",
    "chat.deepseek.com": "deepseek",
    "meta.ai": "meta-ai",
    "chat.mistral.ai": "le-chat",
}

# ChatGPT tags outbound links, and the tag survives when the Referer header is stripped.
UTM_SOURCES = {"chatgpt.com": "chatgpt"}


def classify(user_agent: str) -> Optional[Agent]:
    """Return the Agent a User-Agent string belongs to, or None for everything else."""
    ua = user_agent.lower()
    for agent in _BY_LENGTH:
        if agent.token.lower() in ua:
            return agent
    return None


def referrer_engine(host: str) -> Optional[str]:
    """Map a referrer host to an engine id. Subdomains such as www. are accepted."""
    host = host.lower().split(":")[0]
    while host:
        if host in REFERRERS:
            return REFERRERS[host]
        _, _, host = host.partition(".")
    return None
