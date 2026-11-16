"""Standard library tests. No network. Run: python -m unittest discover -s tests -v"""
from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aeolog.__main__ import main  # noqa: E402
from aeolog.agents import AGENTS, classify, referrer_engine  # noqa: E402
from aeolog.parse import parse_line, read  # noqa: E402
from aeolog.report import Log, load_cited  # noqa: E402

LOG = str(ROOT / "examples" / "access.example.log")
CITED = str(ROOT / "examples" / "cited.example.csv")
LINE = ('198.51.100.7 - - [03/Oct/2026:10:00:00 +0000] "GET {} HTTP/1.1" {} 900 "{}" "{}"')
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0.0.0 Safari/537.36"


class Agents(unittest.TestCase):
    def test_openai_agents_do_not_collide(self):
        self.assertEqual(classify("compatible; GPTBot/1.2; +https://openai.com/gptbot").token, "GPTBot")
        self.assertEqual(classify("compatible; ChatGPT-User/1.0").token, "ChatGPT-User")
        self.assertEqual(classify("compatible; OAI-SearchBot/1.0").token, "OAI-SearchBot")

    def test_anthropic_agents_do_not_collide(self):
        self.assertEqual(classify("ClaudeBot/1.0").purpose, "training")
        self.assertEqual(classify("Claude-SearchBot/1.0").purpose, "search")
        self.assertEqual(classify("claude-user/1.0").purpose, "user")

    def test_browser_is_not_an_agent(self):
        self.assertIsNone(classify(CHROME))

    def test_every_agent_has_a_known_purpose(self):
        self.assertTrue(all(a.purpose in ("training", "search", "user") for a in AGENTS))
        self.assertEqual(len({a.token.lower() for a in AGENTS}), len(AGENTS))

    def test_referrer_subdomains(self):
        self.assertEqual(referrer_engine("www.perplexity.ai"), "perplexity")
        self.assertEqual(referrer_engine("chatgpt.com"), "chatgpt")
        self.assertIsNone(referrer_engine("www.google.com"))
        self.assertIsNone(referrer_engine("notchatgpt.com"))


class Parse(unittest.TestCase):
    def test_bot_line(self):
        hit = parse_line(LINE.format("/pricing/", 200, "-", "compatible; PerplexityBot/1.0"))
        self.assertEqual((hit.path, hit.status, hit.agent.token), ("/pricing", 200, "PerplexityBot"))
        self.assertIsNone(hit.referral)

    def test_referrer_click(self):
        hit = parse_line(LINE.format("/blog/a?x=1", 200, "https://chatgpt.com/", CHROME))
        self.assertEqual((hit.path, hit.referral, hit.agent), ("/blog/a", "chatgpt", None))

    def test_utm_click_without_referrer(self):
        hit = parse_line(LINE.format("/features?utm_source=chatgpt.com", 200, "-", CHROME))
        self.assertEqual(hit.referral, "chatgpt")

    def test_assets_and_garbage(self):
        self.assertTrue(parse_line(LINE.format("/static/app.js", 200, "-", CHROME)).is_asset)
        self.assertIsNone(parse_line("not a log line"))

    def test_common_format_without_user_agent(self):
        hit = parse_line('198.51.100.7 - - [03/Oct/2026:10:00:00 +0000] "GET / HTTP/1.1" 200 12')
        self.assertEqual((hit.path, hit.agent), ("/", None))


class Sample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log = Log(read([LOG]))
        cls.cited = load_cited(CITED)
        cls.gaps = cls.log.gaps(cls.cited)

    def has(self, gap, path, who):
        return any(r[:3] == [gap, path, who] for r in self.gaps)

    def test_assets_are_skipped_by_default(self):
        self.assertEqual(self.log.lines, 1680)
        self.assertEqual(Log(read([LOG], assets=True)).lines, 1764)

    def test_firewalled_page_is_reported_for_anthropic_only(self):
        self.assertTrue(self.has("blocked", "/blog/aeo-checklist", "Claude-User"))
        self.assertFalse(self.has("blocked", "/blog/aeo-checklist", "OAI-SearchBot"))

    def test_training_agents_are_never_reported_as_blocked(self):
        self.assertFalse(any(r[0] == "blocked" and r[2] in ("GPTBot", "ClaudeBot", "CCBot") for r in self.gaps))

    def test_moved_page_is_cited_without_a_fetch(self):
        self.assertTrue(self.has("cited, no fetch", "/docs/api-reference", "perplexity"))

    def test_pricing_is_read_but_not_cited(self):
        self.assertTrue(self.has("read, not cited", "/pricing", "chatgpt"))
        self.assertFalse(self.has("read, not cited", "/blog/compare-trackers", "chatgpt"))

    def test_changelog_is_not_indexed(self):
        self.assertTrue(self.has("not indexed", "/changelog", "all search agents"))

    def test_funnel_narrows(self):
        rows = {r[0]: [int(x) for x in r[1:]] for r in self.log.funnel(self.cited)}
        self.assertEqual(rows["chatgpt"], [13, 11, 3, 2, 2])
        self.assertEqual(set(rows), {"chatgpt", "claude", "perplexity"})

    def test_citation_gaps_need_an_export(self):
        self.assertFalse(any(r[0] in ("read, not cited", "cited, no fetch") for r in self.log.gaps(None)))


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(list(args))
        return code, out.getvalue()

    def test_views_run(self):
        for args in (["--by", "agent"], ["--by", "purpose"], ["--by", "path"], ["--funnel"], ["--json"]):
            code, out = self.run_cli(LOG, *args)
            self.assertEqual(code, 0)
            self.assertTrue(out.strip())

    def test_strict_exit_code(self):
        self.assertEqual(self.run_cli(LOG, "--gaps", "--strict")[0], 1)
        self.assertEqual(self.run_cli(LOG, "--gaps")[0], 0)

    def test_registry(self):
        code, out = self.run_cli("--agents")
        self.assertEqual(code, 0)
        self.assertIn("OAI-SearchBot", out)


class AiclicksExport(unittest.TestCase):
    def test_pages_and_engines(self):
        sys.path.insert(0, str(ROOT / "examples"))
        import aiclicks_cited

        calls = []

        def fake(path, params, key):
            calls.append((params["model"], params["page"]))
            last = params["model"] != "ChatGPT" or params["page"] == 2
            items = [{"url": "example.com/pricing", "frequency": 3}, {"url": "example.com/x", "frequency": 0}]
            return {"data": {"items": items, "total_pages": 2 if params["model"] == "ChatGPT" else 1},
                    "last": last}

        rows = aiclicks_cited.export("uuid", 14, "key", fetch=fake)
        self.assertEqual(calls, [("ChatGPT", 1), ("ChatGPT", 2), ("Claude", 1), ("Perplexity", 1)])
        self.assertEqual(rows[0], ("https://example.com/pricing", "chatgpt", 3))
        self.assertEqual(len(rows), 4)


if __name__ == "__main__":
    unittest.main()
